#!/usr/bin/env python3
"""Manage daily snapshots and compute weekly download history."""

import argparse
import datetime as dt
import json
import os
import glob


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build site data: save snapshot, compute weekly history."
    )
    parser.add_argument(
        "--site-dir",
        required=True,
        help="Directory containing data.json (output from releases.py --json --output-dir).",
    )
    parser.add_argument(
        "--snapshots-dir",
        required=True,
        help="Directory with existing snapshots (from gh-pages checkout). New snapshot saved here too.",
    )
    parser.add_argument(
        "--plugin-snapshots-dir",
        default=None,
        help=(
            "Directory with existing plugin snapshots (from gh-pages checkout). "
            "New plugin snapshot saved here too. If omitted, the plugin track is "
            "skipped. plugins.json is read from --site-dir."
        ),
    )
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def save_snapshot(data_json, snapshots_dir):
    """Save today's data.json as a dated snapshot."""
    today = dt.date.today().isoformat()  # YYYY-MM-DD
    dest = os.path.join(snapshots_dir, "{}.json".format(today))
    os.makedirs(snapshots_dir, exist_ok=True)
    save_json(dest, data_json)
    return dest


def load_all_snapshots(snapshots_dir):
    """Load all snapshot files, return sorted list of (date_str, data) tuples."""
    pattern = os.path.join(snapshots_dir, "*.json")
    files = sorted(glob.glob(pattern))
    snapshots = []
    for f in files:
        date_str = os.path.basename(f).replace(".json", "")
        try:
            dt.date.fromisoformat(date_str)
        except ValueError:
            continue  # skip non-date files
        snapshots.append((date_str, load_json(f)))
    return snapshots


def monday_of(date_str):
    """Return the Monday (ISO week start) for a given YYYY-MM-DD date string."""
    d = dt.date.fromisoformat(date_str)
    return (d - dt.timedelta(days=d.weekday())).isoformat()


PLATFORM_METRICS = ["linux", "mac", "win"]
PLUGIN_METRICS = ["downloads"]


def build_platform_index(snapshot_data):
    """Index a platform snapshot as {(repo,): {tag: {metric: count}}}."""
    index = {}
    for repo_data in snapshot_data.get("repos", []):
        tags = {}
        for rel in repo_data.get("releases", []):
            tags[rel["tag"]] = {m: rel.get(m, 0) for m in PLATFORM_METRICS}
        index[(repo_data["repo"],)] = tags
    return index


def build_plugin_index(snapshot_data):
    """Index a plugin snapshot as {(repo, plugin): {tag: {metric: count}}}.

    Unlike the platform track, a tag is not a unique row key here: plugins.py
    appends one row per asset, and the same release tag can carry two assets
    for the same plugin. Sum same-tag rows rather than overwrite, or the
    earlier row's downloads would silently vanish from the weekly diff.
    """
    index = {}
    for repo_data in snapshot_data.get("repos", []):
        repo = repo_data["repo"]
        for plugin_data in repo_data.get("plugins", []):
            tags = {}
            for rel in plugin_data.get("releases", []):
                counts = tags.setdefault(rel["tag"], {m: 0 for m in PLUGIN_METRICS})
                for m in PLUGIN_METRICS:
                    counts[m] += rel.get(m, 0)
            index[(repo, plugin_data["plugin"])] = tags
    return index


def diff_snapshots(older_index, newer_index, metrics):
    """Per-key, per-metric deltas. Decreases are clamped to zero (D5):
    GitHub download counts can drop when an asset is re-uploaded."""
    result = {}
    zero = {m: 0 for m in metrics}
    for key in set(older_index) | set(newer_index):
        old_tags = older_index.get(key, {})
        new_tags = newer_index.get(key, {})
        delta = {m: 0 for m in metrics}
        for tag in set(old_tags) | set(new_tags):
            old = old_tags.get(tag, zero)
            new = new_tags.get(tag, zero)
            for m in metrics:
                d = new.get(m, 0) - old.get(m, 0)
                if d > 0:
                    delta[m] += d
        result[key] = delta
    return result


def compute_weekly_history(snapshots, index_fn, metrics):
    """Weekly deltas per key. Each consecutive pair's delta lands in the
    ISO week (Monday) of the NEWER snapshot; same-week deltas are summed."""
    if len(snapshots) < 2:
        return {}
    weekly = {}
    for i in range(1, len(snapshots)):
        _, older_data = snapshots[i - 1]
        newer_date, newer_data = snapshots[i]
        deltas = diff_snapshots(index_fn(older_data), index_fn(newer_data), metrics)
        week = monday_of(newer_date)
        for key, delta in deltas.items():
            weeks = weekly.setdefault(key, {})
            entry = weeks.setdefault(week, {m: 0 for m in metrics})
            for m in metrics:
                entry[m] += delta[m]
    return weekly


def build_history_json(weekly):
    """Platform track output: {"repos": [{"repo":..., "weeks":[...]}]}"""
    repos = []
    for key in sorted(weekly):
        weeks_dict = weekly[key]
        weeks = []
        for week in sorted(weeks_dict):
            entry = {"week": week}
            entry.update(weeks_dict[week])
            weeks.append(entry)
        repos.append({"repo": key[0], "weeks": weeks})
    return {"repos": repos}


def build_plugins_history_json(weekly):
    """Plugin track output, grouped by repo then plugin."""
    by_repo = {}
    for key in sorted(weekly):
        repo, plugin = key
        weeks_dict = weekly[key]
        weeks = []
        for week in sorted(weeks_dict):
            entry = {"week": week}
            entry.update(weeks_dict[week])
            weeks.append(entry)
        by_repo.setdefault(repo, []).append({"plugin": plugin, "weeks": weeks})
    return {"repos": [{"repo": r, "plugins": by_repo[r]} for r in sorted(by_repo)]}


def run_plugin_track(plugins_json, plugin_snapshots_dir, site_dir):
    """Snapshot today's plugins.json and rewrite plugins-history.json."""
    snap_path = save_snapshot(plugins_json, plugin_snapshots_dir)
    print("Saved plugin snapshot: {}".format(snap_path))

    snapshots = load_all_snapshots(plugin_snapshots_dir)
    print("Total plugin snapshots: {}".format(len(snapshots)))

    weekly = compute_weekly_history(snapshots, build_plugin_index, PLUGIN_METRICS)

    # Ensure every plugin seen today appears even with no weekly data yet,
    # mirroring the platform track so a brand-new plugin is not invisible.
    for repo_data in plugins_json.get("repos", []):
        repo = repo_data["repo"]
        for plugin_data in repo_data.get("plugins", []):
            weekly.setdefault((repo, plugin_data["plugin"]), {})

    history = build_plugins_history_json(weekly)
    history_path = os.path.join(site_dir, "plugins-history.json")
    save_json(history_path, history)
    print("Wrote {}".format(history_path))
    return history_path


def main():
    args = parse_args()

    data_path = os.path.join(args.site_dir, "data.json")
    if not os.path.exists(data_path):
        raise FileNotFoundError("Expected {} but not found.".format(data_path))

    data_json = load_json(data_path)

    # Save today's snapshot
    snap_path = save_snapshot(data_json, args.snapshots_dir)
    print("Saved snapshot: {}".format(snap_path))

    # Load all snapshots (including the one we just saved)
    snapshots = load_all_snapshots(args.snapshots_dir)
    print("Total snapshots: {}".format(len(snapshots)))

    # Compute weekly history
    weekly = compute_weekly_history(snapshots, build_platform_index, PLATFORM_METRICS)

    # Ensure all repos appear in history even if no weekly data yet
    for repo_data in data_json.get("repos", []):
        weekly.setdefault((repo_data["repo"],), {})

    history = build_history_json(weekly)

    history_path = os.path.join(args.site_dir, "history.json")
    save_json(history_path, history)
    print("Wrote {}".format(history_path))

    # --- Plugin track (independent; never affects the platform output above) ---
    if not args.plugin_snapshots_dir:
        print("No --plugin-snapshots-dir given; skipping plugin track.")
        return

    plugins_path = os.path.join(args.site_dir, "plugins.json")
    if not os.path.exists(plugins_path):
        print("No {}; skipping plugin track.".format(plugins_path))
        return

    run_plugin_track(load_json(plugins_path), args.plugin_snapshots_dir, args.site_dir)


if __name__ == "__main__":
    main()
