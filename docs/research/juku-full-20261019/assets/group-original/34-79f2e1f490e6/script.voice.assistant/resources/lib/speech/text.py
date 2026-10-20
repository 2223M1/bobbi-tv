"""Spoken text and validated, per-occurrence AI pronunciation annotations."""
import json
import re


def clean(text):
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    return re.sub(r'[*#`_]+', '', text).strip()


def commentary_allowed(text):
    # Only public natural-language status messages reach this filter; tool events
    # are never submitted. Drop mixed technical paragraphs as well.
    return not re.search(r'```|(?:^|\s)(?:/|~[/\\])\S+|\b\w+\.(?:py|sh|xml|json|js|ts|cpp|c|log)\b|'
                         r'执行命令|调用脚本|运行脚本|编辑文件|修改文件|删除文件|创建文件|读取文件|写入文件|'
                         r'\b(?:sudo|systemctl|bash|powershell|RunScript|JSON-RPC)\b', text, re.I)


def chunks(text, maximum=40):
    text = clean(text)
    while text:
        match = re.search(r'[。！？!?；;，,\n]', text[:maximum])
        end = match.end() if match else min(maximum, len(text))
        if not match:
            # Keep English words intact when the short synthesis chunk ends.
            for word in re.finditer(r"[A-Za-z][A-Za-z0-9'-]*", text):
                if word.start() < end < word.end():
                    end = word.start() or word.end()
                    break
        part, text = text[:end].strip(), text[end:].lstrip()
        if re.search(r'[\w\u4e00-\u9fff\uE000-\uF8FF]', part):
            yield part


def phoneme_map(tokens):
    # Transport alphabet, not a word/pronunciation correction dictionary.
    phones = [line.rsplit(maxsplit=1)[0] for line in tokens.splitlines() if line.strip()]
    return {phone: chr(0xE000 + i) for i, phone in enumerate(phones) if re.fullmatch(r'[a-z]+[1-5]?', phone)}


def encode(row, mapping, enabled):
    text = row.get('text', '')
    if not isinstance(text, str) or len(text) > 2000:
        raise ValueError('朗读片段过长。')
    # Never accept caller-supplied private phoneme codes.
    text = re.sub(r'[\uE000-\uF8FF]', '', text)
    if not enabled:
        return text
    spans = []
    entries = row.get('pronunciations', [])
    if not isinstance(entries, list): return text
    for entry in entries[:50]:
        try:
            word, phones, start = entry['text'], entry['pinyin'], entry['start']
            if type(start) is not int or not isinstance(word, str) or not word or not isinstance(phones, list):
                continue
            if start < 0 or text[start:start + len(word)] != word or len(phones) != len(word):
                continue
            if not all(isinstance(p, str) for p in phones):
                continue
            # The bilingual model names the neutral tone with a trailing 5.
            phones = [p if p in mapping else p + '5' for p in phones]
            if not all(p in mapping for p in phones):
                continue
            spans.append((start, start + len(word), ''.join(mapping[p] for p in phones)))
        except (KeyError, TypeError):
            continue
    end = 0
    result = []
    for start, stop, replacement in sorted(spans):
        if start < end:
            continue
        result.extend((text[end:start], replacement)); end = stop
    result.append(text[end:])
    return ''.join(result)


def schema(base):
    result = json.loads(json.dumps(base))
    annotation = {'type':'object', 'additionalProperties':False,
        'properties':{'start':{'type':'integer'},'text':{'type':'string'},
                      'pinyin':{'type':'array','items':{'type':'string'}}},
        'required':['start','text','pinyin']}
    speech = {'type':'array','items':{'type':'object','additionalProperties':False,
        'properties':{'text':{'type':'string'}, 'pronunciations':{'type':'array','items':annotation}},
        'required':['text','pronunciations']}}
    result['properties'] = dict(speech=speech, **result['properties'])
    result['required'].insert(0, 'speech')
    return result


def instruction(ai, scope):
    return ('\n语音朗读已开启。最终回复请先输出 speech 数组，然后输出 message 等字段。'
            'speech 是与最终答复内容一致的自然口语，每段约10到25字、最多40字，按标点分段，'
            '不要念 Markdown 标记、URL 或代码。每段含 text 和 pronunciations。'
            + ('根据上下文只用你自己的判断纠正多音字和轻声，pronunciations 列出需要指定读音的词：'
               'start 是该词在此段 text 中从0开始的字符位置，text 是该词原文，pinyin 每字一个小写带数字声调的拼音，'
               '轻声无数字，ü用v。每个出现位置单独标注；不改显示文字。无须修正则空数组。' if ai else
               'pronunciations 必须是空数组。')
            + ('需要向用户说明工作进展时，commentary 也用 {"message":"自然说明", "speech":[同上格式]}，'
               'message 只写自然语言工作说明，不要朗读命令、脚本调用、文件路径、文件编辑或工具调用细节。' if scope == 'all' else ''))


class SpeechStream:
    """Decode only complete speech-array elements from structured output deltas."""
    def __init__(self, emit):
        self.emit = emit
        self.buffer = ''
        self.position = None
        self.count = 0
        self.closed = False

    def feed(self, delta):
        if self.closed or not isinstance(delta, str):
            return
        self.buffer += delta
        if len(self.buffer) > 200000:
            self.closed = True; return
        if self.position is None:
            # Require speech to be the first property, not a string within message.
            match = re.match(r'\s*\{\s*"speech"\s*:\s*\[', self.buffer)
            if not match:
                return
            self.position = match.end()
        while True:
            start = self.position
            while start < len(self.buffer) and self.buffer[start] in ' \r\n\t,':
                start += 1
            if start == len(self.buffer):
                return
            if self.buffer[start] == ']':
                self.closed = True; return
            try:
                row, end = json.JSONDecoder().raw_decode(self.buffer, start)
            except ValueError:
                return
            self.position = end
            if isinstance(row, dict) and isinstance(row.get('text'), str):
                self.emit(row); self.count += 1

    def finish(self, value):
        try:
            rows = json.loads(value).get('speech', [])
            if not isinstance(rows, list):
                return
            for row in rows[self.count:]:
                if isinstance(row, dict) and isinstance(row.get('text'), str):
                    self.emit(row); self.count += 1
        except (ValueError, AttributeError):
            pass
