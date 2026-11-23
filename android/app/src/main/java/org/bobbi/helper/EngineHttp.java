package org.bobbi.helper;

import android.os.SystemClock;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.Proxy;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Only two fixed local probes. No redirects, external proxy, URL credentials or logs. */
final class EngineHttp {
    static final class Response {
        final int code;
        final String body;
        Response(int code, String body) { this.code = code; this.body = body; }
    }

    static Response settings(Credentials credentials, long deadline,
                             java.util.function.BooleanSupplier cancelled) throws Exception {
        URL url = new URL("http://127.0.0.1:" + EnginePolicy.PORT + "/settings");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection(Proxy.NO_PROXY);
        try {
            guard(deadline, cancelled);
            connection.setConnectTimeout(500);
            connection.setReadTimeout(1000);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setRequestProperty("Accept-Encoding", "identity");
            if (credentials != null) connection.setRequestProperty("Authorization", credentials.authorization());
            byte[] payload = "{\"action\":\"get\"}".getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(payload.length);
            connection.setDoOutput(true);
            try (java.io.OutputStream output = connection.getOutputStream()) { output.write(payload); }
            int code = connection.getResponseCode();
            guard(deadline, cancelled);
            if (code != 200) return new Response(code, "");
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) {
                byte[] buffer = new byte[4096];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    guard(deadline, cancelled);
                    if (output.size() + count > 262144) throw new IllegalStateException("RESPONSE_LIMIT");
                    output.write(buffer, 0, count);
                }
            }
            return new Response(code, output.toString("UTF-8"));
        } finally { connection.disconnect(); }
    }

    private static void guard(long deadline, java.util.function.BooleanSupplier cancelled) throws java.io.IOException {
        if (cancelled.getAsBoolean() || SystemClock.elapsedRealtime() >= deadline)
            throw new java.io.IOException("LOCAL_PROBE_CANCELLED_OR_DEADLINE");
    }
}
