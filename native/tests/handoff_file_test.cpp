#include "dialogs/BobiHandoffFile.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <sys/stat.h>
#include <unistd.h>

int main()
{
  char temporary[] = "/tmp/bobbi-handoff-file-XXXXXX";
  const std::string root(mkdtemp(temporary));
  const auto file = root + "/manual.ass";
  const std::string data = "[Script Info]\nTitle: 手选字幕\n";
  { std::ofstream out(file); out << data; }
  std::string read;
  auto consume = [&](const void* bytes, size_t count) { read.append(static_cast<const char*>(bytes), count); };
  assert(BobiReadHandoffFile(root, file, consume) && read == data);
  assert(!BobiReadHandoffFile(root, root + "/../manual.ass", consume));
  assert(!BobiReadHandoffFile(root, root + "/./manual.ass", consume));
  assert(!BobiReadHandoffFile(root, root + "//manual.ass", consume));
  assert(!BobiReadHandoffFile(root, root + "/sub\\manual.ass", consume));
  assert(!BobiReadHandoffFile(root, "/etc/passwd", consume));
  assert(!BobiReadHandoffFile(root, root + "/missing", consume));
  const auto link = root + "/link";
  assert(!symlink(file.c_str(), link.c_str()));
  assert(!BobiReadHandoffFile(root, link, consume));
  const auto fifo = root + "/fifo";
  assert(!mkfifo(fifo.c_str(), 0600));
  assert(!BobiReadHandoffFile(root, fifo, consume));
  assert(!BobiReadHandoffFile(root, root, consume));
  const auto large = root + "/large.ass";
  { std::ofstream out(large); out.seekp(64 * 1024 * 1024); out.put('x'); }
  assert(!BobiReadHandoffFile(root, large, consume));
  assert(!BobiReadHandoffFile(root, file, [&](const void*, size_t) {
    std::ofstream out(file, std::ios::app); out << "changed";
  }));
  unlink(file.c_str()); unlink(link.c_str()); unlink(fifo.c_str()); unlink(large.c_str());
  rmdir(root.c_str());
  std::cout << "Portable handoff file boundaries passed\n";
}
