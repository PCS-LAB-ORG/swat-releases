import json
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from scripts.poll import (
    load_config,
    ReleaseFilter,
    ReleasePollService,
)


SAMPLE_RELEASES = [
    {"tag_name": "26.7.1", "published_at": "2026-07-01T00:00:00Z",
     "html_url": "https://github.com/PCS-LAB-ORG/catalyst-rag-agent/releases/tag/26.7.1",
     "body": "## Features\n\nNew stuff."},
    {"tag_name": "26.6.1", "published_at": "2026-06-23T00:00:00Z",
     "html_url": "https://github.com/PCS-LAB-ORG/catalyst-rag-agent/releases/tag/26.6.1",
     "body": "## Previous release."},
]


def mock_github_client(releases=None):
    client = MagicMock()
    client.get_releases.return_value = releases or SAMPLE_RELEASES
    return client


def test_load_config_returns_tools():
    config = load_config("config/tools.yaml")
    assert len(config["tools"]) == 1
    assert config["tools"][0]["id"] == "cortex-catalyst"


def test_release_filter_skips_when_html_exists(tmp_path):
    html = tmp_path / "cortex-catalyst" / "26.6.1.html"
    html.parent.mkdir()
    html.touch()
    f = ReleaseFilter(repo_root=tmp_path)
    assert f.is_new("26.6.1", "cortex-catalyst") is False


def test_release_filter_skips_when_json_exists(tmp_path):
    j = tmp_path / "data" / "cortex-catalyst" / "26.6.1.json"
    j.parent.mkdir(parents=True)
    j.touch()
    f = ReleaseFilter(repo_root=tmp_path)
    assert f.is_new("26.6.1", "cortex-catalyst") is False


def test_release_filter_passes_new_version(tmp_path):
    f = ReleaseFilter(repo_root=tmp_path)
    assert f.is_new("26.7.1", "cortex-catalyst") is True


def test_poll_service_returns_only_new(tmp_path):
    # 26.6.1 already exists as HTML
    html = tmp_path / "cortex-catalyst" / "26.6.1.html"
    html.parent.mkdir()
    html.touch()

    client = mock_github_client()
    service = ReleasePollService(client, ReleaseFilter(repo_root=tmp_path))
    tool = {"repo": "PCS-LAB-ORG/catalyst-rag-agent", "folder": "cortex-catalyst"}

    results = service.get_new_versions(tool)
    assert len(results) == 1
    assert results[0][0] == "26.7.1"


def test_poll_service_returns_empty_when_all_exist(tmp_path):
    for v in ["26.7.1", "26.6.1"]:
        html = tmp_path / "cortex-catalyst" / f"{v}.html"
        html.parent.mkdir(exist_ok=True)
        html.touch()

    client = mock_github_client()
    service = ReleasePollService(client, ReleaseFilter(repo_root=tmp_path))
    tool = {"repo": "PCS-LAB-ORG/catalyst-rag-agent", "folder": "cortex-catalyst"}

    results = service.get_new_versions(tool)
    assert results == []
