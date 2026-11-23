#!/bin/sh
# Use the CoreELEC Amlogic-ng ARM hard-float toolchain, not the workstation ABI.
set -eu
: "${CC:?set CC to the CoreELEC cross compiler}"
case "$("$CC" -dumpmachine)" in arm*-gnueabihf) ;; *) echo 'CoreELEC ARMHF compiler required' >&2; exit 2;; esac
out=${1:?new output path required}
test ! -e "$out"
source_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
"$CC" -O2 -g0 -fPIC -shared -Wl,-z,now,-z,relro,--no-undefined,-soname,libbobi_liquid_glass.so \
  "$source_dir/bobbi_liquid_glass_gles2.c" -o "$out" -lGLESv2 -lEGL -ldl -lm
