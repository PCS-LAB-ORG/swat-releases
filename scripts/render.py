"""render.py — render HTML from a JSON artifact and rebuild index.html panel."""
from __future__ import annotations

import base64 as _b64
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from google.cloud import storage as _gcs_storage


# ── Asset loading ────────────────────────────────────────────────────────────

def load_assets(images_dir: str = "images") -> dict:
    """Base64-encode PNG assets from the images/ directory."""
    img_dir = Path(images_dir)
    return {
        "favicon": "data:image/png;base64," + _b64.b64encode(
            (img_dir / "cortex-icon.png").read_bytes()
        ).decode(),
        "logo": "data:image/png;base64," + _b64.b64encode(
            (img_dir / "cortex_RGB_logo_By-Line_Negative.png").read_bytes()
        ).decode(),
        "bg": "data:image/png;base64," + _b64.b64encode(
            (img_dir / "cortex-background.png").read_bytes()
        ).decode(),
    }


# ── Version and release data helpers ─────────────────────────────────────────

def load_all_versions(data_folder: str, current_version: str,
                      html_folder: str | None = None) -> list[dict]:
    """Build version nav list from JSON artifacts + existing HTML pages, newest first."""
    seen: dict[str, dict] = {}

    # 1. JSON artifacts (generated releases) — date comes from the artifact
    data_dir = Path(data_folder)
    for json_file in data_dir.glob("*.json"):
        data = json.loads(json_file.read_text())
        v = data["version"]
        seen[v] = {
            "version": v,
            "label": f"{data['date']} — {v}",
            "is_current": v == current_version,
            "href": f"{v}",
        }

    # 2. Hand-authored HTML pages without a JSON artifact — extract date from HTML
    if html_folder:
        date_re = re.compile(
            r'<div class="hero-meta-item"><strong>Released</strong>\s*&nbsp;([^<]+)</div>'
        )
        for html_file in Path(html_folder).glob("*.html"):
            v = html_file.stem
            if v in seen:
                continue  # already have it from JSON
            match = date_re.search(html_file.read_text())
            date = match.group(1).strip() if match else v
            seen[v] = {
                "version": v,
                "label": f"{date} — {v}",
                "is_current": v == current_version,
                "href": f"{v}",
            }

    return sorted(seen.values(), key=lambda x: x["version"], reverse=True)


def load_all_release_data(data_folder: str,
                          html_folder: str | None = None) -> list[dict]:
    """Return all releases (JSON artifacts + HTML-only pages) newest first."""
    seen: dict[str, dict] = {}
    for json_file in Path(data_folder).glob("*.json"):
        data = json.loads(json_file.read_text())
        seen[data["version"]] = data
    if html_folder:
        date_re = re.compile(
            r'<div class="hero-meta-item"><strong>Released</strong>\s*&nbsp;([^<]+)</div>'
        )
        for html_file in Path(html_folder).glob("*.html"):
            v = html_file.stem
            if v in seen:
                continue
            match = date_re.search(html_file.read_text())
            seen[v] = {
                "version": v,
                "date": match.group(1).strip() if match else v,
                "summary": "",
                "release_url": "",
                "entries": [],
            }
    return sorted(seen.values(), key=lambda x: x["version"], reverse=True)


def load_all_release_data_from_gcs(
    storage_client: "_gcs_storage.Client",
    serve_bucket: str,
    tool_id: str,
) -> list[dict]:
    """Return all major release artifacts from GCS serving bucket, newest first.

    Hotfix artifacts (4-part versions like 26.7.1.01) are excluded because
    their content is merged into the parent artifact's 'fixes' list.
    """
    bucket = storage_client.bucket(serve_bucket)
    blobs = bucket.list_blobs(prefix=f"{tool_id}/")
    result = []
    for blob in blobs:
        if not blob.name.endswith(".json"):
            continue
        filename = blob.name.split("/")[-1]
        version = filename[:-5]  # strip .json
        if len(version.split(".")) != 3:
            continue
        result.append(json.loads(blob.download_as_text()))
    return sorted(result, key=lambda x: x["version"], reverse=True)


def _group_by_month(releases: list[dict]) -> list[dict]:
    """Group releases by their 'date' field for panel rendering."""
    groups: dict[str, list] = {}
    for r in releases:
        month = r["date"]
        groups.setdefault(month, []).append(r)
    return [{"month": month, "releases": items} for month, items in groups.items()]


# ── SOLID components ─────────────────────────────────────────────────────────

class TemplateEngine:
    def __init__(self, templates_dir: str) -> None:
        self._env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(['html', 'j2']),
        )

    def render(self, template_name: str, **context) -> str:
        return self._env.get_template(template_name).render(**context)


class IndexUpdater:
    def __init__(self, engine: TemplateEngine, index_path: str) -> None:
        self._engine = engine
        self._index_path = Path(index_path)

    def rebuild_catalyst_panel(
        self,
        tool: dict,
        latest: dict,
        month_groups: list[dict],
        is_default: bool = True,
    ) -> None:
        panel_html = self._engine.render(
            "catalyst-panel.html.j2",
            tool=tool,
            latest=latest,
            month_groups=month_groups,
            is_default=is_default,
        )
        content = self._index_path.read_text()

        # Find the panel div start
        start_pattern = re.compile(
            r'<div class="tool-panel[^"]*" id="panel-catalyst">'
        )
        start_match = start_pattern.search(content)
        if not start_match:
            raise RuntimeError("Could not find panel-catalyst div in index.html")
        start = start_match.start()

        # Find the next tool-panel div (end boundary)
        next_panel_re = re.compile(r'\n\s+<div class="tool-panel[^"]*" id="panel-(?!catalyst)')
        next_panel = next_panel_re.search(content, start + 1)
        if not next_panel:
            raise RuntimeError("Could not find end boundary of panel-catalyst in index.html")
        end = next_panel.start()

        self._index_path.write_text(content[:start] + panel_html + "\n" + content[end:])


class HTMLRenderer:
    def __init__(
        self,
        engine: TemplateEngine,
        updater: IndexUpdater,
        assets: dict,
    ) -> None:
        self._engine = engine
        self._updater = updater
        self._assets = assets

    def render_release_page(
        self,
        tool: dict,
        version: str,
        data: dict,
        all_versions: list[dict],
    ) -> str:
        return self._engine.render(
            "release-page.html.j2",
            favicon=self._assets["favicon"],
            logo=self._assets["logo"],
            bg=self._assets["bg"],
            tool_name=tool["name"],
            tool_description=tool.get("description", "").strip(),
            app_url=tool.get("app_url", ""),
            app_url_display=tool.get("app_url", "").replace("https://", ""),
            version=version,
            date=data["date"],
            summary=data["summary"],
            entries=data["entries"],
            fixes=data.get("fixes", []),
            release_url=data["release_url"],
            all_versions=all_versions,
        )


# ── GCS-backed components ────────────────────────────────────────────────────

class GCSIndexUpdater:
    def __init__(
        self,
        engine: TemplateEngine,
        storage_client: "_gcs_storage.Client",
        serve_bucket: str,
    ) -> None:
        self._engine = engine
        self._client = storage_client
        self._bucket = serve_bucket

    def rebuild_catalyst_panel(
        self,
        tool: dict,
        latest: "dict | None",
        month_groups: list,
        is_default: bool,
    ) -> None:
        panel_html = self._engine.render(
            "catalyst-panel.html.j2",
            tool=tool,
            latest=latest,
            month_groups=month_groups,
            is_default=is_default,
        )
        blob = self._client.bucket(self._bucket).blob("index.html")
        content = blob.download_as_text()

        start_pattern = re.compile(r'<div class="tool-panel[^"]*" id="panel-catalyst">')
        start_match = start_pattern.search(content)
        if not start_match:
            raise RuntimeError("Could not find panel-catalyst div in index.html")
        start = start_match.start()

        next_panel_re = re.compile(r'\n\s+<div class="tool-panel[^"]*" id="panel-(?!catalyst)')
        next_panel = next_panel_re.search(content, start + 1)
        if not next_panel:
            raise RuntimeError("Could not find end boundary of panel-catalyst in index.html")
        end = next_panel.start()

        updated = content[:start] + panel_html + "\n" + content[end:]
        blob.upload_from_string(updated, content_type="text/html")


class GCSHTMLRenderer:
    def __init__(
        self,
        engine: TemplateEngine,
        updater: GCSIndexUpdater,
        assets: dict,
        storage_client: "_gcs_storage.Client",
    ) -> None:
        self._engine = engine
        self._updater = updater
        self._assets = assets
        self._client = storage_client

    def render_and_upload(
        self,
        tool: dict,
        version: str,
        data: dict,
        all_versions: list[dict],
        serve_bucket: str,
    ) -> None:
        html = self._engine.render(
            "release-page.html.j2",
            favicon=self._assets["favicon"],
            logo=self._assets["logo"],
            bg=self._assets["bg"],
            tool_name=tool["name"],
            tool_description=tool.get("description", "").strip(),
            app_url=tool.get("app_url", ""),
            app_url_display=tool.get("app_url", "").replace("https://", ""),
            version=version,
            date=data["date"],
            summary=data["summary"],
            entries=data["entries"],
            fixes=data.get("fixes", []),
            release_url=data["release_url"],
            all_versions=all_versions,
        )
        blob = self._client.bucket(serve_bucket).blob(f"{tool['folder']}/{version}.html")
        blob.upload_from_string(html, content_type="text/html")
