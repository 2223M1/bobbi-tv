"""Add audible file tempo to the proven CE disc-page overlay. Not an Android build."""
from ce_candidate_builder import main

SRC = 'xbmc/cores/VideoPlayer/'
BLD = 'build/cores/VideoPlayer/'
VID = BLD + 'CMakeFiles/VideoPlayer.dir/'
ARCH = BLD + 'VideoPlayer.a'
CODEC = BLD + 'codecs/video/'
VIDEO = SRC + 'VideoPlayer.cpp'
AUDIO = SRC + 'VideoPlayerAudio.cpp'
HEADER = SRC + 'VideoPlayerAudio.h'
AML = SRC + 'DVDCodecs/Video/DVDVideoCodecAmlogic.cpp'
PROFILE = dict(
    name='tempo_experiment', prefix='ce-pcm-tempo-', series='ce-audible-tempo-series.json',
    patch='ce-audible-tempo.patch',
    predecessor_sha256='43f733dc7ae0bbe9cc505f6730d29bc17bae2f3587a2907cf46500bbb127ef60',
    predecessor_proof_sha256='56aa97f442c594bb64c7518fa1461538beef0288818cb5479001c5b146555d0a',
    copy_sources=(HEADER, AUDIO, AML), layout_header=HEADER, layout_units=(VIDEO, AUDIO),
    units=((VIDEO, VID+'VideoPlayer.cpp.o', ARCH), (AUDIO, VID+'VideoPlayerAudio.cpp.o', ARCH),
           (AML, CODEC+'CMakeFiles/dvdvideocodecs.dir/DVDVideoCodecAmlogic.cpp.o', CODEC+'dvdvideocodecs.a')),
    extra_archives=(ARCH, CODEC+'dvdvideocodecs.a'))

if __name__ == '__main__':
    main(PROFILE, __file__, __doc__)
