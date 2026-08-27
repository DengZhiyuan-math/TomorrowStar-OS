from __future__ import annotations

from test_audit_policy import FIXTURE, MANIFEST, ScriptedDecisions, _start

from career_evidence_graph.audit.models import AuditAction, ProbeArea, ProbePlan
from career_evidence_graph.audit.workflow import start_audit, transition_audit


def _establish(snapshot, port):
    return transition_audit(
        snapshot,
        AuditAction(action="answer", answer="I can explain the authorization trade-off"),
        decision_port=port,
    )


def test_ordinary_established_path_requires_ownership_then_assistance(tmp_path) -> None:
    snapshot, port = _start(tmp_path)
    snapshot = _establish(snapshot, port)
    assert snapshot.coverage[0].status == "pending"
    assert snapshot.questions[-1].turn == "ownership"

    snapshot = transition_audit(snapshot, AuditAction(action="answer", answer="I owned it."))
    assert snapshot.questions[-1].turn == "assistance"
    assert snapshot.coverage[0].status == "pending"

    snapshot = transition_audit(
        snapshot,
        AuditAction(action="answer", answer="Codex assisted debugging and testing."),
    )
    record = snapshot.attribution_records[0]
    assert snapshot.coverage[0].status == "verified"
    assert record.ownership == "user-owned"
    assert record.assistance == "coding-agent-assisted"
    assert record.assistance_scope == ("debugging", "testing")
    assert record.tool == "Codex"


def test_early_attribution_signal_uses_same_two_turn_sequence_then_resumes(tmp_path) -> None:
    snapshot, port = _start(tmp_path)
    snapshot = transition_audit(
        snapshot,
        AuditAction(action="answer", answer="this was not my work"),
        decision_port=port,
    )
    assert snapshot.questions[-1].turn == "ownership"
    assert snapshot.coverage[0].status == "pending"

    snapshot = transition_audit(snapshot, AuditAction(action="answer", answer="not me"))
    assert snapshot.questions[-1].turn == "assistance"
    snapshot = transition_audit(snapshot, AuditAction(action="answer", answer="unresolved"))
    assert snapshot.questions[-1].turn == "capability"
    assert snapshot.attribution_records[0].ownership == "other-person-owned"
    assert snapshot.attribution_records[0].assistance == "unresolved"
    assert snapshot.attribution_conflicts


def test_other_person_conflict_uses_the_active_capability_area_fact(tmp_path) -> None:
    plan = ProbePlan(
        contribution_id="contrib-stoa-authorization-boundary",
        areas=(
            ProbeArea(
                area_id="implementation",
                inspected_fact_ids=("evid-stoa-build-week",),
                unverified_capability="authorization-boundary implementation",
                demanding_prompt="How did you implement the authorization boundary?",
                intermediate_prompt="Which authorization check did you add?",
                simple_prompt="Which authorization step did you complete?",
                immediately_higher_capability="independently defending authorization failures",
            ),
            ProbeArea(
                area_id="technical-design",
                inspected_fact_ids=("evid-stoa-backend-audit",),
                unverified_capability="authorization-boundary design",
                demanding_prompt="How did you design the authorization boundary?",
                intermediate_prompt="Which boundary trade-off did you make?",
                simple_prompt="Which design step did you complete?",
                immediately_higher_capability="independently defending authorization design",
            ),
        ),
    )
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id=plan.contribution_id,
        audit_id="audit-attribution-facts",
        decision_port=ScriptedDecisions(plan),
    )
    snapshot = snapshot.model_copy(
        update={
            "inspected_facts": tuple(
                fact.model_copy(update={"statement": f"{fact.statement} ({fact.evidence_id})"})
                for fact in snapshot.inspected_facts
            )
        }
    )
    active_area_fact = next(
        fact for fact in snapshot.inspected_facts if fact.evidence_id == "evid-stoa-build-week"
    )
    assert snapshot.inspected_facts[0] != active_area_fact
    assert snapshot.inspected_facts[0].statement != active_area_fact.statement

    snapshot = transition_audit(
        snapshot,
        AuditAction(action="answer", answer="this was not my work"),
        decision_port=ScriptedDecisions(plan),
    )
    snapshot = transition_audit(snapshot, AuditAction(action="answer", answer="not me"))

    assert snapshot.attribution_conflicts[-1].artifact_claim == active_area_fact.statement


def test_unresolved_attribution_is_truthful_and_pause_restores_next_turn(tmp_path) -> None:
    snapshot, port = _start(tmp_path)
    snapshot = _establish(snapshot, port)
    snapshot = transition_audit(snapshot, AuditAction(action="answer", answer="unclear"))
    assert snapshot.questions[-1].turn == "assistance"
    paused = transition_audit(snapshot, AuditAction(action="pause"))
    resumed = transition_audit(paused, AuditAction(action="resume"))
    assert resumed.questions[-1] == snapshot.questions[-1]

    complete = transition_audit(resumed, AuditAction(action="answer", answer="unclear"))
    assert complete.attribution_records[0].ownership == "unresolved"
    assert complete.attribution_records[0].assistance == "unresolved"
    assert complete.coverage[0].status == "verified"
