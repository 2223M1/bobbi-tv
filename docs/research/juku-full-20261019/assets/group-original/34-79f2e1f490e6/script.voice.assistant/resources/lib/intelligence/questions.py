"""A native Codex question batch, answered by the UI and delivered by its worker."""
import threading


class UserQuestions:
    def __init__(self, params):
        questions = params.get('questions')
        if not isinstance(questions, list) or not questions or len(questions) > 20:
            raise ValueError('Codex 提问格式无效。')
        seen = set()
        for question in questions:
            if not isinstance(question, dict) or not isinstance(question.get('id'), str) or not question['id'] or question['id'] in seen:
                raise ValueError('Codex 问题编号无效。')
            seen.add(question['id'])
            if not isinstance(question.get('question'), str) or not question['question'].strip():
                raise ValueError('Codex 问题内容为空。')
            options = question.get('options') or []
            if not isinstance(options, list) or any(not isinstance(o, dict) or not isinstance(o.get('label'), str) or not o['label'] for o in options):
                raise ValueError('Codex 问题选项无效。')
        self.questions = questions
        self.blocking = params.get('isBlocking', True)
        self.answers = {}
        self.ready = threading.Event()
        self.expired = threading.Event()

    def answer(self, identifier, text):
        if self.expired.is_set() or self.ready.is_set():
            return False
        if identifier not in {q['id'] for q in self.questions} or not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError('请填写有效回答（最多 4000 字符）。')
        self.answers[identifier] = {'answers': [text.strip()]}
        if len(self.answers) == len(self.questions):
            self.ready.set()
        return True
