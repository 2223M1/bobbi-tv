package org.bobbi.helper;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PersistableBundle;
import android.provider.Settings;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/** Native, remote-focusable UI. Pairing is disclosed only after explicit user action. */
public final class MainActivity extends Activity {
    private static final int EXPORT_PAIRING = 20;
    private static final int EXPORT_INSTALLER = 21;
    private final Handler main = new Handler(Looper.getMainLooper());
    private TextView status;
    private Button start;
    private Button stop;
    private CinemaStyle cinema;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            EngineService.Snapshot value = EngineService.snapshot;
            String diagnostic = "FAILED".equals(value.state) || "STOP_UNCONFIRMED".equals(value.state)
                    ? getString(R.string.diagnostic_format, value.detail) : "";
            status.setText(getString(R.string.status_format, EnginePresentation.state(value.state),
                    EnginePresentation.detail(value.detail), diagnostic));
            PairBridge bridge = EngineService.pairing;
            if (bridge != null && bridge.active()) status.append("\n配对码：" + bridge.code + "（两分钟内有效）");
            start.setEnabled(!value.busy());
            stop.setEnabled(value.busy() && !"STOP_UNCONFIRMED".equals(value.state));
            main.postDelayed(this, 1000);
        }
    };

    @Override public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setFitsSystemWindows(true);
        cinema = new CinemaStyle(this);
        LinearLayout page = cinema.column();
        int padding = cinema.dp(32);
        page.setPadding(padding, padding, padding, padding);
        page.setBackgroundColor(cinema.color(R.color.cinema_bg));
        scroll.setClipToPadding(false);
        scroll.addView(page);
        page.addView(cinema.text("bobbi  /  波比影院", 27, true, R.color.cinema_text));
        LinearLayout body = new LinearLayout(this);
        boolean wide = getResources().getConfiguration().screenWidthDp >= 720;
        body.setOrientation(wide ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        body.setClipChildren(false);
        page.addView(body);
        LinearLayout intro = cinema.column();
        intro.setPadding(0, cinema.dp(20), wide ? cinema.dp(36) : 0, cinema.dp(20));
        body.addView(intro, new LinearLayout.LayoutParams(wide ? 0 : -1, -2, wide ? .43f : 0));
        intro.addView(cinema.text("ANDROID  ·  本机助手", 14, true, R.color.cinema_accent_text));
        intro.addView(cinema.text("准备好后台，\n再进入影院。", 34, true, R.color.cinema_text));
        intro.addView(cinema.text("安装影院 → 启动后台 → 输入配对码\n不需要选择盒子型号。", 18, false, R.color.cinema_text_secondary));
        intro.addView(cinema.text(getString(R.string.preview_warning), 15, false, R.color.cinema_text_muted));
        LinearLayout content = cinema.column();
        content.setPadding(cinema.dp(24), cinema.dp(20), cinema.dp(24), cinema.dp(20));
        content.setBackground(cinema.shape(R.color.cinema_surface, R.color.cinema_line));
        body.addView(content, new LinearLayout.LayoutParams(wide ? 0 : -1, -2, wide ? .57f : 0));
        content.addView(cinema.text("本机后台", 14, true, R.color.cinema_accent_text));
        status = text("状态：未运行", 18);
        status.setMinLines(3);
        content.addView(status);
        cinema.button(content, "1. 安装 / 更新波比影院").setOnClickListener(view -> installCinema());
        start = button(content, R.string.start);
        start.setOnClickListener(view -> startEngine());
        cinema.button(content, "3. 显示六位配对码").setOnClickListener(view -> {
            if (!"RUNNING".equals(EngineService.snapshot.state)) {
                new AlertDialog.Builder(this).setMessage("请先启动后台，等待状态显示运行中。").setPositiveButton("知道了", null).show();
            } else startService(new Intent(this, EngineService.class).setAction(EngineService.PAIR));
        });
        button(content, R.string.open_kodi).setOnClickListener(view -> openKodi());
        stop = button(content, R.string.stop);
        stop.setOnClickListener(view -> startService(new Intent(this, EngineService.class).setAction(EngineService.STOP)));
        cinema.button(content, "更多与说明").setOnClickListener(view -> showMore());
        page.addView(cinema.text(getString(R.string.foreground_explanation), 14, false, R.color.cinema_text_secondary));
        page.addView(cinema.text("界面沿用波比影院新 UI · 使用未修改的 HarmonyOS Sans 字体（华为）", 12, false, R.color.cinema_text_muted));
        setContentView(scroll);
        start.requestFocus();
    }

    private TextView text(String value, int sp) {
        return cinema.text(value, sp, false, R.color.cinema_text);
    }

    private Button button(LinearLayout parent, int label) {
        return cinema.button(parent, getString(label));
    }

    private void showMore() {
        new AlertDialog.Builder(this).setTitle("bobbi · 更多与说明")
            .setItems(new String[]{"备用：导出配对文件", getString(R.string.app_settings), "连接范围与开源说明"}, (dialog, item) -> {
                if (item == 0) explainExport();
                else if (item == 1) {
                    Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            android.net.Uri.parse("package:" + getPackageName()));
                    try { startActivity(intent); }
                    catch (RuntimeException unavailable) { Toast.makeText(this, R.string.settings_unavailable, Toast.LENGTH_LONG).show(); }
                } else {
                    new AlertDialog.Builder(this).setTitle("连接范围与开源说明")
                        .setMessage(getString(R.string.media_boundary) + "\n\n" + getString(R.string.notice)
                            + "\n\nHarmonyOS Sans：Copyright 2021 Huawei Device Co., Ltd. 原字体未修改；许可证随包附带。")
                        .setPositiveButton(R.string.close, null).show();
                }
            }).show();
    }

    private void openKodi() {
        Intent launch = getPackageManager().getLeanbackLaunchIntentForPackage("org.xbmc.kodi");
        if (launch == null) launch = getPackageManager().getLaunchIntentForPackage("org.xbmc.kodi");
        try {
            if (launch == null) throw new IllegalStateException();
            startActivity(launch);
        } catch (RuntimeException unavailable) {
            new AlertDialog.Builder(this).setTitle("先安装 Kodi 21")
                .setMessage("影院在 Kodi 内运行。本助手不包含 Kodi，不会替换已有播放器。打开官网下载 Android 版后，再回到此处安装影院。")
                .setNegativeButton("返回", null).setPositiveButton("Kodi 官网", (dialog, which) -> openWeb("https://kodi.tv/download/android/")).show();
        }
    }

    private void openWeb(String url) {
        try { startActivity(new Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url))); }
        catch (RuntimeException unavailable) { Toast.makeText(this, "请在手机打开 github.com/2223M1/bobbi-tv", Toast.LENGTH_LONG).show(); }
    }

    private void installCinema() {
        new AlertDialog.Builder(this).setTitle("安装波比影院 · 只需安装一个仓库")
            .setMessage("① 将安装文件保存到 Downloads。\n② Kodi → 插件 → 从 ZIP 文件安装，选择 repository.bobbi.zip。\n③ 从库安装 → bobbi TV → 程序插件 → bobbi 开始使用。其余组件自动下载。\n\n以后通过同一个 Kodi 仓库收到更新；APK 更新仍需系统确认。不会刷机或改音画设置。")
            .setNegativeButton("查看下载 / 更新", (dialog, which) -> openWeb("https://github.com/2223M1/bobbi-tv/releases"))
            .setPositiveButton("保存安装文件", (dialog, which) -> {
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                    .setType("application/zip").putExtra(Intent.EXTRA_TITLE, "repository.bobbi.zip");
                try { startActivityForResult(intent, EXPORT_INSTALLER); }
                catch (RuntimeException unavailable) { openWeb("https://github.com/2223M1/bobbi-tv/releases"); }
            }).show();
    }

    private void startEngine() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
                && !getPreferences(MODE_PRIVATE).getBoolean("notification_asked", false)) {
            getPreferences(MODE_PRIVATE).edit().putBoolean("notification_asked", true).apply();
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 10);
        }
        try { startForegroundService(new Intent(this, EngineService.class).setAction(EngineService.START)); }
        catch (RuntimeException denied) { Toast.makeText(this, R.string.start_rejected, Toast.LENGTH_LONG).show(); }
    }

    private void showPairing() {
        try {
            String json = Credentials.load(this).pairing();
            TextView value = text(json + "\n\n" + getString(R.string.pairing_warning), 15);
            value.setTextIsSelectable(true);
            int pad = (int) (20 * getResources().getDisplayMetrics().density);
            value.setPadding(pad, pad, pad, pad);
            AlertDialog dialog = new AlertDialog.Builder(this).setTitle(R.string.pairing_title).setView(value)
                    .setNegativeButton(R.string.close, null).setPositiveButton(R.string.copy, (which, button) -> {
                        ClipData clip = ClipData.newPlainText("bobbi local pairing", json);
                        PersistableBundle extras = new PersistableBundle();
                        extras.putBoolean("android.content.extra.IS_SENSITIVE", true);
                        clip.getDescription().setExtras(extras);
                        getSystemService(ClipboardManager.class).setPrimaryClip(clip);
                        Toast.makeText(this, R.string.copied, Toast.LENGTH_LONG).show();
                    }).create();
            if (dialog.getWindow() != null) dialog.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
            dialog.show();
        } catch (Exception unavailable) { Toast.makeText(this, R.string.credentials_failed, Toast.LENGTH_LONG).show(); }
    }

    private void explainExport() {
        new AlertDialog.Builder(this).setTitle(R.string.export_pairing)
                .setMessage(R.string.pairing_warning).setNegativeButton(R.string.close, null)
                .setPositiveButton(R.string.export_pairing, (dialog, button) -> {
                    Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                            .setType("application/json").putExtra(Intent.EXTRA_TITLE, "bobbi-pairing.json");
                    try { startActivityForResult(intent, EXPORT_PAIRING); }
                    catch (RuntimeException unavailable) { Toast.makeText(this, R.string.document_unavailable, Toast.LENGTH_LONG).show(); }
                }).show();
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if ((requestCode != EXPORT_PAIRING && requestCode != EXPORT_INSTALLER) || resultCode != RESULT_OK || data == null || data.getData() == null) return;
        android.net.Uri uri = data.getData();
        if (!"content".equals(uri.getScheme())) {
            Toast.makeText(this, R.string.export_failed, Toast.LENGTH_LONG).show();
            return;
        }
        new Thread(() -> {
            int message = R.string.export_complete;
            try {
                try (OutputStream output = getContentResolver().openOutputStream(uri, "wt")) {
                    if (output == null) throw new IllegalStateException();
                    if (requestCode == EXPORT_INSTALLER) {
                        try (java.io.InputStream input = getAssets().open("repository.bobbi.zip")) {
                            byte[] buffer = new byte[16384]; int count;
                            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                        }
                    } else output.write(Credentials.load(this).pairing().getBytes(StandardCharsets.UTF_8));
                }
            } catch (Exception unavailable) { message = R.string.export_failed; }
            final int result = message;
            main.post(() -> { if (!isFinishing() && !isDestroyed()) {
                if (requestCode == EXPORT_INSTALLER && result == R.string.export_complete)
                    new AlertDialog.Builder(this).setMessage("安装文件已保存。接下来在 Kodi 从 ZIP 安装，然后从 bobbi 仓库安装“bobbi 开始使用”。")
                        .setPositiveButton("打开 Kodi", (dialog, which) -> openKodi()).show();
                else Toast.makeText(this, result, Toast.LENGTH_LONG).show();
            } });
        }, "bobbi-explicit-pairing-export").start();
    }

    @Override protected void onResume() { super.onResume(); main.post(refresh); }
    @Override protected void onPause() { main.removeCallbacks(refresh); super.onPause(); }
}
