import json
import logging
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


def test_upload_get_contains_file_input(client):
    resp = client.get("/upload")
    body = resp.data.decode()
    assert 'type="file"' in body
    assert 'accept=".md' in body


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


def test_upload_post_gcs_exception_returns_styled_500(client, mock_storage):
    blob = _mock_blob(exists=False)
    blob.upload_from_string.side_effect = Exception("GCS unavailable")
    mock_storage.bucket.return_value.blob.return_value = blob

    resp = client.post("/upload", data={
        "tool_id": "cortex-catalyst",
        "version": "26.7.1",
        "content": "# Notes\n\nContent.",
    })
    assert resp.status_code == 500
    body = resp.data.decode()
    assert "Upload Release Notes" in body  # styled form, not raw Flask error
    assert "failed" in body.lower()
    assert "26.7.1" in body  # draft preserved


def test_upload_post_duplicate_returns_409(client, mock_storage):
    blob = _mock_blob(exists=True)
    mock_storage.bucket.return_value.blob.return_value = blob

    resp = client.post("/upload", data={
        "tool_id": "cortex-catalyst",
        "version": "26.7.1",
        "content": "# Notes\n\nContent.",
    })
    assert resp.status_code == 409


# ── Structured logging ────────────────────────────────────────────────────────
# app.logger has propagate=False and a custom StreamHandler, so caplog cannot
# intercept its records. We mock app.logger methods directly instead.

def test_upload_success_emits_structured_log(client, mock_storage):
    blob = _mock_blob(exists=False)
    mock_storage.bucket.return_value.blob.return_value = blob

    with patch.object(app.logger, "info") as mock_info:
        resp = client.post("/upload", data={
            "tool_id": "cortex-catalyst", "version": "26.7.1",
            "content": "# Notes\n\nContent.",
        })

    assert resp.status_code == 200
    success_calls = [
        c for c in mock_info.call_args_list
        if c.args[0] == "upload_success"
    ]
    assert success_calls, "Expected app.logger.info('upload_success', ...)"
    fields = success_calls[0].kwargs.get("extra", {}).get("fields", {})
    assert fields.get("action") == "upload_success"
    assert fields.get("tool_id") == "cortex-catalyst"
    assert fields.get("version") == "26.7.1"
    assert "gcs_path" in fields


def test_upload_gcs_error_emits_structured_log(client, mock_storage):
    blob = _mock_blob(exists=False)
    blob.upload_from_string.side_effect = Exception("network timeout")
    mock_storage.bucket.return_value.blob.return_value = blob

    with patch.object(app.logger, "error") as mock_error:
        resp = client.post("/upload", data={
            "tool_id": "cortex-catalyst", "version": "26.7.1",
            "content": "# Notes\n\nContent.",
        })

    assert resp.status_code == 500
    error_calls = [
        c for c in mock_error.call_args_list
        if c.args[0] == "upload_error"
    ]
    assert error_calls, "Expected app.logger.error('upload_error', ...)"
    fields = error_calls[0].kwargs.get("extra", {}).get("fields", {})
    assert fields.get("action") == "upload_error"
    assert "network timeout" in fields.get("error", "")


def test_json_formatter_emits_valid_json():
    from gateway.main import _JsonFormatter
    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="test_event", args=(), exc_info=None,
    )
    record.fields = {"action": "proxy", "status": 200, "latency_ms": 42}
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["severity"] == "INFO"
    assert parsed["message"] == "test_event"
    assert parsed["action"] == "proxy"
    assert parsed["status"] == 200
    assert parsed["latency_ms"] == 42
