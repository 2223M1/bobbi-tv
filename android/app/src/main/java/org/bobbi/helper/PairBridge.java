package org.bobbi.helper;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Locale;

/** Five attempts, two minutes, one redemption; binds only the device loopback. */
final class PairBridge implements AutoCloseable {
    private final ServerSocket server;
    private final byte[] document;
    final String code;
    private final long expires;
    private volatile boolean closed;
    private final Thread worker;

    PairBridge(String json) throws IOException { this(json, 8091, 120000); }
    PairBridge(String json, int port, long duration) throws IOException {
        document = json.getBytes(StandardCharsets.UTF_8);
        if (document.length > 4096) throw new IOException("PAIR_SIZE");
        code = String.format(Locale.ROOT, "%06d", new SecureRandom().nextInt(1000000));
        expires = System.nanoTime() + duration * 1000000L;
        server = new ServerSocket();
        server.bind(new InetSocketAddress("127.0.0.1", port), 2);
        server.setSoTimeout(500);
        worker = new Thread(this::serve, "bobbi-one-time-pairing");
        worker.setDaemon(true);
        worker.start();
    }
    int port() { return server.getLocalPort(); }
    boolean active() { return !closed && System.nanoTime() < expires; }

    private static String line(InputStream in) throws IOException {
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        int ch;
        while ((ch = in.read()) >= 0 && ch != '\n') {
            if (line.size() >= 1024) throw new IOException("PAIR_HEADER");
            if (ch != '\r') line.write(ch);
        }
        if (ch < 0) throw new EOFException();
        return line.toString("US-ASCII");
    }
    private void serve() {
        int attempts = 0;
        try {
            while (active() && attempts < 5) {
                try (Socket socket = server.accept()) {
                    attempts++;
                    socket.setSoTimeout(1500);
                    InputStream in = socket.getInputStream();
                    boolean valid = "POST /pair HTTP/1.1".equals(line(in));
                    int length = -1;
                    boolean ended = false;
                    for (int count = 0; count < 24; count++) {
                        String header = line(in);
                        if (header.isEmpty()) { ended = true; break; }
                        String lower = header.toLowerCase(Locale.ROOT);
                        if (lower.startsWith("origin:") || lower.startsWith("transfer-encoding:")) valid = false;
                        if (lower.startsWith("content-length:")) {
                            if (length != -1) valid = false;
                            try { length = Integer.parseInt(header.substring(15).trim()); }
                            catch (NumberFormatException bad) { valid = false; }
                        }
                    }
                    valid &= ended && length == 6 && active();
                    byte[] supplied = new byte[6];
                    if (valid) {
                        new DataInputStream(in).readFully(supplied);
                        valid = java.security.MessageDigest.isEqual(code.getBytes(StandardCharsets.US_ASCII), supplied) && active();
                    }
                    byte[] body = valid ? document : new byte[0];
                    OutputStream out = socket.getOutputStream();
                    out.write(((valid ? "HTTP/1.1 200 OK" : "HTTP/1.1 403 Forbidden") +
                        "\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: " +
                        body.length + "\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
                    out.write(body);
                    out.flush();
                    if (valid) break;
                } catch (SocketTimeoutException idle) { /* bounded wait; no diagnostic data */ }
                  catch (IOException rejected) { if (closed) break; }
            }
        } finally { close(); }
    }
    @Override public void close() {
        closed = true;
        try { server.close(); } catch (IOException ignored) { }
    }
}
