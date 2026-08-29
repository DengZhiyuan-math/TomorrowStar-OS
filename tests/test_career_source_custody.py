"""Synthetic end-to-end coverage for the private career-source custody tracer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from career_evidence_graph.validation.hashing import sha256_digest

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts/run_career_evidence.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_tracer_declares_captures_transforms_and_inspects_without_authority(tmp_path: Path) -> None:
    source = b'{"synthetic": "career source"}'
    workspace = str(tmp_path)

    declared = _run(
        "career-source",
        "declare",
        "--workspace",
        workspace,
        "--cutoff",
        "2026-08-01",
        "--category",
        "project",
        "--source-id",
        "source-probe",
        "--availability",
        "available",
    )
    assert declared.returncode == 0, declared.stderr
    assert json.loads(declared.stdout) == {"declared": True, "candidate_only": True}

    captured = _run(
        "career-source",
        "capture",
        "--workspace",
        workspace,
        "--source-id",
        "source-probe",
        "--paste",
        source.decode("utf-8"),
    )
    assert captured.returncode == 0, captured.stderr
    capture_status = json.loads(captured.stdout)
    assert capture_status == {"captured": True, "candidate_only": True}

    transformed = _run(
        "career-source",
        "transform",
        "--workspace",
        workspace,
        "--source-id",
        "source-probe",
        "--transformer",
        "deterministic-whole-source",
        "--version",
        "v1",
        "--configuration-json",
        "{}",
    )
    assert transformed.returncode == 0, transformed.stderr
    assert json.loads(transformed.stdout) == {"transformed": True, "candidate_only": True}

    inspected = _run("career-source", "inspect", "--workspace", workspace)
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout) == {
        "candidate_only": True,
        "capture_count": 1,
        "declaration_present": True,
        "transformation_count": 1,
    }
    assert source.decode("utf-8") not in inspected.stdout

    root = tmp_path / ".career-evidence" / "sources"
    declaration = json.loads((root / "declarations" / "current.json").read_text())
    assert declaration["schema_version"] == "career-source-universe/v1"
    capture = next((root / "captures").iterdir())
    manifest = json.loads((capture / "manifest.json").read_text())
    assert manifest["source_id"] == "source-probe"
    assert manifest["content_hash"] == sha256_digest(source)
    assert (tmp_path / ".career-evidence" / "raw" / manifest["capture_id"]).read_bytes() == source
    transformation = next((root / "transformations").iterdir())
    transformed_manifest = json.loads((transformation / "manifest.json").read_text())
    assert transformed_manifest["predecessor_capture_id"] == manifest["capture_id"]
    assert transformed_manifest["candidate_only"] is True
    assert not list(tmp_path.glob("**/*assessment*"))
