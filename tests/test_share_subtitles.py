from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.catalog/lib'))
from bobbi_core import share_subtitles as sidecar

CHINESE = '1\n00:30:00,000 --> 00:30:02,000\n中文字幕，不用通过时间轴准入\n'.encode()
VIDEO = 'Example.2025.S01E02.1080p.Group.mkv'


@pytest.mark.parametrize('name', ['Example.2025.S01E03.1080p.Group.chs.srt', 'Other.2025.chs.srt',
                                'Example.2025.S01E02.1080p.Group.forced.srt', '../sub.srt'])
def test_wrong_work_episode_or_forced_never_selected(name):
    assert not sidecar.matches(VIDEO, name)


def test_sidecar_beyond_first_page_and_no_video_read(tmp_path):
    row = dict(name=VIDEO, size=999999, parent='11', share={'code':'fixture','password':''})
    calls = []
    class API:
        def list_directory(self, share, parent, offset, limit, deadline, cancelled):
            calls.append(offset)
            if not offset:
                return dict(rows=[dict(fid=str(i+1000),name='folder',size=0,is_dir=True) for i in range(100)], total=101)
            return dict(rows=[dict(fid='7',name=VIDEO[:-4]+'.chs.srt',size=len(CHINESE),is_dir=False)], total=101)
        def resolve(self, share, file, deadline):
            assert file['fid'] == '7'
            return 'https://cdn.115cdn.com/subtitle|User-Agent=fixture'
    answer = sidecar.fetch_candidate(dict(title=VIDEO,size=999999), {'duration':60}, time.monotonic()+10,
        lambda: False, API(), lambda: True, selected=lambda _: row,
        transport=lambda *args, **kw: CHINESE, root=tmp_path/'subtitles')
    assert calls == [0,100]
    assert Path(answer['file']['path']).read_bytes() == CHINESE
    assert answer['origin'] == 'same-share'


def test_account_change_cannot_publish(tmp_path):
    row = dict(name=VIDEO,size=1,parent='11',share={})
    with pytest.raises(sidecar.Stopped, match='ACCOUNT_CHANGED'):
        sidecar.fetch_candidate(dict(title=VIDEO,size=1), {}, time.monotonic()+1,
            lambda:False, object(), lambda:False, selected=lambda _:row, root=tmp_path)
