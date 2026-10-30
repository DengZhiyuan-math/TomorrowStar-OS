"""Normal analysis discovers evidence and reuses facts without a per-job override."""

import json
from copy import deepcopy

import pytest
from test_application_information import answer, library_with
from test_application_match import model_output, model_runner
from test_canonical_career_sources import canonical as canonical
from test_career_portal_http import portal as portal

from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.usefixtures("planner_path")

APPLICATION = {
    "id": "normal-analysis",
    "revision": "job-v1",
    "company": "Unfamiliar Employer",
    "role_title": "Research Intern",
    "country": "CHE",
    "job_description": (
        "Collaborate across scientific domains. Communicate in English and other languages."
    ),
}


def requirement(text, *, preferred=False, hard=False):
    return {
        "text": text,
        "importance": "preferred" if preferred else "required",
        "hard_condition": hard,
    }


class RecordedPipeline:
    def __init__(
        self,
        requirements,
        *,
        select=True,
        judgments=None,
        after_evaluation=None,
        followup_select=False,
    ):
        self.requirements = requirements
        self.select = select
        self.followup_select = followup_select
        self.judgments = judgments
        self.after_evaluation = after_evaluation
        self.calls = []
        self.phases = []
        self.contexts = []
        self.brief_calls = []
        self.read_calls = []

    def __call__(self, config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        if set(schema["properties"]) == {"selections"}:
            data = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
            self.read_calls.append(data)
            selections = []
            for supplied in data.get("source_ranges", [data]):
                if "spans" in supplied:
                    if supplied["spans"]:
                        selections.append(
                            {
                                "span_id": supplied["spans"][0]["span_id"],
                                "requirement_indexes": list(range(len(self.requirements))),
                            }
                        )
                elif supplied["text"].strip():
                    selections.append(
                        {
                            "source_id": supplied["source"]["source_id"],
                            "requirement_indexes": list(range(len(self.requirements))),
                        }
                    )
            return model_runner({"selections": selections}, self.calls)(config, prompt, **kwargs)
        if set(schema["properties"]) == {"business_object", "role_understanding", "groups"}:
            data = json.loads(prompt.rsplit("\n", 1)[1])
            output = {
                "business_object": "Recorded business context",
                "role_understanding": model_output(
                    {"items": [{"source_id": "unused", "text": "unused"}]}
                )["role_understanding"],
                "groups": [
                    {
                        "label": req["text"],
                        "jd_quote": data["job_description"],
                        "operator": "all",
                        "importance": req["importance"],
                        "hard_condition": req["hard_condition"],
                        "weight": 1,
                        "weight_reason": "Equal recorded test groups",
                        "requirements": [
                            {"text": req["text"], "jd_quote": data["job_description"]}
                        ],
                    }
                    for req in self.requirements
                ],
            }
            self.brief_calls.append(data)
            return model_runner(output, self.calls)(config, prompt, **kwargs)
        if schema["title"] == "_PageResult":
            data = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
            followup = data["unknown_requirement_indexes"] is not None
            output = {"requirements": self.requirements, "selections": []}
            if (self.select and not followup) or (
                self.followup_select and followup and not data["already_selected_candidate_ids"]
            ):
                output["selections"] = [
                    {
                        "candidate_id": data["records"][0]["candidate_id"],
                        "requirement_indexes": [0],
                        "rationale": "Read the relevant interdisciplinary source.",
                    }
                ]
            self.phases.append("followup" if followup else "plan")
        else:
            data = json.loads(prompt.rsplit("\n", 1)[1])
            output = model_output({"items": [{"source_id": "unused", "text": "unused"}]})
            output["requirements"] = []
            output["selected_source_ids"] = []
            output["selection_rationale"] = []
            for index, req in enumerate(self.requirements):
                fact = "language_english_fluent" if index == 0 else "language_french_cefr"
                candidates = [
                    s
                    for s in data["sources"]
                    if s.get("confirmed_information", {}).get("fact") == fact
                ]
                if self.select or self.followup_select:
                    candidates = [
                        s
                        for s in data["sources"]
                        if s.get("source_kind") != "confirmed_information"
                    ][-1:]
                judgment = (
                    self.judgments[index]
                    if self.judgments and candidates
                    else ("supported" if candidates else "unknown")
                )
                citations = [
                    {"source_id": s["source_id"], "quote": s["text"].splitlines()[0][:1000]}
                    for s in candidates
                ]
                output["requirements"].append(
                    {
                        **req,
                        "judgment": judgment,
                        "explanation": "Supported by the cited source."
                        if candidates
                        else "No applicable confirmed answer.",
                        "source_ids": [s["source_id"] for s in candidates],
                        "citations": citations,
                        "claim_scope": "documentary",
                    }
                )
            self.phases.append("evaluate")
        self.contexts.append(data)
        result = model_runner(output, self.calls)(config, prompt, **kwargs)
        if self.phases[-1] == "evaluate" and self.after_evaluation:
            self.after_evaluation()
        return result


def thin(canonical):
    library, _, _, base, *_ = canonical
    base["schemaVersion"] = 1
    snapshot = library.snapshot_for_analysis(base)
    snapshot["career_library"]["canonical_sources"] = True
    snapshot.pop("revision", None)
    snapshot["revision"] = digest(snapshot)
    return snapshot


def test_normal_entry_discovers_unlisted_candidate_reads_capture_and_persists_provenance(
    canonical, tmp_path
):
    library, _, _, base, *_ = canonical
    snapshot = thin(canonical)
    before = deepcopy(snapshot)
    runner = RecordedPipeline(
        [requirement("Experience combining distinct scientific disciplines")], judgments=["partial"]
    )
    result = analyze_job(
        APPLICATION,
        snapshot,
        tmp_path / "normal",
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library=library_with(),
    )
    assert runner.phases == ["plan", "evaluate"]
    assert runner.contexts[0]["records"][0]["candidate_id"] == "unseen-identity"
    evaluation = runner.contexts[1]
    assert any("Physics and biology" in source["text"] for source in evaluation["sources"])
    assert "private irrelevant text" not in json.dumps(evaluation)
    assert result["retrieval"]["selected_candidate_ids"] == ["unseen-identity"]
    assert result["retrieval"]["source_reads"][0]["status"] == "read"
    assert result["input_source_snapshot_revision"] == snapshot["revision"]
    assert result["source_snapshot_revision"] != snapshot["revision"]
    assert result["requirements"][0]["evidence_state"] == "searched_evidence_insufficient"
    assert result["requirements"][0]["judgment"] == "partial"
    assert len(result["retrieval"]["plans"]) == 1
    assert snapshot == before
    assert json.loads((tmp_path / "normal/analysis.json").read_text()) == result
    assert (tmp_path / "normal/selected-read-snapshot.json").is_file()


def test_paraphrased_language_requirements_use_confirmed_facts_without_resume_selection(
    canonical, tmp_path
):
    library, _, _, base, *_ = canonical
    lib = library_with(answer("English fluency", "professional"), answer("French level", "A1"))
    before = deepcopy(lib)
    runner = RecordedPipeline(
        [
            requirement("Can communicate professionally using English", hard=True),
            requirement("Some knowledge of another language is advantageous", preferred=True),
        ],
        select=False,
    )
    result = analyze_job(
        APPLICATION,
        thin(canonical),
        tmp_path / "languages",
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library=lib,
    )
    assert runner.phases == ["plan", "evaluate"]
    assert result["score"]["lower"] == 100
    assert result["selected_source_ids"] == []
    assert all(
        row["information_support"]["status"] == "supported" for row in result["requirements"]
    )
    assert all(
        source["resume_eligible"] is False
        for row in result["requirements"]
        for source in row["sources"]
    )
    assert lib == before


@pytest.mark.parametrize("state", ["missing", "inferred", "conflict"])
def test_withdrawal_and_conflict_are_unknown_in_normal_analysis(canonical, tmp_path, state):
    library, _, _, base, *_ = canonical
    records = [
        answer(
            "English fluency",
            None if state == "missing" else "yes",
            state="confirmed" if state == "conflict" else state,
        )
    ]
    if state == "conflict":
        records.append(answer("Are you fluent in English?", "no"))
    runner = RecordedPipeline(
        [requirement("Professional communication in English", hard=True)], select=False
    )
    result = analyze_job(
        APPLICATION,
        thin(canonical),
        tmp_path / state,
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library=library_with(*records),
    )
    assert result["requirements"][0]["judgment"] == "unknown"
    assert not result["requirements"][0].get("information_support")
    assert result["selected_source_ids"] == []
    assert runner.phases == ["plan", "evaluate", "followup"]


def test_changed_capture_after_evaluation_cannot_be_adopted(canonical, tmp_path):
    library, _, capture, base, *_ = canonical
    runner = RecordedPipeline(
        [requirement("Combine scientific domains")],
        judgments=["partial"],
        after_evaluation=lambda: capture.write_text("changed"),
    )
    with pytest.raises(PortalDataError) as error:
        analyze_job(
            APPLICATION,
            thin(canonical),
            tmp_path / "drift",
            runner=runner,
            source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
            information_library=library_with(),
        )
    assert error.value.code == "match_sources_changed"
    assert not (tmp_path / "drift/analysis.json").exists()
    assert (tmp_path / "drift/evaluation-1/analysis.json").is_file()


def test_default_portal_flow_callback_uses_normal_planner_and_active_answer_library(
    canonical, portal, tmp_path
):
    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.career_portal import create_server
    from career_evidence_graph.career_portal_data import ApplicationStore

    _, _, _, _, _, manifest, _ = canonical
    store = helper.Store(tmp_path / "answers")
    store.initialize()
    for question, value in (("English fluency", "professional"), ("French level", "A1")):
        _, record = answer(question, value)
        store.put_answer(record)
    answers_before = store.answers_path.read_bytes()
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": APPLICATION["company"],
            "role_title": APPLICATION["role_title"],
            "job_description": APPLICATION["job_description"],
        }
    )
    runner = RecordedPipeline(
        [
            requirement("Use English professionally in a research team", hard=True),
            requirement("Any extra language knowledge is an advantage", preferred=True),
        ],
        select=False,
    )
    server = create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        career_library_manifest=manifest,
        information_library_root=store.root,
        flow_match_runner=runner,
        write_admission_policy="development",
    )
    try:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        before = (flow.root / "flow.json").read_bytes()
        result = flow.callbacks["analysis"](task)
        assert runner.phases == ["plan", "evaluate"]
        assert result["retrieval"]["index_status"] == "searched"
        assert result["score"]["lower"] == 100
        assert result["selected_source_ids"] == []
        assert (flow.root / "flow.json").read_bytes() == before
        assert store.answers_path.read_bytes() == answers_before
    finally:
        server.server_close()


def test_unknown_requirement_triggers_additional_read_and_new_evaluation(canonical, tmp_path):
    library, _, _, base, *_ = canonical
    runner = RecordedPipeline(
        [requirement("Scientific work across disciplines")],
        select=False,
        followup_select=True,
        judgments=["partial"],
    )
    result = analyze_job(
        APPLICATION,
        thin(canonical),
        tmp_path / "additional-read",
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library=library_with(),
    )
    assert runner.phases == ["plan", "evaluate", "followup", "evaluate"]
    assert runner.contexts[1]["sources"] == []
    assert runner.contexts[2]["unknown_requirement_indexes"] == [0]
    assert any("Physics and biology" in item["text"] for item in runner.contexts[3]["sources"])
    assert len(result["retrieval"]["evaluations"]) == 2
    assert result["retrieval"]["selected_candidate_ids"] == ["unseen-identity"]
    assert runner.contexts[2]["already_selected_candidate_ids"] == []
    assert result["requirements"][0]["judgment"] == "partial"
    assert result["requirements"][0]["evidence_state"] == "searched_evidence_insufficient"


def test_selected_candidate_without_a_successful_read_does_not_count_as_exhausted(
    canonical, tmp_path
):
    library, _, _, base, *_ = canonical
    runner = RecordedPipeline([requirement("Scientific work across disciplines")])

    def selected_but_not_read(ids):
        snapshot = library.snapshot_for_analysis(base, ids)
        snapshot["items"] = []
        snapshot["documents"] = []
        snapshot["career_library"]["source_reads"] = [
            {"candidate_id": "unseen-identity", "status": "indexed_not_read"}
        ]
        snapshot.pop("revision", None)
        snapshot["revision"] = digest(snapshot)
        return snapshot

    result = analyze_job(
        APPLICATION,
        thin(canonical),
        tmp_path / "not-read",
        runner=runner,
        source_loader=selected_but_not_read,
        information_library=library_with(),
    )
    assert runner.phases == ["plan", "evaluate"]
    assert len(result["retrieval"]["plans"]) == 2
    followup = result["retrieval"]["plans"][-1]
    assert followup["selected_candidate_ids"] == []
    assert followup["coverage"]["visited_candidate_ids"] == ["unseen-identity"]
    assert result["requirements"][0]["judgment"] == "unknown"
    assert result["requirements"][0]["evidence_state"] == "searched_evidence_insufficient"


def test_evaluation_sees_short_source_handles_and_the_report_keeps_real_identities(
    canonical, tmp_path
):
    import re

    library, _, _, base, *_ = canonical
    runner = RecordedPipeline([requirement("Experience combining distinct scientific disciplines")])
    result = analyze_job(
        APPLICATION,
        thin(canonical),
        tmp_path / "short-handles",
        runner=runner,
        source_loader=lambda ids: library.snapshot_for_analysis(base, ids),
        information_library=library_with(),
    )
    seen = [source["source_id"] for source in runner.contexts[-1]["sources"]]
    # The model needs a handle unique within this call; content-bound IDs stay internal.
    assert seen and all(re.fullmatch(r"S\d+", source_id) for source_id in seen)
    cited = result["requirements"][0]["source_ids"]
    assert cited and not any(re.fullmatch(r"S\d+", source_id) for source_id in cited)
