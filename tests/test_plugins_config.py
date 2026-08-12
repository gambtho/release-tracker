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
