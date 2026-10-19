package org.bobbi.helper;

import android.content.Context;
import android.util.AtomicFile;
import android.util.Base64;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;

/** Private, backup-excluded installation credentials. Never written to logs/URLs. */
final class Credentials {
    final String username;
    final String password;

    private Credentials(String user, String pass) { username = user; password = pass; }

    static synchronized Credentials load(Context context) throws Exception {
        File file = new File(context.getNoBackupFilesDir(), "engine-credentials.json");
        AtomicFile storage = new AtomicFile(file);
        JSONObject value;
        if (file.exists() || new File(file.getPath() + ".bak").exists()) {
            if ((file.exists() && file.length() > 4096) || new File(file.getPath() + ".bak").length() > 4096)
                throw new IllegalStateException("CREDENTIALS_INVALID");
            value = new JSONObject(new String(storage.readFully(), StandardCharsets.UTF_8));
        } else {
            SecureRandom random = new SecureRandom();
            byte[] user = new byte[6];
            byte[] pass = new byte[24];
            random.nextBytes(user);
            random.nextBytes(pass);
            value = new JSONObject().put("username", "bobbi_" + hex(user)).put("password", hex(pass));
            write(file, value.toString());
        }
        String user = value.getString("username");
        String pass = value.getString("password");
        if (!user.matches("bobbi_[0-9a-f]{12}") || !pass.matches("[0-9a-f]{48}"))
            throw new IllegalStateException("CREDENTIALS_INVALID");
        return new Credentials(user, pass);
    }

    String authorization() {
        return "Basic " + Base64.encodeToString((username + ":" + password)
                .getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
    }

    String pairing() throws Exception {
        return new JSONObject().put("schema", "bobbi-local-engine-v1")
                .put("engine", "TorrServer").put("version", BuildConfig.ENGINE_VERSION)
                .put("url", "http://127.0.0.1:" + EnginePolicy.PORT)
                .put("username", username).put("password", password).toString(2);
    }

    String accounts() throws Exception { return new JSONObject().put(username, password).toString(); }

    static void write(File file, String value) throws Exception {
        AtomicFile storage = new AtomicFile(file);
        FileOutputStream stream = null;
        try {
            stream = storage.startWrite();
            stream.write(value.getBytes(StandardCharsets.UTF_8));
            storage.finishWrite(stream);
            stream = null;
            if (!file.setReadable(false, false) || !file.setWritable(false, false)
                    || !file.setReadable(true, true) || !file.setWritable(true, true))
                throw new IllegalStateException("PRIVATE_PERMISSIONS_FAILED");
        } finally {
            if (stream != null) storage.failWrite(stream);
        }
    }

    static String hex(byte[] value) {
        StringBuilder result = new StringBuilder();
        for (byte item : value) result.append(String.format(java.util.Locale.ROOT, "%02x", item & 255));
        return result.toString();
    }
}
