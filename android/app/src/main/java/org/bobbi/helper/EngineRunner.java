package org.bobbi.helper;

import android.content.Context;
import android.os.SystemClock;
import org.json.JSONObject;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.security.MessageDigest;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Owns exactly one installed executable. No shell, downloaded execution, or auto-restart. */
final class EngineRunner implements Runnable {
    interface Listener {
        void state(EngineRunner owner, String state, String detail);
        void finished(EngineRunner owner);
    }
    private static final class Failure extends Exception {
        Failure(String reason) { super(reason); }
    }
    private final Context context;
    private final Listener listener;
    private final AtomicBoolean requested = new AtomicBoolean(true);
    private volatile Process process;

    EngineRunner(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
    }
    boolean requested() { return requested.get(); }

    void stop() {
        requested.set(false);
        Process owned = process;
        if (owned != null) owned.destroy(); // Signal only our exact child, never killall/adopt.
    }

    private void guard() throws Failure {
        if (!requested.get() || Thread.currentThread().isInterrupted()) throw new Failure("CANCELLED");
    }

    private File verifiedBinary() throws Exception {
        File directory = new File(context.getApplicationInfo().nativeLibraryDir).getCanonicalFile();
        File binary = new File(directory, EnginePolicy.BINARY).getCanonicalFile();
        if (!directory.equals(binary.getParentFile()) || !binary.isFile() || !binary.canExecute())
            throw new Failure("ENGINE_MISSING_OR_NOT_EXECUTABLE");
        byte[] header = new byte[20];
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (FileInputStream input = new FileInputStream(binary)) {
            if (input.read(header) != header.length || header[0] != 0x7f || header[1] != 'E'
                    || header[2] != 'L' || header[3] != 'F' || header[5] != 1)
                throw new Failure("ENGINE_FORMAT_INVALID");
            hash.update(header);
            byte[] block = new byte[1024 * 1024];
            int count;
            while ((count = input.read(block)) != -1) { guard(); hash.update(block, 0, count); }
        }
        int machine = (header[18] & 255) | ((header[19] & 255) << 8);
        String abi = machine == 183 ? "arm64-v8a" : machine == 40 ? "armeabi-v7a" : "unsupported";
        String expected = EnginePolicy.expectedHash(abi);
        if (expected == null || !expected.equals(Credentials.hex(hash.digest())))
            throw new Failure("ENGINE_HASH_OR_ABI_INVALID");
        return binary;
    }

    private void ensureFreePort() throws Failure {
        try (ServerSocket socket = new ServerSocket()) {
            socket.setReuseAddress(false);
            socket.bind(new InetSocketAddress(InetAddress.getByName(EnginePolicy.HOST), EnginePolicy.PORT));
        } catch (IOException error) { throw new Failure("PORT_IN_USE"); }
    }

    private void verifySettings(String body) throws Exception {
        JSONObject value = new JSONObject(body);
        for (String name : new String[]{"EnableBonjour", "EnableLPD", "EnableDLNA", "UseDisk",
                "EnableRutorSearch", "EnableTorznabSearch", "EnableDebug"}) {
            if (!value.has(name) || value.getBoolean(name)) throw new Failure("UNSAFE_ENGINE_SETTINGS");
        }
        if (!value.getBoolean("DisableUPNP") || value.getInt("RetrackersMode") != 0
                || !value.getString("TorrentsSavePath").isEmpty())
            throw new Failure("UNSAFE_ENGINE_SETTINGS");
    }

    private void waitForReady(Credentials credentials) throws Exception {
        long deadline = SystemClock.elapsedRealtime() + EnginePolicy.STARTUP_MILLIS;
        while (SystemClock.elapsedRealtime() < deadline) {
            guard();
            if (process == null || !process.isAlive()) throw new Failure("ENGINE_EXITED_DURING_START");
            try {
                EngineHttp.Response anonymous = EngineHttp.settings(null, deadline, () -> !requested.get());
                if (anonymous.code != 401) throw new Failure("CONTROL_AUTH_NOT_ENFORCED");
                guard();
                EngineHttp.Response authorized = EngineHttp.settings(credentials, deadline, () -> !requested.get());
                if (authorized.code != 200) throw new Failure("CONTROL_AUTH_REJECTED");
                verifySettings(authorized.body);
                guard();
                if (!process.isAlive()) throw new Failure("ENGINE_EXITED_DURING_START");
                return;
            } catch (IOException unavailable) {
                // The owned process is starting. No torrent/download requests are retried.
            }
            Thread.sleep(200);
        }
        throw new Failure("STARTUP_TIMEOUT");
    }

    private boolean reapOwnedProcess() {
        Process owned = process;
        if (owned == null) return true;
        owned.destroy();
        try {
            if (!owned.waitFor(10, TimeUnit.SECONDS)) {
                owned.destroyForcibly();
                if (!owned.waitFor(2, TimeUnit.SECONDS)) return false;
            }
        } catch (InterruptedException interrupted) {
            owned.destroyForcibly();
            Thread.currentThread().interrupt();
            if (owned.isAlive()) return false;
        }
        process = null;
        return true;
    }

    @Override public void run() {
        String failure = null;
        try {
            listener.state(this, "STARTING", "VERIFYING_PACKAGED_ENGINE");
            File binary = verifiedBinary();
            guard();
            Credentials credentials = Credentials.load(context);
            File privateDirectory = new File(context.getNoBackupFilesDir(), "torrserver");
            if (!privateDirectory.isDirectory() && !privateDirectory.mkdirs())
                throw new Failure("PRIVATE_STORAGE_UNAVAILABLE");
            Credentials.write(new File(privateDirectory, "accs.db"), credentials.accounts());
            Credentials.write(new File(privateDirectory, "settings.json"), EnginePolicy.SETTINGS);
            ensureFreePort();
            guard();
            ProcessBuilder builder = new ProcessBuilder(EnginePolicy.command(binary, privateDirectory));
            builder.directory(privateDirectory);
            builder.environment().put("GODEBUG", "madvdontneed=1");
            builder.environment().put("TMPDIR", context.getCacheDir().getAbsolutePath());
            builder.redirectOutput(new File("/dev/null"));
            builder.redirectError(new File("/dev/null"));
            process = builder.start();
            listener.state(this, "STARTING", "VERIFYING_CONTROL_AUTH");
            waitForReady(credentials);
            listener.state(this, "RUNNING", "CONTROL_AUTH_VERIFIED_MEDIA_BOUNDARY_APPLIES");
            while (requested.get()) {
                if (!process.isAlive()) throw new Failure("ENGINE_EXITED");
                Thread.sleep(500);
            }
        } catch (Failure error) {
            if (!"CANCELLED".equals(error.getMessage())) failure = error.getMessage();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (Exception unavailable) {
            // Never log exception text, credentials, engine URLs or response bodies.
            failure = "ENGINE_START_OR_STORAGE_FAILED";
        } finally {
            requested.set(false);
            listener.state(this, "STOPPING", "STOPPING_OWNED_PROCESS");
            if (!reapOwnedProcess()) {
                listener.state(this, "STOP_UNCONFIRMED", "PROCESS_STOP_NOT_CONFIRMED_USE_ANDROID_FORCE_STOP");
                return; // Keep the service/owner; do not permit a new child or claim stopped.
            }
            listener.state(this, failure == null ? "STOPPED" : "FAILED", failure == null ? "USER_STOPPED" : failure);
            listener.finished(this);
        }
    }
}
