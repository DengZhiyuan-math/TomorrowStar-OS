"""Human letter successors cross the Flow interface, preserving its original history."""

from copy import deepcopy

import pytest
from test_application_worker import service as service
from test_cover_letter_delivery import modern as modern
from test_cover_letter_edit import editable as editable
from test_cover_letter_edit import letter_rows
from test_supplemental_material_module import prepared as prepared

from career_evidence_graph.application_cover_letter import edit_cover_letter
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


def test_flow_adopts_a_human_letter_successor_once(editable):
    flow, _, old, payload, state = editable
    content = edit_cover_letter(
        old["letter_content"],
        "Helped build Python services for analysts.",
        expected_revision=old["content_revision"],
        edit_id=payload["request_id"],
    )
    source = deepcopy(old["source_binding"]) | {"manual_edit": True}
    result = flow.adopt_cover_letter_successor(
        payload["task_id"],
        expected_attempt_id=old["letter_attempt_id"],
        expected_content_revision=old["content_revision"],
        content=content,
        source_binding=source,
        request_id=payload["request_id"],
    )
    assert result["content_revision"] == content["revision"]
    assert result["actor"] == "user"
    assert letter_rows(state["tasks"][0])[-2]["content_revision"] == old["content_revision"]
    before = deepcopy(state)
    flow.adopt_cover_letter_successor(
        payload["task_id"],
        expected_attempt_id=old["letter_attempt_id"],
        expected_content_revision=old["content_revision"],
        content=content,
        source_binding=source,
        request_id=payload["request_id"],
    )
    assert state == before


@pytest.mark.parametrize(
    "fault", ["parent_revision", "foreign_application", "source_scope", "unprotected"]
)
def test_flow_rejects_unbound_letter_successors_without_changing_history(editable, fault):
    flow, _, old, payload, state = editable
    content = edit_cover_letter(
        old["letter_content"],
        "Helped build Python services for analysts.",
        expected_revision=old["content_revision"],
        edit_id=payload["request_id"],
    )
    expected = old["content_revision"]
    source = deepcopy(old["source_binding"]) | {"manual_edit": True}
    if fault == "parent_revision":
        expected = "wrong-parent-revision"
    elif fault == "foreign_application":
        content["application_id"] = "another-application"
    elif fault == "source_scope":
        source["application"]["role_title"] = "Another role"
    else:
        content["paragraphs"][0]["protected"] = False
    content["revision"] = digest({key: row for key, row in content.items() if key != "revision"})
    before = deepcopy(state)
    with pytest.raises(PortalDataError) as error:
        flow.adopt_cover_letter_successor(
            payload["task_id"],
            expected_attempt_id=old["letter_attempt_id"],
            expected_content_revision=expected,
            content=content,
            source_binding=source,
            request_id=payload["request_id"],
        )
    assert error.value.code == "material_changed"
    assert state == before


def test_letter_edit_identity_cannot_replace_an_already_adopted_body(editable):
    flow, _, old, payload, state = editable
    content = edit_cover_letter(
        old["letter_content"],
        "Helped build Python services for analysts.",
        expected_revision=old["content_revision"],
        edit_id=payload["request_id"],
    )
    source = deepcopy(old["source_binding"]) | {"manual_edit": True}
    request = {
        "expected_attempt_id": old["letter_attempt_id"],
        "expected_content_revision": old["content_revision"],
        "source_binding": source,
        "request_id": payload["request_id"],
    }
    flow.adopt_cover_letter_successor(payload["task_id"], content=content, **request)
    another = edit_cover_letter(
        old["letter_content"],
        "Different human body.",
        expected_revision=old["content_revision"],
        edit_id=payload["request_id"],
    )
    before = deepcopy(state)
    with pytest.raises(PortalDataError):
        flow.adopt_cover_letter_successor(payload["task_id"], content=another, **request)
    assert state == before
