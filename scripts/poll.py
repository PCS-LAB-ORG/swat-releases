"""poll.py — detect new GitHub releases for tracked tools.

Usage: python scripts/poll.py
Writes space-separated new versions to $GITHUB_OUTPUT as `new_versions`.
Set INPUT_FORCE_VERSION=26.7.1 to bypass skip logic for a specific version.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Protocol

import requests
import yaml


# ── Shared config loader (used by all scripts) ──────────────────────────────

def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# ── Protocols ───────────────────────────────────────────────────────────────

class GitHubClient(Protocol):
    def get_releases(self, repo: str) -> list[dict]: ...
    def get_release(self, repo: str, tag: str) -> dict: ...


# ── Implementations ─────────────────────────────────────────────────────────

class GitHubReleaseSource:
    def __init__(self, token: str):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def get_releases(self, repo: str) -> list[dict]:
        url = f"https://api.github.com/repos/{repo}/releases"
        resp = requests.get(url, headers=self._headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_release(self, repo: str, tag: str) -> dict:
        url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        resp = requests.get(url, headers=self._headers, timeout=30)
        resp.raise_for_status()
        return resp.json()


class ReleaseFilter:
    def __init__(self, repo_root: str | Path = "."):
        self._root = Path(repo_root)

    def is_new(self, version: str, folder: str) -> bool:
        html_path = self._root / folder / f"{version}.html"
        json_path = self._root / "data" / folder / f"{version}.json"
        return not html_path.exists() and not json_path.exists()


class ReleasePollService:
    def __init__(self, client: GitHubClient, release_filter: ReleaseFilter):
        self._client = client
        self._filter = release_filter

    def get_new_versions(self, tool: dict) -> list[tuple[str, str]]:
        """Return [(version, body), ...] for releases not yet processed."""
        releases = self._client.get_releases(tool["repo"])
        result = []
        for release in releases:
            version = release["tag_name"]
            if self._filter.is_new(version, tool["folder"]):
                result.append((version, release["body"]))
        return result


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    force_version = os.environ.get("INPUT_FORCE_VERSION", "").strip()
    token = os.environ["GITHUB_TOKEN"]
    config = load_config("config/tools.yaml")

    client = GitHubReleaseSource(token)

    if force_version:
        # Bypass skip logic — return just the forced version
        new_versions = [force_version]
    else:
        release_filter = ReleaseFilter()
        service = ReleasePollService(client, release_filter)
        tool = config["tools"][0]  # PoC: Catalyst only
        new_versions = [v for v, _ in service.get_new_versions(tool)]

    output = " ".join(new_versions)
    print(f"New versions: {output or '(none)'}", file=sys.stderr)

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"new_versions={output}\n")
    else:
        print(f"new_versions={output}")


if __name__ == "__main__":
    main()
