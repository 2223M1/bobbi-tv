package org.bobbi.helper;

import android.content.Context;

/** Human-readable status; diagnostic codes remain stable without exposing exception text. */
final class EnginePresentation {
    private EnginePresentation() {}

    static String state(Context context, String value) {
        switch (value) {
            case "STARTING": return context.getString(R.string.state_starting);
            case "RUNNING": return context.getString(R.string.state_running);
            case "STOPPING": return context.getString(R.string.state_stopping);
            case "STOP_UNCONFIRMED": return context.getString(R.string.state_stop_unconfirmed);
            case "FAILED": return context.getString(R.string.state_failed);
            default: return context.getString(R.string.state_stopped);
        }
    }

    static String detail(Context context, String value) {
        switch (value) {
            case "NOT_STARTED": return context.getString(R.string.detail_not_started);
            case "VERIFYING_PACKAGED_ENGINE": return context.getString(R.string.detail_verifying_engine);
            case "VERIFYING_CONTROL_AUTH": return context.getString(R.string.detail_verifying_auth);
            case "CONTROL_AUTH_VERIFIED_MEDIA_BOUNDARY_APPLIES": return context.getString(R.string.detail_auth_verified);
            case "USER_REQUESTED_STOP":
            case "STOPPING_OWNED_PROCESS": return context.getString(R.string.detail_stopping_owned);
            case "USER_STOPPED": return context.getString(R.string.detail_user_stopped);
            case "PORT_IN_USE": return context.getString(R.string.detail_port_in_use);
            case "PROCESS_STOP_NOT_CONFIRMED_USE_ANDROID_FORCE_STOP":
            case "SERVICE_DESTROYED_NO_AUTOMATIC_RESTART": return context.getString(R.string.detail_force_stop);
            case "FOREGROUND_SERVICE_DENIED": return context.getString(R.string.detail_fgs_denied);
            case "STARTUP_TIMEOUT": return context.getString(R.string.detail_startup_timeout);
            case "ENGINE_MISSING_OR_NOT_EXECUTABLE":
            case "ENGINE_FORMAT_INVALID":
            case "ENGINE_HASH_OR_ABI_INVALID": return context.getString(R.string.detail_engine_invalid);
            case "CONTROL_AUTH_NOT_ENFORCED":
            case "CONTROL_AUTH_REJECTED":
            case "UNSAFE_ENGINE_SETTINGS": return context.getString(R.string.detail_auth_failed);
            case "ENGINE_EXITED":
            case "ENGINE_EXITED_DURING_START": return context.getString(R.string.detail_engine_exited);
            default: return context.getString(R.string.detail_default);
        }
    }
}
