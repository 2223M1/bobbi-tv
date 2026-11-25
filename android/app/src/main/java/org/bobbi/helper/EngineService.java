package org.bobbi.helper;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** User-started special-use FGS; never boot starts, sticky restarts or accessibility. */
public final class EngineService extends Service implements EngineRunner.Listener {
    static final String START = "org.bobbi.helper.START";
    static final String STOP = "org.bobbi.helper.STOP";
    static final String PAIR = "org.bobbi.helper.PAIR";
    static final String REFRESH_LOCALE = "org.bobbi.helper.REFRESH_LOCALE";
    static volatile PairBridge pairing;
    private static final String CHANNEL = "bobbi_engine";
    private static final int NOTIFICATION = 8090;
    static final class Snapshot {
        final String state;
        final String detail;
        Snapshot(String state, String detail) { this.state = state; this.detail = detail; }
        boolean busy() { return "STARTING".equals(state) || "RUNNING".equals(state)
                || "STOPPING".equals(state) || "STOP_UNCONFIRMED".equals(state); }
    }
    static volatile Snapshot snapshot = new Snapshot("STOPPED", "NOT_STARTED");
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EngineRunner runner;
    private boolean destroyed;

    static void refreshLocale(Context app) {
        Context localized = AppLocale.wrap(app);
        NotificationManager manager = app.getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL,
                    localized.getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW));
        }
        if (snapshot.busy()) {
            try { app.startService(new Intent(app, EngineService.class).setAction(REFRESH_LOCALE)); }
            catch (RuntimeException ignored) { }
        }
    }

    private Context localizedContext() {
        return AppLocale.wrap(this);
    }

    @Override public void onCreate() {
        super.onCreate();
        Context localized = localizedContext();
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL,
                localized.getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW));
    }

    private Notification notification(Context localized, String message) {
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, EngineService.class).setAction(STOP),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL).setSmallIcon(R.drawable.ic_bobbi)
                .setContentTitle(localized.getString(R.string.app_name)).setContentText(message)
                .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
                .addAction(new Notification.Action.Builder(null, localized.getString(R.string.stop), stop).build()).build();
    }

    private String statusNotificationText(Context localized, String state) {
        if ("STARTING".equals(state)) return localized.getString(R.string.notification_starting_verify);
        return EnginePresentation.state(localized, state);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        Context localized = localizedContext();
        if (START.equals(action) && runner == null) {
            snapshot = new Snapshot("STARTING", "VERIFYING_PACKAGED_ENGINE");
            Notification notice = notification(localized, localized.getString(R.string.notification_starting_verify));
            try {
                if (Build.VERSION.SDK_INT >= 34)
                    startForeground(NOTIFICATION, notice, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
                else startForeground(NOTIFICATION, notice);
            } catch (RuntimeException denied) {
                snapshot = new Snapshot("FAILED", "FOREGROUND_SERVICE_DENIED");
                stopSelf();
                return START_NOT_STICKY;
            }
            runner = new EngineRunner(this, this);
            executor.execute(runner);
        } else if (REFRESH_LOCALE.equals(action) && runner != null && snapshot.busy()) {
            NotificationManager manager = getSystemService(NotificationManager.class);
            manager.createNotificationChannel(new NotificationChannel(CHANNEL,
                    localized.getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW));
            manager.notify(NOTIFICATION, notification(localized, statusNotificationText(localized, snapshot.state)));
        } else if (PAIR.equals(action) && runner != null && "RUNNING".equals(snapshot.state)) {
            if (pairing != null) pairing.close();
            try { pairing = new PairBridge(Credentials.load(this).pairing()); }
            catch (Exception unavailable) { pairing = null; }
        } else if (STOP.equals(action)) {
            if (pairing != null) pairing.close();
            if ("STOP_UNCONFIRMED".equals(snapshot.state)) {
                if (runner != null) runner.stop();
                else stopSelf();
                return START_NOT_STICKY;
            }
            snapshot = new Snapshot("STOPPING", "USER_REQUESTED_STOP");
            if (runner != null) runner.stop();
            else { snapshot = new Snapshot("STOPPED", "USER_STOPPED"); stopSelf(); }
        } else if (runner == null) stopSelf();
        return START_NOT_STICKY;
    }

    @Override public void state(EngineRunner owner, String state, String detail) {
        main.post(() -> {
            if (destroyed || owner != runner) return;
            if (("RUNNING".equals(state) || "STARTING".equals(state)) && !owner.requested()) return;
            snapshot = new Snapshot(state, detail);
            if ("RUNNING".equals(state) || "STOPPING".equals(state) || "STOP_UNCONFIRMED".equals(state)) {
                Context localized = localizedContext();
                String label = EnginePresentation.state(localized, state);
                getSystemService(NotificationManager.class).notify(NOTIFICATION, notification(localized, label));
            }
        });
    }

    @Override public void finished(EngineRunner owner) {
        main.post(() -> {
            if (destroyed || owner != runner) return;
            runner = null;
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
        });
    }

    @Override public void onDestroy() {
        destroyed = true;
        if (pairing != null) pairing.close();
        if (runner != null) runner.stop();
        executor.shutdown();
        if (snapshot.busy()) snapshot = new Snapshot("STOP_UNCONFIRMED", "SERVICE_DESTROYED_NO_AUTOMATIC_RESTART");
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
