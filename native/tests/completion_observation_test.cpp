// SPDX-License-Identifier: GPL-2.0-or-later
#include "cores/VideoPlayer/BobiCompletion.h"
#include <cassert>
#include <limits>

int main()
{
  using namespace std::chrono;
  const auto now = CBobiCompletion::Clock::time_point(seconds(100));
  for (const int speed : {1, 8, 32})
  {
    CBobiCompletion observation;
    observation.Observe(100000 - speed * 1000, 100000, true, now);
    observation.Observe(99960, 100000, true, now + seconds(1));
    const auto end = observation.Snapshot(now + seconds(1) + milliseconds(20));
    assert(end["valid"].asBoolean());
    assert(end["position_ms"].asInteger() == 99960);
    assert(end["duration_ms"].asInteger() == 100000);
    assert(end["age_us"].asInteger() == 20000);
  }
  CBobiCompletion stalled;
  stalled.Observe(99000, 100000, true, now);
  stalled.Observe(99000, 100000, true, now + seconds(10));
  assert(stalled.Snapshot(now + seconds(10))["age_us"].asInteger() == 10000000);
  stalled.Observe(99000, 100000, false, now + seconds(11));
  stalled.Observe(99000, 100000, true, now + seconds(12));
  assert(stalled.Snapshot(now + seconds(12))["age_us"].asInteger() == 12000000);
  stalled.Invalidate(99000);
  stalled.Observe(99000, 100000, false, now + seconds(11));
  stalled.Observe(99000, 100000, true, now + seconds(12));
  assert(!stalled.Snapshot(now + seconds(12))["valid"].asBoolean());
  stalled.Observe(1000, 100000, true, now + seconds(13));
  assert(stalled.Snapshot(now + seconds(13))["position_ms"].asInteger() == 1000);
  stalled.Observe(22000, 100000, true, now + seconds(14));
  assert(stalled.Snapshot(now + seconds(20))["position_ms"].asInteger() == 22000);
  assert(!stalled.Snapshot(now)["valid"].asBoolean());
  for (double invalid : {-1.0, std::numeric_limits<double>::quiet_NaN(),
                         std::numeric_limits<double>::infinity()})
  {
    stalled.Observe(invalid, 100000, true, now);
    assert(!stalled.Snapshot(now)["valid"].asBoolean());
  }
  stalled.Observe(100000, 0, true, now);
  assert(!stalled.Snapshot(now)["valid"].asBoolean());
  stalled.Observe(100000, 100000, false, now);
  assert(!stalled.Snapshot(now)["valid"].asBoolean());
}
