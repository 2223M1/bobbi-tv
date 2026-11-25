# Modified for bobbi portability and explicit credentials, 2026-10-19.
"""Manual source picker: download only, then explicit native-safe file browsing."""
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from resources.lib.context import ContextUnavailable, capture, text
from bobbi_platform.instance_lock import InstanceLock


OPERATION_SECONDS = 20.0
MAX_BYTES = 8 * 1024 * 1024
HEADING = "找中文字幕 · OpenSubtitles"


def _tr(msg_id, zh_text, en_text):
    try:
        from bobbi_platform.i18n import tr
        return tr(msg_id, zh_text, en_text, addon_id="script.bobbi.opensubtitles")
    except Exception:
        return zh_text


def _heading():
    return _tr(32002, HEADING, "Find Subtitles · OpenSubtitles")


class AlreadyRunning(RuntimeError):
    pass


def _private_directory(path):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("PRIVATE_DIRECTORY_REQUIRED")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if (not stat.S_ISDIR(info.st_mode)
            or (os.name == "posix" and (info.st_mode & 0o022 or info.st_uid != os.getuid()))):
        raise ValueError("PRIVATE_DIRECTORY_REQUIRED")
    return path


class InvocationLock:
    """The lock inode is never unlinked: all Kodi interpreters share one lock."""
    def __init__(self, directory):
        self.directory, self.lock = directory, None

    def __enter__(self):
        directory = _private_directory(self.directory)
        path = directory / "manual-source.lock"
        self.lock = InstanceLock(path)
        try:
            self.lock.acquire()
            info = os.fstat(self.lock.fd)
            if (not stat.S_ISREG(info.st_mode) or
                    (os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077))):
                raise ValueError("PRIVATE_LOCK_REQUIRED")
        except (BlockingIOError, PermissionError) as error:
            self.lock.close()
            raise AlreadyRunning('ALREADY_RUNNING') from error
        except BaseException:
            self.lock.close()
            raise
        return self

    def __exit__(self, *unused):
        if self.lock is not None:
            self.lock.close()
            self.lock = None


class Guard:
    def __init__(self, snapshot, rpc, monitor, progress, clock=time.monotonic, current=lambda: True):
        self.snapshot, self.rpc, self.monitor, self.progress = snapshot, rpc, monitor, progress
        self.clock, self.next_read, self.stopped = clock, 0.0, False
        self.current = current

    def __call__(self, force=False):
        if self.stopped:
            return True
        if self.current() is not True or self.monitor.abortRequested() or (self.progress and self.progress.iscanceled()):
            self.stopped = True
        elif force or self.clock() >= self.next_read:
            self.next_read = self.clock() + 0.25
            self.stopped = not self.snapshot.current(self.rpc)
        return self.stopped


def readable_alias(result, context, root, cancelled=lambda: False):
    """Publish a human-readable immutable copy; original hash object is retained."""
    if cancelled():
        raise ContextUnavailable("PLAYBACK_CHANGED")
    directory = _private_directory(root)
    source = Path(result.get("path", ""))
    digest, size = result.get("sha256"), result.get("bytes")
    if (source.parent != directory or source.suffix != ".srt"
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or type(size) is not int or not 0 < size <= MAX_BYTES
            or result.get("sync_verified") is not False):
        raise ValueError("DOWNLOAD_DESCRIPTOR_INVALID")
    info = source.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size != size or info.st_dev != directory.stat().st_dev
            or (os.name == "posix" and (info.st_mode & 0o222 or info.st_uid != os.getuid()))):
        raise ValueError("DOWNLOAD_FILE_INVALID")
    with source.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("DOWNLOAD_HASH_CHANGED")
    title = text(context.get("showtitle") or context.get("title"), 64)
    title = re.sub(r"[^\w .()（）-]", "_", title).strip(" .") or "影片"
    episode = " S{:02d}E{:02d}".format(context["season"], context["episode"]) if context.get("mode") == "tv" else ""
    year = " {}".format(context["year"]) if context.get("year") else ""
    language = {"zh-tw": "繁中", "zh-Hant": "繁中", "zh-cn": "简中", "ze": "中文双语"}.get(result.get("language"), "中文")
    if result.get("bilingual") is True and not language.endswith("双语"):
        language += "双语"
    prefix = "手动下载-"
    suffix = "{}{}-{}-待校准-{}.srt".format(year, episode, language, digest[:8])
    title_budget = 240 - len((prefix + suffix).encode("utf-8"))
    title = title.encode("utf-8")[:title_budget].decode("utf-8", "ignore").rstrip(" .") or "影片"
    name = prefix + title + suffix
    target = directory / name
    if target.exists() or target.is_symlink():
        info = target.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_size != size
                or (os.name == "posix" and (info.st_mode & 0o222 or info.st_uid != os.getuid()))
                or hashlib.sha256(target.read_bytes()).hexdigest() != digest):
            raise ValueError("ALIAS_COLLISION")
        return target
    # Native browsing refuses >512 entries. Leave room for its staged copies.
    for count, unused in enumerate(directory.iterdir(), 1):
        if count >= 480:
            raise ValueError("BROWSER_CAPACITY")
    fd, temporary = tempfile.mkstemp(prefix=".manual-source-", dir=str(directory))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444)
        if cancelled():
            raise ContextUnavailable("PLAYBACK_CHANGED")
        if os.name == 'nt':
            os.rename(temporary, target)  # Windows rename never overwrites.
        else:
            os.link(temporary, target)  # Atomic no-replace.
    finally:
        if os.path.exists(temporary):
            if os.name == 'nt':
                os.chmod(temporary, 0o600)
            os.unlink(temporary)
    return target


def _label(candidate):
    label = text(candidate.get("title") or candidate.get("label") or candidate.get("release"), 150)
    label = label.replace("[", "［").replace("]", "］") or _tr(32003, "中文字幕候选", "Chinese Subtitle Candidate")
    language = text(candidate.get("language"), 20)
    return _tr(32004, "%s  ·  %s  ·  待校准", "%s  ·  %s  ·  Sync unverified") % (
        label, language or _tr(32005, "中文", "Chinese")
    )


def _failure(error):
    reason = str(getattr(error, "reason", str(error)))
    if reason == 'PROVIDER_NOT_CONFIGURED':
        return _tr(32006, '请先在“找中文字幕”插件设置中填写 OpenSubtitles API Key。当前播放不受影响。',
                   'Enter your OpenSubtitles API Key in the add-on settings first. Current playback is unaffected.')
    if reason == 'READ_ONLY_RPC_UNAVAILABLE':
        return _tr(32007, '当前播放器不支持此字幕功能，原字幕和播放保留。',
                   'Current player does not support this subtitle action; existing subtitles and playback are kept.')
    if reason in {"NO_ACTIVE_PLAYBACK", "DURATION_UNAVAILABLE"}:
        return _tr(32008, "请先开始播放影片，待画面出现后再找字幕。",
                   "Start playing a video first and wait for video output before searching subtitles.")
    if reason in {"PLAYBACK_CHANGED", "CANCELLED", "CANCELLED_OR_DEADLINE"}:
        return _tr(32009, "操作已取消或播放选择已变化，未加载字幕。",
                   "Action cancelled or playback changed; no subtitle was loaded.")
    if reason in {"MEDIA_CONTEXT_UNAVAILABLE", "CONTEXT_INVALID"}:
        return _tr(32010, "影片资料不足，无法查找对应字幕。",
                   "Insufficient media metadata to search for matching subtitles.")
    if "LIMIT" in reason or "QUOTA" in reason or "429" in reason:
        return _tr(32011, "字幕下载或查询次数已达限制，请稍后重试。原字幕保留。",
                   "Subtitle download or search quota reached; retry later. Existing subtitles are kept.")
    if "TIMEOUT" in reason or "DEADLINE" in reason:
        return _tr(32012, "字幕服务响应超时，请稍后重试。原字幕保留。",
                   "Subtitle service timed out; retry later. Existing subtitles are kept.")
    if "AUTH" in reason:
        return _tr(32013, "字幕服务登录验证失败，请检查插件设置。原字幕保留。",
                   "Subtitle service authentication failed; check add-on settings. Existing subtitles are kept.")
    return _tr(32014, "字幕操作未完成，请稍后重试。原字幕和播放保留。",
               "Subtitle action did not complete; retry later. Existing subtitles and playback are kept.")


def _completion_message(alias, result):
    lines = [_tr(32015, "字幕已下载，需手动加载。时间可能需要调整。",
                 "Subtitle downloaded; load it manually. Timing adjustment may be needed.")]
    cached = result.get("cached") is True
    if cached:
        lines.append(_tr(32016, "使用已下载文件，不占下载次数。",
                         "Reused cached file without consuming download quota."))
    remaining = result.get("remaining")
    if type(remaining) is int and remaining >= 0:
        if cached:
            lines.append(_tr(32017, "上次记录还可下载 %d 次，以网站为准。",
                             "Last recorded remaining downloads: %d (subject to website).") % remaining)
        else:
            lines.append(_tr(32018, "还可下载 %d 次，以网站为准。",
                             "Remaining downloads: %d (subject to website).") % remaining)
    lines.extend([
        _tr(32019, "点击“浏览字幕”，在本地缓存中选择以下文件",
            "Select \"Browse Subtitles\" and pick the following file in local cache"),
        alias.name,
    ])
    return "\n".join(lines)


def run(rpc, dialogs, progress_factory, monitor, builtin, provider_factory,
        state_directory, root, clock=time.monotonic, lock_factory=InvocationLock,
        account_reader=None, current=lambda: True):
    """Only this user-driven script displays UI; provider never applies subtitles."""
    heading = _heading()
    try:
        if current() is not True:
            return 'cancelled'
        with lock_factory(state_directory):
            snapshot = capture(rpc, account_reader)
            provider = provider_factory(state_directory)
            progress = progress_factory()
            progress.create(heading, _tr(32020, "正在搜索当前影片的中文字幕；可返回取消。",
                                         "Searching Chinese subtitles for current video; press Back to cancel."))
            guard = Guard(snapshot, rpc, monitor, progress, clock, current)
            try:
                choices = provider.search(snapshot.context, clock() + OPERATION_SECONDS, guard)
                if guard(force=True):
                    return "cancelled"
            finally:
                progress.close()
            if not isinstance(choices, list) or len(choices) > 20 or any(not isinstance(c, dict) for c in choices):
                raise ValueError("PROVIDER_CANDIDATES_INVALID")
            if not choices:
                dialogs.ok(heading, _tr(32021, "未找到中文字幕，原字幕保留。",
                                        "No Chinese subtitles found; existing subtitles are kept."))
                return "empty"
            selected = dialogs.select(
                heading + _tr(32022, " · 选择后下载", " · Select to Download"),
                [_label(c) for c in choices],
            )
            if type(selected) is not int or not 0 <= selected < len(choices):
                return "cancelled"
            if current() is not True or not snapshot.current(rpc) or monitor.abortRequested():
                return "cancelled"
            progress = progress_factory()
            progress.create(heading, _tr(32023, "正在下载所选字幕；仅保存到本地，不自动应用。",
                                         "Downloading selected subtitle; saved locally only and never auto-applied."))
            guard = Guard(snapshot, rpc, monitor, progress, clock, current)
            try:
                result = provider.download(choices[selected], snapshot.context,
                                           clock() + OPERATION_SECONDS, guard, root)
                if guard(force=True):
                    return "cancelled"
                alias = readable_alias(result, snapshot.context, root, lambda: guard(force=True))
                if guard(force=True):
                    return "cancelled"
            finally:
                progress.close()
            message = _completion_message(alias, result)
            browse = dialogs.yesno(
                heading,
                message,
                nolabel=_tr(32024, "稍后", "Later"),
                yeslabel=_tr(32025, "浏览字幕", "Browse Subtitles"),
            )
            if browse and current() is True and snapshot.current(rpc) and not monitor.abortRequested():
                # This opens the patched native browser. The user chooses a
                # file there; ReserveBobiSubtitle + native actor own application.
                builtin("Action(BrowseSubtitle,FullscreenVideo)")
                return "browser_opened"
            return "downloaded"
    except AlreadyRunning:
        dialogs.ok(heading, _tr(32026, "已有字幕搜索窗口，请先完成或取消上次操作。",
                                "Another subtitle search window is active; finish or cancel it first."))
        return "busy"
    except (ContextUnavailable, RuntimeError, ValueError, TypeError, OSError) as error:
        if not monitor.abortRequested():
            dialogs.ok(heading, _failure(error))
        return "failed"
