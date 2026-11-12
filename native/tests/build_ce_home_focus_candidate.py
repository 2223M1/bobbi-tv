"""Build the directory visibility delta on pinned completion2114 archives, off-device."""
from ce_candidate_builder import main


PREDECESSOR_SHA = '4177ade3b59b0c69062f0e49d1e6dc27fa4dba78aed883721e9e83d4fc36fc6a'
PREDECESSOR_PROOF_SHA = '0b54e0b6b3e982dd9e02f2867cdbc6fc3df36afd7709e7cf4c368ec655651f7c'
UNIT = 'xbmc/guilib/listproviders/DirectoryProvider.cpp'
OBJECT = 'build/guilib_listproviders/CMakeFiles/guilib_listproviders.dir/DirectoryProvider.cpp.o'
ARCHIVE = 'build/guilib_listproviders/guilib_listproviders.a'

PROFILE = dict(
    name='home_focus', prefix='ce-home-focus-',
    patch='0007-bobbi-directory-visibility.patch',
    predecessor_sha256=PREDECESSOR_SHA, predecessor_proof_sha256=PREDECESSOR_PROOF_SHA,
    units=((UNIT, OBJECT, ARCHIVE),), extra_archives=(ARCHIVE,),
    production_harness='run_directory_visibility_test.py',
    production_fixture='directory_visibility_test.cpp',
    copy_sources=('xbmc/guilib/GUIWindow.cpp',), preserve_predecessor_archives=True)


if __name__ == '__main__':
    main(PROFILE, __file__, __doc__)
