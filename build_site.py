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


def build_repo_index(snapshot_data):
    """Build a dict mapping repo -> {tag -> {linux, mac, win}} from a snapshot."""
    index = {}
    for repo_data in snapshot_data.get("repos", []):
        repo_name = repo_data["repo"]
        tags = {}
        for rel in repo_data.get("releases", []):
            tags[rel["tag"]] = {
                "linux": rel.get("linux", 0),
                "mac": rel.get("mac", 0),
                "win": rel.get("win", 0),
            }
        index[repo_name] = tags
    return index


def diff_snapshots(older_index, newer_index):
    """Compute per-repo, per-platform download deltas between two snapshot indexes."""
    result = {}
    all_repos = set(older_index.keys()) | set(newer_index.keys())
    for repo in all_repos:
        old_tags = older_index.get(repo, {})
        new_tags = newer_index.get(repo, {})
        delta = {"linux": 0, "mac": 0, "win": 0}
        all_tag_names = set(old_tags.keys()) | set(new_tags.keys())
        for tag in all_tag_names:
            old = old_tags.get(tag, {"linux": 0, "mac": 0, "win": 0})
            new = new_tags.get(tag, {"linux": 0, "mac": 0, "win": 0})
            for p in ("linux", "mac", "win"):
                d = new[p] - old[p]
                if d > 0:
                    delta[p] += d
        result[repo] = delta
    return result


def compute_weekly_history(snapshots):
    """Given sorted snapshots, compute weekly download deltas per repo per platform.

    Strategy: for each consecutive pair of snapshots, compute the delta and
    assign it to the week (Monday) of the newer snapshot. If multiple deltas
    land in the same week, they are summed.
    """
    if len(snapshots) < 2:
        return {}

    # repo -> week -> {linux, mac, win}
    weekly = {}

    for i in range(1, len(snapshots)):
        older_date, older_data = snapshots[i - 1]
        newer_date, newer_data = snapshots[i]

        older_index = build_repo_index(older_data)
        newer_index = build_repo_index(newer_data)
        deltas = diff_snapshots(older_index, newer_index)

        week = monday_of(newer_date)

        for repo, delta in deltas.items():
            if repo not in weekly:
                weekly[repo] = {}
            if week not in weekly[repo]:
                weekly[repo][week] = {"linux": 0, "mac": 0, "win": 0}
            for p in ("linux", "mac", "win"):
                weekly[repo][week][p] += delta[p]

    return weekly


def build_history_json(weekly):
    """Convert the weekly dict into the history.json structure."""
    repos = []
    for repo_name in sorted(weekly.keys()):
        weeks_dict = weekly[repo_name]
        weeks = []
        for week in sorted(weeks_dict.keys()):
            entry = {"week": week}
            entry.update(weeks_dict[week])
            weeks.append(entry)
        repos.append({"repo": repo_name, "weeks": weeks})
    return {"repos": repos}


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
    weekly = compute_weekly_history(snapshots)
    history = build_history_json(weekly)

    history_path = os.path.join(args.site_dir, "history.json")
    save_json(history_path, history)
    print("Wrote {}".format(history_path))


if __name__ == "__main__":
    main()
