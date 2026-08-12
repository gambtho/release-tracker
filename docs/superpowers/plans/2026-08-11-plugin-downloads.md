# Plugin Download Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third dashboard card charting downloads of the Headlamp `ai-assistant` plugin, and collect daily download history for all 21 plugins in `headlamp-k8s/plugins` without charting them.

**Architecture:** Plugin data has no platform dimension and one repo holds many plugins, so collection runs as a parallel track (`plugins.py` → `plugins.json` → `plugin-snapshots/` → `plugins-history.json`) that reuses the existing snapshot/diff/weekly machinery in `build_site.py` rather than bending the platform model to fit. Shared GitHub HTTP helpers move to a new `github_api.py` so the plugin track and its tests do not depend on matplotlib. The existing platform track and its accumulated `history.json` are untouched.

**Tech Stack:** Python 3.12 (stdlib only for the plugin track), pytest (new), Chart.js 4 via CDN, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-11-plugin-downloads-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **Plugin attribution comes from the asset filename, not the tag.** Strip `.tar.gz`/`.tgz`, strip an optional `headlamp-k8s-` prefix, strip the trailing `-<version>`. Verified against all 93 distinct observed assets: 93/93 parse, 21 plugins, zero unmatched.
- **Zero-download releases are KEPT** in the plugin track. This differs deliberately from `releases.py`, which skips them. A newly published plugin at 0 downloads is real information. (Spec D2)
- **`prerelease` comes from GitHub's `prerelease` boolean only.** Never infer it from `-alpha`/`-beta` in a version string. All three real `ai-assistant` releases carry `-alpha` versions with `prerelease: false`. (Spec D3)
- **`--num-releases` trims per plugin, not per repo.** `prometheus` has 18 releases and would otherwise crowd out other plugins in a repo-wide window. (Spec D4)
- **Download decreases clamp to zero, never negative.** GitHub counts can drop when an asset is re-uploaded. The existing `if d > 0` guard is preserved in the shared diff. (Spec D5)
- **The existing platform track must not change behavior.** `snapshots/` and `history.json` hold real accumulated user-visible history. Task 4 gates this with a byte-identical golden-fixture regression test.
- **The plugin track must fail soft.** If `plugins.csv` is missing, `plugins.json` is absent, or the plugin fetch fails, the two existing cards must still render and the platform pipeline must still complete.
- **No new runtime dependencies.** `plugins.py`, `github_api.py`, and `build_site.py` use the Python standard library only. `pytest` is added to the single existing `requirements.txt` — this repo has no separate dev-requirements file and adding one is out of scope, so CI will install a pytest it never runs. That is accepted, not an oversight. `matplotlib`/`numpy` remain required only by `releases.py`'s local chart path.
- **No JS tooling.** This repo has no JavaScript test framework and none is to be added. Dashboard changes are verified by running the local pipeline and viewing the page.
- Python style follows the existing files: `"""docstrings"""`, `.format()` for interpolation, 4-space indent, double quotes.

## Baseline State

- The repository has **zero test files and no test runner**. Task 1 establishes pytest. Tests written here are this project's first.
- `matplotlib` and `numpy` are **not installed** in the dev environment. They are only needed by `releases.py`'s chart path (`make_chart`), which the CI workflow never invokes (it runs `--json`). No test may import them.
- Work happens in the worktree `.claude/worktrees/plugin-downloads` on branch `worktree-plugin-downloads`.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `github_api.py` | Create (Task 1) | Shared GitHub REST helpers: headers, paginated fetch, repo parsing. Stdlib only. |
| `plugins.py` | Create (Tasks 2-3) | Plugin asset attribution, config reading, summarization, CLI → `plugins.json`. |
| `plugins.csv` | Create (Task 3) | Config: which repos to collect, which plugins to chart. |
| `build_site.py` | Modify (Tasks 4-5) | Snapshots + weekly history, now parameterized by metric keys and shared across both tracks. |
| `site/index.html` | Modify (Task 6) | Dashboard; gains plugin card and a generalized toggle. |
| `releases.py` | Modify (Task 1) | Loses its HTTP helpers to `github_api.py`; otherwise unchanged. |
| `.github/workflows/update-site.yml` | Modify (Task 7) | Adds plugin fetch + plugin snapshot persistence. |
| `README.md` | Modify (Task 7) | Documents the plugin track, `plugins.csv` semantics, and how to run tests. |
| `requirements.txt` | Modify (Task 1) | Adds `pytest`. |
| `tests/` | Create (Task 1) | First test suite in this repo. |

## Deviations From the Spec

Both are recorded here rather than silently absorbed:

1. **`github_api.py` extraction (Task 1)** — not in the spec. `releases.py` imports matplotlib/numpy at module top, so importing its HTTP helpers into `plugins.py` would make plugin collection and the entire test suite depend on matplotlib, which is not installed. Extracting the five shared helpers keeps the new code and its tests dependency-free.
2. **`setupToggle` gains a `builders` parameter (Task 6)** — the spec said "reuses `setupToggle` unchanged", which is not achievable without duplicating the function, since it currently closes over its three platform builders. Parameterizing honors the spec's intent (reuse, not duplicate).
3. **`--plugin-site-dir` dropped (Task 5)** — the spec mentioned it; a separate site dir is unnecessary because `data.json` and `plugins.json` both live in `--site-dir`. Only `--plugin-snapshots-dir` is added.

## Real Data Reference

Observed from the live GitHub API on 2026-08-11, for use in fixtures and verification:

- `headlamp-k8s/plugins`: 94 releases, 95 asset instances, 93 distinct asset names, 21 plugins.
- `ai-assistant`: 3 releases totalling **102,447** — `0.1.0-alpha` 81,213 / `0.2.0-alpha` 20,086 / `0.3.0-alpha` 1,148. All three have `prerelease: false`.
- The 21 plugins: `ai-assistant, app-catalog, argocd, backstage, cert-manager, change-logo, cluster-api, flux, karpenter, keda, knative, kompose, kro, kubeflow, minikube, opencost, plugin-catalog, prometheus, radius, strimzi, volcano`.
- **Duplicate asset names across tags** (both real, both kept as separate tag-keyed rows): `app-catalog-0.1.3.tgz` under `v0.1.4` (924) and `v0.1.3` (1448); `prometheus-0.0.1.tgz` under `v0.1.4` (919) and `v0.1.4-alpha` (7).

---
### Task 1: Test infrastructure + extract `github_api.py`

**Context for the implementer:** `releases.py` is a single-file script that fetches GitHub release data and renders matplotlib charts. It imports `numpy` and `matplotlib.pyplot` at module top (lines 12-13), which means *any* module that imports its HTTP helpers inherits a hard dependency on the plotting stack. A later task adds `plugins.py`, which needs those helpers but must never touch matplotlib. **matplotlib and numpy are not installed in this dev environment** and are only needed by `releases.py`'s chart path; the test suite must run without them.

This repo has zero test files and no test runner today. This task establishes pytest.

**Files:**
- Create: `github_api.py`
- Create: `pytest.ini`
- Create: `tests/test_github_api.py`
- Create: `tests/test_releases_regression.py`
- Modify: `requirements.txt:1-2`
- Modify: `releases.py:3-13` (import block), `releases.py:15` (`API_BASE`), `releases.py:73-128` (`github_headers`, `http_get_json`, `parse_repo`, `fetch_all_releases`)
- Test: `tests/test_github_api.py`, `tests/test_releases_regression.py`

**Interfaces:**
- Consumes: nothing
- Produces (module `github_api`):
  - `API_BASE = "https://api.github.com"`
  - `github_headers() -> dict`
  - `http_get_json(url) -> object`
  - `parse_repo(repo: str) -> tuple[str, str]` returning `(owner, name)`
  - `fetch_all_releases(owner: str, repo: str) -> list[dict]`

---

- [ ] **Step 1: Add pytest and the test layout**

Append to `requirements.txt` (final contents):

```
matplotlib
numpy
pytest
```

Create `pytest.ini` at the repo root. Without `pythonpath = .`, pytest puts only `tests/` on `sys.path` and `import github_api` fails:

```ini
[pytest]
testpaths = tests
pythonpath = .
```

Then run:

```bash
mkdir -p tests
python3 -m pip install pytest
```

- [ ] **Step 2: Write the failing test for `github_api`**

Create `tests/test_github_api.py`:

```python
"""Tests for github_api — the shared GitHub REST helpers.

These must import without matplotlib/numpy, which are not installed here and
are only needed by releases.py's chart path.
"""

import pytest

import github_api


def test_api_base_constant():
    assert github_api.API_BASE == "https://api.github.com"


def test_github_headers_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    headers = github_api.github_headers()
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["User-Agent"] == "github-release-chart"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert "Authorization" not in headers


def test_github_headers_with_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "abc123")
    assert github_api.github_headers()["Authorization"] == "Bearer abc123"


@pytest.mark.parametrize(
    "repo,expected",
    [
        ("headlamp-k8s/plugins", ("headlamp-k8s", "plugins")),
        ("  owner / name  ", ("owner", "name")),
        ("owner/name/extra", ("owner", "name/extra")),
    ],
)
def test_parse_repo_valid(repo, expected):
    assert github_api.parse_repo(repo) == expected


@pytest.mark.parametrize("repo", ["noslash", "", "/name", "owner/", "  /  "])
def test_parse_repo_invalid_raises(repo):
    with pytest.raises(ValueError) as excinfo:
        github_api.parse_repo(repo)
    assert "Expected OWNER/REPO" in str(excinfo.value)


def test_http_get_json_uses_github_headers(monkeypatch):
    """http_get_json must send the auth headers and decode UTF-8 JSON."""
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req, timeout=None):
        captured["headers"] = req.headers
        captured["timeout"] = timeout
        captured["url"] = req.full_url
        return FakeResponse()

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setattr(github_api.urllib.request, "urlopen", fake_urlopen)

    assert github_api.http_get_json("https://example.test/x") == {"ok": True}
    assert captured["timeout"] == 30
    # urllib title-cases header keys on Request objects.
    assert captured["headers"]["Authorization"] == "Bearer tok"


def test_fetch_all_releases_paginates(monkeypatch):
    """Stops when a short page comes back; concatenates pages in order."""
    pages = {1: [{"id": i} for i in range(100)], 2: [{"id": 100}]}
    seen_urls = []

    def fake_get(url):
        seen_urls.append(url)
        page = int(url.rsplit("page=", 1)[1])
        return pages.get(page, [])

    monkeypatch.setattr(github_api, "http_get_json", fake_get)
    monkeypatch.setattr(github_api.time, "sleep", lambda _s: None)

    releases = github_api.fetch_all_releases("headlamp-k8s", "plugins")
    assert len(releases) == 101
    assert releases[-1] == {"id": 100}
    assert seen_urls[0] == (
        "https://api.github.com/repos/headlamp-k8s/plugins/releases?per_page=100&page=1"
    )


def test_fetch_all_releases_rejects_non_list(monkeypatch):
    monkeypatch.setattr(
        github_api, "http_get_json", lambda _url: {"message": "Not Found"}
    )
    with pytest.raises(RuntimeError) as excinfo:
        github_api.fetch_all_releases("bad", "repo")
    assert "Unexpected response" in str(excinfo.value)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_github_api.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'github_api'`.

- [ ] **Step 4: Create `github_api.py`**

Create `github_api.py` with the five items moved **verbatim** from `releases.py` (`API_BASE` at line 15, `github_headers` at 73, `http_get_json` at 85, `parse_repo` at 91, `fetch_all_releases` at 102). Do not change any behavior — this is a move, not a rewrite:

```python
#!/usr/bin/env python3
"""Shared GitHub REST helpers.

Extracted from releases.py so that modules which only need the API (and not
matplotlib/numpy) can import them without pulling in the plotting stack.
"""

import json
import os
import time
import urllib.request

API_BASE = "https://api.github.com"


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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_github_api.py -v`

Expected: 14 passed. Also confirm the module is matplotlib-free:

```bash
python3 -c "import sys, github_api; assert 'matplotlib' not in sys.modules and 'numpy' not in sys.modules; print('clean')"
```

Expected output: `clean`.

- [ ] **Step 6: Write the regression test for `releases.py`**

`releases.py` still imports matplotlib at module top, which is not installed here, so this test guards the import behind `importorskip`. Step 9 installs the deps once so the guard actually runs.

Create `tests/test_releases_regression.py`:

```python
"""Regression guard: releases.py must behave identically after the extraction.

releases.py imports matplotlib/numpy at module top, so these tests skip unless
the chart dependencies happen to be installed.
"""

import pytest

pytest.importorskip("matplotlib", reason="releases.py needs the chart deps")
pytest.importorskip("numpy", reason="releases.py needs the chart deps")

import releases  # noqa: E402
import github_api  # noqa: E402


def test_releases_reexports_shared_helpers_from_github_api():
    """The moved names must still be reachable via releases.py and be the
    same objects, not re-implementations."""
    assert releases.API_BASE is github_api.API_BASE
    assert releases.github_headers is github_api.github_headers
    assert releases.http_get_json is github_api.http_get_json
    assert releases.parse_repo is github_api.parse_repo
    assert releases.fetch_all_releases is github_api.fetch_all_releases


def test_classify_platform_still_reachable():
    assert callable(releases.classify_platform)
    assert releases.classify_platform("Headlamp-0.30.0-linux-x64.tar.gz") == "linux"
    assert releases.classify_platform("Headlamp-0.30.0-mac-arm64.dmg") == "mac"
    assert releases.classify_platform("Headlamp-0.30.0-win-x64.exe") == "win"
    # Plugin archives and checksums remain unclassifiable.
    assert releases.classify_platform("checksums.txt") is None
    assert releases.classify_platform("headlamp-k8s-flux-0.1.0.tgz") is None


def test_summarize_repo_still_reachable_and_uses_shared_fetch(monkeypatch):
    assert callable(releases.summarize_repo)

    fake_releases = [
        {
            "tag_name": "v1.0.0",
            "name": "1.0.0",
            "published_at": "2026-01-01T00:00:00Z",
            "prerelease": False,
            "assets": [
                {"name": "App-1.0.0-linux-x64.deb", "download_count": 5},
                {"name": "App-1.0.0-win-x64.exe", "download_count": 3},
                {"name": "checksums.txt", "download_count": 99},
            ],
        },
        {"tag_name": "v0.9.0", "draft": True, "assets": []},
    ]
    monkeypatch.setattr(releases, "fetch_all_releases", lambda o, r: fake_releases)

    summary = releases.summarize_repo("headlamp-k8s/headlamp")
    assert summary["repo"] == "headlamp-k8s/headlamp"
    assert summary["approx_all_time_release_downloads"] == 8
    assert len(summary["releases"]) == 1
    row = summary["releases"][0]
    assert (row["linux"], row["win"], row["mac"]) == (5, 3, 0)
    assert row["download_total"] == 8
```

- [ ] **Step 7: Run the regression test and see it skip**

Run: `python3 -m pytest tests/test_releases_regression.py -v -rs`

Expected: 3 skipped, with reason `releases.py needs the chart deps` — matplotlib is not installed yet. This confirms the guard works; Step 9 makes the assertions actually execute.

- [ ] **Step 8: Modify `releases.py` to import the shared helpers**

Replace the import block at `releases.py:3-13`. `time` and `urllib.request` become unused once `fetch_all_releases` and `http_get_json` move out; `json`, `os`, and `re` are still used by `main`, `read_repos_csv`, and `classify_platform`:

```python
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import numpy as np
import matplotlib.pyplot as plt

from github_api import API_BASE, fetch_all_releases, github_headers, http_get_json, parse_repo
```

Then delete these definitions from `releases.py`, which are now in `github_api.py`:
- line 15: `API_BASE = "https://api.github.com"`
- lines 73-82: `github_headers`
- lines 85-88: `http_get_json`
- lines 91-99: `parse_repo`
- lines 102-128: `fetch_all_releases`

Leave `PLATFORMS`, `PLATFORM_COLORS`, and everything from `classify_platform` (line 131) onward untouched. `API_BASE`, `github_headers`, and `http_get_json` are imported but not referenced elsewhere in `releases.py`; keep them in the import so the module's public surface is unchanged for any external caller.

- [ ] **Step 9: Install chart deps and run the full suite green**

```bash
python3 -m pip install matplotlib numpy
python3 -m pytest tests/ -v
```

Expected: 17 passed, 0 skipped. The three regression tests must now actually run — if they still report "skipped", the install did not take and the regression guard has not been exercised.

- [ ] **Step 10: Verify the suite is dependency-free without matplotlib**

The CI/plugin path must not need the chart stack. Confirm in a throwaway environment:

```bash
python3 -m venv /tmp/rt-nodeps && /tmp/rt-nodeps/bin/pip install pytest
/tmp/rt-nodeps/bin/python -m pytest tests/ -v -rs
```

Expected: 14 passed, 3 skipped. `tests/test_github_api.py` passes with no matplotlib present; only the `releases.py` regression tests skip.

- [ ] **Step 11: Commit**

```bash
git add github_api.py pytest.ini requirements.txt releases.py tests/test_github_api.py tests/test_releases_regression.py
git commit -m "Extract GitHub API helpers into github_api.py and add pytest

releases.py imports matplotlib/numpy at module top, so importing its HTTP
helpers would force the plugin collector and the whole test suite to depend
on the chart stack. Move API_BASE, github_headers, http_get_json, parse_repo,
and fetch_all_releases verbatim into github_api.py and import them back.

Establishes the first tests in this repo: pytest, pytest.ini, and tests/."
```

---

### Task 2: `parse_plugin_asset` — plugin attribution from asset filenames

**Context for the implementer:** The repo `headlamp-k8s/plugins` publishes one GitHub release per plugin, and each release carries a single `.tar.gz` (or legacy `.tgz`) asset. The plugin name is derived from the **asset filename**, not the release tag — six legacy `v0.1.x` releases have version-only tags but correctly-named assets, so tag-based attribution produces junk buckets. Filenames come in two styles: with a `headlamp-k8s-` vendor prefix and without it. Versions are trailing and may have multi-part suffixes (`0.1.0-beta-1`), and plugin names themselves may contain hyphens (`cert-manager`, `cluster-api`) — so the split point is "the last hyphen before a segment that starts with a digit or `v`+digit".

This function is pure and is the only substantive logic in the plugin track. It implements spec decision **D1** (attribution from the asset filename, not the tag).

**Files:**
- Create: `plugins.py`
- Create: `tests/fixtures/plugin_assets.txt` (generated from the live API in Step 1)
- Create: `tests/test_plugins.py`
- Test: `tests/test_plugins.py`

**Interfaces:**
- Consumes: `github_api.parse_repo(repo) -> (owner, name)` and `github_api.fetch_all_releases(owner, repo) -> list[dict]` from Task 1 — used only by the one-off fixture generator in Step 1, not by `plugins.py` yet.
- Produces (module `plugins`):
  - `PLUGIN_ASSET_EXTENSIONS = (".tar.gz", ".tgz")`
  - `VENDOR_PREFIX = "headlamp-k8s-"`
  - `parse_plugin_asset(filename: str) -> tuple[str, str] | None` returning `(plugin, version)`, or `None` when the filename is not a recognizable plugin archive

---

- [ ] **Step 1: Capture the real asset filenames as a test fixture**

The 21-plugin assertion must run against real data, not invented filenames. Generate the fixture once from the live API and commit it, so the test stays offline and deterministic afterwards.

```bash
mkdir -p tests/fixtures
python3 - > tests/fixtures/plugin_assets.txt <<'PY'
from github_api import fetch_all_releases, parse_repo

owner, repo = parse_repo("headlamp-k8s/plugins")
names = []
for release in fetch_all_releases(owner, repo):
    for asset in release.get("assets", []):
        names.append(asset["name"])
for name in sorted(names):
    print(name)
PY
wc -l tests/fixtures/plugin_assets.txt
```

Expected: ~95 lines (95 asset instances were observed on 2026-08-11; the count grows as new plugin releases land). Set `GITHUB_TOKEN` first if you hit the unauthenticated rate limit. Eyeball the file — every line should end in `.tar.gz` or `.tgz`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_plugins.py`:

```python
"""Tests for plugin attribution from GitHub release asset filenames."""

import os

import pytest

from plugins import PLUGIN_ASSET_EXTENSIONS, VENDOR_PREFIX, parse_plugin_asset

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "plugin_assets.txt")

# Every plugin currently published by headlamp-k8s/plugins.
EXPECTED_PLUGINS = {
    "ai-assistant",
    "app-catalog",
    "argocd",
    "backstage",
    "cert-manager",
    "change-logo",
    "cluster-api",
    "flux",
    "karpenter",
    "keda",
    "knative",
    "kompose",
    "kro",
    "kubeflow",
    "minikube",
    "opencost",
    "plugin-catalog",
    "prometheus",
    "radius",
    "strimzi",
    "volcano",
}


def test_module_constants():
    assert PLUGIN_ASSET_EXTENSIONS == (".tar.gz", ".tgz")
    assert VENDOR_PREFIX == "headlamp-k8s-"


@pytest.mark.parametrize(
    "filename,expected",
    [
        # Vendor-prefixed, .tar.gz, alpha suffix.
        (
            "headlamp-k8s-ai-assistant-0.3.0-alpha.tar.gz",
            ("ai-assistant", "0.3.0-alpha"),
        ),
        # Legacy bare name, .tgz.
        ("app-catalog-0.1.0.tgz", ("app-catalog", "0.1.0")),
        # Multi-part version suffix.
        (
            "headlamp-k8s-backstage-0.1.0-beta-1.tar.gz",
            ("backstage", "0.1.0-beta-1"),
        ),
        (
            "headlamp-k8s-karpenter-0.1.0-alpha-0.tar.gz",
            ("karpenter", "0.1.0-alpha-0"),
        ),
        # Hyphenated plugin name — the split must not land inside the name.
        ("headlamp-k8s-cert-manager-0.1.0.tar.gz", ("cert-manager", "0.1.0")),
        # Vendor prefix combined with the legacy .tgz extension.
        ("headlamp-k8s-kompose-0.1.0-beta.tgz", ("kompose", "0.1.0-beta")),
        ("prometheus-0.0.1.tgz", ("prometheus", "0.0.1")),
        # Bare name that is itself hyphenated.
        ("change-logo-0.0.1.tar.gz", ("change-logo", "0.0.1")),
    ],
)
def test_parse_plugin_asset_valid(filename, expected):
    assert parse_plugin_asset(filename) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "checksums.txt",  # not an archive at all
        "headlamp-k8s-ai-assistant.tar.gz",  # no version segment
        "noversion.tgz",  # no version segment
        "-0.1.0.tgz",  # empty plugin name
    ],
)
def test_parse_plugin_asset_unrecognized(filename):
    assert parse_plugin_asset(filename) is None


def test_every_real_asset_parses_and_yields_the_expected_plugin_set():
    """All observed assets must parse, with no unmatched names and no
    junk buckets. This is the guard on the attribution rule itself."""
    with open(FIXTURE, encoding="utf-8") as f:
        filenames = [line.strip() for line in f if line.strip()]

    assert filenames, "fixture is empty — regenerate it"

    unparsed = [n for n in filenames if parse_plugin_asset(n) is None]
    assert unparsed == []

    plugins = {parse_plugin_asset(n)[0] for n in filenames}
    assert plugins == EXPECTED_PLUGINS
    assert len(plugins) == 21


def test_versions_are_non_empty_for_real_assets():
    with open(FIXTURE, encoding="utf-8") as f:
        filenames = [line.strip() for line in f if line.strip()]
    for name in filenames:
        plugin, version = parse_plugin_asset(name)
        assert plugin, name
        assert version, name
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_plugins.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'plugins'`.

- [ ] **Step 4: Create `plugins.py` with the attribution function**

Create `plugins.py`. The regex `^(.*?)-v?\d[\w.\-]*$` is non-greedy on the name but anchored at the end, so backtracking settles on the split that lets the remainder match a version — that is what keeps `cert-manager-0.1.0` from splitting at the first hyphen while still splitting `backstage-0.1.0-beta-1` at the right place:

```python
#!/usr/bin/env python3
"""Collect per-plugin download counts from GitHub release assets."""

import re

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
```

Note the extension loop order: `.tar.gz` is checked before `.tgz` so that `foo.tar.gz` does not fall through, and the `for/else` returns `None` for any filename matching neither.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_plugins.py -v`

Expected: 15 passed. If `test_every_real_asset_parses_and_yields_the_expected_plugin_set` fails with an extra plugin name, a new plugin has shipped since the fixture was captured — add it to `EXPECTED_PLUGINS` and update the `== 21` count. If it fails with an *unparsed* name, the naming scheme has changed and the attribution rule needs extending; do not loosen the test.

- [ ] **Step 6: Confirm the plugin module stays matplotlib-free**

```bash
python3 -c "import sys, plugins; assert 'matplotlib' not in sys.modules and 'numpy' not in sys.modules; print('clean')"
python3 -m pytest tests/ -v
```

Expected: `clean`, then the full suite green (32 passed with the chart deps installed).

- [ ] **Step 7: Commit**

```bash
git add plugins.py tests/test_plugins.py tests/fixtures/plugin_assets.txt
git commit -m "Add parse_plugin_asset for plugin attribution from asset filenames

Plugin identity comes from the release asset filename, not the tag: six
legacy v0.1.x releases carry version-only tags but correctly-named assets,
so tag-based attribution would produce junk buckets.

Strips .tar.gz/.tgz, strips the optional headlamp-k8s- vendor prefix, then
splits the trailing version. Verified against all real assets in
headlamp-k8s/plugins: every one parses, yielding exactly 21 plugins."
```

---
### Task 3: `plugins.py` — config reading, per-plugin summarization, and CLI

**Files:**
- Create: `plugins.csv`
- Create: `tests/test_plugins_config.py`
- Create: `tests/test_plugins_summary.py`
- Create: `tests/test_plugins_cli.py`
- Modify: `plugins.py:1-10` (imports block at top of file)
- Modify: `plugins.py:11-EOF` (append all new functions below the existing `parse_plugin_asset`)

**Interfaces:**
- Consumes (built in Tasks 1–2, import them; do not re-implement):
  - `github_api.parse_repo(repo: str) -> tuple[str, str]`
  - `github_api.fetch_all_releases(owner: str, repo: str) -> list[dict]`
  - `plugins.parse_plugin_asset(filename: str) -> tuple[str, str] | None` → `(plugin, version)`
- Produces (later tasks depend on these exact names and on the `plugins.json` shape):
  - `plugins.read_plugins_csv(path="plugins.csv") -> dict[str, set[str]]`
  - `plugins.summarize_plugin_repo(repo_full_name: str, charted: set[str]) -> dict`
  - `plugins.parse_args()`, `plugins.main()`
  - Output file `plugins.json`:

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

**Domain context for the implementer (this repo is small; none of this is obvious from the code):**
`headlamp-k8s/plugins` publishes one GitHub release per plugin, tagged `<plugin>-<version>`. Which plugin a download belongs to is derived from the **asset filename**, not the tag — six legacy `v0.1.x` tags bundle several plugins' assets under a version-only tag. `parse_plugin_asset` (Task 2) does that derivation. This task turns a repo's raw release list into per-plugin rows.

---

- [ ] **Step 1: Confirm tests can import top-level modules**

Run: `python3 -m pytest tests/ -q` and confirm the existing Task 2 tests import `plugins` successfully. If any test errors with `ModuleNotFoundError: No module named 'plugins'`, the `pythonpath = .` line in `pytest.ini` (added in Task 1) is missing or wrong — fix it there rather than adding a `conftest.py`.

Expected: Task 1–2 tests pass and `import plugins` resolves.

- [ ] **Step 2: Add `tests/__init__.py`**

Cycle C imports a shared helper across test modules (`from tests.test_plugins_summary import make_release`), which requires `tests/` to be a package:

```bash
touch tests/__init__.py
```

---

#### Cycle A — `read_plugins_csv`

- [ ] **Step 3: Write the failing config-reading test**

Create `tests/test_plugins_config.py`:

```python
import pytest

import plugins


def write_csv(tmp_path, text):
    path = tmp_path / "plugins.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_reads_charted_plugin_for_repo(tmp_path):
    path = write_csv(
        tmp_path,
        "repo,plugin,chart\nheadlamp-k8s/plugins,ai-assistant,1\n",
    )
    assert plugins.read_plugins_csv(path) == {
        "headlamp-k8s/plugins": {"ai-assistant"}
    }


def test_chart_zero_row_declares_repo_but_charts_nothing(tmp_path):
    path = write_csv(
        tmp_path,
        "repo,plugin,chart\nheadlamp-k8s/plugins,prometheus,0\n",
    )
    assert plugins.read_plugins_csv(path) == {"headlamp-k8s/plugins": set()}


def test_multiple_rows_for_one_repo_union_their_charted_plugins(tmp_path):
    path = write_csv(
        tmp_path,
        "repo,plugin,chart\n"
        "headlamp-k8s/plugins,ai-assistant,1\n"
        "headlamp-k8s/plugins,flux,1\n"
        "headlamp-k8s/plugins,keda,0\n",
    )
    assert plugins.read_plugins_csv(path) == {
        "headlamp-k8s/plugins": {"ai-assistant", "flux"}
    }


def test_multiple_repos_are_separate_keys(tmp_path):
    path = write_csv(
        tmp_path,
        "repo,plugin,chart\n"
        "headlamp-k8s/plugins,ai-assistant,1\n"
        "someorg/other-plugins,,0\n",
    )
    assert plugins.read_plugins_csv(path) == {
        "headlamp-k8s/plugins": {"ai-assistant"},
        "someorg/other-plugins": set(),
    }


def test_blank_repo_rows_and_whitespace_are_ignored(tmp_path):
    path = write_csv(
        tmp_path,
        "repo,plugin,chart\n"
        "  headlamp-k8s/plugins , ai-assistant , 1 \n"
        ",,\n",
    )
    assert plugins.read_plugins_csv(path) == {
        "headlamp-k8s/plugins": {"ai-assistant"}
    }


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        plugins.read_plugins_csv(str(tmp_path / "nope.csv"))
```

- [ ] **Step 4: Run the test and watch it fail**

Run: `python3 -m pytest tests/test_plugins_config.py -v`
Expected: FAIL — `AttributeError: module 'plugins' has no attribute 'read_plugins_csv'`

- [ ] **Step 5: Implement `read_plugins_csv`**

Add to the imports at the top of `plugins.py` (keep the existing `import re`):

```python
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys

from github_api import fetch_all_releases, parse_repo
```

Append below `parse_plugin_asset`:

```python
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
```

- [ ] **Step 6: Run the test and watch it pass**

Run: `python3 -m pytest tests/test_plugins_config.py -v`
Expected: PASS — 6 passed

- [ ] **Step 7: Create `plugins.csv` and commit cycle A**

Create `plugins.csv`:

```csv
repo,plugin,chart
headlamp-k8s/plugins,ai-assistant,1
```

```bash
git add plugins.py plugins.csv tests/__init__.py tests/test_plugins_config.py
git commit -m "Add plugins.csv config and read_plugins_csv

The repo column drives collection (all plugins in that repo); plugin+chart
drive display only. A chart=0 row is a no-op beyond declaring its repo."
```

---

#### Cycle B — `summarize_plugin_repo`

- [ ] **Step 8: Write the failing summarization test**

Create `tests/test_plugins_summary.py`. Fixtures are synthetic dicts shaped like the GitHub releases API; `fetch_all_releases` is monkeypatched so no network call happens.

```python
import plugins


def make_release(tag, published_at, assets, prerelease=False, draft=False):
    """Synthetic GitHub release dict. assets is a list of (filename, downloads)."""
    return {
        "tag_name": tag,
        "name": tag,
        "published_at": published_at,
        "prerelease": prerelease,
        "draft": draft,
        "assets": [{"name": n, "download_count": c} for n, c in assets],
    }


def install_releases(monkeypatch, releases):
    monkeypatch.setattr(
        plugins, "fetch_all_releases", lambda owner, repo: list(releases)
    )


AI_RELEASES = [
    make_release(
        "ai-assistant-0.1.0-alpha",
        "2025-08-07T14:04:34Z",
        [("ai-assistant-0.1.0-alpha.tar.gz", 81213)],
    ),
    make_release(
        "ai-assistant-0.2.0-alpha",
        "2025-11-12T09:00:00Z",
        [("ai-assistant-0.2.0-alpha.tar.gz", 20086)],
    ),
    make_release(
        "ai-assistant-0.3.0-alpha",
        "2026-05-04T10:30:00Z",
        [("ai-assistant-0.3.0-alpha.tar.gz", 1148)],
    ),
]


def test_groups_assets_into_plugins_with_totals(monkeypatch):
    install_releases(monkeypatch, AI_RELEASES)

    summary = plugins.summarize_plugin_repo(
        "headlamp-k8s/plugins", {"ai-assistant"}
    )

    assert summary["repo"] == "headlamp-k8s/plugins"
    assert len(summary["plugins"]) == 1
    entry = summary["plugins"][0]
    assert entry["plugin"] == "ai-assistant"
    assert entry["chart"] is True
    assert entry["approx_all_time_downloads"] == 102447
    assert entry["releases"] == [
        {
            "tag": "ai-assistant-0.1.0-alpha",
            "version": "0.1.0-alpha",
            "published_at": "2025-08-07T14:04:34Z",
            "prerelease": False,
            "downloads": 81213,
        },
        {
            "tag": "ai-assistant-0.2.0-alpha",
            "version": "0.2.0-alpha",
            "published_at": "2025-11-12T09:00:00Z",
            "prerelease": False,
            "downloads": 20086,
        },
        {
            "tag": "ai-assistant-0.3.0-alpha",
            "version": "0.3.0-alpha",
            "published_at": "2026-05-04T10:30:00Z",
            "prerelease": False,
            "downloads": 1148,
        },
    ]


def test_uncharted_plugins_are_still_collected_and_sorted_by_name(monkeypatch):
    install_releases(
        monkeypatch,
        [
            make_release(
                "prometheus-0.5.0", "2026-01-01T00:00:00Z",
                [("prometheus-0.5.0.tar.gz", 10)],
            ),
            make_release(
                "ai-assistant-0.3.0-alpha", "2026-01-02T00:00:00Z",
                [("ai-assistant-0.3.0-alpha.tar.gz", 20)],
            ),
            make_release(
                "flux-0.2.0", "2026-01-03T00:00:00Z",
                [("flux-0.2.0.tar.gz", 30)],
            ),
        ],
    )

    summary = plugins.summarize_plugin_repo(
        "headlamp-k8s/plugins", {"ai-assistant"}
    )

    assert [p["plugin"] for p in summary["plugins"]] == [
        "ai-assistant",
        "flux",
        "prometheus",
    ]
    assert [p["chart"] for p in summary["plugins"]] == [True, False, False]


def test_releases_are_sorted_oldest_first(monkeypatch):
    install_releases(monkeypatch, list(reversed(AI_RELEASES)))

    summary = plugins.summarize_plugin_repo("headlamp-k8s/plugins", set())

    published = [r["published_at"] for r in summary["plugins"][0]["releases"]]
    assert published == sorted(published)


def test_zero_download_release_is_kept(monkeypatch):
    """D2: unlike releases.py, a brand-new plugin at 0 downloads is real data."""
    install_releases(
        monkeypatch,
        [make_release("argocd-0.1.0", "2026-06-01T00:00:00Z",
                      [("argocd-0.1.0.tar.gz", 0)])],
    )

    summary = plugins.summarize_plugin_repo("headlamp-k8s/plugins", set())

    entry = summary["plugins"][0]
    assert entry["plugin"] == "argocd"
    assert entry["approx_all_time_downloads"] == 0
    assert len(entry["releases"]) == 1
    assert entry["releases"][0]["downloads"] == 0


def test_prerelease_comes_only_from_the_github_flag(monkeypatch):
    """D3: an -alpha version with prerelease=false must stay false."""
    install_releases(
        monkeypatch,
        [
            make_release("ai-assistant-0.3.0-alpha", "2026-01-01T00:00:00Z",
                         [("ai-assistant-0.3.0-alpha.tar.gz", 5)],
                         prerelease=False),
            make_release("flux-1.0.0", "2026-01-02T00:00:00Z",
                         [("flux-1.0.0.tar.gz", 5)],
                         prerelease=True),
        ],
    )

    summary = plugins.summarize_plugin_repo("headlamp-k8s/plugins", set())
    flags = {
        p["plugin"]: p["releases"][0]["prerelease"] for p in summary["plugins"]
    }
    assert flags == {"ai-assistant": False, "flux": True}


def test_draft_releases_are_skipped(monkeypatch):
    install_releases(
        monkeypatch,
        [
            make_release("flux-0.1.0", "2026-01-01T00:00:00Z",
                         [("flux-0.1.0.tar.gz", 7)]),
            make_release("flux-0.2.0", "2026-01-02T00:00:00Z",
                         [("flux-0.2.0.tar.gz", 999)], draft=True),
        ],
    )

    summary = plugins.summarize_plugin_repo("headlamp-k8s/plugins", set())

    entry = summary["plugins"][0]
    assert [r["tag"] for r in entry["releases"]] == ["flux-0.1.0"]
    assert entry["approx_all_time_downloads"] == 7


def test_same_asset_name_under_two_tags_yields_two_rows(monkeypatch):
    """Real data: legacy v0.1.x tags re-ship an identically named asset with a
    different download_count. Rows are keyed by tag, so both must survive."""
    install_releases(
        monkeypatch,
        [
            make_release("v0.1.3", "2024-03-01T00:00:00Z",
                         [("app-catalog-0.1.3.tgz", 1448)]),
            make_release("v0.1.4", "2024-04-01T00:00:00Z",
                         [("app-catalog-0.1.3.tgz", 924),
                          ("prometheus-0.0.1.tgz", 919)]),
            make_release("v0.1.4-alpha", "2024-03-15T00:00:00Z",
                         [("prometheus-0.0.1.tgz", 7)]),
        ],
    )

    summary = plugins.summarize_plugin_repo("headlamp-k8s/plugins", set())
    by_name = {p["plugin"]: p for p in summary["plugins"]}

    app_catalog = by_name["app-catalog"]
    assert [(r["tag"], r["version"], r["downloads"]) for r in app_catalog["releases"]] == [
        ("v0.1.3", "0.1.3", 1448),
        ("v0.1.4", "0.1.3", 924),
    ]
    assert app_catalog["approx_all_time_downloads"] == 2372

    prometheus = by_name["prometheus"]
    assert [(r["tag"], r["version"], r["downloads"]) for r in prometheus["releases"]] == [
        ("v0.1.4-alpha", "0.0.1", 7),
        ("v0.1.4", "0.0.1", 919),
    ]
    assert prometheus["approx_all_time_downloads"] == 926


def test_unparseable_asset_is_counted_and_reported_not_fatal(monkeypatch, capsys):
    install_releases(
        monkeypatch,
        [
            make_release("flux-0.1.0", "2026-01-01T00:00:00Z",
                         [("flux-0.1.0.tar.gz", 7),
                          ("checksums.txt", 3)]),
        ],
    )

    summary = plugins.summarize_plugin_repo("headlamp-k8s/plugins", set())

    assert [p["plugin"] for p in summary["plugins"]] == ["flux"]
    assert summary["plugins"][0]["approx_all_time_downloads"] == 7
    err = capsys.readouterr().err
    assert "1" in err and "unparseable" in err.lower()


def test_charted_plugin_missing_from_repo_warns_and_is_skipped(monkeypatch, capsys):
    install_releases(
        monkeypatch,
        [make_release("flux-0.1.0", "2026-01-01T00:00:00Z",
                      [("flux-0.1.0.tar.gz", 7)])],
    )

    summary = plugins.summarize_plugin_repo(
        "headlamp-k8s/plugins", {"flux", "does-not-exist"}
    )

    assert [p["plugin"] for p in summary["plugins"]] == ["flux"]
    assert summary["plugins"][0]["chart"] is True
    err = capsys.readouterr().err
    assert "does-not-exist" in err
```

- [ ] **Step 9: Run the test and watch it fail**

Run: `python3 -m pytest tests/test_plugins_summary.py -v`
Expected: FAIL — `AttributeError: module 'plugins' has no attribute 'summarize_plugin_repo'`

- [ ] **Step 10: Implement `summarize_plugin_repo`**

Append to `plugins.py`:

```python
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
```

- [ ] **Step 11: Run the test and watch it pass**

Run: `python3 -m pytest tests/test_plugins_summary.py -v`
Expected: PASS — 9 passed

- [ ] **Step 12: Commit cycle B**

```bash
git add plugins.py tests/test_plugins_summary.py
git commit -m "Add summarize_plugin_repo with per-tag release rows

Rows are keyed by tag, not version: the same asset filename appears under
two different tags with different counts (app-catalog-0.1.3.tgz in both
v0.1.3 and v0.1.4). Zero-download releases are kept, unlike releases.py."
```

---

#### Cycle C — CLI

- [ ] **Step 13: Write the failing CLI test**

Create `tests/test_plugins_cli.py`:

```python
import json

import pytest

import plugins
from tests.test_plugins_summary import make_release


FIXTURE_RELEASES = [
    make_release("ai-assistant-0.1.0-alpha", "2025-08-07T14:04:34Z",
                 [("ai-assistant-0.1.0-alpha.tar.gz", 81213)]),
    make_release("ai-assistant-0.2.0-alpha", "2025-11-12T09:00:00Z",
                 [("ai-assistant-0.2.0-alpha.tar.gz", 20086)]),
    make_release("ai-assistant-0.3.0-alpha", "2026-05-04T10:30:00Z",
                 [("ai-assistant-0.3.0-alpha.tar.gz", 1148)]),
    make_release("prometheus-0.5.0", "2026-01-01T00:00:00Z",
                 [("prometheus-0.5.0.tar.gz", 40)]),
    make_release("prometheus-0.6.0", "2026-02-01T00:00:00Z",
                 [("prometheus-0.6.0.tar.gz", 50)]),
]


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    (tmp_path / "plugins.csv").write_text(
        "repo,plugin,chart\nheadlamp-k8s/plugins,ai-assistant,1\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        plugins, "fetch_all_releases", lambda owner, repo: list(FIXTURE_RELEASES)
    )
    return tmp_path


def run_main(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["plugins.py"] + argv)
    plugins.main()


def test_json_output_dir_writes_plugins_json(workdir, monkeypatch):
    run_main(monkeypatch, ["--json", "--output-dir", "out", "-n", "0"])

    payload = json.loads((workdir / "out" / "plugins.json").read_text())
    assert payload["generated_at"].endswith("Z")
    assert len(payload["repos"]) == 1
    entries = {p["plugin"]: p for p in payload["repos"][0]["plugins"]}
    assert set(entries) == {"ai-assistant", "prometheus"}
    assert entries["ai-assistant"]["chart"] is True
    assert entries["ai-assistant"]["approx_all_time_downloads"] == 102447
    assert entries["prometheus"]["chart"] is False


def test_num_releases_trims_per_plugin_not_per_repo(workdir, monkeypatch):
    run_main(monkeypatch, ["--json", "--output-dir", "out", "-n", "2"])

    payload = json.loads((workdir / "out" / "plugins.json").read_text())
    entries = {p["plugin"]: p for p in payload["repos"][0]["plugins"]}

    # Every plugin keeps its own last 2 releases; prometheus does not crowd
    # ai-assistant out of a shared repo-wide window.
    assert [r["tag"] for r in entries["ai-assistant"]["releases"]] == [
        "ai-assistant-0.2.0-alpha",
        "ai-assistant-0.3.0-alpha",
    ]
    assert [r["tag"] for r in entries["prometheus"]["releases"]] == [
        "prometheus-0.5.0",
        "prometheus-0.6.0",
    ]
    # All-time totals are unaffected by trimming.
    assert entries["ai-assistant"]["approx_all_time_downloads"] == 102447


def test_json_to_stdout_when_no_output_dir(workdir, monkeypatch, capsys):
    run_main(monkeypatch, ["--json", "-n", "0"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["repos"][0]["repo"] == "headlamp-k8s/plugins"


def test_text_report_is_the_default(workdir, monkeypatch, capsys):
    run_main(monkeypatch, ["-n", "0"])

    out = capsys.readouterr().out
    assert "headlamp-k8s/plugins" in out
    assert "ai-assistant" in out
    assert "102,447" in out


def test_missing_plugins_csv_exits_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch, ["--json"])
    assert exc.value.code == 0
```

- [ ] **Step 14: Run the test and watch it fail**

Run: `python3 -m pytest tests/test_plugins_cli.py -v`
Expected: FAIL — `AttributeError: module 'plugins' has no attribute 'main'`

- [ ] **Step 15: Implement `parse_args`, the text report, and `main`**

Append to `plugins.py`:

```python
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
```

Note: `dt.datetime.utcnow()` is deprecated in Python 3.12 but is used here deliberately to match `releases.py:325`, so both files emit an identically formatted `generated_at`. Changing one without the other would be a silent inconsistency.

- [ ] **Step 16: Run the CLI test and watch it pass**

Run: `python3 -m pytest tests/test_plugins_cli.py -v`
Expected: PASS — 5 passed

- [ ] **Step 17: Run the whole suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS — all Task 1–3 tests green.

- [ ] **Step 18: Commit cycle C**

```bash
git add plugins.py tests/test_plugins_cli.py
git commit -m "Add plugins.py CLI with per-plugin release trimming

--num-releases trims per plugin rather than per repo, so a plugin with many
releases cannot crowd others out of a shared repo-wide window."
```

---

#### Verification

- [ ] **Step 19: Manual end-to-end check against the live API**

Not part of the automated suite — it makes real network calls and its numbers drift as downloads accrue. Run once by hand with `GITHUB_TOKEN` exported:

```bash
python3 plugins.py --json --output-dir /tmp/plugincheck --num-releases 0
python3 -c "
import json
d = json.load(open('/tmp/plugincheck/plugins.json'))
r = d['repos'][0]
print('plugins:', len(r['plugins']))
a = [p for p in r['plugins'] if p['plugin'] == 'ai-assistant'][0]
print('total:', a['approx_all_time_downloads'])
for x in a['releases']:
    print('  ', x['tag'], x['downloads'], 'prerelease=' + str(x['prerelease']))
"
```

Expected, matching the live API as of 2026-08-11 (totals only grow over time; the relationships must hold exactly):
- 21 plugins in `headlamp-k8s/plugins` (collected from 94 releases)
- `ai-assistant`: 3 releases, `approx_all_time_downloads` 102447, with `ai-assistant-0.1.0-alpha`=81213, `ai-assistant-0.2.0-alpha`=20086, `ai-assistant-0.3.0-alpha`=1148
- all three ai-assistant releases report `prerelease: False` despite their `-alpha` versions (D3)
- no "unparseable asset name" warning on stderr (currently zero occur)

If the plugin count or the ai-assistant total has changed, do not adjust the fixture tests — the fixtures are synthetic and independent. Investigate only if the *relationships* break (e.g. a plugin count far from 21, or a nonzero unparseable count, which signals a new asset naming scheme).

---
### Task 4: Refactor `build_site.py` to parameterized metrics (no behavior change)

**Files:**
- Create: `tests/fixtures/platform_snapshots/2026-08-05.json`
- Create: `tests/fixtures/platform_snapshots/2026-08-07.json`
- Create: `tests/fixtures/platform_snapshots/2026-08-11.json`
- Create: `tests/generate_golden.py` (one-shot generator, run against the **pre-refactor** code)
- Create: `tests/fixtures/golden_history.json` (generated output, committed)
- Create: `tests/test_build_site_refactor.py`
- Modify: `build_site.py:69-150` (replace `build_repo_index`, `diff_snapshots`, `compute_weekly_history`; keep `build_history_json` behavior)
- Modify: `build_site.py:171-177` (call sites in `main`)

**Interfaces:**
- Consumes: `pytest` test runner and `tests/` package layout established in Task 1.
- Produces, relied on by Task 5:
  - `build_site.PLATFORM_METRICS: list[str]`
  - `build_site.PLUGIN_METRICS: list[str]`
  - `build_site.build_platform_index(snapshot_data) -> dict[tuple[str], dict[str, dict[str, int]]]`
  - `build_site.build_plugin_index(snapshot_data) -> dict[tuple[str, str], dict[str, dict[str, int]]]`
  - `build_site.diff_snapshots(older_index, newer_index, metrics) -> dict[tuple, dict[str, int]]`
  - `build_site.compute_weekly_history(snapshots, index_fn, metrics) -> dict[tuple, dict[str, dict[str, int]]]`
  - `build_site.build_history_json(weekly) -> dict`

**Why byte-identity holds (state this in the commit message):** the refactor changes only *how* keys and metric names are spelled, never the order anything is produced in. `build_platform_index` still walks `snapshot_data["repos"]` in file order and still builds each tag's metric dict as `linux, mac, win` in that order, because `PLATFORM_METRICS` preserves the literal order of the old hardcoded dict. `compute_weekly_history` still seeds each week entry from `{m: 0 for m in metrics}`, so the per-week dict's insertion order is unchanged, and `build_history_json` still emits `{"week": ...}` first and then `.update()`s the metrics on top. The only semantic change is that the top-level index key becomes a 1-tuple `(repo,)` instead of the bare string `repo` — and since `sorted()` over 1-tuples of strings orders identically to `sorted()` over those strings, the repo ordering in the output is also unchanged. `json.dump(..., indent=2)` is therefore fed a structurally identical object graph in an identical order, which is what makes the byte comparison the right assertion rather than an over-strict one.

---

- [ ] **Step 1: Create the three synthetic platform snapshot fixtures**

Three snapshots across two ISO weeks (2026-08-05 Wed and 2026-08-07 Fri are both in week Monday 2026-08-03; 2026-08-11 Tue is in week Monday 2026-08-10), two repos, one deliberate **decrease** (`acme/tool` `v1.1` mac goes 5 → 4), and one tag that appears only in the newest snapshot (`v1.2`).

`tests/fixtures/platform_snapshots/2026-08-05.json`:

```json
{
  "generated_at": "2026-08-05T06:00:00Z",
  "repos": [
    {
      "repo": "acme/tool",
      "releases": [
        { "tag": "v1.0", "linux": 100, "mac": 50, "win": 20 },
        { "tag": "v1.1", "linux": 10, "mac": 5, "win": 1 }
      ]
    },
    {
      "repo": "beta/app",
      "releases": [{ "tag": "v2.0", "linux": 7, "mac": 3, "win": 2 }]
    }
  ]
}
```

`tests/fixtures/platform_snapshots/2026-08-07.json`:

```json
{
  "generated_at": "2026-08-07T06:00:00Z",
  "repos": [
    {
      "repo": "acme/tool",
      "releases": [
        { "tag": "v1.0", "linux": 110, "mac": 50, "win": 25 },
        { "tag": "v1.1", "linux": 15, "mac": 4, "win": 1 }
      ]
    },
    {
      "repo": "beta/app",
      "releases": [{ "tag": "v2.0", "linux": 9, "mac": 3, "win": 2 }]
    }
  ]
}
```

`tests/fixtures/platform_snapshots/2026-08-11.json`:

```json
{
  "generated_at": "2026-08-11T06:00:00Z",
  "repos": [
    {
      "repo": "acme/tool",
      "releases": [
        { "tag": "v1.0", "linux": 120, "mac": 55, "win": 25 },
        { "tag": "v1.1", "linux": 15, "mac": 8, "win": 3 },
        { "tag": "v1.2", "linux": 4, "mac": 2, "win": 1 }
      ]
    },
    {
      "repo": "beta/app",
      "releases": [{ "tag": "v2.0", "linux": 9, "mac": 3, "win": 2 }]
    }
  ]
}
```

---

- [ ] **Step 2: Write the one-shot golden generator**

`tests/generate_golden.py`:

```python
#!/usr/bin/env python3
"""Generate the platform golden fixture from build_site.py.

Run this EXACTLY ONCE, against the pre-refactor build_site.py. The committed
output is the byte-for-byte contract that the metric-parameterization refactor
must preserve. If tests/test_build_site_refactor.py ever fails, the refactor is
wrong -- do NOT re-run this script to make the failure go away.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_site  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(HERE, "fixtures", "platform_snapshots")
GOLDEN = os.path.join(HERE, "fixtures", "golden_history.json")


def main():
    snapshots = build_site.load_all_snapshots(SNAPSHOT_DIR)
    weekly = build_site.compute_weekly_history(snapshots)
    history = build_site.build_history_json(weekly)
    with open(GOLDEN, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    print("Wrote {}".format(GOLDEN))


if __name__ == "__main__":
    main()
```

Note it calls the current single-argument `compute_weekly_history`, and it uses `json.dump(..., indent=2)` — identical to `save_json`, and emitting **no trailing newline**. Do not let an editor add one; the test compares the file bytes.

The filename has no `test_` prefix, so pytest will not collect it as a test module.

---

- [ ] **Step 3: Generate the golden fixture and verify it by hand**

Run: `python3 tests/generate_golden.py && cat tests/fixtures/golden_history.json`

Expected — confirm these numbers before trusting the fixture, since everything downstream is pinned to them:

- `acme/tool` week `2026-08-03`: linux 15 (`v1.0` +10, `v1.1` +5), mac **0** (`v1.1` −1 is clamped, `v1.0` unchanged), win 5.
- `acme/tool` week `2026-08-10`: linux 14 (`v1.0` +10, new `v1.2` +4), mac 11 (`v1.0` +5, `v1.1` +4, `v1.2` +2), win 3 (`v1.1` +2, `v1.2` +1).
- `beta/app` week `2026-08-03`: linux 2, mac 0, win 0.
- `beta/app` week `2026-08-10`: linux 0, mac 0, win 0.
- Repo order is `acme/tool` then `beta/app`; each week entry has keys in the order `week, linux, mac, win`.

If any number differs, stop — the fixtures are wrong, not the code.

---

- [ ] **Step 4: Write the failing regression test**

`tests/test_build_site_refactor.py`:

```python
"""Regression gate for the metric-parameterization refactor of build_site.py.

The golden fixture was generated from the pre-refactor implementation. The
refactored code must reproduce it byte for byte -- the assertion compares the
serialized JSON string, not parsed objects, so key ordering counts.
"""

import json
import os

import build_site

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(HERE, "fixtures", "platform_snapshots")
GOLDEN = os.path.join(HERE, "fixtures", "golden_history.json")


def test_platform_output_is_byte_identical_to_golden():
    snapshots = build_site.load_all_snapshots(SNAPSHOT_DIR)
    weekly = build_site.compute_weekly_history(
        snapshots, build_site.build_platform_index, build_site.PLATFORM_METRICS
    )
    history = build_site.build_history_json(weekly)
    produced = json.dumps(history, indent=2)

    with open(GOLDEN, "r", encoding="utf-8") as f:
        expected = f.read()

    assert produced == expected


def test_metric_constants_preserve_platform_key_order():
    assert build_site.PLATFORM_METRICS == ["linux", "mac", "win"]
    assert build_site.PLUGIN_METRICS == ["downloads"]


def test_build_platform_index_keys_are_one_tuples():
    snapshot = {
        "repos": [
            {
                "repo": "acme/tool",
                "releases": [{"tag": "v1.0", "linux": 1, "mac": 2, "win": 3}],
            }
        ]
    }
    index = build_site.build_platform_index(snapshot)
    assert list(index.keys()) == [("acme/tool",)]
    assert index[("acme/tool",)] == {"v1.0": {"linux": 1, "mac": 2, "win": 3}}
    assert list(index[("acme/tool",)]["v1.0"].keys()) == ["linux", "mac", "win"]


def test_build_platform_index_defaults_missing_metrics_to_zero():
    snapshot = {"repos": [{"repo": "acme/tool", "releases": [{"tag": "v1.0"}]}]}
    index = build_site.build_platform_index(snapshot)
    assert index[("acme/tool",)]["v1.0"] == {"linux": 0, "mac": 0, "win": 0}


def test_diff_snapshots_clamps_decreases_to_zero():
    older = {("acme/tool",): {"v1.0": {"linux": 10, "mac": 10, "win": 10}}}
    newer = {("acme/tool",): {"v1.0": {"linux": 4, "mac": 12, "win": 10}}}
    assert build_site.diff_snapshots(older, newer, build_site.PLATFORM_METRICS) == {
        ("acme/tool",): {"linux": 0, "mac": 2, "win": 0}
    }


def test_diff_snapshots_treats_absent_key_as_all_zeros():
    older = {}
    newer = {("new/repo",): {"v1.0": {"linux": 5, "mac": 0, "win": 0}}}
    assert build_site.diff_snapshots(older, newer, build_site.PLATFORM_METRICS) == {
        ("new/repo",): {"linux": 5, "mac": 0, "win": 0}
    }


def test_compute_weekly_history_returns_empty_for_fewer_than_two_snapshots():
    snapshots = [("2026-08-11", {"repos": []})]
    weekly = build_site.compute_weekly_history(
        snapshots, build_site.build_platform_index, build_site.PLATFORM_METRICS
    )
    assert weekly == {}
```

---

- [ ] **Step 5: Run the test and watch it fail**

Run: `python3 -m pytest tests/test_build_site_refactor.py -v`

Expected: FAIL. `test_platform_output_is_byte_identical_to_golden` and `test_compute_weekly_history_returns_empty_for_fewer_than_two_snapshots` fail with `TypeError: compute_weekly_history() takes 1 positional argument but 3 were given`; the remaining tests fail with `AttributeError: module 'build_site' has no attribute 'PLATFORM_METRICS'` / `'build_platform_index'` / `TypeError: diff_snapshots() takes 2 positional arguments but 3 were given`.

---

- [ ] **Step 6: Apply the refactor to `build_site.py`**

Replace lines 69-150 (`build_repo_index` through `build_history_json`) with the target implementation. `build_repo_index` is **renamed** to `build_platform_index` and returns 1-tuple keys; `build_plugin_index`, `PLATFORM_METRICS`, and `PLUGIN_METRICS` are new; `build_history_json` is unchanged in behavior and only reads `key[0]` instead of the bare repo name.

```python
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
    """Index a plugin snapshot as {(repo, plugin): {tag: {metric: count}}}."""
    index = {}
    for repo_data in snapshot_data.get("repos", []):
        repo = repo_data["repo"]
        for plugin_data in repo_data.get("plugins", []):
            tags = {}
            for rel in plugin_data.get("releases", []):
                tags[rel["tag"]] = {m: rel.get(m, 0) for m in PLUGIN_METRICS}
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
```

---

- [ ] **Step 7: Update the two call sites in `main`**

In `build_site.py`, replace lines 171-177:

```python
    # Compute weekly history
    weekly = compute_weekly_history(snapshots, build_platform_index, PLATFORM_METRICS)

    # Ensure all repos appear in history even if no weekly data yet
    for repo_data in data_json.get("repos", []):
        weekly.setdefault((repo_data["repo"],), {})
```

The `setdefault` key is now a 1-tuple to match `build_platform_index`. Getting this wrong is the one way to silently break byte-identity (a bare string key would sort against tuples and raise `TypeError` in `sorted(weekly)`), which is exactly what Step 8's end-to-end check catches.

---

- [ ] **Step 8: Run the tests and the real script**

Run: `python3 -m pytest tests/ -v`

Expected: PASS, all tests in `tests/test_build_site_refactor.py` green, and all Task 1-3 tests still green.

Then confirm `main()` itself still runs end to end:

```bash
rm -rf /tmp/rt-check
mkdir -p /tmp/rt-check/site /tmp/rt-check/snaps
cp tests/fixtures/platform_snapshots/*.json /tmp/rt-check/snaps/
cp tests/fixtures/platform_snapshots/2026-08-11.json /tmp/rt-check/site/data.json
python3 build_site.py --site-dir /tmp/rt-check/site --snapshots-dir /tmp/rt-check/snaps
python3 -c "import json; d=json.load(open('/tmp/rt-check/site/history.json')); print([r['repo'] for r in d['repos']])"
```

Expected: exits 0, prints the snapshot/history messages, and prints `['acme/tool', 'beta/app']`. (Today's date adds a fourth snapshot here, so the week totals differ from the golden fixture — that is expected; this check is for "does `main` still run and key correctly", not for values.)

---

- [ ] **Step 9: Commit**

```bash
git add build_site.py tests/generate_golden.py tests/test_build_site_refactor.py tests/fixtures/
git commit -m "Parameterize build_site metrics; golden-fixture regression gate

build_repo_index becomes build_platform_index with (repo,) tuple keys;
diff_snapshots/compute_weekly_history take metric keys and an index
function. build_plugin_index and PLUGIN_METRICS are added for the plugin
track. Platform output is unchanged: iteration order, metric-dict
insertion order, and sort order are all preserved, and 1-tuples of
strings sort identically to the strings themselves. Verified by
comparing the serialized JSON against a golden fixture generated from
the pre-refactor implementation."
```

---

### Task 5: Plugin snapshot track in `build_site.py`

**Files:**
- Modify: `build_site.py` — `parse_args` (add `--plugin-snapshots-dir`), new `build_plugins_history_json` and `run_plugin_track` after `build_history_json`, and a plugin-track block at the end of `main`
- Test: `tests/test_plugin_track.py`

**Interfaces:**
- Consumes (from Task 4): `build_site.build_plugin_index(snapshot_data)`, `build_site.PLUGIN_METRICS`, `build_site.compute_weekly_history(snapshots, index_fn, metrics)`, `build_site.save_snapshot(data_json, snapshots_dir)`, `build_site.load_all_snapshots(snapshots_dir)`, `build_site.save_json(path, data)`, `build_site.load_json(path)`
- Produces:
  - `build_site.build_plugins_history_json(weekly) -> dict`
  - `build_site.run_plugin_track(plugins_json, plugin_snapshots_dir, site_dir) -> str` (path written)
  - CLI flag `--plugin-snapshots-dir`
  - Output file `<site-dir>/plugins-history.json`, consumed by Task 6

**Spec refinement — one new flag, not two.** The design doc says "New arguments `--plugin-site-dir` and `--plugin-snapshots-dir`". Only `--plugin-snapshots-dir` is added. A separate plugin site directory would be write-only ceremony: `plugins.json` is produced by `plugins.py --output-dir _site/` into the *same* directory that already holds `data.json`, and `plugins-history.json` must land next to `history.json` for the dashboard to fetch both with relative URLs. Two site dirs would have to be passed the same value on every invocation. So the plugin track reads `plugins.json` from and writes `plugins-history.json` to the existing `--site-dir`, and `--plugin-snapshots-dir` alone gates the track. Carry this refinement into Task 7.

The existing `snapshots/` and `history.json` are untouched — the plugin track is a second, independent pipeline appended after the platform one, with no migration and no shared state beyond the pure helper functions.

---

- [ ] **Step 1: Write the failing tests**

`tests/test_plugin_track.py`:

```python
"""Plugin snapshot track: weekly deltas, decrease guard, first run, and skip."""

import json
import os
import subprocess
import sys

import build_site

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SNAP_2026_08_07 = {
    "generated_at": "2026-08-07T06:00:00Z",
    "repos": [
        {
            "repo": "headlamp-k8s/plugins",
            "plugins": [
                {
                    "plugin": "ai-assistant",
                    "chart": True,
                    "releases": [
                        {"tag": "ai-assistant-0.1.0-alpha", "downloads": 81213},
                        {"tag": "ai-assistant-0.2.0-alpha", "downloads": 20086},
                    ],
                },
                {
                    "plugin": "flux",
                    "chart": False,
                    "releases": [{"tag": "flux-1.0.0", "downloads": 100}],
                },
            ],
        }
    ],
}

SNAP_2026_08_11 = {
    "generated_at": "2026-08-11T06:00:00Z",
    "repos": [
        {
            "repo": "headlamp-k8s/plugins",
            "plugins": [
                {
                    "plugin": "ai-assistant",
                    "chart": True,
                    "releases": [
                        {"tag": "ai-assistant-0.1.0-alpha", "downloads": 81300},
                        {"tag": "ai-assistant-0.2.0-alpha", "downloads": 20086},
                        {"tag": "ai-assistant-0.3.0-alpha", "downloads": 25},
                    ],
                },
                {
                    "plugin": "flux",
                    "chart": False,
                    # Re-uploaded asset: count went DOWN from 100.
                    "releases": [{"tag": "flux-1.0.0", "downloads": 90}],
                },
            ],
        }
    ],
}


def _weekly(snapshots):
    return build_site.compute_weekly_history(
        snapshots, build_site.build_plugin_index, build_site.PLUGIN_METRICS
    )


def test_two_snapshots_produce_per_plugin_weekly_deltas():
    snapshots = [("2026-08-07", SNAP_2026_08_07), ("2026-08-11", SNAP_2026_08_11)]
    history = build_site.build_plugins_history_json(_weekly(snapshots))

    # 2026-08-11 is a Tuesday; its ISO week starts Monday 2026-08-10.
    # ai-assistant: +87 on 0.1.0, +0 on 0.2.0, +25 for the new 0.3.0 tag.
    assert history == {
        "repos": [
            {
                "repo": "headlamp-k8s/plugins",
                "plugins": [
                    {
                        "plugin": "ai-assistant",
                        "weeks": [{"week": "2026-08-10", "downloads": 112}],
                    },
                    {
                        "plugin": "flux",
                        "weeks": [{"week": "2026-08-10", "downloads": 0}],
                    },
                ],
            }
        ]
    }


def test_decreasing_count_contributes_zero_never_negative():
    snapshots = [("2026-08-07", SNAP_2026_08_07), ("2026-08-11", SNAP_2026_08_11)]
    weekly = _weekly(snapshots)
    assert weekly[("headlamp-k8s/plugins", "flux")] == {"2026-08-10": {"downloads": 0}}


def test_first_run_with_no_prior_snapshots_produces_empty_weeks(tmp_path):
    site_dir = tmp_path / "site"
    snaps_dir = tmp_path / "plugin-snapshots"
    site_dir.mkdir()

    out_path = build_site.run_plugin_track(
        SNAP_2026_08_11, str(snaps_dir), str(site_dir)
    )

    with open(out_path, "r", encoding="utf-8") as f:
        history = json.load(f)

    assert history == {
        "repos": [
            {
                "repo": "headlamp-k8s/plugins",
                "plugins": [
                    {"plugin": "ai-assistant", "weeks": []},
                    {"plugin": "flux", "weeks": []},
                ],
            }
        ]
    }


def _run_build_site(site_dir, snaps_dir, plugin_snaps_dir=None):
    cmd = [
        sys.executable,
        os.path.join(REPO_ROOT, "build_site.py"),
        "--site-dir",
        str(site_dir),
        "--snapshots-dir",
        str(snaps_dir),
    ]
    if plugin_snaps_dir is not None:
        cmd += ["--plugin-snapshots-dir", str(plugin_snaps_dir)]
    return subprocess.run(cmd, capture_output=True, text=True)


def _write_platform_data(site_dir):
    data = {
        "generated_at": "2026-08-11T06:00:00Z",
        "repos": [
            {
                "repo": "acme/tool",
                "releases": [{"tag": "v1.0", "linux": 1, "mac": 2, "win": 3}],
            }
        ],
    }
    with open(os.path.join(str(site_dir), "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def test_plugin_track_skipped_when_plugins_json_absent(tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    snaps_dir = tmp_path / "snapshots"
    plugin_snaps_dir = tmp_path / "plugin-snapshots"
    _write_platform_data(site_dir)

    proc = _run_build_site(site_dir, snaps_dir, plugin_snaps_dir)

    assert proc.returncode == 0, proc.stderr
    assert "skipping plugin track" in proc.stdout
    assert not (site_dir / "plugins-history.json").exists()

    # Platform track unaffected.
    with open(str(site_dir / "history.json"), "r", encoding="utf-8") as f:
        assert json.load(f) == {"repos": [{"repo": "acme/tool", "weeks": []}]}


def test_plugin_track_skipped_when_flag_omitted(tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    snaps_dir = tmp_path / "snapshots"
    _write_platform_data(site_dir)
    with open(str(site_dir / "plugins.json"), "w", encoding="utf-8") as f:
        json.dump(SNAP_2026_08_11, f, indent=2)

    proc = _run_build_site(site_dir, snaps_dir)

    assert proc.returncode == 0, proc.stderr
    assert "skipping plugin track" in proc.stdout
    assert not (site_dir / "plugins-history.json").exists()
    assert (site_dir / "history.json").exists()
```

---

- [ ] **Step 2: Run the tests and watch them fail**

Run: `python3 -m pytest tests/test_plugin_track.py -v`

Expected: FAIL. The first three fail with `AttributeError: module 'build_site' has no attribute 'build_plugins_history_json'` / `'run_plugin_track'`; the last two fail on `assert proc.returncode == 0` with `argparse` reporting `unrecognized arguments: --plugin-snapshots-dir` (exit 2), and `test_plugin_track_skipped_when_flag_omitted` additionally fails its `"skipping plugin track" in proc.stdout` assertion.

---

- [ ] **Step 3: Add the `--plugin-snapshots-dir` argument**

In `build_site.py`, inside `parse_args`, before `return parser.parse_args()`:

```python
    parser.add_argument(
        "--plugin-snapshots-dir",
        default=None,
        help=(
            "Directory with existing plugin snapshots (from gh-pages checkout). "
            "New plugin snapshot saved here too. If omitted, the plugin track is "
            "skipped. plugins.json is read from --site-dir."
        ),
    )
```

Optional by design: an existing invocation that does not pass it keeps working exactly as before.

---

- [ ] **Step 4: Add the plugin emitter and track runner**

In `build_site.py`, after `build_history_json`:

```python
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
```

`sorted(weekly)` over `(repo, plugin)` tuples means plugins land in the `by_repo` lists already alphabetized within each repo, so no second sort is needed.

---

- [ ] **Step 5: Wire the track into `main`**

At the end of `build_site.py`'s `main`, after `print("Wrote {}".format(history_path))`:

```python
    # --- Plugin track (independent; never affects the platform output above) ---
    if not args.plugin_snapshots_dir:
        print("No --plugin-snapshots-dir given; skipping plugin track.")
        return

    plugins_path = os.path.join(args.site_dir, "plugins.json")
    if not os.path.exists(plugins_path):
        print("No {}; skipping plugin track.".format(plugins_path))
        return

    run_plugin_track(load_json(plugins_path), args.plugin_snapshots_dir, args.site_dir)
```

Both skip paths `return` after the platform output is already written, and both print a message containing "skipping plugin track", which is what the tests assert on.

---

- [ ] **Step 6: Run the tests and watch them pass**

Run: `python3 -m pytest tests/ -v`

Expected: PASS — all of `tests/test_plugin_track.py` green, and `tests/test_build_site_refactor.py` still byte-identical to the golden fixture (the plugin track must not have perturbed the platform path).

---

- [ ] **Step 7: Verify the happy path end to end**

```bash
rm -rf /tmp/rt-plugins
mkdir -p /tmp/rt-plugins/site /tmp/rt-plugins/snaps /tmp/rt-plugins/psnaps
cp tests/fixtures/platform_snapshots/2026-08-11.json /tmp/rt-plugins/site/data.json
python3 -c "
import json, sys
sys.path.insert(0, 'tests')
from test_plugin_track import SNAP_2026_08_07, SNAP_2026_08_11
json.dump(SNAP_2026_08_07, open('/tmp/rt-plugins/psnaps/2026-08-07.json','w'), indent=2)
json.dump(SNAP_2026_08_11, open('/tmp/rt-plugins/site/plugins.json','w'), indent=2)
"
python3 build_site.py --site-dir /tmp/rt-plugins/site --snapshots-dir /tmp/rt-plugins/snaps \
  --plugin-snapshots-dir /tmp/rt-plugins/psnaps
python3 -m json.tool /tmp/rt-plugins/site/plugins-history.json
```

Expected: exits 0, prints "Saved plugin snapshot", "Total plugin snapshots: 2", and "Wrote .../plugins-history.json", then prints a document with one repo `headlamp-k8s/plugins` containing `ai-assistant` and `flux`, each with a single week entry keyed on the current week's Monday. (The week label and the totals depend on today's date, since the second snapshot is written as today's — the shape is what this checks.)

---

- [ ] **Step 8: Commit**

```bash
git add build_site.py tests/test_plugin_track.py
git commit -m "Add plugin snapshot track to build_site.py

Adds --plugin-snapshots-dir, run_plugin_track, and
build_plugins_history_json, writing <site-dir>/plugins-history.json from
<site-dir>/plugins.json via the shared diff/weekly logic. The design doc
also listed a --plugin-site-dir; it is omitted because plugins.json and
plugins-history.json both live in the existing --site-dir alongside
data.json and history.json, so a second site dir would always be passed
the same value.

The track is skipped with a message when the flag is absent or
plugins.json does not exist; snapshots/ and history.json are untouched
and no migration is required."
```

---
### Task 6: Dashboard plugin card

**Files:**
- Modify: `site/index.html:125-129` (add plugin color to `COLORS`)
- Modify: `site/index.html:254-283` (generalize `setupToggle` signature)
- Modify: `site/index.html:283-284` (insert plugin builders + `buildPluginCard` between `setupToggle` and `buildCard`)
- Modify: `site/index.html:318-357` (`init`: fetch plugin files, render plugin cards)
- Test: manual — no JS test runner exists in this repo and none is to be added; see verification steps below

**Interfaces:**
- Consumes `_site/plugins.json` from Task 3 and `_site/plugins-history.json` from Task 5 (shapes given in the plan header's Real Data Reference and in those tasks' Produces blocks).
- Produces: one additional dashboard card per plugin with `chart: true`, rendered after the two existing repo cards, with the same By Release / By Week / By Month toggle. Also produces a generalized `setupToggle(chartId, builders, hasWeekly)` used by both the platform and plugin cards.

**Spec refinement — `setupToggle` is parameterized, not reused verbatim.**
The design doc's Dashboard section says the plugin card "reuses `setupToggle` and `CHART_DEFAULTS` unchanged". `CHART_DEFAULTS` genuinely is reused unchanged. `setupToggle` is not reusable as written: at line 254 it takes `(chartId, repoData, weeklyData)` and closes over the three *platform* builder functions by name, so a plugin card could only use it by duplicating the whole function. This task therefore changes its signature to `setupToggle(chartId, builders, hasWeekly)`, where `builders` is `{release, weekly, monthly}` of zero-arg functions, and updates the single existing call site (line 351) to pass the platform builders explicitly. This honors the spec's *intent* — reuse the toggle machinery, do not duplicate it — while diverging from its literal wording. The behavior of the two existing cards is unchanged.

---

- [ ] **Step 1: Add the plugin series color to `COLORS`**

In `site/index.html`, extend the `COLORS` object at line 125 with a fourth entry. The faded variant is used for releases whose `prerelease` flag is true (per D3, no `ai-assistant` release is currently flagged prerelease, so nothing is faded today — but the code must honor the flag).

```javascript
const COLORS = {
  linux: { bg: '#F5A623', bgFaded: 'rgba(245,166,35,0.45)' },
  mac:   { bg: '#4A90D9', bgFaded: 'rgba(74,144,217,0.45)' },
  win:   { bg: '#7ED321', bgFaded: 'rgba(126,211,33,0.45)' },
  plugin:{ bg: '#BC7EE8', bgFaded: 'rgba(188,126,232,0.45)' },
};
```

- [ ] **Step 2: Generalize `setupToggle` to accept injected builders**

Replace the whole function at lines 254-283 with the version below. The only changes: the parameter list, and the removal of the local `builders`/`hasWeekly` derivation (both now supplied by the caller). Everything from `const initialView` down is byte-identical to the current code.

```javascript
function setupToggle(chartId, builders, hasWeekly) {
  const canvas = document.getElementById(chartId);
  if (!canvas) return;

  const initialView = hasWeekly ? 'weekly' : 'release';
  let chart = new Chart(canvas, builders[initialView]());

  const container = canvas.closest('.chart-container');
  if (!container) return;
  const buttons = container.querySelectorAll('[data-view]');

  buttons.forEach(btn => {
    btn.addEventListener('click', function() {
      const view = btn.getAttribute('data-view');
      if (!builders[view]) return;
      buttons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      chart.destroy();
      chart = new Chart(canvas, builders[view]());
    });
  });
}
```

- [ ] **Step 3: Update the existing platform call site to pass its builders**

In `init()` (currently line 351), replace the single `setupToggle(chartId, repoData, weeklyData);` call with an explicit builder object. The `hasWeekly` expression is copied verbatim from the old function body and from `buildCard` (line 290), so the platform cards keep their exact current behavior.

```javascript
      const chartId = 'chart-' + repoData.repo.replace(/\//g, '-');
      const hasWeekly = weeklyData && weeklyData.weeks && weeklyData.weeks.length >= 2;
      setupToggle(chartId, {
        release: () => buildReleaseChartConfig(repoData),
        weekly:  () => buildWeeklyChartConfig(weeklyData),
        monthly: () => buildMonthlyChartConfig(weeklyData),
      }, hasWeekly);
```

- [ ] **Step 4: Verify the refactor changed nothing visible (platform cards only)**

Run the existing pipeline and confirm the two current cards still render and both toggles still work. This is the regression check for Steps 2-3 in isolation, before any plugin code exists.

```bash
mkdir -p _site _snapshots
python3 releases.py --json --output-dir _site/
python3 build_site.py --site-dir _site/ --snapshots-dir _snapshots/
cp site/index.html _site/index.html
python3 -m http.server 8080 --directory _site/
```

Open http://localhost:8080. Expect: two cards (`Azure/aks-desktop`, `kubernetes-sigs/headlamp`), each opening on **By Release** (a fresh `_snapshots/` has only one snapshot, so `hasWeekly` is false and the Week/Month buttons are absent). Confirm the browser console is free of errors. Stop the server with Ctrl-C.

- [ ] **Step 5: Add the plugin release-chart builder, with duplicate-version label handling**

Insert immediately **after** `setupToggle` and **before** `buildCard` (i.e. after the closing brace at line 283 of the original file).

Why the label logic is not simply `r.version`: within a single plugin, the same `version` can legitimately appear under two different tags. Real examples in `headlamp-k8s/plugins`: `app-catalog` version `0.1.3` appears under both `v0.1.4` and `v0.1.3`; `prometheus` version `0.0.1` appears under both `v0.1.4` and `v0.1.4-alpha`. This comes from the legacy version-only tags, where one release bundled several plugin assets. Labelling by `version` alone would produce two bars with identical captions and no way to tell them apart. So: a version that occurs exactly once is labelled by `version` (short and readable); a version that occurs more than once falls back to the full `tag`, which is unique per release. `ai-assistant` has no duplicate versions, so today every bar is labelled by version and this branch is dormant — but it must be correct before any other plugin is charted.

```javascript
function buildPluginReleaseChartConfig(pluginData) {
  const releases = pluginData.releases;

  // A version can repeat within one plugin (legacy version-only tags bundled
  // several plugins into one release, e.g. app-catalog 0.1.3 under both
  // 'v0.1.4' and 'v0.1.3'). Identical labels would be indistinguishable, so
  // any version appearing more than once is labelled by its unique tag.
  const versionCounts = new Map();
  for (const r of releases) {
    versionCounts.set(r.version, (versionCounts.get(r.version) || 0) + 1);
  }

  const labels = releases.map(r => {
    const base = versionCounts.get(r.version) > 1 ? r.tag : r.version;
    return r.prerelease ? base + ' (pre)' : base;
  });

  return {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Downloads',
          data: releases.map(r => r.downloads),
          backgroundColor: releases.map(r => r.prerelease ? COLORS.plugin.bgFaded : COLORS.plugin.bg)
        }
      ]
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        ...CHART_DEFAULTS.scales,
        x: { ...CHART_DEFAULTS.scales.x, ticks: { ...CHART_DEFAULTS.scales.x.ticks, font: { size: releases.length > 30 ? 9 : 11 } } }
      }
    }
  };
}
```

- [ ] **Step 6: Add the plugin weekly and monthly builders**

Insert directly after `buildPluginReleaseChartConfig`. The date formatting mirrors `buildWeeklyChartConfig` (line 198) and `buildMonthlyChartConfig` (line 233) exactly; only the metric key differs (`downloads` instead of `linux`/`mac`/`win`). The `'T00:00:00'` suffix forces local-time parsing — without it, a bare `YYYY-MM-DD` is parsed as UTC and can render as the previous day west of Greenwich.

```javascript
function buildPluginWeeklyChartConfig(weeklyData) {
  const weeks = weeklyData.weeks;
  const labels = weeks.map(w => {
    const d = new Date(w.week + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });

  return {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Downloads', data: weeks.map(w => w.downloads), backgroundColor: COLORS.plugin.bg }
      ]
    },
    options: CHART_DEFAULTS
  };
}

function aggregatePluginMonthly(weeklyData) {
  // Group weekly entries by YYYY-MM (based on the Monday-of-week date) and sum.
  const byMonth = new Map();
  for (const w of weeklyData.weeks) {
    const ym = w.week.slice(0, 7); // 'YYYY-MM'
    const cur = byMonth.get(ym) || { month: ym, downloads: 0 };
    cur.downloads += w.downloads;
    byMonth.set(ym, cur);
  }
  return Array.from(byMonth.values()).sort((a, b) => a.month.localeCompare(b.month));
}

function buildPluginMonthlyChartConfig(weeklyData) {
  const months = aggregatePluginMonthly(weeklyData);
  const labels = months.map(m => {
    const d = new Date(m.month + '-01T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  });

  return {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Downloads', data: months.map(m => m.downloads), backgroundColor: COLORS.plugin.bg }
      ]
    },
    options: CHART_DEFAULTS
  };
}
```

- [ ] **Step 7: Add `pluginChartId` and `buildPluginCard`**

Insert directly after `buildPluginMonthlyChartConfig`, still before `buildCard`. The markup deliberately mirrors `buildCard` (line 285) — same `.card`, `.card-header`, `.stat`, `.toggle-bar`, `.chart-container` classes — so no CSS changes are needed. The chart id is namespaced with a `chart-plugin-` prefix and includes both repo and plugin name, since two repos could each contain a plugin of the same name.

```javascript
function pluginChartId(repo, plugin) {
  return 'chart-plugin-' + (repo + '-' + plugin).replace(/[^A-Za-z0-9_-]/g, '-');
}

function buildPluginCard(repo, pluginData, weeklyData) {
  const card = document.createElement('div');
  card.className = 'card';

  const repoUrl = 'https://github.com/' + repo;
  const hasWeekly = weeklyData && weeklyData.weeks && weeklyData.weeks.length >= 2;
  const chartId = pluginChartId(repo, pluginData.plugin);

  let html = '<div class="card-header">'
    + '<h2><a href="' + repoUrl + '" target="_blank">' + repo + '</a> &mdash; ' + pluginData.plugin + '</h2>'
    + '<div class="stat">Total Downloads: <strong>' + fmt(pluginData.approx_all_time_downloads) + '</strong></div>'
    + '</div>';

  html += '<div class="chart-container">';

  html += '<div class="toggle-bar">'
    + '<button class="toggle-btn' + (hasWeekly ? '' : ' active') + '" data-view="release">By Release</button>';
  if (hasWeekly) {
    html += '<button class="toggle-btn active" data-view="weekly">By Week</button>'
      + '<button class="toggle-btn" data-view="monthly">By Month</button>';
  }
  html += '</div>';

  html += '<div style="position:relative;height:' + Math.max(300, pluginData.releases.length * 8) + 'px">'
    + '<canvas id="' + chartId + '"></canvas>'
    + '</div></div>';

  card.innerHTML = html;
  return card;
}
```

- [ ] **Step 8: Fetch the plugin files tolerantly in `init()`**

In `init()`, extend the `Promise.all` at line 321 and the parsing block below it. The `.catch(() => null)` on each plugin fetch is required by the spec's Failure Handling section: if `plugins.json` is absent (plugin track not yet run, or its workflow step failed), the two existing cards must still render. Note that `fetch` only rejects on network-level failure — a 404 resolves with `ok === false` — so both the `.catch` and the `.ok` check are needed, exactly as the existing `history.json` handling does it.

```javascript
    const [dataResp, histResp, pluginResp, pluginHistResp] = await Promise.all([
      fetch('./data.json'),
      fetch('./history.json').catch(() => null),
      fetch('./plugins.json').catch(() => null),
      fetch('./plugins-history.json').catch(() => null)
    ]);

    if (!dataResp.ok) throw new Error('Failed to load data.json');
    const data = await dataResp.json();

    let history = { repos: [] };
    if (histResp && histResp.ok) {
      history = await histResp.json();
    }

    let plugins = { repos: [] };
    if (pluginResp && pluginResp.ok) {
      plugins = await pluginResp.json();
    }

    let pluginHistory = { repos: [] };
    if (pluginHistResp && pluginHistResp.ok) {
      pluginHistory = await pluginHistResp.json();
    }
```

- [ ] **Step 9: Render the plugin cards after the repo loop**

Insert this block in `init()` immediately after the existing `for (const repoData of data.repos) { ... }` loop closes (original line 352) and before the `} catch (err) {`. Placing it after the loop is what puts the plugin card third, below the two repo cards. The whole block is wrapped in its own `try/catch` so a malformed `plugins.json` degrades to "plugin cards missing" rather than replacing the entire page with the error div.

```javascript
    // Plugin cards render after the platform cards. Failures here must not
    // take down the platform cards, so this block swallows its own errors.
    try {
      for (const pluginRepo of (plugins.repos || [])) {
        const histRepo = (pluginHistory.repos || []).find(r => r.repo === pluginRepo.repo);
        for (const pluginData of (pluginRepo.plugins || [])) {
          if (!pluginData.chart) continue;
          const weeklyData = histRepo
            ? (histRepo.plugins || []).find(p => p.plugin === pluginData.plugin)
            : null;
          const hasWeekly = weeklyData && weeklyData.weeks && weeklyData.weeks.length >= 2;

          content.appendChild(buildPluginCard(pluginRepo.repo, pluginData, weeklyData));

          setupToggle(pluginChartId(pluginRepo.repo, pluginData.plugin), {
            release: () => buildPluginReleaseChartConfig(pluginData),
            weekly:  () => buildPluginWeeklyChartConfig(weeklyData),
            monthly: () => buildPluginMonthlyChartConfig(weeklyData),
          }, hasWeekly);
        }
      }
    } catch (pluginErr) {
      console.error('Plugin cards failed to render:', pluginErr);
    }
```

- [ ] **Step 10: Verify the By Release view against real data**

Run the full pipeline including the plugin steps. This is the first-run case: `_plugin_snapshots/` is empty, so `plugins-history.json` has no weeks and the card must open on **By Release** with no Week/Month buttons.

```bash
rm -rf _site _snapshots _plugin_snapshots
mkdir -p _site _snapshots _plugin_snapshots
python3 releases.py --json --output-dir _site/
python3 plugins.py --json --output-dir _site/ --num-releases 0
python3 build_site.py --site-dir _site/ --snapshots-dir _snapshots/ \
  --plugin-snapshots-dir _plugin_snapshots/
cp site/index.html _site/index.html
python3 -m http.server 8080 --directory _site/
```

Open http://localhost:8080 and check the third card:
- Heading reads `headlamp-k8s/plugins — ai-assistant`, with `headlamp-k8s/plugins` linking to https://github.com/headlamp-k8s/plugins.
- Total Downloads reads **102,447**.
- Three purple (`#BC7EE8`) bars labelled `0.1.0-alpha`, `0.2.0-alpha`, `0.3.0-alpha` with values **81,213 / 20,086 / 1,148**. All three are solid, not faded (D3: GitHub's `prerelease` flag is false on all three despite the `-alpha` suffix).
- Only the **By Release** button is present, and it is active.
- Browser console is clean.

Stop the server.

- [ ] **Step 11: Verify the Week/Month toggles with hand-made history**

Real weekly history needs several days of accumulated snapshots, which do not exist locally. Fabricate a three-week `plugins-history.json` spanning a month boundary so both the weekly and monthly views have something to draw. Run this against the `_site/` produced in Step 10, without re-running the pipeline (which would overwrite the file).

```bash
cat > _site/plugins-history.json <<'EOF'
{
  "repos": [
    {
      "repo": "headlamp-k8s/plugins",
      "plugins": [
        {
          "plugin": "ai-assistant",
          "weeks": [
            { "week": "2026-07-27", "downloads": 310 },
            { "week": "2026-08-03", "downloads": 275 },
            { "week": "2026-08-10", "downloads": 412 }
          ]
        }
      ]
    }
  ]
}
EOF
python3 -m http.server 8080 --directory _site/
```

Reload http://localhost:8080 and check the third card:
- All three buttons are present; the card opens on **By Week** (active), matching the platform cards' behavior when `weeks.length >= 2`.
- **By Week** shows three bars labelled `Jul 27`, `Aug 3`, `Aug 10` with values 310 / 275 / 412.
- **By Month** shows two bars: `Jul 2026` = 310 and `Aug 2026` = 687 (275 + 412).
- **By Release** still shows the three release bars from Step 10.
- Clicking between all three views repeatedly does not leak or stack canvases (`chart.destroy()` runs on each switch) and logs no console errors.

Stop the server.

- [ ] **Step 12: Verify the duplicate-version label fallback**

`ai-assistant` has no duplicate versions, so this branch cannot be exercised through the charted plugin. Flip a non-charted plugin that does have duplicates into the chart temporarily, using the already-generated `plugins.json` — no pipeline re-run needed.

```bash
python3 - <<'EOF'
import json
p = '_site/plugins.json'
d = json.load(open(p))
for repo in d['repos']:
    for pl in repo['plugins']:
        if pl['plugin'] == 'app-catalog':
            pl['chart'] = True
        vers = [r['version'] for r in pl['releases']]
        dupes = {v for v in vers if vers.count(v) > 1}
        if dupes:
            print(pl['plugin'], 'duplicate versions:', sorted(dupes))
json.dump(d, open(p, 'w'), indent=2)
EOF
python3 -m http.server 8080 --directory _site/
```

Expect the script to print at least `app-catalog duplicate versions: ['0.1.3']` and `prometheus duplicate versions: ['0.0.1']`, confirming the condition is real in current data. Reload the page: a fourth card for `app-catalog` appears, and its two `0.1.3` bars are labelled with their full tags (`v0.1.4` and `v0.1.3`) rather than two identical `0.1.3` captions. Every other bar in that card, whose version is unique, is still labelled by version alone.

Then discard the scratch state — it is generated output, not tracked, but leaving it invites confusion:

```bash
rm -rf _site _snapshots _plugin_snapshots
```

- [ ] **Step 13: Review the diff and confirm no unintended changes**

```bash
git diff site/index.html
git status
```

Confirm the diff touches only: the `COLORS` object, the `setupToggle` signature and its two removed derivation lines, the four new plugin functions plus `pluginChartId`, the platform `setupToggle` call site, and the two new blocks in `init()`. No CSS changes, and no changes to `buildReleaseChartConfig`, `buildWeeklyChartConfig`, `aggregateMonthly`, `buildMonthlyChartConfig`, or `buildCard`. Confirm `git status` shows no stray `_site/`, `_snapshots/`, or `_plugin_snapshots/` directories.

- [ ] **Step 14: Commit**

```bash
git add site/index.html
git commit -m "Add plugin download card to dashboard

Renders a card per plugin flagged chart=true in plugins.json, after the
existing repo cards, with the same By Release / By Week / By Month toggle.

Generalizes setupToggle to setupToggle(chartId, builders, hasWeekly) so the
plugin card reuses it instead of duplicating it; the platform call site now
passes its three existing builders explicitly, with unchanged behavior.

Plugin fetches use the tolerant catch-to-null pattern already used for
history.json, so the existing cards still render when the plugin track is
absent or fails.

Bars are labelled by version, falling back to the full tag when a version
appears more than once within a plugin (legacy version-only tags bundle
several plugins, e.g. app-catalog 0.1.3 under both v0.1.4 and v0.1.3)."
```

---

### Task 7: Workflow and documentation

**Files:**
- Modify: `.github/workflows/update-site.yml:9-14` (`paths:` trigger)
- Modify: `.github/workflows/update-site.yml:41-55` (plugin fetch step + build step)
- Modify: `README.md:22-30` (How It Works), `README.md:47-64` (local pipeline), `README.md:75-84` (Project Structure), plus a new `plugins.csv` section and a testing section
- Test: manual — see the YAML parse check and the end-to-end run below

**Interfaces:**
- Consumes: `plugins.py` (Task 3) with the CLI `--json --output-dir DIR --num-releases N`; `build_site.py` (Task 5) with the new `--plugin-snapshots-dir`; `plugins.csv` (Task 3) with columns `repo,plugin,chart`; `pytest` in `requirements.txt` and `tests/` (Tasks 1-5).
- Produces: a daily CI run that fetches plugin data, snapshots it to `_gh_pages/plugin-snapshots`, publishes `plugins.json` and `plugins-history.json` to `gh-pages`, and persists `plugin-snapshots/` there so tomorrow's diff has a prior day to compare against. Plus a README that documents the plugin track and the pytest suite.

---

- [ ] **Step 1: Add the plugin config and module to the `paths:` trigger**

Without this, editing `plugins.csv` or `plugins.py` on `main` would not rebuild the site — the change would sit unpublished until the next 06:00 UTC cron. Replace lines 9-14 of `.github/workflows/update-site.yml`.

```yaml
    paths:
      - 'site/**'
      - 'build_site.py'
      - 'releases.py'
      - 'plugins.py'
      - 'repos.csv'
      - 'plugins.csv'
      - '.github/workflows/update-site.yml'
```

- [ ] **Step 2: Add the plugin fetch step**

Insert directly after the existing "Fetch release data" step (lines 41-44) and before "Build site". `--num-releases 0` means "all releases"; per D4 the plugin track applies that limit per plugin rather than per repo, so a default value would silently truncate plugins with many releases. `GITHUB_TOKEN` raises the API rate limit from 60/hr to 5000/hr and is the same token the release step already uses.

```yaml
      - name: Fetch plugin release data
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python plugins.py --json --output-dir _site/ --num-releases 0
```

- [ ] **Step 3: Extend the build step to carry the plugin snapshot directory**

Replace the "Build site (snapshots + history)" step (lines 46-55). Two things matter here. First, snapshots live on the `gh-pages` branch, not `main` — the earlier "Checkout gh-pages snapshots" step (line 26) puts them at `_gh_pages/`, and weekly deltas are computed by diffing today's snapshot against yesterday's, so losing them resets all history to zero. Second, the `mkdir -p` guard handles the first run, when `gh-pages` does not yet exist and that checkout step was allowed to fail (`continue-on-error: true` at line 31). The plugin snapshot dir gets identical treatment.

```yaml
      - name: Build site (snapshots + history)
        run: |
          # Use existing snapshots from gh-pages if available, else empty dir
          SNAP_DIR="_gh_pages/snapshots"
          if [ ! -d "$SNAP_DIR" ]; then
            mkdir -p "$SNAP_DIR"
          fi
          PLUGIN_SNAP_DIR="_gh_pages/plugin-snapshots"
          if [ ! -d "$PLUGIN_SNAP_DIR" ]; then
            mkdir -p "$PLUGIN_SNAP_DIR"
          fi
          python build_site.py --site-dir _site/ --snapshots-dir "$SNAP_DIR" \
            --plugin-snapshots-dir "$PLUGIN_SNAP_DIR"
          # Copy snapshots into _site so they persist on gh-pages
          cp -r "$SNAP_DIR" _site/snapshots
          cp -r "$PLUGIN_SNAP_DIR" _site/plugin-snapshots
```

- [ ] **Step 4: Verify the workflow YAML still parses**

`yamllint` is not installed in this environment. Use Python's YAML parser instead, which catches the failure mode that actually matters here — broken indentation or a mangled block scalar in the multi-line `run:` script.

```bash
python3 -c "import yaml; d = yaml.safe_load(open('.github/workflows/update-site.yml')); print('\n'.join(s['name'] for s in d['jobs']['build-and-deploy']['steps']))"
```

Expect the step names printed in order, including `Fetch plugin release data` between `Fetch release data` and `Build site (snapshots + history)`. If PyYAML is missing (`ModuleNotFoundError: No module named 'yaml'`), install it with `pip install pyyaml` — nothing in this project depends on it, so it is a local-only convenience. If installation is not possible, fall back to careful manual review: confirm every step key is at exactly 6 spaces of indentation, every `run:`/`env:` key at 8, the `|` block-scalar body at 10, and that the backslash line continuation inside the `python build_site.py` command has no trailing whitespace after it.

- [ ] **Step 5: Verify the trigger paths against the real filenames**

A typo in `paths:` fails silently — the workflow simply never fires. Confirm each listed path exists.

```bash
python3 -c "
import yaml, os
d = yaml.safe_load(open('.github/workflows/update-site.yml'))
paths = d[True]['push']['paths']
for p in paths:
    print(('OK  ' if os.path.exists(p.rstrip('/*')) else 'MISS'), p)
"
```

Expect `OK` for all seven entries. (Note the `d[True]` — PyYAML parses the bare `on:` key as the boolean `True`, a YAML 1.1 quirk, not a bug in the workflow.)

- [ ] **Step 6: Update "How It Works" in the README**

Replace the 4-item list at `README.md:22-30` with the 5-item list below. The new item 2 describes the plugin track; the old items 2-4 shift down by one, and items 3 and 4 gain a clause about the second track.

````markdown
## How It Works

1. **`releases.py`** fetches release data from the GitHub API and classifies assets by platform based on filename patterns (`.dmg`, `.exe`, `.AppImage`, `.deb`, `.tar.gz`, etc.). Assets that can't be classified (checksums, helm charts) are skipped.

2. **`plugins.py`** runs a parallel track for Headlamp plugin repos configured in [`plugins.csv`](plugins.csv). Plugin releases have no Linux/Mac/Win dimension and one repo holds many plugins, so downloads are attributed to a plugin from the asset filename (`[headlamp-k8s-]<plugin>-<version>.tar.gz`) rather than the release tag. Download counts for *every* plugin in a configured repo are collected, so any of them can be charted later with history already accumulated.

3. **`build_site.py`** saves a daily snapshot of both tracks and diffs consecutive snapshots to compute weekly download deltas — per repo and platform for the release track, per plugin for the plugin track.

4. **`site/index.html`** is a self-contained dark-themed dashboard that renders the data as interactive Chart.js stacked bar charts -- downloads by release, per week, and per month -- with one card per tracked repo plus one card per plugin flagged for charting.

5. A **GitHub Action** (`.github/workflows/update-site.yml`) runs this pipeline daily and deploys the result to the `gh-pages` branch.
````

- [ ] **Step 7: Add a "Tracked Plugins" section documenting `plugins.csv` semantics**

Insert after the existing "Tracked Repos" section (after `README.md:20`) and before "How It Works". The two-column split is the part people get wrong: `repo` controls what is *collected*, `plugin`+`chart` control only what is *displayed*.

````markdown
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
````

- [ ] **Step 8: Update the local pipeline commands**

Replace the "Run the full pipeline locally" block at `README.md:47-64`.

````markdown
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
````

- [ ] **Step 9: Update the Project Structure block and add a testing section**

Replace the block at `README.md:75-84`, then append the testing section after it.

````markdown
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
````

- [ ] **Step 10: Verify the README renders and its links resolve**

Markdown link targets are the easy thing to get wrong, and a broken relative link is invisible until someone clicks it.

```bash
python3 -c "
import re, os
src = open('README.md').read()
for text, target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', src):
    if target.startswith('http'): continue
    print(('OK  ' if os.path.exists(target) else 'MISS'), target, '->', text)
"
```

Expect `OK` for `repos.csv` and `plugins.csv`. Then read `README.md` top to bottom once and confirm the numbered "How It Works" list runs 1-5 with no duplicate numbers, and that the fenced CSV example inside the "Tracked Plugins" section did not break the surrounding fences (if your editor shows the rest of the file as code, a fence is unbalanced).

- [ ] **Step 11: Run the full end-to-end pipeline exactly as documented**

This is the final verification for the whole feature: run the README's own commands verbatim, against the real GitHub API, and confirm the dashboard is correct. If the README instructions do not work here, they do not work for anyone.

```bash
rm -rf _site _snapshots _plugin_snapshots
export GITHUB_TOKEN=$(gh auth token)
mkdir -p _site _snapshots _plugin_snapshots
python3 releases.py --json --output-dir _site/
python3 plugins.py --json --output-dir _site/ --num-releases 0
python3 build_site.py --site-dir _site/ --snapshots-dir _snapshots/ \
  --plugin-snapshots-dir _plugin_snapshots/
cp site/index.html _site/index.html
ls -la _site/ _plugin_snapshots/
python3 -m http.server 8080 --directory _site/
```

Check before opening the browser: `_site/` contains `data.json`, `history.json`, `plugins.json`, `plugins-history.json`, and `index.html`; `_plugin_snapshots/` contains one `YYYY-MM-DD.json`. Then open http://localhost:8080 and confirm three cards render, with the `ai-assistant` card showing a total of **102,447** and three bars (81,213 / 20,086 / 1,148). Stop the server and clean up:

```bash
rm -rf _site _snapshots _plugin_snapshots
```

- [ ] **Step 12: Run the test suite and inspect the final diff**

```bash
pytest tests/ -v
git status
git diff
```

Confirm all tests pass, that `git status` shows no untracked `_site/`, `_snapshots/`, or `_plugin_snapshots/` left behind, and that the diff for this task touches only `.github/workflows/update-site.yml` and `README.md`.

- [ ] **Step 13: Commit**

```bash
git add .github/workflows/update-site.yml README.md
git commit -m "Wire plugin track into CI workflow and document it

Workflow: add plugins.py/plugins.csv to the push paths trigger, add a
plugin fetch step, and pass --plugin-snapshots-dir pointing at
_gh_pages/plugin-snapshots with the same first-run mkdir guard the
existing snapshot dir uses. Copy plugin-snapshots into _site so daily
snapshots persist on gh-pages and tomorrow's diff has a prior day.

README: document the plugin track in How It Works, add a Tracked Plugins
section spelling out that the repo column drives collection while
plugin+chart drive display only, update the local pipeline commands, list
plugins.py/plugins.csv/tests in the project structure, and note pytest."
```
