"""Build explicit user transport on the untouched scoped2122 CE predecessor."""
from ce_candidate_builder import main
from pathlib import Path
from build_ce_scoped_controls_candidate import VIDEO, APPLICATION, FACTORY, RPC, RPC_OBJECT, RPC_ARCHIVE

PROFILE = dict(
    name='user_transport', prefix='ce-user-transport-',
    patch='0009-bobbi-user-transport-controls.patch',
    predecessor_sha256='7e88830c9cb24ef22a64a521a035a5ba411d17aeb57af2ba9db874fd9689294c',
    predecessor_proof_sha256='86d981e935ff6968c54373724682fb7bd80f24edecc40c3ba0f45e2953df2c0b',
    units=(
        (VIDEO, 'build/cores/VideoPlayer/CMakeFiles/VideoPlayer.dir/VideoPlayer.cpp.o', 'build/cores/VideoPlayer/VideoPlayer.a'),
        (APPLICATION, 'build/application/CMakeFiles/application.dir/ApplicationPlayer.cpp.o', 'build/application/application.a'),
        (FACTORY, 'build/cores/playercorefactory/CMakeFiles/playercorefactory.dir/PlayerCoreConfig.cpp.o', 'build/cores/playercorefactory/playercorefactory.a'),
        (RPC+'PlayerOperations.cpp', RPC_OBJECT+'PlayerOperations.cpp.o', RPC_ARCHIVE),
        (RPC+'JSONRPC.cpp', RPC_OBJECT+'JSONRPC.cpp.o', RPC_ARCHIVE),
        (RPC+'JSONServiceDescription.cpp', RPC_OBJECT+'JSONServiceDescription.cpp.o', RPC_ARCHIVE)),
    layout_header='xbmc/cores/VideoPlayer/VideoPlayer.h',
    layout_units=(VIDEO, APPLICATION, FACTORY), schema_methods=('Player.BobiControl',),
    contexts=(
        (' #include "utils/ScopeGuard.h"\n+#include <exception>\n \n #include <iterator>\n #include <algorithm>\n',
         ' #include "utils/ScopeGuard.h"\n+#include <exception>\n \n #include <algorithm>\n #include <fcntl.h>\n'),
        ('   CLog::Log(LOGINFO, "CVideoPlayer::OnExit()");\n',
         '   CLog::Log(LOGDEBUG, "CVideoPlayer::OnExit()");\n'),
        ('   // thread, not directly when initalizing the player to keep GUI responsible.\n',
         '   // thread, not directly when initializing the player to keep GUI responsible.\n'),
        ('       if (std::static_pointer_cast<CDVDMsgPlayerSetSpeed>(pMsg)->IsTempo())\n'
         '         m_processInfo->SetTempo(static_cast<float>(speed) / DVD_PLAYSPEED_NORMAL);\n'
         '       else\n',
         '       if ((speed == DVD_PLAYSPEED_NORMAL) &&\n'
         '           (m_playSpeed == DVD_PLAYSPEED_PAUSE) &&\n'
         '           m_State.canseek && m_pInputStream && !m_pInputStream->IsRealtime() &&\n')),
    platform_patch='tests/ce_user_transport_followup.patch',
    historical_inputs={
        '/mnt/d/AM6B-Project/bobbi-tv-ce-search-recall-20261026/native/patches/series.json':
        str(Path(__file__).with_name('scoped2122-series.json'))})

if __name__ == '__main__':
    main(PROFILE, __file__, __doc__)
