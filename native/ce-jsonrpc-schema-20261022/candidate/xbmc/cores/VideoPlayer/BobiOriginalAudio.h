/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <cstdint>
#include <string>
#include <tuple>
#include <vector>

// Bind the hint to the actual initial open. A transport capsule owns its audio
// choice even when the child item also contains a valid cached language hint.
inline bool BobiOriginalAudioHintBound(const std::string& language,
    const std::string& request, const std::string& identity, const std::string& urlSha,
    const std::string& hintRequest, const std::string& hintIdentity,
    const std::string& hintUrlSha, bool handoffOpen)
{
  return !handoffOpen && request.size() == 32 &&
      request.find_first_not_of("0123456789abcdef") == std::string::npos &&
      !identity.empty() && identity.size() <= 1024 && language.size() == 2 &&
      language.find_first_not_of("abcdefghijklmnopqrstuvwxyz") == std::string::npos &&
      urlSha.size() == 64 && urlSha.find_first_not_of("0123456789abcdef") == std::string::npos &&
      hintRequest == request && hintIdentity == identity && hintUrlSha == urlSha;
}

inline bool BobiAudioExplicitCommentary(std::string name, bool flagged)
{
  if (flagged)
    return true;
  for (char& value : name)
    if (value >= 'A' && value <= 'Z')
      value += 'a' - 'A';
  for (const auto* marker : {"commentary", "commentaire", "kommentar", "comentario",
                              "commento", "评论", "評論", "解説"})
    if (name.find(marker) != std::string::npos)
      return true;
  return false; // Absence of a known marker is NOT verified non-commentary.
}

// No ordinal is part of identity. VideoPlayer's SelectionStream.id comes from
// the demuxer's uniqueId. Access is serialized by CVideoPlayer::m_bobiLock.
struct BobiAudioKey
{
  int source{0};
  int64_t demuxerId{-1};
  int uniqueId{-1};
  std::string language;
  std::string codec;
  int channels{0};
  std::string name;
  unsigned flags{0};

  bool operator==(const BobiAudioKey& other) const
  {
    return std::tie(source, demuxerId, uniqueId, language, codec, channels, name, flags) ==
        std::tie(other.source, other.demuxerId, other.uniqueId, other.language,
                 other.codec, other.channels, other.name, other.flags);
  }
};

struct BobiAudioCandidate
{
  BobiAudioKey key;
  int index{-1};
  bool originalLanguage{false}; // normalized language match, not commentary
};

struct BobiAudioPlan
{
  std::string language;
  int retainedIndex{-1};
  uint64_t generation{0};
};

class CBobiOriginalAudio
{
public:
  void Clear()
  {
    ++m_generation;
    m_language.clear();
    m_pending = m_prepared = m_retained = false;
    m_key = {};
  }

  void Reset(const std::string& language, uint64_t epoch)
  {
    Clear();
    m_epoch = epoch;
    m_language = language;
    m_pending = !language.empty();
  }

  const std::string& Language() const { return m_language; }

  BobiAudioPlan Prepare(uint64_t epoch, bool original, int explicitIndex,
                        const std::vector<BobiAudioCandidate>& streams, bool initialOpen,
                        int currentSource, int64_t currentDemuxer, int currentId)
  {
    if (epoch != m_epoch || !original || explicitIndex >= 0)
    {
      Clear();
      return {};
    }
    if (m_language.empty() || streams.empty())
      return {};
    if (m_pending)
    {
      if (!initialOpen)
      {
        Clear();
        return {};
      }
      m_pending = false;
      for (const auto& stream : streams)
        if (stream.originalLanguage)
        {
          m_prepared = true;
          return {m_language, -1, m_generation};
        }
      Clear(); // No original track: the old ordering is entirely unchanged.
      return {};
    }
    if (m_retained)
    {
      if (m_key.source != currentSource || m_key.demuxerId != currentDemuxer ||
          m_key.uniqueId != currentId)
      {
        Clear(); // Preserve the current stream, not a previously selected one.
        return {};
      }
      int index = -1;
      for (const auto& stream : streams)
        if (stream.key == m_key)
        {
          if (index >= 0)
          {
            Clear(); // Ambiguous stream identity must not become authority.
            return {};
          }
          index = stream.index;
        }
      if (index >= 0)
        return {"", index, m_generation};
      Clear(); // Never rerun the language guess after initial selection.
    }
    return {};
  }

  void Selected(const BobiAudioPlan& plan, const BobiAudioCandidate* selected)
  {
    if (!m_prepared || plan.language.empty() || plan.generation != m_generation)
      return;
    m_prepared = false;
    if (!selected)
    {
      m_pending = true; // No successful audio open yet; retry only while OPEN.
      return;
    }
    if (selected->originalLanguage)
    {
      m_key = selected->key;
      m_retained = true;
    }
    else
      Clear();
  }

private:
  std::string m_language;
  uint64_t m_epoch{0};
  uint64_t m_generation{0};
  bool m_pending{false};
  bool m_prepared{false};
  bool m_retained{false};
  BobiAudioKey m_key;
};
