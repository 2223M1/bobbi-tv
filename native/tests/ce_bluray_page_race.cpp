// Exercise CE's real page cache, worker, LRU, EOF and retry paths. Only the
// disc callback and logging are simulated. TestMiss is an observation barrier.
#include "BlurayIsoCache.h"
#include <array>
#include <chrono>
#include <cstring>
#include <future>
#include <iostream>
#include <stdexcept>
using namespace std::chrono_literals;
namespace {
constexpr int page = 4096, length = page * 4 + 2048;
std::mutex lock;
std::condition_variable wake;
bool observed = false;
unsigned char sample(int i) { return static_cast<unsigned char>((i / 2048 * 31 + i % 253) % 251); }
void require(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
}
void TestMiss(int64_t index) {
  if (index == 1) { {std::lock_guard<std::mutex> guard(lock); observed = true;} wake.notify_all(); }
}
int main(int argc, char** argv) {
  try {
    bool failedRead = argc == 2 && std::strcmp(argv[1], "retry") == 0;
    std::promise<void> entered, release;
    auto allow = release.get_future().share();
    std::atomic<int> calls{0};
    CBlurayIsoCache cache(length, [&](int64_t off, uint8_t* dst, size_t n) -> int64_t {
      if (off == page && ++calls == 1) {
        entered.set_value();
        require(allow.wait_for(4s) == std::future_status::ready, "timeout");
        if (failedRead) return -1;
      }
      require(off >= 0 && off + static_cast<int64_t>(n) <= length, "invalid range");
      for (size_t i=0;i<n;i++) dst[i]=sample(off+i);
      return n;
    }, {page, 2*page, 1});
    cache.Start();
    auto read = [&](int block, int blocks=1) {
      std::array<uint8_t,8192> bytes{};
      int got = cache.ReadBlocks(bytes.data(),block,blocks);
      int need = std::min(blocks, length / 2048 - block);
      require(got == need, "wrong block count");
      for (int i=0; i<got*2048; ++i) require(bytes[i]==sample(block*2048+i), "wrong content");
    };
    read(0);
    require(entered.get_future().wait_for(4s) == std::future_status::ready, "no prefetch");
    auto reader = std::async(std::launch::async,[&]{read(2);});
    { std::unique_lock<std::mutex> guard(lock);
      require(wake.wait_for(guard,4s,[]{return observed;}),"no foreground miss"); }
    release.set_value();
    reader.get();
    require(calls == (failedRead ? 2 : 1), "duplicate page IO");
    for (int block : {7, 0, 5, 8, 4, 2, 7, 8}) read(block, 2);
    cache.Stop();
    cache.Start(); read(0); cache.Stop();
    std::cout << "OK: overlapping page, bounded LRU, random seeks, partial EOF, restart\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
