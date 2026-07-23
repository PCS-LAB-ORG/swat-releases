import base64
import json
import re
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from scripts.render import (
    load_assets,
    load_all_versions,
    load_all_release_data,
    load_all_release_data_from_gcs,
    TemplateEngine,
    IndexUpdater,
    HTMLRenderer,
    GCSIndexUpdater,
    GCSHTMLRenderer,
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


def test_load_assets_reads_pngs_from_images_dir():
    assets = load_assets("images")
    assert assets["favicon"].startswith("data:image/png;base64,")
    assert assets["logo"].startswith("data:image/png;base64,")
    assert assets["bg"].startswith("data:image/png;base64,")
    # Verify it's valid base64
    base64.b64decode(assets["favicon"].split(",")[1])


def test_load_all_versions_sorts_newest_first(tmp_path):
    for v in ["26.6.1", "26.7.1"]:
        write_artifact(tmp_path, v, {**SAMPLE_ARTIFACT, "version": v, "date": f"Month {v}"})

    versions = load_all_versions(str(tmp_path / "data" / "cortex-catalyst"), "26.7.1")
    assert versions[0]["version"] == "26.7.1"
    assert versions[0]["is_current"] is True
    assert versions[1]["version"] == "26.6.1"
    assert versions[1]["is_current"] is False


def test_load_all_versions_href_has_no_html_extension(tmp_path):
    write_artifact(tmp_path, "26.7.1", {**SAMPLE_ARTIFACT, "version": "26.7.1"})
    versions = load_all_versions(str(tmp_path / "data" / "cortex-catalyst"), "26.7.1")
    assert versions[0]["href"] == "26.7.1"
    assert not versions[0]["href"].endswith(".html")


def test_load_all_release_data_returns_sorted(tmp_path):
    for v in ["26.6.1", "26.7.1"]:
        write_artifact(tmp_path, v, {**SAMPLE_ARTIFACT, "version": v})

    releases = load_all_release_data(str(tmp_path / "data" / "cortex-catalyst"))
    assert releases[0]["version"] == "26.7.1"


def test_load_all_release_data_from_gcs_returns_major_only():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    artifact_261 = {**SAMPLE_ARTIFACT, "version": "26.6.1", "date": "June 2026"}
    artifact_271 = {**SAMPLE_ARTIFACT, "version": "26.7.1", "date": "July 2026"}
    hotfix_blob_name = "cortex-catalyst/26.7.1.01.json"  # should be excluded

    def make_blob(name, data):
        b = MagicMock()
        b.name = name
        b.download_as_text.return_value = json.dumps(data)
        return b

    mock_bucket.list_blobs.return_value = [
        make_blob("cortex-catalyst/26.6.1.json", artifact_261),
        make_blob("cortex-catalyst/26.7.1.json", artifact_271),
        make_blob(hotfix_blob_name, {"version": "26.7.1.01"}),  # 4-part, excluded
    ]

    releases = load_all_release_data_from_gcs(mock_client, "swat-releases-serve", "cortex-catalyst")

    assert len(releases) == 2
    assert releases[0]["version"] == "26.7.1"
    assert releases[1]["version"] == "26.6.1"
    versions = [r["version"] for r in releases]
    assert "26.7.1.01" not in versions


def test_template_engine_renders_release_page():
    assets = load_assets("images")
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
        fixes=[],
        release_url="https://github.com/...",
        all_versions=[{"version": "26.7.1", "label": "July 2026 — 26.7.1",
                       "is_current": True, "href": "26.7.1"}],
    )
    assert "26.7.1" in html
    assert "Citation Panel" in html
    assert "tag-feature" in html
    assert "<!DOCTYPE html>" in html


def test_template_engine_renders_fixes_section():
    assets = load_assets("images")
    engine = TemplateEngine("scripts/templates")
    fixes = [
        {
            "version": "26.7.1.01",
            "date": "July 2026",
            "entries": [
                {"tag": "Fixed", "title": "Auth timeout", "description": "Fixed session timeout bug."}
            ],
        }
    ]
    html = engine.render(
        "release-page.html.j2",
        favicon=assets["favicon"],
        logo=assets["logo"],
        bg=assets["bg"],
        tool_name="Cortex® Catalyst",
        tool_description="Test description.",
        app_url="",
        app_url_display="",
        version="26.7.1",
        date="July 2026",
        summary="Test summary.",
        entries=SAMPLE_ARTIFACT["entries"],
        fixes=fixes,
        release_url="https://github.com/...",
        all_versions=[],
    )
    assert "Fixes" in html
    assert "26.7.1.01" in html
    assert "Auth timeout" in html


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
    updater.rebuild_panel(tool, latest=latest, month_groups=[], is_default=True)

    updated = index_path.read_text()
    assert "OLD CONTENT" not in updated
    assert "26.7.1" in updated
    assert "Latest" in updated


def test_catalyst_panel_template_hrefs_have_no_html_extension():
    engine = TemplateEngine("scripts/templates")
    tool = {
        "name": "Cortex® Catalyst",
        "description": "Test.",
        "folder": "cortex-catalyst",
        "panel_id": "catalyst",
    }
    latest = {"version": "26.7.1", "date": "July 2026", "summary": "Test summary."}
    html = engine.render(
        "catalyst-panel.html.j2",
        tool=tool,
        latest=latest,
        month_groups=[],
        is_default=True,
    )
    assert "cortex-catalyst/26.7.1" in html
    assert "cortex-catalyst/26.7.1.html" not in html


def test_gcs_index_updater_uploads_updated_index():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    index_content = '''\
<div class="layout">
        <div class="tool-panel active" id="panel-catalyst">
          <h2>OLD</h2>
        </div>

        <div class="tool-panel" id="panel-insights">
'''
    mock_blob.download_as_text.return_value = index_content

    engine = TemplateEngine("scripts/templates")
    updater = GCSIndexUpdater(engine, mock_client, "swat-releases-serve")

    tool = {
        "name": "Cortex® Catalyst",
        "description": "Test.",
        "folder": "cortex-catalyst",
        "panel_id": "catalyst",
    }
    latest = {"version": "26.7.1", "date": "July 2026", "summary": "Test summary."}
    updater.rebuild_panel(tool, latest=latest, month_groups=[], is_default=True)

    mock_blob.upload_from_string.assert_called_once()
    uploaded_html = mock_blob.upload_from_string.call_args[0][0]
    assert "OLD" not in uploaded_html
    assert "26.7.1" in uploaded_html


def test_index_updater_rebuild_panel_works_for_non_catalyst_panel(tmp_path):
    index_content = '''\
<div class="layout">
  <aside class="sidebar"></aside>
  <main class="content">
        <div class="tool-panel active" id="panel-catalyst">
          <h2 class="tool-title">Cortex® Catalyst</h2>
        </div>

        <div class="tool-panel" id="panel-session-planner">
          <h2 class="tool-title">Session Planner</h2>
          <div class="coming-soon">Release notes coming soon.</div>
        </div>

        <div class="tool-panel" id="panel-other">
'''
    index_path = tmp_path / "index.html"
    index_path.write_text(index_content)

    engine = TemplateEngine("scripts/templates")
    updater = IndexUpdater(engine, str(index_path))

    tool = {
        "name": "Session Planner",
        "description": "",
        "folder": "session-planner",
        "panel_id": "session-planner",
    }
    latest = {"version": "26.7.1", "date": "July 2026", "summary": "Test."}
    updater.rebuild_panel(tool, latest=latest, month_groups=[], is_default=False)

    updated = index_path.read_text()
    assert "coming soon" not in updated
    assert "session-planner/26.7.1" in updated
    assert "Latest" in updated
    # catalyst panel must be untouched
    assert 'id="panel-catalyst"' in updated


def test_index_updater_rebuild_panel_last_panel_uses_main_close_boundary(tmp_path):
    index_content = '''\
<div class="layout">
  <main class="content">
        <div class="tool-panel active" id="panel-catalyst">
          <h2>Catalyst</h2>
        </div>

        <div class="tool-panel" id="panel-ai-sweeper">
          <div class="coming-soon">Release notes coming soon.</div>
        </div>

      </main>
    </div>
'''
    index_path = tmp_path / "index.html"
    index_path.write_text(index_content)

    engine = TemplateEngine("scripts/templates")
    updater = IndexUpdater(engine, str(index_path))

    tool = {
        "name": "AI Sweeper",
        "description": "",
        "folder": "ai-sweeper",
        "panel_id": "ai-sweeper",
    }
    latest = {"version": "26.7.1", "date": "July 2026", "summary": "Test."}
    updater.rebuild_panel(tool, latest=latest, month_groups=[], is_default=False)

    updated = index_path.read_text()
    assert "coming soon" not in updated
    assert "ai-sweeper/26.7.1" in updated
    # Structure after the replaced panel must still contain </main>
    assert "</main>" in updated
    # catalyst panel untouched
    assert 'id="panel-catalyst"' in updated


def test_rebuild_index_only_catalyst_gets_is_default_true():
    from scripts.generator.main import rebuild_index
    from scripts.render import group_by_month

    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    mock_bucket.list_blobs.return_value = []

    index_content = '''\
<div class="layout">
  <main class="content">
        <div class="tool-panel active" id="panel-session-planner">
          <div class="coming-soon">OLD</div>
        </div>

      </main>
'''
    mock_blob.download_as_text.return_value = index_content

    engine_mock = MagicMock()
    engine_mock.render.return_value = '<div class="tool-panel" id="panel-session-planner">NEW</div>'

    from unittest.mock import patch
    with patch("scripts.generator.main.TemplateEngine", return_value=engine_mock), \
         patch("scripts.generator.main.GCSIndexUpdater") as mock_updater_cls, \
         patch("scripts.generator.main.load_all_release_data_from_gcs", return_value=[]):
        mock_updater = MagicMock()
        mock_updater_cls.return_value = mock_updater

        session_tool = {
            "id": "session-planner", "folder": "session-planner",
            "name": "Session Planner", "description": "", "panel_id": "session-planner",
        }
        rebuild_index(session_tool, mock_client, "swat-releases-serve")

    mock_updater.rebuild_panel.assert_called_once()
    call_kwargs = mock_updater.rebuild_panel.call_args
    assert call_kwargs.kwargs.get("is_default") is False or call_kwargs.args[3] is False


def test_gcs_html_renderer_uploads_release_page():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    assets = load_assets("images")
    engine = TemplateEngine("scripts/templates")
    mock_updater = MagicMock()
    renderer = GCSHTMLRenderer(engine, mock_updater, assets, mock_client)

    tool = {
        "name": "Cortex® Catalyst",
        "description": "Test.",
        "folder": "cortex-catalyst",
        "panel_id": "catalyst",
        "app_url": "",
    }
    data = {**SAMPLE_ARTIFACT, "version": "26.7.1"}
    renderer.render_and_upload(
        tool=tool,
        version="26.7.1",
        data=data,
        all_versions=[],
        serve_bucket="swat-releases-serve",
    )

    mock_bucket.blob.assert_called_once_with("cortex-catalyst/26.7.1.html")
    mock_blob.upload_from_string.assert_called_once()
    uploaded_html = mock_blob.upload_from_string.call_args[0][0]
    assert "26.7.1" in uploaded_html
    assert "<!DOCTYPE html>" in uploaded_html
