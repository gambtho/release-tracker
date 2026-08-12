#!/usr/bin/env python3
"""Collect per-plugin download counts from GitHub release assets."""

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys

from github_api import fetch_all_releases, parse_repo

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


TRUTHY = {"1", "true", "yes", "y"}


def read_plugins_csv(path="plugins.csv"):
    """Read plugin config.

    Returns {repo_full_name: set_of_charted_plugin_names}.

    The 'repo' column drives collection: every repo named in any row has all of
    its plugins collected, so a repo always appears as a key (possibly with an
    empty set). The 'plugin' + 'chart' columns drive display only -- a chart=0
    row is a no-op beyond declaring its repo, and its 'plugin' value is ignored.
    """
    charted_by_repo = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            repo = (row.get("repo") or "").strip()
            if not repo:
                continue
            charted = charted_by_repo.setdefault(repo, set())
            plugin = (row.get("plugin") or "").strip()
            chart = (row.get("chart") or "").strip().lower()
            if plugin and chart in TRUTHY:
                charted.add(plugin)
    return charted_by_repo
