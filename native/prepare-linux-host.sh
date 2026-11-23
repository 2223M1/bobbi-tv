#!/usr/bin/env bash
set -euo pipefail
task_root="${1:?Supply isolated native build root}"
case "$task_root" in /opt/bobbi-native-*) ;; *) echo 'Unexpected isolated root' >&2; exit 2;; esac
mkdir -p "$task_root/host-debs" "$task_root/host-root" "$task_root/host-bin"
ln -sfn /usr/bin/gcc-12 "$task_root/host-bin/cc"
ln -sfn /usr/bin/g++-12 "$task_root/host-bin/c++"
# Only package indexes are refreshed. Development packages are extracted inside
# this build, never installed into the existing CoreELEC build distribution.
apt-get update
cd "$task_root/host-debs"
apt-get download libcurl4-openssl-dev libnghttp2-dev libssl-dev flex
for archive in *.deb; do dpkg-deb -x "$archive" "$task_root/host-root"; done
ln -sfn "$task_root/host-root/usr/bin/flex" "$task_root/host-bin/flex"
sha256sum *.deb > "$task_root/logs/host-deb-sha256.txt"
prefix="$task_root/depends-arm64/x86_64-linux-gnu-native"
mkdir -p "$prefix/include" "$prefix/lib"
cp -a "$task_root/host-root/usr/include/x86_64-linux-gnu/curl" "$prefix/include/"
cp -a "$task_root/host-root/usr/include/nghttp2" "$prefix/include/"
# Use host OS runtime libraries without mutating that OS. Do not use CE target libs.
ln -sfn /usr/lib/x86_64-linux-gnu/libcurl.so.4 "$prefix/lib/libcurl.so"
ln -sfn /usr/lib/x86_64-linux-gnu/libnghttp2.so.14 "$prefix/lib/libnghttp2.so"
# Kodi builds a fixed native OpenSSL itself; do not shadow it with host SSL3.
