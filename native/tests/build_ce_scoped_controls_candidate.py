"""Build scoped controls plus both schema consumers on the frozen Home native."""
from ce_candidate_builder import main


VIDEO = 'xbmc/cores/VideoPlayer/VideoPlayer.cpp'
APPLICATION = 'xbmc/application/ApplicationPlayer.cpp'
FACTORY = 'xbmc/cores/playercorefactory/PlayerCoreConfig.cpp'
RPC = 'xbmc/interfaces/json-rpc/'
RPC_OBJECT = 'build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/'
RPC_ARCHIVE = 'build/interfaces/json-rpc/jsonrpc_interface.a'
WORKSPACE = '/mnt/d/AM6B-Project/bobbi-tv-ce-search-recall-20261026/'
HISTORICAL = '/mnt/d/AM6B-Project/AM6B/tmp/bobbi-review-9446e59-20261112/results/native-build-inputs/'
CE_CONTEXTS = (
    (' #include "windowing/WinSystem.h"\n+#include "utils/ScopeGuard.h"\n \n #include <iterator>\n #include <algorithm>\n',
     ' #include "windowing/WinSystem.h"\n+#include "utils/ScopeGuard.h"\n \n #include <algorithm>\n #include <fcntl.h>\n'),
    (' #include "BobiCompletion.h"\n+#include "BobiScopedControl.h"\n #include "DVDMessageQueue.h"\n',
     ' #include "BobiCompletion.h"\n+#include "BobiScopedControl.h"\n #include "DVDInputStreams/DVDInputStream.h"\n #include "DVDMessageQueue.h"\n'),
    ('       CLog::Log(LOGDEBUG, "demuxer seek to: {:f}", time);\n'
     '       if (m_pDemuxer && m_pDemuxer->SeekTime(time, msg.GetBackward(), &start))\n'
     '       {\n+        scopedApplied = true;\n'
     '         CLog::Log(LOGDEBUG, "demuxer seek to: {:f}, success", time);\n'
     '         if(m_pSubtitleDemuxer)\n',
     '       logComponentM(LOGDEBUG, LOGVIDEO, "demuxer seek to: {:f}", time);\n'
     '       if (m_pDemuxer && m_pDemuxer->SeekTime(time, msg.GetBackward(), &start))\n'
     '       {\n+        scopedApplied = true;\n'
     '         logComponentM(LOGDEBUG, LOGVIDEO, "demuxer seek to: {:f}, success", time);\n'
     '         if (m_pSubtitleDemuxer)\n'),
    ('+            AdaptForcedSubtitles();\n \n           CDVDMsgPlayerSeek::CMode mode;\n',
     '+            AdaptForcedSubtitles();\n \n'
     '           if (m_pInputStream && m_pInputStream->IsStreamType(DVDSTREAM_TYPE_BLURAY) && m_pDemuxer)\n'
     '           {\n'
     '             CDemuxStream* ds = m_pDemuxer->GetStream(st.demuxerId, st.id);\n'
     '             if (ds)\n'
     '               std::static_pointer_cast<CDVDInputStreamBluray>(m_pInputStream)\n'
     '                 ->EnableStream(BLURAY_AUDIO_STREAM, ds->dvdNavId, true);\n'
     '           }\n \n           CDVDMsgPlayerSeek::CMode mode;\n'),
)
CE_VARIANTS = (
    ('preserve-ce-subtitle-switch-and-bluray',
     '           CloseStream(m_CurrentSubtitle, false);\n'
     '-          OpenStream(m_CurrentSubtitle, st.demuxerId, st.id, st.source);\n'
     '+          scopedApplied = OpenStream(m_CurrentSubtitle, st.demuxerId, st.id, st.source);\n'
     '         }\n       }\n     }\n',
     '           CloseStream(m_CurrentSubtitle, false);\n'
     '-          if (OpenStream(m_CurrentSubtitle, st.demuxerId, st.id, st.source))\n'
     '+          scopedApplied = OpenStream(m_CurrentSubtitle, st.demuxerId, st.id, st.source);\n'
     '+          if (scopedApplied)\n'
     '           {\n             QueueSubtitleSwitchSeek(st);\n'
     '             if (m_pInputStream && m_pInputStream->IsStreamType(DVDSTREAM_TYPE_BLURAY) && m_pDemuxer)\n'),
)
CE_CONTEXTS += (
    ('         SetEnableStream(m_CurrentSubtitle, false);\n \n'
     '       SetSubtitleVisibleInternal(isVisible);\n+      scopedApplied = GetSubtitleVisible() == isVisible;\n',
     '       }\n \n'
     '       SetSubtitleVisibleInternal(isVisible);\n+      scopedApplied = GetSubtitleVisible() == isVisible;\n'),
)
PROFILE = dict(
    name='scoped_controls', prefix='ce-scoped-controls-',
    patch='0008-bobbi-scoped-playback-controls.patch',
    predecessor_sha256='591fa655fa6a507145c7fd90163a18eee91266b98fe89315268e1a5bd32be032',
    predecessor_proof_sha256='8de56368ca0f4d47f5a3e0207201d0c29bf67866b0cc60d93c7d4803930d9993',
    units=(
        (VIDEO, 'build/cores/VideoPlayer/CMakeFiles/VideoPlayer.dir/VideoPlayer.cpp.o', 'build/cores/VideoPlayer/VideoPlayer.a'),
        (APPLICATION, 'build/application/CMakeFiles/application.dir/ApplicationPlayer.cpp.o', 'build/application/application.a'),
        (FACTORY, 'build/cores/playercorefactory/CMakeFiles/playercorefactory.dir/PlayerCoreConfig.cpp.o', 'build/cores/playercorefactory/playercorefactory.a'),
        (RPC+'PlayerOperations.cpp', RPC_OBJECT+'PlayerOperations.cpp.o', RPC_ARCHIVE),
        (RPC+'JSONRPC.cpp', RPC_OBJECT+'JSONRPC.cpp.o', RPC_ARCHIVE),
        (RPC+'JSONServiceDescription.cpp', RPC_OBJECT+'JSONServiceDescription.cpp.o', RPC_ARCHIVE)),
    layout_header='xbmc/cores/VideoPlayer/VideoPlayer.h',
    layout_units=(VIDEO, APPLICATION, FACTORY), schema_methods=('Player.BobiControl',),
    contexts=CE_CONTEXTS, variant_hunks=CE_VARIANTS,
    platform_patch='tests/ce_scoped_subtitle_followup.patch',
    historical_inputs={WORKSPACE+'native/patches/series.json': HISTORICAL+'series-9446e59.json',
                       WORKSPACE+'native/tests/ce_candidate_builder.py': HISTORICAL+'ce_candidate_builder-9446e59.py'})


if __name__ == '__main__':
    main(PROFILE, __file__, __doc__)
