"""Where MangaBinder keeps its cache and, by default, your downloads."""

import os
import sys


def cache_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "mangabinder")


def default_library():
    """~/Documents/MangaBinder, or ~/MangaBinder when there is no Documents folder."""
    home = os.path.expanduser("~")
    documents = os.path.join(home, "Documents")
    return os.path.join(documents if os.path.isdir(documents) else home, "MangaBinder")
