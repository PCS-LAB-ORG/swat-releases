import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from scripts.extract import ResponseValidator, GeminiExtractor

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


# ── GeminiExtractor ──────────────────────────────────────────────────────────

def mock_gemini_client(response: str = VALID_JSON_STR):
    client = MagicMock()
    client.generate.return_value = response
    return client


def test_extractor_returns_validated_dict():
    extractor = GeminiExtractor(mock_gemini_client(), ResponseValidator())
    result = extractor.extract(
        system_prompt="test prompt",
        version="26.7.1",
        release_url="https://github.com/...",
        release_body="test body",
    )
    assert result["version"] == "26.7.1"
    assert result["entries"][0]["tag"] == "Feature"


def test_extractor_overrides_release_url():
    """release_url in JSON is always replaced with the canonical URL."""
    wrong_url_artifact = {**VALID_ARTIFACT, "release_url": "https://github.com/wrong-url"}
    client = mock_gemini_client(response=json.dumps(wrong_url_artifact))
    extractor = GeminiExtractor(client, ResponseValidator())
    canonical = "https://github.com/PCS-LAB-ORG/catalyst-rag-agent/releases/tag/26.7.1"
    result = extractor.extract("p", "26.7.1", canonical, "body")
    assert result["release_url"] == canonical


def test_extractor_raises_on_invalid_gemini_response():
    client = mock_gemini_client(response="not json")
    extractor = GeminiExtractor(client, ResponseValidator())
    with pytest.raises(ValueError, match="Invalid JSON"):
        extractor.extract("p", "26.7.1", "url", "body")
