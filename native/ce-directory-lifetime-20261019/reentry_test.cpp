#include <cassert>
#include <functional>
#include <memory>
#include <iostream>

struct Directory { int id; };
using Ptr = std::shared_ptr<Directory>;
// Model the same reference ownership and nested GUI message dispatch without
// dereferencing a dangling pointer. This is not a Kodi end-to-end crash test.
int old_request(const Ptr& member, const std::function<void()>& dispatch) {
  dispatch();
  return member ? member->id : -1;
}
int fixed_request(const Ptr& directory, const std::function<void()>& dispatch) {
  const Ptr member = directory;
  dispatch();
  return member ? member->id : -1;
}
int main() {
  for (bool replace : {false, true}) {
    Ptr caller = std::make_shared<Directory>(Directory{1});
    std::weak_ptr<Directory> original = caller;
    auto dispatch = [&] { caller = replace ? std::make_shared<Directory>(Directory{2}) : Ptr{}; };
    assert(old_request(caller, dispatch) == (replace ? 2 : -1));
    assert(original.expired());
    caller = std::make_shared<Directory>(Directory{1});
    original = caller;
    assert(fixed_request(caller, [&] { dispatch(); assert(!original.expired()); }) == 1);
    assert(original.expired());
  }
  Ptr empty;
  assert(fixed_request(empty, []{}) == -1);
  std::cout << "PASS: reset, replacement, lifetime, null\n";
}
