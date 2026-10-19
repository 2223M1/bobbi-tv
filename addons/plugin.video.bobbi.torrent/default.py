"""Each invocation has its own request; importing the addon starts nothing."""
import os
import sys

# The plugin entry root is on sys.path; its exported module lives in lib.
# Only this component's own immutable directory is added, never another addon.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from bobbi_torrent.entry import main

if __name__ == "__main__":
    main()
