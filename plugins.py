#!/usr/bin/env python3
"""Collect per-plugin download counts from GitHub release assets."""

import re

PLUGIN_ASSET_EXTENSIONS = (".tar.gz", ".tgz")
VENDOR_PREFIX = "headlamp-k8s-"
_VERSION_RE = re.compile(r"^(.*?)-v?\d[\w.\-]*$")


def parse_plugin_asset(filename):
    """Split a release asset filename into (plugin, version).

    Returns None when the filename is not a recognizable plugin archive.
    """
    stem = filename
    for ext in PLUGIN_ASSET_EXTENSIONS:
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break
    else:
        return None

    if stem.startswith(VENDOR_PREFIX):
        stem = stem[len(VENDOR_PREFIX):]

    match = _VERSION_RE.match(stem)
    if not match:
        return None
    plugin = match.group(1)
    if not plugin:
        return None
    return plugin, stem[len(plugin) + 1:]
