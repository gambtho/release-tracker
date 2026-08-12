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
