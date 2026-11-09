"""The actual synthetic backend keeps complete LaTeX and material gates separate."""

import json
import subprocess
import sys
import time
from http.client import HTTPConnection

import pytest
from test_installed_preparation_mode import (
    CHECKOUT,
    assert_backend_diagnostics,
    request,
    start_backend,
    stop_backend,
)

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_flow_store import read_flow_state
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import ApplicationStore


def create_fixture(tmp_path):
    root = tmp_path / "complete synthetic preparation"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(CHECKOUT / "scripts/create_synthetic_flow.py"),
            "--preparation",
            str(root),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["new_model_calls"] == 0
    return root


def snapshot(address):
    status, result = request(address, "GET", "/api/flow/state")
    assert status == 200, result
    return result


def restore_saved_pre_json_task(root, task):
    """Replay only this idle historical task through the actual child backend."""
    assert task["material_contract"] == "content-writing/v1"
    path = root / "runtime/material-preparation/flow.json"
    with ApplicationStore(root / "applications").write_lock():
        state = read_flow_state(path.parent)
        saved = next(row for row in state["tasks"] if row["id"] == task["id"])
        assert saved["revision"] == task["revision"]
        assert all(stage["status"] == "pending" for stage in saved["stages"].values())
        assert saved.pop("material_contract") == "content-writing/v1"
        saved["revision"] = digest(
            {key: value for key, value in saved.items() if key != "revision"}
        )
        helper.atomic_write_json(path, state)


def action(address, token, task, name, **payload):
    status, result = request(
        address,
        "POST",
        "/api/flow/" + name,
        payload={"task_id": task["id"], "task_revision": task["revision"], **payload},
        token=token,
    )
    assert status == 200, result
    return result


def blocked(address, token, task, name, expected_error, **payload):
    status, result = request(
        address,
        "POST",
        "/api/flow/" + name,
        payload={"task_id": task["id"], "task_revision": task["revision"], **payload},
        token=token,
    )
    assert status == 409 and result["error"] == expected_error, result


def wait_task(address, expected):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        task = snapshot(address)["active_task"]
        if task["status"] == expected:
            return task
        assert task["status"] != "failed", task
        time.sleep(0.02)
    raise AssertionError(f"Synthetic stage did not reach {expected}: {task}")


def draft(address, task):
    status, result = request(address, "GET", "/api/flow/drafts/" + task["draft_id"])
    assert status == 200, result
    return result


def pdf_bytes(address, path):
    connection = HTTPConnection(address.hostname, address.port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == 200
        assert response.headers.get_content_type() == "application/pdf"
        return response.read()
    finally:
        connection.close()


def current_source(address):
    return snapshot(address)["group_review"]["live_source_revision"]


def capture(address, token, task):
    return action(
        address,
        token,
        task,
        "capture-group-review",
        expected_source_revision=current_source(address),
    )


def review_groups(address, token, task, groups):
    for group in groups:
        task = action(
            address,
            token,
            task,
            "review-group",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
            group_id=group["id"],
            review_fingerprint=group["review_fingerprint"],
        )
    return task


def export_pdf(address, token, task):
    action(
        address,
        token,
        task,
        "export-pdf",
        draft_id=task["draft_id"],
        draft_sha256=task["draft_sha256"],
    )
    return wait_task(address, "materials_ready")


def confirm_pdf(address, token, task):
    return action(
        address,
        token,
        task,
        "confirm-materials",
        resume_id=task["resume_id"],
        resume_sha256=task["resume_sha256"],
    )


def retained_files(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("shutdown", ["eof", "sigterm"])
def test_backend_complete_latex_review_export_and_independent_confirmation(tmp_path, shutdown):
    root = create_fixture(tmp_path)
    unrelated = tmp_path / "unrelated home"
    unrelated.mkdir()
    base_before = (root / "latex-base/main.tex").read_bytes()
    library_before = (root / "information-library/answers.json").read_bytes()
    process, ready, address = start_backend(root, unrelated)
    try:
        assert ready["capabilities"]["synthetic"]
        assert ready["capabilities"]["worker"] is False
        status, state = request(address, "GET", "/api/state")
        assert status == 200
        token = state["csrf_token"]
        status, result = request(
            address,
            "POST",
            "/api/applications",
            token=token,
            payload={
                "company": "Synthetic Employer",
                "role_title": "Synthetic Python Engineer",
                "job_description": "Python\nunit tests",
            },
        )
        assert status == 201, result
        job = result["application"]
        status, task = request(
            address,
            "POST",
            "/api/flow/create",
            token=token,
            payload={"application_id": job["id"], "application_revision": job["revision"]},
        )
        assert status == 200, task
        # Group review/PDF confirmation exercises an already saved pre-JSON task.
        # The backend's newly created task still declares the current contract.
        restore_saved_pre_json_task(root, task)
        task = snapshot(address)["active_task"]
        action(address, token, task, "start", stage="analysis")
        task = wait_task(address, "analysis_ready")
        analysis_id = task["analysis_id"]
        task = action(
            address,
            token,
            task,
            "bind-latex-base",
            project_root=str(root / "latex-base"),
            main="main.tex",
        )
        action(address, token, task, "start", stage="resume")
        task = wait_task(address, "draft_ready")
        assert task["analysis_id"] == analysis_id
        generated = draft(address, task)
        assert generated["origin"] == "generated_latex"
        assert len(generated["review_groups"]) == 2
        assert not task["materials_confirmed"] and not task["worker_ref"]
        task = action(address, token, task, "begin-group-review")
        prepared = draft(address, task)
        group = prepared["review_groups"][0]
        blocked(
            address,
            token,
            task,
            "review-group",
            "flow_group_preview_required",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
            group_id=group["id"],
            review_fingerprint=group["review_fingerprint"],
        )
        status, disabled = request(
            address,
            "POST",
            "/api/flow/open-prism",
            token=token,
            payload={"task_id": task["id"], "task_revision": task["revision"]},
        )
        assert status == 409 and disabled["error"] == "synthetic_prism_editor_disabled"
        task = capture(address, token, task)
        captured = draft(address, task)
        preview_id = captured["group_preview"]["id"]
        (build_path,) = (root / "runtime").rglob(preview_id + "/build.json")
        build = json.loads(build_path.read_bytes())
        assert build["synthetic"] is True and build["real_compilation"] is False
        fixture_pdf = (root / "synthetic-preview.pdf").read_bytes()
        assert pdf_bytes(address, captured["group_preview"]["preview_url"]) == fixture_pdf
        blocked(
            address,
            token,
            task,
            "export-pdf",
            "flow_factual_review_required",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
        )
        task = review_groups(address, token, task, captured["review_groups"])
        assert task["factual_review"] == "groups_reviewed"
        assert task["resume_id"] is None and not task["materials_confirmed"]
        task = export_pdf(address, token, task)
        assert task["materials_confirmed"] and not task["worker_ref"]
        assert task["material_binding"]["actor"] == "system"
        assert task["material_binding"]["human_reviewed"] is False
        assert not task.get("material_reviews")
        assert pdf_bytes(address, f"/api/flow/resumes/{task['resume_id']}/pdf") == fixture_pdf
        (intent_path,) = (root / "runtime").rglob(task["resume_id"] + "/export-intent.json")
        intent = json.loads(intent_path.read_bytes())
        assert intent["export_configuration"]["synthetic"] is True
        assert intent["export_configuration"]["real_compilation"] is False
        task = confirm_pdf(address, token, task)
        assert task["materials_confirmed"] and not task["worker_ref"]
        first = task
        first_receipts = {row["group_id"]: row for row in first["group_reviews"]}
        changed = captured["review_groups"][1]
        identity = captured["review_groups"][0]
        task = action(
            address,
            token,
            task,
            "edit-review-group",
            payload={
                "group_id": changed["id"],
                "title": changed["title"],
                "latex": changed["rewritten"].replace(
                    "Implemented a Python health-check endpoint and unit tests.",
                    "Implemented unit tests and a Python health-check endpoint.",
                ),
                "source_ids": [row["source_id"] for row in changed["sources"]],
            },
        )
        assert task["draft_id"] != first["draft_id"]
        assert not task["materials_confirmed"] and task["resume_id"] is None
        assert [row["group_id"] for row in task["group_reviews"]] == [identity["id"]]
        assert (
            task["group_reviews"][0]["inherited_from"]["receipt_id"]
            == first_receipts[identity["id"]]["id"]
        )
        assert all(row in task["group_review_history"] for row in first_receipts.values())
        assert task["material_reviews"] == first["material_reviews"]
        task = capture(address, token, task)
        revised = draft(address, task)
        assert {row["group_id"] for row in task["group_reviews"]} == {identity["id"]}
        task = review_groups(
            address,
            token,
            task,
            [row for row in revised["review_groups"] if row["id"] == changed["id"]],
        )
        assert task["factual_review"] == "groups_reviewed" and not task["materials_confirmed"]
        task = export_pdf(address, token, task)
        assert task["resume_id"] != first["resume_id"]
        assert task["resume_sha256"] == first["resume_sha256"]
        assert task["materials_confirmed"]
        assert task["material_binding"]["resume_id"] == task["resume_id"]
        assert task["material_binding"]["human_reviewed"] is False
        assert len(task["material_reviews"]) == 1
        task = confirm_pdf(address, token, task)
        assert task["materials_confirmed"] and len(task["material_reviews"]) == 2
        assert task["material_reviews"][0] == first["material_reviews"][0]
        assert task["material_reviews"][1]["resume_id"] == task["resume_id"]
        assert draft(address, first)["latex_source"] == captured["latex_source"]
        assert (root / "latex-base/main.tex").read_bytes() == base_before
        assert (root / "information-library/answers.json").read_bytes() == library_before
        assert list(unrelated.iterdir()) == []
    finally:
        if shutdown == "sigterm" and process.poll() is None:
            process.terminate()
            assert process.wait(timeout=5) == 0
        stop_backend(process)
    assert process.returncode == 0 and process.stderr.read() == ""
    first_diagnostics = assert_backend_diagnostics(
        root, {process.pid: "signal" if shutdown == "sigterm" else "parent_pipe_eof"}
    )
    retained = retained_files(root)
    reopened, reopened_ready, address = start_backend(root, unrelated)
    try:
        assert reopened_ready["capabilities"]["worker"] is False
        assert snapshot(address)["active_task"] == task
        assert snapshot(address)["active_task"] == task
        assert draft(address, task)["id"] == task["draft_id"]
        assert draft(address, first)["latex_source"] == captured["latex_source"]
        assert pdf_bytes(address, f"/api/flow/resumes/{task['resume_id']}/pdf") == fixture_pdf
        assert pdf_bytes(address, f"/api/flow/resumes/{first['resume_id']}/pdf") == fixture_pdf
    finally:
        stop_backend(reopened)
    assert reopened.returncode == 0 and reopened.stderr.read() == ""
    diagnostics = assert_backend_diagnostics(
        root,
        {
            process.pid: "signal" if shutdown == "sigterm" else "parent_pipe_eof",
            reopened.pid: "parent_pipe_eof",
        },
    )
    assert {path: diagnostics[path] for path in first_diagnostics} == first_diagnostics
    new_diagnostics = {
        path: value for path, value in diagnostics.items() if path not in first_diagnostics
    }
    assert len(new_diagnostics) == 1
    assert retained_files(root) == retained | new_diagnostics
    assert list(unrelated.iterdir()) == []
