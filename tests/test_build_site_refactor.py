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


def test_main_end_to_end_writes_history_without_key_type_mismatch(tmp_path, monkeypatch):
    """Regression for the `weekly.setdefault(...)` call in main(): its key must
    be a (repo,) tuple to match the keys build_platform_index produces. A bare
    string key there is a no-op for repos that already have diff data, but it
    still inserts a second, differently-typed key into `weekly` -- which makes
    `sorted(weekly)` in build_history_json raise TypeError (str vs tuple) as
    soon as there are >= 2 snapshots. This only surfaces by running main() end
    to end; none of the unit-level tests above call main()."""
    site_dir = tmp_path / "site"
    snapshots_dir = tmp_path / "snaps"
    site_dir.mkdir()
    snapshots_dir.mkdir()

    with open(os.path.join(SNAPSHOT_DIR, "2026-08-05.json"), encoding="utf-8") as f:
        older_snapshot = f.read()
    with open(os.path.join(SNAPSHOT_DIR, "2026-08-11.json"), encoding="utf-8") as f:
        latest_snapshot = f.read()

    # One pre-existing snapshot on disk, plus today's data.json -- main() will
    # save data.json as a second snapshot, giving compute_weekly_history two
    # snapshots to diff and populating `weekly` with (repo,) tuple keys.
    (snapshots_dir / "2026-08-05.json").write_text(older_snapshot, encoding="utf-8")
    (site_dir / "data.json").write_text(latest_snapshot, encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "build_site.py",
            "--site-dir",
            str(site_dir),
            "--snapshots-dir",
            str(snapshots_dir),
        ],
    )
    build_site.main()

    history = json.loads((site_dir / "history.json").read_text(encoding="utf-8"))
    assert [r["repo"] for r in history["repos"]] == ["acme/tool", "beta/app"]
