import json
from pathlib import Path
from scripts.pr_body import generate_pr_body

SAMPLE = json.loads(Path("tests/fixtures/sample_artifact.json").read_text())


def test_pr_body_contains_version(tmp_path):
    d = tmp_path / "cortex-catalyst"
    d.mkdir()
    (d / "26.7.1.json").write_text(json.dumps(SAMPLE))
    body = generate_pr_body(str(d), "26.7.1")
    assert "26.7.1" in body


def test_pr_body_contains_summary(tmp_path):
    d = tmp_path / "cortex-catalyst"
    d.mkdir()
    (d / "26.7.1.json").write_text(json.dumps(SAMPLE))
    body = generate_pr_body(str(d), "26.7.1")
    assert SAMPLE["summary"] in body


def test_pr_body_contains_entry_count(tmp_path):
    d = tmp_path / "cortex-catalyst"
    d.mkdir()
    (d / "26.7.1.json").write_text(json.dumps(SAMPLE))
    body = generate_pr_body(str(d), "26.7.1")
    assert "2" in body  # 2 entries in sample artifact


def test_pr_body_contains_correction_note(tmp_path):
    d = tmp_path / "cortex-catalyst"
    d.mkdir()
    (d / "26.7.1.json").write_text(json.dumps(SAMPLE))
    body = generate_pr_body(str(d), "26.7.1")
    assert "26.7.1.json" in body  # correction procedure reference
