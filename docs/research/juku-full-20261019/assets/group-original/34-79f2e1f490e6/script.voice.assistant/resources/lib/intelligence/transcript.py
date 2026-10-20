"""The last fifty displayed question/answer rounds belonging to the current session."""
from ..data_paths import data_path
from pathlib import Path
import time

from ..storage import read_json, write_json


class Transcript:
    LIMIT = 50

    def __init__(self, profile, session_id):
        if not isinstance(session_id, str) or not session_id:
            raise ValueError('聊天记录缺少会话标识。')
        self.path = data_path(Path(profile), 'chat-history.json')
        self.session_id = session_id
        value = read_json(self.path, {})
        rows = value.get('rounds', []) if isinstance(value, dict) and value.get('session_id') == session_id else []
        self.rounds = [row for row in rows if isinstance(row, dict)
                       and isinstance(row.get('user'), str)
                       and (row.get('answer') is None or isinstance(row['answer'], dict))][-self.LIMIT:] if isinstance(rows, list) else []
        self.current = None

    def begin(self, text):
        self.current = {'user': text, 'answer': None, 'activity': [], 'events': [],
                        'state': 'working', 'created_at': time.time()}
        self.rounds.append(self.current)
        self.rounds = self.rounds[-self.LIMIT:]
        self.save()

    def activity(self, message):
        if self.current is not None:
            self.current['activity'].append(message)
            self.current['events'].append({'role': 'activity', 'text': message})

    def message(self, role, text):
        if self.current is not None:
            self.current['events'].append({'role': role, 'text': text})
            self.save()

    def finish(self, presentation):
        self.current.update(answer=presentation, state='done')
        self.save()
        self.current = None

    def interrupt(self):
        if self.current is not None:
            self.current['state'] = 'interrupted'
            self.save()
            self.current = None

    def save(self):
        write_json(self.path, {'session_id': self.session_id, 'rounds': self.rounds})
