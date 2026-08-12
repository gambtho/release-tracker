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
