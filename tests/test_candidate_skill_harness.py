"""Synthetic acceptance contracts for Candidate Skill Link audit context."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from career_evidence_graph.assessment import (
    _materialize_audit,
    _repository_root,
    propose_assessments,
)
from career_evidence_graph.audit.decision import RecordedDecisionPort
from career_evidence_graph.audit.models import (
    AuditAction,
    AuditSnapshot,
    BoundaryDecision,
    CandidateSkillLink,
    ProbeArea,
    ProbePlan,
)
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.audit.workflow import start_audit, transition_audit
from career_evidence_graph.domain.models import Skill, SkillAlias
from career_evidence_graph.validation.hashing import sha256_digest

FIXTURE = Path("validation/fixtures/stoa/v1/known-good.json")
MANIFEST = FIXTURE.parent / "source-manifest.json"
CORPUS_PATH = Path("validation/calibration/phase-04/corpus-review-safe-v1.json")


def _plan() -> ProbePlan:
    return ProbePlan(
        contribution_id="contrib-stoa-authorization-boundary",
        areas=(
            ProbeArea(
                area_id="implementation",
                inspected_fact_ids=("evid-stoa-build-week",),
                unverified_capability="implementation choices at the authorization boundary",
                demanding_prompt="Which authorization trade-off did you personally make?",
                intermediate_prompt="Which authorization change did you make and verify?",
                simple_prompt="Which authorization step did you personally complete?",
                immediately_higher_capability="defending the boundary under failure",
                candidate_skill_link_ids=("candidate-skill-stoa-authorization",),
            ),
        ),
    )


def _candidate_link() -> CandidateSkillLink:
    return CandidateSkillLink(
        id="candidate-skill-stoa-authorization",
        experience_candidate_id="experience-candidate-stoa",
        source_id="source-synthetic-stoa",
        capture_hash=sha256_digest(b"synthetic-candidate-source"),
        source_locator="README.md#authorization",
        candidate_text="Authorization boundary verification",
        extraction_version="synthetic-extractor/v1",
    )


def test_selected_candidate_link_is_a_nonconclusive_recall_reminder(tmp_path: Path) -> None:
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        experience_candidate_id="experience-candidate-stoa",
        candidate_skill_links=(_candidate_link(),),
        audit_id="audit-candidate-skill-reminder",
        decision_port=RecordedDecisionPort(plan=_plan(), decisions={}),
    )

    question = snapshot.questions[0]
    assert question.recall_reminder == (
        "Candidate skill reminder (unverified): Authorization boundary verification"
    )
    assert question.candidate_skill_link_ids == ("candidate-skill-stoa-authorization",)
    assert "Candidate skill" not in question.prompt
    assert snapshot.candidate_skill_links == (_candidate_link(),)


def test_complete_audit_remains_score_eligible_without_candidate_skill_links(
    tmp_path: Path,
) -> None:
    corpus = __import__("json").loads(CORPUS_PATH.read_text(encoding="utf-8"))
    snapshot = _materialize_audit(
        workspace=tmp_path,
        corpus=corpus,
        root=_repository_root(CORPUS_PATH),
        audit_id="audit-e2e",
    )
    proposals = propose_assessments(
        snapshot=snapshot,
        fixture_hash=corpus["fixture_hash"],
        source_manifest_hash=corpus["source_manifest_hash"],
        skills=(Skill(id="skill.testing", name="Testing"),),
        candidates_by_entry={"entry-implementation": ("Testing",)},
        aliases=(
            SkillAlias(
                alias="testing",
                skill_id="skill.testing",
                ontology_source_id="mind-tech-ontology",
                pinned_revision="a" * 40,
            ),
        ),
    )

    assert len(proposals) == 1
    assert proposals[0].candidate_skill_link_ids == ()


def test_confirmed_audit_retains_selected_candidate_link_as_optional_provenance(
    tmp_path: Path,
) -> None:
    corpus = __import__("json").loads(CORPUS_PATH.read_text(encoding="utf-8"))
    journey = deepcopy(corpus["audit_journey"])
    journey["probe_plan"]["areas"][0]["candidate_skill_link_ids"] = [
        "candidate-skill-stoa-authorization"
    ]
    plan = ProbePlan.model_validate(journey["probe_plan"])
    decisions = tuple(BoundaryDecision.model_validate(item) for item in journey["decisions"])
    port = RecordedDecisionPort(
        plan=plan,
        decisions={(decision.question_id, decision.answer): decision for decision in decisions},
    )
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=Path(corpus["fixture_path"]),
        manifest_path=Path(corpus["source_manifest_path"]),
        contribution_id=corpus["contribution_id"],
        experience_candidate_id="experience-candidate-stoa",
        candidate_skill_links=(_candidate_link(),),
        audit_id="audit-candidate-provenance",
        decision_port=port,
    )
    for action_value in journey["actions"]:
        snapshot = transition_audit(
            snapshot, AuditAction.model_validate(action_value), decision_port=port
        )
        AuditStore(tmp_path).replace(snapshot)

    proposals = propose_assessments(
        snapshot=snapshot,
        fixture_hash=corpus["fixture_hash"],
        source_manifest_hash=corpus["source_manifest_hash"],
        skills=(
            Skill(id="skill.authorization", name="Authorization boundary verification"),
            Skill(id="skill.testing", name="Testing"),
        ),
        candidates_by_entry={
            "entry-implementation": ("Authorization boundary verification", "Testing")
        },
        aliases=(
            SkillAlias(
                alias="authorization boundary verification",
                skill_id="skill.authorization",
                ontology_source_id="mind-tech-ontology",
                pinned_revision="a" * 40,
            ),
            SkillAlias(
                alias="testing",
                skill_id="skill.testing",
                ontology_source_id="mind-tech-ontology",
                pinned_revision="a" * 40,
            ),
        ),
    )

    assert [(proposal.skill_id, proposal.candidate_skill_link_ids) for proposal in proposals] == [
        ("skill.authorization", ("candidate-skill-stoa-authorization",)),
        ("skill.testing", ()),
    ]


def test_candidate_skill_link_cannot_cross_the_selected_experience_candidate(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="must match the selected Experience Candidate"):
        start_audit(
            workspace=tmp_path,
            fixture_path=FIXTURE,
            manifest_path=MANIFEST,
            contribution_id="contrib-stoa-authorization-boundary",
            experience_candidate_id="experience-candidate-unrelated",
            candidate_skill_links=(_candidate_link(),),
            audit_id="audit-candidate-skill-cross-experience",
            decision_port=RecordedDecisionPort(plan=_plan(), decisions={}),
        )


def test_snapshot_rejects_a_probe_reference_to_a_missing_candidate_skill_link(
    tmp_path: Path,
) -> None:
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        experience_candidate_id="experience-candidate-stoa",
        candidate_skill_links=(_candidate_link(),),
        audit_id="audit-candidate-skill-forged-link",
        decision_port=RecordedDecisionPort(plan=_plan(), decisions={}),
    )
    payload = snapshot.model_dump(mode="json")
    payload["probe_plan"]["areas"][0]["candidate_skill_link_ids"] = ["candidate-skill-forged"]

    with pytest.raises(ValueError, match="references a missing Candidate Skill Link"):
        AuditSnapshot.model_validate(payload)
