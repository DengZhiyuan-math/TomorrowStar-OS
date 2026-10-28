"""Retrieved analysis evidence reaches generation without changing the input binding."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.application_career_library import CareerLibrary
from career_evidence_graph.application_experience_latex import prepare_generation
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import career_source_snapshot, draft_resume
from career_evidence_graph.career_portal_data import PortalDataError


def retrieval(store, tmp_path, analysis):
    root = tmp_path / "bound-career-library"
    (root / ".career-evidence/raw").mkdir(parents=True)

    def write(name, value):
        raw = json.dumps(value).encode()
        (root / name).write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

    raw = json.dumps({"facts": "Developed a physics simulation with biologists."}).encode()
    revision = hashlib.sha256(raw).hexdigest()
    capture = root / ".career-evidence/raw" / revision
    capture.write_bytes(raw)
    catalog = write(
        "catalog.json",
        {
            "records": [
                {
                    "candidate_id": "arbitrary-new-experience",
                    "title": "Interdisciplinary simulation",
                    "record_class": "current-confirmed-identity",
                    "source_links": [
                        {
                            "source_id": "registered-source",
                            "content_identity": "sha256:" + revision,
                            "locator": "/facts",
                            "role": "identity",
                        }
                    ],
                }
            ]
        },
    )
    registry = write(
        "registry.json",
        {
            "sources": [
                {
                    "source_id": "registered-source",
                    "availability": "available",
                    "capture": {"content_hash": "sha256:" + revision},
                }
            ]
        },
    )
    manifest = tmp_path / "retrieval-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "root": str(root),
                "catalog": catalog,
                "source_registry": registry,
            }
        )
    )
    store.career_library = CareerLibrary(manifest)
    thin = career_source_snapshot(store.catalog, career_library=store.career_library)
    selected = store.career_library.snapshot_for_analysis(
        career_source_snapshot(store.catalog), ["arbitrary-new-experience"]
    )
    source_id = selected["items"][-1]["source_id"]
    report = deepcopy(analysis)
    report.update(
        input_source_snapshot_revision=thin["revision"],
        source_snapshot_revision=selected["revision"],
        retrieval={"selected_candidate_ids": ["arbitrary-new-experience"]},
        selected_source_ids=[source_id],
        requirements=[{"source_ids": [source_id]}],
    )
    return thin, selected, report, capture


def test_default_snapshot_is_upgraded_to_exact_retrieved_evidence(task_resume, tmp_path):
    store, job, _, analysis, _ = task_resume
    thin, selected, report, _ = retrieval(store, tmp_path, analysis)
    before_report = deepcopy(report)
    supplied = deepcopy(thin)
    assert store._task_current(job["id"], supplied, report)["id"] == job["id"]
    assert supplied == selected
    assert report == before_report
    assert store._task_current(job["id"], supplied, report)["id"] == job["id"]
    draft = draft_resume(
        job,
        store.catalog,
        source_snapshot=supplied,
        selected_source_ids=report["selected_source_ids"],
    )
    assert "biologists" in draft["items"][0]["text"]


@pytest.mark.parametrize("change", ["capture", "input", "selected", "supplied"])
def test_retrieved_source_drift_cannot_reach_generation(task_resume, tmp_path, change):
    store, job, _, analysis, _ = task_resume
    thin, _, report, capture = retrieval(store, tmp_path, analysis)
    if change == "capture":
        capture.write_text('{"facts":"different responsibility"}')
    elif change == "input":
        report["input_source_snapshot_revision"] = "stale"
    elif change == "selected":
        report["source_snapshot_revision"] = "stale"
    else:
        thin["items"].append({"text": "Injected unmatched source"})
    with pytest.raises(PortalDataError, match="经历检索来源"):
        store._task_current(job["id"], thin, report)


def test_experience_handoff_archives_retrieved_sources_with_stable_flow_binding(
    full_latex, tmp_path
):
    store, job, _, analysis, calls, project, _, _ = full_latex
    thin, selected, report, _ = retrieval(store, tmp_path, analysis)
    original = (project / "main.tex").read_bytes()
    state = prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=deepcopy(thin),
        analysis=report,
        task_inputs={"sources_revision": thin["revision"]},
        latex_base=source_snapshot(project, "main.tex"),
    )
    archived = json.loads((store.root / state["id"] / "experience-generation.json").read_text())
    assert archived["request"]["source_snapshot"] == selected
    assert archived["request"]["task_inputs"]["sources_revision"] == thin["revision"]
    assert (project / "main.tex").read_bytes() == original
    assert calls == []


def test_malformed_retrieval_metadata_fails_as_invalid_inputs(task_resume, tmp_path):
    store, job, _, analysis, _ = task_resume
    thin, _, report, _ = retrieval(store, tmp_path, analysis)
    report["retrieval"] = []
    with pytest.raises(PortalDataError) as error:
        store._task_current(job["id"], deepcopy(thin), report)
    assert error.value.code == "resume_inputs_stale"
