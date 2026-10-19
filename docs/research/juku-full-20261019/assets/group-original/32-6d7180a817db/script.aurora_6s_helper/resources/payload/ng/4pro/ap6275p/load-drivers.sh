#!/bin/sh
# Installed outside Kodi; invoked by systemd at boot.
set -eu
fail() { echo "Aurora 4 Pro AP6275P NG: $*" >&2; exit 1; }
[ "$(uname -r)" = '4.9.269' ] &&
[ "$(uname -m)" = aarch64 ] || fail 'Kernel release/architecture mismatch; modules were not loaded.'
kernel_config=$(zcat /proc/config.gz) || fail 'Cannot read kernel configuration.'
for flag in CONFIG_ARM64 CONFIG_SMP CONFIG_PREEMPT CONFIG_MODULE_UNLOAD CONFIG_MODVERSIONS; do
  case "
$kernel_config
" in
    *"
$flag=y
"*) ;;
    *) fail "Incompatible kernel option: $flag" ;;
  esac
done
# Never force loading: the kernel validates vermagic and imported-symbol CRCs.
. /etc/os-release
[ "${ID:-}" = coreelec ] && [ "${COREELEC_ARCH:-${LIBREELEC_ARCH:-}}" = Amlogic-ng.arm ] || fail 'Wrong CE variant.'
[ "$(tr -d '\000' < /proc/device-tree/coreelec-dt-id)" = sc2_s905x4_tencent_aurora_4pro_ap6275p_ng ] || fail 'Install the Aurora 4 Pro AP6275P NG DTB and reboot first.'
root=/storage/.config/aurora6s-ng
[ "${1:-}" = led ] || fail 'Usage: load-drivers.sh led'
[ -e /dev/i2c-3 ] || /sbin/modprobe i2c-dev
[ -d /sys/module/leds_tca6507 ] || /sbin/insmod "$root/leds-tca6507.ko"
