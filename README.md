# Release Tracker

A GitHub Pages dashboard that tracks download statistics for GitHub releases, broken down by platform (Linux, Mac, Windows) with weekly download trends computed from daily snapshots.

## Dashboard

The dashboard is deployed automatically to GitHub Pages and updated daily at 06:00 UTC.

**[View the dashboard](https://gambtho.github.io/release-tracker/)**

## Tracked Repos

Repos are configured in [`repos.csv`](repos.csv):

| Repo |
|------|
| [Azure/aks-desktop](https://github.com/Azure/aks-desktop) |
| [kubernetes-sigs/headlamp](https://github.com/kubernetes-sigs/headlamp) |

To add or remove repos, edit `repos.csv` and push to `main`. The next workflow run will pick up the changes.

## Tracked Plugins

Plugin repos are configured in [`plugins.csv`](plugins.csv):

```csv
repo,plugin,chart
headlamp-k8s/plugins,ai-assistant,1
```

The two halves of a row do different jobs:

| Column | Effect |
|--------|--------|
| `repo` | **Drives collection.** Any repo named in any row has *all* of its plugins collected and snapshotted daily, regardless of the row's other values. |
| `plugin` | **Display only.** Names the plugin the `chart` flag applies to. Ignored when `chart=0`. |
| `chart` | **Display only.** `1` gives that plugin its own card on the dashboard; `0` does not. |

Consequences worth knowing:

- To collect a repo's download history without charting anything from it yet, add a single row with `chart=0`. History accumulates from that day forward, so flipping the flag to `1` later gives you a chart with real trend data instead of one starting from zero.
- A `plugin` value that names a plugin not present in the repo is reported as a warning and skipped — it is not a fatal error.

To add or remove plugin repos, edit `plugins.csv` and push to `main`. The next workflow run will pick up the changes.

## How It Works

1. **`releases.py`** fetches release data from the GitHub API and classifies assets by platform based on filename patterns (`.dmg`, `.exe`, `.AppImage`, `.deb`, `.tar.gz`, etc.). Assets that can't be classified (checksums, helm charts) are skipped.

2. **`plugins.py`** runs a parallel track for Headlamp plugin repos configured in [`plugins.csv`](plugins.csv). Plugin releases have no Linux/Mac/Win dimension and one repo holds many plugins, so downloads are attributed to a plugin from the asset filename (`[headlamp-k8s-]<plugin>-<version>.tar.gz`) rather than the release tag. Download counts for *every* plugin in a configured repo are collected, so any of them can be charted later with history already accumulated.

3. **`build_site.py`** saves a daily snapshot of both tracks and diffs consecutive snapshots to compute weekly download deltas — per repo and platform for the release track, per plugin for the plugin track.

4. **`site/index.html`** is a self-contained dark-themed dashboard that renders the data as interactive Chart.js stacked bar charts -- downloads by release, per week, and per month -- with one card per tracked repo plus one card per plugin flagged for charting.

5. A **GitHub Action** (`.github/workflows/update-site.yml`) runs this pipeline daily and deploys the result to the `gh-pages` branch.

## Local Usage

### Generate a text report

```bash
pip install -r requirements.txt
python releases.py
```

### Generate JSON output

```bash
python releases.py --json --output-dir _site/
```

### Run the full pipeline locally

```bash
mkdir -p _site _snapshots _plugin_snapshots

# Fetch release data (platform track)
python releases.py --json --output-dir _site/

# Fetch plugin release data (plugin track)
python plugins.py --json --output-dir _site/ --num-releases 0

# Build snapshots and history for both tracks
python build_site.py --site-dir _site/ --snapshots-dir _snapshots/ \
  --plugin-snapshots-dir _plugin_snapshots/

# Copy the dashboard
cp site/index.html _site/index.html

# Serve locally
python -m http.server 8080 --directory _site/
# Open http://localhost:8080
```

On a first local run there is only one snapshot per track, so no weekly deltas can be computed and every card opens on **By Release** with the By Week / By Month buttons hidden. That is expected — the trend views appear once at least two days of snapshots exist.

Set `GITHUB_TOKEN` in your environment to raise the GitHub API rate limit from 60 to 5000 requests per hour:

```bash
export GITHUB_TOKEN=$(gh auth token)
```

### Options

| Flag | Description |
|------|-------------|
| `--repo OWNER/NAME` | Track a specific repo (can be repeated, overrides `repos.csv`) |
| `--json` | Output JSON instead of text/charts |
| `--output-dir DIR` | Write `data.json` to this directory |
| `--num-releases N` | Limit to N most recent releases per repo (0 = all, default 6) |

## Project Structure

```
repos.csv                          # Repos to track (platform downloads)
plugins.csv                        # Plugin repos to track + which to chart
releases.py                        # Fetch + classify release downloads by platform
plugins.py                         # Fetch + attribute plugin downloads by asset filename
github_api.py                      # Shared GitHub REST helpers
build_site.py                      # Daily snapshots + weekly history (both tracks)
site/index.html                    # Dashboard (Chart.js, inline CSS/JS)
tests/                             # pytest suite
.github/workflows/update-site.yml  # Daily cron + deploy to gh-pages
requirements.txt                   # Python dependencies
```

## Tests

`pytest` is listed in `requirements.txt`. After `pip install -r requirements.txt`:

```bash
pytest tests/ -v
```

The suite covers plugin attribution from asset filenames, weekly-delta computation (including the guard against decreasing download counts when an asset is re-uploaded), and a regression check that the shared snapshot-diff logic produces byte-identical output for the platform track.
