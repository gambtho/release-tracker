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
