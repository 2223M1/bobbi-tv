package org.bobbi.helper;

/** Human-readable status; diagnostic codes remain stable without exposing exception text. */
final class EnginePresentation {
    private EnginePresentation() {}

    static String state(String value) {
        switch (value) {
            case "STARTING": return "正在启动";
            case "RUNNING": return "已就绪，可以打开 Kodi";
            case "STOPPING": return "正在停止";
            case "STOP_UNCONFIRMED": return "需要系统协助停止";
            case "FAILED": return "启动失败";
            default: return "未运行";
        }
    }

    static String detail(String value) {
        switch (value) {
            case "NOT_STARTED": return "第一步：启动本机引擎。首次使用再导出配对文件给 Kodi。";
            case "VERIFYING_PACKAGED_ENGINE": return "正在检查安装包内的引擎，请稍候。";
            case "VERIFYING_CONTROL_AUTH": return "正在验证本机连接，最多等待 30 秒。";
            case "CONTROL_AUTH_VERIFIED_MEDIA_BOUNDARY_APPLIES": return "本机控制连接已验证。首次使用请导出配对文件，然后在 Kodi 中导入。";
            case "USER_REQUESTED_STOP":
            case "STOPPING_OWNED_PROCESS": return "正在关闭本助手启动的引擎，请稍候。";
            case "USER_STOPPED": return "已停止。下次观看前请重新启动。";
            case "PORT_IN_USE": return "本机 8090 端口已被其他程序占用；本助手没有停止它。请先关闭其他 BT 服务，再试一次。";
            case "PROCESS_STOP_NOT_CONFIRMED_USE_ANDROID_FORCE_STOP":
            case "SERVICE_DESTROYED_NO_AUTOMATIC_RESTART": return "尚不能确认引擎已停止。请打开下方系统应用设置，手动选择强行停止，然后重新打开助手。";
            case "FOREGROUND_SERVICE_DENIED": return "系统拒绝后台服务。请保持助手在前台，检查系统应用设置后重试。";
            case "STARTUP_TIMEOUT": return "本机引擎未在 30 秒内就绪。可以重新启动一次；仍失败请保留此诊断代码。";
            case "ENGINE_MISSING_OR_NOT_EXECUTABLE":
            case "ENGINE_FORMAT_INVALID":
            case "ENGINE_HASH_OR_ABI_INVALID": return "安装的引擎不完整或系统不支持。请勿反复重试，请核对设备和安装包。";
            case "CONTROL_AUTH_NOT_ENFORCED":
            case "CONTROL_AUTH_REJECTED":
            case "UNSAFE_ENGINE_SETTINGS": return "本机控制验证未通过，已停止自己的引擎。请勿把此状态当作连接成功。";
            case "ENGINE_EXITED":
            case "ENGINE_EXITED_DURING_START": return "引擎进程已退出。可以手动重试；持续失败需要设备验收。";
            default: return "操作未完成，请查看诊断代码。不会自动更换引擎、账户或片源。";
        }
    }
}
