package org.bobbi.helper;

import java.io.File;
import java.util.Arrays;
import java.util.List;

/** Pure policy, independently unit-testable without a device. */
final class EnginePolicy {
    static final int PORT = 8090;
    static final String HOST = "127.0.0.1";
    static final String BINARY = "libbobbi_torrserver.so";
    static final long STARTUP_MILLIS = 30_000;
    static final String SETTINGS = "{\"BitTorr\":{" +
            "\"CacheSize\":67108864,\"PreloadCache\":50,\"ConnectionsLimit\":25," +
            "\"TorrentDisconnectTimeout\":30,\"ReaderReadAHead\":95," +
            "\"ResponsiveMode\":true,\"ShowFSActiveTorr\":true," +
            "\"StoreSettingsInJson\":true,\"StoreViewedInJson\":false," +
            "\"RetrackersMode\":0,\"TrackersListURL\":\"\",\"DefaultTrackers\":\"\"," +
            "\"UseDisk\":false,\"TorrentsSavePath\":\"\",\"EnableBonjour\":false," +
            "\"EnableLPD\":false,\"EnableDLNA\":false,\"EnableRutorSearch\":false," +
            "\"EnableTorznabSearch\":false,\"DisableUPNP\":true," +
            "\"EnableDebug\":false,\"EnableIPv6\":false}}";

    private EnginePolicy() {}

    static List<String> command(File installedBinary, File privateDirectory) {
        if (!installedBinary.isAbsolute() || !privateDirectory.isAbsolute())
            throw new IllegalArgumentException("Absolute Android-owned paths required");
        return Arrays.asList(installedBinary.getPath(), "-i", HOST, "-p", Integer.toString(PORT),
                "-d", privateDirectory.getPath(), "-a", "-l", "/dev/null", "-w", "/dev/null");
    }

    static String expectedHash(String abi) {
        if ("armeabi-v7a".equals(abi)) return BuildConfig.ENGINE_ARM32_SHA256;
        if ("arm64-v8a".equals(abi)) return BuildConfig.ENGINE_ARM64_SHA256;
        return null;
    }
}
