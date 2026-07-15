import json
import pytest
from unittest.mock import MagicMock, patch, call


def make_md_blob(name):
    b = MagicMock()
    b.name = name
    return b


def test_generator_processes_new_major_release():
    from scripts.generator.main import run_generator

    mock_storage = MagicMock()
    mock_input_bucket = MagicMock()
    mock_serve_bucket = MagicMock()

    mock_storage.bucket.side_effect = lambda name: (
        mock_input_bucket if "input" in name else mock_serve_bucket
    )
    mock_input_bucket.list_blobs.return_value = [
        make_md_blob("cortex-catalyst/26.7.1.md"),
    ]

    with patch("scripts.generator.main.process_release") as mock_process, \
         patch("scripts.generator.main.render_version") as mock_render, \
         patch("scripts.generator.main.rebuild_index") as mock_index, \
         patch("scripts.generator.main.storage.Client", return_value=mock_storage), \
         patch("scripts.generator.main.VertexGeminiClient"):

        mock_process.return_value = {"version": "26.7.1", "entries": [], "fixes": []}

        run_generator(
            input_bucket="swat-releases-input",
            serve_bucket="swat-releases-serve",
            config={"tools": [{"id": "cortex-catalyst", "folder": "cortex-catalyst",
                               "prompt": "scripts/prompts/model1_user_facing.txt",
                               "name": "Cortex® Catalyst", "description": "Test.",
                               "app_url": "https://example.com", "panel_id": "catalyst",
                               "model": "user-facing", "repo": "PCS-LAB-ORG/x"}]},
        )

    mock_process.assert_called_once_with(
        "cortex-catalyst", "26.7.1",
        "swat-releases-input", "swat-releases-serve",
        gemini_extractor=mock_process.call_args.kwargs["gemini_extractor"],
        gcs_md_source=mock_process.call_args.kwargs["gcs_md_source"],
        gcs_artifact_store=mock_process.call_args.kwargs["gcs_artifact_store"],
        config=mock_process.call_args.kwargs["config"],
    )
    mock_render.assert_called_once()
    mock_index.assert_called_once()


def test_generator_skips_non_md_blobs():
    from scripts.generator.main import run_generator

    mock_storage = MagicMock()
    mock_input_bucket = MagicMock()
    mock_input_bucket.list_blobs.return_value = [
        make_md_blob("cortex-catalyst/26.7.1.html"),  # not .md
        make_md_blob("cortex-catalyst/"),              # directory stub
    ]
    mock_storage.bucket.return_value = mock_input_bucket

    with patch("scripts.generator.main.process_release") as mock_process, \
         patch("scripts.generator.main.render_version"), \
         patch("scripts.generator.main.rebuild_index"), \
         patch("scripts.generator.main.storage.Client", return_value=mock_storage), \
         patch("scripts.generator.main.VertexGeminiClient"):
        run_generator(
            input_bucket="swat-releases-input",
            serve_bucket="swat-releases-serve",
            config={"tools": [{"id": "cortex-catalyst", "folder": "cortex-catalyst",
                               "prompt": "scripts/prompts/model1_user_facing.txt",
                               "name": "Cortex® Catalyst", "description": "Test.",
                               "app_url": "https://example.com", "panel_id": "catalyst",
                               "model": "user-facing", "repo": "PCS-LAB-ORG/x"}]},
        )
    mock_process.assert_not_called()


def test_rebuild_index_called_only_for_catalyst():
    """rebuild_index must not run for non-catalyst tools — doing so overwrites the
    catalyst panel with wrong data, corrupting index.html."""
    from scripts.generator.main import run_generator

    mock_storage = MagicMock()
    mock_input_bucket = MagicMock()
    mock_input_bucket.list_blobs.return_value = []
    mock_storage.bucket.return_value = mock_input_bucket

    multi_tool_config = {
        "tools": [
            {"id": "cortex-catalyst", "folder": "cortex-catalyst",
             "prompt": "scripts/prompts/model1_user_facing.txt",
             "name": "Cortex® Catalyst", "description": "Test.",
             "app_url": "https://example.com", "panel_id": "catalyst",
             "model": "user-facing", "repo": "PCS-LAB-ORG/x"},
            {"id": "cortex-insights", "folder": "cortex-insights",
             "prompt": "scripts/prompts/model1_user_facing.txt",
             "name": "Cortex Insights", "description": "Test.",
             "model": "user-facing"},
            {"id": "ai-sweeper", "folder": "ai-sweeper",
             "prompt": "scripts/prompts/model1_user_facing.txt",
             "name": "AI Sweeper", "description": "Test.",
             "model": "user-facing"},
        ]
    }

    with patch("scripts.generator.main.rebuild_index") as mock_index, \
         patch("scripts.generator.main.storage.Client", return_value=mock_storage), \
         patch("scripts.generator.main.VertexGeminiClient"):
        run_generator("swat-releases-input", "swat-releases-serve", multi_tool_config)

    mock_index.assert_called_once()
    called_tool = mock_index.call_args[0][0]
    assert called_tool["id"] == "cortex-catalyst"


def test_generator_logs_and_continues_on_error():
    from scripts.generator.main import run_generator
    import logging

    mock_storage = MagicMock()
    mock_input_bucket = MagicMock()
    mock_input_bucket.list_blobs.return_value = [
        make_md_blob("cortex-catalyst/26.7.1.md"),
    ]
    mock_storage.bucket.return_value = mock_input_bucket

    with patch("scripts.generator.main.process_release", side_effect=RuntimeError("Gemini failed")), \
         patch("scripts.generator.main.render_version"), \
         patch("scripts.generator.main.rebuild_index"), \
         patch("scripts.generator.main.storage.Client", return_value=mock_storage), \
         patch("scripts.generator.main.VertexGeminiClient"):
        # Should not raise — errors are logged and skipped
        run_generator(
            input_bucket="swat-releases-input",
            serve_bucket="swat-releases-serve",
            config={"tools": [{"id": "cortex-catalyst", "folder": "cortex-catalyst",
                               "prompt": "scripts/prompts/model1_user_facing.txt",
                               "name": "Cortex® Catalyst", "description": "Test.",
                               "app_url": "https://example.com", "panel_id": "catalyst",
                               "model": "user-facing", "repo": "PCS-LAB-ORG/x"}]},
        )
