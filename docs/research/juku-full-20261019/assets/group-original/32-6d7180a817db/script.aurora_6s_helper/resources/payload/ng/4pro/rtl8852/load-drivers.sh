#!/bin/sh
# Installed outside Kodi; invoked by systemd at boot.
set -eu
fail() { echo "Aurora 4 Pro NG: $*" >&2; exit 1; }
[ "$(uname -r)" = '4.9.269' ] &&
[ "$(uname -m)" = aarch64 ] || fail 'Kernel release/architecture mismatch; modules were not loaded.'
kernel_config=$(zcat /proc/config.gz) || fail 'Cannot read kernel configuration.'
for flag in CONFIG_ARM64 CONFIG_SMP CONFIG_PREEMPT CONFIG_MODULE_UNLOAD CONFIG_MODVERSIONS; do
  printf '%s\n' "$kernel_config" | grep -qx "$flag=y" || fail "Incompatible kernel option: $flag"
done
# Never force loading: the kernel validates vermagic and imported-symbol CRCs.
. /etc/os-release
[ "${ID:-}" = coreelec ] && [ "${COREELEC_ARCH:-${LIBREELEC_ARCH:-}}" = Amlogic-ng.arm ] || fail 'Wrong CE variant.'
[ "$(tr -d '\000' < /proc/device-tree/coreelec-dt-id)" = sc2_s905x4_tencent_aurora_4pro_rtl8852_ng ] || fail 'Install the Aurora 4 Pro NG DTB and reboot first.'
root=/storage/.config/aurora6s-ng
case "${1:-}" in
 wifi)
  [ "$(od -An -tx1 /proc/device-tree/pcieA@f5000000/power-domains | tr -d ' \n')" = 0000001400000007 ] || fail 'PCIe power-domain association missing.'
  [ -d /sys/bus/pci/devices/0000:01:00.0 ] || fail 'PCIe wireless device missing.'
  [ -d /sys/module/rtkm ] || /sbin/insmod "$root/rtkm.ko"
  [ -d /sys/module/8852be ] || /sbin/insmod "$root/8852be.ko"
  ;;
 led)
  [ -e /dev/i2c-3 ] || /sbin/modprobe i2c-dev
  [ -d /sys/module/leds_tca6507 ] || /sbin/insmod "$root/leds-tca6507.ko"
  ;;
 *) fail 'Usage: load-drivers.sh wifi|led' ;;
esac
