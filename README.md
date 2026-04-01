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

## How It Works

1. **`releases.py`** fetches release data from the GitHub API and classifies assets by platform based on filename patterns (`.dmg`, `.exe`, `.AppImage`, `.deb`, `.tar.gz`, etc.). Assets that can't be classified (checksums, helm charts) are skipped.

2. **`build_site.py`** saves a daily snapshot of the release data and diffs consecutive snapshots to compute weekly download deltas per repo and platform.

3. **`site/index.html`** is a self-contained dark-themed dashboard that renders the data as interactive Chart.js stacked bar charts -- downloads by release and downloads per week.

4. A **GitHub Action** (`.github/workflows/update-site.yml`) runs this pipeline daily and deploys the result to the `gh-pages` branch.

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
mkdir -p _site _snapshots

# Fetch release data
python releases.py --json --output-dir _site/

# Build snapshots and history
python build_site.py --site-dir _site/ --snapshots-dir _snapshots/

# Copy the dashboard
cp site/index.html _site/index.html

# Serve locally
python -m http.server 8080 --directory _site/
# Open http://localhost:8080
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
repos.csv                          # Repos to track
releases.py                        # Fetch + classify release downloads
build_site.py                      # Daily snapshots + weekly history
site/index.html                    # Dashboard (Chart.js, inline CSS/JS)
.github/workflows/update-site.yml  # Daily cron + deploy to gh-pages
requirements.txt                   # Python dependencies
```
