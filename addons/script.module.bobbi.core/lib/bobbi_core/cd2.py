"""Bounded CD2 gRPC-Web adapter using the official CloudDriveFileSrv schema.

Wire field numbers: https://www.clouddrive2.com/api/clouddrive.proto
Only a small documented subset is implemented; unknown fields are skipped.
No automatic retries, credential logging, or implicit cloud mutations.
"""
from __future__ import annotations
import struct
import time
import requests

LIMIT = 8 * 1024 * 1024
BASE = ""  # Explicit user configuration required.


class CD2Error(RuntimeError):
    def __init__(self, status):
        self.status = str(status)
        super().__init__("CD2 request failed (status " + self.status + ")")


def varint(value):
    if not 0 <= value < 2**64:
        raise ValueError("Unsigned 64-bit value required")
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def read_varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("Truncated protobuf varint")
        byte = data[offset]
        offset += 1
        if shift == 63 and byte > 1:
            raise ValueError("Protobuf varint overflow")
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise ValueError("Invalid protobuf varint")


def field(number, value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    if isinstance(value, bytes):
        return varint(number << 3 | 2) + varint(len(value)) + value
    return varint(number << 3) + varint(int(value))


def fields(data):
    result, offset = {}, 0
    if len(data) > LIMIT:
        raise ValueError("Oversized protobuf message")
    while offset < len(data):
        key, offset = read_varint(data, offset)
        number, kind = key >> 3, key & 7
        if not number:
            raise ValueError("Invalid protobuf field zero")
        if kind == 0:
            value, offset = read_varint(data, offset)
        else:
            if kind == 2:
                size, offset = read_varint(data, offset)
            elif kind in (1, 5):
                size = 8 if kind == 1 else 4
            else:
                raise ValueError("Unsupported protobuf wire type")
            if size > len(data) - offset:
                raise ValueError("Truncated protobuf field")
            value = data[offset:offset + size]
            offset += size
        result.setdefault(number, []).append(value)
    return result


def decode_response(body, headers):
    frames, offset = [], 0
    status = headers.get("grpc-status")
    if len(body) > LIMIT:
        raise ValueError("Oversized gRPC response")
    while offset < len(body):
        if len(body) - offset < 5:
            raise ValueError("Truncated gRPC frame")
        flag, size = struct.unpack_from(">BI", body, offset)
        offset += 5
        if size > len(body) - offset:
            raise ValueError("Truncated gRPC payload")
        payload, offset = body[offset:offset + size], offset + size
        if flag == 128:
            for line in payload.decode("ascii").splitlines():
                key, separator, value = line.partition(":")
                if separator and key.lower() == "grpc-status":
                    status = value.strip()
        elif flag == 0:
            frames.append(payload)
        else:
            raise ValueError("Compressed/unknown gRPC frame refused")
    if status != "0":
        raise CD2Error(status or "missing-grpc-status")
    return frames


class CD2:
    def __init__(self, token=None, base=BASE):
        if not base:
            raise CD2Error("not_configured")
        self.token = token
        self.base = base.rstrip("/") + "/"
        self.session = requests.Session()
        self.session.trust_env = False  # LAN credentials must not use a global proxy.

    def rpc(self, method, payload=b""):
        if method not in {"GetSystemInfo", "GetToken", "GetSubFiles", "AddOfflineFiles", "GetSearchResults", "GetDownloadUrlPath", "ListOfflineFilesByPath", "GetRuntimeInfo", "GetSpaceInfo"}:
            raise ValueError("Method outside the reviewed adapter subset")
        headers = {"Content-Type": "application/grpc-web+proto", "x-grpc-web": "1"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        deadline, body = time.monotonic() + 15, bytearray()
        with self.session.post(self.base + method, data=struct.pack(">BI", 0, len(payload)) + payload,
                               headers=headers, timeout=(3.05, 8), stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                raise CD2Error("http-" + str(response.status_code))
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > LIMIT or time.monotonic() > deadline:
                    raise CD2Error("response-bound-exceeded")
            return decode_response(bytes(body), response.headers)

    def login(self, username, password):
        replies = self.rpc("GetToken", field(1, username) + field(2, password))
        if len(replies) != 1:
            raise CD2Error("invalid-login-response")
        data = fields(replies[0])
        if data.get(1, [0])[0] != 1 or not data.get(3):
            raise CD2Error("login-rejected")
        self.token = data[3][0].decode("utf-8")
        return self.token

    def list_directory(self, path):
        if not path.startswith("/"):
            raise ValueError("Absolute CD2 path required")
        return [fields(reply) for reply in self.rpc("GetSubFiles", field(1, path) + field(2, False))]

    def files(self, path):
        """Typed names and capabilities; deliberately omit signed URLs/tokens."""
        return decode_files(self.list_directory(path))

    def search(self, path, query):
        if not (path == "/115open" or path.startswith("/115open/")) or not query.strip():
            raise ValueError("Search requires a scoped 115 path and nonempty query")
        payload = field(1, path) + field(2, query) + field(3, False) + field(4, True) + field(5, False)
        return decode_files([fields(reply) for reply in self.rpc("GetSearchResults", payload)])

    def download_path(self, path):
        """Return an ephemeral local CD2 route IN MEMORY; never persist/log it."""
        if not path.startswith("/115open/"):
            raise ValueError("Expected a scoped 115 media path")
        replies = self.rpc("GetDownloadUrlPath", field(1, path) + field(2, False) + field(3, True) + field(4, False))
        if len(replies) != 1:
            raise CD2Error("invalid-download-path-response")
        return fields(replies[0]).get(1, [b""])[0].decode("utf-8")

    def add_offline(self, magnet, folder):
        if not magnet.startswith("magnet:?") or not folder.startswith("/115open/"):
            raise ValueError("Expected reviewed magnet and existing 115 destination")
        replies = self.rpc("AddOfflineFiles", field(1, magnet) + field(2, folder))
        if len(replies) != 1 or fields(replies[0]).get(1, [0])[0] != 1:
            raise CD2Error("offline-request-not-accepted")
        # Accepted is not completed or playable. Callers must prove final media.
        return {"status": "ACCEPTED_NOT_VERIFIED"}

    def offline_files(self, folder):
        """Read hash/status proof from the official offline-task API; omit URLs."""
        if not folder.startswith('/115open/') or any(x in {'.', '..'} for x in folder.split('/')):
            raise ValueError('Scoped 115 destination required')
        replies = self.rpc('ListOfflineFilesByPath', field(1, folder))
        if len(replies) != 1:
            raise CD2Error('invalid-offline-list-response')
        entries = fields(replies[0]).get(1, [])
        if len(entries) > 1000:
            raise CD2Error('offline-list-bound-exceeded')
        result = []
        for entry in entries:
            data = fields(entry)
            result.append({'name': data.get(1, [b''])[0].decode('utf-8'),
                           'bytes': data.get(2, [0])[0],
                           'status': data.get(4, [0])[0],
                           'hash': data.get(5, [b''])[0].decode('utf-8')})
        return result


    def runtime_info(self):
        replies = self.rpc("GetRuntimeInfo")
        if len(replies) != 1:
            raise CD2Error("invalid-runtime-response")
        data = fields(replies[0])
        return {"product": data.get(1, [b""])[0].decode("utf-8"),
                "version": data.get(2, [b""])[0].decode("utf-8")}

    def account_scope(self):
        import hashlib
        api = self._cloud_api()
        return hashlib.sha256(api[1][0] + b'\0' + api[2][0]).hexdigest()

    def _cloud_api(self):
        roots = [fields(item) for reply in self.list_directory('/') for item in reply.get(1, [])]
        matches = [row for row in roots if row.get(3, [b''])[0] == b'/115open']
        if len(matches) != 1 or not matches[0].get(9):
            raise CD2Error('cloud-account-unresolved')
        api = fields(matches[0][9][0])
        if not api.get(1) or not api.get(2):
            raise CD2Error('cloud-account-unresolved')
        return api

    def provider_identity(self):
        """Read actual mounted 115 UID, never infer it from nickname or a hash.

        Official CloudAPI uses name=1 and userName=2. 115open returns its
        numeric UID as userName; other/non-numeric providers stay unbound.
        """
        import hashlib
        import re
        api = self._cloud_api()
        # Do not expose the provider login name to caller logs or UI snapshots.
        username = api[2][0].decode('ascii')
        if not re.fullmatch(r'[1-9][0-9]{0,31}', username):
            raise CD2Error('cloud-account-uid-unavailable')
        return dict(legacy_scope=hashlib.sha256(api[1][0] + b'\0' + api[2][0]).hexdigest(),
                    account_id='115:' + hashlib.sha256(('115:' + username).encode('ascii')).hexdigest())

    def space(self, path):
        if not (path == "/115open" or path.startswith("/115open/")):
            raise ValueError("Scoped provider capacity required")
        replies = self.rpc("GetSpaceInfo", field(1, path))
        if len(replies) != 1:
            raise CD2Error("invalid-capacity-response")
        data = fields(replies[0])
        total, used, free = (data.get(n, [0])[0] for n in (1, 2, 3))
        if not total > 0 or not 0 <= free <= total or not 0 <= used <= total:
            raise CD2Error("unverified-capacity")
        return {"total": total, "used": used, "free": free}

    def identified_files(self, path):
        replies = self.list_directory(path)
        legacy = decode_files(replies)
        raw = [fields(item) for reply in replies for item in reply.get(1, [])]
        for item, data in zip(legacy, raw):
            item["file_id"] = data.get(1, [b""])[0].decode("utf-8")
            item["hashes"] = {}
            for value in data.get(70, []):
                pair = fields(value)
                kind = pair.get(1, [0])[0]
                digest = pair.get(2, [b""])[0].decode("ascii")
                # File hashes and torrent info-hashes are distinct types.
                if kind in (1, 2):
                    label, length = ("md5", 32) if kind == 1 else ("sha1", 40)
                    if len(digest) == length and all(c in "0123456789abcdefABCDEF" for c in digest):
                        item["hashes"][label] = digest.lower()
        return legacy

    def offline_tasks(self, folder):
        if not folder.startswith("/115open/") or any(x in {"", ".", ".."} for x in folder.split("/")[1:]):
            raise ValueError("Scoped destination required")
        replies = self.rpc("ListOfflineFilesByPath", field(1, folder))
        if len(replies) != 1:
            raise CD2Error("invalid-offline-list-response")
        entries = fields(replies[0]).get(1, [])
        if len(entries) > 1000:
            raise CD2Error("offline-list-bound-exceeded")
        result = []
        for entry in entries:
            data = fields(entry)
            def text(number):
                return data.get(number, [b""])[0].decode("utf-8")
            result.append({"name": text(1), "bytes": data.get(2, [0])[0],
                           "status": data.get(4, [0])[0], "info_hash": text(5).lower(),
                           "file_id": text(6), "parent_id": text(8)})
        return result


def decode_files(replies):
    result = []
    for reply in replies:
        for data in reply.get(1, []):
            entry = fields(data)
            def text_value(number):
                return entry.get(number, [b""])[0].decode("utf-8")
            path = text_value(3)
            if not path.startswith("/") or "\x00" in path:
                raise ValueError("Invalid CD2 file path")
            result.append({"name": text_value(2), "path": path,
                           "bytes": entry.get(4, [0])[0],
                           "directory": bool(entry.get(30, [False])[0]) or entry.get(5, [0])[0] == 0,
                           "forbidden": bool(entry.get(36, [False])[0]),
                           "can_search": bool(entry.get(63, [False])[0]),
                           "can_offline_download": bool(entry.get(66, [False])[0])})
            if len(result) > 10000:
                raise ValueError("Directory item budget exceeded")
    return result
