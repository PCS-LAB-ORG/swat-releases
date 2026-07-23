"""extract.py — call Gemini and write the JSON artifact for one release.

Orchestration is handled by scripts/generator/main.py; this module exposes
composable classes and process_release() rather than a CLI entry point.
"""
from __future__ import annotations

import json as _json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from google import genai
from google.cloud import storage as _storage
from google.cloud.exceptions import NotFound
from google.genai.types import HttpOptions


# ── Version classification ────────────────────────────────────────────────────

def is_hotfix(version: str) -> bool:
    return len(version.split(".")) == 4


def parent_version(version: str) -> str:
    return ".".join(version.split(".")[:3])


# ── GCS I/O classes ───────────────────────────────────────────────────────────

class GCSMarkdownSource:
    def __init__(self, client: "_storage.Client") -> None:
        self._client = client

    def read(self, bucket: str, tool_id: str, version: str) -> str:
        blob = self._client.bucket(bucket).blob(f"{tool_id}/{version}.md")
        return blob.download_as_text()


class GCSArtifactStore:
    def __init__(self, client: "_storage.Client") -> None:
        self._client = client

    def read_json(self, bucket: str, tool_id: str, version: str) -> dict | None:
        blob = self._client.bucket(bucket).blob(f"{tool_id}/{version}.json")
        try:
            return _json.loads(blob.download_as_text())
        except NotFound:
            return None

    def write_json(self, bucket: str, tool_id: str, version: str, data: dict) -> None:
        blob = self._client.bucket(bucket).blob(f"{tool_id}/{version}.json")
        blob.upload_from_string(_json.dumps(data, indent=2), content_type="application/json")


# ── Protocols ────────────────────────────────────────────────────────────────

class GeminiClient(Protocol):
    def generate(self, system_prompt: str, content: str) -> str: ...


# ── Implementations ──────────────────────────────────────────────────────────

class VertexGeminiClient:
    def __init__(self) -> None:
        self._client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", "pcs-swat-resources"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            http_options=HttpOptions(api_version="v1"),
        )

    def generate(self, system_prompt: str, content: str) -> str:
        prompt = f"{system_prompt}\n\n{content}"
        response = self._client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
        )
        return response.text


REQUIRED_FIELDS = {"version", "date", "release_url", "summary", "entries"}
VALID_TAGS = {"Feature", "Enhancement", "Fixed", "Planned", "Known", "Architecture", "Infrastructure"}


class ResponseValidator:
    def validate(self, raw: str) -> dict:
        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError as e:
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

    def validate_hotfix(self, raw: str) -> list[dict]:
        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Gemini: {e}\nRaw: {raw[:300]}")
        if "entries" not in data or not isinstance(data["entries"], list):
            raise ValueError("Hotfix response must have an 'entries' list")
        for entry in data["entries"]:
            if not all(k in entry for k in ["tag", "title", "description"]):
                raise ValueError(f"Entry missing required keys: {entry}")
            if entry["tag"] != "Fixed":
                raise ValueError(f"Hotfix entries must use 'Fixed' tag, got '{entry['tag']}'")
        return data["entries"]


class GeminiExtractor:
    def __init__(self, client: GeminiClient, validator: ResponseValidator) -> None:
        self._client = client
        self._validator = validator

    def extract(self, system_prompt: str, md_content: str, version: str) -> dict:
        raw = self._client.generate(system_prompt, md_content)
        data = self._validator.validate(raw)
        data["version"] = version  # always canonical
        return data

    def extract_hotfix(
        self, system_prompt: str, md_content: str, hotfix_version: str
    ) -> list[dict]:
        raw = self._client.generate(system_prompt, md_content)
        return self._validator.validate_hotfix(raw)


# ── Orchestration ─────────────────────────────────────────────────────────────

def process_release(
    tool_id: str,
    version: str,
    input_bucket: str,
    serve_bucket: str,
    *,
    gemini_extractor: "GeminiExtractor",
    gcs_md_source: "GCSMarkdownSource",
    gcs_artifact_store: "GCSArtifactStore",
    config: dict,
    force: bool = False,
) -> dict:
    """Extract and store the JSON artifact for one release version.

    For major releases: creates a new artifact.
    For hotfixes: fetches parent artifact, appends fix entries, re-saves.
    Returns the final artifact dict.
    """
    tool = next(t for t in config["tools"] if t["id"] == tool_id)

    if is_hotfix(version):
        pv = parent_version(version)
        parent_artifact = gcs_artifact_store.read_json(serve_bucket, tool_id, pv)
        if parent_artifact is None:
            raise RuntimeError(
                f"Parent artifact {tool_id}/{pv}.json not found in {serve_bucket}. "
                f"Process {pv} before {version}."
            )
        # Skip if this hotfix version already exists in the parent's fixes list
        existing_fixes = parent_artifact.get("fixes", [])
        if not force and any(f["version"] == version for f in existing_fixes):
            return parent_artifact

        hotfix_prompt = Path("scripts/prompts/model1_hotfix.txt").read_text()
        md_content = gcs_md_source.read(input_bucket, tool_id, version)
        fix_entries = gemini_extractor.extract_hotfix(hotfix_prompt, md_content, version)

        fix_record = {
            "version": version,
            "date": datetime.now(timezone.utc).strftime("%B %Y"),
            "entries": fix_entries,
        }
        existing_fixes.append(fix_record)
        parent_artifact["fixes"] = existing_fixes
        gcs_artifact_store.write_json(serve_bucket, tool_id, pv, parent_artifact)
        return parent_artifact

    # Major release
    existing = gcs_artifact_store.read_json(serve_bucket, tool_id, version)
    if not force and existing is not None:
        return existing

    major_prompt = Path(tool["prompt"]).read_text()
    md_content = gcs_md_source.read(input_bucket, tool_id, version)
    data = gemini_extractor.extract(major_prompt, md_content, version)
    data.setdefault("fixes", [])
    gcs_artifact_store.write_json(serve_bucket, tool_id, version, data)
    return data
