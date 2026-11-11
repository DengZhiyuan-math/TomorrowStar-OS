"""Synthetic fixture succession retains historical bytes without inheriting their reviews."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_evidence_graph.assessment import (
    AssessmentWorkflowError,
    _materialize_audit,
    propose_assessment,
    propose_assessments,
)
from career_evidence_graph.audit import workflow
from career_evidence_graph.audit.decision import RecordedDecisionPort
from career_evidence_graph.audit.models import (
    AuditAction,
    BoundaryDecision,
    ProbePlan,
    conclusion_lineage_digest,
    effective_conclusion_digest,
)
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.domain.models import Skill, SkillAlias
from career_evidence_graph.validation.hashing import canonical_json_bytes, sha256_digest

ROOT = Path(__file__).parents[1]
CALIBRATION = ROOT / "validation/calibration/phase-04"
HISTORICAL = CALIBRATION / "corpus.json"
SUCCESSOR = CALIBRATION / "corpus-review-safe-v1.json"


def test_successor_keeps_source_scores_and_historical_artifacts_unchanged():
    historical = json.loads(HISTORICAL.read_bytes())
    successor = json.loads(SUCCESSOR.read_bytes())
    assert sha256_digest(HISTORICAL.read_bytes()) == (
        "sha256:5bbb737862799fad4574ba25151a2f76947191abc1f76f1bfc749427cb016121"
    )
    assert sha256_digest((CALIBRATION / "policy-calibration/history.json").read_bytes()) == (
        "sha256:812483e660b1b7989ac95342ef36d6a82395efbd8c7eda21c392e5dd32c96403"
    )
    assert {key for key in successor if successor[key] != historical[key]} == {
        "audit_journey",
        "audit_snapshot_hash",
        "conclusion_lineage_hash",
    }
    assert successor["candidate"]["authority_label"] == "derived-counterfactual"
    assert not any(
        action.get("decision") == "edit" for action in successor["audit_journey"]["actions"]
    )


def test_historical_edit_then_confirm_corpus_is_rejected(tmp_path):
    corpus = json.loads(HISTORICAL.read_bytes())
    with pytest.raises(AssessmentWorkflowError, match="prose-corrected audit"):
        _materialize_audit(
            workspace=tmp_path, corpus=corpus, root=ROOT, audit_id=corpus["audit_id"]
        )


def test_legacy_erased_correction_history_cannot_authorize_any_assessment(tmp_path, monkeypatch):
    corpus = json.loads(HISTORICAL.read_bytes())
    journey = corpus["audit_journey"]
    plan = ProbePlan.model_validate(journey["probe_plan"])
    decisions = tuple(BoundaryDecision.model_validate(item) for item in journey["decisions"])
    port = RecordedDecisionPort(
        plan=plan, decisions={(item.question_id, item.answer): item for item in decisions}
    )
    current_review = workflow._append_review

    def legacy_erasing_review(snapshot, **kwargs):
        """Reconstruct old bytes only inside this synthetic regression."""
        updated = current_review(snapshot, **kwargs)
        if kwargs["target"] != "entry" or kwargs["outcome"] == "edit":
            return updated
        entries = tuple(
            entry.model_copy(update={"correction": None})
            if entry.id == kwargs["entry_id"]
            else entry
            for entry in updated.conclusion.entries
        )
        effective_hash = effective_conclusion_digest(entries, updated.conclusion.whole_review)
        conclusion = updated.conclusion.model_copy(
            update={"entries": entries, "effective_conclusion_hash": effective_hash}
        )
        reviews = (
            *updated.conclusion_reviews[:-1],
            updated.conclusion_reviews[-1].model_copy(
                update={"after_effective_hash": effective_hash}
            ),
        )
        return updated.model_copy(
            update={
                "conclusion": conclusion,
                "conclusion_reviews": reviews,
                "conclusion_lineage_hash": conclusion_lineage_digest(conclusion, reviews),
            }
        )

    snapshot = workflow.start_audit(
        workspace=tmp_path,
        fixture_path=ROOT / corpus["fixture_path"],
        manifest_path=ROOT / corpus["source_manifest_path"],
        contribution_id=corpus["contribution_id"],
        audit_id=corpus["audit_id"],
        decision_port=port,
    )
    with monkeypatch.context() as legacy:
        legacy.setattr(workflow, "_append_review", legacy_erasing_review)
        for value in journey["actions"]:
            snapshot = workflow.transition_audit(
                snapshot, AuditAction.model_validate(value), decision_port=port
            )
    assert sha256_digest(canonical_json_bytes(snapshot) + b"\n") == corpus["audit_snapshot_hash"]
    assert snapshot.conclusion_lineage_hash == corpus["conclusion_lineage_hash"]
    assert snapshot.conclusion.entries[0].correction is None
    AuditStore(tmp_path).replace(snapshot)
    snapshot = AuditStore(tmp_path).read(snapshot.audit_id)

    assert (
        propose_assessments(
            snapshot=snapshot,
            fixture_hash=corpus["fixture_hash"],
            source_manifest_hash=corpus["source_manifest_hash"],
            skills=(Skill(id="skill.testing", name="Testing"),),
            aliases=(
                SkillAlias(
                    alias="Testing",
                    skill_id="skill.testing",
                    ontology_source_id="synthetic",
                    pinned_revision="a" * 40,
                ),
            ),
            candidates_by_entry={"entry-implementation": ("Testing",)},
        )
        == ()
    )
    with pytest.raises(AssessmentWorkflowError, match="prose-corrected audit"):
        propose_assessment(snapshot=snapshot, corpus=corpus, root=ROOT)
    with pytest.raises(AssessmentWorkflowError, match="prose-corrected audit"):
        _materialize_audit(
            workspace=tmp_path,
            corpus=corpus,
            root=ROOT,
            audit_id=corpus["audit_id"],
            allow_replay=False,
        )
