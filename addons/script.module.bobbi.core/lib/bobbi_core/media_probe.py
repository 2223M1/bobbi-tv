"""Seekable, byte/time-limited header probe for an exact cloud file.

ffprobe only sees an ephemeral loopback URL. A serial HTTP bridge enforces the
combined range-read budget, including MP4 tail seeks. No full file is cached;
the digest identifies probe reads, not the full video. No Kodi or audio output.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import re
import secrets
import socket
import subprocess
import threading
import time

BYTE_BUDGET = 16 * 1024 * 1024
TIME_BUDGET = 20.0
OUTPUT_BUDGET = 1024 * 1024
SOCKET_BUFFER = 32768
ANALYSIS_BYTES = 2 * 1024 * 1024
ANALYSIS_MICROSECONDS = 1000000
_LANE = threading.BoundedSemaphore(1)


class ProbeError(RuntimeError):
    pass


class ProbeHTTPServer(HTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        # Metadata demuxers seek from the header to the tail and back. Do not
        # queue megabytes of a discarded range in loopback socket buffers.
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_BUFFER)
        return connection, address


def write_probe_chunk(stream, chunk):
    """False means the consumer abandoned its range, not provider read failure."""
    try:
        stream.write(chunk)
        return True
    except (BrokenPipeError, ConnectionResetError, TimeoutError):
        # This is deliberately scoped to the downstream write only. Upstream
        # read timeouts and byte/time budget errors must still reject the probe.
        return False


def requested_range(header, size):
    if header is None:
        return 0, size - 1
    match = re.fullmatch(r'bytes=(\d+)-(\d*)', header)
    if not match:
        raise ProbeError('INVALID_RANGE')
    start, end = int(match[1]), int(match[2]) if match[2] else size - 1
    if not 0 <= start <= end or start >= size:
        raise ProbeError('RANGE_OUTSIDE_FILE')
    return start, min(end, size - 1)


class RangeBudget:
    def __init__(self, size, read, cancelled, clock=time.monotonic):
        if type(size) is not int or size <= 0:
            raise ValueError('Exact positive file size required')
        self.size, self.read, self.cancelled, self.clock = size, read, cancelled, clock
        self.started, self.count, self.requests = clock(), 0, 0
        self.digest = hashlib.sha256()
        self.failure = None

    def guard(self):
        if self.cancelled():
            raise ProbeError('CANCELLED')
        if self.clock() - self.started >= TIME_BUDGET:
            raise ProbeError('TIME_BUDGET')

    def chunks(self, start, end):
        self.guard()
        self.requests += 1
        if self.requests > 32:
            raise ProbeError('REQUEST_BUDGET')
        remaining = min(end - start + 1, BYTE_BUDGET - self.count)
        if remaining <= 0:
            raise ProbeError('BYTE_BUDGET')
        offset = start
        # read is an exact HTTP range reader, never a mounted file read that
        # could block the Kodi process in FUSE while the provider is offline.
        for chunk in self.read(start, start + remaining - 1):
            self.guard()
            if not isinstance(chunk, bytes) or not 0 < len(chunk) <= min(65536, remaining):
                raise ProbeError('INVALID_OR_OVERSIZED_CHUNK')
            self.digest.update(offset.to_bytes(8, 'big'))
            self.digest.update(len(chunk).to_bytes(4, 'big'))
            self.digest.update(chunk)
            self.count += len(chunk)
            offset += len(chunk)
            remaining -= len(chunk)
            yield chunk
            if not remaining:
                break
        if remaining:
            raise ProbeError('TRUNCATED_RANGE')


def http_range_reader(session, url, size):
    """URL remains in memory. Caller pins it to its configured CD2 endpoint."""
    def read(start, end):
        with session.get(url, headers={'Range': 'bytes={}-{}'.format(start, end),
                                      'Accept-Encoding': 'identity'},
                         timeout=(3.05, 4), stream=True, allow_redirects=False) as response:
            expected = 'bytes {}-{}/{}'.format(start, end, size)
            if (response.status_code != 206 or response.headers.get('Content-Range') != expected
                    or response.headers.get('Content-Encoding', 'identity') != 'identity'):
                raise ProbeError('EXACT_RANGE_UNAVAILABLE')
            for chunk in response.iter_content(65536):
                if chunk:
                    yield chunk
    return read


def probe(binary, size, read, cancelled=lambda: False):
    if not _LANE.acquire(blocking=False):
        raise ProbeError('PROBE_ALREADY_RUNNING')
    transferred = []
    try:
        return _probe(binary, size, read, cancelled, transferred)
    finally:
        # _probe holds the lease until its IO thread has actually exited.
        # A stalled provider cannot cause accumulating daemon probe threads.
        if not transferred:
            _LANE.release()


def probe_command(binary, port, token):
    # Container headers/attachments and tail seeks consume the same fixed
    # network budget as stream analysis. Spending 8 MiB analysing packets can
    # exhaust that budget after a perfectly valid large Matroska header. This
    # is metadata qualification, not decoding five seconds of every track.
    # Insufficient codec/duration metadata still fails the checks below.
    return [str(binary), '-v', 'error', '-threads', '1', '-protocol_whitelist', 'http,tcp',
            '-recv_buffer_size', str(SOCKET_BUFFER),
            '-probesize', str(ANALYSIS_BYTES), '-analyzeduration', str(ANALYSIS_MICROSECONDS),
            '-show_entries', 'format=format_name,duration:stream=index,codec_type,codec_name,width,height,pix_fmt,color_transfer,color_primaries,avg_frame_rate,sample_rate,channels,channel_layout,bits_per_raw_sample:stream_tags=language,title,filename,mimetype:stream_disposition=attached_pic,default,comment:stream_side_data',
            '-of', 'json', 'http://127.0.0.1:{}{}'.format(port, token)]


def detail_probe(binary, size, read, cancelled, command_factory, result_parser):
    """Reuse the same single lane and unchanged byte/time/output limits.

    Factories are trusted local functions, never IPC-supplied argv or code.
    Subtitle reference sampling must not start a second media IO lane.
    """
    if not callable(command_factory) or not callable(result_parser):
        raise ValueError('Local probe command and result adapter required')
    if not _LANE.acquire(blocking=False):
        raise ProbeError('PROBE_ALREADY_RUNNING')
    transferred = []
    try:
        return _probe(binary, size, read, cancelled, transferred, command_factory, result_parser)
    finally:
        if not transferred:
            _LANE.release()


def _probe(binary, size, read, cancelled, transferred, command_factory=None, result_parser=None):
    budget = RangeBudget(size, read, cancelled)
    token = '/' + secrets.token_hex(24)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_HEAD(self):
            if self.path != token:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Length', str(size))
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()

        def do_GET(self):
            if self.path != token:
                self.send_error(404)
                return
            try:
                start, end = requested_range(self.headers.get('Range'), size)
                self.send_response(206 if self.headers.get('Range') else 200)
                self.send_header('Content-Length', str(end - start + 1))
                self.send_header('Accept-Ranges', 'bytes')
                if self.headers.get('Range'):
                    self.send_header('Content-Range', 'bytes {}-{}/{}'.format(start, end, size))
                self.end_headers()
                self.connection.settimeout(2)
                for chunk in budget.chunks(start, end):
                    if not write_probe_chunk(self.wfile, chunk):
                        break
            except (BrokenPipeError, ConnectionResetError):
                # ffprobe can stop a range intentionally after finding headers.
                pass
            except Exception as error:
                budget.failure = str(error) if isinstance(error, ProbeError) else type(error).__name__
            finally:
                self.close_connection = True

    server = ProbeHTTPServer(('127.0.0.1', 0), Handler)
    server.timeout = 0.1
    closing = threading.Event()

    def serve():
        try:
            while not closing.is_set():
                server.handle_request()
        finally:
            server.server_close()
            _LANE.release()

    thread = threading.Thread(target=serve, name='cinema-probe-range', daemon=True)
    try:
        thread.start()
    except BaseException:
        server.server_close()
        raise
    transferred.append(True)
    command = (command_factory or probe_command)(binary, server.server_port, token)
    process, readers, output, oversized = None, [], [bytearray(), bytearray()], threading.Event()

    def drain(stream, destination):
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    return
                if len(destination) + len(chunk) > OUTPUT_BUDGET:
                    oversized.set()
                    return
                destination.extend(chunk)
        finally:
            stream.close()

    try:
        budget.guard()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        for stream, destination in zip((process.stdout, process.stderr), output):
            reader = threading.Thread(target=drain, args=(stream, destination), daemon=True)
            readers.append(reader)
            reader.start()
        while process.poll() is None:
            budget.guard()
            if oversized.is_set():
                raise ProbeError('OUTPUT_BUDGET')
            time.sleep(0.05)
        for reader in readers:
            reader.join(1)
        if oversized.is_set() or any(reader.is_alive() for reader in readers):
            raise ProbeError('OUTPUT_BUDGET')
        if process.returncode != 0 or budget.failure or not budget.count:
            raise ProbeError(budget.failure or 'FFPROBE_FAILED')
        data = json.loads(output[0])
        if result_parser is not None:
            result = result_parser(data)
            return dict(result, read_bytes=budget.count, probe_sha256=budget.digest.hexdigest(),
                        requests=budget.requests, seconds=round(time.monotonic() - budget.started, 3))
        streams = data.get('streams')
        if not isinstance(streams, list) or len(streams) > 128:
            raise ProbeError('STREAM_BUDGET')
        duration = float(data.get('format', {}).get('duration', 0))
        video = [stream for stream in streams if stream.get('codec_type') == 'video'
                 and not stream.get('disposition', {}).get('attached_pic')
                 and stream.get('width', 0) > 0 and stream.get('height', 0) > 0]
        if not video or not math.isfinite(duration) or duration <= 0:
            raise ProbeError('NO_TIMED_VIDEO')
        return dict(duration=duration, streams=streams, read_bytes=budget.count,
                    probe_sha256=budget.digest.hexdigest(), requests=budget.requests,
                    seconds=round(time.monotonic() - budget.started, 3),
                    state='HEADER_PROBED_NOT_IDENTITY_OR_PLAYBACK_PROOF')
    except ProbeError as error:
        error.metrics = dict(read_bytes=budget.count, requests=budget.requests,
                             seconds=round(time.monotonic() - budget.started, 3),
                             probe_sha256=budget.digest.hexdigest())
        raise
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        closing.set()
        thread.join(5)
        for reader in readers:
            reader.join(1)
