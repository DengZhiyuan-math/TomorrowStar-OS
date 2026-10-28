"""Recommendation polling scales with incoming and retained records independently."""

from copy import deepcopy

import pytest
from test_application_pipeline import advance
from test_application_pipeline import environment as environment

from career_evidence_graph import application_pipeline


def test_pending_recommendations_index_retained_ids_once(environment, monkeypatch):
    pipeline, _flow, intake, _worker, jobs = environment

    class RetainedId(str):
        hash_calls = 0

        def __hash__(self):
            type(self).hash_calls += 1
            return super().__hash__()

    state = pipeline._load()
    state["items"] = [
        {"application_id": jobs[0]["id"], "recommendation_id": RetainedId(f"seen-{index}")}
        for index in range(64)
    ]
    # Saved legacy entries can have no recommendation identity.
    state["items"].append({"application_id": jobs[1]["id"]})
    state["current_recommendation_id"] = "current"
    incoming = [
        {"id": identifier}
        for identifier in [
            "seen-0",
            "current",
            *(f"pending-{index}" for index in range(256)),
            "seen-63",
            "pending-0",
        ]
    ]
    intake.state["recommendations"] = incoming
    monkeypatch.setattr(pipeline, "_load", lambda: state)
    original = pipeline.path.read_bytes()

    result = pipeline.snapshot()

    assert result["pending_recommendations"] == incoming[2:-2] + [incoming[-1]]
    assert RetainedId.hash_calls <= len(state["items"])
    assert "pending_recommendations" not in state
    assert pipeline.path.read_bytes() == original


def test_matching_screens_only_current_application_with_full_history(environment, monkeypatch):
    pipeline, _flow, _intake, _worker, jobs = environment
    screening = application_pipeline.screen_applications
    calls = []

    def selected(records, **options):
        calls.append((options.get("application_id"), [row["id"] for row in records]))
        return screening(records, **options)

    monkeypatch.setattr(application_pipeline, "screen_applications", selected)
    pipeline.start(request_id="targeted-screening")
    advance(pipeline, "generating_resume")

    assert len(calls) == 1
    assert calls[0][0] == jobs[0]["id"]
    assert set(calls[0][1]) == {row["id"] for row in jobs}


def test_snapshot_reads_labels_once_and_keeps_missing_application(environment, monkeypatch):
    pipeline, flow, _intake, _worker, jobs = environment
    state = pipeline._load()
    state["items"] = [
        {"application_id": job["id"], "company": "old", "role_title": "old role"} for job in jobs
    ] + [{"application_id": "f" * 24, "company": "retained", "role_title": "retained role"}]
    original_state = deepcopy(state)
    original_bytes = pipeline.path.read_bytes()
    original_list = flow.applications.list_applications
    reads = []

    def listed():
        reads.append("list")
        return original_list()

    def forbidden_get(_identifier):
        pytest.fail("Healthy label polling must not read each application separately")

    monkeypatch.setattr(pipeline, "_load", lambda: state)
    monkeypatch.setattr(flow.applications, "list_applications", listed)
    monkeypatch.setattr(flow.applications, "get_application", forbidden_get)

    result = pipeline.snapshot()

    assert reads == ["list"]
    assert result["items"] == [
        {**item, "company": job["company"], "role_title": job["role_title"]}
        for item, job in zip(state["items"], jobs, strict=False)
    ] + [state["items"][-1]]
    assert state == original_state
    assert pipeline.path.read_bytes() == original_bytes


@pytest.mark.parametrize("damaged_format", ["legacy", "json"])
def test_snapshot_label_fallback_preserves_existing_error_semantics(
    environment, monkeypatch, damaged_format
):
    pipeline, flow, _intake, _worker, jobs = environment
    state = pipeline._load()
    state["items"] = [
        {"application_id": jobs[0]["id"], "company": "retained", "role_title": "retained role"},
        {"application_id": "f" * 24, "company": "missing", "role_title": "missing role"},
    ]
    suffix = ".md" if damaged_format == "legacy" else ".json"
    unrelated = flow.applications.root / ("unrelated" + suffix)
    unrelated.write_text("invalid application document", encoding="utf-8")
    original_bytes = pipeline.path.read_bytes()
    original_get = flow.applications.get_application
    original_list = flow.applications.list_applications
    reads = []

    def listed():
        reads.append("list")
        return original_list()

    def get(identifier):
        reads.append(identifier)
        return original_get(identifier)

    monkeypatch.setattr(pipeline, "_load", lambda: state)
    monkeypatch.setattr(flow.applications, "list_applications", listed)
    monkeypatch.setattr(flow.applications, "get_application", get)

    result = pipeline.snapshot()

    assert reads == ["list", jobs[0]["id"], "f" * 24]
    if damaged_format == "legacy":
        assert result["items"][0]["company"] == jobs[0]["company"]
        assert result["items"][0]["role_title"] == jobs[0]["role_title"]
    else:
        # Invalid JSON is still checked by each single-record read.
        assert result["items"][0] == state["items"][0]
    assert result["items"][1] == state["items"][1]
    assert pipeline.path.read_bytes() == original_bytes
    assert unrelated.read_text(encoding="utf-8") == "invalid application document"


def test_empty_snapshot_does_not_read_application_labels(environment, monkeypatch):
    pipeline, flow, _intake, _worker, _jobs = environment

    def forbidden():
        pytest.fail("An empty pipeline has no application labels to read")

    monkeypatch.setattr(flow.applications, "list_applications", forbidden)
    assert pipeline.snapshot()["items"] == []
