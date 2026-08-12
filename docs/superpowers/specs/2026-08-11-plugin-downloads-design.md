# Plugin Download Tracking — Design

**Date:** 2026-08-11
**Status:** Approved
**Scope:** Add a third dashboard chart for the Headlamp AI assistant plugin, and store download history for all plugins in `headlamp-k8s/plugins` without charting them.

## Intended Outcome

The dashboard gains a third card showing download counts for the `ai-assistant` plugin from `headlamp-k8s/plugins`, with the same By Release / By Week / By Month toggle as the existing two cards. Download data for all plugins in that repo is collected and snapshotted daily, so any of them can be charted later by flipping a config flag — with trend history already accumulated rather than starting from zero.

## Repository Evidence

Observed from the GitHub API on 2026-08-11 (`headlamp-k8s/plugins`):

- 94 releases, 95 release assets.
- Each release covers **one plugin**, tagged `<plugin>-<version>` (e.g. `ai-assistant-0.3.0-alpha`).
- Every asset is a single `.tar.gz` (or legacy `.tgz`) with a real `download_count`.
- Six legacy `v0.1.x` tags predate per-plugin tagging and bundle plugin `.tgz` assets whose filenames carry the plugin name.
- AI assistant: 3 releases, 102,447 downloads total — `0.1.0-alpha` 81,213 / `0.2.0-alpha` 20,086 / `0.3.0-alpha` 1,148.
- Top plugins by downloads: flux 159,684 / cert-manager 157,869 / prometheus 119,921 / ai-assistant 102,447 / keda 81,181.

### Key constraint: shape mismatch

Plugin downloads have **no Linux/Mac/Win dimension**, and one repo contains many plugins. The existing pipeline is built entirely around a platform breakdown keyed by repo. `classify_platform()` returns `None` for every plugin asset, so adding `headlamp-k8s/plugins` to `repos.csv` today would render an empty card.

This design therefore runs plugin collection as a **parallel track** that reuses the existing snapshot/diff/weekly machinery, rather than bending the platform model to fit. The two existing cards are unaffected.

### Baseline state

The repository has **no test suite** (zero test files). The tests specified below are the first in this project; the implementation plan must establish a test runner (pytest) and add it to `requirements.txt`.

## Decisions

### D1: Plugin attribution comes from the asset filename, not the tag

Derivation: strip `.tar.gz`/`.tgz`, strip an optional `headlamp-k8s-` prefix, strip the trailing `-<version>`.

Validated against all 95 observed assets: **95/95 parse, yielding 21 distinct plugins, zero unmatched.**

Tag-based attribution was rejected: it produces 27 buckets including junk entries (`v0.1.4`, `v0.1.3`, …) because the legacy releases carry version-only tags. Filename attribution correctly folds those into `app-catalog` and `prometheus`.

Known cosmetic artifact, accepted: the tag `example-change-logo-*` ships an asset named `change-logo-*.tar.gz`, so that plugin is named `change-logo`. It is an example plugin, not charted. Not worth a special case.

### D2: Releases with zero downloads are kept

`releases.py` skips releases whose classified downloads total 0, which is correct for platform data — an unclassifiable asset set should not render an empty bar. For plugins the opposite holds: a freshly published plugin at 0 downloads is real information, and dropping it would make new plugins invisible. (`argocd` currently has 3 downloads.)

### D3: `-alpha` versions are not treated as prereleases

All three AI assistant releases carry `-alpha` in the version, but GitHub's `prerelease` flag is `false` on every one. GitHub's flag is the single source of truth, matching `releases.py`. Consequence: all three AI assistant bars render solid, none faded.

Rejected: inferring prerelease from the version string, which would introduce a second conflicting notion of "prerelease" into one codebase.

### D4: Release limiting is per-plugin, not per-repo

`--num-releases` currently trims per repo. Applied naively to plugins, `prometheus` (18 releases) would crowd out other plugins within a single repo-wide window. The plugin track applies the limit per plugin. The workflow passes `0` (all), so this affects local runs only.

### D5: Decreasing counts stay guarded

GitHub download counts can drop when an asset is re-uploaded. The shared diff retains the existing `if d > 0` guard, so a re-upload registers as zero for that week rather than a negative bar.

## Architecture

### Configuration — `plugins.csv`

```csv
repo,plugin,chart
headlamp-k8s/plugins,ai-assistant,1
```

Semantics, stated precisely because the two columns do different jobs:

- The **`repo` column drives collection**. Any repo appearing in any row has *all* of its plugins collected and snapshotted, regardless of the row's other values.
- The **`plugin` + `chart` columns drive display only**. A row with `chart=1` gives that plugin a dashboard card. A row with `chart=0` is a no-op beyond declaring its repo.
- To collect a repo without charting anything from it, add a row with `chart=0`; the `plugin` value is then ignored.
- A `plugin` value naming a plugin absent from the repo is reported as a warning and skipped, not fatal.

Mirrors the existing `repos.csv` convention.

### New module — `plugins.py`

Mirrors `releases.py`'s structure and reuses its conventions (`github_headers`, pagination, `--json --output-dir`). Emits `plugins.json`:

```json
{
  "generated_at": "2026-08-11T06:00:00Z",
  "repos": [
    {
      "repo": "headlamp-k8s/plugins",
      "plugins": [
        {
          "plugin": "ai-assistant",
          "chart": true,
          "approx_all_time_downloads": 102447,
          "releases": [
            {
              "tag": "ai-assistant-0.1.0-alpha",
              "version": "0.1.0-alpha",
              "published_at": "2025-08-07T14:04:34Z",
              "prerelease": false,
              "downloads": 81213
            }
          ]
        }
      ]
    }
  ]
}
```

All 21 plugins appear. `chart` is true only for plugins flagged in `plugins.csv`.

### `build_site.py` — second snapshot track

New arguments `--plugin-site-dir` and `--plugin-snapshots-dir`, writing `plugin-snapshots/YYYY-MM-DD.json` and `plugins-history.json`.

The weekly-delta logic is refactored so `build_platform_index`, `diff_snapshots`, `compute_weekly_history`, and `build_history_json` take the metric keys as a parameter — `["linux", "mac", "win"]` for the platform track, `["downloads"]` for the plugin track — and are shared by both.

Existing `snapshots/` and `history.json` are untouched. No migration; the accumulated platform history carries no risk.

`plugins-history.json` structure:

```json
{
  "repos": [
    {
      "repo": "headlamp-k8s/plugins",
      "plugins": [
        {
          "plugin": "ai-assistant",
          "weeks": [{ "week": "2026-08-10", "downloads": 412 }]
        }
      ]
    }
  ]
}
```

### Dashboard — `site/index.html`

A third card renders after the two existing ones, for each plugin with `chart: true`. It reuses `setupToggle` and `CHART_DEFAULTS` unchanged; the only new code is single-series config builders paralleling the existing three.

- Series color `#BC7EE8` — a distinct fourth hue, so the single series does not read as "Linux".
- Stacking remains enabled (harmless with one series).
- Same graceful degradation as today: with fewer than two weeks of snapshots the card opens on **By Release** and the week/month buttons do not render.
- Card header links to the repo and shows the plugin's all-time total.

### Workflow — `.github/workflows/update-site.yml`

- Add `plugins.csv` to the `paths:` trigger.
- Add a plugin fetch step (`python plugins.py --json --output-dir _site/ --num-releases 0`).
- Extend the build step to pass the plugin snapshot directory, and copy `plugin-snapshots` into `_site` alongside `snapshots`.

## Data Flow

```
plugins.csv ──> plugins.py ──> _site/plugins.json
                                    │
                                    ├──> plugin-snapshots/YYYY-MM-DD.json  (daily)
                                    │           │
                                    │           v
                                    │    shared diff/weekly logic
                                    │           │
                                    │           v
                                    └──> _site/plugins-history.json
                                                │
                                                v
                                        site/index.html (card 3)
```

## Failure Handling

- **First run:** no prior plugin snapshots. `compute_weekly_history` already returns `{}` for fewer than 2 snapshots; the dashboard falls back to By Release.
- **Missing `plugins.json`/`plugins-history.json`:** the dashboard's existing `fetch(...).catch(() => null)` pattern is extended to the plugin files, so the two existing cards still render if the plugin track fails.
- **Missing `plugins.csv`:** the plugin track is skipped with a message; the platform pipeline proceeds unaffected.
- **Unparseable asset name:** counted and reported, not fatal. (Currently zero occurrences.)
- **API rate limits:** one additional paginated fetch per day (94 releases = one page at `per_page=100`). Negligible against the authenticated limit.

## Testing

The attribution function is the only substantive logic and is pure.

1. **Attribution table test** over all 95 observed asset names — both prefix styles, legacy `.tgz` forms, and the `change-logo` artifact — asserting the 21 expected plugin names.
2. **Diff test** feeding two synthetic plugin snapshots, asserting per-plugin weekly deltas, including the D5 decrease-guard case.
3. **Refactor regression test** asserting the shared metric-keys refactor leaves platform output byte-identical to current behavior. This guards the only change that touches working code.
4. **First-run test** asserting the plugin track produces valid output with zero prior snapshots.
5. **End-to-end local pipeline run** against the real API before pushing.

## Documentation

Update `README.md`: project structure, How It Works, tracked-repos section, and the options table.

## Explicit Exclusions

- No chart for any plugin other than `ai-assistant` (data is collected for all; charting is a config flag).
- No changes to the two existing cards or to platform data collection beyond the shared-logic refactor.
- No ArtifactHub integration — GitHub release assets are the data source.
- No snapshot retention/pruning policy. Snapshot files accumulate one per day per track on `gh-pages`; this is pre-existing behavior, not introduced here.

## Assumptions That May Change

- Plugin asset naming stays `[headlamp-k8s-]<plugin>-<version>.tar.gz`. A new naming scheme would need the attribution rule extended — the unparseable-name counter surfaces this.
- One plugin per release. If a future release bundles several plugins, filename attribution already handles it correctly (as it does for the legacy `v0.1.x` tags).
