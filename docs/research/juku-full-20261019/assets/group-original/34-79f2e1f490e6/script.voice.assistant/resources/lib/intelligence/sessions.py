"""Native Codex thread lifetime; one flow includes all follow-up turns."""
from ..data_paths import data_path
import hashlib
import json
from pathlib import Path
import time
import uuid

from ..storage import read_json, write_json

# Native dynamic tools are registered when a thread is created, not on resume.
TOOLSET_REVISION = 7


class Sessions:
    def __init__(self, profile, policy='conversation', signature='', today=None):
        if policy not in ('conversation', 'daily', 'forever'):
            raise ValueError('会话有效期无效。')
        self.path = data_path(Path(profile), 'conversation.json')
        self.codebuddy = None  # Live connection only; never serialized with history.
        self.policy, self.signature = policy, signature
        self.today = today or time.strftime('%Y-%m-%d')
        self.value = read_json(self.path, {}) or {}
        if not isinstance(self.value, dict): self.value = {}
        valid = (self.value.get('policy') == policy and self.value.get('signature') == signature
                 and (policy != 'daily' or self.value.get('date') == self.today))
        if policy == 'conversation' or not valid:
            self._new()
        elif not self.value.get('history_id'):
            # Old display history mixes native threads; never attach it to a
            # retained daily/forever thread merely because it shares a date.
            self.value['history_id'] = uuid.uuid4().hex
            self.save()

    def _new(self):
        self.close()
        self.value = {'policy': self.policy, 'signature': self.signature, 'date': self.today,
                      'history_id': uuid.uuid4().hex, 'thread_id': None, 'media': [], 'turns': 0}
        self.save()

    @property
    def history_id(self):
        return self.value['history_id']

    def refresh(self, policy=None, signature=None, today=None):
        """Rotate only between turns, never interrupt a task at midnight."""
        policy = policy or self.policy
        if policy not in ('conversation', 'daily', 'forever'):
            raise ValueError('会话有效期无效。')
        signature = self.signature if signature is None else signature
        today = today or time.strftime('%Y-%m-%d')
        saved = read_json(self.path, {})
        changed = (policy != self.policy or signature != self.signature
                   or (policy == 'daily' and today != self.today)
                   or not isinstance(saved, dict) or saved.get('history_id') != self.history_id)
        self.policy, self.signature, self.today = policy, signature, today
        if changed: self._new()
        return changed

    @property
    def thread_id(self):
        return self.value.get('thread_id')

    @property
    def media(self):
        return self.value.get('media', [])

    def started(self, thread_id):
        self.value['thread_id'] = thread_id
        self.save()

    def completed(self, media):
        self.value['turns'] = int(self.value.get('turns', 0)) + 1
        self.value['media'] = list(media)[-100:]
        self.save()

    @property
    def last_local_action(self):
        return self.value.get('last_local_action')

    def record_local(self, request, result):
        # Supply the next native turn with actions that ran without the model.
        # This is a past result, never a substitute for querying current playback.
        self.value['last_local_action'] = {'request': request[:1000], 'result': result[:2000]}
        self.save()

    def save(self):
        self.value['updated_at'] = time.time()
        write_json(self.path, self.value)

    def clear(self):
        self._new()

    def close(self):
        cached, self.codebuddy = self.codebuddy, None
        if cached:
            cached[1].close()


def signature(values):
    keys = ('agent_backend', 'codex_provider', 'codex_chatgpt_model', 'codex_chatgpt_effort', 'agent_model',
            'agent_effort', 'agent_base_url', 'permission_level', 'approval_strategy',
            'codebuddy_region', 'codebuddy_model', 'codebuddy_internal_model', 'codebuddy_approval_strategy')
    context = {k: values.get(k) for k in keys}
    context['toolset_revision'] = TOOLSET_REVISION
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
