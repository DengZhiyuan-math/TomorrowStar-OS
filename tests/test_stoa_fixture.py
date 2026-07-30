"""Offline regression coverage for the unsealed STOA fixture packet."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.domain.fixtures import SourceScopeError, verify_source_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "validation/fixtures/stoa/v1/source-manifest.json"


def test_source_manifest_verifies_exact_pinned_document_inventory() -> None:
    result = verify_source_manifest(MANIFEST)

    assert result.valid is True
    assert result.repository_count == 4
    assert result.document_count == 10


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("pinned_commit", "0" * 40),
        ("tracked_path", "src/private.py"),
        ("tracked_path", "../private.txt"),
        ("tracked_path", "/private/tmp/private.txt"),
    ],
)
def test_source_manifest_rejects_scope_escape(tmp_path: Path, field: str, replacement: str) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["documents"][0][field] = replacement
    altered = tmp_path / "altered-manifest.json"
    altered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceScopeError, match="source-scope"):
        verify_source_manifest(altered)


def test_source_manifest_documents_are_non_personal_and_have_proof_limits() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert {item["repository_id"] for item in payload["documents"]} == {
        "stoa-backend",
        "stoa-frontend",
        "stoa-infra",
        "stoa-docs",
    }
    assert all(
        item["proof_limit"] != "personal_responsibility_and_claimed_capability"
        for item in payload["documents"]
    )
    assert all(item["personal_claim_proof"] == "none" for item in payload["documents"])
    assert all(
        item["section_locator_policy"] == "markdown-heading-or-document"
        for item in payload["documents"]
    )


def test_fixture_source_verify_cli_is_offline_and_reports_counts() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "career_evidence_graph.cli",
            "fixture",
            "source",
            "verify",
            "--manifest",
            str(MANIFEST),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["valid"] is True
    assert result["repository_count"] == 4
    assert result["document_count"] == 10
    assert result["manifest_hash"].startswith("sha256:")
