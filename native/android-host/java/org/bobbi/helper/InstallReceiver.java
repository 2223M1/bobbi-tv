package org.bobbi.helper;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;

public final class InstallReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirmation = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirmation != null) {
                confirmation.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try { context.startActivity(confirmation); }
                catch (RuntimeException denied) { HostBridge.installFinished("CONFIRMATION_UNAVAILABLE"); }
            } else HostBridge.installFinished("FAILED");
        } else HostBridge.installFinished(status == PackageInstaller.STATUS_SUCCESS ? "INSTALLED" : "CANCELLED_OR_FAILED");
    }
}
