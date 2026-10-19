"""No Kodi installation, network, device, or playback operations required."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[1] / "addons/script.bobbi.opensubtitles"
sys.path.insert(0, str(ROOT.parent / 'script.module.bobbi.core/lib'))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


context = load("bobbi_subtitle_context_test", ROOT / "resources/lib/context.py")
previous = sys.modules.get("resources.lib.context")
sys.modules["resources.lib.context"] = context
try:
    ui = load("bobbi_subtitle_ui_test", ROOT / "resources/lib/ui.py")
finally:
    if previous is None:
        sys.modules.pop("resources.lib.context", None)
    else:
        sys.modules["resources.lib.context"] = previous


class RPC:
    def __init__(self):
        self.state = {"protocol": 1, "selection_epoch": 4, "playback": {
            "protocol": 1, "phase": "AV_STARTED", "native_instance": "11111111-1111-1111-1111-111111111111",
            "request_id": "a" * 32, "file_identity": "bt:" + "d" * 40 + "|" + "e" * 64, "url_sha256": "b" * 64,
            "open_epoch": 4, "subtitle_intent": 2}}
        self.item = {"type": "movie", "title": "中文电影", "originaltitle": "A Film", "year": 2008,
                     "uniqueid": {"tmdb": "98765432", "imdb": "tt0780536"},
                     "file": "https://media.invalid/A.Film.2008.mkv?token=not-exported"}
        self.calls = []
        self.after_item = None

    def __call__(self, method, params):
        self.calls.append(method)
        if method == "Player.BobiState":
            return copy.deepcopy(self.state)
        if method == "Player.GetActivePlayers":
            return [{"playerid": 1, "type": "video"}]
        if method == "Player.GetItem":
            result = {"item": copy.deepcopy(self.item)}
            if self.after_item:
                self.after_item()
            return result
        if method == "Player.GetProperties":
            return {"totaltime": {"hours": 1, "minutes": 47, "seconds": 3, "milliseconds": 125}}
        raise AssertionError("Unexpected mutating or unrelated RPC: " + method)


def test_read_context_sandwiched_and_url_never_escapes():
    rpc = RPC()
    snap = context.capture(rpc)
    assert snap.context["title"] == "A Film"
    assert snap.context["tmdb"] == 98765432
    assert snap.context["duration"] == 6423.125
    assert snap.context["release"] == "A.Film.2008.mkv"
    assert "token" not in json.dumps(snap.context)
    assert rpc.calls[0] == rpc.calls[-1] == "Player.BobiState"


@pytest.mark.parametrize("field,value", [("native_instance", "22222222-2222-2222-2222-222222222222"),
    ("subtitle_intent", 3), ("file_identity", "other"), ("url_sha256", "c" * 64)])
def test_capture_rejects_identity_or_manual_intent_race(field, value):
    rpc = RPC()
    rpc.after_item = lambda: rpc.state["playback"].update({field: value})
    with pytest.raises(context.ContextUnavailable, match="PLAYBACK_CHANGED"):
        context.capture(rpc)


def test_pending_new_selection_rejected_before_metadata():
    rpc = RPC()
    rpc.state["selection_epoch"] = 5
    with pytest.raises(context.ContextUnavailable):
        context.capture(rpc)
    assert rpc.calls == ["Player.BobiState"]


def test_tagged_episode_uses_am6b_parent_contract_and_specials_zero():
    rpc = RPC()
    rpc.item.update(type="episode", showtitle="A Show", season=0, episode=3,
                    uniqueid={"tmdb": "1234", "imdb": "tt0999999"})
    snap = context.capture(rpc)
    assert snap.context["mode"] == "tv"
    assert snap.context["season"] == 0
    assert snap.context["tmdb"] == 1234 and snap.context["imdb"] == "tt0999999"
    rpc.item["uniqueid"]["tmdb.tv"] = "4567"
    assert context.capture(rpc).context["tmdb"] == 4567


def test_untagged_generic_episode_id_not_promoted():
    rpc = RPC()
    rpc.item.update(type="episode", showtitle="A Show", season=1, episode=3)
    rpc.state["playback"].update(request_id="", file_identity="")
    with pytest.raises(context.ContextUnavailable, match="MEDIA_CONTEXT_UNAVAILABLE"):
        context.capture(rpc)


@pytest.mark.parametrize("explicit", [{"tmdb.episode": "1234"}, {"imdb.episode": "tt0999999"}])
def test_explicit_episode_ids_never_promoted_even_in_tagged_playback(explicit):
    rpc = RPC()
    rpc.item.update(type="episode", showtitle="A Show", season=1, episode=3,
                    uniqueid=dict({"tmdb": "1234", "imdb": "tt0999999"}, **explicit))
    with pytest.raises(context.ContextUnavailable, match="MEDIA_CONTEXT_UNAVAILABLE"):
        context.capture(rpc)


@pytest.mark.parametrize("identity", ["nonsense", "bt:" + "d" * 40, "transport:" + "c" * 64])
def test_unbound_or_malformed_file_identity_does_not_inherit_parent_contract(identity):
    rpc = RPC()
    rpc.item.update(type="episode", showtitle="A Show", season=1, episode=3)
    rpc.state["playback"]["file_identity"] = identity
    with pytest.raises(context.ContextUnavailable, match="MEDIA_CONTEXT_UNAVAILABLE"):
        context.capture(rpc)


@pytest.mark.parametrize("changes", [{"year": 0}, {"originaltitle": "", "title": ""},
    {"type": "episode", "showtitle": "Show", "season": -1, "episode": 3}])
def test_missing_media_identity_not_guessed(changes):
    rpc = RPC()
    rpc.item.update(changes)
    with pytest.raises(context.ContextUnavailable, match="MEDIA_CONTEXT_UNAVAILABLE"):
        context.capture(rpc)


class Progress:
    def __init__(self):
        self.cancel = False
        self.closed = False

    def create(self, *args):
        pass

    def iscanceled(self):
        return self.cancel

    def close(self):
        self.closed = True


class Dialogs:
    def __init__(self, select=0, browse=True):
        self.selection, self.browse, self.messages = select, browse, []
        self.onselect = None
        self.onyes = None

    def ok(self, *args):
        self.messages.append(args)

    def select(self, *args):
        self.messages.append(args)
        if self.onselect:
            self.onselect()
        return self.selection

    def yesno(self, *args, **kwargs):
        self.messages.append(args)
        if self.onyes:
            self.onyes()
        return self.browse


class NoLock:
    def __init__(self, unused):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Provider:
    def __init__(self, unused):
        self.searches, self.downloads = 0, 0
        self.onsearch, self.ondownload = None, None

    def search(self, ctx, deadline, cancelled):
        self.searches += 1
        assert 0 < deadline - __import__("time").monotonic() <= 20
        if self.onsearch:
            self.onsearch()
        return [{"title": "A Film 2008 BluRay", "language": "zh-cn", "file_id": 7}]

    def download(self, candidate, ctx, deadline, cancelled, root):
        self.downloads += 1
        if self.ondownload:
            self.ondownload()
        return artifact(root)


def artifact(root):
    raw = "1\n00:00:10,000 --> 00:00:12,000\n中文测试\n".encode()
    digest = hashlib.sha256(raw).hexdigest()
    target = Path(root) / (digest[:32] + ".srt")
    target.write_bytes(raw)
    if os.name == "posix":
        target.chmod(0o444)
    return dict(path=str(target), sha256=digest, bytes=len(raw), language="zh-cn", sync_verified=False)


def harness(tmp_path, dialogs=None):
    rpc, dialogs, provider, calls, progresses = RPC(), dialogs or Dialogs(), Provider(None), [], []
    def factory():
        value = Progress()
        progresses.append(value)
        return value
    def run():
        return ui.run(rpc, dialogs, factory, types.SimpleNamespace(abortRequested=lambda: False),
                      calls.append, lambda unused: provider, str(tmp_path), str(tmp_path),
                      lock_factory=NoLock)
    return run, rpc, dialogs, provider, calls, progresses


def test_download_only_then_explicit_safe_browser(tmp_path):
    run, rpc, dialogs, provider, calls, progresses = harness(tmp_path)
    assert run() == "browser_opened"
    assert provider.downloads == 1
    assert calls == ["Action(BrowseSubtitle,FullscreenVideo)"]
    assert all(p.closed for p in progresses)
    names = [p.name for p in tmp_path.iterdir()]
    assert any("手动下载-A Film 2008-简中-待校准-" in n for n in names)
    assert "尚未应用" in dialogs.messages[-1][1]


def test_cancel_selection_never_downloads(tmp_path):
    run, rpc, dialogs, provider, calls, progresses = harness(tmp_path, Dialogs(select=-1))
    assert run() == "cancelled"
    assert provider.downloads == 0 and not calls


@pytest.mark.parametrize("stage", ["search", "select", "download", "confirm"])
def test_late_film_or_subtitle_change_never_applies(tmp_path, stage):
    run, rpc, dialogs, provider, calls, progresses = harness(tmp_path)
    change = lambda: rpc.state["playback"].update(subtitle_intent=3)
    if stage == "search":
        provider.onsearch = change
    elif stage == "select":
        dialogs.onselect = change
    elif stage == "download":
        provider.ondownload = change
    else:
        dialogs.onyes = change
    assert run() in {"cancelled", "downloaded"}
    assert not calls
    if stage in {"search", "select"}:
        assert provider.downloads == 0
    assert all(p.closed for p in progresses)


def test_download_can_be_saved_without_opening_browser(tmp_path):
    run, rpc, dialogs, provider, calls, progresses = harness(tmp_path, Dialogs(browse=False))
    assert run() == "downloaded"
    assert provider.downloads == 1 and not calls


def test_alias_preserves_original_and_deduplicates(tmp_path):
    result = artifact(tmp_path)
    ctx = dict(mode="movie", title="Title / [x]", year=2008)
    alias = ui.readable_alias(result, ctx, str(tmp_path))
    assert alias == ui.readable_alias(result, ctx, str(tmp_path))
    assert alias.read_bytes() == Path(result["path"]).read_bytes()
    assert alias.parent == tmp_path and "待校准" in alias.name


def test_alias_rejects_wrong_root_hash_and_false_sync_claim(tmp_path):
    result = artifact(tmp_path)
    ctx = dict(mode="movie", title="Title", year=2008)
    for changes in ({"path": str(tmp_path.parent / "wrong.srt")},
                    {"sha256": "0" * 64}, {"sync_verified": True}, {"bytes": True}):
        with pytest.raises(ValueError):
            ui.readable_alias(dict(result, **changes), ctx, str(tmp_path))


def test_bilingual_language_code_does_not_claim_simplified(tmp_path):
    result = dict(artifact(tmp_path), language="ze", bilingual=True)
    alias = ui.readable_alias(result, dict(mode="movie", title="Title", year=2008), str(tmp_path))
    assert "中文双语" in alias.name and "简中" not in alias.name and "双语双语" not in alias.name


def test_alias_filename_uses_utf8_byte_limit_for_four_byte_cjk(tmp_path):
    result = artifact(tmp_path)
    alias = ui.readable_alias(result, dict(mode="movie", title="\U00020000" * 64, year=2008), str(tmp_path))
    assert len(alias.name.encode("utf-8")) <= 240
    assert alias.name.endswith(".srt") and "待校准" in alias.name


def test_guard_cancelled_immediately_and_subtitle_read_is_throttled():
    rpc, progress = RPC(), Progress()
    snap = context.capture(rpc)
    tick = [10.0]
    guard = ui.Guard(snap, rpc, types.SimpleNamespace(abortRequested=lambda: False), progress, lambda: tick[0])
    assert not guard()
    count = len(rpc.calls)
    assert not guard() and len(rpc.calls) == count
    progress.cancel = True
    assert guard()


def test_no_playback_does_not_create_provider_or_browser(tmp_path):
    run, rpc, dialogs, provider, calls, progresses = harness(tmp_path)
    rpc.state["playback"] = None
    assert run() == "failed"
    assert not provider.searches and not calls and not progresses
    assert "先开始播放" in dialogs.messages[-1][1]


def test_account_epoch_change_invalidates_context_without_requiring_login():
    rpc = RPC()
    account = dict(account_id='', epoch=0, authenticated=False)
    snap = context.capture(rpc, lambda: dict(account))
    assert snap.current(rpc)
    account['epoch'] = 1
    assert not snap.current(rpc)


def test_account_change_during_metadata_read_is_rejected():
    rpc = RPC()
    account = dict(account_id='', epoch=0, authenticated=False)
    rpc.after_item = lambda: account.update(epoch=1)
    with pytest.raises(context.ContextUnavailable, match='PLAYBACK_CHANGED'):
        context.capture(rpc, lambda: dict(account))


def test_missing_personal_key_has_useful_message():
    assert 'API Key' in ui._failure(RuntimeError('PROVIDER_NOT_CONFIGURED'))
    assert '原生字幕接口' in ui._failure(RuntimeError('READ_ONLY_RPC_UNAVAILABLE'))


@pytest.mark.parametrize("remaining", [0, 4])
def test_fresh_remaining_quota_is_displayed_as_provider_report(remaining):
    message = ui._completion_message(Path("example.srt"), dict(remaining=remaining, cached=False))
    assert "来源返回剩余下载次数：{}（以网站为准）".format(remaining) in message
    assert "缓存命中" not in message


@pytest.mark.parametrize("remaining", [0, 4])
def test_cached_remaining_is_explicitly_historical(remaining):
    message = ui._completion_message(Path("example.srt"), dict(remaining=remaining, cached=True))
    assert "本地缓存命中，本次未消耗来源下载次数" in message
    assert "最近记录" in message and "可能已变化" in message


@pytest.mark.parametrize("remaining", [True, -1, "4", None])
def test_invalid_remaining_is_not_displayed(remaining):
    assert "剩余下载次数" not in ui._completion_message(Path("example.srt"), dict(remaining=remaining))


def test_two_independent_invocations_do_not_share_lock(tmp_path):
    with ui.InvocationLock(str(tmp_path)):
        with pytest.raises(ui.AlreadyRunning):
            with ui.InvocationLock(str(tmp_path)):
                pytest.fail("parallel invocation accepted")
    assert (tmp_path / "manual-source.lock").exists()
    with ui.InvocationLock(str(tmp_path)):
        pass
