/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "cores/VideoSettings.h"
#include "cores/BobiGuiGate.h"
#include "utils/Variant.h"

#include <chrono>
#include <memory>
#include <mutex>
#include <string>

// One process-local, single-use presentation capsule. The receipt survives the
// old IPlayer, but file references and settings never leave native memory.
struct BobiHandoffCapsule
{
  CVariant receipt{CVariant::VariantTypeObject};
  CVideoSettings settings;
  std::string identity;
  std::string catalog;
  std::string video;
  std::string audio;
  std::string subtitle;
  std::string external;
  std::string companion;
  std::string externalSha;
  std::string companionSha;
  int externalId{-1};
  uint64_t subtitleAutoIntent{0};
  uint64_t guiUserIntent{0};
  bool subtitleFileApplied{false};
  std::string subtitleFileSha256;
  std::chrono::steady_clock::time_point expires;

  bool CaptureSubtitleProof(const CVariant& state)
  {
    const auto& applied = state["subtitle_file_applied"];
    if (!applied.isNull() && !applied.isBoolean()) return false;
    subtitleFileApplied = applied.asBoolean();
    subtitleFileSha256.clear();
    if (!subtitleFileApplied) return true;
    const auto& proof = state["subtitle_file_sha256"];
    if (!proof.isString()) return false;
    const auto hash = proof.asString();
    if (hash.size() != 64 || hash.find_first_not_of("0123456789abcdef") != std::string::npos)
      return false;
    // This is the already accepted automatic-subtitle receipt proof. It is
    // independent of the currently selected external track's content hash:
    // the user may have subsequently selected another subtitle or Off.
    subtitleFileSha256 = hash;
    return true;
  }

  void RestoreSubtitleProof(CVariant& state) const
  {
    state["subtitle_file_applied"] = subtitleFileApplied;
    if (subtitleFileApplied)
      state["subtitle_file_sha256"] = subtitleFileSha256;
    else
      state.erase("subtitle_file_sha256");
  }
};

class CBobiHandoff
{
public:
  static CBobiHandoff& Get()
  {
    static CBobiHandoff value;
    return value;
  }

  CVariant Status()
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    Expire();
    return m_receipt;
  }

  void Capture(const std::shared_ptr<BobiHandoffCapsule>& capsule)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    m_capsule = capsule;
    m_boundChild = capsule->receipt["child_request_id"].asString();
    m_receipt = capsule->receipt;
    m_receipt["phase"] = "CAPTURED";
    m_receipt["restorable"] = true;
    m_receipt["reason"] = "";
  }

  std::shared_ptr<BobiHandoffCapsule> Captured(const std::string& token)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    Expire();
    return m_capsule && m_receipt["phase"].asString() == "CAPTURED" &&
        m_receipt["token"].asString() == token ? m_capsule : nullptr;
  }

  bool Stop(const std::shared_ptr<BobiHandoffCapsule>& capsule,
            const std::string& command, int64_t position)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    Expire();
    if (!m_capsule || capsule != m_capsule || m_receipt["phase"].asString() != "CAPTURED")
      return false;
    m_receipt["phase"] = "STOP_REQUESTED";
    m_receipt["command_id"] = command;
    m_receipt["position_ms"] = position;
    capsule->receipt = m_receipt;
    return true;
  }

  void Terminal(const std::string& instance, const std::string& reason)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    if (!m_capsule || m_receipt["parent_native_instance"].asString() != instance)
      return;
    if (m_receipt["phase"].asString() == "STOP_REQUESTED" && reason == "STOP")
    {
      m_receipt["phase"] = "STOPPED";
      m_capsule->receipt = m_receipt;
    }
    else
      Invalidate(instance, "PARENT_TERMINAL_" + reason);
  }

  bool CanOpen(const std::string& token, const std::string& request,
               uint64_t epoch, const std::string& identity)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    Expire();
    return m_capsule && m_receipt["phase"].asString() == "STOPPED" &&
        m_receipt["token"].asString() == token &&
        m_receipt["child_request_id"].asString() == request &&
        m_receipt["expected_child_epoch"].asUnsignedInteger() == epoch &&
        m_capsule->identity == identity;
  }

  bool RequiresToken(const std::string& request)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    // A malformed/lost child payload must not turn into an ordinary open with
    // default tracks, including a retry after this capsule was rejected.
    return !request.empty() && m_boundChild == request;
  }

  bool Consume(const std::string& token, const std::string& request,
               uint64_t epoch, const std::string& identity, const std::string& instance)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    if (!CanOpen(token, request, epoch, identity))
      return false;
    m_receipt["phase"] = "CONSUMED";
    m_receipt["native_instance"] = instance;
    m_capsule->receipt = m_receipt;
    return true;
  }

  std::shared_ptr<BobiHandoffCapsule> Restoring(const std::string& instance)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    Expire();
    return m_capsule && m_receipt["phase"].asString() == "CONSUMED" &&
        m_receipt["native_instance"].asString() == instance ? m_capsule : nullptr;
  }

  bool Restored(const std::string& instance, const CVariant& restored, uint64_t epoch)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    if (!Restoring(instance))
      return false;
    if (m_receipt["expected_child_epoch"].asUnsignedInteger() != epoch)
    {
      Invalidate(instance, "SELECTION_CHANGED");
      return false;
    }
    m_receipt["phase"] = "RESTORED";
    m_receipt["restored"] = restored;
    m_capsule.reset();
    return true;
  }

  void Reject(const CVariant& command, const std::string& reason)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    m_capsule.reset();
    if (m_receipt["token"].asString() != command["handoff_token"].asString())
      m_receipt = CVariant(CVariant::VariantTypeObject);
    m_receipt["protocol"] = 1;
    m_receipt["command_id"] = command["command_id"];
    m_receipt["phase"] = "REJECTED";
    m_receipt["restorable"] = false;
    m_receipt["reason"] = reason;
  }

  void Invalidate(const std::string& instance, const std::string& reason)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    if (m_capsule && (instance.empty() ||
        m_receipt["parent_native_instance"].asString() == instance ||
        m_receipt["native_instance"].asString() == instance))
    {
      m_capsule.reset();
      m_receipt["phase"] = "REJECTED";
      m_receipt["restorable"] = false;
      m_receipt["reason"] = reason;
    }
  }

  void SelectionChanged(uint64_t epoch, const std::string& request)
  {
    std::lock_guard<std::recursive_mutex> lock(m_mutex);
    if (m_capsule && !(m_receipt["phase"].asString() == "STOPPED" &&
        m_receipt["expected_child_epoch"].asUnsignedInteger() == epoch &&
        m_receipt["child_request_id"].asString() == request))
      Invalidate("", "SELECTION_CHANGED");
  }

private:
  void Expire()
  {
    if (m_capsule && m_capsule->guiUserIntent != CBobiGuiGate::Get().Snapshot().userIntent)
      Invalidate("", "GUI_USER_INTENT");
    if (m_capsule && m_receipt["phase"].asString() != "CONSUMED" &&
        std::chrono::steady_clock::now() > m_capsule->expires)
      Invalidate("", "EXPIRED");
  }
  std::recursive_mutex m_mutex;
  std::shared_ptr<BobiHandoffCapsule> m_capsule;
  std::string m_boundChild;
  CVariant m_receipt{CVariant::VariantTypeObject};
};
