# GitHub Release Downloads Dashboard -- Design Spec

**Date:** 2026-04-01
**Status:** Approved

## Goal

Convert the `githubreports` project into a GitHub Pages site that displays a polished, leadership-facing dark dashboard showing GitHub release download stats by release, broken down by platform (Mac/Win/Linux). A GitHub Action updates the data daily.

## Repo Configuration

### File: `repos.csv`

A simple CSV file with a single `repo` column, one row per repository to track:

```csv
repo
Azure/aks-desktop
kubernetes-sigs/headlamp
```

To add or remove repos from the dashboard, edit this file. The script and action both read from it. The hardcoded `DEFAULT_REPOS` list in `releases.py` is replaced by reading this file.

When `repos.csv` is present, the script uses it. The `--repo` CLI flag still works and takes precedence (useful for one-off local runs). If neither `repos.csv` nor `--repo` is provided, the script errors with a helpful message.

## Data Pipeline

### `releases.py` changes

- Replace `DEFAULT_REPOS` with logic to read `repos.csv`
- Add an `--output-dir DIR` argument. When combined with `--json`, the script writes a `data.json` file into that directory containing the per-release, per-platform download data for all configured repos. The JSON structure is the same as the existing `--json` output, with a top-level `generated_at` ISO timestamp added.

Existing functionality (PNG charts, CSV, text report) is preserved for local use.

### Daily snapshots

Each run saves a timestamped copy of the JSON data as `snapshots/YYYY-MM-DD.json` on the `gh-pages` branch. Since GitHub release download counts are cumulative (they only go up), diffing two snapshots produces the actual downloads that occurred between those dates.

A new script, `build_site.py`, runs after `releases.py` and is responsible for:

1. Reading today's `data.json` (produced by `releases.py`)
2. Reading all existing snapshots from `snapshots/` on the `gh-pages` branch (checked out by the action)
3. Saving today's snapshot to `snapshots/YYYY-MM-DD.json`
4. Computing weekly download deltas by diffing snapshots: for each week, find the closest snapshots bounding that week and compute the difference per repo, per platform
5. Writing a `history.json` file containing the weekly time-series data

If fewer than 2 snapshots exist (first run), `history.json` is written with an empty `weeks` array and the weekly chart is hidden on the site.

### JSON output structure

#### `data.json` -- current release totals

```json
{
  "generated_at": "2026-04-01T06:00:00Z",
  "repos": [
    {
      "repo": "Azure/aks-desktop",
      "approx_all_time_release_downloads": 2032,
      "releases": [
        {
          "tag": "v0.1.0-alpha",
          "name": "...",
          "published_at": "2025-11-19T22:51:24Z",
          "prerelease": false,
          "download_total": 1464,
          "linux": 26,
          "mac": 695,
          "win": 743
        }
      ]
    }
  ]
}
```

#### `history.json` -- weekly download velocity

```json
{
  "repos": [
    {
      "repo": "Azure/aks-desktop",
      "weeks": [
        {
          "week": "2026-03-23",
          "linux": 12,
          "mac": 85,
          "win": 34
        }
      ]
    }
  ]
}
```

`week` is the Monday that starts the week (ISO week). Each entry contains the total new downloads per platform across all releases during that week.

## Site

### File: `site/index.html`

A single self-contained HTML file with all CSS and JS inline. No build step, no npm, no external frameworks beyond Chart.js loaded from CDN.

### Visual design

- **Theme:** Dark modern dashboard (`#0d1117` background, `#161b22` cards)
- **Typography:** System font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, ...`)
- **Layout:** Full-width page. Header with title and "last updated" timestamp. One card per repo stacked vertically.

### Per-repo card contents

1. **Repo name** as heading (linked to the GitHub repo)
2. **Headline stat:** total downloads, formatted with commas
3. **Stacked bar chart** -- "Downloads by Release" (Chart.js):
   - X-axis: release tags, chronological order (oldest left)
   - Y-axis: download count
   - Stacked segments: Linux (orange `#F5A623`), Mac (blue `#4A90D9`), Win (green `#7ED321`)
   - Hover tooltips showing exact per-platform counts
   - Dark-themed axes, gridlines, and legend
4. **Stacked area or bar chart** -- "Downloads per Week" (Chart.js):
   - X-axis: week labels (e.g., "Mar 23"), chronological
   - Y-axis: downloads that week
   - Stacked by platform (same colors as above)
   - Only shown when `history.json` has at least 2 weeks of data
5. Prerelease tags visually distinguished (lighter opacity or label marker)

### Data loading

The page loads both `data.json` and `history.json` via `fetch()` at runtime.

## GitHub Action

### File: `.github/workflows/update-site.yml`

**Triggers:**
- `schedule`: daily at 06:00 UTC (`cron: '0 6 * * *'`)
- `workflow_dispatch`: manual trigger

**Steps:**
1. Checkout `main` branch
2. Checkout `gh-pages` branch into a separate directory (to access existing snapshots)
3. Set up Python 3.x
4. Install dependencies from `requirements.txt`
5. Run: `python releases.py --json --output-dir _site/` (writes `_site/data.json`)
6. Run: `python build_site.py --site-dir _site/ --snapshots-dir <gh-pages-checkout>/snapshots/` (reads existing snapshots, saves today's snapshot, writes `_site/history.json`)
7. Copy `site/index.html` to `_site/index.html`
8. Copy `_site/snapshots/` into final output (so snapshots persist on gh-pages)
9. Deploy `_site/` to `gh-pages` branch using `peaceiris/actions-gh-pages@v4`

**Authentication:** Default `GITHUB_TOKEN` (for both GitHub API calls in the script and the gh-pages push).

**Permissions:** `contents: write` (needed for gh-pages push).

## File layout after implementation

```
githubreports/
  repos.csv                # list of repos to track (single 'repo' column)
  releases.py              # updated with repos.csv support and --output-dir flag
  build_site.py            # snapshot management and history.json generation
  requirements.txt         # matplotlib, numpy (matplotlib still used for local PNG)
  site/
    index.html             # the dashboard page (checked into main)
  .github/
    workflows/
      update-site.yml      # the daily action
```

On the `gh-pages` branch (generated, not checked into main):

```
gh-pages branch:
  index.html
  data.json
  history.json
  snapshots/
    2026-04-01.json
    2026-04-02.json
    ...
```

## What's NOT in scope

- No per-asset breakdown beyond platform (no arch-level detail)
- No authentication UI or configuration UI
- No framework, bundler, or build tooling
