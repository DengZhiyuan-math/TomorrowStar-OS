"""Contribution-to-specific-Skill proposal contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.assessment import (
    _materialize_audit,
    _repository_root,
    propose_assessments,
    resolve_skill_candidate,
)
from career_evidence_graph.audit.decision import RecordedDecisionPort
from career_evidence_graph.audit.models import (
    AuditAction,
    BoundaryDecision,
    CandidateSkillLink,
    ProbePlan,
)
from career_evidence_graph.audit.workflow import start_audit, transition_audit
from career_evidence_graph.domain.models import OntologyRelation, Skill, SkillAlias

ROOT = Path(__file__).parents[1]
CORPUS_PATH = ROOT / "validation/calibration/phase-04/corpus-review-safe-v1.json"


def _alias(alias: str, skill_id: str) -> SkillAlias:
    return SkillAlias(
        alias=alias,
        skill_id=skill_id,
        ontology_source_id="mind-tech-ontology",
        pinned_revision="a" * 40,
    )


def test_resolve_skill_candidate_only_auto_resolves_one_unambiguous_alias() -> None:
    skills = (
        Skill(id="skill.python", name="Python"),
        Skill(id="skill.sql", name="SQL"),
    )

    matched = resolve_skill_candidate(
        " PYTHON ", skills=skills, aliases=(_alias("Python", "skill.python"),)
    )
    ambiguous = resolve_skill_candidate(
        "data", skills=skills, aliases=(_alias("data", "skill.python"), _alias("DATA", "skill.sql"))
    )
    unmatched = resolve_skill_candidate("backend development", skills=skills)

    assert matched.review_status == "matched"
    assert matched.candidate_skill_ids == ("skill.python",)
    assert ambiguous.review_status == "review-required"
    assert ambiguous.candidate_skill_ids == ("skill.python", "skill.sql")
    assert unmatched.review_status == "unmatched"
    assert unmatched.candidate_skill_ids == ()


def test_propose_assessments_emits_all_and_only_matched_specific_skills_with_custody(
    tmp_path: Path,
) -> None:
    corpus = __import__("json").loads(CORPUS_PATH.read_text(encoding="utf-8"))
    snapshot = _materialize_audit(
        workspace=tmp_path,
        corpus=corpus,
        root=_repository_root(CORPUS_PATH),
        audit_id="audit-e2e",
    )
    skills = (
        Skill(id="skill.authorization", name="Authorization boundary verification"),
        Skill(id="skill.testing", name="Testing"),
    )

    proposals = propose_assessments(
        snapshot=snapshot,
        fixture_hash=corpus["fixture_hash"],
        source_manifest_hash=corpus["source_manifest_hash"],
        skills=skills,
        candidates_by_entry={
            "entry-implementation": (
                "Authorization boundary verification",
                "Testing",
                "backend development",
            )
        },
        aliases=(
            _alias("authorization boundary verification", "skill.authorization"),
            _alias("testing", "skill.testing"),
        ),
    )

    assert [(proposal.skill_id, proposal.contribution_id) for proposal in proposals] == [
        ("skill.authorization", "contrib-stoa-authorization-boundary"),
        ("skill.testing", "contrib-stoa-authorization-boundary"),
    ]
    for proposal in proposals:
        assert proposal.fixture_hash == corpus["fixture_hash"]
        assert proposal.audit_id == "audit-e2e"
        assert proposal.conclusion_lineage_hash == snapshot.conclusion_lineage_hash
        assert proposal.conclusion_entry_ids == ("entry-implementation",)
        assert proposal.evidence_ids == ("evid-stoa-backend-audit", "evid-stoa-build-week")
        assert proposal.answer_question_ids == (
            "question-implementation-assistance-2",
            "question-implementation-hard-0-0",
            "question-implementation-ownership-1",
        )
        assert proposal.attribution_area_ids == ("implementation",)
        assert proposal.normalization_record_hash.startswith("sha256:")


@pytest.mark.parametrize("relation_kind", ("dependency", "implies_knowledge"))
def test_descriptive_relation_does_not_hide_an_exact_alias_proposal(
    tmp_path: Path, relation_kind: str
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
        skills=(
            Skill(id="skill.python", name="Python"),
            Skill(id="skill.programming", name="Programming"),
        ),
        aliases=(_alias("Python", "skill.python"),),
        ontology_relations=(
            OntologyRelation(
                source_skill_id="skill.python",
                target_skill_id="skill.programming",
                relation_kind=relation_kind,
                ontology_source_id="mind-tech-ontology",
                pinned_revision="a" * 40,
            ),
        ),
        candidates_by_entry={"entry-implementation": ("Python",)},
    )

    assert [proposal.skill_id for proposal in proposals] == ["skill.python"]


@pytest.mark.parametrize("with_ambiguous_aliases", (False, True))
def test_descriptive_relationship_cannot_resolve_a_missing_or_ambiguous_alias(
    with_ambiguous_aliases: bool,
) -> None:
    skills = (
        Skill(id="skill.python", name="Python"),
        Skill(id="skill.programming", name="Programming"),
    )
    aliases = (
        (_alias("Python", "skill.python"), _alias("Python", "skill.programming"))
        if with_ambiguous_aliases
        else ()
    )
    record = resolve_skill_candidate(
        "Python",
        skills=skills,
        aliases=aliases,
        ontology_relations=(
            OntologyRelation(
                source_skill_id="skill.python",
                target_skill_id="skill.programming",
                relation_kind="implies_knowledge",
                ontology_source_id="mind-tech-ontology",
                pinned_revision="a" * 40,
            ),
        ),
    )

    assert record.review_status == (
        "review-required" if with_ambiguous_aliases else "descriptive-only"
    )
    assert record.candidate_skill_ids == (
        ("skill.programming", "skill.python") if with_ambiguous_aliases else ("skill.programming",)
    )


def test_confirmed_aliases_of_one_skill_keep_one_proposal_and_all_candidate_sources(
    tmp_path: Path,
) -> None:
    corpus = __import__("json").loads(CORPUS_PATH.read_text(encoding="utf-8"))
    links = tuple(
        CandidateSkillLink(
            id=f"candidate-skill-{wording.lower()}",
            experience_candidate_id="experience-candidate-python",
            source_id="source-python",
            capture_hash="sha256:" + "a" * 64,
            source_locator=f"synthetic.md#{wording.lower()}",
            candidate_text=wording,
            extraction_version="synthetic/v1",
        )
        for wording in ("Python", "py")
    )
    plan_payload = corpus["audit_journey"]["probe_plan"]
    plan_payload["areas"][0]["candidate_skill_link_ids"] = [link.id for link in links]
    decisions = tuple(
        BoundaryDecision.model_validate(item) for item in corpus["audit_journey"]["decisions"]
    )
    port = RecordedDecisionPort(
        plan=ProbePlan.model_validate(plan_payload),
        decisions={(item.question_id, item.answer): item for item in decisions},
    )
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=ROOT / corpus["fixture_path"],
        manifest_path=ROOT / corpus["source_manifest_path"],
        contribution_id=corpus["contribution_id"],
        audit_id="audit-e2e",
        experience_candidate_id="experience-candidate-python",
        candidate_skill_links=links,
        decision_port=port,
    )
    for action in corpus["audit_journey"]["actions"]:
        snapshot = transition_audit(
            snapshot, AuditAction.model_validate(action), decision_port=port
        )
    arguments = {
        "snapshot": snapshot,
        "fixture_hash": corpus["fixture_hash"],
        "source_manifest_hash": corpus["source_manifest_hash"],
        "skills": (Skill(id="skill.python", name="Python"),),
        "aliases": (_alias("Python", "skill.python"), _alias("py", "skill.python")),
    }
    proposals = propose_assessments(
        **arguments,
        candidates_by_entry={"entry-implementation": ("Python", "py", " PYTHON ")},
    )

    assert len(proposals) == 1
    assert proposals[0].skill_id == "skill.python"
    assert proposals[0].candidate_skill_link_ids == (
        "candidate-skill-py",
        "candidate-skill-python",
    )
    assert proposals[0].evidence_ids == ("evid-stoa-backend-audit", "evid-stoa-build-week")
    assert proposals == propose_assessments(
        **arguments,
        candidates_by_entry={"entry-implementation": ("py", "Python")},
    )
    single = propose_assessments(
        **arguments, candidates_by_entry={"entry-implementation": ("Python",)}
    )
    assert single == propose_assessments(
        **arguments,
        candidates_by_entry={"entry-implementation": ("Python", " PYTHON ")},
    )
    assert single[0].normalization_record_hash != proposals[0].normalization_record_hash
