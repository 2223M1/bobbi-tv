"""One resident recognizer, independent streams and one active PCM client."""
from ..data_paths import data_path
import json
from pathlib import Path
import select
import socket
import socketserver
import struct
import threading
import time
from .native import Native, command
from ..dependencies.catalog import preload_delay, installed, catalog


class Service:
    def __init__(self, root, profile, clock=time.monotonic, delay=None, rpc=None):
        self.root, self.profile = Path(root), Path(profile)
        self.rpc = rpc
        self.hotwords = {}
        self.history = []
        self.active_cancelled = None
        self.unload_reason = 'initial_load'
        self.last_load = {}
        self.clock = clock
        self.preload_at = clock() + (preload_delay() if delay is None else delay)
        self.closed = threading.Event()
        self.wake = threading.Event()
        self.lock = threading.Lock()
        self.native = None
        self.loaded_model = None
        self.loaded_decoding = None
        self.demand_model = None
        self.values = {}
        self.status = {'state': 'disabled'}
        self.clients = set()
        self.clients_lock = threading.Lock()
        self.retry_at = 0
        owner = self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                owner.handle(self)
        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True
        directory = data_path(self.profile, 'asr')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        self.path = directory / 'control.sock'
        self.path.unlink(missing_ok=True)
        self.server = Server(str(self.path), Handler)
        self.path.chmod(0o600)
        self.server_thread = threading.Thread(target=self.server.serve_forever,
            kwargs={'poll_interval': .1}, daemon=True)
        self.worker = threading.Thread(target=self.work, name='onnx-preload', daemon=True)
        self.server_thread.start(); self.worker.start()

    def selected(self):
        return self.values.get('onnx_model') if self.values.get('recognition_engine') == 'onnx' else None

    def decoding(self, model):
        if model and catalog(str(self.root))['asr_models'].get(model, {}).get('family') == 'zipformer':
            return {'max_active_paths': self.values.get('zipformer_max_active_paths', 4),
                    'hotwords_score': float(self.values.get('zipformer_hotwords_score', '2'))}
        return None

    def tick(self, values):
        selected = values.get('onnx_model') if values.get('recognition_engine') == 'onnx' else None
        changed = selected != self.selected()
        previous_decoding = self.decoding(self.selected())
        self.values = dict(values)
        changed = changed or previous_decoding != self.decoding(selected)
        if changed:
            self.retry_at = 0
            self.demand_model = None
            self.wake.set()

    def available(self, model):
        data = catalog(str(self.root))['asr_models'][model]
        return all(installed(self.root, self.profile, item) for item in ('onnx-runtime', data['component']))

    def event(self, kind, **details):
        from ..storage import write_json
        self.history = getattr(self, 'history', [])[-79:] + [dict(details, event=kind, at=time.time())]
        try:
            write_json(data_path(self.profile, 'asr/lifecycle.json'), self.history)
        except OSError:
            pass  # Diagnostics must never stop recognition (e.g. full storage).

    def ready(self, model):
        self.status = {'state': 'ready', 'model': model, 'pid': self.native.process.pid}
        if self.hotwords:
            self.status['hotwords'] = self.hotwords
        if getattr(self, 'last_load', None):
            self.status['last_load'] = self.last_load
        if self.loaded_decoding is not None:
            self.status['decoding'] = dict(self.loaded_decoding)

    def unload(self, reason='unload'):
        if self.native:
            self.event('unload', model=self.loaded_model, pid=self.native.process.pid,
                       returncode=self.native.process.poll(), reason=reason)
            self.native.close()
        self.native, self.loaded_model = None, None
        self.loaded_decoding = None
        self.hotwords = {}
        self.unload_reason = reason

    def load(self, model, cancelled):
        decoding = self.decoding(model)
        if self.native and (model != self.loaded_model or self.native.process.poll() is not None
                            or decoding != self.loaded_decoding):
            reason = ('model_changed' if model != self.loaded_model else
                      'process_exited' if self.native.process.poll() is not None else 'decoding_changed')
            self.unload(reason)
        if not self.native:
            began = time.monotonic()
            reason = getattr(self, 'unload_reason', 'initial_load')
            self.event('load_started', model=model, reason=reason)
            self.status = {'state': 'loading', 'model': model}
            arguments = command(self.root, self.profile, model)
            if self.rpc and arguments[-8] == 'zipformer':
                from .library_hotwords import prepare
                try:
                    path, report = prepare(self.profile, arguments[-4], self.rpc, cancelled, force=True)
                    arguments[-1] = path
                    self.hotwords = {key: value for key, value in report.items() if key != 'skipped'}
                except InterruptedError:
                    raise
                except Exception:
                    self.hotwords = {'warning': '影视库热词准备失败，本次使用普通识别。'}
            if cancelled():
                raise InterruptedError('识别已取消。')
            self.native = Native(arguments, cancelled, **({'decoding': decoding} if decoding is not None else {}))
            self.loaded_model = model
            self.loaded_decoding = decoding
            self.last_load = {'seconds': round(time.monotonic() - began, 3), 'reason': reason}
            self.event('load_ready', model=model, pid=self.native.process.pid, **self.last_load)
        self.native.cancelled = cancelled
        self.ready(model)

    def work(self):
        while not self.closed.is_set():
            self.wake.wait(.3); self.wake.clear()
            if not self.lock.acquire(blocking=False): continue
            try:
                model = self.selected()
                if self.native and self.loaded_model != model:
                    self.unload('model_changed')
                if not model:
                    self.status = {'state': 'disabled'}
                elif not self.available(model):
                    self.status = {'state': 'missing', 'model': model}
                elif self.clock() < self.preload_at and not self.native and self.demand_model != model:
                    self.status = {'state': 'waiting', 'model': model,
                        'seconds': max(0, round(self.preload_at - self.clock()))}
                elif self.clock() >= self.retry_at:
                    decoding = self.decoding(model)
                    self.load(model, lambda: self.closed.is_set() or self.selected() != model
                              or self.decoding(model) != decoding)
            except InterruptedError:
                self.unload('loading_cancelled')
                self.retry_at = 0
                self.status = {'state': 'waiting' if self.selected() else 'disabled'}
            except Exception as error:
                self.event('load_failed', model=self.selected(), error_type=type(error).__name__)
                self.unload('load_error')
                self.status = {'state': 'error', 'model': self.selected(), 'error': str(error)}
                self.retry_at = self.clock() + 10
            finally:
                self.lock.release()

    def handle(self, handler):
        connection = handler.request
        with self.clients_lock: self.clients.add(connection)
        acquired = False
        def reply(value):
            handler.wfile.write((json.dumps(value, ensure_ascii=False) + '\n').encode())
            handler.wfile.flush()
        def cancelled():
            if self.closed.is_set(): return True
            try:
                return bool(select.select([connection], [], [], 0)[0]) and connection.recv(1, socket.MSG_PEEK) == b''
            except (OSError, ValueError):
                return True
        def read(count):
            output = bytearray()
            while len(output) < count:
                data = handler.rfile.read(count - len(output))
                if not data: raise InterruptedError('录音客户端已退出。')
                output.extend(data)
            return bytes(output)
        try:
            connection.settimeout(2)
            line = handler.rfile.readline(2049)
            if len(line) > 2048: raise ValueError('识别请求无效。')
            request = json.loads(line)
            model = request.get('model')
            if model != self.selected() or not model:
                raise ValueError('语音识别设置已更改，请重新开始。')
            self.demand_model = model
            self.wake.set()
            deadline = time.monotonic() + 125
            # Only the permanent worker thread spawns the native child. Linux's
            # PDEATHSIG follows the creating thread, even within one process.
            # Spawning in this short-lived handler kills a healthy resident as
            # soon as the first utterance's handler returns.
            while True:
                if cancelled(): raise InterruptedError()
                if model != self.selected(): raise ValueError('语音识别设置已更改，请重新开始。')
                if (self.status.get('state') == 'busy' and
                        not (self.active_cancelled and self.active_cancelled())):
                    raise ValueError('语音识别正在使用中。')
                if time.monotonic() >= deadline: raise ValueError('本地模型加载超时。')
                if not self.lock.acquire(timeout=.05): continue
                if (self.native and self.loaded_model == model and self.native.process.poll() is None
                        and self.loaded_decoding == self.decoding(model)):
                    acquired = True
                    break
                error = self.status.get('error') if self.status.get('state') == 'error' else None
                self.lock.release()
                if error: raise ValueError(error)
                self.wake.set()
                time.sleep(.02)
            self.active_cancelled = cancelled
            # Finish each framed native operation even if the frontend leaves.
            # Interrupting its read loses protocol alignment and forces a reload.
            # Only shutdown/model changes may abort the native operation itself.
            self.native.cancelled = lambda: self.closed.is_set() or self.selected() != model
            self.native.exchange(reset=True)
            self.status.update(state='busy')
            reply({'ready': True, 'streaming': self.native.ready['streaming']})
            connection.settimeout(40)
            while True:
                if cancelled(): raise InterruptedError('录音客户端已退出。')
                length = struct.unpack('<I', read(4))[0]
                if length > 32000 or length % 2:
                    raise ValueError('识别音频格式无效。')
                result = self.native.exchange(read(length) if length else b'')
                if cancelled(): raise InterruptedError('录音客户端已退出。')
                reply(result)
                if not length: break
            if self.native: self.ready(model)
        except Exception as error:
            if acquired:
                recovered = False
                if (cancelled() and not self.closed.is_set() and model == self.selected()
                        and self.native and self.native.process.poll() is None):
                    try:
                        self.status.update(state='resetting')
                        result = self.native.exchange(reset=True)
                        if not result.get('reset'):
                            raise ValueError('本地识别流重置失败。')
                        self.event('client_cancelled', model=model, pid=self.native.process.pid,
                                   model_retained=True)
                        self.ready(model)
                        recovered = True
                    except Exception as reset_error:
                        self.event('reset_failed', model=model, error_type=type(reset_error).__name__)
                if not recovered:
                    self.event('client_failed', model=model, error_type=type(error).__name__)
                    self.unload('client_error')
                    self.status = {'state': 'error', 'error': str(error)}
            try: reply({'error': str(error) or '识别已取消。'})
            except OSError: pass
        finally:
            with self.clients_lock: self.clients.discard(connection)
            if acquired:
                self.active_cancelled = None
                if self.native: self.native.cancelled = self.closed.is_set
                self.lock.release()
            self.wake.set()

    def close(self):
        self.closed.set(); self.wake.set()
        with self.clients_lock:
            for connection in self.clients:
                try: connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
        if self.native and self.native.process.poll() is None:
            try: self.native.process.terminate()
            except ProcessLookupError: pass
        self.server.shutdown(); self.server.server_close()
        self.server_thread.join(2); self.worker.join(3)
        with self.lock:
            self.unload('shutdown')
        self.path.unlink(missing_ok=True)
