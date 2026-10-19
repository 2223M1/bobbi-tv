"""Checkpointable, bounded reader for a completed Juku JSON snapshot.

This resumes local validation, NOT HTTP downloads. A socket failure discards
its partial file; no Range/ETag support is assumed. The envelope may place
library/movies/success in any order. No rows are visible until its final EOF.
"""
import json

MAX_VALUE = 4 * 1024 * 1024


class SnapshotReader:
    def __init__(self, stream, checkpoint, guard):
        self.stream, self.guard = stream, guard
        self.state = dict(checkpoint or dict(offset=0, phase='start', top=[], data=[], count=0))
        self.state['top'] = list(self.state['top'])
        self.state['data'] = list(self.state['data'])
        self.stream.seek(self.state['offset'])
        self.buffer = b''
        self.eof = False
        self.decoder = json.JSONDecoder(parse_constant=self._constant,
                                        object_pairs_hook=self._object)

    @staticmethod
    def _constant(value):
        raise ValueError('Nonfinite snapshot number')

    @staticmethod
    def _object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate snapshot object key')
            result[key] = value
        return result

    def _fill(self):
        self.guard()
        block = self.stream.read(65536)
        self.eof = not block
        self.buffer += block
        if len(self.buffer) > MAX_VALUE + 65536:
            raise ValueError('Snapshot record budget')

    def _consume(self, count):
        self.state['offset'] += count
        self.buffer = self.buffer[count:]

    def peek(self):
        while True:
            self.guard()
            count = len(self.buffer) - len(self.buffer.lstrip(b' \r\n\t'))
            self._consume(count)
            if self.buffer:
                return chr(self.buffer[0])
            if self.eof:
                return ''
            self._fill()

    def token(self, expected):
        if self.peek() != expected:
            raise ValueError('Malformed snapshot punctuation')
        self._consume(1)

    def value(self):
        self.peek()
        while True:
            self.guard()
            # A chunk may end inside a multibyte codepoint. Ignore only that
            # incomplete suffix; other malformed UTF-8 is always rejected.
            try:
                text = self.buffer.decode('utf-8')
            except UnicodeDecodeError as error:
                if error.reason != 'unexpected end of data' or self.eof:
                    raise ValueError('Invalid snapshot UTF-8') from None
                text = self.buffer[:error.start].decode('utf-8')
            try:
                result, end = self.decoder.raw_decode(text)
            except json.JSONDecodeError:
                if self.eof or len(self.buffer) >= MAX_VALUE:
                    raise ValueError('Invalid or oversized snapshot record') from None
                self._fill()
                continue
            used = len(text[:end].encode('utf-8'))
            # A numeric/scalar token at a read boundary could still continue.
            if used == len(self.buffer) and not self.eof:
                self._fill()
                continue
            if used > MAX_VALUE:
                raise ValueError('Snapshot record budget')
            self._consume(used)
            return result

    def next_movie(self):
        while self.state['phase'] != 'done':
            self.guard()
            phase = self.state['phase']
            if phase == 'start':
                self.token('{')
                self.state['phase'] = 'top_key'
            elif phase in ('top_key', 'data_key'):
                scope = 'top' if phase == 'top_key' else 'data'
                if self.peek() == '}':
                    self.token('}')
                    self.state['phase'] = 'end' if scope == 'top' else 'top_delim'
                    continue
                key = self.value()
                if not isinstance(key, str) or key in self.state[scope]:
                    raise ValueError('Invalid/duplicate snapshot field')
                self.state[scope].append(key)
                if len(self.state[scope]) > 32:
                    raise ValueError('Snapshot envelope field budget')
                self.token(':')
                if scope == 'top' and key == 'data':
                    self.token('{')
                    self.state['phase'] = 'data_key'
                elif scope == 'data' and key == 'movies':
                    self.token('[')
                    self.state['phase'] = 'movie_first'
                else:
                    value = self.value()
                    if scope == 'top' and key == 'success':
                        self.state['success'] = value is True
                    elif scope == 'data' and key == 'library':
                        if not isinstance(value, dict):
                            raise ValueError('Snapshot library shape')
                        self.state['library'] = {name: value[name] for name in
                            ('shareCode', 'version', 'itemCount', 'isPublic') if name in value}
                    self.state['phase'] = scope + '_delim'
            elif phase in ('top_delim', 'data_delim'):
                scope = phase.split('_')[0]
                symbol = self.peek()
                if symbol == ',':
                    self.token(',')
                    if self.peek() == '}':
                        raise ValueError('Trailing snapshot comma')
                    self.state['phase'] = scope + '_key'
                elif symbol == '}':
                    self.token('}')
                    self.state['phase'] = 'end' if scope == 'top' else 'top_delim'
                else:
                    raise ValueError('Invalid snapshot object delimiter')
            elif phase in ('movie_first', 'movie_next'):
                if phase == 'movie_first' and self.peek() == ']':
                    self.token(']')
                    self.state['phase'] = 'data_delim'
                    continue
                movie = self.value()
                if not isinstance(movie, dict):
                    raise ValueError('Snapshot movie must be an object')
                self.state['count'] += 1
                self.state['phase'] = 'movie_delim'
                return movie
            elif phase == 'movie_delim':
                if self.peek() == ',':
                    self.token(',')
                    self.state['phase'] = 'movie_next'
                else:
                    self.token(']')
                    self.state['phase'] = 'data_delim'
            elif phase == 'end':
                if (self.peek() or self.state.get('success') is not True
                        or 'movies' not in self.state['data'] or 'library' not in self.state):
                    raise ValueError('Incomplete/unsuccessful snapshot envelope')
                self.state['phase'] = 'done'
            else:
                raise ValueError('Invalid snapshot checkpoint')
        return None
