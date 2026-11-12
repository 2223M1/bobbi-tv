"""Build the canonical completion delta on verified frozen CE archives, off-device."""
from ce_candidate_builder import main


PROFILE = dict(
    name='completion', prefix='ce-completion-',
    patch='0006-bobbi-completion-observation.patch', verified_predecessor=True,
    units=(
        ('xbmc/cores/VideoPlayer/VideoPlayer.cpp', 'build/cores/VideoPlayer/CMakeFiles/VideoPlayer.dir/VideoPlayer.cpp.o', 'build/cores/VideoPlayer/VideoPlayer.a'),
        ('xbmc/application/ApplicationPlayer.cpp', 'build/application/CMakeFiles/application.dir/ApplicationPlayer.cpp.o', 'build/application/application.a'),
        ('xbmc/cores/playercorefactory/PlayerCoreConfig.cpp', 'build/cores/playercorefactory/CMakeFiles/playercorefactory.dir/PlayerCoreConfig.cpp.o', 'build/cores/playercorefactory/playercorefactory.a')),
    layout_header='xbmc/cores/VideoPlayer/VideoPlayer.h',
    contexts=(
        ('   CLog::Log(LOGDEBUG, "CVideoPlayer::FlushBuffers - flushing buffers");',
         '   logComponentM(LOGDEBUG, LOGVIDEO, "CVideoPlayer::FlushBuffers - flushing buffers");'),
        ('+#include "BobiCompletion.h"\n #include "DVDMessageQueue.h"',
         '+#include "BobiCompletion.h"\n #include "DVDInputStreams/DVDInputStream.h"\n #include "DVDMessageQueue.h"')))


if __name__ == '__main__':
    main(PROFILE, __file__, __doc__)
