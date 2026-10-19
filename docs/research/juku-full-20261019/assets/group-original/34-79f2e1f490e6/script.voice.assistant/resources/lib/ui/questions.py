"""Render a question batch in the existing conversation without a second modal."""
import queue
import uuid


class QuestionFlow:
    def __init__(self, requests, window, on_message):
        self.requests, self.window, self.on_message = requests, window, on_message
        self.request = None
        self.index = 0
        self.token = ''

    def tick(self):
        if self.request and self.request.expired.is_set():
            self.window.activity('该提问已结束。')
            self.clear()
        if self.request is None:
            while True:
                try:
                    request = self.requests.get_nowait()
                except queue.Empty:
                    return
                if not request.expired.is_set():
                    self.request, self.index = request, 0
                    self.show()
                    return

    def show(self):
        question = self.request.questions[self.index]
        parts = [question['question']]
        for option in question.get('options') or []:
            parts.append(option['label'] + ('：' + option['description'] if option.get('description') else ''))
        self.on_message('assistant', '\n'.join(parts))
        self.token = uuid.uuid4().hex
        self.window.show_question(self.token, question)

    def answer(self, value, target):
        if isinstance(value, dict):
            target, value = value.get('question'), value.get('text')
        if not self.request or target != self.token:
            return False
        question = self.request.questions[self.index]
        if not self.request.answer(question['id'], value):
            self.window.activity('任务已结束，这条回答未提交。')
            self.clear()
            return True
        self.on_message('user', '（已提交隐藏回答）' if question.get('isSecret') else value.strip())
        self.index += 1
        if self.index < len(self.request.questions):
            self.show()
        else:
            self.window.activity('回答已提交，继续处理任务。')
            self.clear()
        return True

    def clear(self):
        self.window.clear_question()
        self.request = None
        self.token = ''
