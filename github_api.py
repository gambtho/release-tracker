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
