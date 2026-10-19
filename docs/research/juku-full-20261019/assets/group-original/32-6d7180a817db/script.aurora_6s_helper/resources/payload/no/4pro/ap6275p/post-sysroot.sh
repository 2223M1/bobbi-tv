#!/bin/sh
# BEGIN Aurora NO DTB check
# CoreELEC sources this hook after mounting SYSTEM, before its DTB filename check.
# These custom DTBs are supplied by the helper, outside CE's stock DTB directory.
if [ -f /proc/device-tree/coreelec ] &&
   [ -f /proc/device-tree/coreelec-dt-id ] &&
   grep -qE '^(COREELEC_DEVICE|DISTRO_DEVICE)="?Amlogic-no"?$' /sysroot/etc/os-release; then
    case "$(tr -d '\000' < /proc/device-tree/coreelec-dt-id)" in
        sc2_s905x4_tencent_aurora_6s_hs400|sc2_s905x4_tencent_aurora_4pro_rtl8852_hs400|sc2_s905x4_tencent_aurora_4pro_ap6275p_hs400)
            check_amlogic_dtb() {
                progress "Skipping stock DTB filename check for helper-managed Aurora NO DTB"
                return 0
            }
            ;;
    esac
fi
# END Aurora NO DTB check
