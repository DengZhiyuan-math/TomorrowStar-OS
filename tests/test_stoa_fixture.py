"""Offline regression coverage for the unsealed STOA fixture packet."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.domain.fixtures import (
    CandidateReviewRecord,
    SourceScopeError,
    evaluate_review_status,
    load_candidate_packet,
    load_sealed_fixture,
    materialize_review_decisions,
    seal_reviewed_fixture,
    verify_source_manifest,
)
from career_evidence_graph.validation.replay import replay_recorded_response
from career_evidence_graph.validation.store import FormalRunStorageError, FormalRunStore

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "validation/fixtures/stoa/v1/source-manifest.json"
CANDIDATES = ROOT / "validation/fixtures/stoa/v1/candidates.json"
REVIEW = ROOT / "validation/fixtures/stoa/v1/review.json"
LAUNCHER = ROOT / "scripts" / "run_career_evidence.py"
CHECKPOINT_SUMMARY = (
    ROOT
    / ".planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants"
    / "02-04-SUMMARY.md"
)


def _sealed_workspace(tmp_path: Path) -> Path:
    """Create the canonical on-disk input layout required by sealed loading."""
    workspace = tmp_path / "validation/fixtures/stoa/v1"
    workspace.mkdir(parents=True)
    shutil.copyfile(MANIFEST, workspace / "source-manifest.json")
    shutil.copyfile(REVIEW, workspace / "review.json")
    charter = tmp_path / "validation/charter"
    charter.mkdir(parents=True)
    shutil.copyfile(ROOT / "validation/charter/v1.json", charter / "v1.json")
    checkpoint = (
        tmp_path / ".planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants"
    )
    checkpoint.mkdir(parents=True)
    shutil.copyfile(CHECKPOINT_SUMMARY, checkpoint / "02-04-SUMMARY.md")
    return workspace


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
            str(LAUNCHER),
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


def test_recorded_review_has_six_resolved_groups_and_can_seal() -> None:
    candidates, review = load_candidate_packet(CANDIDATES, REVIEW)
    status = evaluate_review_status(candidates, review)

    assert status.sealable is True
    assert set(status.pending_ids_by_group) == {
        "fact",
        "attribution_assistance",
        "evidence_links",
        "completion",
        "limitations_conflicts",
        "fixture_score_range",
    }
    assert not any(status.pending_ids_by_group.values())
    assert (ROOT / "validation/fixtures/stoa/v1/known-good.json").exists()


def test_candidate_packet_rejects_documentary_personal_claim_and_planned_lineage(
    tmp_path: Path,
) -> None:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    candidates["claims"][0]["documentary_status"] = "personal-confirmed"
    altered_candidates = tmp_path / "candidates.json"
    altered_candidates.write_text(json.dumps(candidates), encoding="utf-8")

    with pytest.raises(SourceScopeError, match="source-scope"):
        load_candidate_packet(altered_candidates, REVIEW)


def test_review_materialization_preserves_human_corrections_and_unresolved_values() -> None:
    """The confirmed checkpoint response is complete without fabricating mastery."""
    candidates, pending_review = load_candidate_packet(CANDIDATES, REVIEW)
    summary_path = (
        ROOT
        / ".planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants"
        / "02-04-SUMMARY.md"
    )

    review, fixture = materialize_review_decisions(
        candidates, pending_review, summary_path.read_bytes()
    )

    assert review.reviewer_id == "zhdeng"
    assert review.checkpoint_summary_hash.startswith("sha256:")
    assert review.candidate_ledger_hash == pending_review.candidate_ledger_hash
    assert evaluate_review_status(candidates, review).sealable is True
    assert all(item.fixture_score_range.status == "unresolved" for item in review.items)
    assert all(
        claim.responsibility == "user" and claim.assistance == "codex_assisted"
        for claim in fixture.claims
    )
    assert all(
        view.expectation_status == "fixture-test-expectation" for view in fixture.user_skill_views
    )
    confirmed_result = json.loads(
        (
            ROOT
            / "validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/confirmed_result.json"
        ).read_text(encoding="utf-8")
    )
    assert fixture.model_dump(mode="json") == confirmed_result


def test_rejected_fact_is_omitted_but_unresolved_fact_cannot_be_sealed() -> None:
    candidates, review = load_candidate_packet(CANDIDATES, REVIEW)
    payload = review.model_dump(mode="json")
    payload["items"][0]["fact"]["status"] = "rejected"
    rejected = CandidateReviewRecord.model_validate(payload)
    _, fixture = materialize_review_decisions(
        candidates,
        rejected,
        (
            ROOT
            / ".planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants"
            / "02-04-SUMMARY.md"
        ).read_bytes(),
    )
    assert rejected.items[0].candidate_id not in {claim.id for claim in fixture.claims}

    payload["items"][0]["fact"]["status"] = "unresolved"
    unresolved = CandidateReviewRecord.model_validate(payload)
    assert evaluate_review_status(candidates, unresolved).sealable is False


def test_materialization_rejects_tampered_correction_authority() -> None:
    candidates, review = load_candidate_packet(CANDIDATES, REVIEW)
    payload = review.model_dump(mode="json")
    payload["corrections"][0]["reviewer_id"] = "someone-else"
    tampered = CandidateReviewRecord.model_validate(payload)

    assert evaluate_review_status(candidates, tampered).sealable is False

    payload = review.model_dump(mode="json")
    payload["candidate_ledger_hash"] = "sha256:" + "0" * 64
    wrong_ledger = CandidateReviewRecord.model_validate(payload)

    assert evaluate_review_status(candidates, wrong_ledger).sealable is False


def test_seal_publishes_verified_bundle_and_provider_free_replay(tmp_path: Path) -> None:
    """Known-good can only be recovered from verified immutable formal evidence."""
    workspace = _sealed_workspace(tmp_path)
    candidates, review = load_candidate_packet(CANDIDATES, REVIEW)
    output = workspace / "known-good.json"

    sealed = seal_reviewed_fixture(
        workspace=workspace,
        run_id="stoa-known-good",
        manifest_path=workspace / "source-manifest.json",
        candidates=candidates,
        review=review,
        checkpoint_summary_bytes=CHECKPOINT_SUMMARY.read_bytes(),
        output_path=output,
    )

    assert FormalRunStore(workspace).verify("stoa-known-good").run_id == "stoa-known-good"
    assert replay_recorded_response(FormalRunStore(workspace), "stoa-known-good").matched
    assert load_sealed_fixture(output, workspace).fixture_hash == sealed.fixture_hash
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["confirmed_result_hash"] == sealed.fixture_hash


def test_seal_recovers_only_identical_missing_output_and_rejects_overwrite(tmp_path: Path) -> None:
    workspace = _sealed_workspace(tmp_path)
    candidates, review = load_candidate_packet(CANDIDATES, REVIEW)
    summary = CHECKPOINT_SUMMARY.read_bytes()
    output = workspace / "known-good.json"
    kwargs = {
        "workspace": workspace,
        "run_id": "stoa-known-good",
        "manifest_path": workspace / "source-manifest.json",
        "candidates": candidates,
        "review": review,
        "checkpoint_summary_bytes": summary,
        "output_path": output,
    }

    sealed = seal_reviewed_fixture(**kwargs)
    output.unlink()
    assert seal_reviewed_fixture(**kwargs).fixture_hash == sealed.fixture_hash
    output.write_text('{"unexpected":true}\n', encoding="utf-8")

    with pytest.raises(Exception, match="divergent bytes"):
        seal_reviewed_fixture(**kwargs)

    assert not list(workspace.glob(".known-good.json.*"))


@pytest.mark.parametrize(
    "field",
    ("source_manifest_hash", "review_hash", "checkpoint_summary_hash"),
)
def test_load_sealed_fixture_rejects_each_tampered_envelope_hash(
    tmp_path: Path, field: str
) -> None:
    workspace = _sealed_workspace(tmp_path)
    candidates, review = load_candidate_packet(CANDIDATES, REVIEW)
    output = workspace / "known-good.json"
    seal_reviewed_fixture(
        workspace=workspace,
        run_id="stoa-known-good",
        manifest_path=workspace / "source-manifest.json",
        candidates=candidates,
        review=review,
        checkpoint_summary_bytes=CHECKPOINT_SUMMARY.read_bytes(),
        output_path=output,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload[field] = "sha256:" + "0" * 64
    output.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FormalRunStorageError, match=field):
        load_sealed_fixture(output, workspace)


def test_reissue_preserves_fixture_evidence_and_creates_new_formal_lineage(tmp_path: Path) -> None:
    workspace = _sealed_workspace(tmp_path)
    candidates, review = load_candidate_packet(CANDIDATES, REVIEW)
    output = workspace / "known-good.json"
    kwargs = {
        "workspace": workspace,
        "manifest_path": workspace / "source-manifest.json",
        "candidates": candidates,
        "review": review,
        "checkpoint_summary_bytes": CHECKPOINT_SUMMARY.read_bytes(),
        "output_path": output,
    }
    first = seal_reviewed_fixture(run_id="stoa-known-good", **kwargs)
    reissued = seal_reviewed_fixture(run_id="stoa-known-good-v2", reissue=True, **kwargs)

    sealed = json.loads(output.read_text(encoding="utf-8"))
    assert first.fixture_hash == reissued.fixture_hash
    assert sealed["formal_run_id"] == "stoa-known-good-v2"
    assert FormalRunStore(workspace).verify("stoa-known-good").run_id == "stoa-known-good"
    assert load_sealed_fixture(output, workspace).fixture_hash == reissued.fixture_hash
