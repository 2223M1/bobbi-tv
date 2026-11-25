"""Bounded subtitle upload validation and legacy multipart compatibility parser.

Standalone unauthenticated port 8082 listener is retired (U10 / ROOT-SUBTITLE-PARSER).
Subtitle uploads are served exclusively through paired PhoneManagement sessions
bound to (profile, target_id, source_key) with CSRF and Origin enforcement.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import re
import socket
import time
from urllib.parse import unquote
import uuid

from lib.utils.kodi.utils import ADDON_PROFILE_PATH, kodilog

MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
MAX_MULTIPART_OVERHEAD = 16 * 1024
MAX_MULTIPART_PARTS = 8
READ_CHUNK_BYTES = 16 * 1024
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".sub", ".vtt", ".txt"}


def _ensure_upload_dir(base_dir: str | Path | None = None) -> str:
    root = str(base_dir) if base_dir is not None else ADDON_PROFILE_PATH
    upload_dir = os.path.join(root, "Subtitles", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def sanitize_subtitle_filename(raw_filename: str) -> str:
    """Validate and sanitize a subtitle filename while preserving UTF-8 / Chinese characters."""
    if not isinstance(raw_filename, str):
        raise ValueError("SUBTITLE_FILENAME_INVALID")
    normalized = raw_filename.replace("\\", "/").split("/")[-1].strip()
    if (
        not 1 <= len(normalized) <= 180
        or normalized in {".", ".."}
        or any(ord(c) < 32 or ord(c) == 127 or c in '<>:"|?*\x00' for c in normalized)
    ):
        raise ValueError("SUBTITLE_FILENAME_INVALID")
    stem, ext = os.path.splitext(normalized)
    ext_lower = ext.lower()
    if not stem.strip() or ext_lower not in SUBTITLE_EXTENSIONS:
        raise ValueError("SUBTITLE_EXTENSION_UNSUPPORTED")
    return stem.strip() + ext_lower


def validate_subtitle_bytes(raw_bytes: bytes) -> bytes:
    """Validate bounded subtitle content, preserving UTF-8, UTF-8 BOM, UTF-16 BOM, or legacy CJK encodings."""
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise ValueError("SUBTITLE_CONTENT_INVALID")
    data = bytes(raw_bytes)
    if not 1 <= len(data) <= MAX_SUBTITLE_BYTES:
        raise ValueError("SUBTITLE_SIZE_INVALID")
    has_utf16_bom = data.startswith((b"\xff\xfe", b"\xfe\xff"))
    if not has_utf16_bom and b"\x00" in data:
        raise ValueError("SUBTITLE_BINARY_REJECTED")
    return data


def store_validated_subtitle(upload_dir: str | Path, raw_filename: str, raw_bytes: bytes) -> dict:
    """Atomically store a validated subtitle file with restricted permissions."""
    clean_name = sanitize_subtitle_filename(raw_filename)
    data = validate_subtitle_bytes(raw_bytes)
    out_dir = Path(upload_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    safe_filename = f"{timestamp}_{unique_id}_{clean_name}"
    file_path = out_dir / safe_filename
    fd = os.open(str(file_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except BaseException:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return {
        "file_name": clean_name,
        "path": str(file_path),
        "byte_length": len(data),
        "sha256": sha256(data).hexdigest(),
    }


def _extract_disposition_filename(headers_text: str) -> str | None:
    # RFC 5987 filename*=UTF-8''... first
    m_star = re.search(r"filename\*\s*=\s*UTF-8''([^;\r\n]+)", headers_text, flags=re.IGNORECASE)
    if m_star:
        decoded = unquote(m_star.group(1).strip().strip('"'))
        if decoded:
            return decoded
    for quote_char in ('"', "'"):
        marker = f"filename={quote_char}"
        start = headers_text.find(marker)
        if start != -1:
            start += len(marker)
            end = headers_text.find(quote_char, start)
            if end != -1:
                return headers_text[start:end]
    m_bare = re.search(r"filename\s*=\s*([^;\s\r\n]+)", headers_text, flags=re.IGNORECASE)
    if m_bare:
        return m_bare.group(1).strip()
    return None


def parse_bounded_multipart(
    headers,
    rfile,
    *,
    max_bytes: int = MAX_SUBTITLE_BYTES,
    timeout_sec: float = 5.0,
    clock=time.monotonic,
) -> tuple[str | None, bytes | str]:
    """Strictly bounded, non-backtracking multipart/form-data file extractor.

    Every branch either strictly advances `pos` or returns immediately with an
    explicit `(None, reason)` tuple. Enforces Content-Length bounds, read deadlines,
    truncated-body detection, header terminator presence, and closing boundary presence.
    """
    if headers is None or rfile is None:
        return None, "Missing request headers or body"
    content_type = str(headers.get("Content-Type", "") or "")
    if not content_type.lower().startswith("multipart/form-data"):
        return None, "Invalid content type"

    boundary_idx = content_type.find("boundary=")
    if boundary_idx == -1:
        return None, "No boundary in content type"
    raw_boundary = content_type[boundary_idx + len("boundary=") :].split(";", 1)[0].strip().strip('"')
    if (
        not 1 <= len(raw_boundary) <= 200
        or any(c in raw_boundary for c in ("\r", "\n", "\x00"))
    ):
        return None, "Invalid multipart boundary"

    raw_len = headers.get("Content-Length")
    if raw_len is None:
        return None, "Missing Content-Length"
    try:
        content_length = int(str(raw_len).strip())
    except (ValueError, TypeError):
        return None, "Invalid Content-Length"
    if content_length <= 0:
        return None, "Invalid or empty Content-Length"
    max_wire_bytes = max_bytes + MAX_MULTIPART_OVERHEAD
    if content_length > max_wire_bytes:
        return None, "Content-Length exceeds maximum subtitle upload limit"

    deadline = clock() + max(0.1, float(timeout_sec))
    buf = bytearray()
    remaining = content_length
    while remaining > 0:
        if clock() >= deadline:
            return None, "Multipart read timed out"
        try:
            chunk = rfile.read(min(READ_CHUNK_BYTES, remaining))
        except (OSError, ValueError):
            return None, "Multipart stream read error"
        if not chunk:
            return None, "Truncated multipart stream"
        buf.extend(chunk)
        remaining -= len(chunk)
        if len(buf) > max_wire_bytes:
            return None, "Multipart payload exceeds limit"

    post_data = bytes(buf)
    boundary_bytes = ("--" + raw_boundary).encode("utf-8")
    end_boundary_bytes = ("--" + raw_boundary + "--").encode("utf-8")

    start_idx = post_data.find(boundary_bytes)
    if start_idx == -1:
        return None, "Missing initial boundary"
    if post_data.find(end_boundary_bytes, start_idx + len(boundary_bytes)) == -1:
        return None, "Missing closing boundary"

    pos = start_idx + len(boundary_bytes)
    parts_seen = 0

    while pos < len(post_data):
        parts_seen += 1
        if parts_seen > MAX_MULTIPART_PARTS:
            return None, "Too many multipart sections"
        if post_data[pos : pos + 2] == b"--":
            break

        if post_data[pos : pos + 2] == b"\r\n":
            pos += 2
        elif post_data[pos : pos + 1] == b"\n":
            pos += 1
        else:
            return None, "Malformed boundary line ending"

        part_boundary = post_data.find(boundary_bytes, pos)
        if part_boundary == -1:
            return None, "Missing part boundary"

        crlf_end = post_data.find(b"\r\n\r\n", pos, part_boundary)
        lf_end = post_data.find(b"\n\n", pos, part_boundary)
        if crlf_end != -1 and (lf_end == -1 or crlf_end <= lf_end):
            header_end, header_sep_len = crlf_end, 4
        elif lf_end != -1:
            header_end, header_sep_len = lf_end, 2
        else:
            return None, "Missing multipart header terminator"

        if header_end - pos > 8192:
            return None, "Multipart part headers too large"
        part_headers = post_data[pos:header_end].decode("utf-8", errors="replace")
        body_start = header_end + header_sep_len
        next_boundary = part_boundary

        field_data = post_data[body_start:next_boundary]
        if field_data.endswith(b"\r\n"):
            field_data = field_data[:-2]
        elif field_data.endswith(b"\n"):
            field_data = field_data[:-1]

        if len(field_data) > max_bytes:
            return None, "Subtitle file exceeds maximum size"

        if "content-disposition" in part_headers.lower():
            filename = _extract_disposition_filename(part_headers)
            if filename is not None:
                if not filename.strip():
                    return None, "Empty subtitle filename"
                return filename, field_data

        # Strictly advance past next_boundary
        next_pos = next_boundary + len(boundary_bytes)
        if next_pos <= pos:
            return None, "Multipart cursor stalled"
        pos = next_pos

    return None, "No file found in upload"


class SubtitleUploadHandler:
    """Compatibility shim preserving bounded `_parse_multipart()` for legacy witness checks."""

    headers: dict = {}
    rfile = None

    def _parse_multipart(self):
        return parse_bounded_multipart(self.headers, self.rfile)


def get_local_ip():
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
