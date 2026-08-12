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
