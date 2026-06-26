import json
import re
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from scripts.render import (
    load_assets,
    load_all_versions,
    load_all_release_data,
    TemplateEngine,
    IndexUpdater,
    HTMLRenderer,
)

SAMPLE_ARTIFACT = json.loads(
    Path("tests/fixtures/sample_artifact.json").read_text()
)


def write_artifact(tmp_path, version, artifact=None):
    d = tmp_path / "data" / "cortex-catalyst"
    d.mkdir(parents=True, exist_ok=True)
    data = artifact or {**SAMPLE_ARTIFACT, "version": version}
    (d / f"{version}.json").write_text(json.dumps(data))
    return data


def test_load_all_versions_sorts_newest_first(tmp_path):
    for v in ["26.6.1", "26.7.1"]:
        write_artifact(tmp_path, v, {**SAMPLE_ARTIFACT, "version": v, "date": f"Month {v}"})

    versions = load_all_versions(str(tmp_path / "data" / "cortex-catalyst"), "26.7.1")
    assert versions[0]["version"] == "26.7.1"
    assert versions[0]["is_current"] is True
    assert versions[1]["version"] == "26.6.1"
    assert versions[1]["is_current"] is False


def test_load_all_release_data_returns_sorted(tmp_path):
    for v in ["26.6.1", "26.7.1"]:
        write_artifact(tmp_path, v, {**SAMPLE_ARTIFACT, "version": v})

    releases = load_all_release_data(str(tmp_path / "data" / "cortex-catalyst"))
    assert releases[0]["version"] == "26.7.1"


def test_template_engine_renders_release_page(tmp_path):
    assets = load_assets("cortex-catalyst/26.6.1.html")
    engine = TemplateEngine("scripts/templates")
    html = engine.render(
        "release-page.html.j2",
        favicon=assets["favicon"],
        logo=assets["logo"],
        bg=assets["bg"],
        tool_name="Cortex® Catalyst",
        tool_description="Test description.",
        app_url="https://example.com",
        app_url_display="example.com",
        version="26.7.1",
        date="July 2026",
        summary="Test summary.",
        entries=SAMPLE_ARTIFACT["entries"],
        release_url="https://github.com/...",
        all_versions=[{"version": "26.7.1", "label": "July 2026 — 26.7.1",
                       "is_current": True, "href": "26.7.1.html"}],
    )
    assert "26.7.1" in html
    assert "Citation Panel" in html
    assert "tag-feature" in html
    assert "<!DOCTYPE html>" in html


def test_index_updater_replaces_panel(tmp_path):
    # Write a minimal index.html with the catalyst panel
    index_content = '''\
<div class="layout">
  <aside class="sidebar"></aside>
  <main class="content">
        <div class="tool-panel active" id="panel-catalyst">
          <h2 class="tool-title">Cortex® Catalyst</h2>
          <div class="coming-soon"><div class="coming-soon-dot"></div>OLD CONTENT</div>
        </div>

        <div class="tool-panel" id="panel-insights">
'''
    index_path = tmp_path / "index.html"
    index_path.write_text(index_content)

    engine = TemplateEngine("scripts/templates")
    updater = IndexUpdater(engine, str(index_path))

    tool = {
        "name": "Cortex® Catalyst",
        "description": "Test.",
        "folder": "cortex-catalyst",
        "panel_id": "catalyst",
    }
    latest = {"version": "26.7.1", "date": "July 2026", "summary": "Test summary."}
    updater.rebuild_catalyst_panel(tool, latest=latest, month_groups=[], is_default=True)

    updated = index_path.read_text()
    assert "OLD CONTENT" not in updated
    assert "26.7.1" in updated
    assert "Latest" in updated
