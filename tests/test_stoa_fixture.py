"""Offline regression coverage for the unsealed STOA fixture packet."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.domain.fixtures import (
    SourceScopeError,
    evaluate_review_status,
    load_candidate_packet,
    verify_source_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "validation/fixtures/stoa/v1/source-manifest.json"
CANDIDATES = ROOT / "validation/fixtures/stoa/v1/candidates.json"
REVIEW = ROOT / "validation/fixtures/stoa/v1/review.json"


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


def test_candidate_packet_is_one_stoa_experience_grouped_by_durable_outcome() -> None:
    candidates, review = load_candidate_packet(CANDIDATES, REVIEW)

    assert candidates.experience_id == "exp-stoa"
    assert len(candidates.contributions) >= 3
    assert all(
        "repository" not in contribution.outcome_group_id
        for contribution in candidates.contributions
    )
    assert all(
        "commit" not in contribution.outcome_group_id for contribution in candidates.contributions
    )
    assert all(
        "phase" not in contribution.outcome_group_id for contribution in candidates.contributions
    )
    assert len(review.items) == len(candidates.claims)


def test_candidate_packet_covers_each_source_and_preserves_non_personal_limits() -> None:
    candidates, _ = load_candidate_packet(CANDIDATES, REVIEW)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert len(candidates.source_section_dispositions) == len(manifest["documents"])
    assert {item.disposition for item in candidates.source_section_dispositions} <= {
        "used",
        "background-only",
        "conflict",
        "excluded-with-reason",
    }
    assert all(
        claim.documentary_status == "document-derived-non-personal" for claim in candidates.claims
    )
    assert all(claim.responsibility == "unconfirmed" for claim in candidates.claims)
    assert all(claim.assistance == "unconfirmed" for claim in candidates.claims)
    assert all(item.background_only for item in candidates.background_context)
    assert {item.source_entry_id for item in candidates.source_section_dispositions} == {
        item["id"] for item in manifest["documents"]
    }


def test_review_status_has_six_pending_decision_groups_and_cannot_seal() -> None:
    candidates, review = load_candidate_packet(CANDIDATES, REVIEW)
    status = evaluate_review_status(candidates, review)

    assert status.sealable is False
    assert set(status.pending_ids_by_group) == {
        "fact",
        "attribution_assistance",
        "evidence_links",
        "completion",
        "limitations_conflicts",
        "fixture_score_range",
    }
    assert all(status.pending_ids_by_group.values())
    assert not (ROOT / "validation/fixtures/stoa/v1/known-good.json").exists()


def test_candidate_packet_rejects_documentary_personal_claim_and_planned_lineage(
    tmp_path: Path,
) -> None:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    candidates["claims"][0]["documentary_status"] = "personal-confirmed"
    altered_candidates = tmp_path / "candidates.json"
    altered_candidates.write_text(json.dumps(candidates), encoding="utf-8")

    with pytest.raises(SourceScopeError, match="source-scope"):
        load_candidate_packet(altered_candidates, REVIEW)
