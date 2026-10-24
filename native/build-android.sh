#!/usr/bin/env bash
set -euo pipefail
task_root="${1:?Supply isolated build root}"
abi="${2:?Supply arm64 or armv7}"
step="${3:-host}"
script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
case "$task_root" in /opt/bobbi-native-*) ;; *) echo 'Invalid isolated root' >&2; exit 2;; esac
case "$abi" in arm64|armv7) ;; *) exit 2;; esac
source_root="$task_root/src-$abi"
if [ "$(git -C "$source_root" rev-parse HEAD)" != a3a448d26b8d560a65655dab2cd122994dc4e146 ]; then
  echo 'Wrong Kodi source base' >&2; exit 2
fi
export JAVA_HOME="$task_root/toolchain/jdk-17.0.18+8"
export PATH="$task_root/depends-arm64/x86_64-linux-gnu-native/bin:$task_root/host-bin:$JAVA_HOME/bin:/usr/local/bin:/usr/bin:/bin"
export GRADLE_USER_HOME="$task_root/gradle"
cd "$source_root"
case "$step" in
  depends) make -C tools/depends/target -j8 ;;
  host)
    make -C tools/depends/target/cmakebuildsys BUILD_DIR="$task_root/build-$abi" \
      CMAKE_EXTRA_ARGUMENTS='-DAPP_PACKAGE=org.bobbi.helper -DENABLE_TESTING=OFF -DKODI_MIRROR=https://mirrors.kodi.tv'
    make -C "$task_root/build-$abi" -j8
    ;;
  apk)
    echo 'Use the template step, then repackage-android.py with native/engine/probe/font inputs. A template APK is not distributable.' >&2
    exit 2
    ;;
  template)
    export BOBBI_COMPONENTS_MANIFEST="${BOBBI_COMPONENTS_MANIFEST:?Frozen components manifest required}"
    export BOBBI_STAGE_TOOL="$script_root/stage-components.py"
    export BOBBI_GRADLE="python3 $script_root/gradle-isolated.py $task_root"
    # An ephemeral build-only certificate is replaced on Windows with the
    # original release key. No release password crosses a WSL command line.
    export KODI_ANDROID_STORE_FILE="$task_root/build-only.keystore"
    export KODI_ANDROID_STORE_PASSWORD=android
    export KODI_ANDROID_KEY_PASSWORD=android
    export KODI_ANDROID_KEY_ALIAS=androiddebugkey
    if [ ! -f "$KODI_ANDROID_STORE_FILE" ]; then
      keytool -genkeypair -keystore "$KODI_ANDROID_STORE_FILE" -alias androiddebugkey \
        -storepass android -keypass android -keyalg RSA -keysize 2048 -validity 365 \
        -dname 'CN=Build Only,O=Local Build,C=CN'
    fi
    make -C "$task_root/build-$abi" apk
    echo 'Build-only packaging template. Do not install or distribute; use repackage-android.py and sign-host-apk.py.'
    ;;
  *) exit 2;;
esac
