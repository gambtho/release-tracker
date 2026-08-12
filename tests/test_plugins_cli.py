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
