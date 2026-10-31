"""Real loopback POST admission with synthetic receipts; no native or browser process."""

import json
from contextlib import contextmanager
from threading import Thread

import pytest
from test_career_portal_http import Portal
from test_installed_write_admission import bytes_under, installed_evidence, prepared_inputs

from career_evidence_graph.career_portal import create_server


@contextmanager
def installed_portal(
    tmp_path, monkeypatch, *, unconfirmed_pdf=False, job_description="Build Python services."
):
    applications, root, career, task = prepared_inputs(tmp_path, job_description=job_description)
    if unconfirmed_pdf:
        from career_evidence_graph.application_worker import digest

        saved = json.loads((root / "flow.json").read_text())
        task = saved["tasks"][0]
        task.update(status="resume_ready", materials_confirmed=False)
        task["revision"] = digest({k: v for k, v in task.items() if k != "revision"})
        (root / "flow.json").write_text(json.dumps(saved))
    options = installed_evidence(monkeypatch, tmp_path)
    server = create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        **options,
    )
    starts = []
    monkeypatch.setattr(server.worker_service, "spawn", lambda: starts.append(True))
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield Portal(server, applications.root, career), task, options, starts
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
        assert not thread.is_alive()


def post(portal, operation, payload):
    status, _, raw = portal.request(
        "POST",
        "/api/flow/" + operation,
        body=json.dumps(payload).encode(),
        headers=portal.write_headers(),
    )
    return status, json.loads(raw)


def business_bytes(portal):
    flow = portal.server.application_flow_service
    return {
        "flow": bytes_under(flow.root),
        "worker": bytes_under(portal.server.worker_service.store.root),
        "applications": bytes_under(portal.applications),
    }


def prepare_payload(task):
    return {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "country": "CHE",
        "send_confirmed": True,
    }


@pytest.mark.parametrize("conflicting", [False, True])
def test_installed_prepare_uses_request_country_for_language_scope(
    tmp_path, monkeypatch, conflicting
):
    with installed_portal(tmp_path, monkeypatch, job_description="German B2 required.") as (
        portal,
        task,
        _options,
        starts,
    ):
        worker = portal.server.worker_service
        for question, scope, value in [
            ("German level", {}, "A1"),
            ("German level", {"country": "CHE"}, "B2"),
            *([("German proficiency CEFR", {"company": "Synthetic"}, "C1")] if conflicting else []),
        ]:
            worker.store.answers.put_answer(
                {"question": question, "scope": scope, "value": value, "state": "confirmed"}
            )
        before = business_bytes(portal)
        status, shown = post(portal, "prepare-worker", prepare_payload(task))
        if conflicting:
            assert status == 409 and shown["error"] == "language_information_required"
            assert business_bytes(portal) == before
        else:
            assert status == 200, shown
            assert worker.store.load()["jobs"][0]["country"] == "CHE"
            assert worker.store.load()["control"] == "paused"
        assert starts == []


@pytest.mark.parametrize(
    "failure", ["accessibility", "screen_recording", "nonce", "responsibility", "stale", "unknown"]
)
def test_prepare_post_uses_current_materials_despite_invalid_native_diagnostic(
    tmp_path, monkeypatch, failure
):
    with installed_portal(tmp_path, monkeypatch) as (portal, task, options, starts):
        receipt = options["native_host_identity"].receipt
        if failure in {"accessibility", "screen_recording"}:
            receipt[failure] = False
        elif failure == "nonce":
            receipt["launch_nonce"] = "synthetic-other-launch"
        elif failure == "responsibility":
            receipt["daemon"]["proxy_responsible_pid"] = 999
        elif failure == "stale":
            receipt["captured_at"] = receipt["daemon"]["checked_at"] = 1
        else:
            receipt["kind"] = "sample"
        status, shown = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200 and shown["status"] == "queued"
        worker = portal.server.worker_service.store.load()
        assert worker["control"] == "paused" and worker.get("runtime") is None
        assert worker["jobs"][0]["application_id"] == task["application_id"]
        assert worker["jobs"][0]["file_sha256"] == task["resume_sha256"]
        assert starts == []


@pytest.mark.parametrize("change", ["permission", "nonce", "configuration"])
def test_prepare_post_ignores_unrelated_diagnostic_change_during_preparation(
    tmp_path, monkeypatch, change
):
    with installed_portal(tmp_path, monkeypatch) as (portal, task, options, starts):
        flow = portal.server.application_flow_service
        original = flow._checked
        reached = []

        def change_after_scan(*arguments):
            result = original(*arguments)
            reached.append(True)
            if change == "permission":
                options["native_host_identity"].receipt["accessibility"] = False
            elif change == "nonce":
                options["native_host_identity"].receipt["launch_nonce"] = "synthetic-other-launch"
            else:
                monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", "/synthetic/changed-codex")
            return result

        monkeypatch.setattr(flow, "_checked", change_after_scan)
        status, shown = post(portal, "prepare-worker", prepare_payload(task))
        assert reached
        assert status == 200 and shown["status"] == "queued"
        state = portal.server.worker_service.store.load()
        assert state["control"] == "paused" and state.get("runtime") is None
        assert state["jobs"][0]["file_sha256"] == task["resume_sha256"]
        assert starts == []


def test_valid_prepare_and_explicit_resume_posts_admit_synthetic_command_but_not_submit(
    tmp_path, monkeypatch
):
    with installed_portal(tmp_path, monkeypatch) as (portal, task, _, starts):
        status, prepared = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 200 and prepared["status"] == "queued"
        worker = portal.server.worker_service
        assert worker.store.load()["control"] == "paused" and starts == []
        payload = {
            "task_id": task["id"],
            "task_revision": prepared["revision"],
            "operation": "submit",
            "payload": {"controller": "synthetic-controller"},
        }
        before = business_bytes(portal)
        status, shown = post(portal, "worker-action", payload)
        assert status == 400 and shown["error"] == "invalid_flow_request"
        assert business_bytes(portal) == before and starts == []
        status, resumed = post(portal, "worker-action", payload | {"operation": "resume"})
        assert status == 200 and resumed["worker_ref"]["status"] == "queued"
        state = worker.store.load()
        assert state["control"] == "running" and starts == [True]
        assert state.get("runtime") is None
        assert not state["jobs"][0].get("page_observation")


@pytest.mark.parametrize(
    "change,error_code",
    [
        # A career source revision is not one of them (APP-04).
        ("target", "conflict"),
        ("pdf", "flow_materials_changed"),
        ("task", "conflict"),
    ],
)
def test_prepare_post_rejects_real_input_changes_before_saving_approval(
    tmp_path, monkeypatch, change, error_code
):
    with installed_portal(tmp_path, monkeypatch) as (portal, task, _, starts):
        flow = portal.server.application_flow_service
        original = flow._checked
        retained = []

        def change_before_locked_check(*arguments):
            assert not retained
            if change == "target":
                application = flow.applications.get_application(task["application_id"])
                flow.applications.update_application(
                    application["id"],
                    {"url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000002"},
                    application["revision"],
                )
            elif change == "pdf":
                (flow.root / "resumes" / task["resume_id"] / "resume.pdf").write_bytes(
                    b"%PDF-1.4 synthetic changed PDF bytes"
                )
            else:
                saved = flow._load()
                saved["tasks"][0]["status"] = "cancelled"
                flow._save(saved)
            retained.append(business_bytes(portal))
            return original(*arguments)

        monkeypatch.setattr(flow, "_checked", change_before_locked_check)
        status, shown = post(portal, "prepare-worker", prepare_payload(task))
        assert status == 409 and shown["error"] == error_code, shown
        assert business_bytes(portal) == retained[0]
        assert starts == []
        assert portal.server.worker_service.store.load()["jobs"] == []


@pytest.mark.parametrize("failure", [None, "permission", "verification"])
def test_installed_prepare_auto_binds_exact_pdf_and_remains_paused(tmp_path, monkeypatch, failure):
    with installed_portal(tmp_path, monkeypatch, unconfirmed_pdf=True) as (
        portal,
        task,
        options,
        starts,
    ):
        from career_evidence_graph.career_portal_data import PortalDataError

        if failure == "permission":
            options["native_host_identity"].receipt["accessibility"] = False
        elif failure == "verification":

            def changed_pdf(_):
                raise PortalDataError("flow_materials_changed", "Changed PDF", 409)

            portal.server.application_flow_service.callbacks["verify_materials"] = changed_pdf
        before = business_bytes(portal)
        status, prepared = post(portal, "prepare-worker", prepare_payload(task))
        if failure == "verification":
            assert status == 409 and prepared["error"] == "flow_materials_changed"
            assert business_bytes(portal) == before and starts == []
            return
        assert status == 200, prepared
        assert prepared["status"] == "queued" and prepared["materials_confirmed"]
        assert prepared["material_binding"]["pdf_sha256"] == task["resume_sha256"]
        assert prepared["material_binding"]["actor"] == "system"
        assert prepared["material_binding"]["human_reviewed"] is False
        assert prepared.get("material_reviews", []) == task.get("material_reviews", [])
        state = portal.server.worker_service.store.load()
        assert state["control"] == "paused" and starts == []
        assert not state.get("runtime") and not state["jobs"][0].get("page_observation")
