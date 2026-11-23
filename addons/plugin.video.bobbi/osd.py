"""Bobbi-owned script entry; shipped with the updatable product addon."""
import sys


def main(argv=None):
    from lib.boot_gate import ready
    if not ready():
        return
    from lib.services.osd_playback import run, _notice
    params = {}
    for value in sys.argv[1:] if argv is None else argv:
        key, separator, argument = value.partition('=')
        if not separator or key not in ('bobbi_osd', 'token') or key in params:
            _notice('rejected')
            return
        params[key] = argument
    if params.get('bobbi_osd'):
        return run(**params)


if __name__ == '__main__':
    main()
