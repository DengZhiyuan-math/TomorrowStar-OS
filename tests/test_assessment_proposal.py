"""Contribution-to-specific-Skill proposal contracts."""

from __future__ import annotations

from pathlib import Path

from career_evidence_graph.assessment import (
    _materialize_audit,
    _repository_root,
    propose_assessments,
    resolve_skill_candidate,
)
from career_evidence_graph.domain.models import Skill, SkillAlias

ROOT = Path(__file__).parents[1]
CORPUS_PATH = ROOT / "validation/calibration/phase-04/corpus.json"


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
