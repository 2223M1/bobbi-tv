package org.bobbi.helper;

import org.junit.Test;
import java.io.File;
import java.util.List;
import static org.junit.Assert.*;

public class EnginePolicyTest {
    @Test public void exactCommandUsesSeparateArgsAndLoopbackAuth() {
        File nativeFile = new File("/data/app/pkg/lib/arm64/libbobbi_torrserver.so").getAbsoluteFile();
        File data = new File("/data/user/0/org.bobbi.helper/no_backup/torrserver").getAbsoluteFile();
        List<String> args = EnginePolicy.command(nativeFile, data);
        assertEquals(nativeFile.getPath(), args.get(0));
        assertEquals("127.0.0.1", args.get(args.indexOf("-i") + 1));
        assertEquals("8090", args.get(args.indexOf("-p") + 1));
        assertTrue(args.contains("-a"));
        assertEquals(data.getPath(), args.get(args.indexOf("-d") + 1));
        assertEquals("/dev/null", args.get(args.indexOf("-l") + 1));
        assertEquals("/dev/null", args.get(args.indexOf("-w") + 1));
        for (String forbidden : new String[]{"-k", "-u", "-s", "-t", "-T", "--webdav", "sh", "su", "&"})
            assertFalse(args.contains(forbidden));
    }

    @Test public void spacesInPathsAreNeverShellInterpolation() {
        File nativeFile = new File("/data/test space/libbobbi_torrserver.so").getAbsoluteFile();
        File data = new File("/data/test space/private").getAbsoluteFile();
        List<String> args = EnginePolicy.command(nativeFile, data);
        assertEquals(nativeFile.getPath(), args.get(0));
        assertEquals(data.getPath(), args.get(args.indexOf("-d") + 1));
    }

    @Test public void exactEngineVersionsAndABIsOnly() {
        assertEquals("MatriX.147", BuildConfig.ENGINE_VERSION);
        assertEquals(64, EnginePolicy.expectedHash("armeabi-v7a").length());
        assertEquals(64, EnginePolicy.expectedHash("arm64-v8a").length());
        assertNull(EnginePolicy.expectedHash("x86_64"));
    }

    @Test public void noDiscoveryDiskOrAddedTrackerServiceByDefault() {
        for (String flag : new String[]{"EnableBonjour", "EnableLPD", "EnableDLNA", "UseDisk",
                "EnableRutorSearch", "EnableTorznabSearch", "EnableDebug"})
            assertTrue(EnginePolicy.SETTINGS.contains("\"" + flag + "\":false"));
        assertTrue(EnginePolicy.SETTINGS.contains("\"DisableUPNP\":true"));
        assertTrue(EnginePolicy.SETTINGS.contains("\"RetrackersMode\":0"));
        assertTrue(EnginePolicy.SETTINGS.startsWith("{\"BitTorr\":{"));
    }
}
