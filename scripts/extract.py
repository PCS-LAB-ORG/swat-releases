"""extract.py — call Gemini and write the JSON artifact for one release.

Usage: python scripts/extract.py <tool_id> <version> [--force]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Protocol

from google import genai
from google.genai.types import HttpOptions

from scripts.poll import load_config, GitHubReleaseSource


# ── Protocols ────────────────────────────────────────────────────────────────

class GeminiClient(Protocol):
    def generate(
        self,
        system_prompt: str,
        version: str,
        release_url: str,
        release_body: str,
    ) -> str: ...


# ── Implementations ──────────────────────────────────────────────────────────

class VertexGeminiClient:
    def __init__(self) -> None:
        self._client = genai.Client(vertexai=True, project=os.environ.get("GOOGLE_CLOUD_PROJECT", "pcs-swat-resources"), location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"), http_options=HttpOptions(api_version="v1"))

    def generate(
        self,
        system_prompt: str,
        version: str,
        release_url: str,
        release_body: str,
    ) -> str:
        prompt = (
            f"{system_prompt}\n\n"
            f"Release version: {version}\n"
            f"Release URL: {release_url}\n\n"
            f"Release notes:\n{release_body}"
        )
        response = self._client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
        )
        return response.text


REQUIRED_FIELDS = {"version", "date", "release_url", "summary", "entries"}
VALID_TAGS = {"Feature", "Enhancement", "Fixed", "Planned", "Known"}


class ResponseValidator:
    def validate(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Gemini: {e}\nRaw: {raw[:300]}")

        missing = REQUIRED_FIELDS - data.keys()
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        if not isinstance(data["entries"], list):
            raise ValueError("'entries' must be a list")

        for entry in data["entries"]:
            if not all(k in entry for k in ["tag", "title", "description"]):
                raise ValueError(f"Entry missing required keys: {entry}")
            if entry["tag"] not in VALID_TAGS:
                raise ValueError(
                    f"Invalid tag '{entry['tag']}', must be one of {VALID_TAGS}"
                )
        return data


class GeminiExtractor:
    def __init__(self, client: GeminiClient, validator: ResponseValidator) -> None:
        self._client = client
        self._validator = validator

    def extract(
        self,
        system_prompt: str,
        version: str,
        release_url: str,
        release_body: str,
    ) -> dict:
        raw = self._client.generate(system_prompt, version, release_url, release_body)
        data = self._validator.validate(raw)
        data["release_url"] = release_url  # always use canonical URL
        return data


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python scripts/extract.py <tool_id> <version> [--force]",
              file=sys.stderr)
        sys.exit(1)

    tool_id = sys.argv[1]
    version = sys.argv[2]
    force = "--force" in sys.argv

    config = load_config("config/tools.yaml")
    tool = next(t for t in config["tools"] if t["id"] == tool_id)

    output_dir = Path("data") / tool["folder"]
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{version}.json"

    if not force and output_file.exists():
        print(f"Skipping {version}: artifact already exists at {output_file}",
              file=sys.stderr)
        return

    # Load prompt
    system_prompt = Path(tool["prompt"]).read_text()

    # Fetch release from GitHub
    token = os.environ["GITHUB_TOKEN"]
    gh_client = GitHubReleaseSource(token)
    release = gh_client.get_release(tool["repo"], version)

    # Extract via Gemini
    gemini_client = VertexGeminiClient()
    extractor = GeminiExtractor(gemini_client, ResponseValidator())
    data = extractor.extract(
        system_prompt,
        version,
        release["html_url"],
        release["body"],
    )

    output_file.write_text(json.dumps(data, indent=2))
    print(f"Written: {output_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
