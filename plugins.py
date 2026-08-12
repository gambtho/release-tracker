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


def summarize_plugin_repo(repo_full_name, charted):
    """Collect every plugin in one repo, keyed by asset filename.

    Returns one entry of the plugins.json 'repos' array. Plugins are sorted by
    name; each plugin's releases are sorted oldest-first, matching releases.py.
    Unlike releases.py, zero-download releases are kept (D2) because a newly
    published plugin at 0 downloads is real information.
    """
    owner, repo = parse_repo(repo_full_name)
    releases = fetch_all_releases(owner, repo)

    rows_by_plugin = {}
    unparseable = 0

    for release in releases:
        if release.get("draft"):
            continue

        tag = release.get("tag_name", "")
        published_at = release.get("published_at") or release.get("created_at")
        prerelease = bool(release.get("prerelease", False))

        for asset in release.get("assets", []):
            parsed = parse_plugin_asset(asset.get("name", ""))
            if parsed is None:
                unparseable += 1
                continue
            plugin, version = parsed
            # Keyed by tag: the same asset filename legitimately appears under
            # two different tags (e.g. app-catalog-0.1.3.tgz in v0.1.3 and
            # v0.1.4) with different counts. Both are distinct release rows.
            rows_by_plugin.setdefault(plugin, []).append(
                {
                    "tag": tag,
                    "version": version,
                    "published_at": published_at,
                    "prerelease": prerelease,
                    "downloads": asset.get("download_count", 0),
                }
            )

    if unparseable:
        print(
            "Warning: {} unparseable asset name(s) in {} were skipped.".format(
                unparseable, repo_full_name
            ),
            file=sys.stderr,
        )

    for name in sorted(charted):
        if name not in rows_by_plugin:
            print(
                "Warning: plugins.csv lists plugin '{}' for {}, "
                "which was not found in that repo. Skipping.".format(
                    name, repo_full_name
                ),
                file=sys.stderr,
            )

    plugin_entries = []
    for plugin in sorted(rows_by_plugin):
        rows = rows_by_plugin[plugin]
        rows.sort(key=lambda r: r["published_at"] or "")
        plugin_entries.append(
            {
                "plugin": plugin,
                "chart": plugin in charted,
                # All-time total is over every release, before any
                # --num-releases trim (which happens later, in main()).
                "approx_all_time_downloads": sum(r["downloads"] for r in rows),
                "releases": rows,
            }
        )

    return {"repo": repo_full_name, "plugins": plugin_entries}


def parse_args():
    parser = argparse.ArgumentParser(
        description="GitHub release downloads per Headlamp plugin."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON output.",
    )
    parser.add_argument(
        "-n",
        "--num-releases",
        type=int,
        default=6,
        dest="num_releases",
        help="Number of most recent releases to show per plugin "
             "(default: 6). Use 0 for all.",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Write JSON output to plugins.json in this directory "
             "instead of stdout.",
    )
    return parser.parse_args()


def print_text_report(summary):
    print("=" * 90)
    print(summary["repo"])
    print("=" * 90)
    for entry in summary["plugins"]:
        marker = " [charted]" if entry["chart"] else ""
        print()
        print("{}{} - approx all-time downloads: {:,}".format(
            entry["plugin"], marker, entry["approx_all_time_downloads"]
        ))
        print("  {:<32} {:>12}".format("Release", "Downloads"))
        print("  " + "-" * 46)
        for row in entry["releases"]:
            tag = row["tag"]
            if len(tag) > 31:
                tag = tag[:28] + "..."
            pre = " *" if row["prerelease"] else ""
            print("  {:<32} {:>12,}{}".format(tag, row["downloads"], pre))
    print()
    print("  * = prerelease")
    print()


def main():
    args = parse_args()

    if not os.path.exists("plugins.csv"):
        print(
            "No plugins.csv found; skipping plugin download collection.",
            file=sys.stderr,
        )
        sys.exit(0)

    charted_by_repo = read_plugins_csv("plugins.csv")
    if not charted_by_repo:
        print("No repos listed in plugins.csv; nothing to do.", file=sys.stderr)
        sys.exit(0)

    summaries = [
        summarize_plugin_repo(repo, charted_by_repo[repo])
        for repo in charted_by_repo
    ]

    # D4: trim per plugin, not per repo -- prometheus has many more releases
    # than the other plugins and would otherwise crowd them out of a shared
    # repo-wide window. Releases are oldest-first, so this keeps the last N.
    if args.num_releases > 0:
        for summary in summaries:
            for entry in summary["plugins"]:
                entry["releases"] = entry["releases"][-args.num_releases:]

    if args.json:
        output = {
            "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "repos": summaries,
        }
        json_str = json.dumps(output, indent=2)

        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            out_path = os.path.join(args.output_dir, "plugins.json")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(json_str)
            print("Wrote {}".format(out_path))
        else:
            print(json_str)
        return

    for summary in summaries:
        print_text_report(summary)


if __name__ == "__main__":
    main()
