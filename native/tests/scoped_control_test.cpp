/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cores/VideoPlayer/BobiScopedControl.h"
#include <cassert>
#include <limits>

int main()
{
  CVariant state(CVariant::VariantTypeObject);
  state["native_instance"] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  state["request_id"] = std::string(32, 'b');
  state["phase"] = "AV_STARTED";
  for (const auto* key : {"user_intent", "subtitle_intent", "audio_intent", "sequence", "open_epoch"})
    state[key] = uint64_t{7};
  CVariant command = state;
  command["control_protocol"] = 1;
  command["action"] = "seek";
  command["file_sha256"] = std::string(64, 'c');
  command["expected_sequence"] = uint64_t{7};
  command["selection_epoch"] = uint64_t{7};
  command["command_id"] = std::string(32, 'd');
  assert(BobiScopedMatches(command, state, 7, std::string(64, 'c')));
  for (const auto* key : {"user_intent", "subtitle_intent", "audio_intent", "expected_sequence", "selection_epoch"})
  {
    auto stale = command;
    stale[key] = uint64_t{8};
    assert(!BobiScopedMatches(stale, state, 7, std::string(64, 'c')));
  }
  for (const auto* key : {"native_instance", "request_id", "file_sha256"})
  {
    auto stale = command;
    stale[key] = "different";
    assert(!BobiScopedMatches(stale, state, 7, std::string(64, 'c')));
  }
  auto manual = state;
  manual["subtitle_intent"] = uint64_t{8};
  assert(!BobiScopedMatches(command, manual, 7, std::string(64, 'c')));
  assert(!BobiScopedMatches(command, state, 8, std::string(64, 'c')));
  assert(BobiScopedSeek(CVariant(0), 5000, true));
  assert(BobiScopedSeek(CVariant(4999), 5000, true));
  for (const auto& value : {CVariant(-1), CVariant(5000), CVariant(true),
       CVariant(1.5), CVariant(std::numeric_limits<double>::infinity())})
    assert(!BobiScopedSeek(value, 5000, true));
  assert(!BobiScopedSeek(CVariant(1), 5000, false));
  assert(!BobiScopedSeek(CVariant(0), 0, true));
  CBobiScopedCommands ledger;
  assert(ledger.Admit(command));
  assert(ledger.Recent()[0]["status"].asString() == "queued");
  assert(!ledger.Admit(command));
  auto reused = command;
  reused["action"] = "subtitle_visible";
  assert(!ledger.Admit(reused));
  assert(ledger.Finish(command, "applied")["status"].asString() == "applied");
  assert(ledger.Finish(command, "failed").isNull());
  assert(!ledger.Admit(command));
  assert(ledger.Recent()[0]["status"].asString() == "applied");
  ledger.Reset();
  auto newer = command;
  newer["native_instance"] = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee";
  assert(ledger.Admit(newer));
  assert(ledger.Finish(command, "rejected").isNull());
  assert(ledger.Recent()[0]["status"].asString() == "queued");
}
