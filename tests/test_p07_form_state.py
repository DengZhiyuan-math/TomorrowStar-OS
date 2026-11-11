"""Conservative ATS value comparison and parser observation; synthetic values only."""

from copy import deepcopy

import pytest

from career_evidence_graph.application_form_state import decision, equivalent, sample


def field(value="", **extra):
    return {"id": "email", "type": "email", "value": value, **extra}


def observed(value="", parser="unknown", **extra):
    return {"fields": [field(value)], "parser": {"status": parser, "signal": parser}, **extra}


BINDING = {"run_id": "run", "page_id": "page", "step": "contact"}


@pytest.mark.parametrize(
    "kind,left,right,expected",
    [
        ("text", "  Jane  Smith\n", "Jane Smith", True),
        ("text", "Jane Smith", "jane smith", False),
        ("email", "User@EXAMPLE.TEST", "User@example.test", True),
        ("email", "User@example.test", "user@example.test", False),
        ("tel", "+41 (22) 123-45-67", "+41221234567", True),
        ("tel", "0041 22 123 45 67", "+41221234567", True),
        ("tel", "0221234567", "+41221234567", False),
        ("tel", "+41221234567 x12", "+4122123456712", False),
        ("date", "2026-10-23", "2026/10/23", True),
        ("date", "23/10/2026", "2026-10-23", True),
        ("date", "10/23/2026", "2026-10-23", True),
        ("date", "04/05/2026", "2026-04-05", False),
        ("date", "2026-02-30", "2026/02/30", False),
        ("text", "2026-10-23", "2026/10/23", False),
    ],
)
def test_meaning_equivalence_does_not_guess(kind, left, right, expected):
    assert equivalent({"type": kind}, left, right) is expected


def test_existing_nonempty_baseline_is_protected_after_site_replacement():
    baseline = field("Human@example.test")
    assert (
        decision(field("parsed@example.test"), "parsed@example.test", baseline=baseline)
        == "difference"
    )
    assert decision(field(""), "proposed@example.test", baseline=baseline) == "difference"
    assert (
        decision(field("Human@EXAMPLE.TEST"), "other@example.test", baseline=baseline)
        == "difference"
    )
    assert decision(field("Human@EXAMPLE.TEST"), "Human@example.test", baseline=baseline) == "keep"


def test_only_blanks_are_safe_without_user_choice_or_parser_origin_proof():
    assert decision(field(), "new@example.test", baseline=field()) == "fill"
    assert (
        decision(field("valid@example.test"), "new@example.test", baseline=field()) == "difference"
    )
    assert decision(field("broken"), "new@example.test", baseline=field()) == "difference"
    assert (
        decision(field("broken", parser_completed=True), "new@example.test", baseline=field())
        == "difference"
    )
    assert (
        decision(
            field("broken", parser_completed=True), "new@example.test", baseline=field("broken")
        )
        == "difference"
    )
    assert (
        decision(field("broken", parser_completed=True), "also broken", baseline=field())
        == "difference"
    )
    assert decision(field(""), "", baseline=field()) == "keep"


def test_unknown_parser_needs_spaced_quiet_samples_and_preserves_baseline():
    state = sample(None, observed("human@example.test"), binding=BINDING, now=0)
    original = deepcopy(state)
    assert state["parser"]["status"] == "waiting"
    assert (
        sample(state, observed("human@example.test"), binding=BINDING, now=0.1)["parser"]["samples"]
        == 1
    )
    for now in [0.25, 0.5, 0.75]:
        state = sample(state, observed("human@example.test"), binding=BINDING, now=now)
        assert state["parser"]["status"] == "waiting"
    state = sample(state, observed("human@example.test"), binding=BINDING, now=1)
    assert state["parser"]["status"] == "stable"
    assert original["parser"]["samples"] == 1
    state["choices"] = {"email": "current"}
    changed = sample(state, observed("parsed@example.test", "active"), binding=BINDING, now=1.25)
    assert changed["baseline"]["email"]["value"] == "human@example.test"
    assert changed["snapshot"]["fields"][0]["value"] == "parsed@example.test"
    assert changed["revision"] == state["revision"] + 1
    assert changed["choices"] == state["choices"]
    assert changed["parser"]["status"] == "waiting"


def test_explicit_completion_is_not_instant_or_blocked_by_unrelated_validation():
    state = None
    for now in [0, 0.25, 0.5]:
        state = sample(
            state,
            observed(
                "x@example.test",
                "complete",
                validation_errors=[{"id": "later", "message": "Required"}],
            ),
            binding=BINDING,
            now=now,
        )
    assert state["parser"]["status"] == "stable"
    assert state["snapshot"]["validation_errors"]


def test_active_and_unstable_timeout_are_explicit_failures():
    state = sample(None, observed(parser="active"), binding=BINDING, now=5)
    state = sample(state, observed(parser="active"), binding=BINDING, now=34.9)
    assert state["parser"]["status"] == "waiting"
    state = sample(state, observed(parser="active"), binding=BINDING, now=35)
    assert state["parser"]["status"] == "failed"
    assert state["parser"]["reason"] == "parser_unstable"
    failed = sample(None, observed(parser="failed"), binding=BINDING, now=0)
    assert failed["parser"]["status"] == "failed"
    assert failed["parser"]["reason"] == "parser_failed"


def test_binding_change_discards_choices_and_attachment_baseline():
    state = sample(
        None,
        observed("first@example.test", upload={"filename": "human.pdf"}),
        binding=BINDING,
        now=0,
    )
    state["choices"] = {"email": "current"}
    state["differences"] = [{"id": "email"}]
    state["upload_epoch"] = 2
    fresh = sample(
        state, observed("second@example.test"), binding={**BINDING, "step": "documents"}, now=1
    )
    assert fresh["baseline"]["email"]["value"] == "second@example.test"
    assert "choices" not in fresh
    assert "differences" not in fresh
    assert "upload_epoch" not in fresh
    assert fresh["revision"] == 1


def test_attachment_and_validity_changes_reset_stability_without_overwriting_baseline():
    first = {
        "fields": [{"id": "resume", "type": "file", "filename": "human.pdf", "file_sha256": "a"}],
        "parser": {"status": "unknown"},
    }
    state = sample(None, first, binding=BINDING, now=0)
    later = deepcopy(first)
    later["fields"][0]["filename"] = "generated.pdf"
    later["fields"][0]["file_sha256"] = "b"
    changed = sample(state, later, binding=BINDING, now=0.5)
    assert changed["attachment_baseline"][0]["filename"] == "human.pdf"
    assert changed["parser"]["samples"] == 1
    assert changed["snapshot_sha256"] != state["snapshot_sha256"]


def test_phone_extension_and_nonempty_local_domain_are_not_invented_parse_errors():
    phone = {
        "id": "phone",
        "type": "tel",
        "value": "+1 415 555 0123 ext 12",
        "parser_completed": True,
    }
    assert decision(phone, "+14155550123", baseline={**phone, "value": ""}) == "difference"
    assert (
        decision(
            field("user@localhost", parser_completed=True), "user@example.test", baseline=field()
        )
        == "difference"
    )


def test_upload_receipt_baseline_is_an_independent_immutable_capture():
    upload = {"filename": "human.pdf", "state": "complete"}
    state = sample(None, observed(upload=upload), binding=BINDING, now=0)
    upload["filename"] = "new.pdf"
    next_state = sample(state, observed(upload=upload), binding=BINDING, now=0.25)
    assert next_state["upload_baseline"] == {"filename": "human.pdf", "state": "complete"}


def test_unicode_domain_is_not_folded_into_a_different_address():
    assert not equivalent({"type": "email"}, "user@straße.example", "user@strasse.example")
