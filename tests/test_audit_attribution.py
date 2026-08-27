from __future__ import annotations

from test_audit_policy import _start

from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.workflow import transition_audit


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
