"""Real loopback HTTP contracts using disposable synthetic private workspaces."""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any

import pytest

from career_evidence_graph.career_portal import create_server


@dataclass
class Portal:
    server: HTTPServer
    applications: Path
    career: Path

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def state(self) -> dict[str, Any]:
        status, _, body = self.request("GET", "/api/state")
        assert status == 200, body
        return json.loads(body)

    def write_headers(self) -> dict[str, str]:
        return {
            "Origin": self.origin,
            "X-CSRF-Token": self.state()["csrf_token"],
            "Content-Type": "application/json",
        }


@contextmanager
def _running_portal(
    applications: Path,
    career: Path,
    *,
    worker_root: Path | None = None,
    flow_root: Path | None = None,
    flow_analyzer=None,
    flow_resume_factory=None,
    flow_intake_factory=None,
    application_processed_label=None,
    information_library_root=None,
    preparation_only=False,
    worker_fixtures=False,
    worker_headless=False,
) -> Iterator[Portal]:
    options = {"flow_root": flow_root} if flow_root is not None else {}
    if flow_analyzer is not None:
        options["flow_analyzer"] = flow_analyzer
    if flow_resume_factory is not None:
        options["flow_resume_factory"] = flow_resume_factory
    if flow_intake_factory is not None:
        options["flow_intake_factory"] = flow_intake_factory
    server = create_server(
        applications,
        career,
        port=0,
        write_admission_policy="development",
        worker_root=worker_root,
        worker_fixtures=worker_fixtures,
        worker_headless=worker_headless,
        preparation_only=preparation_only,
        information_library_root=information_library_root,
        **(
            {"application_processed_label": application_processed_label}
            if application_processed_label is not None
            else {}
        ),
        **options,
    )
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield Portal(server, applications, career)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive()


def test_single_job_task_http_persists_without_url_or_worker(portal: Portal, tmp_path) -> None:
    from career_evidence_graph.career_portal_data import ApplicationStore

    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Build reliable Python services.",
        }
    )
    flow_root = tmp_path / "synthetic-flow"
    with _running_portal(portal.applications, portal.career, flow_root=flow_root) as active:
        payload = json.dumps(
            {
                "application_id": job["id"],
                "application_revision": job["revision"],
                "inputs": {"jd_revision": "synthetic-jd", "sources_revision": "synthetic-sources"},
            }
        ).encode()
        denied, _, _ = active.request("POST", "/api/flow/create", body=payload)
        assert denied == 403
        status, _, raw = active.request(
            "POST", "/api/flow/create", body=payload, headers=active.write_headers()
        )
        assert status == 409, raw
        assert json.loads(raw)["error"] == "flow_inputs_mismatch"
        payload = json.dumps(
            {"application_id": job["id"], "application_revision": job["revision"]}
        ).encode()
        status, _, raw = active.request(
            "POST", "/api/flow/create", body=payload, headers=active.write_headers()
        )
        assert status == 200, raw
        task = json.loads(raw)
        assert task["inputs"]["sources_revision"]
        duplicate, _, raw = active.request(
            "POST", "/api/flow/create", body=payload, headers=active.write_headers()
        )
        assert duplicate == 200
        assert json.loads(raw)["id"] == task["id"]
        status, _, raw = active.request(
            "POST",
            "/api/flow/cancel",
            body=json.dumps({"task_id": task["id"], "task_revision": "outdated"}).encode(),
            headers=active.write_headers(),
        )
        assert status == 409
        assert json.loads(raw)["error"] == "conflict"
        status, _, raw = active.request(
            "POST",
            "/api/flow/bind-worker",
            body=json.dumps({"task_id": task["id"], "task_revision": task["revision"]}).encode(),
            headers=active.write_headers(),
        )
        assert status == 400
        assert json.loads(raw)["error"] == "invalid_flow_request"
    with _running_portal(portal.applications, portal.career, flow_root=flow_root) as reopened:
        status, _, raw = reopened.request("GET", "/api/flow/state")
        assert status == 200
        assert [row["id"] for row in json.loads(raw)["tasks"]] == [task["id"]]
        status, _, _ = reopened.request("GET", "/api/flow/../../outside")
        assert status == 404


def test_single_job_http_model_is_async_and_rejects_changed_sources(
    portal: Portal, tmp_path
) -> None:
    from career_evidence_graph.career_portal_data import ApplicationStore

    job = ApplicationStore(portal.applications).create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Use Python."}
    )
    entered, release = Event(), Event()
    calls = []
    source = portal.career / "sources/synthetic.md"
    source.parent.mkdir()
    source.write_text("Original synthetic career document.")

    def model_double(task):
        calls.append(task["id"])
        entered.set()
        assert release.wait(3)
        return {"id": "synthetic-analysis"}

    try:
        with _running_portal(
            portal.applications, portal.career, flow_root=tmp_path / "background-flow"
        ) as active:
            active.server.application_flow_service.callbacks["analysis"] = model_double
            status, _, raw = active.request(
                "POST",
                "/api/flow/create",
                body=json.dumps(
                    {"application_id": job["id"], "application_revision": job["revision"]}
                ).encode(),
                headers=active.write_headers(),
            )
            assert status == 200, raw
            task = json.loads(raw)
            payload = json.dumps(
                {"task_id": task["id"], "task_revision": task["revision"], "stage": "analysis"}
            ).encode()
            for _ in range(2):
                status, _, raw = active.request(
                    "POST", "/api/flow/start", body=payload, headers=active.write_headers()
                )
                assert status == 200, raw
                assert json.loads(raw)["id"] == task["id"]
            assert entered.wait(2)
            assert calls == [task["id"]]
            assert not release.is_set()
            source.write_text("Changed synthetic career document.")
            release.set()
            deadline = time.monotonic() + 3
            observed = {}
            while time.monotonic() < deadline:
                status, _, raw = active.request("GET", "/api/flow/state")
                assert status == 200
                observed = json.loads(raw)["active_task"]
                if observed["status"] == "stale":
                    break
                time.sleep(0.01)
            assert observed["status"] == "stale"
            assert observed["analysis_id"] is None
            status, _, raw = active.request(
                "POST",
                "/api/flow/update-inputs",
                body=json.dumps(
                    {
                        "task_id": task["id"],
                        "task_revision": observed["revision"],
                        "application_revision": job["revision"],
                    }
                ).encode(),
                headers=active.write_headers(),
            )
            assert status == 200, raw
            refreshed = json.loads(raw)
            assert refreshed["id"] == task["id"]
            assert refreshed["inputs"]["sources_revision"] != task["inputs"]["sources_revision"]
            assert calls == [task["id"]]
    finally:
        release.set()


@pytest.mark.parametrize("with_benchmark", [False, True])
def test_single_job_http_analyzes_full_jd_without_profile_url_or_worker(
    portal: Portal, tmp_path, monkeypatch, with_benchmark
) -> None:
    from functools import partial

    from test_application_benchmark import baseline, write_baseline
    from test_application_match import model_output, model_runner

    from career_evidence_graph.application_match import analyze_job, match_configuration_revision
    from career_evidence_graph.application_resume import career_source_snapshot
    from career_evidence_graph.application_worker import digest
    from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog

    applications = ApplicationStore(portal.applications)
    job = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Python is required. Rust is preferred.",
        }
    )
    source = portal.career / "contributions/python.md"
    source.parent.mkdir()
    source.write_text(
        "# Synthetic Python service\n\n## Scope\nImplemented a Python service.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n"
    )
    sources = career_source_snapshot(CareerCatalog(portal.career))
    assert sources["profile"] is None
    output = model_output(sources)
    output["requirements"].append(
        {
            "text": "Rust",
            "importance": "preferred",
            "judgment": "unknown",
            "hard_condition": False,
            "explanation": "Documentary evidence is unavailable.",
            "source_ids": [],
            "citations": [],
            "claim_scope": "unknown",
        }
    )
    calls = []
    analyzer = partial(analyze_job, runner=model_runner(output, calls))
    if with_benchmark:
        cohort = baseline()
        cohort.update(
            source_snapshot_revision=sources["revision"],
            configuration_revision=match_configuration_revision(),
        )
        cohort["revision"] = digest({k: v for k, v in cohort.items() if k != "revision"})
        benchmark_path = write_baseline(portal.career, cohort)
        assert (
            career_source_snapshot(CareerCatalog(portal.career))["revision"] == sources["revision"]
        )

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "analysis-flow",
        flow_analyzer=analyzer,
    ) as active:
        status, _, raw = active.request(
            "POST",
            "/api/flow/create",
            body=json.dumps(
                {"application_id": job["id"], "application_revision": job["revision"]}
            ).encode(),
            headers=active.write_headers(),
        )
        assert status == 200, raw
        task = json.loads(raw)
        status, _, raw = active.request(
            "POST",
            "/api/flow/start",
            body=json.dumps(
                {"task_id": task["id"], "task_revision": task["revision"], "stage": "analysis"}
            ).encode(),
            headers=active.write_headers(),
        )
        assert status == 200, raw
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status, _, raw = active.request("GET", "/api/flow/state")
            assert status == 200
            completed = json.loads(raw)["active_task"]
            if completed["status"] == "analysis_ready":
                break
            time.sleep(0.01)
        assert completed["status"] == "analysis_ready"
        assert len(calls) == 2
        assert job["job_description"] in calls[-1][-1]
        assert completed["analysis_id"]
        assert completed["artifacts"][-1]["result"]["score"] == {
            "lower": 75,
            "upper": 100,
            "coverage": 75,
            "eligibility": "not_specified",
        }
        comparison = completed["artifacts"][-1]["result"]["historical_reference"]
        assert comparison["status"] == ("ready" if with_benchmark else "missing")
        if with_benchmark:
            assert comparison["comparisons"][0]["position"] == "overlaps"
            assert comparison["reference_range"] == {"lower": 50, "upper": 75}
        repeat = json.dumps(
            {"task_id": task["id"], "task_revision": completed["revision"], "stage": "analysis"}
        ).encode()
        status, _, raw = active.request(
            "POST", "/api/flow/start", body=repeat, headers=active.write_headers()
        )
        assert status == 200, raw
        assert json.loads(raw)["analysis_id"] == completed["analysis_id"]
        assert len(calls) == 2
        if with_benchmark:
            cohort["cases"][0]["limitations"].append("A new historical event was verified.")
            cohort["revision"] = digest({k: v for k, v in cohort.items() if k != "revision"})
            benchmark_path.write_text(json.dumps(cohort))
            status, _, raw = active.request(
                "POST", "/api/flow/start", body=repeat, headers=active.write_headers()
            )
            assert status == 200, raw
            retained = json.loads(raw)
            assert retained["analysis_id"] == completed["analysis_id"]
            assert retained["inputs"] == completed["inputs"]
            assert retained["artifacts"] == completed["artifacts"]
            assert len(calls) == 2
        monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", "/synthetic/changed/codex")
        status, _, raw = active.request(
            "POST", "/api/flow/start", body=repeat, headers=active.write_headers()
        )
        assert status == 200, raw
        retained = json.loads(raw)
        assert retained["analysis_id"] == completed["analysis_id"]
        assert retained["inputs"] == completed["inputs"]
        assert retained["artifacts"] == completed["artifacts"]
        assert len(calls) == 2
        assert applications.get_application(job["id"])["status"] == "drafting"


def test_gmail_intake_http_reads_in_background_and_selects_a_source_bound_job(
    portal: Portal, tmp_path
):
    from test_application_intake import message, page

    from career_evidence_graph.application_intake import ApplicationIntakeService
    from career_evidence_graph.career_portal_data import ApplicationStore

    entered, release = Event(), Event()
    reads = []
    applications = ApplicationStore(portal.applications)
    before = len(applications.list_applications())

    def reader(directory, *, max_results):
        reads.append(max_results)
        entered.set()
        assert release.wait(3)
        directory.mkdir()
        return {"status": "readable", "emails": [message()], "provenance": {}}

    def factory(applications, root):
        return ApplicationIntakeService(applications, root, reader=reader, fetcher=page)

    try:
        with _running_portal(
            portal.applications,
            portal.career,
            flow_root=tmp_path / "recommendation-flow",
            flow_intake_factory=factory,
        ) as active:
            status, _, raw = active.request("GET", "/api/recommendations/state")
            assert status == 200 and json.loads(raw)["status"] == "idle"
            assert reads == []
            status, _, raw = active.request(
                "POST",
                "/api/recommendations/refresh",
                body=b"{}",
                headers={"Content-Type": "application/json"},
            )
            assert status == 403 and reads == []
            payload = b'{"max_results":1,"max_candidates":2}'
            for _ in range(2):
                status, _, raw = active.request(
                    "POST",
                    "/api/recommendations/refresh",
                    body=payload,
                    headers=active.write_headers(),
                )
                assert status == 200 and json.loads(raw)["status"] == "running"
            assert entered.wait(2)
            assert reads == [1]
            release.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                status, _, raw = active.request("GET", "/api/recommendations/state")
                state = json.loads(raw)
                if state["status"] == "complete":
                    break
                time.sleep(0.01)
            assert state["status"] == "complete"
            assert len(applications.list_applications()) == before + 1
            recommendation = state["recommendations"][0]
            assert recommendation["selection_status"] == "saved"
            saved_id = recommendation["existing_application"]["id"]
            assert active.server.application_flow_service.snapshot()["tasks"] == []
            assert active.server.worker_service is None
            assert not list((tmp_path / "recommendation-flow").rglob("model-result.json"))
            status, _, raw = active.request(
                "POST",
                "/api/recommendations/select",
                body=json.dumps(
                    {
                        "id": recommendation["id"],
                        "revision": recommendation["revision"],
                    }
                ).encode(),
                headers=active.write_headers(),
            )
            assert status == 200, raw
            selected = json.loads(raw)
            assert selected["created"] is False
            job = selected["application"]
            assert job["id"] == saved_id
            assert job["company"] == "Synthetic Labs"
            assert job["job_description"] == page(job["url"])["body_text"]
            assert len(applications.list_applications()) == before + 1
            status, _, raw = active.request(
                "POST",
                "/api/flow/create",
                body=json.dumps(
                    {
                        "application_id": job["id"],
                        "application_revision": job["revision"],
                    }
                ).encode(),
                headers=active.write_headers(),
            )
            assert status == 200 and json.loads(raw)["job_description"] == job["job_description"]
    finally:
        release.set()


@pytest.mark.parametrize("has_profile", [True, False])
def test_single_job_http_previews_imported_latex_without_inventing_factual_acceptance(
    portal: Portal, tmp_path, has_profile
):
    from test_application_flow import wait_for
    from test_pdf_export_http import create_authorized_latex, export_payload
    from test_preparation_entry import post

    from career_evidence_graph.career_portal_data import ApplicationStore

    applications = ApplicationStore(portal.applications)
    job = applications.create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Use Python."}
    )
    if has_profile:
        profile = portal.career / "sources/profile.json"
        profile.parent.mkdir()
        profile.write_text(json.dumps({"name": "Synthetic Person"}))
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "materials-flow",
        preparation_only=True,
    ) as active:
        task = create_authorized_latex(active, job)
        status, _ = post(active, "export-pdf", export_payload(task))
        assert status == 200
        task = wait_for(
            active.server.application_flow_service,
            task["id"],
            lambda row: row["status"] == "resume_ready",
        )
        assert task["origin"] == "existing_latex"
        result = task["artifacts"][-1]["result"]
        store = active.server.application_resume_store
        pdf_path = store.root / result["id"] / "resume.pdf"
        pdf_bytes = pdf_path.read_bytes()
        status, headers, raw = active.request("GET", result["preview_url"])
        assert status == 200 and raw == pdf_bytes
        assert headers["Content-Type"] == "application/pdf"
        assert headers["X-Frame-Options"] == "SAMEORIGIN"
        assert "frame-ancestors 'self'" in headers["Content-Security-Policy"]
        status, headers, _ = active.request("GET", "/api/flow/resumes/missing/pdf")
        assert status == 404
        assert headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        payload = {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "resume_id": result["id"],
            "resume_sha256": result["pdf_sha256"],
        }
        pdf_path.write_bytes(pdf_bytes + b" changed after preview")
        assert active.request("GET", result["preview_url"])[0] == 409
        pdf_path.write_bytes(pdf_bytes)
        assert active.request("GET", result["preview_url"])[0] == 200
        status, rejected = post(active, "confirm-materials", payload)
        assert status == 409 and rejected["error"] == "flow_factual_review_required"
        assert not task["materials_confirmed"]
        assert applications.get_application(job["id"])["status"] == "drafting"
        assert not list(store.root.rglob("resume.html"))


@pytest.mark.parametrize(
    "mutation,expected_error",
    [("before_callback", "flow_inputs_stale"), ("adapter_result", "flow_analysis_mismatch")],
)
def test_analysis_cannot_adopt_a_different_jd_when_the_note_is_restored(
    portal: Portal, tmp_path, mutation, expected_error
) -> None:
    from test_application_match import model_output, model_runner

    from career_evidence_graph.application_match import analyze_job
    from career_evidence_graph.application_resume import career_source_snapshot
    from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog

    applications = ApplicationStore(portal.applications)
    job = applications.create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Original Python JD."}
    )
    source = portal.career / "contributions/python.md"
    source.parent.mkdir()
    source.write_text(
        "# Python\n\n## Scope\nImplemented a Python service.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n"
    )
    snapshot = career_source_snapshot(CareerCatalog(portal.career))
    process = model_runner(model_output(snapshot), [])

    def change_jd(description):
        current = applications.get_application(job["id"])
        return applications.update_application(
            job["id"], {"job_description": description}, current["revision"]
        )

    def runner(config, prompt, **kwargs):
        change_jd(job["job_description"])
        return process(config, prompt, **kwargs)

    def analyzer(application, sources, directory):
        if mutation == "adapter_result":
            application = change_jd("Changed Python JD.")
        return analyze_job(application, sources, directory, runner=runner)

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "aba-flow",
        flow_analyzer=analyzer,
    ) as active:
        service = active.server.application_flow_service
        original_callback = service.callbacks["analysis"]

        def callback(task):
            if mutation == "before_callback":
                change_jd("Changed Python JD.")
            return original_callback(task)

        service.callbacks["analysis"] = callback
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        deadline = time.monotonic() + 3
        observed = {}
        while time.monotonic() < deadline:
            observed = service.snapshot(task["id"])["active_task"]
            if observed["status"] in {"analysis_ready", "failed", "stale"}:
                break
            time.sleep(0.01)
        assert observed["analysis_id"] is None
        assert observed["stages"]["analysis"]["error_code"] == expected_error


@pytest.fixture
def portal(tmp_path: Path) -> Iterator[Portal]:
    applications = tmp_path / "synthetic-applications"
    applications.mkdir()
    career = tmp_path / "synthetic-career"
    career.mkdir()
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    (career / ".gitignore").write_text(".career-evidence/raw/\n", encoding="utf-8")
    with _running_portal(applications, career) as instance:
        yield instance


def test_only_single_job_pdf_allows_same_origin_frames(portal: Portal, tmp_path: Path) -> None:
    worker_root = tmp_path / "legacy-worker"
    identifier = "a" * 32
    pdf = worker_root / "resumes" / identifier / "resume.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 Synthetic legacy document")
    with _running_portal(portal.applications, portal.career, worker_root=worker_root) as active:
        for path, expected_status in (
            ("/", 200),
            ("/api/state", 200),
            ("/static/app.js", 200),
            (f"/api/resumes/{identifier}/pdf", 200),
            ("/api/resumes/missing/pdf", 404),
        ):
            status, headers, _ = active.request(
                "GET",
                path + "?allow_same_origin_frame=true",
                headers={
                    "X-Allow-Same-Origin-Frame": "true",
                    "X-Frame-Options": "SAMEORIGIN",
                    "Content-Security-Policy": "frame-ancestors *",
                },
            )
            assert status == expected_status
            assert headers["X-Frame-Options"] == "DENY"
            assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_loopback_state_has_private_response_headers_and_process_csrf(portal: Portal) -> None:
    assert portal.server.server_address[0] == "127.0.0.1"
    status, headers, body = portal.request("GET", "/api/state")
    assert status == 200
    state = json.loads(body)
    assert {"applications", "evidence", "statuses", "tracks", "connections", "csrf_token"} <= set(
        state
    )
    assert isinstance(state["csrf_token"], str) and len(state["csrf_token"]) >= 32
    assert state["csrf_token"] == portal.state()["csrf_token"]
    assert "no-store" in headers.get("Cache-Control", "")
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert "Access-Control-Allow-Origin" not in headers
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")
    assert headers.get("Referrer-Policy") == "no-referrer"


def test_public_site_reads_only_selected_presentation_and_keeps_errors_private(
    portal: Portal,
) -> None:
    status, _, body = portal.request("GET", "/api/public-site")
    assert status == 404
    assert str(portal.career).encode() not in body
    source = portal.career / "reports/public-site/site-content.json"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "publication_status": "public",
                "profile": {"name": "Synthetic Public Person"},
            }
        )
    )
    status, headers, body = portal.request("GET", "/api/public-site")
    assert status == 200
    assert json.loads(body)["profile"]["name"] == "Synthetic Public Person"
    assert "no-store" in headers["Cache-Control"]
    source.write_text('{"private_note": "Synthetic confidential note"}')
    status, _, body = portal.request("GET", "/api/public-site")
    assert status == 404
    assert b"confidential" not in body


def test_screening_is_read_only_derived_state(portal: Portal) -> None:
    from career_evidence_graph.career_portal_data import ApplicationStore

    store = ApplicationStore(portal.applications)
    app = store.create_application({"company": "Synthetic", "role_title": "AI Engineer"})
    before = {path: path.read_bytes() for path in portal.applications.rglob("*") if path.is_file()}
    shown = next(row for row in portal.state()["applications"] if row["id"] == app["id"])
    assert shown["screening"]["target_relevant"]
    assert shown["screening"]["category"] == "manual"
    assert shown["screening"]["review_reasons"]
    assert "screening" not in store.get_application(app["id"])
    assert before == {
        path: path.read_bytes() for path in portal.applications.rglob("*") if path.is_file()
    }


@pytest.mark.parametrize("scope_kind", ["application_id", "country", "company"])
def test_screening_uses_job_language_exception_without_changing_library(portal, scope_kind):
    from career_evidence_graph.career_portal_data import ApplicationStore

    with _running_portal(
        portal.applications, portal.career, worker_root=portal.career.parent / "language-worker"
    ) as instance:
        store = ApplicationStore(instance.applications)
        jobs = [
            store.create_application(
                {
                    "company": f"Synthetic language {index}",
                    "role_title": "AI Engineer",
                    "job_description": "German B2 required.",
                    "location": "Zurich, Switzerland" if index == 1 else "Boston, USA",
                    "url": f"https://jobs.lever.co/synthetic/00000000-0000-0000-0000-{index:012d}",
                }
            )
            for index in (1, 2)
        ]
        answers = instance.server.worker_service.store.answers
        context = {"application_id": jobs[0]["id"], "country": "CHE", "company": jobs[0]["company"]}
        for scope, value in [({}, "A1"), ({scope_kind: context[scope_kind]}, "B2")]:
            answers.put_answer(
                {
                    "question": "German proficiency CEFR",
                    "value": value,
                    "scope": scope,
                    "state": "confirmed",
                }
            )
        before = answers.answers_path.read_bytes()
        shown = {row["id"]: row["screening"] for row in instance.state()["applications"]}
        assert shown[jobs[0]["id"]]["language_mismatch"] is False
        assert shown[jobs[1]["id"]]["language_mismatch"] is True
        assert answers.answers_path.read_bytes() == before


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("failure", ["portal", "os", "value", "key", "type", "runtime", "missing"])
def test_application_returns_a_saved_receipt_when_screening_fails(
    portal, monkeypatch, method, failure
):
    from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

    store = ApplicationStore(portal.applications)
    payload = {"company": "Synthetic", "role_title": "AI Engineer"}
    path = "/api/applications"
    previous = None
    if method == "PATCH":
        previous = store.create_application(payload)
        path += "/" + previous["id"]
        payload = {"revision": previous["revision"], "notes": "Changed synthetic note."}
    headers = portal.write_headers()

    def unavailable(*args, **kwargs):
        if failure == "missing":
            return []
        error = {
            "portal": PortalDataError(
                "synthetic-screening-error", "Synthetic private failure.", 503
            ),
            "os": OSError("Synthetic private failure."),
            "value": ValueError("Synthetic private failure."),
            "key": KeyError("Synthetic private failure."),
            "type": TypeError("Synthetic private failure."),
            "runtime": RuntimeError("Synthetic private failure."),
        }[failure]
        raise error

    with monkeypatch.context() as faults:
        faults.setattr("career_evidence_graph.career_portal.screen_applications", unavailable)
        status, _, body = portal.request(
            method, path, body=json.dumps(payload).encode(), headers=headers
        )

    assert status == (201 if method == "POST" else 200), body
    response = json.loads(body)
    app = response["application"]
    assert app == store.get_application(app["id"])
    assert len(store.list_applications()) == 1
    if previous:
        assert app["id"] == previous["id"]
        assert app["revision"] != previous["revision"]
        assert app["notes"] == payload["notes"]
    assert response["screening_warning"]["code"] == "screening_unavailable"
    assert "已保存" in response["screening_warning"]["message"]
    assert b"Synthetic private failure" not in body
    assert "screening" not in app
    shown = portal.state()["applications"]
    assert len(shown) == 1 and shown[0]["revision"] == app["revision"]
    assert "screening" in shown[0]
    assert "screening_warning" not in shown[0]


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("source", ["other-note", "answer-library"])
def test_saved_receipt_survives_corrupt_screening_sources(portal, method, source):
    from career_evidence_graph.career_portal_data import ApplicationStore

    worker_root = portal.career.parent / "synthetic-worker"
    with _running_portal(portal.applications, portal.career, worker_root=worker_root) as instance:
        store = ApplicationStore(instance.applications)
        payload = {"company": "Synthetic", "role_title": "AI Engineer"}
        path = "/api/applications"
        previous = None
        if method == "PATCH":
            previous = store.create_application(payload)
            path += "/" + previous["id"]
            payload = {"revision": previous["revision"], "notes": "Saved synthetic edit."}
        headers = instance.write_headers()
        if source == "other-note":
            corrupt = instance.applications / "synthetic-corrupt.md"
            original = None
            damaged = b"---\ntype: job_application\nstatus: drafting\nstatus: rejected\n---\n"
        else:
            corrupt = instance.server.worker_service.store.answers.answers_path
            original = corrupt.read_bytes()
            damaged = b'{"Synthetic private answer library sentinel":'
        corrupt.write_bytes(damaged)

        status, _, body = instance.request(
            method, path, body=json.dumps(payload).encode(), headers=headers
        )

        assert status == (201 if method == "POST" else 200), body
        response = json.loads(body)
        app = response["application"]
        assert app == store.get_application(app["id"])
        assert response["screening_warning"]["code"] == "screening_unavailable"
        assert b"sentinel" not in body
        assert str(corrupt).encode() not in body
        assert corrupt.read_bytes() == damaged
        assert instance.server.worker_service.process is None
        if previous:
            assert app["id"] == previous["id"] and app["revision"] != previous["revision"]
            assert app["notes"] == payload["notes"]
        if original is None:
            corrupt.unlink()
        else:
            corrupt.write_bytes(original)
        assert len(instance.state()["applications"]) == 1


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_storage_failure_still_returns_an_unsaved_error(portal, monkeypatch, method):
    from career_evidence_graph.career_portal_data import ApplicationStore

    store = ApplicationStore(portal.applications)
    payload = {"company": "Synthetic", "role_title": "Engineer"}
    path = "/api/applications"
    if method == "PATCH":
        app = store.create_application(payload)
        path += "/" + app["id"]
        payload = {"revision": app["revision"], "notes": "Unsaved synthetic edit."}
    headers = portal.write_headers()
    before = {
        note: note.read_bytes()
        for note in portal.applications.glob("*")
        if note.suffix in {".md", ".json"}
    }

    if method == "PATCH":
        assert before

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic private storage failure.")

    monkeypatch.setattr(
        ApplicationStore,
        "create_application" if method == "POST" else "update_application",
        unavailable,
    )
    status, _, body = portal.request(
        method, path, body=json.dumps(payload).encode(), headers=headers
    )
    assert status == 500
    assert json.loads(body)["error"] == "save_failed"
    assert b"Synthetic private storage failure" not in body
    assert "screening_warning" not in json.loads(body)
    assert {
        note: note.read_bytes()
        for note in portal.applications.glob("*")
        if note.suffix in {".md", ".json"}
    } == before


def test_selecting_copied_applications_keeps_crud_and_rejects_the_old_runtime(
    portal: Portal, tmp_path
):
    worker_root = tmp_path / "worker"
    with _running_portal(portal.applications, portal.career, worker_root=worker_root) as original:
        status, _, body = original.request(
            "POST",
            "/api/applications",
            body=json.dumps({"company": "Original", "role_title": "Engineer"}).encode(),
            headers=original.write_headers(),
        )
        assert status == 201
        application_id = json.loads(body)["application"]["id"]
    copied = tmp_path / "copied-applications"
    shutil.copytree(portal.applications, copied)
    original_records = {path.name: path.read_bytes() for path in portal.applications.glob("*.json")}
    runtime_bytes = {
        path.relative_to(worker_root): path.read_bytes()
        for path in worker_root.rglob("*")
        if path.is_file()
    }
    with _running_portal(copied, portal.career, worker_root=worker_root) as switched:
        state = switched.state()
        assert state["applications"][0]["id"] == application_id
        status, _, body = switched.request("GET", "/api/worker/state")
        assert status == 200
        assert json.loads(body)["enabled"] is False
        assert json.loads(body)["error"] == "runtime_applications_mismatch"
        status, _, body = switched.request(
            "POST",
            "/api/worker/resume",
            body=b'{"controller":"synthetic-controller"}',
            headers=switched.write_headers(),
        )
        assert status == 409
        assert json.loads(body)["error"] == "runtime_applications_mismatch"
        status, _, _ = switched.request(
            "POST",
            "/api/applications",
            body=json.dumps({"company": "New directory", "role_title": "Engineer"}).encode(),
            headers=switched.write_headers(),
        )
        assert status == 201
        assert len(switched.state()["applications"]) == 2
    assert len(list(portal.applications.glob("*.json"))) == 1
    assert not list(portal.applications.glob("*.md"))
    assert {
        path.name: path.read_bytes() for path in portal.applications.glob("*.json")
    } == original_records
    assert {
        path.relative_to(worker_root): path.read_bytes()
        for path in worker_root.rglob("*")
        if path.is_file()
    } == runtime_bytes


@pytest.mark.parametrize("failure", [ValueError, OSError])
def test_single_flow_keeps_material_routes_when_worker_is_unavailable(
    portal: Portal, tmp_path, monkeypatch, failure
):
    def unavailable(*args, **kwargs):
        raise failure("private worker diagnostic must not leave the server")

    monkeypatch.setattr("career_evidence_graph.application_runtime.WorkerService", unavailable)
    with _running_portal(
        portal.applications,
        portal.career,
        worker_root=tmp_path / "worker",
        flow_root=tmp_path / "flow",
    ) as active:
        assert active.state()["connections"] == {"applications": True, "career": True}
        status, _, body = active.request("GET", "/api/flow/state")
        assert status == 200 and b"private worker diagnostic" not in body
        state = json.loads(body)
        assert state["enabled"] is True
        assert state["capabilities"]["worker"] is False
        assert state["worker"]["error"] == "flow_worker_unavailable"
        status, _, body = active.request("GET", "/")
        assert status == 200


def test_single_flow_reports_missing_cli_without_blocking_saved_materials(
    portal: Portal, tmp_path, monkeypatch
):
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(tmp_path / "missing-codex"))
    with _running_portal(portal.applications, portal.career, flow_root=tmp_path / "flow") as active:
        status, _, body = active.request("GET", "/api/flow/state")
        assert status == 200
        assert json.loads(body)["capabilities"] == {
            "codex_cli": "unavailable",
            "analysis": False,
            "resume": False,
            "worker": False,
        }
        assert active.state()["connections"] == {"applications": True, "career": True}


def test_create_retry_after_a_lost_receipt_reopens_one_persisted_record(portal: Portal):
    headers = portal.write_headers() | {"Idempotency-Key": "a" * 32}
    payload = json.dumps({"company": "Synthetic", "role_title": "Engineer"}).encode()
    first_status, _, first_body = portal.request(
        "POST", "/api/applications", body=payload, headers=headers
    )
    assert first_status == 201
    first = json.loads(first_body)["application"]
    primary = portal.applications / first["source_name"]
    saved = primary.read_bytes()
    assert json.loads(saved)["schema_version"] == "application-record/v1"
    # The browser never received the first receipt. Retry through the same public API.
    second_status, _, second_body = portal.request(
        "POST", "/api/applications", body=payload, headers=headers
    )

    assert second_status == 201
    assert (
        json.loads(second_body)["application"]["id"] == json.loads(first_body)["application"]["id"]
    )
    assert len(portal.state()["applications"]) == 1
    assert len(list(portal.applications.glob("*.json"))) == 1
    assert not list(portal.applications.glob("*.md"))
    assert primary.read_bytes() == saved
    assert json.loads(second_body)["application"]["revision"] == first["revision"]


@pytest.mark.parametrize("warning", [True, False])
@pytest.mark.parametrize(
    "receipt",
    [
        "ok",
        "disconnect",
        "invalid-json",
        "missing-identity",
        "invalid-identity",
        "invalid-revision",
        "patch-disconnect",
        "patch-revert",
    ],
)
def test_application_form_keeps_the_saved_identity_and_shows_screening_warnings(warning, receipt):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the offline application form regression")
    script = r"""
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const warning = JSON.parse(process.argv[2]);
const receipt = process.argv[3];
class Element {
  constructor(id = "") {
    this.id = id; this.children = []; this.listeners = {}; this.value = "";
    this.textContent = ""; this.hidden = false; this.open = false; this.checked = false;
    this.classList = {toggle() {}, add() {}, remove() {}};
  }
  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  setAttribute() {} removeAttribute() {} focus() {} before() {} after() {}
  closest() { return this; } querySelector() { return this; }
  get options() { return this.children; }
  get lastElementChild() { return this.children.at(-1) || this; }
  reportValidity() { return true; }
  reset() { for (const field of this.elements) { field.value = ""; field.checked = false; } }
  showModal() { this.open = true; } close() { this.open = false; }
}
const roots = new Map();
function get(id) {
  if (!roots.has(id)) {
    const element = new Element(id); roots.set(id, element);
    if (id === "application-form") {
      element.elements = [];
      element.elements.namedItem = name => {
        let field = element.elements.find(field => field.name === name);
        if (!field) { field = new Element(name); field.name = name; element.elements.push(field); }
        return field;
      };
    }
  }
  return roots.get(id);
}
const state = {applications: [], evidence: [], statuses: [{value: "drafting", label: "准备投递"}],
  tracks: [], connections: {applications: true, career: true}, csrf_token: "synthetic"};
const writes = []; let stored, storedKey, dropped = false, creations = 0;
let sourcePending = false, detailDropped = false;
const sourceText = "Company: Synthetic\nTitle: AI Engineer\nRequirements: Python";
function savedJob(status = "saved") {
  return {job: {request_id: storedKey, status, application_id: stored?.id,
    fields: {company: "Synthetic", role_title: "AI Engineer", job_description: sourceText},
    missing_fields: []}};
}
const context = {
  document: {getElementById: get, createElement: () => new Element(),
    createTextNode: text => ({textContent: text}), querySelectorAll: () => [],
    querySelector: selector => get(selector),
    addEventListener() {}},
  window: {addEventListener() {}}, location: {hash: "#applications"}, URL,
  crypto: require("node:crypto").webcrypto, AbortController,
  setTimeout() {}, clearTimeout() {},
  fetch: async (path, options) => {
    if (path === "/api/state") return {ok: true, json: async () => state};
    if (path === "/api/intake/state") return {ok: true, json: async () =>
      stored ? savedJob(sourcePending ? "needs_recheck" : "saved") : {job: null}};
    if (!options.method) {
      if (!detailDropped &&
          ["missing-identity", "invalid-identity", "invalid-revision"].includes(receipt)) {
        detailDropped = true;
        return {ok: true, json: async () => receipt === "missing-identity" ? {} : {
          application: {id: receipt === "invalid-identity" ? [] : stored.id,
            revision: receipt === "invalid-revision" ? [] : stored.revision}
        }};
      }
      return {ok: true, json: async () => ({application: stored})};
    }
    const payload = JSON.parse(options.body), key = payload.request_id;
    if (path === "/api/intake/reconcile") {
      assert.equal(payload.request_id, storedKey);
      writes.push({path, method: options.method, payload, key}); sourcePending = false;
      return {ok: true, json: async () => savedJob()};
    }
    writes.push({path, method: options.method, payload, key});
    if (options.method === "POST") {
      if (!stored || storedKey !== key) {
        assert.equal(path, "/api/intake/ingest");
        assert.equal(payload.text, sourceText);
        stored = {company: "Synthetic", role_title: "AI Engineer", job_description: sourceText,
          notes: "", status: "drafting", id: "a".repeat(24), revision: "1".repeat(64)};
        state.applications = [stored];
        storedKey = key; creations++;
      }
      if (!["ok", "patch-disconnect", "patch-revert"].includes(receipt) && !dropped) {
        dropped = true; sourcePending = true;
        if (receipt === "disconnect") throw new Error("Synthetic lost response");
        return {ok: true, json: async () => {
          if (receipt === "invalid-json") throw new Error("Synthetic truncated response");
          if (receipt === "invalid-identity")
            return {application: {id: [], revision: "1".repeat(64)}};
          if (receipt === "invalid-revision")
            return {application: {id: "a".repeat(24), revision: []}};
          return {};
        }};
      }
    } else {
      assert.equal(payload.revision, stored.revision);
      stored = {...stored, ...payload, revision: String(Number(stored.revision[0]) + 1).repeat(64)};
      if (["patch-disconnect", "patch-revert"].includes(receipt) && !dropped) {
        dropped = true; throw new Error("Synthetic lost PATCH receipt");
      }
    }
    if (path === "/api/intake/ingest") return {ok: true, json: async () => savedJob()};
    return {ok: true, json: async () => ({application: stored, ...(warning ? {screening_warning: {
      code: "screening_unavailable",
      message: "记录已保存，但筛选结果暂不可用。请刷新；无需重复保存。"
    }} : {})})};
  },
};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), context);
(async () => {
  const tick = () => new Promise(setImmediate);
  await tick();
  await get("add-application").listeners.click(); await tick();
  const form = get("application-form"), dialog = get("application-dialog");
  const sourceDialog = get("source-intake-dialog"), sourceInput = get("source-intake-input");
  assert.equal(sourceDialog.open, true, "new records start with their source");
  assert.equal(dialog.open, false, "manual fields are not the creation entry");
  sourceInput.value = sourceText;
  await get("source-intake-form").listeners.submit({preventDefault() {}});
  const unknownCreation = !["ok", "patch-disconnect", "patch-revert"].includes(receipt);
  if (unknownCreation) {
    assert.match(get("source-intake-status").textContent, /待核验|未知/);
    assert.equal(sourceInput.disabled, true);
    assert.equal(get("source-intake-submit").disabled, true);
    await get("source-intake-form").listeners.submit({preventDefault() {}});
    assert.equal(writes.length, 1, "unknown creation cannot submit the source twice");
    get("close-source-intake").listeners.click();
    await get("add-application").listeners.click(); await tick();
    assert.equal(sourceInput.value, sourceText);
    assert.equal(sourceInput.disabled, true);
    await get("source-intake-recheck").listeners.click(); await tick();
    assert.equal(writes[0].key, writes[1].key, "reconcile the original creation identity");
    assert.equal(writes[1].path, "/api/intake/reconcile");
    assert.deepEqual(writes[1].payload, {request_id: writes[0].key});
    assert.equal(writes.filter(write => write.path === "/api/intake/ingest").length, 1);
  }
  await tick();
  assert.equal(get("source-intake-submit").disabled, true, "saved sources do not submit twice");
  assert.equal(creations, 1);
  const openSaved = get("source-intake-result").children.find(
    child => child.textContent === "查看已保存岗位");
  assert.ok(openSaved, "the saved result exposes its canonical record");
  await openSaved.listeners.click(); await tick();
  assert.equal(sourceDialog.open, false);
  assert.equal(dialog.open, true);
  if (["missing-identity", "invalid-identity", "invalid-revision"].includes(receipt)) {
    assert.equal(get("form-notice").hidden, false, "invalid record readback is not editable");
    assert.equal(form.elements.namedItem("company").disabled, true);
    assert.equal(writes.length, 2, "invalid readback cannot trigger another create or PATCH");
    await get("cancel-application").listeners.click();
    await get("recent-applications").children[0].listeners.click(); await tick();
    assert.equal(get("form-notice").hidden, true);
    assert.equal(form.elements.namedItem("company").disabled, false);
  }
  assert.equal(get("application-corrections").open, false, "saved records open read-only");
  assert.equal(get("save-application").hidden, true);
  assert.equal(form.elements.namedItem("company").value, "Synthetic");
  assert.equal(form.elements.namedItem("role_title").value, "AI Engineer");
  for (const method of ["PATCH"]) {
    get("application-corrections").open = true;
    get("application-corrections").listeners.toggle();
    assert.equal(get("save-application").hidden, false);
    form.elements.namedItem("notes").value = "Changed synthetic note.";
    await form.listeners.submit({preventDefault() {}});
    if (method === "PATCH" && ["patch-disconnect", "patch-revert"].includes(receipt)) {
      assert.match(get("save-hint").textContent, /待核验|未知/);
      assert.equal(get("load-latest").hidden, false);
      if (receipt === "patch-revert") {
        form.elements.namedItem("notes").value = "";
        await form.listeners.submit({preventDefault() {}});
        assert.equal(dialog.open, true, "an unknown PATCH cannot close as a no-op");
        assert.match(get("save-hint").textContent, /待核验|未知/);
        assert.equal(writes.length, 2, "recheck the committed version before another PATCH");
        assert.equal(stored.notes, "Changed synthetic note.");
      }
      const loading = get("load-latest").listeners.click();
      get("confirmation-dialog").returnValue = "continue";
      get("confirmation-dialog").listeners.close(); await loading;
      await new Promise(setImmediate);
      assert.equal(form.elements.namedItem("notes").value, "Changed synthetic note.");
      if (receipt === "patch-revert") form.elements.namedItem("notes").value = "";
      await form.listeners.submit({preventDefault() {}});
    }
    assert.equal(dialog.open, false, "a saved form must close");
    assert.equal(get("form-notice").hidden, true);
    assert.doesNotMatch(get("save-hint").textContent, /尚未保存/);
    if (receipt === "patch-disconnect") {
      // Neither source intake nor the lost PATCH delivered a screening warning.
      // Loading the committed version then saving unchanged must remain a no-op.
      assert.equal(get("page-notice").hidden, true);
      assert.match(get("toast").textContent, /没有需要保存的修改/);
    } else if (warning) {
      assert.match(get("page-notice").textContent, /已保存/);
      assert.match(get("page-notice").textContent, /筛选.*暂不可用/);
      assert.match(get("toast").textContent, /已保存/);
    } else assert.equal(get("page-notice").hidden, true);
    assert.equal(get("recent-applications").children.length, 1);
  }
  assert.deepEqual(writes.map(write => write.method),
    receipt === "patch-revert" ? ["POST", "PATCH", "PATCH"] :
    ["ok", "patch-disconnect"].includes(receipt) ? ["POST", "PATCH"] : ["POST", "POST", "PATCH"]);
  assert.equal(writes.filter(write => write.path === "/api/intake/ingest").length, 1);
  assert.equal(writes[0].path, "/api/intake/ingest");
  assert.match(writes[0].key, /^[a-f0-9]{32}$/);
  assert.equal(creations, 1);
  assert.equal(writes.at(-1).path, "/api/applications/" + "a".repeat(24));
  assert.equal(writes.at(-1).payload.revision,
    (receipt === "patch-revert" ? "2" : "1").repeat(64));
  if (receipt === "patch-revert") assert.equal(stored.notes, "");
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [
            node,
            "-e",
            script,
            str(Path(__file__).parents[1] / "src/career_evidence_graph/portal_static/app.js"),
            json.dumps(warning),
            receipt,
        ],
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("host", ["attacker.example", "127.0.0.1:1", "localhost.evil:80"])
def test_foreign_or_wrong_port_host_cannot_read_private_state(portal: Portal, host: str) -> None:
    status, _, body = portal.request("GET", "/api/state", headers={"Host": host})
    assert status == 403
    assert b"csrf_token" not in body
    assert str(portal.career).encode() not in body


@pytest.mark.parametrize("origin", ["null", "https://attacker.example", "http://localhost:1"])
def test_foreign_origin_cannot_read_private_state(portal: Portal, origin: str) -> None:
    status, _, body = portal.request("GET", "/api/state", headers={"Origin": origin})
    assert status == 403
    assert b"csrf_token" not in body


@pytest.mark.parametrize(
    "missing", ["Origin", "X-CSRF-Token", "bad-token", "non-ascii-token", "foreign-origin"]
)
@pytest.mark.parametrize(
    "path", ["/api/applications", "/api/interview/inspect-plan", "/api/automation/prepare"]
)
def test_mutation_requires_same_origin_and_process_csrf(
    portal: Portal, missing: str, path: str
) -> None:
    before = portal.state()["applications"]
    headers = portal.write_headers()
    if missing == "bad-token":
        headers["X-CSRF-Token"] = "synthetic-wrong-token"
    elif missing == "non-ascii-token":
        headers["X-CSRF-Token"] = "é"
    elif missing == "foreign-origin":
        headers["Origin"] = "https://attacker.example"
    else:
        del headers[missing]
    status, _, _ = portal.request("POST", path, body=b"{}", headers=headers)
    assert status == 403
    assert portal.state()["applications"] == before


@pytest.mark.parametrize("path", ["/api/applications", "/api/interview/inspect-plan"])
def test_mutation_requires_json_and_bounded_body(portal: Portal, path: str) -> None:
    headers = portal.write_headers()
    headers["Content-Type"] = "text/plain"
    status, _, _ = portal.request("POST", path, body=b"{}", headers=headers)
    assert status == 415
    headers["Content-Type"] = "application/json"
    # The server must reject the declared length before waiting for its body.
    headers["Content-Length"] = str(1024 * 1024 + 1)
    status, _, body = portal.request("POST", path, body=None, headers=headers)
    assert status == 413
    assert b"Traceback" not in body
    assert portal.state()["applications"] == []


@pytest.mark.parametrize(
    "path",
    [
        "/.git/config",
        "/../README.md",
        "/%2e%2e/README.md",
        "/api/evidence/../../.git/config",
        "/api/evidence/%2e%2e%2f.git%2fconfig",
        "/api/evidence/%2Fetc%2Fpasswd",
    ],
)
def test_routes_do_not_expose_arbitrary_paths(portal: Portal, path: str) -> None:
    status, _, body = portal.request("GET", path)
    assert status in {400, 404}
    assert b"[core]" not in body
    assert str(portal.career).encode() not in body
    assert str(portal.applications).encode() not in body


def test_api_errors_do_not_echo_input_or_tracebacks(portal: Portal) -> None:
    sentinel = "synthetic-sensitive-application-body-sentinel"
    status, _, body = portal.request(
        "POST",
        "/api/applications",
        body=json.dumps({"company": sentinel, "status": "invalid-status"}).encode(),
        headers=portal.write_headers(),
    )
    assert status == 400
    assert sentinel.encode() not in body
    assert b"Traceback" not in body
    assert str(portal.career).encode() not in body
    assert portal.state()["applications"] == []


@pytest.mark.parametrize("body", [b"{", b"[]", b"null", b"\xff"])
def test_malformed_json_has_safe_failure_and_no_write(portal: Portal, body: bytes) -> None:
    status, _, response = portal.request(
        "POST", "/api/applications", body=body, headers=portal.write_headers()
    )
    assert status == 400
    assert b"Traceback" not in response
    assert portal.state()["applications"] == []


def test_cross_site_fetch_metadata_rejected_even_without_origin(portal: Portal) -> None:
    status, _, body = portal.request("GET", "/api/state", headers={"Sec-Fetch-Site": "cross-site"})
    assert status == 403
    assert b"csrf_token" not in body


def test_application_write_reload_and_conflict_preserve_legacy_and_career(portal: Portal) -> None:
    legacy = portal.applications / "legacy.md"
    legacy_bytes = (
        b'---\ntype: job_application\ncompany: "Legacy Synthetic"\n'
        b'role_title: "Engineer"\nstatus: applied\ntrack: "AI/ML"\n'
        b'custom_property: "retain me"\n---\n\n## Next Action\n\nFollow up\n'
    )
    legacy.write_bytes(legacy_bytes)
    reports = portal.career / "reports"
    reports.mkdir()
    evidence_path = reports / "synthetic-report.md"
    evidence_bytes = b"# Synthetic project\n\nCandidate context only, no audited mastery.\n"
    evidence_path.write_bytes(evidence_bytes)
    state = portal.state()
    evidence = state["evidence"][0]
    assert evidence["status"] == "documentary"
    payload = {
        "company": "Synthetic New Company",
        "role_title": "Research Engineer",
        "status": "applied",
        "track": "Research",
        "linked_evidence": [evidence["id"]],
        "job_description": "Synthetic role description.",
        "next_action": "Prepare the interview examples.",
    }
    status, _, body = portal.request(
        "POST",
        "/api/applications",
        body=json.dumps(payload).encode(),
        headers=portal.write_headers(),
    )
    assert status == 201, body
    created = json.loads(body)["application"]
    assert created["company"] == payload["company"]
    assert created["linked_evidence"] == [evidence["id"]]
    assert created["job_description"] == payload["job_description"]
    assert len(portal.state()["applications"]) == 2
    status, _, body = portal.request("GET", f"/api/applications/{created['id']}")
    assert status == 200
    assert json.loads(body)["application"]["revision"] == created["revision"]

    route = f"/api/applications/{created['id']}"
    changes = {"status": "interview_scheduled", "revision": created["revision"]}
    status, _, body = portal.request(
        "PATCH", route, body=json.dumps(changes).encode(), headers=portal.write_headers()
    )
    assert status == 200, body
    updated = json.loads(body)["application"]
    assert updated["status"] == "interview_scheduled"
    assert updated["revision"] != created["revision"]
    assert updated["linked_evidence"] == [evidence["id"]]

    changes["status"] = "rejected"
    status, _, _ = portal.request(
        "PATCH", route, body=json.dumps(changes).encode(), headers=portal.write_headers()
    )
    assert status == 409
    assert legacy.read_bytes() == legacy_bytes
    assert evidence_path.read_bytes() == evidence_bytes
    status, _, body = portal.request("GET", f"/api/evidence/{evidence['id']}")
    assert status == 200
    detail = json.loads(body)
    assert detail["status"] == "documentary"
    assert "mastery" not in detail
    assert detail["content"].encode() == evidence_bytes

    with _running_portal(portal.applications, portal.career) as reloaded:
        state_after = reloaded.state()
        persisted = next(
            item for item in state_after["applications"] if item["id"] == created["id"]
        )
        assert persisted["status"] == "interview_scheduled"
        assert persisted["revision"] == updated["revision"]
        assert state_after["csrf_token"] != state["csrf_token"]
    assert legacy.read_bytes() == legacy_bytes
    assert evidence_path.read_bytes() == evidence_bytes


@pytest.mark.parametrize("extra", [{"mastery": 100}, {"linked_evidence": ["f" * 24]}])
def test_application_cannot_write_assessment_or_unknown_evidence(
    portal: Portal, extra: dict[str, object]
) -> None:
    payload = {"company": "Synthetic Company", "role_title": "Engineer", **extra}
    status, _, _ = portal.request(
        "POST",
        "/api/applications",
        body=json.dumps(payload).encode(),
        headers=portal.write_headers(),
    )
    assert status == 400
    assert portal.state()["applications"] == []
    assert not (portal.career / ".career-evidence").exists()


def test_csv_export_preserves_data_and_neutralizes_spreadsheet_formulas(portal: Portal) -> None:
    payload = {"company": "=1+1", "role_title": "+SUM(1,2)", "notes": "@synthetic\nsecond line"}
    status, _, body = portal.request(
        "POST",
        "/api/applications",
        body=json.dumps(payload).encode(),
        headers=portal.write_headers(),
    )
    assert status == 201, body
    status, headers, body = portal.request("GET", "/api/export.csv")
    assert status == 200
    assert headers["Content-Type"].startswith("text/csv")
    assert "attachment" in headers["Content-Disposition"]
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["company"] == "'=1+1"
    assert rows[0]["role_title"] == "'+SUM(1,2)"
    assert rows[0]["notes"] == "'@synthetic\nsecond line"
    assert portal.state()["applications"][0]["company"] == "=1+1"


def test_request_logs_do_not_copy_personal_query_text(
    portal: Portal, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "synthetic-sensitive-query-sentinel"
    portal.request("GET", f"/missing?query={sentinel}")
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err


@pytest.mark.parametrize("missing_root", ["applications", "career"])
def test_disconnected_private_root_is_not_a_connected_empty_state(
    portal: Portal, missing_root: str
) -> None:
    before = portal.state()
    assert before["connections"] == {"applications": True, "career": True}
    root = getattr(portal, missing_root)
    moved = root.with_name(f"{root.name}-temporarily-unavailable")
    root.rename(moved)
    status, _, body = portal.request("GET", "/api/state")
    assert status == 503
    error = json.loads(body)
    assert "error" in error
    assert "csrf_token" not in error
    assert str(root).encode() not in body
    assert not root.exists()
    status, _, body = portal.request(
        "POST",
        "/api/applications",
        body=json.dumps({"company": "Synthetic", "role_title": "Engineer"}).encode(),
        headers={
            "Origin": portal.origin,
            "X-CSRF-Token": before["csrf_token"],
            "Content-Type": "application/json",
        },
    )
    assert status == 503
    assert str(root).encode() not in body
    assert not root.exists()


def test_evidence_api_excludes_raw_hidden_and_replaced_symlink_sources(portal: Portal) -> None:
    reports = portal.career / "reports"
    reports.mkdir()
    public_context = reports / "synthetic-context.md"
    public_context.write_text("# Synthetic context\n\nDocumentary example.\n", encoding="utf-8")
    hidden = reports / ".hidden.md"
    hidden.write_text("synthetic-hidden-sentinel", encoding="utf-8")
    raw = portal.career / ".career-evidence/raw"
    raw.mkdir(parents=True)
    (raw / "synthetic-capture.md").write_text("synthetic-raw-sentinel", encoding="utf-8")
    external = portal.career.parent / "outside-private-selection.md"
    external.write_text("synthetic-outside-selection-sentinel", encoding="utf-8")

    state = portal.state()
    assert len(state["evidence"]) == 1
    identifier = state["evidence"][0]["id"]
    encoded = json.dumps(state)
    assert "synthetic-hidden-sentinel" not in encoded
    assert "synthetic-raw-sentinel" not in encoded
    public_context.unlink()
    public_context.symlink_to(external)
    assert portal.state()["evidence"] == []
    status, _, body = portal.request("GET", f"/api/evidence/{identifier}")
    assert status == 404
    assert b"synthetic-outside-selection-sentinel" not in body
    assert str(external).encode() not in body


def test_graph_endpoint_and_assets_are_removed(portal: Portal) -> None:
    # 2026-11-10: the evidence page shows a category table of the career library instead.
    assert portal.request("GET", "/api/graph")[0] == 404
    for asset in ("graph.js", "graph.css"):
        assert portal.request("GET", f"/static/{asset}")[0] == 404


def _interview_payload() -> dict:
    corpus = (
        Path(__file__).parents[1] / "validation/calibration/phase-04/corpus-review-safe-v1.json"
    )
    depth = json.loads(corpus.read_text())["audit_journey"]["probe_plan"]
    depth["question_layer"] = "project-depth"
    depth["areas"][0]["evaluation_criteria"] = {
        difficulty: ["Explain the authorization choice and its verification."]
        for difficulty in ("hard", "intermediate", "simple")
    }
    transfer = deepcopy(depth)
    transfer["question_layer"] = "transfer"
    transfer["areas"][0]["changed_condition"] = "The authorization boundary serves two tenants."
    return {
        "experience_id": "experience-synthetic",
        "plan": {
            "experience_id": "experience-synthetic",
            "overview": {
                "id": "question-overview",
                "reason": "Synthetic authorization context.",
                "prompt": "Introduce the synthetic project and your contribution.",
                "area": "project-overview",
                "question_layer": "project-overview",
                "inspection_reference": "synthetic.md#authorization",
                "evaluation_criteria": ["Explain goal, method, role and limits."],
            },
            "depth_plans": [depth],
            "transfer_plans": [transfer],
        },
        "facts_by_contribution": {
            depth["contribution_id"]: [
                {
                    "evidence_id": depth["areas"][0]["inspected_fact_ids"][0],
                    "source_locator": "synthetic.md#authorization",
                    "statement": "PrivateInspectionCanary: synthetic source body.",
                }
            ]
        },
    }


@pytest.mark.parametrize(
    "problem",
    [
        None,
        "experience",
        "foreign-fact",
        "blank-criteria",
        "wrong-layer",
        "missing-change",
        "empty-facts",
        "malformed-facts",
    ],
)
def test_interview_inspection_is_read_only_and_uses_bounded_safe_results(
    portal: Portal, monkeypatch: pytest.MonkeyPatch, problem: str | None
) -> None:
    def unexpected_model(*_: object, **__: object) -> None:
        pytest.fail("Read-only preparation must not invoke a model")

    monkeypatch.setattr("career_evidence_graph.codex_cli.run_codex_exec", unexpected_model)
    payload = _interview_payload()
    if problem == "experience":
        payload["experience_id"] = "experience-private-canary"
    elif problem == "foreign-fact":
        payload["plan"]["transfer_plans"][0]["areas"][0]["inspected_fact_ids"] = [
            "evidence-private-canary"
        ]
    elif problem == "blank-criteria":
        payload["plan"]["overview"]["evaluation_criteria"] = [" "]
    elif problem == "wrong-layer":
        payload["plan"]["depth_plans"][0]["question_layer"] = "transfer"
    elif problem == "missing-change":
        del payload["plan"]["transfer_plans"][0]["areas"][0]["changed_condition"]
    elif problem == "empty-facts":
        payload["facts_by_contribution"] = {}
    elif problem == "malformed-facts":
        payload["facts_by_contribution"] = {"PrivateKeyCanary": "PrivateValueCanary"}
    headers = portal.write_headers()
    before = {
        file: file.read_bytes()
        for root in (portal.applications, portal.career)
        for file in root.rglob("*")
        if file.is_file()
    }
    status, response_headers, body = portal.request(
        "POST", "/api/interview/inspect-plan", body=json.dumps(payload).encode(), headers=headers
    )
    after = {
        file: file.read_bytes()
        for root in (portal.applications, portal.career)
        for file in root.rglob("*")
        if file.is_file()
    }
    assert after == before
    assert response_headers["Cache-Control"] == "no-store"
    for marker in (b"Private", b"private-canary", b"Traceback", str(portal.career).encode()):
        assert marker not in body
    result = json.loads(body)
    if problem is None:
        assert status == 200
        assert result == {
            "valid": True,
            "status": "preparation-only",
            "schema_version": "project-interview-plan/v1",
            "policy_version": "artifact-aware-question/v3",
            "layer_order": ["project-overview", "project-depth", "transfer"],
            "contribution_count": 1,
            "depth_area_count": 1,
            "transfer_area_count": 1,
        }
    else:
        assert status == 400
        assert result["error"] == "invalid_interview_plan"


def test_interview_protocol_reads_the_system_document_without_exposing_private_records(
    portal: Portal,
) -> None:
    status, headers, body = portal.request("GET", "/api/interview/protocol")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    expected = Path(__file__).parents[1] / "docs/question-scoring-pipeline.md"
    assert json.loads(body)["content"] == expected.read_text()
    assert str(portal.career).encode() not in body
    status, _, _ = portal.request(
        "GET", "/api/interview/protocol", headers={"Origin": "https://outside.invalid"}
    )
    assert status == 403


@pytest.mark.parametrize(
    "decisions,route", [({}, "review"), ({"target_company": "target"}, "manual")]
)
def test_saved_routing_is_visible_and_guards_plugin_entry(portal, decisions, route):
    status, _, raw = portal.request(
        "POST",
        "/api/applications",
        body=json.dumps(
            {
                "company": "Synthetic",
                "role_title": "AI Engineer",
                "url": "https://boards.greenhouse.io/synthetic/jobs/999",
                **decisions,
            }
        ).encode(),
        headers=portal.write_headers(),
    )
    assert status == 201
    record = json.loads(raw)["application"]
    assert record["screening"]["application_route"] == route
    hint = next(app for app in portal.state()["applications"] if app["id"] == record["id"])[
        "screening"
    ]
    assert hint["application_route"] == route
    assert not hint["batch_preparable"]
    before = {p: p.read_bytes() for p in portal.applications.rglob("*") if p.is_file()}
    status, _, raw = portal.request(
        "POST",
        "/api/automation/prepare",
        body=json.dumps({"application_id": record["id"], "revision": record["revision"]}).encode(),
        headers=portal.write_headers(),
    )
    result = json.loads(raw)
    if route == "review":
        assert status == 409
        assert result["error"] == "application_route_required"
    else:
        assert status == 200
        assert result["application_route"] == "manual"
        assert "人工精准" in result["prompt"]
    assert {p: p.read_bytes() for p in portal.applications.rglob("*") if p.is_file()} == before


def test_edited_routing_response_retains_screening_without_a_page_refresh(portal):
    status, _, raw = portal.request(
        "POST",
        "/api/applications",
        body=json.dumps(
            {
                "company": "Synthetic",
                "role_title": "AI Engineer",
                "url": "https://boards.greenhouse.io/synthetic/jobs/888",
                "application_strategy": "batch",
            }
        ).encode(),
        headers=portal.write_headers(),
    )
    assert status == 201
    record = json.loads(raw)["application"]
    status, _, raw = portal.request(
        "PATCH",
        "/api/applications/" + record["id"],
        body=json.dumps(
            {
                "revision": record["revision"],
                "application_strategy": "",
                "compensation_priority": "exceptional",
            }
        ).encode(),
        headers=portal.write_headers(),
    )
    assert status == 200
    updated = json.loads(raw)["application"]
    assert updated["screening"]["application_route"] == "manual"
    assert updated["screening"]["precision_preparable"]
    assert not updated["screening"]["batch_preparable"]
    assert updated["status"] == "drafting"


def test_automation_task_is_read_only_revision_bound_and_requires_csrf(portal: Portal) -> None:
    status, _, raw = portal.request(
        "POST",
        "/api/applications",
        body=json.dumps(
            {
                "company": "Example",
                "role_title": "Engineer",
                "url": "https://boards.greenhouse.io/example/jobs/123",
                "application_strategy": "batch",
            }
        ).encode(),
        headers=portal.write_headers(),
    )
    assert status == 201
    record = json.loads(raw)["application"]
    before = {p: p.read_bytes() for p in portal.applications.rglob("*") if p.is_file()}
    payload = json.dumps({"application_id": record["id"], "revision": record["revision"]}).encode()
    status, _, _ = portal.request("POST", "/api/automation/prepare", body=payload)
    assert status == 403
    status, headers, raw = portal.request(
        "POST", "/api/automation/prepare", body=payload, headers=portal.write_headers()
    )
    assert status == 200
    task = json.loads(raw)
    assert task["executed"] is False
    assert task["revision"] == record["revision"]
    assert "no-store" in headers["Cache-Control"]
    assert {p: p.read_bytes() for p in portal.applications.rglob("*") if p.is_file()} == before
    changed = dict(application_id=record["id"], revision="0" * 64)
    status, _, raw = portal.request(
        "POST",
        "/api/automation/prepare",
        body=json.dumps(changed).encode(),
        headers=portal.write_headers(),
    )
    assert status == 409
    assert json.loads(raw)["error"] == "conflict"
    for invalid in ({}, {**changed, "auto_submit": True}, {**changed, "revision": 123}):
        status, _, _ = portal.request(
            "POST",
            "/api/automation/prepare",
            body=json.dumps(invalid).encode(),
            headers=portal.write_headers(),
        )
        assert status == 400


def test_single_job_http_rejects_retired_html_without_starting_or_accepting_other_jobs(
    portal: Portal, tmp_path, monkeypatch
):
    import base64
    from functools import partial

    from test_application_match import model_output, model_runner

    from career_evidence_graph.application_match import analyze_job
    from career_evidence_graph.application_resume import (
        career_source_snapshot,
    )
    from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog

    applications = ApplicationStore(portal.applications)
    job = applications.create_application(
        {
            "company": "Synthetic Single",
            "role_title": "Engineer",
            "job_description": "Use Python.",
            "url": "https://jobs.lever.co/synthetic/11111111-1111-4111-8111-111111111111",
        }
    )
    source = portal.career / "contributions/single.md"
    source.parent.mkdir(exist_ok=True)
    source.write_text(
        "# Synthetic Python\n\n## Scope\nImplemented a Python service.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n"
    )
    profile = portal.career / "sources/profile.json"
    profile.parent.mkdir(exist_ok=True)
    profile.write_text(json.dumps({"name": "Synthetic Person"}))
    sources = career_source_snapshot(CareerCatalog(portal.career))
    analyzer = partial(analyze_job, runner=model_runner(model_output(sources), []))
    raw_pdf = b"%PDF-1.4 Exact synthetic approved bytes"

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "single-flow",
        worker_root=tmp_path / "single-worker",
        worker_fixtures=True,
        worker_headless=True,
        flow_analyzer=analyzer,
    ) as active:
        worker = active.server.worker_service
        validations, starts = [], []
        monkeypatch.setattr(
            worker.store, "single_validator", lambda *args, **kwargs: validations.append(kwargs)
        )
        monkeypatch.setattr(worker, "spawn", lambda: starts.append("spawn"))
        before_worker = worker.store.path.read_bytes()
        status, _, raw = active.request(
            "POST",
            "/api/worker/prepare",
            body=json.dumps(
                {
                    "jobs": [
                        {
                            "application_id": job["id"],
                            "revision": job["revision"],
                            "country": "CHE",
                            "filename": "unreviewed.pdf",
                            "file_base64": base64.b64encode(raw_pdf).decode(),
                        }
                    ]
                }
            ).encode(),
            headers=active.write_headers(),
        )
        assert status == 409 and json.loads(raw)["error"] == "flow_scoped_worker_required"
        assert worker.store.path.read_bytes() == before_worker and starts == []
        status, _, raw = active.request("GET", "/api/worker/state")
        assert status == 200 and json.loads(raw)["enabled"] is False

        def post(action, payload):
            status, _, raw = active.request(
                "POST",
                "/api/flow/" + action,
                body=json.dumps(payload).encode(),
                headers=active.write_headers(),
            )
            return status, json.loads(raw)

        def observe():
            status, _, raw = active.request("GET", "/api/flow/state")
            assert status == 200, raw
            return json.loads(raw)

        def wait(expected):
            end = time.monotonic() + 3
            while time.monotonic() < end:
                state = observe()
                if state["active_task"]["status"] in expected:
                    return state["active_task"]
                time.sleep(0.01)
            pytest.fail("Single fixture did not reach expected state")

        status, task = post(
            "create", {"application_id": job["id"], "application_revision": job["revision"]}
        )
        assert status == 200
        for stage in ("analysis", "resume"):
            status, _ = post(
                "start", {"task_id": task["id"], "task_revision": task["revision"], "stage": stage}
            )
            assert status == 200
            task = wait({"analysis_ready"} if stage == "analysis" else {"failed"})
        assert task["material_contract"] == "content-writing/v1"
        assert task["stages"]["resume"]["error_code"] == "resume_content_material_required"
        assert task["resume_id"] is None
        assert not task["materials_confirmed"]
        status, _ = post(
            "prepare-worker",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "country": "CHE",
                "send_confirmed": True,
            },
        )
        assert status == 409
        assert worker.store.path.read_bytes() == before_worker
        assert validations == starts == []
        assert not list(active.server.application_resume_store.root.rglob("resume.html"))
        assert not list(active.server.application_resume_store.root.rglob("resume.pdf"))
    assert worker.store.load()["control"] == "paused"


def test_shutdown_cannot_be_undone_by_an_already_queued_resume(tmp_path, monkeypatch):
    from test_application_single_binding import bound_single

    from career_evidence_graph.application_worker import digest

    applications, flow_root, career, _, _ = bound_single.__wrapped__(tmp_path)
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    path = flow_root / "flow.json"
    state = json.loads(path.read_text())
    task = state["tasks"][0]
    application = applications.get_application(task["application_id"])
    task.update(
        worker_ref=None,
        status="materials_ready",
        application_revision=application["revision"],
        job_description=application["job_description"],
        stages={"analysis": {"status": "complete"}, "resume": {"status": "complete"}},
    )
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    path.write_text(json.dumps(state))
    server = create_server(
        applications.root,
        career,
        write_admission_policy="development",
        flow_root=flow_root,
        worker_root=tmp_path / "worker",
        worker_fixtures=True,
    )
    service = server.application_flow_service
    worker = server.worker_service
    intake = server.application_intake_service
    spawned = []
    monkeypatch.setattr(worker, "spawn", lambda: spawned.append("spawn"))
    task = service.prepare_worker(task["id"], task["revision"], "CHE", True)
    with worker.store.applications.write_lock():
        worker_state = worker.store.load()
        worker_state.update(control="running", controller="synthetic-controller")
        worker.store.save(worker_state)
    server_thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    server_thread.start()
    active = Portal(server, applications.root, career)
    headers = active.write_headers()
    admitted, release_request, shutdown_gap, release_close = (Event() for _ in range(4))
    original_request, original_close = service.request, intake.close

    def held_request(action, payload):
        if action == "worker-action":
            admitted.set()
            assert release_request.wait(3)
        return original_request(action, payload)

    def held_intake_close():
        shutdown_gap.set()
        assert release_close.wait(3)
        original_close()

    monkeypatch.setattr(service, "request", held_request)
    monkeypatch.setattr(intake, "close", held_intake_close)
    results = []

    def request_resume():
        results.append(
            active.request(
                "POST",
                "/api/flow/worker-action",
                body=json.dumps(
                    {
                        "task_id": task["id"],
                        "task_revision": task["revision"],
                        "operation": "resume",
                        "payload": {"controller": "synthetic-controller"},
                    }
                ).encode(),
                headers=headers,
            )
        )

    requester = Thread(target=request_resume, daemon=True)
    closer = None
    try:
        requester.start()
        assert admitted.wait(3)
        server.shutdown()
        server_thread.join(3)
        closer = Thread(target=server.server_close, daemon=True)
        closer.start()
        assert shutdown_gap.wait(3)
        assert worker.store.load()["control"] == "paused"
        release_request.set()
        requester.join(3)
        assert not requester.is_alive()
        release_close.set()
        closer.join(3)
        assert not closer.is_alive()
        assert worker.store.load()["control"] == "paused"
        assert spawned == []
        assert results[0][0] == 409
    finally:
        release_request.set()
        release_close.set()
        if closer is not None:
            closer.join(3)
        if server_thread.is_alive():
            server.shutdown()
            server_thread.join(3)
        original_close()
        service.close()
        server.socket.close()


def test_incomplete_real_worker_checkpoint_does_not_hide_the_career_workspace(
    portal: Portal, tmp_path
):
    worker_root = tmp_path / "incomplete-worker"
    worker_root.mkdir()
    checkpoint = worker_root / "run.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "applications_root": str(portal.applications),
                "control": "paused",
                "jobs": [],
                "heartbeat_at": 0,
                "worker_heartbeat": 0,
                "lease_seconds": 60,
                "commands": [],
            }
        )
    )
    before = checkpoint.read_bytes()
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "degraded-flow",
        worker_root=worker_root,
    ) as active:
        assert active.state()["connections"] == {"applications": True, "career": True}
        status, _, raw = active.request("GET", "/api/flow/state")
        assert status == 200
        assert json.loads(raw)["capabilities"]["worker"] is False
        assert json.loads(raw)["worker"]["error"] == "flow_worker_unavailable"
        assert checkpoint.read_bytes() == before


def test_shutdown_still_pauses_worker_when_flow_checkpoint_fails(tmp_path, monkeypatch):
    from test_application_single_binding import bound_single

    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.application_worker import digest

    applications, flow_root, career, _, _ = bound_single.__wrapped__(tmp_path)
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    path = flow_root / "flow.json"
    state = json.loads(path.read_text())
    task = state["tasks"][0]
    application = applications.get_application(task["application_id"])
    task.update(
        worker_ref=None,
        status="materials_ready",
        application_revision=application["revision"],
        job_description=application["job_description"],
        stages={"analysis": {"status": "complete"}, "resume": {"status": "complete"}},
    )
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    path.write_text(json.dumps(state))
    server = create_server(
        applications.root,
        career,
        write_admission_policy="development",
        flow_root=flow_root,
        worker_root=tmp_path / "worker",
        worker_fixtures=True,
    )
    service, worker = server.application_flow_service, server.worker_service

    def no_spawn():
        pytest.fail("Closing must not start a browser worker")

    monkeypatch.setattr(worker, "spawn", no_spawn)
    task = service.prepare_worker(task["id"], task["revision"], "CHE", True)
    service.observe_worker(task["id"], task["revision"], task["worker_ref"] | {"status": "filling"})
    with worker.store.applications.write_lock():
        worker_state = worker.store.load()
        worker_state["control"] = "running"
        worker_state["jobs"][0].update(
            status="filling", page_open=True, intent={"action": "upload"}
        )
        worker.store.save(worker_state)
    before = deepcopy(worker.store.load()["jobs"])
    original_write = helper.atomic_write_json

    def fail_flow_checkpoint(destination, value):
        if Path(destination) == service.path:
            raise OSError("Synthetic flow-only checkpoint failure")
        return original_write(destination, value)

    monkeypatch.setattr(helper, "atomic_write_json", fail_flow_checkpoint)
    close_error = None
    try:
        try:
            server.server_close()
        except OSError as error:
            close_error = error
        assert worker.store.load()["control"] == "paused", repr(close_error)
        assert worker.store.load()["jobs"] == before
        assert service._lock_file.closed
        assert close_error is None
    finally:
        monkeypatch.setattr(helper, "atomic_write_json", original_write)
        server.application_intake_service.close()
        service.close()
        if server.worker_fixtures:
            server.worker_fixtures.shutdown()
            server.worker_fixtures.server_close()
        server.socket.close()
