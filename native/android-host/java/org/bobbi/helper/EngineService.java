package org.bobbi.helper;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.Context;
import android.content.pm.ServiceInfo;
import android.content.res.Configuration;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicLong;

/** User-started special-use FGS; never boot starts, sticky restarts or accessibility. */
public final class EngineService extends Service implements EngineRunner.Listener {
    static final String START = "org.bobbi.helper.START";
    static final String STOP = "org.bobbi.helper.STOP";
    static final String REFRESH_LOCALE = "org.bobbi.helper.REFRESH_LOCALE";
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
    private static volatile String projectedLocale = "";
    private static final AtomicLong generation = new AtomicLong();

    static String normalizeLocaleTag(String raw) {
        if (raw == null) return "";
        String lower = raw.trim().toLowerCase(Locale.ROOT).replace('-', '_');
        if (lower.startsWith("en") || lower.startsWith("resource.language.en")) return "en";
        if (lower.startsWith("zh") || lower.startsWith("resource.language.zh")) return "zh";
        return "";
    }

    private static String readKodiGuiLocale(Context app) {
        File external = app.getExternalFilesDir(null);
        File[] bases = external != null ? new File[]{external, app.getFilesDir()} : new File[]{app.getFilesDir()};
        for (File base : bases) {
            if (base == null) continue;
            File gui = new File(base, ".kodi/userdata/guisettings.xml");
            if (!gui.isFile() || gui.length() <= 0 || gui.length() > 512 * 1024) continue;
            try (FileInputStream in = new FileInputStream(gui)) {
                byte[] buf = new byte[(int) gui.length()];
                int read = in.read(buf);
                if (read <= 0) continue;
                String xml = new String(buf, 0, read, StandardCharsets.UTF_8);
                int idx = xml.indexOf("id=\"locale.language\"");
                if (idx >= 0) {
                    int gt = xml.indexOf('>', idx);
                    int lt = gt >= 0 ? xml.indexOf('<', gt + 1) : -1;
                    if (gt >= 0 && lt > gt) {
                        String norm = normalizeLocaleTag(xml.substring(gt + 1, lt));
                        if (!norm.isEmpty()) return norm;
                    }
                }
            } catch (Exception ignored) { }
        }
        return "";
    }

    static String effectiveLocale(Context app) {
        String explicit = projectedLocale;
        if (!explicit.isEmpty()) return explicit;
        String fromKodi = readKodiGuiLocale(app);
        return fromKodi.isEmpty() ? "zh" : fromKodi;
    }

    static String hostString(Context app, String resName, String fallbackEn) {
        boolean en = "en".equals(effectiveLocale(app));
        Locale target = en ? Locale.ENGLISH : Locale.SIMPLIFIED_CHINESE;
        Configuration cfg = new Configuration(app.getResources().getConfiguration());
        cfg.setLocale(target);
        Context localized = app.createConfigurationContext(cfg);
        int id = localized.getResources().getIdentifier(resName, "string", app.getPackageName());
        if (id != 0) {
            try { return localized.getString(id); }
            catch (RuntimeException ignored) { }
        }
        return fallbackEn;
    }

    static synchronized boolean applyUiLocale(Context app, String rawLocale) {
        String normalized = normalizeLocaleTag(rawLocale);
        if (normalized.isEmpty()) return false;
        projectedLocale = normalized;
        NotificationManager manager = app.getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL,
                    hostString(app, "bobbi_host_channel_name", "BT Playback"),
                    NotificationManager.IMPORTANCE_LOW));
        }
        if (snapshot.busy() && activeEngine != null) {
            try { app.startService(new Intent(app, EngineService.class).setAction(REFRESH_LOCALE)); }
            catch (RuntimeException ignored) { }
        }
        return true;
    }

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
                hostString(this, "bobbi_host_channel_name", "BT Playback"),
                NotificationManager.IMPORTANCE_LOW));
    }

    private Notification notification(String message) {
        PendingIntent open = PendingIntent.getActivity(this, 0, getPackageManager().getLaunchIntentForPackage(getPackageName()),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, EngineService.class).setAction(STOP),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL).setSmallIcon(android.R.drawable.stat_sys_download)
                .setContentTitle(hostString(this, "bobbi_host_app_title", "bobbi TV")).setContentText(message)
                .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
                .addAction(new Notification.Action.Builder(null,
                        hostString(this, "bobbi_host_stop_bt", "Stop BT"), stop).build()).build();
    }

    private String statusText(String state) {
        if ("STARTING".equals(state)) return hostString(this, "bobbi_host_starting_verify", "Starting and verifying local control interface");
        if ("RUNNING".equals(state)) return hostString(this, "bobbi_host_ready", "BT playback ready");
        return hostString(this, "bobbi_host_stopping", "Stopping BT");
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        if (START.equals(action) && runner == null && activeEngine == null
                && intent.getLongExtra("generation", -1) == generation.get()) {
            snapshot = new Snapshot("STARTING", "VERIFYING_PACKAGED_ENGINE");
            Notification notice = notification(statusText("STARTING"));
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
        } else if (REFRESH_LOCALE.equals(action) && runner != null && snapshot.busy()) {
            NotificationManager manager = getSystemService(NotificationManager.class);
            manager.createNotificationChannel(new NotificationChannel(CHANNEL,
                    hostString(this, "bobbi_host_channel_name", "BT Playback"),
                    NotificationManager.IMPORTANCE_LOW));
            manager.notify(NOTIFICATION, notification(statusText(snapshot.state)));
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
                getSystemService(NotificationManager.class).notify(NOTIFICATION, notification(statusText(state)));
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
