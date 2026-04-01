# GitHub Release Downloads Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert githubreports into a GitHub Pages site with a dark executive dashboard showing release downloads by platform, weekly download trends from daily snapshots, driven by a CSV config file and updated by a daily GitHub Action.

**Architecture:** `releases.py` fetches GitHub release data and writes JSON. `build_site.py` manages daily snapshots and computes weekly deltas. A static `site/index.html` renders both datasets as Chart.js charts. A GitHub Action orchestrates the pipeline daily and deploys to `gh-pages`.

**Tech Stack:** Python 3 (stdlib + matplotlib/numpy for local use), Chart.js 4.x (CDN), GitHub Actions, GitHub Pages

---

## File Structure

| File | Responsibility |
|------|---------------|
| `repos.csv` | List of repos to track (single `repo` column) |
| `releases.py` | Fetch GitHub release data, output JSON/CSV/PNG/text. Reads `repos.csv` for defaults. |
| `build_site.py` | Read `data.json`, manage snapshots, compute weekly deltas, write `history.json` |
| `site/index.html` | Self-contained dark dashboard. Loads `data.json` + `history.json`, renders Chart.js charts. |
| `.github/workflows/update-site.yml` | Daily cron + manual dispatch. Runs pipeline, deploys to `gh-pages`. |
| `requirements.txt` | Python dependencies (matplotlib, numpy) |

---

### Task 1: Create `repos.csv` and update `releases.py` to read it

**Files:**
- Create: `repos.csv`
- Modify: `releases.py`

- [ ] **Step 1: Create `repos.csv`**

```csv
repo
Azure/aks-desktop
kubernetes-sigs/headlamp
```

- [ ] **Step 2: Add `read_repos_csv()` function and `--output-dir` arg to `releases.py`**

In `releases.py`, remove the `DEFAULT_REPOS` constant. Add a function to read `repos.csv`:

```python
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
```

Add `--output-dir` argument to `parse_args()`:

```python
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Write JSON output to data.json in this directory instead of stdout.",
    )
```

- [ ] **Step 3: Update `main()` to use `repos.csv` and `--output-dir`**

Replace the repos resolution logic in `main()`:

```python
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

    # ... rest of existing chart/csv/text logic unchanged ...
```

Add `import sys` at the top of the file.

- [ ] **Step 4: Test locally**

Run: `python releases.py --json --output-dir _test_site/`

Expected: `_test_site/data.json` is created with the correct structure including `generated_at` and `repos` array.

Run: `python releases.py` (no --repo flag, repos.csv present)

Expected: text report prints for both repos from repos.csv.

Clean up: `rm -rf _test_site/`

- [ ] **Step 5: Commit**

```bash
git add repos.csv releases.py
git commit -m "feat: read repos from repos.csv, add --output-dir for JSON output"
```

---

### Task 2: Create `build_site.py` -- snapshot management and history generation

**Files:**
- Create: `build_site.py`

- [ ] **Step 1: Write `build_site.py`**

```python
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
```

- [ ] **Step 2: Test locally with synthetic snapshots**

```bash
# Create test dirs
mkdir -p _test_site _test_snapshots

# Run releases.py to get real data.json
python releases.py --json --output-dir _test_site/

# Simulate an older snapshot by copying data.json with tweaked numbers
python3 -c "
import json
with open('_test_site/data.json') as f:
    data = json.load(f)
# Reduce all counts by 10 to simulate yesterday
for repo in data['repos']:
    for rel in repo['releases']:
        for p in ('linux','mac','win'):
            rel[p] = max(0, rel[p] - 10)
        rel['download_total'] = rel['linux'] + rel['mac'] + rel['win']
with open('_test_snapshots/2026-03-31.json','w') as f:
    json.dump(data, f, indent=2)
"

# Run build_site.py
python build_site.py --site-dir _test_site/ --snapshots-dir _test_snapshots/

# Verify outputs
cat _test_site/history.json
ls _test_snapshots/
```

Expected: `history.json` has weekly data with non-zero deltas. `_test_snapshots/` has both `2026-03-31.json` and today's dated snapshot.

Clean up: `rm -rf _test_site _test_snapshots`

- [ ] **Step 3: Commit**

```bash
git add build_site.py
git commit -m "feat: add build_site.py for snapshot management and weekly history"
```

---

### Task 3: Create `site/index.html` -- dark executive dashboard

**Files:**
- Create: `site/index.html`

- [ ] **Step 1: Create `site/` directory**

```bash
mkdir -p site
```

- [ ] **Step 2: Write `site/index.html`**

A single self-contained HTML file. All CSS inline in `<style>`, all JS inline in `<script>`. Chart.js 4.x loaded from CDN. The file fetches `data.json` and `history.json` at runtime, then renders:

- A page header with title and last-updated timestamp
- One card per repo with:
  - Repo name (linked to GitHub), total downloads headline stat
  - "Downloads by Release" stacked bar chart (Linux/Mac/Win)
  - "Downloads per Week" stacked bar chart (only if history data exists)

Key design details:
- Background: `#0d1117`, cards: `#161b22` with `1px solid #30363d` border and `border-radius: 12px`
- Colors: Linux `#F5A623`, Mac `#4A90D9`, Win `#7ED321`
- Font: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`
- Chart.js config: dark gridlines (`#30363d`), light tick labels (`#8b949e`), tooltip with all three platforms
- Prerelease tags get a `(pre)` suffix and reduced bar opacity (`0.5`)

The full HTML content is approximately 350-450 lines. Here is the complete file:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub Release Downloads Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.5;
    padding: 2rem;
  }
  .header {
    text-align: center;
    margin-bottom: 2.5rem;
  }
  .header h1 {
    font-size: 1.75rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
  }
  .header .updated {
    color: #8b949e;
    font-size: 0.85rem;
  }
  .card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.5rem 2rem;
    margin: 0 auto 2rem auto;
    max-width: 1100px;
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    margin-bottom: 1rem;
  }
  .card-header h2 {
    font-size: 1.25rem;
    font-weight: 600;
  }
  .card-header h2 a {
    color: #58a6ff;
    text-decoration: none;
  }
  .card-header h2 a:hover {
    text-decoration: underline;
  }
  .stat {
    font-size: 1.1rem;
    color: #8b949e;
  }
  .stat strong {
    color: #e6edf3;
    font-size: 1.35rem;
  }
  .chart-container {
    position: relative;
    width: 100%;
    margin-bottom: 1.5rem;
  }
  .chart-label {
    font-size: 0.8rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.5rem;
  }
  .loading {
    text-align: center;
    color: #8b949e;
    padding: 4rem 0;
    font-size: 1rem;
  }
  .error {
    text-align: center;
    color: #f85149;
    padding: 4rem 0;
  }
</style>
</head>
<body>

<div class="header">
  <h1>GitHub Release Downloads</h1>
  <div class="updated" id="updated"></div>
</div>
<div id="content">
  <div class="loading">Loading data&hellip;</div>
</div>

<script>
const COLORS = {
  linux: { bg: '#F5A623', bgFaded: 'rgba(245,166,35,0.45)' },
  mac:   { bg: '#4A90D9', bgFaded: 'rgba(74,144,217,0.45)' },
  win:   { bg: '#7ED321', bgFaded: 'rgba(126,211,33,0.45)' },
};

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      labels: { color: '#8b949e', padding: 16, usePointStyle: true, pointStyle: 'rectRounded' }
    },
    tooltip: {
      backgroundColor: '#1c2128',
      titleColor: '#e6edf3',
      bodyColor: '#e6edf3',
      borderColor: '#30363d',
      borderWidth: 1,
      padding: 10,
      callbacks: {
        footer: function(items) {
          let sum = 0;
          items.forEach(i => sum += i.parsed.y);
          return 'Total: ' + sum.toLocaleString();
        }
      }
    }
  },
  scales: {
    x: {
      stacked: true,
      ticks: { color: '#8b949e', maxRotation: 45 },
      grid: { color: 'rgba(48,54,61,0.5)' },
    },
    y: {
      stacked: true,
      ticks: { color: '#8b949e', callback: v => v.toLocaleString() },
      grid: { color: 'rgba(48,54,61,0.5)' },
    }
  }
};

function fmt(n) { return Number(n).toLocaleString(); }

function makeReleaseChart(canvas, repoData) {
  const releases = repoData.releases;
  const labels = releases.map(r => r.prerelease ? r.tag + ' (pre)' : r.tag);
  const bgAlpha = releases.map(r => r.prerelease ? 0.5 : 1.0);

  function colorArr(base, faded) {
    return releases.map(r => r.prerelease ? faded : base);
  }

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Linux', data: releases.map(r => r.linux),  backgroundColor: colorArr(COLORS.linux.bg, COLORS.linux.bgFaded) },
        { label: 'Mac',   data: releases.map(r => r.mac),    backgroundColor: colorArr(COLORS.mac.bg, COLORS.mac.bgFaded) },
        { label: 'Win',   data: releases.map(r => r.win),    backgroundColor: colorArr(COLORS.win.bg, COLORS.win.bgFaded) },
      ]
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        ...CHART_DEFAULTS.scales,
        x: { ...CHART_DEFAULTS.scales.x, ticks: { ...CHART_DEFAULTS.scales.x.ticks, font: { size: releases.length > 30 ? 9 : 11 } } }
      }
    }
  });
}

function makeWeeklyChart(canvas, weeklyData) {
  const weeks = weeklyData.weeks;
  const labels = weeks.map(w => {
    const d = new Date(w.week + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Linux', data: weeks.map(w => w.linux), backgroundColor: COLORS.linux.bg },
        { label: 'Mac',   data: weeks.map(w => w.mac),   backgroundColor: COLORS.mac.bg },
        { label: 'Win',   data: weeks.map(w => w.win),   backgroundColor: COLORS.win.bg },
      ]
    },
    options: CHART_DEFAULTS
  });
}

function buildCard(repoData, weeklyData) {
  const card = document.createElement('div');
  card.className = 'card';

  const repoUrl = 'https://github.com/' + repoData.repo;
  let html = '<div class="card-header">'
    + '<h2><a href="' + repoUrl + '" target="_blank">' + repoData.repo + '</a></h2>'
    + '<div class="stat">Total Downloads: <strong>' + fmt(repoData.approx_all_time_release_downloads) + '</strong></div>'
    + '</div>';

  // Release chart
  const releaseId = 'release-' + repoData.repo.replace(/\//g, '-');
  html += '<div class="chart-container">'
    + '<div class="chart-label">Downloads by Release</div>'
    + '<div style="position:relative;height:' + Math.max(300, repoData.releases.length * 8) + 'px">'
    + '<canvas id="' + releaseId + '"></canvas>'
    + '</div></div>';

  // Weekly chart placeholder
  const weeklyId = 'weekly-' + repoData.repo.replace(/\//g, '-');
  if (weeklyData && weeklyData.weeks && weeklyData.weeks.length >= 2) {
    html += '<div class="chart-container">'
      + '<div class="chart-label">Downloads per Week</div>'
      + '<div style="position:relative;height:260px">'
      + '<canvas id="' + weeklyId + '"></canvas>'
      + '</div></div>';
  }

  card.innerHTML = html;
  return card;
}

async function init() {
  const content = document.getElementById('content');
  try {
    const [dataResp, histResp] = await Promise.all([
      fetch('./data.json'),
      fetch('./history.json').catch(() => null)
    ]);

    if (!dataResp.ok) throw new Error('Failed to load data.json');
    const data = await dataResp.json();

    let history = { repos: [] };
    if (histResp && histResp.ok) {
      history = await histResp.json();
    }

    // Update header
    if (data.generated_at) {
      const d = new Date(data.generated_at);
      document.getElementById('updated').textContent = 'Last updated: ' + d.toLocaleDateString('en-US', {
        year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'
      });
    }

    content.innerHTML = '';

    for (const repoData of data.repos) {
      const weeklyData = history.repos.find(r => r.repo === repoData.repo);
      const card = buildCard(repoData, weeklyData);
      content.appendChild(card);

      // Render charts after DOM insertion
      const releaseId = 'release-' + repoData.repo.replace(/\//g, '-');
      const releaseCanvas = document.getElementById(releaseId);
      if (releaseCanvas) makeReleaseChart(releaseCanvas, repoData);

      const weeklyId = 'weekly-' + repoData.repo.replace(/\//g, '-');
      const weeklyCanvas = document.getElementById(weeklyId);
      if (weeklyCanvas && weeklyData) makeWeeklyChart(weeklyCanvas, weeklyData);
    }

  } catch (err) {
    content.innerHTML = '<div class="error">Error: ' + err.message + '</div>';
  }
}

init();
</script>
</body>
</html>
```

- [ ] **Step 3: Test locally with a quick HTTP server**

```bash
# Generate data
mkdir -p _test_site
python releases.py --json --output-dir _test_site/

# Create minimal history.json for testing
echo '{"repos":[]}' > _test_site/history.json

# Copy index.html
cp site/index.html _test_site/index.html

# Serve and check in browser
python -m http.server 8080 --directory _test_site/
# Open http://localhost:8080 -- verify dark dashboard renders with charts
```

Expected: Dark background page, two cards with stacked bar charts. Weekly chart hidden (no history data). No console errors.

Stop the server after verifying.

Clean up: `rm -rf _test_site`

- [ ] **Step 4: Commit**

```bash
git add site/index.html
git commit -m "feat: add dark executive dashboard with Chart.js stacked charts"
```

---

### Task 4: Create GitHub Action workflow

**Files:**
- Create: `.github/workflows/update-site.yml`

- [ ] **Step 1: Create workflow directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Write `.github/workflows/update-site.yml`**

```yaml
name: Update Dashboard

on:
  schedule:
    - cron: '0 6 * * *'   # Daily at 06:00 UTC
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout main
        uses: actions/checkout@v4

      - name: Checkout gh-pages snapshots
        uses: actions/checkout@v4
        with:
          ref: gh-pages
          path: _gh_pages
        continue-on-error: true  # First run: gh-pages branch won't exist yet

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Fetch release data
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python releases.py --json --output-dir _site/ --num-releases 0

      - name: Build site (snapshots + history)
        run: |
          # Use existing snapshots from gh-pages if available, else empty dir
          SNAP_DIR="_gh_pages/snapshots"
          if [ ! -d "$SNAP_DIR" ]; then
            mkdir -p "$SNAP_DIR"
          fi
          python build_site.py --site-dir _site/ --snapshots-dir "$SNAP_DIR"
          # Copy snapshots into _site so they persist on gh-pages
          cp -r "$SNAP_DIR" _site/snapshots

      - name: Copy index.html
        run: cp site/index.html _site/index.html

      - name: Deploy to gh-pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./_site
          publish_branch: gh-pages
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/update-site.yml
git commit -m "feat: add daily GitHub Action to update dashboard and deploy to gh-pages"
```

---

### Task 5: Update `requirements.txt` and clean up old output files

**Files:**
- Modify: `requirements.txt`
- Delete: old CSV/PNG output files in repo root

- [ ] **Step 1: Verify `requirements.txt` has needed deps**

The file should contain:

```
matplotlib
numpy
```

No changes needed -- these are already present.

- [ ] **Step 2: Remove old generated output files from repo root**

These were generated during development and should not be checked in:

```bash
rm -f Azure_aks-desktop_approx_release_month_downloads.csv
rm -f Azure_aks-desktop_downloads_by_release.csv
rm -f Azure_aks-desktop_downloads_by_release.png
rm -f kubernetes-sigs_headlamp_approx_release_month_downloads.csv
rm -f kubernetes-sigs_headlamp_downloads_by_release.csv
rm -f kubernetes-sigs_headlamp_downloads_by_release.png
```

- [ ] **Step 3: Add `.gitignore`**

Create `.gitignore` to prevent generated files from being committed:

```
_site/
_test_site/
_test_snapshots/
_gh_pages/
*.png
*_downloads_by_release.csv
*_approx_release_month_downloads.csv
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .gitignore
git rm --cached -f Azure_aks-desktop_approx_release_month_downloads.csv Azure_aks-desktop_downloads_by_release.csv Azure_aks-desktop_downloads_by_release.png kubernetes-sigs_headlamp_approx_release_month_downloads.csv kubernetes-sigs_headlamp_downloads_by_release.csv kubernetes-sigs_headlamp_downloads_by_release.png 2>/dev/null || true
git commit -m "chore: add .gitignore, remove generated output files"
```

---

### Task 6: End-to-end local test

- [ ] **Step 1: Run the full pipeline locally**

```bash
# Step 1: Generate data
mkdir -p _test_site _test_snapshots

python releases.py --json --output-dir _test_site/ --num-releases 0

# Step 2: Create a fake "yesterday" snapshot
python3 -c "
import json
with open('_test_site/data.json') as f:
    data = json.load(f)
for repo in data['repos']:
    for rel in repo['releases']:
        for p in ('linux','mac','win'):
            rel[p] = max(0, rel[p] - 10)
        rel['download_total'] = rel['linux'] + rel['mac'] + rel['win']
with open('_test_snapshots/2026-03-31.json','w') as f:
    json.dump(data, f, indent=2)
"

# Step 3: Run build_site.py
python build_site.py --site-dir _test_site/ --snapshots-dir _test_snapshots/

# Step 4: Copy index.html
cp site/index.html _test_site/index.html

# Step 5: Serve
python -m http.server 8080 --directory _test_site/
```

Expected: Open `http://localhost:8080`. Dashboard shows:
- Two repo cards with dark theme
- "Downloads by Release" stacked bar charts
- "Downloads per Week" stacked bar charts (with one week of data from the fake snapshot)
- Correct total download counts
- Hover tooltips working

- [ ] **Step 2: Clean up**

```bash
rm -rf _test_site _test_snapshots
```
