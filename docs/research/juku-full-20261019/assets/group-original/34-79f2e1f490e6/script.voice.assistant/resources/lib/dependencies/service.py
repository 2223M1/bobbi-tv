"""One download owner, used by both the web page and Kodi configuration UI."""
from ..data_paths import data_path
import copy
import fcntl
import json
from pathlib import Path
import socket
import socketserver
import threading
import time
from .catalog import display_label, catalog, missing, requirements, specification, installed
from .download import install
from .uploads import cached, cache_path, file_info, locate, receive


class Manager:
    def __init__(self, root, profile):
        self.root, self.profile = Path(root), Path(profile)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.receiving = False
        self.upload_finished = threading.Event()
        self.upload_finished.set()
        self.job = {'state': 'idle'}
        self.web_saved = False
        self.runtime = {}
        self.profile.mkdir(parents=True, exist_ok=True)
        self.lease = (data_path(self.profile, 'components.lock')).open('a')
        fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manager = self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(2)
                try:
                    line = self.rfile.readline(32769)
                    if len(line) > 32768: return
                    value = json.loads(line)
                    if value.get('op') == 'start': manager.start(manager.values)
                    elif value.get('op') == 'cancel': manager.cancel()
                    elif value.get('op') != 'state': raise ValueError('未知下载操作。')
                    result = manager.state(manager.values)
                except Exception as error:
                    result = {'error': str(error)}
                self.wfile.write((json.dumps(result, ensure_ascii=False) + '\n').encode())
        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True
        self.values = {}
        self.path = data_path(self.profile, 'components.sock')
        self.path.unlink(missing_ok=True)
        self.server = Server(str(self.path), Handler)
        self.path.chmod(0o600)
        self.server_thread = threading.Thread(target=self.server.serve_forever,
            kwargs={'poll_interval': .1}, daemon=True)
        self.server_thread.start()

    def state(self, values):
        required = requirements(self.root, values)
        rows = []
        for name in required:
            spec = specification(self.root, name)
            rows.append({'id': name, 'label': display_label(name, spec), 'ready': installed(self.root, self.profile, name),
                         'bytes': sum(asset['bytes'] for asset in spec['assets']),
                         'files': [file_info(self.profile, asset) for asset in spec['assets']]})
        upload_files = []
        for name, spec in catalog(str(self.root))['components'].items():
            ready = installed(self.root, self.profile, name)
            upload_files.extend(dict(file_info(self.profile, asset), component=name, label=display_label(name, spec), ready=ready)
                                for asset in spec['assets'])
        with self.lock:
            return {'components': rows, 'missing': [row for row in rows if not row['ready']],
                    'job': copy.deepcopy(self.job), 'runtime': copy.deepcopy(self.runtime), 'upload_files': upload_files}

    def update(self, values):
        self.values = dict(values)

    def start(self, values):
        with self.lock:
            if self.receiving or self.thread and self.thread.is_alive():
                return  # Both UIs attach to the same active job.
            selected = missing(self.root, self.profile, values)
            if not selected:
                self.job = {'state': 'done'}
                return
            self.stop.clear()
            self.job = {'state': 'running', 'phase': 'downloading', 'pending': selected,
                        'completed': 0, 'total_components': len(selected), 'downloaded': 0,
                        'total': 0, 'speed': 0, 'percent': 0}
            self.thread = threading.Thread(target=self._work, args=(selected,), name='component-download', daemon=True)
            self.thread.start()

    def upload(self, filename, length, source):
        identifier, asset = locate(self.root, filename)
        if length != asset['bytes']:
            raise ValueError('依赖文件大小不符：' + filename)
        with self.lock:
            if self.receiving or self.thread and self.thread.is_alive():
                raise ValueError('组件正在处理，请完成后再上传。')
            self.receiving = True
            self.upload_finished.clear()
            self.stop.clear()
            self.job = {'state': 'running', 'phase': 'uploading', 'label': filename,
                        'component': identifier, 'downloaded': 0, 'total': length, 'speed': 0, 'percent': 0}
        try:
            def progress(done, total, speed):
                with self.lock:
                    self.job.update(downloaded=done, speed=round(speed), percent=round(100 * done / total, 1))
            receive(self.root, self.profile, filename, length, source, self.stop.is_set, progress)
            spec = specification(self.root, identifier)
            with self.lock:
                if self.stop.is_set():
                    raise InterruptedError('上传已取消。')
                pending = [row.get('filename', row['url'].rsplit('/', 1)[-1]) for row in spec['assets']
                           if not cached(self.profile, row)]
                if installed(self.root, self.profile, identifier):
                    cache_path(self.profile, asset).unlink(missing_ok=True)
                    pending = []
                    self.job.update(state='done', phase='ready', percent=100)
                elif pending:
                    self.job.update(state='waiting_files', pending_files=pending, speed=0)
                else:
                    self.job.update(phase='extracting', pending=[identifier], completed=0, total_components=1)
                    self.thread = threading.Thread(target=self._work, args=([identifier], True),
                                                   name='component-upload-install', daemon=True)
                    self.thread.start()
            return {'ok': True, 'filename': filename, 'component': identifier, 'pending_files': pending}
        except InterruptedError:
            with self.lock:
                self.job.update(state='cancelled', speed=0)
            raise
        except Exception as error:
            with self.lock:
                self.job.update(state='error', error=str(error), speed=0)
            raise
        finally:
            with self.lock:
                self.receiving = False
                self.upload_finished.set()

    def _work(self, selected, offline=False):
        try:
            for index, identifier in enumerate(selected):
                spec = specification(self.root, identifier)
                with self.lock:
                    self.job.update(component=identifier, label=display_label(identifier, spec), completed=index)
                def progress(done, total, speed, phase='downloading'):
                    with self.lock:
                        self.job.update(downloaded=done, total=total, speed=round(speed), phase=phase,
                            percent=round(100 * (index + (done / total if total else 0)) / len(selected), 1))
                if offline:
                    def no_network(*args, **kwargs):
                        raise ValueError('依赖文件未齐全，请继续上传。')
                    install(self.root, self.profile, identifier, self.stop.is_set, progress, opener=no_network)
                else:
                    install(self.root, self.profile, identifier, self.stop.is_set, progress)
            with self.lock:
                self.job.update(state='done', phase='ready', completed=len(selected), percent=100)
        except InterruptedError:
            with self.lock: self.job.update(state='cancelled', speed=0)
        except Exception as error:
            with self.lock: self.job.update(state='error', error=str(error), speed=0)

    def cancel(self):
        self.stop.set()

    def close(self):
        self.cancel()
        self.upload_finished.wait(12)
        if self.thread: self.thread.join(12)
        self.server.shutdown(); self.server.server_close()
        self.server_thread.join(2)
        self.path.unlink(missing_ok=True)
        self.lease.close()


def request(profile, operation='state'):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        connection.connect(str(data_path(Path(profile), 'components.sock')))
        connection.sendall((json.dumps({'op': operation}) + '\n').encode())
        with connection.makefile('rb') as source:
            data = source.readline(131073)
        if len(data) > 131072:
            raise ValueError('组件状态无效。')
        value = json.loads(data)
        if value.get('error'):
            raise ValueError(value['error'])
        return value
