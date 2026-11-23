package org.bobbi.helper;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.Context;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicLong;

/** User-started special-use FGS; never boot starts, sticky restarts or accessibility. */
public final class EngineService extends Service implements EngineRunner.Listener {
    static final String START = "org.bobbi.helper.START";
    static final String STOP = "org.bobbi.helper.STOP";
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
    private static volatile EngineRunner activeEngine;
    private static final AtomicLong generation = new AtomicLong();
    static synchronized void requestStart(Context app) {
        if (snapshot.busy() || activeEngine != null) return;
        long ticket = generation.incrementAndGet();
        snapshot = new Snapshot("STARTING", "START_REQUESTED");
        try {
            app.startForegroundService(new Intent(app, EngineService.class).setAction(START)
                    .putExtra("generation", ticket));
        } catch (RuntimeException denied) {
            snapshot = new Snapshot("FAILED", "FOREGROUND_SERVICE_DENIED");
        }
    }
    static synchronized void requestStop() {
        generation.incrementAndGet(); // Also revoke a start queued before onCreate.
        EngineRunner owner = activeEngine;
        if (owner != null) owner.stop();
        else snapshot = new Snapshot("STOPPED", "START_CANCELLED");
    }
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EngineRunner runner;
    private boolean destroyed;

    @Override public void onCreate() {
        super.onCreate();
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL,
                "BT 播放", NotificationManager.IMPORTANCE_LOW));
    }

    private Notification notification(String message) {
        PendingIntent open = PendingIntent.getActivity(this, 0, getPackageManager().getLaunchIntentForPackage(getPackageName()),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, EngineService.class).setAction(STOP),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL).setSmallIcon(android.R.drawable.stat_sys_download)
                .setContentTitle("波比 TV").setContentText(message)
                .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
                .addAction(new Notification.Action.Builder(null, "停止 BT", stop).build()).build();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        if (START.equals(action) && runner == null && activeEngine == null
                && intent.getLongExtra("generation", -1) == generation.get()) {
            snapshot = new Snapshot("STARTING", "VERIFYING_PACKAGED_ENGINE");
            Notification notice = notification("正在启动并验证本机控制接口");
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
            activeEngine = runner;
            if (intent.getLongExtra("generation", -1) != generation.get()) runner.stop();
            executor.execute(runner);
        } else if (STOP.equals(action)) {
            requestStop();
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
            if (owner != activeEngine) return;
            if (("RUNNING".equals(state) || "STARTING".equals(state)) && !owner.requested()) return;
            snapshot = new Snapshot(state, detail);
            if (!destroyed && ("RUNNING".equals(state) || "STOPPING".equals(state) || "STOP_UNCONFIRMED".equals(state))) {
                String label = "RUNNING".equals(state) ? "BT 播放已就绪" : "正在停止 BT";
                getSystemService(NotificationManager.class).notify(NOTIFICATION, notification(label));
            }
        });
    }

    @Override public void finished(EngineRunner owner) {
        main.post(() -> {
            if (owner != activeEngine) return;
            activeEngine = null;
            runner = null;
            if (destroyed) return;
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
        });
    }

    @Override public void onDestroy() {
        destroyed = true;
        if (runner != null) runner.stop();
        executor.shutdown();
        if (runner != null && snapshot.busy())
            snapshot = new Snapshot("STOP_UNCONFIRMED", "SERVICE_DESTROYED_NO_AUTOMATIC_RESTART");
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public void onTaskRemoved(Intent rootIntent) {
        if (runner != null) runner.stop();
        else stopSelf();
    }
}
