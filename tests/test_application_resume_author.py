"""Actual JSON author Interfaces overlap with letter calls using controlled runners."""

import json
import threading
from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_canonical_career_sources import canonical as canonical
from test_cover_letter_content import phase
from test_j08_flow_combination import json_flow as json_flow
from test_j08_flow_combination import start_json_writing

from career_evidence_graph.application_resume_author import execute_content_generation
from career_evidence_graph.application_resume_content import validate_plan
from career_evidence_graph.career_portal_data import PortalDataError


def response(output):
    return SimpleNamespace(
        structured_result=output, model_dump=lambda **_: {"structured_result": output}
    )


def scoped_output(context):
    assignment = context["assignment"]
    return {
        "schema_version": "experience-writing/v1",
        "assignment_revision": context["input_revision"],
        "experience_id": assignment["experience_id"],
        "candidate_id": assignment["candidate_id"],
        "status": "complete",
        "items": [
            {
                "id": "item-" + assignment["experience_id"],
                "text": assignment["experience"]["facts"][0]["text"],
                "fact_refs": assignment["allowed_fact_refs"][:1],
            }
        ],
    }


def author_output(request):
    if request["role"] == "plan":
        # The planner returns only its choices; the program rebuilds assignments.
        plan = validate_plan(request["context"]["content_plan"]).model_dump(mode="json")
        return {
            **{key: plan[key] for key in ("headline", "summary", "skills") if key in plan},
            "assignments": [
                {
                    "experience_id": row["experience_id"],
                    "writing_requirements": row["writing_requirements"],
                }
                for row in plan["assignments"]
            ],
        }
    if request["role"].startswith("experience-"):
        # The writer's union schema is answered inside "result".
        return {"result": scoped_output(request["context"])}
    return {"passed": True, "issues": [], "content_patch": None, "rewrite_experience_ids": []}


@pytest.mark.parametrize("json_flow", [{"automatic_resume_author": True}], indirect=True)
def test_actual_scoped_resume_writer_overlaps_whole_letter_writer(json_flow):
    case = json_flow
    entered = threading.Barrier(3)
    release = threading.Event()
    calls = []
    resume_waited = False

    def runner(config, prompt, **kwargs):
        nonlocal resume_waited
        if "automatic-authors" in config.workspace.parts:
            request = json.loads(prompt.split("\n", 1)[1])
            role = request["role"]
            calls.append(role)
            if role.startswith("experience-") and not resume_waited:
                resume_waited = True
                entered.wait(timeout=5)
                assert release.wait(5)
            return response(author_output(request))
        if "material-consistency" in config.workspace.parts:
            return response({"consistent": True, "issues": []})
        if phase(prompt) == "review-schema.json":
            calls.append("letter-review")
            return response({"supported": True, "reason": "Synthetic sources preserved."})
        calls.append("letter-author")
        entered.wait(timeout=5)
        assert release.wait(5)
        return response(
            {
                "language": "en",
                "paragraphs": [
                    {
                        "id": "motivation",
                        "kind": "motivation",
                        "text": "I would like to contribute to reliable technical systems.",
                        "source_ids": [],
                        "source_quotes": [],
                    }
                ],
            }
        )

    case.store.model_runner = runner
    task = case.flow.create(case.job["id"], case.job["revision"])
    case.flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(case.flow, task["id"], lambda row: row["status"] == "analysis_ready")
    task = case.flow.prepare_automatic_materials(
        task["id"], task["revision"], project_root=str(case.project), main="main.tex"
    )
    try:
        case.flow.start(task["id"], task["revision"], "resume")
        entered.wait(timeout=5)
        current = case.flow.task_snapshot(task["id"])
        assert current["cover_letter"]["status"] == "running"
        assert current["stages"]["resume"]["status"] == "running"
        release.set()
        done = wait_for(
            case.flow,
            task["id"],
            lambda row: row["status"] == "draft_ready" and row["cover_letter"]["status"] == "ready",
        )
        assert done["draft_id"]
        assert calls.count("plan") == 1
        assert len([role for role in calls if role.startswith("experience-")]) == 2
        assert calls.count("review") == 1
        assert calls.count("letter-author") == calls.count("letter-review") == 1
    finally:
        release.set()


def test_an_author_call_without_answer_is_resent_alone(json_flow):
    """Model Call Record: only the unanswered call is sent again; answered ones are kept."""
    case = json_flow
    task = start_json_writing(case)
    calls, lost = [], []

    def runner(config, prompt, **kwargs):
        request = json.loads(prompt.split("\n", 1)[1])
        calls.append(request["role"])
        if request["role"].startswith("experience-") and not lost:
            lost.append(request["role"])
            raise TimeoutError("lost response")
        return response(author_output(request))

    identifier = task["experience_handoff"]["id"]
    with pytest.raises(PortalDataError) as first:
        execute_content_generation(case.store, identifier, runner=runner)
    assert first.value.code == "resume_author_no_answer"
    before = list(calls)
    # A receipt-only check never sends the missing call.
    with pytest.raises(PortalDataError) as checked:
        execute_content_generation(case.store, identifier, runner=runner, allow_calls=False)
    assert checked.value.code == "resume_author_needs_recheck"
    assert calls == before
    result = execute_content_generation(case.store, identifier, runner=runner)
    assert result["kind"] == "draft"
    resent = calls[len(before) :]
    assert "plan" not in resent
    assert resent[0] == lost[0]
    assert resent.count(lost[0]) == 1


def test_an_author_reservation_saved_before_model_call_record_is_resent(json_flow):
    """A legacy intent.json without a result no longer blocks: that one call is resent."""
    case = json_flow
    task = start_json_writing(case)
    calls, lost = [], []

    def runner(config, prompt, **kwargs):
        request = json.loads(prompt.split("\n", 1)[1])
        calls.append(request["role"])
        if request["role"].startswith("experience-") and not lost:
            lost.append(config.workspace)
            raise TimeoutError("lost response")
        return response(author_output(request))

    identifier = task["experience_handoff"]["id"]
    with pytest.raises(PortalDataError):
        execute_content_generation(case.store, identifier, runner=runner)
    directory = lost[0]
    prompt = json.loads((directory / "prompt.json").read_text())["prompt"]
    # Rewrite the record as the old reservation: intent saved, no result.
    (directory / "intent.json").write_text(
        json.dumps(
            {
                "binding": directory.name.rsplit("-", 1)[0],
                "request": json.loads(prompt.split("\n", 1)[1]),
                "schema": json.loads((directory / "schema.json").read_text()),
            }
        )
    )
    (directory / "prompt.json").unlink()
    (directory / "result.json").unlink()
    before = list(calls)
    result = execute_content_generation(case.store, identifier, runner=runner)
    assert result["kind"] == "draft"
    assert calls[len(before)] == calls[len(before) - 1]
    assert "plan" not in calls[len(before) :]


def test_adoption_response_loss_reuses_complete_authors_and_review(json_flow, monkeypatch):
    from career_evidence_graph import application_experience_latex as generation

    case = json_flow
    task = start_json_writing(case)
    calls = []

    def runner(config, prompt, **kwargs):
        request = json.loads(prompt.split("\n", 1)[1])
        calls.append(request["role"])
        return response(author_output(request))

    original = generation.adopt_generation
    lost = []

    def lose_once(store, identifier):
        result = original(store, identifier)
        if not lost:
            lost.append(True)
            raise OSError("adoption response lost after durable save")
        return result

    monkeypatch.setattr(generation, "adopt_generation", lose_once)
    identifier = task["experience_handoff"]["id"]
    with pytest.raises(PortalDataError) as error:
        execute_content_generation(case.store, identifier, runner=runner)
    assert error.value.code == "resume_author_needs_recheck"
    before = list(calls)
    result = execute_content_generation(case.store, identifier, runner=runner, allow_calls=False)
    assert result["kind"] == "draft"
    assert result["generation_contract"] == "content-writing/v1"
    assert calls == before


def test_pause_during_scoped_author_stops_new_calls_and_resumes_only_missing_work(json_flow):
    from career_evidence_graph import application_experience_latex as generation

    case = json_flow
    task = start_json_writing(case)
    identifier = task["experience_handoff"]["id"]
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    calls, failures = [], []

    def runner(config, prompt, **kwargs):
        request = json.loads(prompt.split("\n", 1)[1])
        calls.append(request["role"])
        if request["role"].startswith("experience-") and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return response(author_output(request))

    def execute():
        try:
            execute_content_generation(
                case.store, identifier, runner=runner, admit_call=lambda: not stopped.is_set()
            )
        except PortalDataError as error:
            failures.append(error.code)

    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(5)
        stopped.set()
        release.set()
        thread.join(5)
        assert not thread.is_alive()
        assert failures == ["resume_author_paused"]
        before = list(calls)
        assert before[0] == "plan" and len(before) == 2
        state = generation.generation_state(case.store, identifier)
        assert len(state["completed_experience_ids"]) == 1
        with pytest.raises(PortalDataError) as paused:
            execute_content_generation(
                case.store, identifier, runner=runner, admit_call=lambda: False
            )
        assert paused.value.code == "resume_author_paused"
        assert calls == before
        with case.flow.applications.write_lock():
            flow_state = case.flow._load()
            current = case.flow._task(flow_state, task["id"])
            current["stages"]["resume"].update(status="failed", error_code="resume_author_paused")
            current["status"] = "failed"
            case.flow._save(flow_state)
        case.flow.callbacks["resume"] = lambda request: execute_content_generation(
            case.store, identifier, runner=runner, admit_call=lambda: True
        )
        current = case.flow.task_snapshot(task["id"])
        case.flow.start(task["id"], current["revision"], "resume", retry=True)
        resumed = wait_for(case.flow, task["id"], lambda row: row["status"] == "draft_ready")
        assert resumed["draft_id"]
        assert calls.count("plan") == 1
        assert len([role for role in calls if role.startswith("experience-")]) == 2
        assert calls.count("review") == 1
    finally:
        release.set()
        thread.join(5)


def test_resume_prompts_keep_job_fit_and_agent_assistance_out_of_the_review():
    """2026-11-08 (finnova): the review failed a resume on German A2 versus C1, then
    patched in "agent-assisted" and returned passed with issues."""
    from career_evidence_graph.application_experience_content import (
        REVIEW_INSTRUCTIONS,
        WRITER_INSTRUCTIONS,
    )

    assert "unmet JD requirement such as a language level" in REVIEW_INSTRUCTIONS
    assert "languages line are fixed template text" in REVIEW_INSTRUCTIONS
    assert "passed true means issues is empty" in REVIEW_INSTRUCTIONS
    for instructions in (REVIEW_INSTRUCTIONS, WRITER_INSTRUCTIONS):
        assert "coding-agent" in instructions and "internal records" in instructions


def test_rewrite_keeps_reviewer(json_flow):
    """2026-11-08 (finnova): the review after a local rewrite came with a new reviewer id,
    which the generation refused, and the resume stopped."""
    case = json_flow
    task = start_json_writing(case)
    reviews = []

    written = []

    def runner(config, prompt, **kwargs):
        request = json.loads(prompt.split("\n", 1)[1])
        if request["role"].startswith("experience-"):
            output = scoped_output(request["context"])
            eid = request["context"]["assignment"]["experience_id"]
            if eid in written:
                # A real rewrite changes the wording, so the next review sees a new draft.
                output["items"][0]["id"] += "-rewritten"
            written.append(eid)
            return response({"result": output})
        if request["role"] != "review":
            return response(author_output(request))
        reviews.append(request["context"])
        if len(reviews) == 1:
            first = request["context"]["writing_plan"]["assignments"][0]["experience_id"]
            return response(
                {
                    "passed": False,
                    "issues": ["Rewrite the first experience's scope."],
                    "content_patch": None,
                    "rewrite_experience_ids": [first],
                }
            )
        return response(author_output(request))

    identifier = task["experience_handoff"]["id"]
    result = execute_content_generation(case.store, identifier, runner=runner)
    assert result["kind"] == "draft"
    assert len(reviews) == 2
