#include "cores/BobiHandoff.h"

#include <atomic>
#include <cassert>
#include <iostream>
#include <thread>

static std::shared_ptr<BobiHandoffCapsule> fixture()
{
  auto capsule = std::make_shared<BobiHandoffCapsule>();
  capsule->identity = "same-complete-file";
  capsule->guiUserIntent = CBobiGuiGate::Get().Snapshot().userIntent;
  capsule->expires = std::chrono::steady_clock::now() + std::chrono::seconds(30);
  auto& r = capsule->receipt;
  r["token"] = "opaque-native-token";
  r["command_id"] = "capture-command";
  r["parent_native_instance"] = "parent-instance";
  r["parent_request_id"] = "parent-request";
  r["parent_selection_epoch"] = static_cast<uint64_t>(10);
  r["expected_child_epoch"] = static_cast<uint64_t>(11);
  r["child_request_id"] = "child-request";
  r["position_ms"] = static_cast<int64_t>(123456);
  r["subtitle_intent"] = static_cast<uint64_t>(5);
  r["audio_intent"] = static_cast<uint64_t>(3);
  capsule->settings.m_SubtitleOn = false;
  capsule->settings.m_SubtitleDelay = 1.25f;
  capsule->settings.m_AudioDelay = -0.375f;
  capsule->settings.m_AudioStream = 2;
  capsule->external = "/storage/private-manual.ass";
  return capsule;
}

int main()
{
  // The automatic subtitle receipt proof survives even if the user now has
  // subtitles Off or a different manual external subtitle selected.
  CVariant parent(CVariant::VariantTypeObject);
  parent["subtitle_file_applied"] = true;
  parent["subtitle_file_sha256"] = std::string(64, 'a');
  auto proofCapsule = fixture();
  assert(proofCapsule->CaptureSubtitleProof(parent));
  proofCapsule->externalSha = std::string(64, 'b');
  CVariant child(CVariant::VariantTypeObject);
  proofCapsule->RestoreSubtitleProof(child);
  assert(child["subtitle_file_applied"].asBoolean());
  assert(child["subtitle_file_sha256"].asString() == std::string(64, 'a'));
  for (const auto& invalid : {std::string(), std::string(63, 'a'), std::string(64, 'A'), std::string(64, 'g')})
  {
    parent["subtitle_file_sha256"] = invalid;
    assert(!proofCapsule->CaptureSubtitleProof(parent));
  }
  parent.erase("subtitle_file_sha256");
  assert(!proofCapsule->CaptureSubtitleProof(parent));
  parent["subtitle_file_applied"] = "true";
  assert(!proofCapsule->CaptureSubtitleProof(parent));
  parent["subtitle_file_applied"] = false;
  parent["subtitle_file_sha256"] = std::string(64, 'c');
  assert(proofCapsule->CaptureSubtitleProof(parent));
  proofCapsule->RestoreSubtitleProof(child);
  assert(!child["subtitle_file_applied"].asBoolean());
  assert(!child.isMember("subtitle_file_sha256"));

  auto& gate = CBobiHandoff::Get();
  auto c = fixture();
  gate.Capture(c);
  assert(gate.Status()["phase"].asString() == "CAPTURED");
  assert(gate.RequiresToken("child-request"));
  assert(!gate.RequiresToken("ordinary-request"));
  assert(!gate.CanOpen("opaque-native-token", "child-request", 11, c->identity));
  assert(!gate.Captured("wrong-token"));
  assert(gate.Stop(c, "stop-command", 123789));
  assert(!gate.CanOpen("opaque-native-token", "child-request", 11, c->identity));
  gate.Terminal("parent-instance", "STOP");
  assert(!gate.Stop(c, "duplicate-stop", 0));
  assert(gate.Status()["position_ms"].asInteger() == 123789);
  assert(gate.Status()["command_id"].asString() == "stop-command");
  assert(!gate.CanOpen("wrong-token", "child-request", 11, c->identity));
  assert(!gate.CanOpen("opaque-native-token", "different-child", 11, c->identity));
  assert(!gate.CanOpen("opaque-native-token", "child-request", 12, c->identity));
  assert(!gate.CanOpen("opaque-native-token", "child-request", 11, "different-file"));
  gate.SelectionChanged(11, "child-request");
  assert(gate.CanOpen("opaque-native-token", "child-request", 11, c->identity));
  std::atomic<int> consumed{0};
  auto consume = [&]() {
    if (gate.Consume("opaque-native-token", "child-request", 11, c->identity, "new-instance"))
      ++consumed;
  };
  std::thread a(consume), b(consume);
  a.join(); b.join();
  assert(consumed == 1);
  assert(!gate.Restoring("other-instance"));
  auto restore = gate.Restoring("new-instance");
  assert(restore && !restore->settings.m_SubtitleOn);
  assert(restore->settings.m_SubtitleDelay == 1.25f);
  assert(restore->settings.m_AudioDelay == -0.375f);
  assert(restore->settings.m_AudioStream == 2);
  assert(restore->external == "/storage/private-manual.ass");
  assert(gate.Status()["external"].isNull()); // No private reference in receipts.
  assert(!gate.Restored("other-instance", CVariant(), 11));
  assert(gate.Status()["phase"].asString() == "CONSUMED");
  assert(gate.Restored("new-instance", CVariant(CVariant::VariantTypeObject), 11));
  assert(gate.Status()["phase"].asString() == "RESTORED");
  assert(!gate.Restoring("new-instance"));
  assert(!gate.Consume("opaque-native-token", "child-request", 11, c->identity, "again"));

  for (const auto phase : {"capture", "stop", "consume"})
  {
    c = fixture();
    gate.Capture(c);
    if (std::string(phase) != "capture") assert(gate.Stop(c, "stop-command", 123456));
    if (std::string(phase) != "capture") gate.Terminal("parent-instance", "STOP");
    if (std::string(phase) == "consume") assert(gate.Consume("opaque-native-token", "child-request", 11, c->identity, "new-instance"));
    gate.Invalidate("parent-instance", "USER_INTENT");
    assert(gate.Status()["phase"].asString() == "REJECTED");
    assert(!gate.Captured("opaque-native-token"));
    assert(!gate.Restoring("new-instance"));
  }
  c = fixture(); gate.Capture(c);
  gate.SelectionChanged(11, "child-request"); // Cannot reserve child before STOP.
  assert(gate.Status()["phase"].asString() == "REJECTED");
  c = fixture(); gate.Capture(c); assert(gate.Stop(c, "stop", 100));
  gate.Terminal("parent-instance", "STOP");
  gate.SelectionChanged(11, "different-child");
  assert(gate.Status()["phase"].asString() == "REJECTED");
  c = fixture(); gate.Capture(c); assert(gate.Stop(c, "stop", 100));
  gate.Terminal("parent-instance", "STOP");
  gate.SelectionChanged(12, "child-request");
  assert(gate.Status()["phase"].asString() == "REJECTED");
  c = fixture(); c->expires = std::chrono::steady_clock::now() - std::chrono::seconds(1);
  gate.Capture(c);
  assert(gate.Status()["reason"].asString() == "EXPIRED");
  assert(!gate.CanOpen("opaque-native-token", "child-request", 11, c->identity));
  for (const auto reason : {"ERROR", "NATURAL_EOF", "SUPERSEDED"})
  {
    c = fixture(); gate.Capture(c); assert(gate.Stop(c, "stop", 100));
    gate.Terminal("parent-instance", reason);
    assert(gate.Status()["phase"].asString() == "REJECTED");
    assert(!gate.CanOpen("opaque-native-token", "child-request", 11, c->identity));
  }
  c = fixture(); gate.Capture(c); assert(gate.Stop(c, "stop", 100));
  gate.Terminal("parent-instance", "STOP");
  CBobiGuiGate::Get().UserReturn();
  assert(!gate.CanOpen("opaque-native-token", "child-request", 11, c->identity));
  assert(gate.Status()["reason"].asString() == "GUI_USER_INTENT");
  assert(gate.RequiresToken("child-request"));
  std::cout << "PASS actual native capsule: one-shot, epoch, child, file, expiry, intent, settings, privacy\n";
}
