#!/usr/bin/env bash
set -euo pipefail
task_root="${1:?isolated native root}"
abi="${2:?arm64 or armv7}"
case "$task_root" in /opt/bobbi-native-*) ;; *) exit 2;; esac
case "$abi" in
  arm64) triple=aarch64-linux-android26;;
  armv7) triple=armv7a-linux-androideabi26;;
  *) exit 2;;
esac
script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
archive="$task_root/android-font-input/7z2301-src.tar.xz"
test "$(sha256sum "$archive" | cut -d' ' -f1)" = 356071007360e5a1824d9904993e8b2480b51b570e8c9faf7c0f58ebe4bf9f74
variant="${3:-}"
case "$variant" in *[!a-z0-9-]*) exit 2;; esac
build="$task_root/fonts-$abi${variant:+-$variant}"
if test ! -e "$build"; then
  mkdir "$build"
  tar -xJf "$archive" -C "$build"
fi
ndk="$task_root/toolchain/android-ndk-r21e/toolchains/llvm/prebuilt/linux-x86_64/bin"
mkdir -p "$build/CPP/7zip/Bundles/Alone2/_o"
# These three files contain only runtime-dispatched crypto implementations.
# NDK21's clang does not understand the later per-function +crypto attribute.
# Never enable this ISA for the generic decoder or CPU detection code.
if test "$abi" = arm64; then crypto='-march=armv8-a+crypto';
else crypto='-march=armv8-a -mfpu=crypto-neon-fp-armv8'; fi
make -C "$build/CPP/7zip/Bundles/Alone2" -f makefile.gcc -j3 \
  _o/AesOpt.o _o/Sha1Opt.o _o/Sha256Opt.o \
  CC="$ndk/$triple-clang" CXX="$ndk/$triple-clang++" MY_ARCH="$crypto" USE_CLANG=1
make -C "$build/CPP/7zip/Bundles/Alone2" -f makefile.gcc -j8 \
  CC="$ndk/$triple-clang" CXX="$ndk/$triple-clang++" \
  LDFLAGS_STATIC_2=-static-libstdc++ USE_CLANG=1 LIB2=-ldl
cp "$build/CPP/7zip/Bundles/Alone2/_o/7zz" "$build/libbobbi_7zip.so"
"$ndk/llvm-strip" "$build/libbobbi_7zip.so"
"$ndk/$triple-clang" -O2 -fPIE -pie "$script_root/android-host/font_limiter.c" -o "$build/libbobbi_font_limiter.so"
"$ndk/llvm-strip" "$build/libbobbi_font_limiter.so"
