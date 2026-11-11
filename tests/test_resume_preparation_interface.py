"""Resume owns fixed preparation, adopted versions and their immutable references."""

import json
from copy import deepcopy

import pytest
from test_application_resume_author import author_output, response
from test_canonical_career_sources import canonical as canonical
from test_j08_flow_combination import json_flow as json_flow
from test_j08_flow_combination import start_json_writing


def test_prepare_resumes_saved_handoff_without_reloading_sources(json_flow):
    case = json_flow
    task = start_json_writing(case)
    fixed = case.flow.fixed_writing_inputs(task)
    calls = []

    def runner(config, prompt, **kwargs):
        request = json.loads(prompt.split("\n", 1)[1])
        calls.append(request["role"])
        return response(author_output(request))

    def forbidden(*args):
        pytest.fail("Saved handoff continuation must not reload inputs or search history")

    case.store.model_runner = runner
    arguments = dict(
        source_provider=forbidden,
        information_provider=forbidden,
        reuse_tasks=forbidden,
        complete_materials=True,
        automatic_author=True,
        admit_call=lambda: True,
    )
    result = case.store.prepare(task, fixed, **arguments)
    assert result["kind"] == "draft"
    assert result["generation_contract"] == "content-writing/v1"
    assert result["application_id"] == task["application_id"]
    assert "Fixed Template Person" in result["latex_source"]
    before = list(calls)
    replay = case.store.prepare(task, fixed, **arguments)
    assert replay == result
    assert calls == before
    assert case.store.read(result) == result


def test_prepare_rejects_changed_task_inputs_before_authors(json_flow):
    from career_evidence_graph.career_portal_data import PortalDataError

    case = json_flow
    task = start_json_writing(case)
    fixed = case.flow.fixed_writing_inputs(task)
    changed = deepcopy(task)
    changed["inputs"]["sources_revision"] = "changed"
    calls = []
    case.store.model_runner = lambda *args, **kwargs: calls.append("unexpected")
    with pytest.raises(PortalDataError) as rejected:
        case.store.prepare(
            changed,
            fixed,
            source_provider=lambda _: pytest.fail("No source reload"),
            information_provider=lambda _: pytest.fail("No information reload"),
            reuse_tasks=lambda: pytest.fail("No history search"),
            complete_materials=True,
            automatic_author=True,
        )
    assert rejected.value.code == "resume_generation_reference_mismatch"
    assert calls == []


def test_prepared_candidate_cannot_replace_archived_wording(json_flow):
    from career_evidence_graph.career_portal_data import PortalDataError

    case = json_flow
    task = start_json_writing(case)

    def runner(config, prompt, **kwargs):
        return response(author_output(json.loads(prompt.split("\n", 1)[1])))

    case.store.model_runner = runner
    result = case.store.execute_generation(task["experience_handoff"])
    forged = deepcopy(result)
    forged["latex_source"] = "Changed wording without a saved successor"
    with pytest.raises(PortalDataError) as rejected:
        case.store.validate_prepared(task, forged)
    assert rejected.value.code == "flow_draft_mismatch"
    assert case.store.read(result)["latex_source"] == result["latex_source"]


def test_read_rejects_foreign_material_reference_without_model_or_build(json_flow):
    from career_evidence_graph.career_portal_data import PortalDataError

    case = json_flow
    task = start_json_writing(case)
    case.store.model_runner = lambda config, prompt, **kwargs: response(
        author_output(json.loads(prompt.split("\n", 1)[1]))
    )
    material = case.store.execute_generation(task["experience_handoff"])

    def forbidden(*args, **kwargs):
        pytest.fail("Reading a saved version cannot run an author or compiler")

    case.store.model_runner = case.store.exporter = forbidden
    for field, value, code in (
        ("application_id", "f" * 32, "flow_draft_mismatch"),
        ("draft_sha256", "f" * 64, "flow_draft_changed"),
        ("task_inputs", {"sources_revision": "foreign"}, "flow_draft_mismatch"),
        ("content_revision", "f" * 64, "flow_draft_mismatch"),
    ):
        reference = {"id": material["id"], field: value}
        with pytest.raises(PortalDataError) as rejected:
            case.store.read(reference)
        assert rejected.value.code == code
    assert case.store.read(material["id"]) == material
