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
