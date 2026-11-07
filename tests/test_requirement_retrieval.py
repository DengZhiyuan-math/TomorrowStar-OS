"""Discovery reads every index page and cannot silently invent source bindings."""

import json
from copy import deepcopy
from functools import partial
from pathlib import Path

import pytest

from career_evidence_graph import application_retrieval as retrieval
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.codex_cli import CodexCLIError, run_codex_exec

REQUIREMENTS = [
    {
        "text": "Work with researchers from different disciplines.",
        "importance": "required",
        "hard_condition": False,
    },
    {
        "text": "Additional languages are an advantage.",
        "importance": "preferred",
        "hard_condition": False,
    },
]


@pytest.fixture
def inputs():
    return (
        {"id": "job", "revision": "v1", "job_description": "Research collaboration and languages."},
        {
            "revision": "sources-v1",
            "career_library": {
                "status": "available",
                "index_revision": "catalog-v1",
                "records": [
                    {
                        "candidate_id": "ordinary",
                        "title": "Software",
                        "summary": "Web service delivery",
                    },
                    {
                        "candidate_id": "unfamiliar",
                        "title": "Placement",
                        "summary": "Models of neural circuits in a biological research team",
                    },
                ],
            },
            "information_context": {"languages": ["French A1", "German A2"]},
        },
    )


def model_runner(callback, calls, schemas=None):
    import subprocess

    def process(argv, **kwargs):
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex synthetic\n", "")
        prompt = kwargs["input"]
        context = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
        calls.append(context)
        if schemas is not None:
            schemas.append(json.loads(Path(argv[argv.index("--output-schema") + 1]).read_text()))
        event = {"type": "structured_result", "result": callback(context)}
        return subprocess.CompletedProcess(argv, 0, json.dumps(event) + "\n", "")

    return partial(run_codex_exec, runner=process)


def relevant(context):
    return {
        "requirements": REQUIREMENTS,
        "selections": [
            {
                "candidate_id": row["candidate_id"],
                "requirement_indexes": [0],
                "rationale": "Read the cross-domain research context.",
            }
            for row in context["records"]
            if "neural circuits" in row.get("summary", "")
        ],
    }


def test_complete_paging_discovers_unfamiliar_late_entry(inputs, tmp_path, monkeypatch):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 180)
    calls = []
    plan = retrieval.plan_retrieval(
        app, snapshot, tmp_path / "discovery", runner=model_runner(relevant, calls), environment={}
    )
    assert len(calls) == 2
    assert plan["selected_candidate_ids"] == ["unfamiliar"]
    assert plan["coverage"]["visited_candidate_ids"] == ["ordinary", "unfamiliar"]
    assert calls[0]["requirements"] is None
    assert calls[1]["requirements"] == REQUIREMENTS
    assert calls[0]["confirmed_information_context"] == snapshot["information_context"]
    assert len(list((tmp_path / "discovery").glob("*/page-*/result.json"))) == 2


def test_exact_refresh_requirements_and_independent_receipts(inputs, tmp_path):
    app, snapshot = inputs
    calls = []
    run = model_runner(relevant, calls)
    first = retrieval.plan_retrieval(
        app, snapshot, tmp_path / "refresh", runner=run, requirements=REQUIREMENTS
    )
    original_bytes = (
        tmp_path / "refresh" / first["directory"].split("/")[-1] / "plan.json"
    ).read_bytes()
    second = retrieval.plan_retrieval(
        app, snapshot, tmp_path / "refresh", runner=run, requirements=REQUIREMENTS
    )
    assert calls[0]["requirements"] == REQUIREMENTS
    assert first["directory"] != second["directory"]
    assert (Path(first["directory"]) / "plan.json").read_bytes() == original_bytes


@pytest.mark.parametrize("bad", ["unknown-id", "ordinary"])
def test_out_of_page_and_already_read_ids_rejected(inputs, tmp_path, bad):
    app, snapshot = inputs
    output = {
        "requirements": REQUIREMENTS,
        "selections": [{"candidate_id": bad, "requirement_indexes": [0], "rationale": "read"}],
    }
    with pytest.raises(PortalDataError):
        retrieval.plan_retrieval(
            app,
            snapshot,
            tmp_path / "bad",
            runner=model_runner(lambda _: output, []),
            selected_candidate_ids=["ordinary"],
        )


def test_followup_limits_to_unknown_indexes_and_additional_candidates(inputs, tmp_path):
    app, snapshot = inputs
    calls = []
    plan = retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "followup",
        runner=model_runner(relevant, calls),
        requirements=REQUIREMENTS,
        unknown_requirements=[0],
        selected_candidate_ids=["ordinary"],
    )
    assert plan["selected_candidate_ids"] == ["unfamiliar"]
    assert calls[0]["unknown_requirement_indexes"] == [0]
    assert calls[0]["already_selected_candidate_ids"] == ["ordinary"]
    with pytest.raises(PortalDataError):
        retrieval.plan_retrieval(
            app,
            snapshot,
            tmp_path / "wrong-index",
            runner=model_runner(relevant, []),
            requirements=REQUIREMENTS,
            unknown_requirements=[1],
        )


def test_changed_exact_requirement_rejected(inputs, tmp_path):
    app, snapshot = inputs
    output = deepcopy(relevant({"records": []}))
    output["requirements"][0]["text"] += " Changed"
    with pytest.raises(PortalDataError):
        retrieval.plan_retrieval(
            app,
            snapshot,
            tmp_path / "changed",
            runner=model_runner(lambda _: output, []),
            requirements=REQUIREMENTS,
        )


@pytest.mark.parametrize("indexes", [[-1], [2], [0, 0], [True]])
def test_invalid_requirement_indexes_rejected(inputs, tmp_path, indexes):
    app, snapshot = inputs
    output = {
        "requirements": REQUIREMENTS,
        "selections": [
            {
                "candidate_id": "unfamiliar",
                "requirement_indexes": indexes,
                "rationale": "Read the relevant source.",
            }
        ],
    }
    with pytest.raises(PortalDataError):
        retrieval.plan_retrieval(
            app, snapshot, tmp_path / "invalid-index", runner=model_runner(lambda _: output, [])
        )


def test_oversized_entry_is_not_silently_truncated(inputs, tmp_path, monkeypatch):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 40)
    calls = []
    with pytest.raises(PortalDataError) as error:
        retrieval.plan_retrieval(
            app, snapshot, tmp_path / "large", runner=model_runner(relevant, calls)
        )
    assert error.value.code == "retrieval_too_large"
    assert not calls


def test_cli_failure_retained_without_retry(inputs, tmp_path):
    app, snapshot = inputs
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise CodexCLIError(
            "interrupted", raw_stdout_jsonl="partial event", redacted_stderr="failure"
        )

    with pytest.raises(PortalDataError):
        retrieval.plan_retrieval(app, snapshot, tmp_path / "failure", runner=fail)
    assert len(calls) == 1
    result_path = next((tmp_path / "failure").glob("*/page-*/result.json"))
    assert json.loads(result_path.read_text())["raw_stdout_jsonl"] == "partial event"


def test_runtime_schema_scopes_candidate_ids_to_page_and_excludes_already_read(
    inputs, tmp_path, monkeypatch
):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 180)
    schemas = []
    retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "scoped-pages",
        runner=model_runner(relevant, [], schemas),
        requirements=REQUIREMENTS,
        selected_candidate_ids=["ordinary"],
    )
    skipped = next((tmp_path / "scoped-pages").glob("*/page-0001/skipped.json"))
    assert json.loads(skipped.read_text())["model_called"] is False
    assert len(schemas) == 1
    second = schemas[0]["$defs"]["_Selection"]["properties"]
    assert second["candidate_id"]["enum"] == ["unfamiliar"]
    assert second["requirement_indexes"]["items"]["enum"] == [0, 1]


def test_followup_runtime_schema_only_allows_unknown_requirement_indexes(inputs, tmp_path):
    app, snapshot = inputs
    schemas = []
    retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "scoped-unknown",
        runner=model_runner(relevant, [], schemas),
        requirements=REQUIREMENTS,
        unknown_requirements=[0],
        selected_candidate_ids=["ordinary"],
    )
    selection = schemas[0]["$defs"]["_Selection"]["properties"]
    assert selection["candidate_id"]["enum"] == ["unfamiliar"]
    assert selection["requirement_indexes"]["items"]["enum"] == [0]


def test_empty_unknown_scope_disallows_selections_without_empty_enum(inputs, tmp_path):
    app, snapshot = inputs
    schemas = []
    retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "empty-unknown",
        runner=model_runner(
            lambda _: {"requirements": REQUIREMENTS, "selections": []}, [], schemas
        ),
        requirements=REQUIREMENTS,
        unknown_requirements=[],
    )
    assert schemas[0]["properties"]["selections"]["maxItems"] == 0
    assert (
        "enum"
        not in schemas[0]["$defs"]["_Selection"]["properties"]["requirement_indexes"]["items"]
    )


def test_same_experience_can_be_selected_for_multiple_requirements(inputs, tmp_path):
    app, snapshot = inputs
    output = {
        "requirements": REQUIREMENTS,
        "selections": [
            {"candidate_id": "unfamiliar", "requirement_indexes": [0], "rationale": "Research"},
            {"candidate_id": "unfamiliar", "requirement_indexes": [1], "rationale": "Languages"},
        ],
    }
    result = retrieval.plan_retrieval(
        app, snapshot, tmp_path / "multiple-reasons", runner=model_runner(lambda _: output, [])
    )
    assert result["selected_candidate_ids"] == ["unfamiliar"]
    assert result["selections"][0]["requirement_indexes"] == [0, 1]
    assert result["selections"][0]["rationale"] == "Research\nLanguages"


def test_duplicate_selection_does_not_hide_an_invalid_requirement_index(inputs, tmp_path):
    app, snapshot = inputs
    output = {
        "requirements": REQUIREMENTS,
        "selections": [
            {"candidate_id": "unfamiliar", "requirement_indexes": [0], "rationale": "Research"},
            {"candidate_id": "unfamiliar", "requirement_indexes": [99], "rationale": "Invalid"},
        ],
    }
    with pytest.raises(PortalDataError, match="序号"):
        retrieval.plan_retrieval(
            app, snapshot, tmp_path / "invalid-repeat", runner=model_runner(lambda _: output, [])
        )


def test_long_directory_entry_is_fully_read_and_late_content_is_selected(
    inputs, tmp_path, monkeypatch
):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 500)
    record = snapshot["career_library"]["records"][1]
    record["summary"] = "多领域记录。" * 400 + "neural circuits"
    calls = []

    def select(context):
        return {
            "requirements": REQUIREMENTS,
            "selections": [
                {
                    "candidate_id": row["candidate_id"],
                    "requirement_indexes": [0],
                    "rationale": "Read actual work.",
                }
                for row in context["records"]
                if "neural circuits" in json.dumps(row, ensure_ascii=False)
            ],
        }

    plan = retrieval.plan_retrieval(
        app, snapshot, tmp_path / "long", runner=model_runner(select, calls)
    )
    assert plan["selected_candidate_ids"] == ["unfamiliar"]
    fragments = [
        row["discovery_fragment"]
        for call in calls
        for row in call["records"]
        if "discovery_fragment" in row
    ]
    original = retrieval._encoded(
        {key: value for key, value in record.items() if key != "candidate_id"}
    )
    assert fragments[0]["start"] == 0 and fragments[-1]["end"] == len(original)
    assert all(
        left["end"] >= right["start"] for left, right in zip(fragments, fragments[1:], strict=False)
    )
    assert all(original[row["start"] : row["end"]] == row["text"] for row in fragments)
    assert plan["coverage"]["visited_candidate_ids"] == ["ordinary", "unfamiliar"]
    assert plan["coverage"]["requirement_indexes"] == [0, 1]
    assert all(len(retrieval._encoded(call["records"]).encode()) <= 500 for call in calls)


def test_directory_fragment_boundaries_preserve_a_complete_search_phrase(monkeypatch):
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 300)
    record = {
        "candidate_id": "item",
        "summary": "x" * 341 + "Bayesian calibration performed in research.",
    }
    fragments = retrieval._record_parts(record)
    assert any(
        "Bayesian calibration performed in research." in row["discovery_fragment"]["text"]
        for row in fragments
    )


def test_business_goal_only_lead_does_not_need_an_atomic_requirement_index(inputs, tmp_path):
    from test_application_job_brief import runner_for

    from career_evidence_graph.application_job_brief import create_job_brief

    app, snapshot = inputs
    output = {
        "business_object": "Research decisions",
        "role_understanding": {
            "business_objective": "Improve research decisions",
            "work_outputs": ["Research outputs"],
            "methods_role": "Methods support research",
        },
        "groups": [
            {
                "label": row["text"],
                "jd_quote": app["job_description"],
                "operator": "all",
                "importance": row["importance"],
                "hard_condition": False,
                "weight": 1,
                "weight_reason": "Fixed engineering fixture",
                "requirements": [{"text": row["text"], "jd_quote": app["job_description"]}],
            }
            for row in REQUIREMENTS
        ],
    }
    brief = create_job_brief(app, tmp_path / "brief", runner=runner_for(output))
    plan = retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "business-only",
        runner=model_runner(
            lambda _: {
                "requirements": REQUIREMENTS,
                "selections": [
                    {
                        "candidate_id": "unfamiliar",
                        "requirement_indexes": [],
                        "business_relevance": True,
                        "rationale": "Business output experience",
                    }
                ],
            },
            [],
        ),
        requirements=REQUIREMENTS,
        job_brief=brief,
    )
    assert plan["selected_candidate_ids"] == ["unfamiliar"]
    assert plan["selections"][0]["business_relevance"]
    assert (
        plan["coverage"]["business_objective"] == brief["role_understanding"]["business_objective"]
    )


def test_full_retrieval_context_budget_fails_before_call_instead_of_truncating(
    inputs, tmp_path, monkeypatch
):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PROMPT_BYTES", 100)
    calls = []
    with pytest.raises(PortalDataError) as error:
        retrieval.plan_retrieval(
            app, snapshot, tmp_path / "prompt-budget", runner=model_runner(relevant, calls)
        )
    assert error.value.code == "retrieval_too_large"
    assert not calls


def test_a_grown_answer_library_still_fits_retrieval(inputs, tmp_path):
    # 38 confirmed answers took 25.6 KB and stopped every job's analysis (2026-11-07).
    app, snapshot = inputs
    snapshot["information_context"] = {
        "facts": [{"fact": f"q{i}", "text": "x" * 700} for i in range(38)]
    }
    calls = []
    retrieval.plan_retrieval(
        app, snapshot, tmp_path / "grown", runner=model_runner(relevant, calls)
    )
    assert calls
