"""render.py — render HTML from a JSON artifact and rebuild index.html panel.

Usage: python scripts/render.py <tool_id> <version>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scripts.poll import load_config


# ── Asset loading ────────────────────────────────────────────────────────────

def load_assets(source_html: str | None = None, folder: str | None = None) -> dict:
    """Extract base64 image data URIs from an existing release page."""
    if source_html is None:
        if folder is None:
            raise ValueError("Either source_html or folder must be provided")
        candidates = sorted(Path(folder).glob("*.html"), reverse=True)
        if not candidates:
            raise RuntimeError(f"No HTML files found in {folder} to extract assets from")
        source_html = str(candidates[0])
    content = Path(source_html).read_text()
    favicon_match = re.search(r'href="(data:image/png;base64,[^"]+)"', content)
    logo_match = re.search(r'<img src="(data:image/png;base64,[^"]+)"', content)
    bg_match = re.search(
        r"background-image:\s*url\('(data:image/png;base64,[^']+)'\)", content
    )
    if not (favicon_match and logo_match and bg_match):
        raise RuntimeError(f"Could not extract base64 assets from {source_html}")
    return {
        "favicon": favicon_match.group(1),
        "logo": logo_match.group(1),
        "bg": bg_match.group(1),
    }


# ── Version and release data helpers ─────────────────────────────────────────

def load_all_versions(data_folder: str, current_version: str) -> list[dict]:
    """Build version nav list from all JSON artifacts, newest first."""
    folder = Path(data_folder)
    versions = []
    for json_file in sorted(folder.glob("*.json"), key=lambda f: f.stem, reverse=True):
        data = json.loads(json_file.read_text())
        v = data["version"]
        versions.append({
            "version": v,
            "label": f"{data['date']} — {v}",
            "is_current": v == current_version,
            "href": f"{v}.html",
        })
    return versions


def load_all_release_data(data_folder: str) -> list[dict]:
    """Return all release artifacts as a list of dicts, newest first."""
    folder = Path(data_folder)
    releases = []
    for json_file in sorted(folder.glob("*.json"), key=lambda f: f.stem, reverse=True):
        releases.append(json.loads(json_file.read_text()))
    return releases


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
            release_url=data["release_url"],
            all_versions=all_versions,
        )


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python scripts/render.py <tool_id> <version>", file=sys.stderr)
        sys.exit(1)

    tool_id = sys.argv[1]
    version = sys.argv[2]

    config = load_config("config/tools.yaml")
    tool = next(t for t in config["tools"] if t["id"] == tool_id)

    data_folder = Path("data") / tool["folder"]
    json_path = data_folder / f"{version}.json"
    data = json.loads(json_path.read_text())

    assets = load_assets(folder=tool["folder"])
    all_versions = load_all_versions(str(data_folder), version)

    engine = TemplateEngine("scripts/templates")
    updater = IndexUpdater(engine, "index.html")
    renderer = HTMLRenderer(engine, updater, assets)

    # Render release page
    html = renderer.render_release_page(tool, version, data, all_versions)
    output_path = Path(tool["folder"]) / f"{version}.html"
    output_path.write_text(html)
    print(f"Written: {output_path}", file=sys.stderr)

    # Re-render all OTHER existing JSON-backed pages to update their version nav
    for other_json in sorted(data_folder.glob("*.json")):
        other_version = other_json.stem
        if other_version == version:
            continue  # already rendered above
        other_data = json.loads(other_json.read_text())
        other_all_versions = load_all_versions(str(data_folder), other_version)
        other_html = renderer.render_release_page(tool, other_version, other_data, other_all_versions)
        other_path = Path(tool["folder"]) / f"{other_version}.html"
        # Only update if the file exists (don't create pages for JSON-only artifacts)
        if other_path.exists():
            other_path.write_text(other_html)
            print(f"Updated nav: {other_path}", file=sys.stderr)

    # Rebuild index.html panel from all artifacts
    all_releases = load_all_release_data(str(data_folder))
    latest = all_releases[0] if all_releases else None
    month_groups = _group_by_month(all_releases[1:]) if len(all_releases) > 1 else []
    updater.rebuild_catalyst_panel(tool, latest=latest,
                                   month_groups=month_groups, is_default=True)
    print("Updated: index.html", file=sys.stderr)


if __name__ == "__main__":
    main()
