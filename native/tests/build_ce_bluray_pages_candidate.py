"""Coalesce overlapping native Blu-ray page loads on the exact CE predecessor."""
from ce_candidate_builder import main

FOLDER = 'xbmc/cores/VideoPlayer/DVDInputStreams/'
ARCHIVE = 'build/cores/VideoPlayer/inputstreams/dvdinputstreams.a'
OBJECTS = 'build/cores/VideoPlayer/inputstreams/CMakeFiles/dvdinputstreams.dir/'
UNITS = ('BlurayIsoCache.cpp', 'DVDInputStreamBluray.cpp')
PROFILE = dict(
    name='bluray_pages', prefix='ce-bluray-pages-', series='ce-downstream-series.json',
    patch='ce-bluray-page-load.patch',
    predecessor_sha256='980265b54e3c6993268de894353e5f1291e791253d9f52e99943819997139fe2',
    predecessor_proof_sha256='3cfcf809c4b7b81f5d8ea562449c21ac7c703efd4a304040611f8bb470328fd1',
    units=tuple((FOLDER + name, OBJECTS + name + '.o', ARCHIVE) for name in UNITS),
    extra_archives=(ARCHIVE,), copy_sources=tuple(FOLDER + name for name in (
        *UNITS, 'BlurayIsoCache.h')),
    layout_header=FOLDER+'BlurayIsoCache.h', preserve_predecessor_archives=True)

if __name__ == '__main__':
    main(PROFILE, __file__, __doc__)
