import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from scripts.extract import (
    ResponseValidator,
    GeminiExtractor,
    GCSMarkdownSource,
    GCSArtifactStore,
    is_hotfix,
    parent_version,
    process_release,
)

VALID_ARTIFACT = json.loads(
    Path("tests/fixtures/sample_artifact.json").read_text()
)

VALID_JSON_STR = json.dumps(VALID_ARTIFACT)


# ── ResponseValidator ────────────────────────────────────────────────────────

def test_validator_accepts_valid_json():
    result = ResponseValidator().validate(VALID_JSON_STR)
    assert result["version"] == "26.7.1"
    assert len(result["entries"]) == 2


def test_validator_accepts_empty_entries():
    data = {**VALID_ARTIFACT, "entries": []}
    result = ResponseValidator().validate(json.dumps(data))
    assert result["entries"] == []


def test_validator_rejects_malformed_json():
    with pytest.raises(ValueError, match="Invalid JSON"):
        ResponseValidator().validate("not json {{{")


def test_validator_rejects_missing_version():
    data = {k: v for k, v in VALID_ARTIFACT.items() if k != "version"}
    with pytest.raises(ValueError, match="Missing required fields"):
        ResponseValidator().validate(json.dumps(data))


def test_validator_rejects_missing_summary():
    data = {k: v for k, v in VALID_ARTIFACT.items() if k != "summary"}
    with pytest.raises(ValueError, match="Missing required fields"):
        ResponseValidator().validate(json.dumps(data))


def test_validator_rejects_invalid_tag():
    entry = {"tag": "INVALID", "title": "Foo", "description": "Bar."}
    data = {**VALID_ARTIFACT, "entries": [entry]}
    with pytest.raises(ValueError, match="Invalid tag"):
        ResponseValidator().validate(json.dumps(data))


def test_validator_rejects_entry_missing_description():
    entry = {"tag": "Feature", "title": "Foo"}
    data = {**VALID_ARTIFACT, "entries": [entry]}
    with pytest.raises(ValueError, match="missing required keys"):
        ResponseValidator().validate(json.dumps(data))


# ── ResponseValidator.validate_hotfix ────────────────────────────────────────

def test_validate_hotfix_returns_entries():
    raw = json.dumps({"entries": [{"tag": "Fixed", "title": "Fix X", "description": "Desc."}]})
    entries = ResponseValidator().validate_hotfix(raw)
    assert len(entries) == 1
    assert entries[0]["tag"] == "Fixed"


def test_validate_hotfix_rejects_invalid_tag():
    raw = json.dumps({"entries": [{"tag": "BAD", "title": "X", "description": "Y"}]})
    with pytest.raises(ValueError, match="must use 'Fixed' tag"):
        ResponseValidator().validate_hotfix(raw)


def test_validate_hotfix_rejects_non_fixed_tag():
    raw = json.dumps({"entries": [{"tag": "Feature", "title": "X", "description": "Y"}]})
    with pytest.raises(ValueError, match="must use 'Fixed' tag"):
        ResponseValidator().validate_hotfix(raw)


def test_validate_hotfix_rejects_missing_entries_key():
    with pytest.raises(ValueError, match="must have an 'entries' list"):
        ResponseValidator().validate_hotfix(json.dumps({"version": "26.7.1.01"}))


# ── GeminiExtractor ──────────────────────────────────────────────────────────

def mock_gemini_client(response: str = VALID_JSON_STR):
    client = MagicMock()
    client.generate.return_value = response
    return client


def test_extractor_returns_validated_dict():
    extractor = GeminiExtractor(mock_gemini_client(), ResponseValidator())
    result = extractor.extract("test prompt", "test body", "26.7.1")
    assert result["version"] == "26.7.1"
    assert result["entries"][0]["tag"] == "Feature"


def test_extractor_extract_sets_version():
    mock_client = MagicMock()
    mock_client.generate.return_value = json.dumps({
        **VALID_ARTIFACT,
        "version": "wrong-from-gemini",
    })
    extractor = GeminiExtractor(mock_client, ResponseValidator())
    result = extractor.extract("sys", "md content", "26.7.1")
    assert result["version"] == "26.7.1"


def test_extractor_extract_hotfix_returns_entries():
    mock_client = MagicMock()
    mock_client.generate.return_value = json.dumps({
        "entries": [{"tag": "Fixed", "title": "Fix Y", "description": "Resolved crash."}]
    })
    extractor = GeminiExtractor(mock_client, ResponseValidator())
    entries = extractor.extract_hotfix("sys", "md content", "26.7.1.01")
    assert entries[0]["tag"] == "Fixed"


def test_extractor_raises_on_invalid_gemini_response():
    client = mock_gemini_client(response="not json")
    extractor = GeminiExtractor(client, ResponseValidator())
    with pytest.raises(ValueError, match="Invalid JSON"):
        extractor.extract("p", "body", "26.7.1")


# ── Version classification ───────────────────────────────────────────────────

def test_is_hotfix_returns_false_for_major():
    assert is_hotfix("26.7.1") is False


def test_is_hotfix_returns_true_for_four_part():
    assert is_hotfix("26.7.1.01") is True


def test_parent_version_extracts_three_parts():
    assert parent_version("26.7.1.01") == "26.7.1"
    assert parent_version("26.7.1.02") == "26.7.1"


# ── GCSMarkdownSource ────────────────────────────────────────────────────────

def test_gcs_markdown_source_reads_blob():
    mock_client = MagicMock()
    mock_blob = MagicMock()
    mock_blob.download_as_text.return_value = "# Release\nAdded feature X."
    mock_client.bucket.return_value.blob.return_value = mock_blob

    source = GCSMarkdownSource(mock_client)
    result = source.read("my-bucket", "cortex-catalyst", "26.7.1")

    mock_client.bucket.assert_called_once_with("my-bucket")
    mock_client.bucket.return_value.blob.assert_called_once_with("cortex-catalyst/26.7.1.md")
    assert result == "# Release\nAdded feature X."


# ── GCSArtifactStore ─────────────────────────────────────────────────────────

def test_gcs_artifact_store_read_json_returns_none_when_missing():
    from google.cloud.exceptions import NotFound
    mock_client = MagicMock()
    mock_blob = MagicMock()
    mock_blob.download_as_text.side_effect = NotFound("not found")
    mock_client.bucket.return_value.blob.return_value = mock_blob

    store = GCSArtifactStore(mock_client)
    result = store.read_json("my-bucket", "cortex-catalyst", "26.7.1")
    assert result is None


def test_gcs_artifact_store_write_json_uploads_blob():
    mock_client = MagicMock()
    mock_blob = MagicMock()
    mock_client.bucket.return_value.blob.return_value = mock_blob

    store = GCSArtifactStore(mock_client)
    data = {"version": "26.7.1", "entries": []}
    store.write_json("my-bucket", "cortex-catalyst", "26.7.1", data)

    mock_client.bucket.return_value.blob.assert_called_once_with("cortex-catalyst/26.7.1.json")
    mock_blob.upload_from_string.assert_called_once_with(
        json.dumps(data, indent=2), content_type="application/json"
    )


# ── process_release ──────────────────────────────────────────────────────────

SAMPLE_CONFIG = {"tools": [{"id": "cortex-catalyst", "name": "Cortex® Catalyst",
    "folder": "cortex-catalyst", "prompt": "scripts/prompts/model1_user_facing.txt",
    "repo": "PCS-LAB-ORG/catalyst-rag-agent", "panel_id": "catalyst", "model": "user-facing",
    "description": "Test.", "app_url": "https://example.com"}]}


def test_process_release_major_writes_artifact():
    mock_extractor = MagicMock()
    mock_md_source = MagicMock()
    mock_artifact_store = MagicMock()

    mock_md_source.read.return_value = "# Release notes\nFeature X added."
    mock_artifact_store.read_json.return_value = None  # not yet processed
    mock_extractor.extract.return_value = {**VALID_ARTIFACT, "fixes": []}

    result = process_release(
        "cortex-catalyst", "26.7.1",
        "swat-releases-input", "swat-releases-serve",
        gemini_extractor=mock_extractor,
        gcs_md_source=mock_md_source,
        gcs_artifact_store=mock_artifact_store,
        config=SAMPLE_CONFIG,
    )

    mock_artifact_store.write_json.assert_called_once()
    assert result["version"] == "26.7.1"


def test_process_release_major_skips_when_exists():
    mock_extractor = MagicMock()
    mock_md_source = MagicMock()
    mock_artifact_store = MagicMock()
    mock_artifact_store.read_json.return_value = {**VALID_ARTIFACT}  # already exists

    process_release(
        "cortex-catalyst", "26.7.1",
        "swat-releases-input", "swat-releases-serve",
        gemini_extractor=mock_extractor,
        gcs_md_source=mock_md_source,
        gcs_artifact_store=mock_artifact_store,
        config=SAMPLE_CONFIG,
    )
    mock_extractor.extract.assert_not_called()


def test_process_release_hotfix_appends_to_parent():
    mock_extractor = MagicMock()
    mock_md_source = MagicMock()
    mock_artifact_store = MagicMock()

    parent = {**VALID_ARTIFACT, "fixes": []}
    mock_artifact_store.read_json.return_value = parent
    mock_md_source.read.return_value = "# Fix notes\nCrash resolved."
    mock_extractor.extract_hotfix.return_value = [
        {"tag": "Fixed", "title": "Crash fix", "description": "Resolved crash."}
    ]

    result = process_release(
        "cortex-catalyst", "26.7.1.01",
        "swat-releases-input", "swat-releases-serve",
        gemini_extractor=mock_extractor,
        gcs_md_source=mock_md_source,
        gcs_artifact_store=mock_artifact_store,
        config=SAMPLE_CONFIG,
    )

    assert len(result["fixes"]) == 1
    assert result["fixes"][0]["version"] == "26.7.1.01"
    mock_artifact_store.write_json.assert_called_once()


def test_process_release_hotfix_errors_when_no_parent():
    mock_artifact_store = MagicMock()
    mock_artifact_store.read_json.return_value = None

    with pytest.raises(RuntimeError, match="Parent artifact"):
        process_release(
            "cortex-catalyst", "26.7.1.01",
            "swat-releases-input", "swat-releases-serve",
            gemini_extractor=MagicMock(),
            gcs_md_source=MagicMock(),
            gcs_artifact_store=mock_artifact_store,
            config=SAMPLE_CONFIG,
        )
