package org.bobbi.helper;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.PackageInstaller;
import android.app.PendingIntent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import org.json.JSONObject;
import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;
import java.lang.ref.WeakReference;
import java.security.MessageDigest;
import java.util.concurrent.atomic.AtomicBoolean;

/** A single Android host owner. JSON receipts contain no account credentials. */
public final class HostBridge {
    private static volatile Context context;
    private static volatile WeakReference<Activity> foreground = new WeakReference<>(null);
    private static final AtomicBoolean installing = new AtomicBoolean();
    static volatile String installState = "IDLE";

    public static void resume(Activity activity) {
        context = activity.getApplicationContext();
        foreground = new WeakReference<>(activity);
    }
    public static void pause(Activity activity) {
        if (foreground.get() == activity) foreground.clear();
    }
    public static void destroy(Activity activity) {
        pause(activity);
        if (activity.isFinishing()) EngineService.requestStop();
    }
    private static boolean visible() {
        Activity activity = foreground.get();
        return activity != null && !activity.isFinishing() && !activity.isDestroyed();
    }
    private static long version(PackageInfo info) {
        return Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
    }
    private static String signer(PackageInfo info) throws Exception {
        android.content.pm.Signature[] values = info.signatures;
        if (values == null || values.length != 1) throw new Exception("SIGNER_COUNT");
        return Credentials.hex(MessageDigest.getInstance("SHA-256").digest(values[0].toByteArray()));
    }
    private static File updateDirectory(Context app) throws Exception {
        File path = new File(app.getCacheDir(), "bobbi-update");
        if (!path.isDirectory() && !path.mkdirs()) throw new Exception("UPDATE_STORAGE");
        return path.getCanonicalFile();
    }
    private static File checkedApk(Context app, String name) throws Exception {
        File file = new File(name).getCanonicalFile();
        if (!file.getParentFile().equals(updateDirectory(app)) || !file.isFile() ||
                !file.getName().equals("update.apk") || file.length() < 20 * 1024 * 1024 ||
                file.length() > 512L * 1024 * 1024) throw new Exception("UPDATE_PATH");
        PackageManager manager = app.getPackageManager();
        PackageInfo current = manager.getPackageInfo(app.getPackageName(), PackageManager.GET_SIGNATURES);
        PackageInfo next = manager.getPackageArchiveInfo(file.getPath(), PackageManager.GET_SIGNATURES);
        if (next == null || !app.getPackageName().equals(next.packageName) ||
                version(next) <= version(current) || !signer(current).equals(signer(next)))
            throw new Exception("UPDATE_IDENTITY");
        return file;
    }
    private static void install(Context app, File file) {
        new Thread(() -> {
            PackageInstaller manager = app.getPackageManager().getPackageInstaller();
            int id = -1;
            try {
                PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
                        PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                params.setAppPackageName(app.getPackageName());
                params.setSize(file.length());
                if (Build.VERSION.SDK_INT >= 31)
                    params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED);
                id = manager.createSession(params);
                try (PackageInstaller.Session session = manager.openSession(id);
                     FileInputStream input = new FileInputStream(file);
                     OutputStream output = session.openWrite("base.apk", 0, file.length())) {
                    byte[] buffer = new byte[1024 * 1024];
                    int count;
                    while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                    session.fsync(output);
                    output.close();
                    Intent result = new Intent(app, InstallReceiver.class).setAction("org.bobbi.helper.INSTALLED");
                    PendingIntent pending = PendingIntent.getBroadcast(app, id, result,
                            PendingIntent.FLAG_UPDATE_CURRENT |
                            (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0));
                    session.commit(pending.getIntentSender());
                    installState = "WAITING_SYSTEM";
                }
            } catch (Exception error) {
                if (id >= 0) try { manager.abandonSession(id); } catch (Exception ignored) { }
                installState = "FAILED";
                installing.set(false);
            }
        }, "bobbi-apk-install").start();
    }
    static void installFinished(String state) {
        installState = state;
        installing.set(false);
    }
    public static synchronized String request(String action, String argument) {
        try {
            Context app = context;
            if (app == null) return "{\"state\":\"UNAVAILABLE\"}";
            if ("engine_start".equals(action)) {
                if (!visible()) return "{\"state\":\"FOREGROUND_REQUIRED\"}";
                EngineService.requestStart(app);
                return "{\"state\":\"REQUESTED\"}";
            }
            if ("engine_stop".equals(action)) {
                EngineService.requestStop();
                return "{\"state\":\"REQUESTED\"}";
            }
            if ("engine_status".equals(action)) {
                EngineService.Snapshot snapshot = EngineService.snapshot;
                JSONObject result = new JSONObject().put("state", snapshot.state).put("detail", snapshot.detail);
                if ("RUNNING".equals(snapshot.state)) {
                    Credentials credentials = Credentials.load(app);
                    File file = new File(app.getNoBackupFilesDir(), "engine-backend.json");
                    JSONObject config = new JSONObject().put("schema", 1)
                        .put("endpoint", "http://127.0.0.1:" + EnginePolicy.PORT)
                        .put("auth", new JSONObject().put("username", credentials.username).put("password", credentials.password))
                        .put("metadata_seconds", 30).put("buffering_seconds", 90);
                    Credentials.write(file, config.toString());
                    result.put("config_path", file.getCanonicalPath());
                }
                return result.toString();
            }
            if ("info".equals(action)) {
                PackageInfo info = app.getPackageManager().getPackageInfo(app.getPackageName(), 0);
                return new JSONObject().put("state", "READY").put("version_code", version(info))
                    .put("abi", android.os.Process.is64Bit() ? "arm64-v8a" : "armeabi-v7a")
                    .put("update_directory", updateDirectory(app).getPath())
                    .put("native_directory", app.getApplicationInfo().nativeLibraryDir)
                    .put("private_directory", app.getNoBackupFilesDir().getCanonicalPath())
                    .put("font_directory", app.getDir("bobbi-fonts", 0).getCanonicalPath())
                    .put("font_cache_directory", app.getDir("bobbi-font-cache", 0).getCanonicalPath())
                    .put("install_state", installState).toString();
            }
            if ("install".equals(action)) {
                if (!visible()) return "{\"state\":\"FOREGROUND_REQUIRED\"}";
                File file = checkedApk(app, argument);
                if (!app.getPackageManager().canRequestPackageInstalls()) {
                    Activity activity = foreground.get();
                    if (activity == null) return "{\"state\":\"FOREGROUND_REQUIRED\"}";
                    activity.runOnUiThread(() -> {
                        try {
                            if (!activity.isFinishing())
                                activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                        Uri.parse("package:" + app.getPackageName())));
                        } catch (RuntimeException ignored) { installState = "PERMISSION_UNAVAILABLE"; }
                    });
                    return "{\"state\":\"PERMISSION_REQUIRED\"}";
                }
                if (!installing.compareAndSet(false, true)) return "{\"state\":\"BUSY\"}";
                installState = "PREPARING";
                install(app, file);
                return "{\"state\":\"REQUESTED\"}";
            }
            return "{\"state\":\"UNSUPPORTED\"}";
        } catch (Exception error) {
            return "{\"state\":\"REJECTED\"}";
        }
    }
}
