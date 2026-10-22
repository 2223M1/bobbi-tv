"""Reuse the real play_video extraction; exercise both final dispatch forms."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sys
from threading import Event

root=Path(__file__).resolve().parents[1]
sys.argv=['probe','--repo',str(root),'--expect-dispatches','0']
with redirect_stdout(StringIO()):
    fixture=runpy.run_path(str(root/'tests/repros/ce2047_local_cancel.py'))
for handoff in (False,True):
    for stage in ('subtitles','final_phase'):
        cancel=Event()
        player=fixture['factory'](cancel_event=cancel)
        player.data=dict(fixture['data'],direct_playback_handoff=handoff)
        player.url=player.data['url'];player.playback_session_id=fixture['rid']
        issued=[]
        player.play=lambda *args:issued.append('play')
        if stage=='subtitles':player.handle_subtitles=lambda item:cancel.set()
        else:
            original=player._cinema_phase
            def phase(value):
                if value in ('PLAY_ISSUED','RESOLUTION_ISSUED'):cancel.set()
                original(value)
            player._cinema_phase=phase
        player.play_video(fixture['ListItem']())
        assert cancel.is_set() and not issued and not fixture['dispatches']
        assert not player._resolution_answered
print('4 late-cancel interleavings passed; no media dispatch')
