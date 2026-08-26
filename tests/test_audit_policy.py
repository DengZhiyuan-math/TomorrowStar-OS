from pathlib import Path

import pytest

from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.audit.workflow import start_audit, transition_audit

FIXTURE = Path("validation/fixtures/stoa/v1/known-good.json")
MANIFEST = FIXTURE.parent / "source-manifest.json"


def _start(tmp_path, audit_id="audit-policy"):
    return start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id=audit_id,
    )


@pytest.mark.phase03_original_probe
def test_transition_has_exactly_one_active_question(tmp_path):
    snap = _start(tmp_path)
    assert [q for q in snap.questions if q.status == "unanswered"] == [snap.questions[-1]]
    snap = transition_audit(
        AuditStore(tmp_path), snap, AuditAction(action="answer", answer="I designed it.")
    )
    assert [q for q in snap.questions if q.status == "unanswered"] == [snap.questions[-1]]


@pytest.mark.phase03_original_probe
def test_only_one_same_level_followup(tmp_path):
    snap = _start(tmp_path)
    assert snap.questions[0].difficulty == "hard"
    snap = transition_audit(
        AuditStore(tmp_path), snap, AuditAction(action="answer", answer="不完整")
    )
    assert snap.questions[-1].follow_up_count == 1
    snap = transition_audit(
        AuditStore(tmp_path), snap, AuditAction(action="answer", answer="不知道")
    )
    assert snap.questions[-1].difficulty == "intermediate"
    assert len({q.id for q in snap.questions}) == len(snap.questions)


@pytest.mark.phase03_original_probe
def test_second_incomplete_answer_descends(tmp_path):
    snap = _start(tmp_path)
    store = AuditStore(tmp_path)
    snap = transition_audit(store, snap, AuditAction(action="answer", answer="不完整"))
    snap = transition_audit(store, snap, AuditAction(action="answer", answer="不确定"))
    assert snap.questions[-1].difficulty == "intermediate"


@pytest.mark.phase03_original_probe
def test_dont_know_descends_without_penalty(tmp_path):
    snap = _start(tmp_path)
    store = AuditStore(tmp_path)
    snap = transition_audit(store, snap, AuditAction(action="answer", answer="不知道"))
    assert snap.questions[-1].difficulty == "hard"
    assert snap.questions[-1].follow_up_count == 1
    assert snap.coverage[0].status == "pending"


@pytest.mark.phase03_original_probe
def test_blank_answer_fails_closed(tmp_path):
    snap = _start(tmp_path)
    with pytest.raises(ValueError, match="requires answer"):
        AuditAction(action="answer", answer="")
    assert snap.answers == ()


@pytest.mark.phase03_original_probe
def test_duplicate_action_is_idempotent(tmp_path):
    snap = _start(tmp_path)
    action = AuditAction(action="answer", answer="I designed it.", action_id="action-policy-dup")
    updated = transition_audit(AuditStore(tmp_path), snap, action)
    assert transition_audit(AuditStore(tmp_path), updated, action) == updated


@pytest.mark.phase03_original_probe
def test_stale_expected_hash_rejects_lost_update(tmp_path):
    snap = _start(tmp_path)
    action = AuditAction(
        action="answer",
        answer="I designed it.",
        expected_snapshot_hash="sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="stale audit snapshot"):
        transition_audit(AuditStore(tmp_path), snap, action)


@pytest.mark.phase03_original_probe
def test_resume_returns_next_unanswered_question(tmp_path):
    snap = _start(tmp_path)
    store = AuditStore(tmp_path)
    snap = transition_audit(store, snap, AuditAction(action="answer", answer="I designed it."))
    next_question = snap.questions[-1]
    paused = transition_audit(store, snap, AuditAction(action="pause"))
    resumed = transition_audit(store, paused, AuditAction(action="resume"))
    assert resumed.questions[-1] == next_question


@pytest.mark.phase03_original_probe
def test_exhausted_or_irrelevant_area_emits_no_question(tmp_path):
    snap = _start(tmp_path)
    store = AuditStore(tmp_path)
    for answer in (
        "skip implementation",
        "skip debugging",
        "skip operation",
        "skip responsibility",
        "skip assistance",
    ):
        snap = transition_audit(store, snap, AuditAction(action="skip", answer=answer))
    assert not [q for q in snap.questions if q.status == "unanswered"]
    assert snap.status == "reviewing"


@pytest.mark.phase03_original_probe
def test_unicode_answer_and_reason_round_trip_exactly(tmp_path):
    snap = _start(tmp_path)
    answer = "我选择了边界 — résumé"
    updated = transition_audit(
        AuditStore(tmp_path), snap, AuditAction(action="answer", answer=answer)
    )
    assert updated.answers[-1].answer == answer
    assert updated.questions[0].reason == snap.questions[0].reason


@pytest.mark.phase03_original_probe
def test_fixture_ladder_is_hard_to_simple_and_stable(tmp_path):
    snap = _start(tmp_path)
    store = AuditStore(tmp_path)
    difficulties = [snap.questions[-1].difficulty]
    for _ in range(5):
        snap = transition_audit(store, snap, AuditAction(action="answer", answer="不知道"))
        difficulties.append(snap.questions[-1].difficulty)
    assert difficulties == ["hard", "hard", "intermediate", "intermediate", "simple", "simple"]


def test_skip_preserves_verbatim_self_rating(tmp_path):
    snap = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-skip",
    )
    snap = transition_audit(
        AuditStore(tmp_path), snap, AuditAction(action="skip", answer="自评：大约 7/10")
    )
    assert snap.coverage[0].status == "skipped"
    assert snap.coverage[0].self_rating == "自评：大约 7/10"
