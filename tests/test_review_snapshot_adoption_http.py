"""HTTP adoption reuses a strict snapshot while preserving an unknown export."""

import hashlib
import json
from threading import Thread

import pytest
from test_application_flow import wait_for
from test_application_prism import compiling_editor
from test_career_portal_http import Portal
from test_career_portal_http import portal as portal
from test_pdf_export_http import export_payload
from test_preparation_entry import post, snapshot

from career_evidence_graph.application_prism import PrismClient
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.fixture
def unknown_export_with_review(portal, tmp_path, monkeypatch):
    project = tmp_path / "dedicated-cv"
    project.mkdir()
    (project / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Synthetic reviewed CV\end{document}"
    )
    config = tmp_path / "resume-review.json"
    config.write_text(json.dumps({"project_root": str(project), "main": "main.tex"}))
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Python Engineer",
            "job_description": "Build Python services.",
        }
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_runtime.WorkerService",
        lambda *_args, **_kwargs: pytest.fail("Material preparation constructed a worker"),
    )
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex-home"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with compiling_editor(project, monkeypatch) as calls:
        server = create_server(
            portal.applications,
            portal.career,
            flow_root=tmp_path / "preparation",
            preparation_only=True,
            resume_review_root=tmp_path / "review-snapshots",
            resume_review_config=config,
            write_admission_policy="development",
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        active = Portal(server, portal.applications, portal.career)
        try:
            store = server.application_resume_store
            store.model_runner = lambda *_a, **_k: pytest.fail("Unexpected model call")
            store.exporter = lambda *_a, **_k: pytest.fail("Unexpected HTML renderer")
            status, _, raw = active.request("GET", "/api/resume-review/state")
            assert status == 200, raw
            status, _, raw = active.request(
                "POST",
                "/api/resume-review/capture",
                body=json.dumps(
                    {"source_revision": json.loads(raw)["live_source_revision"]}
                ).encode(),
                headers=active.write_headers(),
            )
            assert status == 200, raw
            version = json.loads(raw)["latest"]
            status, task = post(
                active,
                "import-latex",
                {
                    "application_id": job["id"],
                    "application_revision": job["revision"],
                    "project_root": str(project),
                    "main": "main.tex",
                },
            )
            assert status == 200, task
            status, task = post(active, "authorize-latex-export", export_payload(task))
            assert status == 200, task
            compile_calls = []

            class UnknownPrism(PrismClient):
                def compile(self, binding):
                    compile_calls.append(binding)
                    raise PortalDataError(
                        "resume_export_needs_recheck", "Synthetic uncertain build", 409
                    )

            store.prism_client = UnknownPrism()
            assert post(active, "export-pdf", export_payload(task))[0] == 200
            task = wait_for(
                server.application_flow_service,
                task["id"],
                lambda row: row["status"] == "needs_recheck",
            )
            prior_id = task["stages"]["export"]["attempt_id"]
            prior_root = store.root / prior_id
            prior_bytes = {path.name: path.read_bytes() for path in prior_root.iterdir()}
            assert "export-intent.json" in prior_bytes and "export.json" not in prior_bytes
            assert len(compile_calls) == 1
            yield {
                "active": active,
                "task": task,
                "version": version,
                "project": project,
                "config": config,
                "calls": calls,
                "compile_calls": compile_calls,
                "prior_id": prior_id,
                "prior_root": prior_root,
                "prior_bytes": prior_bytes,
            }
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


def adoption_payload(case):
    return {
        "task_id": case["task"]["id"],
        "task_revision": case["task"]["revision"],
        "review_version_id": case["version"]["id"],
        "expected_pdf_sha256": case["version"]["pdf_sha256"],
    }


def assert_no_replay(case):
    assert len(case["compile_calls"]) == 1
    assert len([call for call in case["calls"] if call[0] == "POST"]) == 1
    assert {path.name: path.read_bytes() for path in case["prior_root"].iterdir()} == case[
        "prior_bytes"
    ]


def test_known_strict_snapshot_is_adopted_without_replaying_unknown_export(
    unknown_export_with_review,
):
    case = unknown_export_with_review
    active = case["active"]
    state = snapshot(active)
    assert [row["id"] for row in state["review_snapshots"]] == [case["version"]["id"]]
    assert "binding" not in state["review_snapshots"][0]
    assert (
        state["review_snapshots"][0]["source_revision"] == case["task"]["prism"]["source_revision"]
    )
    status, task = post(active, "adopt-review-snapshot", adoption_payload(case))
    assert status == 200, task
    assert task["status"] == "resume_ready"
    assert task["resume_id"] != case["prior_id"]
    assert task["resume_sha256"] == case["version"]["pdf_sha256"]
    status, _, raw = active.request("GET", f"/api/flow/exports/{task['resume_id']}")
    assert status == 200, raw
    receipt = json.loads(raw)
    assert receipt["operation_kind"] == "reuse_completed_review"
    assert receipt["review_snapshot_reuse"]["kind"] == "known_snapshot_reuse"
    assert "file_base64" not in receipt
    status, _, pdf = active.request("GET", f"/api/flow/resumes/{task['resume_id']}/pdf")
    assert status == 200
    assert hashlib.sha256(pdf).hexdigest() == case["version"]["pdf_sha256"]
    assert (
        pdf == active.request("GET", f"/api/resume-review/versions/{case['version']['id']}/pdf")[2]
    )
    state = snapshot(active)
    assert state["pdf_integrity"]["status"] == "valid"
    assert state["active_task"]["materials_confirmed"] is False
    assert state["active_task"]["factual_review"] == "pending"
    assert state["active_task"]["worker_ref"] is None
    assert state["capabilities"]["worker"] is False and active.server.worker_service is None
    assert (
        post(
            active,
            "confirm-materials",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "resume_id": task["resume_id"],
                "resume_sha256": task["resume_sha256"],
            },
        )[0]
        == 409
    )
    assert_no_replay(case)


@pytest.mark.parametrize("damage", ["pdf-hash", "version-id", "review-root"])
def test_adoption_refuses_wrong_identity_and_client_selected_snapshot_root(
    unknown_export_with_review, damage
):
    case = unknown_export_with_review
    payload = adoption_payload(case)
    if damage == "pdf-hash":
        payload["expected_pdf_sha256"] = "0" * 64
    elif damage == "version-id":
        payload["review_version_id"] = "0" * 32
    else:
        payload["review_root"] = str(case["project"])
    status, _ = post(case["active"], "adopt-review-snapshot", payload)
    assert status in {400, 409}
    current = snapshot(case["active"])["active_task"]
    assert current["status"] == "needs_recheck" and current["resume_id"] is None
    assert current["materials_confirmed"] is False and current["worker_ref"] is None
    assert_no_replay(case)


def test_snapshot_projection_requires_same_current_project_and_source(unknown_export_with_review):
    case = unknown_export_with_review
    config = case["config"]
    original = config.read_bytes()
    other = case["project"].parent / "different-cv"
    other.mkdir()
    (other / "main.tex").write_bytes((case["project"] / "main.tex").read_bytes())
    config.write_text(json.dumps({"project_root": str(other), "main": "main.tex"}))
    assert snapshot(case["active"])["review_snapshots"] == []
    assert post(case["active"], "adopt-review-snapshot", adoption_payload(case))[0] == 409
    config.write_bytes(original)
    (case["project"] / "main.tex").write_text("Synthetic changed saved source")
    assert snapshot(case["active"])["review_snapshots"] == []
    assert post(case["active"], "adopt-review-snapshot", adoption_payload(case))[0] == 409
    assert_no_replay(case)
