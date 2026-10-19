#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../lib" && pwd)
exec /usr/bin/python3 "$root/repair.py" "$@"
