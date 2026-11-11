"""Opt-in complete HTTP preparation benchmark with synthetic data and real TeX output.

Review writes below are automated fixture decisions, never evidence of human acceptance.
The analyzer is fixed because person/job matching precedes the measured preparation entry.
"""

import hashlib
import json
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_application_match import model_output, model_runner
from test_career_portal_http import _running_portal

from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_prism import PrismClient
from career_evidence_graph.application_resume import ApplicationResumeStore
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError
from career_evidence_graph.codex_cli import run_codex_exec

pytestmark = pytest.mark.skipif(
    os.environ.get("TOMORROWSTAR_FULL_ENTRY_REUSE_BENCHMARK") != "1",
    reason="Explicit opt-in required for complete local rendering/model benchmark",
)

JD = "Implement reliable Python services for backend software development."
ORIGINAL_JD = "Develop and maintain backend services in Python, focusing on service reliability."
BODY = "Synthetic Applicant\n\\section*{Python service}\nImplemented reliable Python services.\n"
TEX = "\\documentclass{article}\n\\begin{document}\n" + BODY + "\\end{document}\n"


def _post(active, action, task=None, **extra):
    from http.client import HTTPConnection

    payload = extra | ({"task_id": task["id"], "task_revision": task["revision"]} if task else {})
    connection = HTTPConnection("127.0.0.1", active.server.server_port, timeout=90)
    try:
        connection.request(
            "POST",
            "/api/flow/" + action,
            body=json.dumps(payload).encode(),
            headers=active.write_headers(),
        )
        response = connection.getresponse()
        raw = response.read()
        assert response.status == 200, (action, response.status, raw.decode())
        return json.loads(raw)
    finally:
        connection.close()


def _wait(active, task, expected):
    deadline = time.monotonic() + 210
    while time.monotonic() < deadline:
        current = active.server.application_flow_service.snapshot(task["id"])["active_task"]
        assert current["status"] not in {"failed", "export_failed", "needs_recheck"}, current
        if current["status"] in expected:
            return current
        time.sleep(0.01)
    pytest.fail(f"Complete entry timed out: {current}")


class _LocalTectonic:
    """Replace Prism transport only; compile actual generated sources without downloads."""

    def __init__(self, directory, events):
        self.directory, self.events = directory, events

    def configuration(self):
        return PrismClient().configuration()

    def open(self, _binding):
        return "http://127.0.0.1:8790/"

    def compile(self, binding):
        started = time.perf_counter_ns()
        directory = self.directory / uuid4().hex
        directory.mkdir(parents=True)
        command = [
            shutil.which("tectonic"),
            "--only-cached",
            "--outdir",
            str(directory),
            str(Path(binding["project_root"]) / binding["main"]),
        ]
        result = subprocess.run(command, capture_output=True, timeout=60, check=False)
        self.events.append(
            {
                "stage": "tectonic",
                "ms": (time.perf_counter_ns() - started) / 1e6,
                "exit": result.returncode,
            }
        )
        if result.returncode:
            raise PortalDataError(
                "resume_export_failed",
                "Offline Tectonic compile failed: "
                + result.stderr.decode(errors="replace")[-1500:],
                503,
            )
        pdf = directory / Path(binding["main"]).with_suffix(".pdf").name
        return {
            "source_revision": binding["source_revision"],
            "pdf": pdf.read_bytes(),
            "build": {"main": binding["main"], "exit": 0, "pdf_updated": True},
        }


def _inspect_pdf(raw):
    result = subprocess.run(
        ["pdfinfo", "-"], input=raw, capture_output=True, timeout=10, check=True
    )
    pages = next(line for line in result.stdout.decode().splitlines() if line.startswith("Pages:"))
    return int(pages.split(":", 1)[1])


def _synthetic_model(config, prompt, **_kwargs):
    """Deterministic offline smoke control; live measurements never call this runner."""
    payload = json.loads(prompt[prompt.index("{") :])
    properties = json.loads(Path(config.output_schema).read_text())["properties"]
    if "groups" in properties:
        name = next(row for row in payload["sources"] if row.get("source_kind") == "identity")
        work = next(row for row in payload["sources"] if row["title"] == "Synthetic Python service")
        value = {
            "groups": [
                {
                    "title": "Identity",
                    "start_line": 1,
                    "end_line": 1,
                    "source_ids": [name["source_id"]],
                    "latex": "Synthetic Applicant\n",
                    "disposition": "include",
                    "reason": "Confirmed documentary identity",
                },
                {
                    "title": "Python service",
                    "start_line": 2,
                    "end_line": 3,
                    "source_ids": [work["source_id"]],
                    "latex": BODY.split("\n", 1)[1],
                    "disposition": "include",
                    "reason": "Documented Python implementation",
                },
            ],
            "limitations": [],
        }
    elif "profiles" in properties:
        missing = payload.get("missing", payload.get("jobs", []))
        profiles = [
            {
                "id": row["id"],
                "content": "Implement Python backend services",
                "core_work_confirmed": True,
                "locators": [row["jd"]],
            }
            for row in missing
        ]
        ids = [row["id"] for row in missing] + [
            row["id"] for row in payload.get("cached_profiles", [])
        ]
        value = {
            "profiles": profiles,
            **({"task_ids": ids[:1]} if "task_ids" in properties else {}),
        }
    elif "task_ids" in properties:
        value = {"task_ids": [row["id"] for row in payload["profiles"]][:1]}
    else:
        candidates = payload.get("candidates", [])
        value = {
            "approved": True,
            "source_task_id": candidates[0]["source_task_id"],
            "reason": "Offline synthetic suitability control",
        }
    return SimpleNamespace(structured_result=value, model_dump=lambda **_: {"synthetic": True})


def _measured_runner(events, *, live):
    def run(config, prompt, **kwargs):
        started = time.monotonic()
        schema = json.loads(Path(config.output_schema).read_text())
        event = {"stage": "model", "schema": sorted(schema["properties"]), "live": live}
        try:
            if live:
                deadline = started + kwargs.get("timeout_seconds", 180)

                def bounded_process(*args, **options):
                    options["timeout"] = min(
                        options.get("timeout", 180), max(0.001, deadline - time.monotonic())
                    )
                    return subprocess.run(*args, **options)

                result = run_codex_exec(config, prompt, runner=bounded_process, **kwargs)
            else:
                result = _synthetic_model(config, prompt, **kwargs)
            event["result"] = result.structured_result
            return result
        except Exception as error:
            event["error"] = type(error).__name__
            raise
        finally:
            event["ms"] = (time.monotonic() - started) * 1000
            events.append(event)

    return run


def _analyzer(application, snapshot, directory):
    return analyze_job(
        application, snapshot, directory, runner=model_runner(model_output(snapshot), [])
    )


def _ready_task(active, job, base):
    task = _post(active, "create", application_id=job["id"], application_revision=job["revision"])
    task = _post(active, "start", task, stage="analysis")
    task = _wait(active, task, {"analysis_ready"})
    return _post(active, "bind-latex-base", task, project_root=str(base), main="main.tex")


def _finish_pdf(active, task, *, accept=False):
    """Drive existing review APIs with explicitly synthetic approvals."""
    task = _post(active, "start", task, stage="resume")
    task = _wait(active, task, {"draft_ready", "materials_ready"})
    synthetic_review_writes = 0
    if task["status"] == "draft_ready":
        task = _post(active, "begin-group-review", task)
        task = _post(
            active,
            "capture-group-review",
            task,
            expected_source_revision=task["prism"]["source_revision"],
        )
        # Existing screen-state read records pending review requests internally.
        assert active.request("GET", "/api/flow/state")[0] == 200
        draft = active.server.application_resume_store.draft(task["draft_id"])
        from career_evidence_graph.application_group_review import fixed_education_groups

        fixed = {row["id"] for row in fixed_education_groups(draft)}
        for group in draft["review_groups"]:
            if group["id"] in fixed:
                continue
            task = _post(
                active,
                "review-group",
                task,
                draft_id=task["draft_id"],
                draft_sha256=task["draft_sha256"],
                group_id=group["id"],
                review_fingerprint=group["review_fingerprint"],
            )
            synthetic_review_writes += 1
        task = _post(
            active, "export-pdf", task, draft_id=task["draft_id"], draft_sha256=task["draft_sha256"]
        )
        task = _wait(active, task, {"resume_ready"})
    status, _, raw = active.request("GET", f"/api/flow/resumes/{task['resume_id']}/pdf")
    assert status == 200 and raw.startswith(b"%PDF-"), (status, raw[:200])
    assert hashlib.sha256(raw).hexdigest() == task["resume_sha256"]
    assert active.request("GET", "/api/flow/state")[0] == 200
    if accept and not task.get("materials_confirmed"):
        task = _post(
            active,
            "confirm-materials",
            task,
            resume_id=task["resume_id"],
            resume_sha256=task["resume_sha256"],
        )
        synthetic_review_writes += 1
    return task, synthetic_review_writes


def test_full_http_entry_paired_preparation_to_viewable_pdf(tmp_path, monkeypatch):
    assert shutil.which("tectonic") and shutil.which("pdftotext"), (
        "Existing offline TeX/PDF tools required"
    )
    live = os.environ.get("TOMORROWSTAR_FULL_ENTRY_REUSE_LIVE") == "1"
    pairs = int(os.environ.get("TOMORROWSTAR_FULL_ENTRY_REUSE_PAIRS", "3"))
    assert 1 <= pairs <= 5
    output = Path(
        os.environ.get("TOMORROWSTAR_FULL_ENTRY_REUSE_OUTPUT", str(tmp_path / "benchmark.json"))
    )
    report = {
        "scope": "full HTTP resume preparation to viewable PDF",
        "live_models": live,
        "synthetic_data": True,
        "synthetic_original_acceptance": True,
        "synthetic_review_auto_advance": True,
        "real_human_validation": False,
        "real_local_tectonic": True,
        "prism_transport": "local test adapter",
        "matching_in_timing": False,
        "target_jd": JD,
        "original_jd": ORIGINAL_JD,
        "rows": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2) + "\n")

    applications = tmp_path / "applications"
    applications.mkdir()
    career = tmp_path / "career"
    (career / "contributions").mkdir(parents=True)
    (career / "contributions/python.md").write_text(
        "# Synthetic Python service\n\n## Scope\nImplemented reliable Python services.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n\n## Boundaries\nNo management or GPU training claim.\n"
    )
    (career / "sources").mkdir()
    (career / "sources/profile.json").write_text(json.dumps({"name": "Synthetic Applicant"}))
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    base = tmp_path / "base"
    base.mkdir()
    (base / "main.tex").write_text(TEX)
    factory_events = []

    def factory(apps, catalog, root):
        client = _LocalTectonic(tmp_path / "builds", factory_events)
        store = ApplicationResumeStore(
            apps, catalog, root, prism_client=client, pdf_inspector=_inspect_pdf
        )
        store.model_runner = _measured_runner(factory_events, live=False)
        return store

    try:
        with _running_portal(
            applications,
            career,
            preparation_only=True,
            flow_root=tmp_path / "flow",
            flow_analyzer=_analyzer,
            flow_resume_factory=factory,
        ) as active:
            jobs = ApplicationStore(applications)
            seed = jobs.create_application(
                {
                    "company": "Synthetic Original",
                    "role_title": "Backend Developer",
                    "job_description": ORIGINAL_JD,
                }
            )
            task = _ready_task(active, seed, base)
            origin, _ = _finish_pdf(active, task, accept=True)
            report["original_pdf_sha256"] = origin["resume_sha256"]
            store = active.server.application_resume_store
            factory_events.clear()
            store.model_runner = _measured_runner(factory_events, live=live)
            import career_evidence_graph.application_pdf_reuse as reuse_module

            original_reuse = reuse_module.try_reuse
            history = [origin]

            # Each comparison uses exactly the same accepted history. Target PDFs remain unaccepted.
            # Scope only candidate history; source and generation caches remain intact.
            def comparison_reuse(store, task, sources, analysis, _history, **kwargs):
                return original_reuse(store, task, sources, analysis, history, **kwargs)

            for pair in range(pairs):
                order = ("normal", "reuse") if pair % 2 == 0 else ("reuse", "normal")
                for mode in order:
                    monkeypatch.setattr(
                        reuse_module,
                        "try_reuse",
                        comparison_reuse if mode == "reuse" else lambda *a, **k: None,
                    )
                    job = jobs.create_application(
                        {
                            "company": f"Synthetic Pair {pair} {mode}",
                            "role_title": "Python Engineer",
                            "job_description": JD,
                        }
                    )
                    task = _ready_task(active, job, base)
                    before = store.measurements.reuse_summary()
                    events_start = len(factory_events)
                    started = time.perf_counter_ns()
                    row = {
                        "pair": pair,
                        "mode": mode,
                        "jd_sha256": hashlib.sha256(JD.encode()).hexdigest(),
                        "sources_revision": task["inputs"]["sources_revision"],
                        "information_library_revision": task["inputs"][
                            "information_library_revision"
                        ],
                        "candidate_history": [origin["id"]],
                        "case": "new_target_task_preserved_caches",
                        "retrieval_cache": "cold" if pair == 0 and mode == "reuse" else "preserved",
                    }
                    report["rows"].append(row)
                    try:
                        finished, reviews = _finish_pdf(active, task)
                        row.update(
                            total_ms=(time.perf_counter_ns() - started) / 1e6,
                            reused=bool(finished.get("pdf_reuse")),
                            synthetic_group_review_writes=reviews,
                            status=finished["status"],
                            pdf_sha256=finished["resume_sha256"],
                        )
                        after = store.measurements.reuse_summary()
                        for key in ("confirmation_requests", "repeat_confirmation_requests"):
                            row[key] = after[key] - before[key]
                        row["internal_preparation_observations"] = after["preparations"][
                            len(before["preparations"]) :
                        ]
                        # This is the existing hot read path, without new preparation.
                        hot = time.perf_counter_ns()
                        reopened = _post(
                            active,
                            "create",
                            application_id=job["id"],
                            application_revision=job["revision"],
                        )
                        assert reopened["id"] == finished["id"]
                        assert (
                            active.request("GET", f"/api/flow/resumes/{finished['resume_id']}/pdf")[
                                0
                            ]
                            == 200
                        )
                        row["existing_task_hot_read_ms"] = (time.perf_counter_ns() - hot) / 1e6
                    except Exception as error:
                        row.update(
                            error_type=type(error).__name__,
                            failed_total_ms=(time.perf_counter_ns() - started) / 1e6,
                        )
                        raise
                    finally:
                        row["events"] = factory_events[events_start:]
                        save()
            normal = [row for row in report["rows"] if row["mode"] == "normal"]
            reused = [row for row in report["rows"] if row["mode"] == "reuse"]
            assert len({row["sources_revision"] for row in report["rows"]}) == 1
            assert len({row["information_library_revision"] for row in report["rows"]}) == 1
            report["normal_median_ms"] = statistics.median(row["total_ms"] for row in normal)
            report["reuse_median_ms"] = statistics.median(row["total_ms"] for row in reused)
            report["all_reuse_hits"] = all(row["reused"] for row in reused)
            report["paired_speed_pass"] = all(
                next(row["total_ms"] for row in reused if row["pair"] == pair)
                < next(row["total_ms"] for row in normal if row["pair"] == pair)
                for pair in range(pairs)
            )
            report["duplicate_confirmation_nonincrease"] = all(
                next(row["repeat_confirmation_requests"] for row in reused if row["pair"] == pair)
                <= next(
                    row["repeat_confirmation_requests"] for row in normal if row["pair"] == pair
                )
                for pair in range(pairs)
            )
    finally:
        save()
    print(json.dumps(report, indent=2))
