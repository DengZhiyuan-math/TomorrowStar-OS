"""The synthetic JSON resume command never overwrites an existing workspace."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/create_json_resume_demo.py"


def test_existing_destination_is_preserved(tmp_path):
    destination = tmp_path / "human-work"
    destination.mkdir()
    original = b"% Existing human edits must remain unchanged.\n"
    (destination / "main.tex").write_bytes(original)
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "already exists" in result.stderr
    assert (destination / "main.tex").read_bytes() == original
    assert sorted(p.name for p in destination.iterdir()) == ["main.tex"]


def test_new_destination_contains_json_and_complete_tex_without_compiling(tmp_path):
    destination = tmp_path / "synthetic-json-resume"
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    content = json.loads((destination / "resume.json").read_text())
    source = (destination / "main.tex").read_text()
    manifest = json.loads((destination / "render.json").read_text())
    assert content["schema_version"] == "resume-content/v1"
    assert len(content["experiences"]) == 1
    assert source.count(r"\subsection*{") == 1
    assert r"\begin{document}" in source
    assert source.rstrip().endswith(r"\end{document}")
    assert manifest["synthetic"] is True
    assert manifest["operation"] == "render_only"
    assert not list(destination.rglob("*.pdf"))


def test_manifest_binds_fixed_input_and_generated_source(tmp_path):
    destination = tmp_path / "synthetic-input-binding"
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((destination / "render.json").read_text())
    assert (
        manifest["input_sha256"]
        == hashlib.sha256((destination / "input.json").read_bytes()).hexdigest()
    )
    assert (
        manifest["tex_sha256"]
        == hashlib.sha256((destination / "main.tex").read_bytes()).hexdigest()
    )
