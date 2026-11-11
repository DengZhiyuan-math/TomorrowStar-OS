"""Explicitly inspecting a paused original page is separate from final form readiness."""

from copy import deepcopy
from pathlib import Path

import pytest
from test_worker_stability import retained_live_page as retained_live_page

from career_evidence_graph.application_form_state import sample
from career_evidence_graph.career_portal_data import PortalDataError


def retain_form(server, *, status="needs_recheck", condition="unknown_intent"):
    state = server.store.load()
    job = state["jobs"][0]
    observed = {
        "fields": [
            {
                "id": "sponsorship",
                "type": "text",
                "question": "Sponsorship",
                "required": True,
                "value": "",
                "valid": False,
            }
        ],
        "document_token": "retained-document",
        "parser": {"status": "complete"},
    }
    binding = {
        "run_id": state["runtime"]["id"],
        "page_id": job["page_observation"]["page_id"],
        "document_token": observed["document_token"],
        "step": job["job_url"],
    }
    form = None
    for moment in (0, 0.25, 0.5):
        form = sample(form, observed, binding=binding, now=moment)
    if condition == "parser_waiting":
        form["parser"]["status"] = "waiting"
    elif condition == "validation_error":
        form["snapshot"]["validation_errors"] = [{"id": "sponsorship", "message": "Required"}]
    elif condition == "intervention":
        form["intervention_pending"] = True
    elif condition == "difference":
        form["differences"] = [
            {"id": "pending-choice", "field_id": "sponsorship", "important": True}
        ]
    job.update(status=status, form_state=form)
    server.store.save(state)
    return deepcopy(state)


@pytest.mark.parametrize("status", ["needs_input", "needs_recheck"])
@pytest.mark.parametrize(
    "condition",
    ["unknown_intent", "parser_waiting", "validation_error", "intervention", "difference"],
)
def test_partial_review_retains_unknown_intent_and_unfinished_form(
    retained_live_page, status, condition
):
    server, identifier = retained_live_page
    before = retain_form(server, status=status, condition=condition)
    result = server.request("review", {"application_id": identifier, "acknowledge": True})
    current = server.store.load()["jobs"][0]
    assert current["status"] == status
    assert current["intent"] == before["jobs"][0]["intent"]
    assert current["form_state"] == before["jobs"][0]["form_state"]
    assert current["manual_intervention"] is True and current["handed_off"] is True
    assert current["handoff"]["status"] == "pending"
    assert current["handoff"]["source"] == "user_requested_handoff"
    assert current["handoff"]["human_reviewed"] is False
    assert result["commands"] == [{"action": "review", "id": identifier}]
    assert result["control"] == "paused" and server.process is None


@pytest.mark.parametrize(
    "fault,code",
    [("ready", "form_review_pending"), ("unacknowledged", "not_ready"), ("offline", "not_ready")],
)
def test_final_review_or_unacknowledged_partial_keeps_its_form_gate(
    retained_live_page, fault, code
):
    server, identifier = retained_live_page
    retain_form(server, status="ready_for_review" if fault == "ready" else "needs_recheck")
    if fault == "offline":
        server.live = False
    before = server.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        server.request(
            "review", {"application_id": identifier, "acknowledge": fault != "unacknowledged"}
        )
    assert error.value.code == code
    assert server.store.path.read_bytes() == before


@pytest.mark.parametrize(
    "fault,code",
    [
        ("single", "single_binding_invalid"),
        ("target", "target_changed"),
        ("pdf", "file_changed"),
        ("answer", "answer_changed"),
    ],
)
def test_partial_review_still_checks_material_target_and_answer_identity(
    retained_live_page, monkeypatch, fault, code
):
    server, identifier = retained_live_page
    retain_form(server)
    if fault == "single":

        def fail_single(*_args, **_options):
            raise PortalDataError(code, "Synthetic changed single binding", 409)

        monkeypatch.setattr(server.store, "check_single", fail_single)
    elif fault == "target":

        def fail_target(*_args, **_options):
            raise PortalDataError(code, "Synthetic changed application target", 409)

        monkeypatch.setattr(
            "career_evidence_graph.application_worker.validate_application_target", fail_target
        )
    else:
        state = server.store.load()
        job = state["jobs"][0]
        if fault == "pdf":
            path = Path(job["file_path"])
            path.write_bytes(path.read_bytes() + b"changed")
        else:
            answer = server.store.answers.put_answer(
                {
                    "question": "Full name",
                    "value": "Synthetic Person",
                    "state": "confirmed",
                    "scope": {},
                }
            )
            job["answer_refs"] = [{"key": answer["key"], "revision": "0" * 64, "field_id": "name"}]
            server.store.save(state)
    before = server.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        server.request("review", {"application_id": identifier, "acknowledge": True})
    assert error.value.code == code
    assert server.store.path.read_bytes() == before
