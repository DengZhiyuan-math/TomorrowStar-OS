"""Normal two-library analysis requires complete, attributable demand reads."""

import json

import pytest
from test_application_information import answer, library_with
from test_application_match import model_runner
from test_canonical_career_sources import canonical as canonical
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement

from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.usefixtures("planner_path")


class ContentPipeline(RecordedPipeline):
    """Select concrete source context independently of arbitrary project labels."""

    def __call__(self, config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        if schema.get("title") != "_PageResult":
            return super().__call__(config, prompt, **kwargs)
        data = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
        selections = []
        for record in data["records"]:
            content = json.dumps(
                {key: value for key, value in record.items() if key != "title"}
            ).casefold()
            if "neural" in content and "collaborator" in content:
                selections.append(
                    {
                        "candidate_id": record["candidate_id"],
                        "requirement_indexes": [0],
                        "rationale": "Read concrete neural-model work with biology collaborators.",
                    }
                )
        self.phases.append("plan")
        self.contexts.append(data)
        return model_runner(
            {"requirements": self.requirements, "selections": selections}, self.calls
        )(config, prompt, **kwargs)


def analyze(canonical, directory, runner, *, information=None, loader=None):
    library, _, _, base, *_ = canonical
    base["schemaVersion"] = 1
    snapshot = library.snapshot_for_analysis(base)
    return analyze_job(
        APPLICATION,
        snapshot,
        directory,
        runner=runner,
        source_loader=loader or (lambda ids: library.snapshot_for_analysis(base, ids)),
        information_library=information or library_with(),
    )


def save_body(canonical, *, pending=False, body=None, metadata=None):
    _, root, *_ = canonical

    def failed_index(_):
        raise ValueError("Synthetic indexing failure")

    store = ExperienceStore(root, derive=failed_index if pending else None)
    return store.save(
        "unseen-identity",
        title="Opaque historical label",
        body=body or "Built neural models of sensory circuits with biology collaborators.",
        metadata=metadata or {},
    )


def assert_no_evaluation(directory):
    assert not list(directory.rglob("analysis.json"))
    assert not list(directory.rglob("score.json"))


def test_pending_primary_body_is_read_before_relevance_selection(canonical, tmp_path):
    save_body(canonical, pending=True)
    runner = ContentPipeline([requirement("Collaborate across scientific domains")])
    directory = tmp_path / "pending"
    result = analyze(canonical, directory, runner)
    record = runner.contexts[0]["records"][0]
    assert record["summary"] == ""
    assert record["discovery_status"] == "body_fallback_read"
    assert "neural models" in record["body_discovery"][0]["text"]
    assert result["retrieval"]["selected_candidate_ids"] == ["unseen-identity"]
    assert result["score"]["lower"] == 100
    assert json.loads((directory / "index-body-fallback.json").read_text())["status"] == "complete"


def test_failed_pending_body_stops_before_score(canonical, tmp_path):
    save_body(canonical, pending=True)
    _, root, *_ = canonical
    store = ExperienceStore(root)
    path = root / store.directory()["unseen-identity"]["detail_entry"]
    path.write_text("{}")
    runner = ContentPipeline([requirement("Collaborate across scientific domains")])
    directory = tmp_path / "failed-fallback"
    with pytest.raises(PortalDataError) as error:
        analyze(canonical, directory, runner)
    assert error.value.code == "retrieval_execution_incomplete"
    assert runner.phases == []
    assert_no_evaluation(directory)
    failure = json.loads((directory / "retrieval-execution.json").read_text())
    assert failure["phase"] == "index_body_fallback"


def test_selected_missing_capture_is_execution_failure(canonical, tmp_path):
    _, _, capture, *_ = canonical
    capture.unlink()
    runner = RecordedPipeline([requirement("Collaborate across scientific domains")])
    directory = tmp_path / "missing-selected"
    with pytest.raises(PortalDataError) as error:
        analyze(canonical, directory, runner)
    assert error.value.code == "retrieval_execution_incomplete"
    assert runner.phases == ["plan"]
    assert_no_evaluation(directory)
    failure = json.loads((directory / "retrieval-execution.json").read_text())
    assert failure["phase"] == "selected_bodies"


@pytest.mark.parametrize("invalid", ["source_id", "quote", "requirement_indexes"])
def test_invalid_long_source_reference_is_execution_failure(canonical, tmp_path, invalid):
    save_body(
        canonical,
        body="Built neural models with biology collaborators. " + "Literal source detail. " * 4000,
    )

    class InvalidReading(RecordedPipeline):
        def __call__(self, config, prompt, **kwargs):
            schema = json.loads(config.output_schema.read_text())
            if "_SpanSelection" not in schema.get("$defs", {}):
                return super().__call__(config, prompt, **kwargs)
            data = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
            selection = {"span_id": data["spans"][0]["span_id"], "requirement_indexes": [0]}
            if invalid == "source_id":
                selection["span_id"] = "span-that-was-not-provided"
            else:
                selection[invalid] = {
                    "quote": "fabricated literal quote",
                    "requirement_indexes": [999],
                }[invalid]
            return model_runner({"selections": [selection]}, self.calls)(config, prompt, **kwargs)

    runner = InvalidReading([requirement("Collaborate across scientific domains")])
    directory = tmp_path / invalid
    with pytest.raises(PortalDataError) as error:
        analyze(canonical, directory, runner)
    assert error.value.code == "retrieval_execution_incomplete"
    assert runner.phases == ["plan"]
    assert_no_evaluation(directory)
    packet = json.loads((directory / "material-packet-1/material-packet.json").read_text())
    assert packet["status"] == "failed"


@pytest.mark.parametrize("pending", [False, True])
def test_managed_library_without_registry_uses_normal_entry(canonical, tmp_path, pending):
    _, _, _, _, _, manifest, descriptor = canonical
    descriptor.pop("source_registry")
    manifest.write_text(json.dumps(descriptor))
    save_body(canonical, pending=pending)
    runner = ContentPipeline([requirement("Collaborate across scientific domains")])
    result = analyze(canonical, tmp_path / f"managed-{pending}", runner)
    assert runner.phases == ["plan", "evaluate"]
    assert result["score"]["lower"] == 100
    assert result["retrieval"]["selected_candidate_ids"] == ["unseen-identity"]
    assert result["retrieval"]["index_status"] == "searched"


@pytest.mark.parametrize("label", ["Crossfield Lab", "Unfamiliar placement Q-317"])
def test_concrete_content_and_related_implementation_survive_rename(canonical, tmp_path, label):
    library, root, _, base, write, manifest, descriptor = canonical
    catalog = json.loads((root / "catalog.json").read_text())
    record = catalog["records"][0]
    record.update(title=label, accepted_reading_summary="", confirmed_identity_facts={})
    catalog["records"].append(
        {
            "candidate_id": "related-implementation",
            "title": "Notes R",
            "record_class": "current-confirmed-identity",
            "accepted_reading_summary": "Implementation supplement",
        }
    )
    descriptor["catalog"] = write("catalog.json", catalog)
    manifest.write_text(json.dumps(descriptor))
    store = ExperienceStore(root)
    store.save(
        "unseen-identity",
        title=label,
        body="Built neural models of sensory circuits with biology collaborators.",
        metadata={"related_ids": ["related-implementation"]},
    )
    store.save(
        "related-implementation",
        title="Notes R",
        body="Implemented the simulation in Python with sparse matrices; team roles preserved.",
        metadata={"related_ids": ["unseen-identity"]},
    )
    snapshots = []

    def loader(ids):
        snapshot = library.snapshot_for_analysis(base, ids)
        snapshots.append(snapshot)
        return snapshot

    runner = ContentPipeline([requirement("Collaborate across scientific domains")])
    result = analyze(canonical, tmp_path / label.replace(" ", "-"), runner, loader=loader)
    assert result["retrieval"]["selected_candidate_ids"] == ["unseen-identity"]
    selected = snapshots[0]["career_library"]
    assert selected["requested_candidate_ids"] == ["unseen-identity"]
    assert selected["selected_candidate_ids"] == ["related-implementation", "unseen-identity"]
    evaluation = next(data for data in runner.contexts if "sources" in data)
    text = json.dumps(evaluation["sources"])
    assert "neural models" in text and "biology collaborators" in text
    assert "Python with sparse matrices" in text
    assert len([read for read in selected["source_reads"] if read["status"] == "read"]) == 2
    assert result["retrieval"]["material_reads"]


def test_language_facts_remain_applicable_without_experience_selection(canonical, tmp_path):
    information = library_with(
        answer("English fluency", "professional"), answer("French level", "A1")
    )
    runner = RecordedPipeline(
        [
            requirement("Communicate professionally in English", hard=True),
            requirement("Some knowledge of another language is advantageous", preferred=True),
        ],
        select=False,
    )
    result = analyze(canonical, tmp_path / "languages", runner, information=information)
    assert result["score"]["lower"] == 100
    assert result["retrieval"]["selected_candidate_ids"] == []
    assert runner.phases == ["plan", "evaluate"]
    assert all(
        row["information_support"]["status"] == "supported" for row in result["requirements"]
    )
    assert all(
        source["resume_eligible"] is False
        for row in result["requirements"]
        for source in row["sources"]
    )
