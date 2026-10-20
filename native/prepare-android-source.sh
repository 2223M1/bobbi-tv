#!/usr/bin/env bash
set -euo pipefail
task_root="${1:?isolated root}"
abi="${2:?arm64 or armv7}"
case "$task_root" in /opt/bobbi-native-*) ;; *) exit 2;; esac
case "$abi" in arm64) host=aarch64-linux-android; rust=aarch64-linux-android;; armv7) host=arm-linux-androideabi; rust=arm-linux-androideabi;; *) exit 2;; esac
script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_root="$task_root/src-$abi"
test ! -e "$source_root" || { echo 'Source already exists; refusing reset' >&2; exit 2; }
git clone --shared "$task_root/src-arm64" "$source_root"
test "$(git -C "$source_root" rev-parse HEAD)" = a3a448d26b8d560a65655dab2cd122994dc4e146
git -C "$source_root" apply "$script_root/patches/0001-bobbi-playback-contracts.patch" "$script_root/patches/0002-bobbi-host-packaging.patch"
export JAVA_HOME="$task_root/toolchain/jdk-17.0.18+8"
export PATH="$task_root/depends-arm64/x86_64-linux-gnu-native/bin:$task_root/host-bin:$JAVA_HOME/bin:/usr/local/bin:/usr/bin:/bin"
export RUSTUP_HOME="$task_root/depends-arm64/x86_64-linux-gnu-native/.rustup"
export CARGO_HOME="$task_root/depends-arm64/x86_64-linux-gnu-native/.cargo"
"$CARGO_HOME/bin/rustup" target add "$rust"
cd "$source_root/tools/depends"
./bootstrap
./configure --host="$host" --with-ndk-api=26 --with-sdk=34 \
  --with-sdk-path="$task_root/toolchain/sdk" --with-ndk-path="$task_root/toolchain/android-ndk-r21e" \
  --with-tarballs="$task_root/tarballs" --prefix="$task_root/depends-arm64" --disable-debug --disable-ccache
make -C target -j8
