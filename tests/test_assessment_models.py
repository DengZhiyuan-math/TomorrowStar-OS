"""Strict persisted-record contracts for the Phase 4 assessment sidecar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_evidence_graph.assessment import AssessmentStorageError, AssessmentStore, run_assessment
from career_evidence_graph.domain.models import ContributionSkillAssessment

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus.json"
POLICIES = ROOT / "validation/calibration/phase-04/policies.json"


def test_assessment_store_reopens_canonical_record_with_stable_bytes(tmp_path: Path) -> None:
    """Valid local records preserve their exact canonical representation."""
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    run_id = "assessment-audit-e2e-04-baseline-60"
    store = AssessmentStore(tmp_path)

    before = store.path(run_id).read_bytes()
    assert store.read(run_id) == record
    assert store.path(run_id).read_bytes() == before


def test_assessment_store_rejects_corrupt_extra_unsafe_and_directly_linked_records(
    tmp_path: Path,
) -> None:
    """Untrusted storage must fail before corrupt sidecars become current."""
    run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    run_id = "assessment-audit-e2e-04-baseline-60"
    store = AssessmentStore(tmp_path)

    with pytest.raises(AssessmentStorageError, match="unsafe"):
        store.read("../../assessment-escape")

    path = store.path(run_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AssessmentStorageError, match="corrupt"):
        store.read(run_id)

    linked_id = "assessment-linked"
    linked_path = store.path_for(linked_id)
    linked_path.symlink_to(path)
    with pytest.raises(AssessmentStorageError, match="linked"):
        store.read(linked_id)


def test_effective_assessment_keeps_three_independent_judgment_bases(tmp_path: Path) -> None:
    record = run_assessment(
        workspace=tmp_path,
        corpus_path=CORPUS,
        policies_path=POLICIES,
        audit_id="audit-e2e",
        policy_version="policy-04-baseline-60",
    )
    basis = record.proposal.judgment_basis

    assert basis is not None
    assert basis.demonstrated_mastery_basis != basis.skill_centrality_basis
    assert basis.skill_centrality_basis != basis.evidence_confidence_basis

    payload = record.proposal.model_dump(mode="json")
    payload["judgment_basis"] = None
    with pytest.raises(ValueError, match="effective assessments require"):
        ContributionSkillAssessment.model_validate(payload)
