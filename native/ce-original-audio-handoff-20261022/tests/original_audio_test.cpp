#include "cores/VideoPlayer/BobiOriginalAudio.h"
#include "actual_audio_comparator.h"
#include <cassert>
#include <iostream>

int main()
{
  const std::string request(32, 'a'), other(32, 'b'), digest(64, 'c');
  auto bound = [&](std::string language, std::string hintRequest,
                   std::string identity, std::string hintDigest, bool capsule = false) {
    return BobiOriginalAudioHintBound(language, request, "file-one", digest,
                                     hintRequest, identity, hintDigest, capsule);
  };
  assert(bound("ja", request, "file-one", digest));
  assert(!bound("ja", other, "file-one", digest));
  assert(!bound("ja", request, "file-two", digest));
  assert(!bound("ja", request, "file-one", std::string(64, 'd')));
  assert(!bound("", request, "file-one", digest));
  assert(!bound("JA", request, "file-one", digest));
  assert(!bound("ja", request, "file-one", digest, true));

  SelectionStream english{0, StreamFlags::FLAG_DEFAULT, 2, "eng", "eac3", "English"};
  SelectionStream japanese{3, 0, 6, "jpn", "ac3", "Japanese"};
  PredicateAudioFilter ordinary(-1, false), original(-1, false, "jpn"), saved(0, false, "jpn");
  assert(ordinary(english, japanese)); // Exact observed no-hint counterexample.
  assert(original(japanese, english) && !original(english, japanese));
  assert(saved(english, japanese));
  for (const auto& title : {"Director Commentary", "COMMENTAIRE", "Kommentar", "解説"})
  {
    auto commentary = japanese; commentary.name = title;
    assert(!original(commentary, english));
  }
  auto commentary = japanese; commentary.flags = StreamFlags::FLAG_COMMENT;
  assert(!original(commentary, english));
  assert(BobiAudioExplicitCommentary("Clean name", true));
  assert(!BobiAudioExplicitCommentary("Japanese", false));

  const BobiAudioCandidate en{{1, 2, 10, "eng", "eac3", 2, "English", 8}, 0, false};
  const BobiAudioCandidate ja{{1, 2, 40, "jpn", "ac3", 6, "Japanese", 0}, 3, true};
  std::vector<BobiAudioCandidate> streams{en, ja};
  CBobiOriginalAudio audio;
  auto prepare = [&](uint64_t epoch = 10, bool initial = true, int explicitIndex = -1,
                     bool preference = true) {
    return audio.Prepare(epoch, preference, explicitIndex, streams, initial, 1, 2, 40);
  };
  audio.Reset("jpn", 10);
  auto plan = prepare();
  assert(plan.language == "jpn" && plan.retainedIndex == -1);
  audio.Selected(plan, &ja);
  streams[1].index = 1;
  auto retained = prepare(10, false);
  assert(retained.language.empty() && retained.retainedIndex == 1); // Stable key, not 3.
  audio.Clear(); // Manual change after AV.
  assert(prepare(10, false).retainedIndex == -1);
  audio.Reset("jpn", 10);
  plan = prepare();
  audio.Clear(); // Manual change during the native OpenStream call.
  audio.Selected(plan, &ja); // The stale completion cannot resurrect authority.
  assert(prepare().language.empty());
  audio.Reset("jpn", 10);
  audio.Clear(); // Manual choice before initial stream selection.
  assert(prepare().language.empty());
  audio.Reset("jpn", 10);
  assert(prepare(11).language.empty()); // Selection epoch advanced.
  audio.Reset("jpn", 10);
  assert(prepare(10, true, 0).language.empty()); // Saved explicit selection.
  audio.Reset("jpn", 10);
  assert(prepare(10, true, -1, false).language.empty());
  audio.Reset("jpn", 10);
  assert(prepare(10, false).language.empty()); // Late metadata / AV start.
  audio.Reset("jpn", 10);
  streams = {en};
  assert(prepare().language.empty()); // No language match retains ordinary ordering.
  streams = {en, ja};
  assert(prepare().language.empty()); // A later matching stream cannot rerun the hint.
  audio.Reset("jpn", 10);
  plan = prepare(); audio.Selected(plan, nullptr);
  assert(prepare().language == "jpn"); // Retry failed audio open while still OPEN.
  assert(prepare(10, false).language.empty());
  audio.Reset("jpn", 10);
  plan = prepare(); audio.Selected(plan, &ja);
  streams.push_back(ja);
  assert(prepare(10, false).retainedIndex == -1); // Duplicate identity fails closed.
  streams = {en, ja};
  audio.Reset("jpn", 10);
  plan = prepare(); audio.Selected(plan, &ja);
  streams[1].key.codec = "different";
  assert(prepare(10, false).retainedIndex == -1); // Catalogue mutation is not a key.
  audio.Reset("jpn", 10);
  plan = prepare(); audio.Selected(plan, &ja);
  audio.Reset("", 11); // New episode without its own bound hint.
  assert(prepare(11).language.empty());
  audio.Reset(bound("ja", request, "file-one", digest, true) ? "jpn" : "", 11);
  assert(prepare(11, true, 0).language.empty()); // Capsule selected English wins.
  std::cout << "PASS native original audio: binding, comparator, commentary, saved/manual, epoch, stable key, new episode, capsule\n";
}
