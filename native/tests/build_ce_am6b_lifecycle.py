"""Build the AM6B frame-drain and skin-settings lifetime fix on the pinned tempo kernel."""
from ce_candidate_builder import main

SRC = 'xbmc/cores/VideoPlayer/'
BLD = 'build/cores/VideoPlayer/'
HEADER = SRC + 'DVDCodecs/Video/DVDVideoCodecAmlogic.h'
AML = SRC + 'DVDCodecs/Video/DVDVideoCodecAmlogic.cpp'
RENDER = SRC + 'VideoRenderers/HwDecRender/RendererAML.cpp'
WIN = 'xbmc/windowing/amlogic/WinSystemAmlogic.cpp'
SKIN = 'xbmc/addons/Skin.cpp'


def unit(source, folder, archive):
    return (source, f'{folder}/CMakeFiles/{archive}.dir/{source.rsplit("/", 1)[-1]}.o',
            f'{folder}/{archive}.a')


UNITS = (unit(AML, BLD+'codecs/video', 'dvdvideocodecs'),
         unit(RENDER, BLD+'videorenderers/hwdec', 'videorenderers_hwdec'),
         unit(WIN, 'build/windowing/amlogic', 'windowing_Amlogic'),
         unit(SKIN, 'build/addons', 'addons'))
PROFILE = dict(
    name='am6b_lifecycle', prefix='ce-am6b-lifecycle-', series='ce-am6b-lifecycle-series.json',
    patch='ce-am6b-lifecycle.patch',
    predecessor_sha256='dbe974c131f9b8fc82b16eefee80348bac18c44b549245b5f4883c2cc1f8fb25',
    predecessor_proof_sha256='bf105debf8bae6628ee1ee0a7b649e1d67de45ecbadfe36ec9d6d4ae6b2c5e54',
    # AML.cpp already carries the predecessor's audible-tempo implementation.
    copy_sources=(HEADER, RENDER, RENDER[:-3]+'h', WIN, SKIN),
    layout_header=HEADER, layout_units=(AML, RENDER, WIN), units=UNITS,
    extra_archives=tuple(u[2] for u in UNITS))

if __name__ == '__main__':
    main(PROFILE, __file__, __doc__)
