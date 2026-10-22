"""Read-only, bounded EBML directory inspection; never a media validator.

``read(start, end)`` returns exact bytes for an inclusive range. The caller must
enforce transport identity, exact range replies, cancellation, and a hard I/O
deadline: a synchronous callback cannot be interrupted by this parser. Counters
include every callback invocation and every byte it returns, including a short
reply. No URL, filename, MIME value, payload, or exception text is returned.

Only EBML/Segment and the Segment prefix through the first Cluster are walked.
Small SeekHeads may be cached in full as directory metadata; only Attachments
targets are followed. Attachment leaf payloads and Cluster payloads are never
requested. ``end_offset`` is exclusive; an unknown-sized Segment uses the exact
file size as its effective end. No result asserts attachment absence.
"""

import argparse
import json
import math
import os
import time


MAX_BYTES = 128 * 1024
MAX_SECONDS = 20.0
MAX_REQUESTS = 32
MAX_READ = 4096
MAX_ELEMENTS = 256
MAX_SEEK_ENTRIES = 32
MAX_SEEK_TARGETS = 8
MAX_FILE_SIZE = (1 << 63) - 1

EBML = "1a45dfa3"
SEGMENT = "18538067"
CLUSTER = "1f43b675"
SEEK_HEAD = "114d9b74"
SEEK = "4dbb"
SEEK_ID = "53ab"
SEEK_POSITION = "53ac"
ATTACHMENTS = "1941a469"
ATTACHED_FILE = "61a7"
FILE_DATA = "465c"


class _Stop(Exception):
    def __init__(self, code):
        self.code = code


def _width(first, maximum):
    if not first:
        raise _Stop("invalid_vint")
    width = 1
    marker = 0x80
    while not first & marker:
        marker >>= 1
        width += 1
    if width > maximum:
        raise _Stop("invalid_vint")
    return width


class _Directory:
    def __init__(self, size, read, cancelled, clock):
        self.size = size
        self.read = read
        self.cancelled = cancelled
        self.clock = clock
        self.start = None
        self.last_time = None
        self.cache = None
        self.segment = None
        self.visited_attachments = set()
        self.target_offsets = set()
        self.seek_count = 0
        self.result = {
            "schema": "ce-ebml-directory-v1",
            "status": "partial",
            "stop_code": "invalid_input",
            "file_size": size if type(size) is int and 0 <= size <= MAX_FILE_SIZE else None,
            "bytes_read": 0,
            "requests": 0,
            "elapsed_ms": 0,
            "limits": {
                "bytes": MAX_BYTES, "seconds": MAX_SECONDS,
                "requests": MAX_REQUESTS, "read_bytes": MAX_READ,
                "elements": MAX_ELEMENTS, "seek_entries": MAX_SEEK_ENTRIES,
                "seek_targets": MAX_SEEK_TARGETS,
            },
            "elements": [],
            "seeks": [],
        }

    def _check(self):
        try:
            now = float(self.clock())
        except Exception:
            raise _Stop("invalid_clock") from None
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            raise _Stop("invalid_clock")
        if self.start is None:
            self.start = now
        self.last_time = now
        elapsed = now - self.start
        if not math.isfinite(elapsed):
            raise _Stop("invalid_clock")
        self.result["elapsed_ms"] = int(elapsed * 1000) if elapsed < MAX_SECONDS else 20000
        if elapsed >= MAX_SECONDS:
            raise _Stop("time_budget")
        try:
            cancelled = bool(self.cancelled())
        except Exception:
            raise _Stop("cancel_check_failed") from None
        if cancelled:
            raise _Stop("cancelled")

    def _get(self, start, count):
        self._check()
        if count < 0 or start < 0 or start + count > self.size:
            raise _Stop("truncated_header")
        if count == 0:
            return b""
        if self.cache is not None:
            base, data = self.cache
            if base <= start and start + count <= base + len(data):
                return data[start - base:start - base + count]
        if count > MAX_READ:
            raise _Stop("read_size_limit")
        if self.result["requests"] >= MAX_REQUESTS:
            raise _Stop("request_budget")
        if self.result["bytes_read"] + count > MAX_BYTES:
            raise _Stop("byte_budget")
        self.result["requests"] += 1
        try:
            data = self.read(start, start + count - 1)
        except Exception:
            raise _Stop("read_failed") from None
        if not isinstance(data, bytes):
            raise _Stop("read_contract")
        self.result["bytes_read"] += len(data)
        self._check()
        if len(data) != count:
            raise _Stop("short_read" if len(data) < count else "read_contract")
        return data

    def _header(self, offset, bound, scope, parent_offset=None):
        self._check()
        if len(self.result["elements"]) >= MAX_ELEMENTS:
            raise _Stop("element_limit")
        if offset >= bound:
            raise _Stop("truncated_header")
        first = self._get(offset, 1)
        id_width = _width(first[0], 4)
        # Read the remainder of the ID and the size's first byte, never payload.
        if offset + id_width + 1 > bound:
            raise _Stop("truncated_header")
        rest = self._get(offset + 1, id_width)
        element_id = first + rest[:-1]
        # All-one ID data is reserved by EBML; IDs retain their marker bits.
        if int.from_bytes(element_id, "big") == (1 << (7 * id_width + 1)) - 1:
            raise _Stop("invalid_element_id")
        size_width = _width(rest[-1], 8)
        header_bytes = id_width + size_width
        if offset + header_bytes > bound:
            raise _Stop("truncated_header")
        size_bytes = bytes((rest[-1],)) + self._get(offset + id_width + 1, size_width - 1)
        declared = int.from_bytes(size_bytes, "big") & ((1 << (7 * size_width)) - 1)
        unknown = declared == (1 << (7 * size_width)) - 1
        payload = offset + header_bytes
        identifier = element_id.hex()
        end = None if unknown else payload + declared
        record = {
            "id": identifier, "offset": offset, "header_bytes": header_bytes,
            "declared_size": None if unknown else declared,
            "payload_offset": payload, "end_offset": end,
            "scope": scope, "parent_offset": parent_offset,
        }
        self.result["elements"].append(record)
        if unknown:
            if identifier != SEGMENT or scope != "file":
                raise _Stop("unknown_size")
            record["end_offset"] = bound
        elif end > bound:
            raise _Stop("element_out_of_bounds")
        return record

    def _attachments(self, element):
        self.visited_attachments.add(element["offset"])
        offset = element["payload_offset"]
        while offset < element["end_offset"]:
            child = self._header(offset, element["end_offset"], "attachments", element["offset"])
            if child["id"] == ATTACHED_FILE:
                leaf_offset = child["payload_offset"]
                while leaf_offset < child["end_offset"]:
                    leaf = self._header(leaf_offset, child["end_offset"], "attached_file", child["offset"])
                    # Including FileData, filename, MIME, description and UID:
                    # every leaf payload is skipped, not decoded or prefetched.
                    leaf_offset = leaf["end_offset"]
            offset = child["end_offset"]

    def _seek_head(self, element):
        # Only a known, bounded SeekHead is prefetched. No generic read-ahead
        # cache can accidentally ingest a font or the first Cluster's payload.
        old_cache = self.cache
        length = element["declared_size"]
        if 0 < length <= MAX_READ:
            self.cache = (element["payload_offset"], self._get(element["payload_offset"], length))
        try:
            offset = element["payload_offset"]
            while offset < element["end_offset"]:
                child = self._header(offset, element["end_offset"], "seek_head", element["offset"])
                if child["id"] == SEEK:
                    self._seek_entry(child)
                offset = child["end_offset"]
        finally:
            self.cache = old_cache

    def _seek_entry(self, element):
        if self.seek_count >= MAX_SEEK_ENTRIES:
            raise _Stop("seek_entry_limit")
        self.seek_count += 1
        target_id = None
        position = None
        offset = element["payload_offset"]
        while offset < element["end_offset"]:
            leaf = self._header(offset, element["end_offset"], "seek", element["offset"])
            count = leaf["declared_size"]
            if leaf["id"] == SEEK_ID:
                if target_id is not None or not 1 <= count <= 4:
                    raise _Stop("invalid_seek")
                raw = self._get(leaf["payload_offset"], count)
                if _width(raw[0], 4) != count:
                    raise _Stop("invalid_seek")
                if int.from_bytes(raw, "big") == (1 << (7 * count + 1)) - 1:
                    raise _Stop("invalid_seek")
                target_id = raw.hex()
            elif leaf["id"] == SEEK_POSITION:
                if position is not None or not 1 <= count <= 8:
                    raise _Stop("invalid_seek")
                position = int.from_bytes(self._get(leaf["payload_offset"], count), "big")
            offset = leaf["end_offset"]
        if target_id is None or position is None:
            raise _Stop("invalid_seek")
        absolute = self.segment["payload_offset"] + position
        if not self.segment["payload_offset"] <= absolute < self.segment["end_offset"]:
            raise _Stop("seek_out_of_bounds")
        state = "not_followed"
        if target_id == ATTACHMENTS:
            if absolute not in self.target_offsets and len(self.target_offsets) >= MAX_SEEK_TARGETS:
                raise _Stop("seek_target_limit")
            self.target_offsets.add(absolute)
            state = "pending"
        self.result["seeks"].append({
            "target_id": target_id, "relative_offset": position,
            "absolute_offset": absolute, "state": state,
        })

    def _follow_attachments(self):
        for target in self.result["seeks"]:
            if target["state"] != "pending":
                continue
            self._check()
            offset = target["absolute_offset"]
            if offset in self.visited_attachments:
                target["state"] = "already_visited"
                continue
            # A SeekPosition is not allowed to reinterpret a known leaf or its
            # payload as a new top-level directory. Segment itself is excluded.
            for item in self.result["elements"]:
                if item["id"] != SEGMENT and item["offset"] <= offset < (item["end_offset"] or item["payload_offset"]):
                    raise _Stop("seek_overlaps_element")
            element = self._header(offset, self.segment["end_offset"], "segment", self.segment["offset"])
            if element["id"] != ATTACHMENTS:
                target["state"] = "mismatch"
                raise _Stop("seek_target_mismatch")
            self._attachments(element)
            target["state"] = "followed"

    def inspect(self):
        try:
            if self.result["file_size"] is None or not callable(self.read):
                raise _Stop("invalid_input")
            self._check()
            header = self._header(0, self.size, "file")
            if header["id"] != EBML:
                raise _Stop("missing_ebml")
            self.segment = self._header(header["end_offset"], self.size, "file")
            if self.segment["id"] != SEGMENT:
                raise _Stop("missing_segment")
            offset = self.segment["payload_offset"]
            stop_code = "segment_end"
            while offset < self.segment["end_offset"]:
                element = self._header(offset, self.segment["end_offset"], "segment", self.segment["offset"])
                if element["id"] == CLUSTER:
                    stop_code = "first_cluster"
                    break
                if element["id"] == ATTACHMENTS:
                    self._attachments(element)
                elif element["id"] == SEEK_HEAD:
                    self._seek_head(element)
                offset = element["end_offset"]
            self._follow_attachments()
            self._check()
            self.result["stop_code"] = stop_code
            self.result["status"] = "complete" if stop_code == "segment_end" else "partial"
        except _Stop as error:
            self.result["stop_code"] = error.code
        return self.result


def inspect_directory(size, read, cancelled=lambda: False, clock=time.monotonic):
    """Return the closed safe schema, never raw payload or callback errors.

    Limits are fixed, not caller-configurable. A normal ``first_cluster`` result
    is intentionally partial: later unindexed attachments are not ruled out.
    Only ``segment_end`` means the Segment directory was fully traversed.
    """
    return _Directory(size, read, cancelled, clock).inspect()


def main(argv=None):
    """Optional local-file CLI; performs no network or device operations."""
    parser = argparse.ArgumentParser(description="Read a bounded local EBML directory as safe JSON")
    parser.add_argument("file")
    args = parser.parse_args(argv)
    try:
        with open(args.file, "rb") as handle:
            size = os.fstat(handle.fileno()).st_size

            def read(start, end):
                handle.seek(start)
                return handle.read(end - start + 1)

            result = inspect_directory(size, read)
    except (OSError, ValueError):
        result = _Directory(None, None, lambda: False, time.monotonic).result
        result["stop_code"] = "file_unavailable"
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result["stop_code"] in ("first_cluster", "segment_end") else 1


if __name__ == "__main__":
    raise SystemExit(main())
