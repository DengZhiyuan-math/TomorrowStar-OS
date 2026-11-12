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
def test_actual_scoped_resume_writer_runs_before_whole_letter_writer(json_flow):
    """Résumé first, then the letter, on one Flow queue (unified material lifecycle)."""
    case = json_flow
    calls = []

    def runner(config, prompt, **kwargs):
        if "automatic-authors" in config.workspace.parts:
            request = json.loads(prompt.split("\n", 1)[1])
            calls.append(request["role"])
            return response(author_output(request))
        if "material-consistency" in config.workspace.parts:
            return response({"consistent": True, "issues": []})
        if phase(prompt) == "review-schema.json":
            calls.append("letter-review")
            return response({"supported": True, "reason": "Synthetic sources preserved."})
        calls.append("letter-author")
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
    case.flow.start(task["id"], task["revision"], "resume")
    drafted = wait_for(case.flow, task["id"], lambda row: row["status"] == "draft_ready")
    assert "letter-author" not in calls and "letter" not in drafted["stages"]
    case.flow.prepare(task["id"], drafted["revision"])
    done = wait_for(
        case.flow, task["id"], lambda row: row["stages"]["letter"]["status"] == "complete"
    )
    assert done["status"] == "draft_ready" and done["draft_id"] == drafted["draft_id"]
    assert calls.count("plan") == 1
    assert len([role for role in calls if role.startswith("experience-")]) == 2
    assert calls.count("review") == 1
    assert calls.count("letter-author") == calls.count("letter-review") == 1
    assert calls.index("letter-author") > calls.index("review")


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


def test_an_author_input_over_the_cli_limit_stops_without_resend(json_flow):
    """2026-11-10: a 1.15 M-character planner prompt was refused before any model turn."""
    from career_evidence_graph.codex_cli import CodexCLIError

    case = json_flow
    task = start_json_writing(case)
    calls = []

    def runner(config, prompt, **kwargs):
        calls.append(prompt)
        error = CodexCLIError("Codex CLI failed")
        error.redacted_stderr = 'turn/start failed: {"input_error_code":"input_too_large"}'
        raise error

    identifier = task["experience_handoff"]["id"]
    with pytest.raises(PortalDataError) as refused:
        execute_content_generation(case.store, identifier, runner=runner)
    assert refused.value.code == "resume_author_too_large"
    assert len(calls) == 1


def test_the_planner_context_omits_each_requirements_source_texts(json_flow):
    from career_evidence_graph import application_experience_latex as generation

    case = json_flow
    task = start_json_writing(case)
    context = generation.generation_context(case.store, task["experience_handoff"]["id"])
    assert context["requirements"]
    assert all("sources" not in row for row in context["requirements"])
    # Each delivered experience comes with the requirements its sources support.
    assert set(context["experience_support"]) == {
        row["experience_id"] for row in context["content_plan"]["assignments"]
    }


def test_experience_support_lists_supported_requirements_and_empty_for_none():
    """2026-11-10 (Harmattan AI): an experience that supported no requirement led."""
    from career_evidence_graph.application_experience_latex import experience_support

    payload = {
        "content_plan": {
            "assignments": [
                {"experience_id": "a", "experience": {"candidate_id": "exp-a"}},
                {"experience_id": "b", "candidate_id": "exp-b", "experience": {}},
            ]
        },
        "requirements": [
            {
                "importance": "required",
                "fit_score": 90,
                "citations": [{"source_id": "s-a"}],
                # Retrieved for this requirement but not cited by the match.
                "sources": [
                    {"source_id": "s-a", "candidate_id": "exp-a"},
                    {"source_id": "s-b", "candidate_id": "exp-b"},
                ],
            },
            {
                "importance": "preferred",
                "fit_score": 5,
                "citations": [{"source_id": "s-x"}],
                "sources": [{"source_id": "s-x", "candidate_id": "exp-x"}],
            },
        ],
    }
    assert experience_support(payload) == {
        "a": [{"requirement": 0, "importance": "required", "fit_score": 90}],
        "b": [],
    }


def test_the_planner_keeps_at_most_five_experiences():
    from career_evidence_graph.application_resume_author import _plan_choices_schema

    schema = _plan_choices_schema({"properties": {}})
    assert schema["properties"]["assignments"]["maxItems"] == 5


def test_a_reviewed_plan_waits_and_written_feedback_plans_again(json_flow):
    """2026-11-12 (user decision): a high-value job's chosen experiences and order wait
    for the user before any experience is written; written feedback plans again."""
    from career_evidence_graph import application_experience_latex as generation
    from career_evidence_graph.application_resume_author import plan_overview
    from career_evidence_graph.validation.hashing import record_digest as digest

    case = json_flow
    task = start_json_writing(case)
    identifier = task["experience_handoff"]["id"]
    calls, approved = [], set()

    def runner(config, prompt, **kwargs):
        request = json.loads(prompt.split("\n", 1)[1])
        calls.append(request)
        return response(author_output(request))

    def review(plan):
        return digest(plan) in approved

    with pytest.raises(PortalDataError) as waiting:
        execute_content_generation(case.store, identifier, runner=runner, review_plan=review)
    assert waiting.value.code == "resume_plan_review_required"
    assert [row["role"] for row in calls] == ["plan"]
    assert "user_plan_feedback" not in calls[0]["context"]
    overview = plan_overview(generation.generation_context(case.store, identifier))
    plan = generation.generation_state(case.store, identifier)["writing_plan"]
    assert [row["experience_id"] for row in overview["chosen"]] == [
        row["experience_id"] for row in plan["assignments"]
    ]
    assert all(row["title"] for row in overview["chosen"])
    # The fixed writer instruction is not shown to the user (2026-11-12).
    from career_evidence_graph.application_writing import DEFAULT_WRITING_REQUIREMENT

    assert all(
        DEFAULT_WRITING_REQUIREMENT not in row["writing_requirements"] for row in overview["chosen"]
    )

    generation.request_replan(case.store, identifier, "Put the newest experience first.")
    with pytest.raises(PortalDataError) as again:
        execute_content_generation(case.store, identifier, runner=runner, review_plan=review)
    assert again.value.code == "resume_plan_review_required"
    assert [row["role"] for row in calls] == ["plan", "plan"]
    assert calls[1]["context"]["user_plan_feedback"] == ["Put the newest experience first."]
    # A later instruction keeps the earlier ones (2026-11-12: "remove ARC" was lost).
    generation.request_replan(case.store, identifier, "Keep at most four experiences.")
    with pytest.raises(PortalDataError):
        execute_content_generation(case.store, identifier, runner=runner, review_plan=review)
    assert calls[2]["context"]["user_plan_feedback"] == [
        "Put the newest experience first.",
        "Keep at most four experiences.",
    ]
    assert plan_overview(generation.generation_context(case.store, identifier))["feedback"] == [
        "Put the newest experience first.",
        "Keep at most four experiences.",
    ]

    approved.add(digest(generation.generation_state(case.store, identifier)["writing_plan"]))
    result = execute_content_generation(case.store, identifier, runner=runner, review_plan=review)
    assert result["kind"] == "draft"
    roles = [row["role"] for row in calls]
    assert roles.count("plan") == 3
    assert len([role for role in roles if role.startswith("experience-")]) == 2


@pytest.mark.parametrize("json_flow", [{"automatic_resume_author": True}], indirect=True)
def test_flow_continues_a_reviewed_plan_through_its_unadopted_handoff(json_flow):
    """2026-11-12, G-Research: the re-plan was saved, but Flow refused to restart the
    résumé stage because its handoff was not adopted yet."""
    from career_evidence_graph.validation.hashing import record_digest as digest

    case = json_flow
    approved = set()

    def runner(config, prompt, **kwargs):
        if "automatic-authors" in config.workspace.parts:
            return response(author_output(json.loads(prompt.split("\n", 1)[1])))
        return response({"supported": True, "reason": "Synthetic sources preserved."})

    case.store.model_runner = runner
    case.flow.callbacks["plan_allowed"] = lambda task_id, plan: digest(plan) in approved
    task = case.flow.create(case.job["id"], case.job["revision"])
    case.flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(case.flow, task["id"], lambda row: row["status"] == "analysis_ready")
    task = case.flow.prepare_automatic_materials(
        task["id"], task["revision"], project_root=str(case.project), main="main.tex"
    )
    case.flow.start(task["id"], task["revision"], "resume")
    waiting = wait_for(
        case.flow,
        task["id"],
        lambda row: row["stages"]["resume"].get("error_code") == "resume_plan_review_required",
    )
    progress = case.flow.progress(task["id"])
    assert progress["wait_reason"] == "resume_plan_review" and progress["can_continue"]
    plan = case.flow.resume_plan(task["id"])
    approved.add(digest(plan["plan"]))
    case.flow.continue_preparation(
        task["id"],
        waiting["revision"],
        request_id="confirm-plan",
        expected_attempt_id=waiting["stages"]["resume"]["attempt_id"],
    )
    assert wait_for(case.flow, task["id"], lambda row: row["status"] == "draft_ready")


def test_an_experience_a_requirement_cites_is_a_planner_candidate():
    """2026-11-12, G-Research: Volatility Wins backed five requirements, but the
    analysis's own selection left it out, so the planner never saw it."""
    from career_evidence_graph.application_writing import _resume_source_ids

    def fact(candidate):
        return {"record_context": {"fact_id": "f", "candidate_id": candidate}}

    packet = {
        "sources": {
            "selected": fact("exp-a"),
            "cited": fact("exp-volatility"),
            "context-only": {"record_context": {}},
        }
    }
    analysis = {
        "selected_source_ids": ["selected"],
        "requirements": [
            {"source_ids": ["cited", "selected"]},
            {"source_ids": ["context-only"]},
        ],
    }
    assert _resume_source_ids(analysis, packet) == ["selected", "cited"]
    assert _resume_source_ids({"requirements": analysis["requirements"]}, packet) is None
    assert _resume_source_ids({**analysis, "selected_source_ids": []}, packet) == []


def test_material_prompts_leave_out_data_volume(json_flow):
    """2026-11-12 (user decision): no "5,773-candidate comparison" or "129 trades"."""
    from career_evidence_graph import application_experience_latex as generation
    from career_evidence_graph.application_cover_letter import (
        WRITER_INSTRUCTIONS as LETTER_INSTRUCTIONS,
    )
    from career_evidence_graph.application_experience_content import (
        REVIEW_INSTRUCTIONS,
        WRITER_INSTRUCTIONS,
    )
    from career_evidence_graph.application_resume_content import DATA_VOLUME_RULE

    task = start_json_writing(json_flow)
    planner = generation.generation_context(json_flow.store, task["experience_handoff"]["id"])
    for instructions in (
        WRITER_INSTRUCTIONS,
        REVIEW_INSTRUCTIONS,
        LETTER_INSTRUCTIONS,
        planner["instructions"],
    ):
        assert DATA_VOLUME_RULE in instructions
    assert "numbers" not in " ".join(
        text
        for row in planner["content_plan"]["assignments"]
        for text in row["writing_requirements"]
    )


@pytest.mark.parametrize("json_flow", [{"automatic_resume_author": True}], indirect=True)
def test_flow_reviews_drafted_bullets_before_generating_the_resume(json_flow):
    """2026-11-12 (user decision): drafted bullets wait for the user; feedback rewrites
    one experience, edits stay as protected human wording, then the résumé is adopted."""
    from career_evidence_graph import application_experience_latex as generation

    case = json_flow
    requests = []

    def runner(config, prompt, **kwargs):
        if "automatic-authors" in config.workspace.parts:
            request = json.loads(prompt.split("\n", 1)[1])
            requests.append(request)
            return response(author_output(request))
        return response({"supported": True, "reason": "Synthetic sources preserved."})

    case.store.model_runner = runner
    case.flow.callbacks["wording_review_required"] = lambda task_id: True
    task = case.flow.create(case.job["id"], case.job["revision"])
    case.flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(case.flow, task["id"], lambda row: row["status"] == "analysis_ready")
    task = case.flow.prepare_automatic_materials(
        task["id"], task["revision"], project_root=str(case.project), main="main.tex"
    )
    case.flow.start(task["id"], task["revision"], "resume")

    def stopped(row):
        return row["stages"]["resume"].get("error_code") == "resume_wording_review_required"

    waiting = wait_for(case.flow, task["id"], stopped)
    assert case.flow.progress(task["id"])["wait_reason"] == "resume_wording_review"
    assert "review" not in [row["role"] for row in requests]
    review = case.flow.resume_wording(task["id"])
    first, second = review["experiences"]
    case.flow.revise_resume_wording(
        task["id"], first["experience_id"], feedback="Name the method instead."
    )
    before = len(requests)
    case.flow.continue_preparation(
        task["id"],
        waiting["revision"],
        request_id="rewrite-first",
        expected_attempt_id=waiting["stages"]["resume"]["attempt_id"],
    )
    waiting = wait_for(
        case.flow,
        task["id"],
        lambda row: (
            stopped(row)
            and row["stages"]["resume"]["attempt_id"] != waiting["stages"]["resume"]["attempt_id"]
        ),
    )
    rewritten = [row for row in requests[before:] if row["role"].startswith("experience-")]
    assert len(rewritten) == 1
    assert rewritten[0]["context"]["user_feedback"] == ["Name the method instead."]
    handoff = waiting["experience_handoff"]["id"]
    case.flow.approve_resume_wording(task["id"], first["experience_id"])
    assert not generation.wording_is_approved(case.store, handoff)
    item = second["items"][0]
    case.flow.revise_resume_wording(
        task["id"], second["experience_id"], items={item["id"]: "Hand-written bullet."}
    )
    edited = case.flow.resume_wording(task["id"])["experiences"][1]["items"][0]
    assert edited == {"id": item["id"], "text": "Hand-written bullet.", "edited": True}
    # Editing one experience leaves the other's confirmation in place.
    assert [row["confirmed"] for row in case.flow.resume_wording(task["id"])["experiences"]] == [
        True,
        False,
    ]
    case.flow.approve_resume_wording(task["id"], second["experience_id"])
    assert generation.wording_is_approved(case.store, handoff)
    case.flow.continue_preparation(
        task["id"],
        waiting["revision"],
        request_id="confirm-wording",
        expected_attempt_id=waiting["stages"]["resume"]["attempt_id"],
    )
    assert wait_for(case.flow, task["id"], lambda row: row["status"] == "draft_ready")
    from career_evidence_graph.application_experience_content import output

    state = generation._load(case.store, waiting["experience_handoff"]["id"])[1]
    assert state.get("adopted_draft")
    items = {
        experience["id"]: experience["items"]
        for experience in output(state)["resume_content"]["experiences"]
    }
    hand = items[second["experience_id"]][0]
    assert (hand["text"], hand["origin"], hand["protected"]) == (
        "Hand-written bullet.",
        "human",
        True,
    )
    assert all(item["protected"] for item in items[first["experience_id"]])
