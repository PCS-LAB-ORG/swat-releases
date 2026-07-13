import os
import pytest
from unittest.mock import MagicMock, patch

# Keep module in local mode so module-level GCP init is skipped at import time
os.environ.setdefault("BACKEND_URL", "http://localhost:9999")

import gateway.main as proxy_module
from gateway.main import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def mock_storage():
    mock_client = MagicMock()
    with patch.object(proxy_module, "_storage_client", mock_client):
        yield mock_client


def _mock_blob(exists=False):
    blob = MagicMock()
    blob.exists.return_value = exists
    return blob


# ── GET /upload ──────────────────────────────────────────────────────────────

def test_upload_get_renders_form(client):
    resp = client.get("/upload")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Upload Release Notes" in body
    assert "<form" in body
    assert 'name="version"' in body
    assert 'name="content"' in body
    assert 'name="tool_id"' in body


def test_upload_get_contains_tool_option(client):
    resp = client.get("/upload")
    assert b"cortex-catalyst" in resp.data


# ── POST /upload — validation ────────────────────────────────────────────────

def test_upload_post_invalid_version_format(client):
    resp = client.post("/upload", data={
        "tool_id": "cortex-catalyst",
        "version": "not-a-version",
        "content": "# Notes\n\nContent here.",
    })
    assert resp.status_code == 400
    body = resp.data.decode()
    assert "Version must be" in body
    assert "not-a-version" in body
    assert "Content here" in body


def test_upload_post_empty_content(client):
    resp = client.post("/upload", data={
        "tool_id": "cortex-catalyst",
        "version": "26.7.1",
        "content": "",
    })
    assert resp.status_code == 400
    assert b"content is required" in resp.data


def test_upload_post_unknown_tool(client):
    resp = client.post("/upload", data={
        "tool_id": "unknown-tool",
        "version": "26.7.1",
        "content": "# Notes\n\nSomething.",
    })
    assert resp.status_code == 400
    assert b"Unknown tool" in resp.data


def test_upload_post_local_mode_503(client):
    resp = client.post("/upload", data={
        "tool_id": "cortex-catalyst",
        "version": "26.7.1",
        "content": "# Notes\n\nContent.",
    })
    assert resp.status_code == 503


# ── POST /upload — GCS paths ─────────────────────────────────────────────────

def test_upload_post_success_release(client, mock_storage):
    blob = _mock_blob(exists=False)
    mock_storage.bucket.return_value.blob.return_value = blob

    resp = client.post("/upload", data={
        "tool_id": "cortex-catalyst",
        "version": "26.7.1",
        "content": "# Release Notes\n\nSome content.",
    })
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "gs://swat-releases-input/cortex-catalyst/26.7.1.md" in body
    assert "within the hour" in body
    mock_storage.bucket.assert_called_with("swat-releases-input")
    blob.upload_from_string.assert_called_once()


def test_upload_post_success_hotfix(client, mock_storage):
    blob = _mock_blob(exists=False)
    mock_storage.bucket.return_value.blob.return_value = blob

    resp = client.post("/upload", data={
        "tool_id": "cortex-catalyst",
        "version": "26.7.1.01",
        "content": "# Hotfix Notes\n\nFix.",
    })
    assert resp.status_code == 200
    assert b"26.7.1.01.md" in resp.data


def test_upload_post_duplicate_returns_409(client, mock_storage):
    blob = _mock_blob(exists=True)
    mock_storage.bucket.return_value.blob.return_value = blob

    resp = client.post("/upload", data={
        "tool_id": "cortex-catalyst",
        "version": "26.7.1",
        "content": "# Notes\n\nContent.",
    })
    assert resp.status_code == 409
    body = resp.data.decode()
    assert "already exists" in body
    assert "26.7.1" in body
