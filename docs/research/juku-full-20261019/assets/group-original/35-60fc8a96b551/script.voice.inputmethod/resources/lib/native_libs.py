"""Pick the bundled native build that matches the running user space.

One add-on zip carries both CoreELEC user spaces:

* ``linux_armv7l`` - Amlogic-ng and other 32-bit builds (CoreELEC 21 and older).
* ``linux_aarch64`` - Amlogic-no and other 64-bit builds (CoreELEC 22 and newer).

A 64-bit kernel can run either, so the kernel is not a reliable signal; the
width of the interpreter's pointers is. ctypes reports it directly and no
subprocess or platform query is needed.
"""
import ctypes as C
from pathlib import Path

DIRECTORIES = {8: 'linux_aarch64', 4: 'linux_armv7l'}

# glibc's GNU extension; ctypes does not export it. It puts the loaded object's
# own symbols ahead of everything already in the global scope.
RTLD_DEEPBIND = 0x8


def architecture():
    width = C.sizeof(C.c_void_p)
    try:
        return DIRECTORIES[width]
    except KeyError:
        raise RuntimeError('不支持的 CPU 字长：{} 位。'.format(width * 8)) from None


def load(path, global_=True):
    """Load a bundled library without letting the host process interpose it.

    The aarch64 sherpa-ncnn build uses the pre-C++11 std::string ABI. Wherever
    the host has already linked a new-ABI libstdc++ (Kodi does; a bare python3
    does not) the two define the same weak template symbols - std::regex
    internals among them - so a plain dlopen binds our calls to the host's
    copies, the object layouts disagree and the heap is corrupted.
    RTLD_DEEPBIND keeps each library on its own symbols. It falls back to the
    plain mode where the extension is unavailable.

    What actually keeps Kodi alive is that the engine runs in its own process
    (ncnn_worker.py); this flag is defence in depth for a host that happens to
    have libstdc++ preloaded.
    """
    mode = C.RTLD_GLOBAL if global_ else C.RTLD_LOCAL
    try:
        return C.CDLL(str(path), mode=mode | RTLD_DEEPBIND)
    except OSError:
        return C.CDLL(str(path), mode=mode)


def directory(addon_root, component):
    return Path(addon_root) / 'resources/native' / architecture() / component


def library(addon_root, component, names):
    """Return the first bundled ``names`` that exists, else the first candidate.

    The fallback keeps the error message meaningful: callers hand the path to
    ctypes, which reports the missing file it actually looked for.
    """
    folder = directory(addon_root, component)
    for name in names:
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return folder / names[0]
