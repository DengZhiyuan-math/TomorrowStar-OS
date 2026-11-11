"""Bound candidate preparation consumes the exact retained Resume version."""

import json
from copy import deepcopy

import pytest
from test_application_flow import wait_for
from test_application_resume_author import author_output, response
from test_canonical_career_sources import canonical as canonical
from test_j08_flow_combination import json_flow as json_flow
from test_j08_flow_combination import start_json_writing

from career_evidence_graph.career_portal_data import PortalDataError


def test_retained_content_candidate_reuses_version_without_new_inputs_or_author(json_flow):
    case = json_flow
    task = start_json_writing(case)
    case.store.model_runner = lambda config, prompt, **kwargs: response(
        author_output(json.loads(prompt.split("\n", 1)[1]))
    )
    draft = case.store.execute_generation(task["experience_handoff"])
    before = sorted(path.name for path in case.store.root.iterdir())
    request = deepcopy(task)
    request["material_update"] = {
        "old": deepcopy(task),
        "inputs": deepcopy(task["inputs"]),
        "editable_draft": draft,
    }

    def forbidden(*args, **kwargs):
        pytest.fail("Retained complete content must not reload facts, run an author or compile")

    case.store.model_runner = case.store.exporter = forbidden
    result, _ = case.store.prepare_bound_draft(
        request, source_provider=forbidden, information_provider=forbidden
    )
    assert result == draft
    assert sorted(path.name for path in case.store.root.iterdir()) == before
    assert case.store.read(draft["id"]) == draft


@pytest.mark.parametrize("method", ["prepare_bound_draft", "prepare_bound_edit"])
def test_bound_preparation_checks_retained_version_hash(json_flow, method):
    case = json_flow
    task = start_json_writing(case)
    case.store.model_runner = lambda config, prompt, **kwargs: response(
        author_output(json.loads(prompt.split("\n", 1)[1]))
    )
    draft = case.store.execute_generation(task["experience_handoff"])
    request = deepcopy(task)
    request["draft_id"] = draft["id"]
    request["draft_sha256"] = "0" * 64
    request["material_update"] = {
        "old": deepcopy(request),
        "inputs": deepcopy(task["inputs"]),
    }

    def forbidden(*args, **kwargs):
        pytest.fail("Changed retained material must fail before providers/author/build")

    with pytest.raises(PortalDataError) as error:
        getattr(case.store, method)(
            request, source_provider=forbidden, information_provider=forbidden
        )
    assert error.value.code == "flow_draft_changed"


def test_resume_rejects_other_app_retained_version_with_equal_inputs(json_flow):
    case = json_flow
    original_runner = case.store.model_runner
    first = start_json_writing(case)
    case.store.model_runner = lambda config, prompt, **kwargs: response(
        author_output(json.loads(prompt.split("\n", 1)[1]))
    )
    draft = case.store.execute_generation(first["experience_handoff"])
    # A second real application has identical JD/fact/configuration inputs but a distinct ID.
    job = case.applications.create_application(
        {
            "company": case.job["company"],
            "role_title": case.job["role_title"],
            "job_description": case.job["job_description"],
            "url": "https://jobs.lever.co/synthetic/22222222-1234-1234-1234-123456789012",
        }
    )
    case.store.model_runner = original_runner
    second = start_json_writing(case, job)
    case.store.model_runner = lambda config, prompt, **kwargs: response(
        author_output(json.loads(prompt.split("\n", 1)[1]))
    )
    second_draft = case.store.execute_generation(second["experience_handoff"])
    case.store.model_runner = original_runner
    case.flow.request(
        "resume-experience-generation",
        {
            "task_id": second["id"],
            "task_revision": second["revision"],
            "generation_id": second["experience_handoff"]["id"],
        },
    )
    second = wait_for(
        case.flow, second["id"], lambda row: row["status"] in {"draft_ready", "failed"}
    )
    second = wait_for(
        case.flow,
        second["id"],
        lambda row: row.get("material_consistency", {}).get("status") not in {"queued", "running"},
    )
    assert second["draft_id"] == second_draft["id"]
    assert first["application_id"] != second["application_id"]
    assert first["analysis_id"] != second["analysis_id"]
    assert draft["task_inputs"] == second["inputs"]
    request = deepcopy(second)
    request["material_update"] = {
        "old": deepcopy(second),
        "inputs": deepcopy(second["inputs"]),
        "editable_draft": draft,
    }

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid binding must fail before providers/author/build")

    with pytest.raises(PortalDataError):
        result, _ = case.store.prepare_bound_draft(
            request, source_provider=forbidden, information_provider=forbidden
        )
        assert result["application_id"] == first["application_id"]
        assert result["analysis_binding"]["analysis_id"] == first["analysis_id"]
