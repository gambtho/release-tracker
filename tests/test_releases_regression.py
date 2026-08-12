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
