#!/usr/bin/env python3

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
import numpy as np
import matplotlib.pyplot as plt

API_BASE = "https://api.github.com"

PLATFORMS = ["linux", "mac", "win"]
PLATFORM_COLORS = {
    "linux": "#F5A623",
    "mac":   "#4A90D9",
    "win":   "#7ED321",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="GitHub release downloads by release, broken down by platform (Mac/Win/Linux)."
    )
    parser.add_argument(
        "--repo",
        action="append",
        dest="repos",
        help="Repository in OWNER/REPO format. Can be repeated.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON output.",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Write CSV output per repo.",
    )
    parser.add_argument(
        "-n",
        "--num-releases",
        type=int,
        default=6,
        dest="num_releases",
        help="Number of most recent releases to show (default: 6). Use 0 for all.",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Write JSON output to data.json in this directory instead of stdout.",
    )
    return parser.parse_args()


def read_repos_csv(path="repos.csv"):
    """Read repo list from a CSV file with a 'repo' column."""
    repos = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            repo = row["repo"].strip()
            if repo:
                repos.append(repo)
    return repos


def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-release-chart",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def http_get_json(url):
    req = urllib.request.Request(url, headers=github_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_repo(repo):
    if "/" not in repo:
        raise ValueError("Invalid repo '{}'. Expected OWNER/REPO.".format(repo))
    owner, name = repo.split("/", 1)
    owner = owner.strip()
    name = name.strip()
    if not owner or not name:
        raise ValueError("Invalid repo '{}'. Expected OWNER/REPO.".format(repo))
    return owner, name


def fetch_all_releases(owner, repo):
    releases = []
    page = 1

    while True:
        url = "{}/repos/{}/{}/releases?per_page=100&page={}".format(
            API_BASE, owner, repo, page
        )
        data = http_get_json(url)

        if not isinstance(data, list):
            raise RuntimeError(
                "Unexpected response for {}/{}: {}".format(owner, repo, type(data))
            )

        if not data:
            break

        releases.extend(data)

        if len(data) < 100:
            break

        page += 1
        time.sleep(0.1)

    return releases


def classify_platform(filename):
    """Classify an asset filename as mac, win, linux, or None (skip)."""
    name = filename.lower()

    # Skip checksums, signatures, provenance files, and helm charts
    if name.endswith((".txt", ".sig", ".prov", ".asc", ".sha256", ".md5")):
        return None
    # Skip standalone .tgz helm charts (not .tar.gz linux binaries)
    if name.endswith(".tgz") and not name.endswith(".tar.gz"):
        return None

    # Match by platform keyword in filename (most reliable for these repos)
    if re.search(r"[-_]mac[-_.]", name) or name.endswith(".dmg") or name.endswith(".pkg"):
        return "mac"
    if re.search(r"[-_]win[-_.]", name) or name.endswith(".exe") or name.endswith(".msi"):
        return "win"
    if (re.search(r"[-_]linux[-_.]", name)
            or name.endswith(".deb")
            or name.endswith(".rpm")
            or name.endswith(".appimage")
            or name.endswith(".snap")):
        return "linux"

    return None


def safe_filename(repo_full_name, suffix):
    return repo_full_name.replace("/", "_") + suffix


def summarize_repo(repo_full_name):
    owner, repo = parse_repo(repo_full_name)
    releases = fetch_all_releases(owner, repo)

    release_rows = []
    total = 0

    for release in releases:
        if release.get("draft"):
            continue

        published_at = release.get("published_at") or release.get("created_at")
        tag = release.get("tag_name", "")

        platform_downloads = {p: 0 for p in PLATFORMS}
        release_total = 0

        for asset in release.get("assets", []):
            count = asset.get("download_count", 0)
            platform = classify_platform(asset.get("name", ""))
            if platform is not None:
                platform_downloads[platform] += count
                release_total += count

        # Skip releases with zero classified downloads
        if release_total == 0:
            continue

        total += release_total

        release_rows.append(
            {
                "tag": tag,
                "name": release.get("name", ""),
                "published_at": published_at,
                "prerelease": bool(release.get("prerelease", False)),
                "download_total": release_total,
                "linux": platform_downloads["linux"],
                "mac": platform_downloads["mac"],
                "win": platform_downloads["win"],
            }
        )

    # Sort chronologically (oldest first) for chart display
    release_rows.sort(key=lambda r: r["published_at"] or "")

    return {
        "repo": repo_full_name,
        "approx_all_time_release_downloads": total,
        "releases": release_rows,
    }


def write_csv(summary):
    repo = summary["repo"]
    filename = safe_filename(repo, "_downloads_by_release.csv")

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["repo", "tag", "published_at", "prerelease", "linux", "mac", "win", "total"])
        for row in summary["releases"]:
            writer.writerow([
                repo,
                row["tag"],
                row["published_at"],
                row["prerelease"],
                row["linux"],
                row["mac"],
                row["win"],
                row["download_total"],
            ])

    return filename


def make_chart(summary):
    repo = summary["repo"]
    rows = summary["releases"]

    if not rows:
        return None

    tags = [r["tag"] for r in rows]
    linux_vals = np.array([r["linux"] for r in rows])
    mac_vals = np.array([r["mac"] for r in rows])
    win_vals = np.array([r["win"] for r in rows])

    x = np.arange(len(tags))
    width = 0.7

    fig, ax = plt.subplots(figsize=(max(12, len(tags) * 0.8), 7))

    ax.bar(x, linux_vals, width, label="Linux", color=PLATFORM_COLORS["linux"])
    ax.bar(x, mac_vals, width, bottom=linux_vals, label="Mac", color=PLATFORM_COLORS["mac"])
    ax.bar(x, win_vals, width, bottom=linux_vals + mac_vals, label="Win", color=PLATFORM_COLORS["win"])

    ax.set_title("Downloads by Release (Mac / Win / Linux)\n{}".format(repo))
    ax.set_xlabel("Release")
    ax.set_ylabel("Downloads")
    ax.set_xticks(x)
    ax.set_xticklabels(tags, rotation=45, ha="right", fontsize=8)
    ax.legend()
    fig.tight_layout()

    filename = safe_filename(repo, "_downloads_by_release.png")
    fig.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return filename


def print_text_report(summary):
    print("=" * 90)
    print(summary["repo"])
    print("=" * 90)
    print(
        "Approx all-time release downloads: {:,}".format(
            summary["approx_all_time_release_downloads"]
        )
    )
    print()
    print("{:<25} {:>10} {:>10} {:>10} {:>12}".format(
        "Release", "Linux", "Mac", "Win", "Total"
    ))
    print("-" * 70)
    for row in summary["releases"]:
        tag = row["tag"]
        if len(tag) > 24:
            tag = tag[:21] + "..."
        pre = " *" if row["prerelease"] else ""
        print("{:<25} {:>10,} {:>10,} {:>10,} {:>12,}{}".format(
            tag, row["linux"], row["mac"], row["win"], row["download_total"], pre
        ))
    print()
    print("  * = prerelease")
    print()


def main():
    args = parse_args()

    # Repo resolution: --repo flags > repos.csv > error
    if args.repos:
        repos = args.repos
    elif os.path.exists("repos.csv"):
        repos = read_repos_csv("repos.csv")
        if not repos:
            print("Error: repos.csv is empty.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Error: No repos specified. Use --repo or create a repos.csv file.", file=sys.stderr)
        sys.exit(1)

    summaries = []
    for repo in repos:
        summaries.append(summarize_repo(repo))

    # Limit to the N most recent releases (they are sorted oldest-first)
    if args.num_releases > 0:
        for summary in summaries:
            summary["releases"] = summary["releases"][-args.num_releases:]

    if args.json:
        output = {
            "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "repos": summaries,
        }
        json_str = json.dumps(output, indent=2)

        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            out_path = os.path.join(args.output_dir, "data.json")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(json_str)
            print("Wrote {}".format(out_path))
        else:
            print(json_str)
        return

    chart_files = []
    csv_files = []

    for summary in summaries:
        print_text_report(summary)
        chart_file = make_chart(summary)
        if chart_file:
            chart_files.append(chart_file)

        if args.csv:
            csv_file = write_csv(summary)
            csv_files.append(csv_file)

    if chart_files:
        print("Generated chart files:")
        for path in chart_files:
            print("  {}".format(path))

    if csv_files:
        print()
        print("Generated CSV files:")
        for path in csv_files:
            print("  {}".format(path))


if __name__ == "__main__":
    main()
