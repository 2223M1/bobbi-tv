#include "cores/BobiGuiGate.h"
#include "cores/BobiOpenGate.h"
#include "cores/BobiReadStatus.h"
#include "dialogs/BobiSubtitleFile.h"
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>

int main(int argc, char** argv)
{
  assert(argc == 2);
  auto& gate = CBobiOpenGate::Get();
  const std::string first(32, 'a'), second(32, 'b');
  assert(gate.Reserve(0, first));
  assert(!gate.Reserve(0, second));
  assert(gate.Allowed(first));
  assert(gate.Claim(first));
  assert(!gate.Claim(first));
  assert(!gate.Allowed(second));
  assert(gate.Reserve(1, second));
  assert(BobiControlEpochAllows("stop", 1, 2, 2));
  assert(!BobiControlEpochAllows("resume", 1, 2, 2));
  assert(!BobiControlEpochAllows("stop", 1, 2, 3));
  assert(gate.Claim(""));
  assert(!gate.Allowed(second));
  auto& gui = CBobiGuiGate::Get();
  assert(gui.Claim(0, 0, "instance-a"));
  assert(!gui.Claim(0, 0, "instance-a"));
  gui.Confirm("instance-a");
  assert(gui.Snapshot().fullscreenInstance == "instance-a");
  gui.UserReturn();
  assert(!gui.Claim(0, 0, "instance-b"));
  gui.OpenWindow(1, {"token-a", "subtitles", first, "instance-a"});
  assert(gui.AllowsPause("pause", "token-a", "instance-a"));
  assert(!gui.AllowsPause("pause", "token-b", "instance-a"));
  assert(!gui.AllowsPause("resume", "token-a", "instance-a"));
  assert(gui.CloseWindow(1));
  assert(gui.AllowsPause("resume", "token-a", "instance-a"));
  assert(BobiDemuxReadFailure(-5, 0, -1, -2, -3) == -5);
  assert(BobiDemuxReadFailure(-1, -5, -1, -2, -3) == -5);
  assert(BobiDemuxReadFailure(-1, 0, -1, -2, -3) == 0);
  assert(!BobiClearInputReadError(2048, true));
  std::array<uint8_t, 4096> bytes{};
  assert(BobiReadBlocks([](uint8_t*, int) { return -5; }, bytes.data(), 2048) == -1);
  assert(BobiReadBlocks([](uint8_t*, int length) { return length; }, bytes.data(), 4096) == 2);
  namespace fs = std::filesystem;
  const auto directory = fs::absolute(fs::u8path(argv[1]));
  fs::create_directories(directory);
  const auto file = directory / (first + ".srt");
  { std::ofstream stream(file, std::ios::binary); stream << "caption"; }
  assert(BobiVerifiedSubtitleFile(directory.u8string(), file.u8string()));
  assert(!BobiVerifiedSubtitleFile(directory.u8string(), (directory / ".." / "elsewhere.srt").u8string()));
  assert(!BobiVerifiedSubtitleFile(directory.u8string(), (directory / "plain.srt").u8string()));
  std::string received;
  assert(BobiReadVerifiedSubtitle(directory.u8string(), file.u8string(), 7,
      [&](const void* data, size_t count) { received.append(static_cast<const char*>(data), count); }, [] { return true; }));
  assert(received == "caption");
  assert(!BobiReadVerifiedSubtitle(directory.u8string(), file.u8string(), 8, [](const void*, size_t) {}, [] { return true; }));
  assert(!BobiReadVerifiedSubtitle(directory.u8string(), file.u8string(), 7, [](const void*, size_t) {}, [] { return false; }));
  fs::remove(file); // Only the exact file created by this test.
  std::cout << "native protocol/local-file contract tests passed\n";
}
