"""Local synthetic evidence only: no HTTP, accounts, subprocesses or devices."""

import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "ce_ebml_directory", Path(__file__).resolve().parents[1] / "tools/ce_ebml_directory.py")
ebml = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ebml)


def size_vint(value, width=None):
    if width is None:
        width = next(n for n in range(1, 9) if value < (1 << (7 * n)) - 1)
    return ((1 << (7 * width)) | value).to_bytes(width, "big")


def element(identifier, payload=b"", width=None):
    return bytes.fromhex(identifier) + size_vint(len(payload), width) + payload


def document(payload=b"", unknown_segment=False):
    segment = bytes.fromhex(ebml.SEGMENT)
    size = b"\xff" if unknown_segment else size_vint(len(payload))
    return element(ebml.EBML) + segment + size + payload


def attachment(data=b"font-private-bytes", name=b"private-font.ttf", mime=b"font/ttf"):
    content = element("466e", name) + element("4660", mime) + element(ebml.FILE_DATA, data)
    return element(ebml.ATTACHMENTS, element(ebml.ATTACHED_FILE, content))


def seek(identifier, relative, position_width=4):
    return element(ebml.SEEK,
                   element(ebml.SEEK_ID, bytes.fromhex(identifier)) +
                   element(ebml.SEEK_POSITION, relative.to_bytes(position_width, "big")))


class Reader:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def __call__(self, start, end):
        assert type(start) is int and type(end) is int
        assert 0 <= start <= end < len(self.data)
        assert end - start + 1 <= 4096
        self.calls.append((start, end))
        return self.data[start:end + 1]

    def inspect(self, **kwargs):
        return ebml.inspect_directory(len(self.data), self, **kwargs)


def assert_no_payload_reads(result, calls, identifiers):
    for item in result["elements"]:
        if item["id"] in identifiers and item["declared_size"]:
            for start, end in calls:
                assert end < item["payload_offset"] or start >= item["end_offset"]


def assert_closed_result(result):
    assert set(result) == {
        "schema", "status", "stop_code", "file_size", "bytes_read", "requests",
        "elapsed_ms", "limits", "elements", "seeks",
    }
    assert set(result["limits"]) == {
        "bytes", "seconds", "requests", "read_bytes", "elements", "seek_entries", "seek_targets",
    }
    for item in result["elements"]:
        assert set(item) == {
            "id", "offset", "header_bytes", "declared_size", "payload_offset",
            "end_offset", "scope", "parent_offset",
        }
        assert 2 <= len(item["id"]) <= 8
        int(item["id"], 16)
    for item in result["seeks"]:
        assert set(item) == {"target_id", "relative_offset", "absolute_offset", "state"}
    json.dumps(result, allow_nan=False)


def test_empty_segment_is_complete_with_exact_header_counters():
    reader = Reader(document())
    result = reader.inspect()
    assert result["status"] == "complete"
    assert result["stop_code"] == "segment_end"
    assert result["requests"] == len(reader.calls) == 4
    assert result["bytes_read"] == len(reader.data) == 10
    assert [x["id"] for x in result["elements"]] == [ebml.EBML, ebml.SEGMENT]
    assert_closed_result(result)


def test_payloads_are_never_read_or_returned_and_cluster_is_header_only():
    reader = Reader(document(attachment() + element(ebml.CLUSTER, b"private-video")))
    result = reader.inspect()
    assert result["status"] == "partial" and result["stop_code"] == "first_cluster"
    assert_no_payload_reads(result, reader.calls, {"466e", "4660", ebml.FILE_DATA, ebml.CLUSTER})
    assert "private" not in json.dumps(result)
    assert result["bytes_read"] == sum(end - start + 1 for start, end in reader.calls)
    assert "attachments_absent" not in result
    assert_closed_result(result)


def test_large_attachment_is_skipped_to_cluster_under_fixed_limits():
    reader = Reader(document(attachment(data=b"x" * (19 * 1024 * 1024)) + element(ebml.CLUSTER, b"video")))
    result = reader.inspect()
    assert result["stop_code"] == "first_cluster"
    font = next(x for x in result["elements"] if x["id"] == ebml.FILE_DATA)
    assert font["declared_size"] == 19 * 1024 * 1024
    assert result["bytes_read"] < 128 and result["requests"] <= 32
    assert_no_payload_reads(result, reader.calls, {"466e", "4660", ebml.FILE_DATA, ebml.CLUSTER})
    assert any(start >= font["end_offset"] for start, _ in reader.calls)


@pytest.mark.parametrize("unknown_segment", [False, True])
def test_declared_and_unknown_segment_offsets_are_exact(unknown_segment):
    reader = Reader(document(element("ec", b"skip me"), unknown_segment))
    result = reader.inspect()
    assert result["stop_code"] == "segment_end"
    segment = result["elements"][1]
    assert segment["end_offset"] == len(reader.data)
    assert (segment["declared_size"] is None) == unknown_segment
    assert result["elements"][-1]["offset"] == segment["payload_offset"]


@pytest.mark.parametrize("size", [None, True, -1, 1.0, "12", 1 << 63])
def test_invalid_size_does_no_read(size):
    result = ebml.inspect_directory(size, lambda *_: pytest.fail("no reads"))
    assert result["stop_code"] == "invalid_input"
    assert result["file_size"] is None and result["requests"] == 0


@pytest.mark.parametrize("raw,code", [
    (b"", "truncated_header"),
    (b"\x00", "invalid_vint"),
    (b"\x08", "invalid_vint"),
    (b"\xff\x80", "invalid_element_id"),
    (b"\x81\x00", "invalid_vint"),
    (b"\x81\x80", "missing_ebml"),
    (bytes.fromhex(ebml.EBML), "truncated_header"),
    (bytes.fromhex(ebml.EBML) + b"\x40", "truncated_header"),
    (element(ebml.EBML) + element("ec"), "missing_segment"),
    (bytes.fromhex(ebml.EBML) + b"\xff", "unknown_size"),
    (bytes.fromhex(ebml.EBML) + b"\x81", "element_out_of_bounds"),
])
def test_malformed_headers_stop_safely(raw, code):
    result = Reader(raw).inspect()
    assert result["stop_code"] == code
    assert result["status"] == "partial"
    assert_closed_result(result)


@pytest.mark.parametrize("identifier", [ebml.CLUSTER, ebml.ATTACHMENTS, ebml.ATTACHED_FILE, "ec"])
def test_unknown_size_is_not_guessed_outside_segment(identifier):
    result = Reader(document(bytes.fromhex(identifier) + b"\xff")).inspect()
    assert result["stop_code"] == "unknown_size"
    assert result["elements"][-1]["declared_size"] is None


def test_child_may_not_cross_parent_even_when_bytes_exist_in_file():
    malformed = element(ebml.ATTACHMENTS, bytes.fromhex(ebml.ATTACHED_FILE) + b"\x81")
    result = Reader(document(malformed + element(ebml.CLUSTER, b"secret"))).inspect()
    assert result["stop_code"] == "element_out_of_bounds"
    assert result["elements"][-1]["id"] == ebml.ATTACHED_FILE


def test_no_header_read_crosses_parent_boundary():
    reader = Reader(document(element(ebml.ATTACHMENTS, b"\x61") + element("ec", b"secret")))
    result = reader.inspect()
    assert result["stop_code"] == "truncated_header"
    attachments = next(x for x in result["elements"] if x["id"] == ebml.ATTACHMENTS)
    assert reader.calls[-1] == (attachments["payload_offset"], attachments["payload_offset"])


def seek_document(target_id=ebml.ATTACHMENTS, duplicate=False, actual=None):
    first = element(ebml.CLUSTER, b"private-cluster")
    tail = attachment() if actual is None else actual
    dummy = seek(target_id, 0)
    head_size = len(element(ebml.SEEK_HEAD, dummy * (2 if duplicate else 1)))
    entry = seek(target_id, head_size + len(first))
    return document(element(ebml.SEEK_HEAD, entry * (2 if duplicate else 1)) + first + tail)


def test_seek_follows_only_attachments_after_first_cluster():
    reader = Reader(seek_document())
    result = reader.inspect()
    assert result["stop_code"] == "first_cluster"
    assert result["seeks"][0]["state"] == "followed"
    assert any(x["id"] == ebml.FILE_DATA for x in result["elements"])
    assert_no_payload_reads(result, reader.calls, {"466e", "4660", ebml.FILE_DATA, ebml.CLUSTER})
    assert_closed_result(result)


@pytest.mark.parametrize("target", [ebml.SEEK_HEAD, "1c53bb6b", "1549a966", "1654ae6b", ebml.CLUSTER])
def test_other_seek_targets_are_recorded_but_never_followed(target):
    reader = Reader(seek_document(target))
    result = reader.inspect()
    assert result["stop_code"] == "first_cluster"
    assert result["seeks"][0]["state"] == "not_followed"
    assert result["elements"][-1]["id"] == ebml.CLUSTER
    assert not any(x["id"] == ebml.ATTACHMENTS for x in result["elements"])


def test_duplicate_seek_offset_is_visited_once():
    reader = Reader(seek_document(duplicate=True))
    result = reader.inspect()
    assert result["stop_code"] == "first_cluster"
    assert [x["state"] for x in result["seeks"]] == ["followed", "already_visited"]
    assert sum(x["id"] == ebml.ATTACHMENTS for x in result["elements"]) == 1


def test_seek_to_already_walked_attachments_is_not_repeated():
    body = attachment()
    dummy = element(ebml.SEEK_HEAD, seek(ebml.ATTACHMENTS, 0))
    head = element(ebml.SEEK_HEAD, seek(ebml.ATTACHMENTS, len(dummy)))
    reader = Reader(document(head + body + element(ebml.CLUSTER)))
    result = reader.inspect()
    assert result["stop_code"] == "first_cluster"
    assert result["seeks"][0]["state"] == "already_visited"


def test_seek_target_id_mismatch_stops_without_reading_target_payload():
    reader = Reader(seek_document(actual=element("ec", b"private-value")))
    result = reader.inspect()
    assert result["stop_code"] == "seek_target_mismatch"
    assert result["seeks"][0]["state"] == "mismatch"
    assert_no_payload_reads(result, reader.calls, {"ec"})


@pytest.mark.parametrize("target", [0, 10])
def test_seek_cannot_reenter_seekhead_or_cluster_payload(target):
    dummy = element(ebml.SEEK_HEAD, seek(ebml.ATTACHMENTS, 0))
    position = 0 if target == 0 else len(dummy) + 5
    head = element(ebml.SEEK_HEAD, seek(ebml.ATTACHMENTS, position))
    reader = Reader(document(head + element(ebml.CLUSTER, attachment())))
    result = reader.inspect()
    assert result["stop_code"] == "seek_overlaps_element"
    assert_no_payload_reads(result, reader.calls, {ebml.CLUSTER})


def test_out_of_file_seek_is_rejected():
    reader = Reader(document(element(ebml.SEEK_HEAD, seek(ebml.ATTACHMENTS, 0xffffffff))))
    result = reader.inspect()
    assert result["stop_code"] == "seek_out_of_bounds"


@pytest.mark.parametrize("body", [
    element(ebml.SEEK_ID),
    element(ebml.SEEK_ID, b"\x18\x53\x80\x67\x00"),
    element(ebml.SEEK_ID, b"\x00"),
    element(ebml.SEEK_ID, b"\xff"),
    element(ebml.SEEK_ID, b"\x18\x53"),
    element(ebml.SEEK_POSITION),
    element(ebml.SEEK_POSITION, b"\x00" * 9),
    element(ebml.SEEK_ID, bytes.fromhex(ebml.ATTACHMENTS)),
    element(ebml.SEEK_POSITION, b"\x00"),
    element(ebml.SEEK_ID, bytes.fromhex(ebml.ATTACHMENTS)) * 2,
    element(ebml.SEEK_POSITION, b"\x00") * 2,
])
def test_invalid_seek_is_safe_and_closed(body):
    result = Reader(document(element(ebml.SEEK_HEAD, element(ebml.SEEK, body)))).inspect()
    assert result["stop_code"] in {"invalid_seek", "invalid_vint"}
    assert_closed_result(result)


def test_request_budget_is_fixed_and_does_not_read_33rd_request():
    reader = Reader(document(element("ec") * 100))
    result = reader.inspect()
    assert result["stop_code"] == "request_budget"
    assert result["requests"] == len(reader.calls) == 32
    assert result["bytes_read"] <= 128 * 1024


def test_element_limit_applies_inside_cached_seekhead():
    reader = Reader(document(element(ebml.SEEK_HEAD, element("ec") * 300)))
    result = reader.inspect()
    assert result["stop_code"] == "element_limit"
    assert len(result["elements"]) == 256 and result["requests"] < 32


def test_seek_entry_limit_applies_before_following_any_target():
    reader = Reader(document(element(ebml.SEEK_HEAD, seek("1549a966", 0) * 33)))
    result = reader.inspect()
    assert result["stop_code"] == "seek_entry_limit"
    assert len(result["seeks"]) == 32 and result["requests"] < 32


def test_unique_attachment_target_limit_is_eight():
    head = element(ebml.SEEK_HEAD, b"".join(seek(ebml.ATTACHMENTS, i) for i in range(9)))
    result = Reader(document(head)).inspect()
    assert result["stop_code"] == "seek_target_limit"
    assert len(result["seeks"]) == 8 and result["requests"] < 32


def test_byte_budget_is_enforced_by_shared_reader():
    reader = Reader(b"x" * (129 * 1024))
    parser = ebml._Directory(len(reader.data), reader, lambda: False, lambda: 0)
    for i in range(32):
        parser._get(i * 4096, 4096)
    assert parser.result["bytes_read"] == 128 * 1024
    with pytest.raises(ebml._Stop) as exc:
        parser._get(128 * 1024, 1)
    assert exc.value.code == "request_budget"
    assert len(reader.calls) == 32


def test_cancelled_before_first_read_and_after_first_reply():
    reader = Reader(document())
    result = reader.inspect(cancelled=lambda: True)
    assert result["stop_code"] == "cancelled" and not reader.calls
    result = reader.inspect(cancelled=lambda: bool(reader.calls))
    assert result["stop_code"] == "cancelled"
    assert result["requests"] == result["bytes_read"] == 1


def test_total_time_budget_counts_callback_time_and_stops_next_read():
    reader = Reader(document())
    now = [0.0]

    def read(start, end):
        reply = reader(start, end)
        now[0] = 20.0
        return reply

    result = ebml.inspect_directory(len(reader.data), read, clock=lambda: now[0])
    assert result["stop_code"] == "time_budget"
    assert result["requests"] == result["bytes_read"] == 1
    assert result["elapsed_ms"] == 20000


@pytest.mark.parametrize("now", [float("nan"), float("inf"), float("-inf"), "private-clock"])
def test_invalid_clock_is_closed_and_never_reads(now):
    result = ebml.inspect_directory(10, lambda *_: pytest.fail("no reads"), clock=lambda: now)
    assert result["stop_code"] == "invalid_clock" and result["requests"] == 0
    assert_closed_result(result)


def test_backwards_clock_stops():
    times = iter([1.0, 0.0])
    result = ebml.inspect_directory(10, lambda *_: pytest.fail("no reads"), clock=lambda: next(times))
    assert result["stop_code"] == "invalid_clock"


def test_callback_exception_text_is_not_exposed():
    def read(*_):
        raise RuntimeError("https://private/token password account path")

    result = ebml.inspect_directory(10, read)
    assert result["stop_code"] == "read_failed" and result["requests"] == 1
    assert result["bytes_read"] == 0
    assert not any(secret in json.dumps(result) for secret in ("https", "password", "account"))


@pytest.mark.parametrize("reply,code,count", [(b"", "short_read", 0), (b"xx", "read_contract", 2),
                                               ("private", "read_contract", 0), (None, "read_contract", 0)])
def test_nonexact_reader_is_rejected_and_returned_bytes_counted(reply, code, count):
    result = ebml.inspect_directory(10, lambda *_: reply)
    assert result["stop_code"] == code and result["bytes_read"] == count
    assert result["requests"] == 1


def test_cancellation_callback_failure_is_closed():
    def cancelled():
        raise RuntimeError("private-cancel")

    result = ebml.inspect_directory(10, lambda *_: pytest.fail("no read"), cancelled=cancelled)
    assert result["stop_code"] == "cancel_check_failed"
    assert "private" not in json.dumps(result)


def test_cli_emits_only_safe_json_for_local_file_and_missing_file(tmp_path, capsys):
    path = tmp_path / "private-title.mkv"
    path.write_bytes(document(attachment() + element(ebml.CLUSTER)))
    assert ebml.main([str(path)]) == 0
    output = capsys.readouterr().out
    assert "private" not in output
    assert_closed_result(json.loads(output))
    assert ebml.main([str(tmp_path / "missing-private-title.mkv")]) == 1
    output = capsys.readouterr().out
    assert "private" not in output and json.loads(output)["stop_code"] == "file_unavailable"
