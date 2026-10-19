package org.bobbi.helper;

import org.junit.Test;
import static org.junit.Assert.*;

public class EnginePresentationTest {
    @Test public void readyDoesNotClaimPlaybackCertification() {
        assertEquals("已就绪，可以打开 Kodi", EnginePresentation.state("RUNNING"));
        assertTrue(EnginePresentation.detail("CONTROL_AUTH_VERIFIED_MEDIA_BOUNDARY_APPLIES").contains("首次使用"));
    }

    @Test public void uncertainStopProvidesSystemActionNotFalseSuccess() {
        assertEquals("需要系统协助停止", EnginePresentation.state("STOP_UNCONFIRMED"));
        assertTrue(EnginePresentation.detail("PROCESS_STOP_NOT_CONFIRMED_USE_ANDROID_FORCE_STOP").contains("强行停止"));
        assertTrue(EnginePresentation.detail("SERVICE_DESTROYED_NO_AUTOMATIC_RESTART").contains("尚不能确认"));
    }

    @Test public void portConflictNeverSuggestsKillingOtherServices() {
        assertTrue(EnginePresentation.detail("PORT_IN_USE").contains("没有停止它"));
    }
}
