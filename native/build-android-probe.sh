#!/usr/bin/env bash
set -euo pipefail
task_root="${1:?isolated native root}"
abi="${2:?arm64 or armv7}"
case "$task_root" in /opt/bobbi-native-*) ;; *) exit 2;; esac
case "$abi" in
  arm64) arch=aarch64; triple=aarch64-linux-android26;;
  armv7) arch=arm; triple=armv7a-linux-androideabi26;;
  *) exit 2;;
esac
source_root="$task_root/src-$abi/tools/depends/target/ffmpeg"
source_dir="$(find "$source_root" -name configure -path '*-release/configure' -print -quit)"
test -n "$source_dir"
source_dir="$(dirname "$source_dir")"
build="$task_root/probe-$abi"
mkdir -p "$build"
cd "$build"
ndk="$task_root/toolchain/android-ndk-r21e/toolchains/llvm/prebuilt/linux-x86_64/bin"
if test ! -f ffbuild/config.mak; then
  "$source_dir/configure" --target-os=android --arch="$arch" --enable-cross-compile \
    --cc="$ndk/$triple-clang" --cxx="$ndk/$triple-clang++" \
    --ar="$ndk/llvm-ar" --ranlib="$ndk/llvm-ranlib" --nm="$ndk/llvm-nm" \
    --strip="$ndk/llvm-strip" --pkg-config=false --disable-autodetect \
    --disable-shared --enable-static --enable-pic --enable-small \
    --disable-programs --enable-ffprobe --disable-doc --disable-debug \
    --disable-avdevice --disable-avfilter --disable-swscale --disable-swresample \
    --disable-encoders --disable-muxers --disable-filters --disable-hwaccels \
    --disable-protocols --enable-protocol=http,tcp,file,pipe --disable-asm
fi
make -j8 ffprobe
"$ndk/llvm-strip" ffprobe
