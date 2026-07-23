"""Cloud Function entry point for the swat-releases generator.

Triggered hourly by Cloud Scheduler (HTTP POST).
Lists swat-releases-input for .md files, processes each via Gemini,
uploads rendered HTML to swat-releases-serve.
"""
from __future__ import annotations

import json
import logging
import os

import functions_framework
from google.cloud import storage

from scripts.extract import (
    GCSArtifactStore,
    GCSMarkdownSource,
    GeminiExtractor,
    ResponseValidator,
    VertexGeminiClient,
    is_hotfix,
    parent_version,
    process_release,
)
from scripts.render import (
    GCSHTMLRenderer,
    GCSIndexUpdater,
    TemplateEngine,
    load_all_release_data_from_gcs,
    load_assets,
)
from scripts.config import load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INPUT_BUCKET = os.environ.get("INPUT_BUCKET", "swat-releases-input")
SERVE_BUCKET = os.environ.get("SERVE_BUCKET", "swat-releases-serve")


def render_version(
    tool: dict,
    version: str,
    artifact: dict,
    gcs_client: storage.Client,
    serve_bucket: str,
) -> None:
    assets = load_assets("images")
    engine = TemplateEngine("scripts/templates")
    updater = GCSIndexUpdater(engine, gcs_client, serve_bucket)
    renderer = GCSHTMLRenderer(engine, updater, assets, gcs_client)

    all_releases = load_all_release_data_from_gcs(gcs_client, serve_bucket, tool["id"])
    all_versions = [
        {
            "version": r["version"],
            "label": f"{r['date']} — {r['version']}",
            "is_current": r["version"] == version,
            "href": r["version"],
        }
        for r in all_releases
    ]
    renderer.render_and_upload(tool, version, artifact, all_versions, serve_bucket)


def rebuild_index(
    tool: dict,
    gcs_client: storage.Client,
    serve_bucket: str,
) -> None:
    from scripts.render import group_by_month
    assets = load_assets("images")
    engine = TemplateEngine("scripts/templates")
    updater = GCSIndexUpdater(engine, gcs_client, serve_bucket)
    all_releases = load_all_release_data_from_gcs(gcs_client, serve_bucket, tool["id"])
    latest = all_releases[0] if all_releases else None
    month_groups = group_by_month(all_releases[1:]) if len(all_releases) > 1 else []
    updater.rebuild_panel(tool, latest=latest, month_groups=month_groups,
                         is_default=tool.get("is_default", False))

    # Update the latest pointer in GCS
    if latest:
        blob = gcs_client.bucket(serve_bucket).blob(f"{tool['id']}/latest")
        blob.upload_from_string(latest["version"], content_type="text/plain")


def run_generator(
    input_bucket: str,
    serve_bucket: str,
    config: dict,
) -> dict:
    """Core logic, extracted for testability."""
    gcs_client = storage.Client()
    gemini_extractor = GeminiExtractor(VertexGeminiClient(), ResponseValidator())
    gcs_md_source = GCSMarkdownSource(gcs_client)
    gcs_artifact_store = GCSArtifactStore(gcs_client)

    processed = 0
    skipped = 0
    errors = 0

    blobs = gcs_client.bucket(input_bucket).list_blobs()
    for blob in blobs:
        if not blob.name.endswith(".md"):
            continue
        parts = blob.name.split("/")
        if len(parts) != 2:
            continue
        tool_id, filename = parts
        version = filename[:-3]  # strip .md

        tool = next((t for t in config["tools"] if t["id"] == tool_id), None)
        if tool is None:
            logger.warning(json.dumps({"action": "skip", "tool_id": tool_id,
                                       "version": version, "reason": "unknown_tool"}))
            skipped += 1
            continue

        # For hotfixes, check parent exists before attempting
        if is_hotfix(version):
            pv = parent_version(version)
            parent_blob = gcs_client.bucket(serve_bucket).blob(f"{tool_id}/{pv}.json")
            if not parent_blob.exists():
                logger.warning(json.dumps({"action": "skip", "tool_id": tool_id,
                                           "version": version, "reason": "parent_not_found",
                                           "parent": pv}))
                skipped += 1
                continue

        try:
            artifact = process_release(
                tool_id, version,
                input_bucket, serve_bucket,
                gemini_extractor=gemini_extractor,
                gcs_md_source=gcs_md_source,
                gcs_artifact_store=gcs_artifact_store,
                config=config,
            )
            # For hotfixes, render the parent page (which now includes the fix)
            render_target_version = parent_version(version) if is_hotfix(version) else version
            render_version(tool, render_target_version, artifact, gcs_client, serve_bucket)
            logger.info(json.dumps({"action": "processed", "tool_id": tool_id,
                                    "version": version, "type":
                                    "hotfix" if is_hotfix(version) else "major"}))
            processed += 1
        except Exception as exc:
            logger.error(json.dumps({"action": "error", "tool_id": tool_id,
                                     "version": version, "error": str(exc)}))
            errors += 1

    # Rebuild index panel for every tool that declares a panel_id in tools.yaml
    for tool in config["tools"]:
        if "panel_id" not in tool:
            continue
        try:
            rebuild_index(tool, gcs_client, serve_bucket)
        except Exception as exc:
            logger.error(json.dumps({"action": "index_error", "tool_id": tool["id"],
                                     "error": str(exc)}))

    summary = {"processed": processed, "skipped": skipped, "errors": errors}
    logger.info(json.dumps({"action": "summary", **summary}))
    return summary


@functions_framework.http
def handle(request):
    """HTTP Cloud Function entry point."""
    try:
        config = load_config("config/tools.yaml")
        summary = run_generator(INPUT_BUCKET, SERVE_BUCKET, config)
        status = 500 if summary["errors"] > 0 else 200
        return json.dumps(summary), status, {"Content-Type": "application/json"}
    except Exception as exc:
        logger.error(json.dumps({"action": "fatal_error", "error": str(exc)}))
        return json.dumps({"error": str(exc)}), 500, {"Content-Type": "application/json"}
