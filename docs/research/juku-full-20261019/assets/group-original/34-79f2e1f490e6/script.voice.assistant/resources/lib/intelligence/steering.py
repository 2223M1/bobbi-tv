"""Thread-safe delivery state for user input arriving during a Codex turn."""
import threading


class Steering:
    def __init__(self):
        self.lock = threading.Lock()
        self.entries = []

    def submit(self, text):
        text = text.strip()
        if not text or len(text) > 4000:
            raise ValueError('补充内容为空或过长（最多 4000 字符）。')
        with self.lock:
            identifier = 'voice-steer-' + str(len(self.entries) + 1)
            self.entries.append({'id': identifier, 'text': text, 'state': 'queued'})
        return identifier

    def take(self):
        with self.lock:
            for entry in self.entries:
                if entry['state'] == 'queued':
                    entry['state'] = 'sending'
                    return dict(entry)

    def resolve(self, identifier, accepted):
        with self.lock:
            entry = next(entry for entry in self.entries if entry['id'] == identifier)
            entry['state'] = 'accepted' if accepted else 'next_turn'

    def followup(self):
        with self.lock:
            for entry in self.entries:
                if entry['state'] in ('queued', 'next_turn'):
                    entry['state'] = 'accepted'
                    return entry['text']
