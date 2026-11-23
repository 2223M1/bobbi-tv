package org.bobbi.helper;

import org.junit.Test;
import static org.junit.Assert.*;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

public class PairBridgeTest {
    private String send(PairBridge bridge, String code, boolean origin) throws Exception {
        try (Socket socket = new Socket("127.0.0.1", bridge.port())) {
            socket.setSoTimeout(2000);
            socket.getOutputStream().write(("POST /pair HTTP/1.1\r\nHost: localhost\r\nContent-Length: 6\r\n" +
                (origin ? "Origin: https://example.invalid\r\n" : "") + "\r\n" + code).getBytes(StandardCharsets.US_ASCII));
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            byte[] buffer = new byte[2048]; int count;
            while ((count = socket.getInputStream().read(buffer)) != -1) result.write(buffer, 0, count);
            return result.toString("UTF-8");
        }
    }
    @Test public void correctCodeIsSingleUse() throws Exception {
        try (PairBridge bridge = new PairBridge("{\"synthetic\":true}", 0, 5000)) {
            assertTrue(send(bridge, bridge.code, false).endsWith("{\"synthetic\":true}"));
            for (int i = 0; i < 20 && bridge.active(); i++) Thread.sleep(10);
            assertFalse(bridge.active());
        }
    }
    @Test public void browserOriginRejectedEvenWithCorrectCode() throws Exception {
        try (PairBridge bridge = new PairBridge("private", 0, 5000)) {
            String response = send(bridge, bridge.code, true);
            assertTrue(response.startsWith("HTTP/1.1 403"));
            assertFalse(response.contains("private"));
            assertTrue(send(bridge, bridge.code, false).endsWith("private"));
        }
    }
    @Test public void attemptsAreBounded() throws Exception {
        try (PairBridge bridge = new PairBridge("private", 0, 5000)) {
            String wrong = "123456".equals(bridge.code) ? "123457" : "123456";
            for (int i = 0; i < 5; i++) assertTrue(send(bridge, wrong, false).startsWith("HTTP/1.1 403"));
            for (int i = 0; i < 20 && bridge.active(); i++) Thread.sleep(10);
            assertFalse(bridge.active());
        }
    }
    @Test public void expires() throws Exception {
        try (PairBridge bridge = new PairBridge("private", 0, 5)) {
            Thread.sleep(20);
            assertFalse(bridge.active());
        }
    }
}
