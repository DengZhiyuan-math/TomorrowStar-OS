from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.assessment import propose_assessments
from career_evidence_graph.audit.models import (
    ArtifactFact,
    AuditAction,
    BoundaryDecision,
    ProbeArea,
    ProbePlan,
)
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.audit.workflow import AuditWorkflowError, start_audit, transition_audit
from career_evidence_graph.domain.models import Skill, SkillAlias

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def _start(tmp_path: Path, audit_id: str = "audit-regression"):
    return start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id=audit_id,
    )


def test_early_attribution_signal_requires_ownership_then_assistance_before_resuming(
    tmp_path: Path,
):
    snapshot = _start(tmp_path)
    signalled = transition_audit(
        snapshot,
        AuditAction(action="answer", answer="This implementation was not me; the team did it."),
    )
    assert signalled.questions[-1].turn == "ownership"

    owned = transition_audit(
        signalled,
        AuditAction(action="answer", answer="The team owned this work."),
    )
    assert owned.questions[-1].turn == "assistance"
    resumed = transition_audit(
        owned,
        AuditAction(action="answer", answer="No outside assistance."),
    )
    assert resumed.status == "active"
    assert resumed.questions[-1].turn == "capability"
    assert resumed.coverage[0].strongest_capability is None
    assert resumed.attribution_records[0].ownership == "team-owned"


def test_question_target_must_match_the_one_active_question(tmp_path: Path):
    snapshot = _start(tmp_path)
    with pytest.raises(AuditWorkflowError, match="active question"):
        transition_audit(
            snapshot,
            AuditAction(
                action="answer",
                answer="I designed and verified it.",
                question_id="question-implementation-hard-0-99",
            ),
        )


def test_area_skip_never_creates_an_attribution_capability_entry(tmp_path: Path):
    snapshot = _start(tmp_path)
    skipped = transition_audit(
        snapshot, AuditAction(action="skip", answer="Self-rating: uncertain")
    )
    entry = skipped.conclusion.entries[0]
    assert entry.area == "implementation"
    assert entry.verification == "self-assessed-unverified"
    assert entry.area not in {"responsibility", "assistance"}


class SyntheticDecisions:
    def __init__(self, areas=("implementation",), contribution_id="contrib-stoa-synthetic"):
        self.plan = ProbePlan(
            contribution_id=contribution_id,
            areas=tuple(
                ProbeArea(
                    area_id=area,
                    inspected_fact_ids=("evidence-synthetic",),
                    unverified_capability=f"synthetic {area}",
                    demanding_prompt=f"How did you perform {area} under failure?",
                    intermediate_prompt=f"Which {area} change did you check?",
                    simple_prompt=f"Which {area} step did you complete?",
                    immediately_higher_capability="independent advanced work",
                )
                for area in areas
            ),
        )

    def plan_probe(self, contribution_id, facts):
        return self.plan

    def decide_boundary(self, question, answer):
        established = answer == "synthetic capability answer"
        outcome = "established" if established else "attribution-signal"
        if answer == "synthetic incomplete answer":
            outcome = "incomplete"
        return BoundaryDecision(
            question_id=question.id,
            answer=answer,
            outcome=outcome,
            rationale="Synthetic decision for the exact submitted answer.",
            strongest_capability="bounded synthetic work" if established else None,
            next_higher_not_established="independent advanced work" if established else None,
        )


@pytest.fixture
def synthetic_inspection(monkeypatch):
    fact = ArtifactFact(
        evidence_id="evidence-synthetic",
        source_locator="synthetic.md#work",
        statement="A synthetic contribution needs capability and attribution review.",
    )
    monkeypatch.setattr(
        "career_evidence_graph.audit.workflow.inspect_contribution",
        lambda *args: ((fact,), ()),
    )


def _synthetic_start(tmp_path, port, **kwargs):
    return start_audit(
        workspace=tmp_path,
        fixture_path=tmp_path / "synthetic-fixture.json",
        manifest_path=tmp_path / "synthetic-manifest.json",
        contribution_id="contrib-stoa-synthetic",
        audit_id="audit-synthetic-regression",
        decision_port=port,
        **kwargs,
    )


def _answer(snapshot, answer, port):
    return transition_audit(
        snapshot, AuditAction(action="answer", answer=answer), decision_port=port
    )


def test_multiple_capability_areas_complete_separate_attribution_turns(
    tmp_path, synthetic_inspection
):
    port = SyntheticDecisions(("implementation", "technical-design"))
    snapshot = _synthetic_start(tmp_path, port)
    for _ in port.plan.areas:
        snapshot = _answer(snapshot, "synthetic capability answer", port)
        snapshot = _answer(snapshot, "I owned it.", port)
        snapshot = _answer(snapshot, "No outside assistance.", port)

    assert snapshot.status == "reviewing"
    assert len(snapshot.attribution_records) == 2
    assert all(item.status == "verified" for item in snapshot.coverage)
    assert [item.turn for item in snapshot.questions] == [
        "capability",
        "ownership",
        "assistance",
        "capability",
        "ownership",
        "assistance",
    ]
    AuditStore(tmp_path).replace(snapshot)
    assert AuditStore(tmp_path).read(snapshot.audit_id) == snapshot


def test_resumed_capability_reuses_completed_attribution_without_reasking(
    tmp_path, synthetic_inspection
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    for answer in (
        "synthetic attribution signal",
        "I owned it.",
        "Codex assisted testing.",
        "synthetic capability answer",
    ):
        snapshot = _answer(snapshot, answer, port)

    assert snapshot.status == "reviewing"
    assert snapshot.coverage[0].status == "verified"
    assert snapshot.coverage[0].attribution_stage == "complete"
    assert [item.turn for item in snapshot.questions] == [
        "capability",
        "ownership",
        "assistance",
        "capability",
    ]
    assert snapshot.attribution_records[0].assistance == "coding-agent-assisted"
    assert "Codex assisted testing." in snapshot.conclusion.entries[0].assistance_boundary


def test_repeated_attribution_signal_does_not_reopen_attribution_or_verify_capability(
    tmp_path, synthetic_inspection
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    for answer in (
        "synthetic attribution signal",
        "I owned it.",
        "No outside assistance.",
        "synthetic attribution signal",
    ):
        snapshot = _answer(snapshot, answer, port)

    assert snapshot.status == "active"
    assert snapshot.questions[-1].turn == "capability"
    assert snapshot.questions[-1].follow_up_count == 1
    assert snapshot.coverage[0].status == "pending"
    assert snapshot.coverage[0].strongest_capability is None
    assert sum(item.turn == "ownership" for item in snapshot.questions) == 1


@pytest.mark.parametrize(
    "denial",
    [
        "不是我，其他人负责。",
        "我负责的不是这段实现。",
        "The team owned this work.",
        "I owned the planning; someone else implemented this contribution.",
        "Codex did not implement it; I did not implement it either.",
        "第三方没有参与测试，我也没有参与实现。",
    ],
)
def test_later_ownership_conflict_cannot_reuse_the_initial_personal_claim(
    tmp_path, synthetic_inspection, denial
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    for answer in (
        "synthetic attribution signal",
        "I owned it.",
        "No outside assistance.",
        denial,
        "synthetic capability answer",
    ):
        snapshot = _answer(snapshot, answer, port)
    assert snapshot.attribution_records[0].ownership == "unresolved"
    assert snapshot.attribution.ownership == "unresolved"
    assert snapshot.attribution_conflicts[-1].user_claim == denial
    assert any(answer.answer == "I owned it." for answer in snapshot.answers)
    assert any(answer.answer == denial for answer in snapshot.answers)
    assert snapshot.conclusion.entries[0].conflicts
    for action in (
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the recorded unresolved conflict.",
        ),
        AuditAction(
            action="review-conclusion",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the complete record, including its conflict.",
        ),
    ):
        snapshot = transition_audit(snapshot, action)
    assert not propose_assessments(
        snapshot=snapshot,
        fixture_hash="sha256:" + "a" * 64,
        source_manifest_hash="sha256:" + "b" * 64,
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


@pytest.mark.parametrize(
    "initial,correction,scope,tool,ownership",
    [
        (
            "No outside assistance.",
            "Codex assisted testing.",
            ("testing",),
            "Codex",
            "user-owned",
        ),
        ("无协助。", "第三方协助设计。", ("design",), None, "user-owned"),
        (
            "No outside assistance.",
            "No assistance with design; Codex assisted testing.",
            ("design", "testing"),
            None,
            "user-owned",
        ),
        (
            "No outside assistance.",
            "Codex did not assist design; it assisted testing.",
            ("design", "testing"),
            None,
            "user-owned",
        ),
        (
            "No outside assistance.",
            "第三方没有参与设计，但协助了测试。",
            ("design", "testing"),
            None,
            "user-owned",
        ),
        (
            "Codex assisted testing.",
            "Codex assisted design.",
            ("design",),
            "Codex",
            "user-owned",
        ),
        ("A third party assisted testing.", "No outside assistance.", (), None, "user-owned"),
        ("Codex assisted testing.", "I did not use Codex.", (), None, "user-owned"),
        (
            "A third party assisted testing.",
            "No third party assisted me.",
            (),
            None,
            "user-owned",
        ),
        (
            "No outside assistance.",
            "不是我，其他人负责；Codex assisted testing.",
            ("testing",),
            "Codex",
            "unresolved",
        ),
    ],
)
def test_later_assistance_conflict_survives_reload_and_cannot_authorize_a_skill_proposal(
    tmp_path, synthetic_inspection, initial, correction, scope, tool, ownership
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    store = AuditStore(tmp_path)
    for answer in (
        "synthetic attribution signal",
        "I owned it.",
        initial,
        correction,
        "synthetic capability answer",
    ):
        snapshot = _answer(snapshot, answer, port)
        store.replace(snapshot)
        snapshot = store.read(snapshot.audit_id)

    record = snapshot.attribution_records[0]
    assert record.assistance == snapshot.attribution.assistance == "unresolved"
    assert record.assistance_answer == correction
    assert record.assistance_scope == scope
    assert record.tool == snapshot.attribution.tool == tool
    assert record.ownership == snapshot.attribution.ownership == ownership
    assert any(initial in conflict.artifact_claim for conflict in snapshot.attribution_conflicts)
    assert snapshot.attribution_conflicts[-1].user_claim == correction
    assert {initial, correction} <= {answer.answer for answer in snapshot.answers}
    entry = snapshot.conclusion.entries[0]
    assert entry.assistance_boundary == f"unresolved: {correction}"
    assert entry.conflicts

    for action in (
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the recorded assistance conflict.",
        ),
        AuditAction(
            action="review-conclusion",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the complete record, including its conflict.",
        ),
    ):
        snapshot = transition_audit(snapshot, action)
        store.replace(snapshot)
        snapshot = store.read(snapshot.audit_id)
    assert not propose_assessments(
        snapshot=snapshot,
        fixture_hash="sha256:" + "a" * 64,
        source_manifest_hash="sha256:" + "b" * 64,
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


@pytest.mark.parametrize(
    "initial,repeated",
    [
        ("No outside assistance.", "无协助。"),
        ("Codex assisted testing.", "Codex assisted testing."),
        ("Codex assisted testing.", "A coding agent assisted."),
        ("A third party assisted design.", "A third party assisted design."),
        ("No outside assistance.", "I did not use Codex."),
        ("No outside assistance.", "第三方没有参与测试。"),
    ],
)
def test_matching_later_assistance_retains_attribution_without_a_conflict(
    tmp_path, synthetic_inspection, initial, repeated
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    for answer in ("synthetic attribution signal", "I owned it.", initial):
        snapshot = _answer(snapshot, answer, port)
    record = snapshot.attribution_records[0]
    for answer in (repeated, "synthetic capability answer"):
        snapshot = _answer(snapshot, answer, port)

    assert snapshot.attribution_records[0] == record
    assert not snapshot.attribution_conflicts
    assert not snapshot.conclusion.entries[0].conflicts
    assert snapshot.coverage[0].status == "verified"


def test_attribution_signal_on_followup_resumes_then_establishes(tmp_path, synthetic_inspection):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    snapshot = _answer(snapshot, "synthetic incomplete answer", port)
    original_followup = snapshot.questions[-1]
    assert original_followup.follow_up_count == 1
    for answer in (
        "synthetic attribution signal",
        "I owned it.",
        "No outside assistance.",
    ):
        snapshot = _answer(snapshot, answer, port)

    resumed = snapshot.questions[-1]
    assert resumed.turn == "capability"
    assert resumed.difficulty == original_followup.difficulty
    assert resumed.follow_up_count == original_followup.follow_up_count
    assert resumed.prompt != original_followup.prompt
    snapshot = _answer(snapshot, "synthetic capability answer", port)
    assert snapshot.status == "reviewing"
    assert snapshot.coverage[0].status == "verified"


@pytest.mark.parametrize(
    "answer",
    [
        "No assistance with design; Codex assisted testing.",
        "No outside assistance except a third party handled testing.",
        "Codex and a third party assisted testing.",
        "没有协助设计，但代码代理完成了测试。",
        "I did not use Codex; a third party assisted testing.",
        "I did not use a consultant; Codex assisted testing.",
        "Codex did not assist design; Codex assisted testing.",
        "我没有使用代码代理，第三方协助测试。",
        "Codex did not assist design; it assisted testing.",
        "第三方没有参与设计，但协助了测试。",
    ],
)
def test_mixed_assistance_stays_unresolved_with_original_answer(
    tmp_path, synthetic_inspection, answer
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    store = AuditStore(tmp_path)
    for response in ("synthetic capability answer", "I owned it.", answer):
        snapshot = _answer(snapshot, response, port)
        store.replace(snapshot)
        snapshot = store.read(snapshot.audit_id)
    for action in (
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the recorded mixed assistance boundary.",
        ),
        AuditAction(
            action="review-conclusion",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the complete synthetic audit.",
        ),
    ):
        snapshot = transition_audit(snapshot, action)
        store.replace(snapshot)
        snapshot = store.read(snapshot.audit_id)

    record = snapshot.attribution_records[0]
    assert record.assistance == "unresolved"
    assert record.assistance_answer == answer
    assert "testing" in record.assistance_scope
    assert snapshot.conclusion.entries[0].assistance_boundary == f"unresolved: {answer}"


@pytest.mark.parametrize(
    "answer",
    [
        "I did not use Codex.",
        "I didn't use ChatGPT for testing.",
        "I never used a coding agent.",
        "I did not receive assistance from a consultant.",
        "I did not receive any assistance from Codex.",
        "I didn't receive any help from a consultant.",
        "I never received any support from a third party.",
        "No third party assisted me.",
        "Without Codex assistance.",
        "No assistance from a third party.",
        "Codex did not assist me.",
        "A consultant didn't help me.",
        "Codex was not used for generation.",
        "Codex wasn't involved in testing.",
        "我没有使用 Codex。",
        "我没有使用过 Codex。",
        "我未借助过第三方。",
        "我未用代码代理。",
        "没有第三方协助。",
        "第三方没有参与测试。",
        "Codex did not assist design; it did not assist testing either.",
        "第三方没有参与设计，也没有协助测试。",
    ],
)
def test_denied_assistance_survives_reload_and_confirmation(tmp_path, synthetic_inspection, answer):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    store = AuditStore(tmp_path)
    for response in ("synthetic capability answer", "I owned it.", answer):
        snapshot = _answer(snapshot, response, port)
        store.replace(snapshot)
        snapshot = store.read(snapshot.audit_id)
    for action in (
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the recorded capability and attribution.",
        ),
        AuditAction(
            action="review-conclusion",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the complete synthetic audit.",
        ),
    ):
        snapshot = transition_audit(snapshot, action)
        store.replace(snapshot)
        snapshot = store.read(snapshot.audit_id)

    record = snapshot.attribution_records[0]
    assert record.assistance == snapshot.attribution.assistance == "none"
    assert record.assistance_answer == answer
    assert record.assistance_scope == ()
    assert record.tool is None
    assert not snapshot.attribution_conflicts
    assert snapshot.conclusion.entries[0].assistance_boundary == f"none: {answer}"


@pytest.mark.parametrize(
    "answer,assistance,tool",
    [
        ("Codex helped define not-null constraints.", "coding-agent-assisted", "Codex"),
        ("Codex assisted testing; no failures occurred.", "coding-agent-assisted", "Codex"),
        ("Codex helped define invariants.", "coding-agent-assisted", "Codex"),
        ("第三方协助定义不变量。", "third-party-assisted", None),
        ("No downtime occurred; a consultant assisted testing.", "third-party-assisted", None),
    ],
)
def test_technical_negation_does_not_erase_positive_assistance(
    tmp_path, synthetic_inspection, answer, assistance, tool
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    for response in ("synthetic capability answer", "I owned it.", answer):
        snapshot = _answer(snapshot, response, port)
    record = snapshot.attribution_records[0]
    assert record.assistance == snapshot.attribution.assistance == assistance
    assert record.assistance_answer == answer
    assert record.tool == tool
    assert not snapshot.attribution_conflicts


def test_experience_candidate_without_optional_skill_links_uses_v2(tmp_path, synthetic_inspection):
    snapshot = _synthetic_start(
        tmp_path,
        SyntheticDecisions(),
        experience_candidate_id="experience-candidate-synthetic",
    )

    assert snapshot.schema_version == "audit-snapshot/v2"
    assert snapshot.candidate_skill_links == ()
    assert AuditStore(tmp_path).read(snapshot.audit_id) == snapshot


def test_probe_plan_cannot_change_the_selected_contribution(tmp_path, synthetic_inspection):
    with pytest.raises(AuditWorkflowError, match="another Contribution"):
        _synthetic_start(tmp_path, SyntheticDecisions(contribution_id="contrib-stoa-unrelated"))
    assert not (tmp_path / "audits").exists()


@pytest.mark.parametrize(
    "answer",
    [
        "I owned nothing; my colleague implemented everything.",
        "I was responsible for review, not implementation.",
        "I owned the task but never implemented it.",
        "I owned the task but didn't do the implementation.",
        "I owned scheduling but wasn't responsible for the implementation.",
        "我负责的不是这段实现。",
        "我负责设计，不包括实现。",
        "我负责设计，不涉及实现。",
        "I owned planning, not this implementation.",
    ],
)
def test_negated_ownership_stays_unresolved_with_original_answer(
    tmp_path, synthetic_inspection, answer
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    snapshot = _answer(snapshot, "synthetic capability answer", port)
    snapshot = _answer(snapshot, answer, port)

    assert snapshot.attribution_records[0].ownership == "unresolved"
    assert snapshot.attribution_records[0].ownership_answer == answer
    assert snapshot.questions[-1].turn == "assistance"


@pytest.mark.parametrize(
    "answer",
    [
        "我负责定义不变量。",
        "我负责实现不可变数据结构。",
        "I owned the not-null constraints.",
        "I owned the failover; no downtime occurred.",
        "我负责定义不变量，第三方没有参与。",
        "I owned the implementation; Codex did not implement it.",
    ],
)
def test_technical_negation_does_not_erase_reviewed_ownership(
    tmp_path, synthetic_inspection, answer
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    for response in ("synthetic capability answer", answer, "No outside assistance."):
        snapshot = _answer(snapshot, response, port)
    assert snapshot.attribution_records[0].ownership == "user-owned"
    assert snapshot.attribution_records[0].ownership_answer == answer
    for action in (
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the capability and attribution.",
        ),
        AuditAction(
            action="review-conclusion",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the complete synthetic audit.",
        ),
    ):
        snapshot = transition_audit(snapshot, action)
    proposals = propose_assessments(
        snapshot=snapshot,
        fixture_hash="sha256:" + "a" * 64,
        source_manifest_hash="sha256:" + "b" * 64,
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
    assert len(proposals) == 1


def test_confirmed_prose_correction_survives_and_cannot_authorize_a_skill_proposal(
    tmp_path, synthetic_inspection
):
    port = SyntheticDecisions()
    snapshot = _synthetic_start(tmp_path, port)
    for answer in ("synthetic capability answer", "I owned it.", "No outside assistance."):
        snapshot = _answer(snapshot, answer, port)
    original = snapshot.conclusion.original_proposal
    correction = "No capability was established; I did not implement this work."
    for action in (
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="edit",
            correction=correction,
            reviewer_id="synthetic-reviewer",
            reason="Correct the capability claim.",
        ),
        AuditAction(
            action="review-entry",
            entry_id="entry-implementation",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the correction.",
        ),
        AuditAction(
            action="review-conclusion",
            decision="confirm",
            reviewer_id="synthetic-reviewer",
            reason="Confirm the corrected conclusion.",
        ),
    ):
        snapshot = transition_audit(snapshot, action)

    assert snapshot.conclusion.original_proposal == original
    assert snapshot.conclusion.entries[0].correction == correction
    assert snapshot.conclusion.entries[0].review == "confirmed"
    assert snapshot.conclusion_reviews[0].correction == correction
    AuditStore(tmp_path).replace(snapshot)
    assert AuditStore(tmp_path).read(snapshot.audit_id) == snapshot
    assert (
        propose_assessments(
            snapshot=snapshot,
            fixture_hash="sha256:" + "a" * 64,
            source_manifest_hash="sha256:" + "b" * 64,
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
