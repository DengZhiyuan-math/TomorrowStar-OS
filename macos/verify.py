"""Opt-in acceptance of a relocated App, using only disposable synthetic data."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import select
import shutil
import subprocess
import tempfile
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def verify_flow_mode(flow: dict, support: Path, *, preparation: bool) -> dict:
    """Check the selected mode in a fresh disposable acceptance workspace."""
    assert flow["enabled"] is True
    assert flow["capabilities"]["worker"] is (not preparation)
    assert flow["active_task"] is None and flow["tasks"] == []
    mode = "material-preparation" if preparation else "single-job-flow"
    assert (support / mode).is_dir()
    if preparation:
        assert flow["mode"] == "preparation"
        assert not any(
            (support / name).exists()
            for name in (
                "single-job-flow",
                "single-job-worker",
                "application-automation-lab",
                "codex-handoff",
            )
        )
    else:
        assert flow.get("mode") != "preparation"
        worker = json.loads((support / "single-job-worker/run.json").read_text())
        assert worker["worker_pid"] is None
    return {"mode": mode, "worker_enabled": not preparation, "worker_autostart": False}


def check_chrome_launch_environment() -> None:
    """Load the guard from this source tree or this App's bundled system."""
    import importlib.util

    resources = Path(__file__).resolve().parent
    system = resources / "system" if (resources / "system").is_dir() else resources.parent
    source = system / "src/career_evidence_graph/chrome_registration.py"
    try:
        spec = importlib.util.spec_from_file_location("tomorrowstar_chrome_registration", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, AttributeError) as error:
        raise RuntimeError(
            "macos_chrome_registration_unknown: bundled registration guard unavailable"
        ) from error
    module.check_chrome_launch_environment()


def verify(app: Path) -> dict:
    check_chrome_launch_environment()
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    with tempfile.TemporaryDirectory(
        prefix="tomorrowstar-acceptance-", suffix=".noindex"
    ) as temporary:
        root = Path(temporary)
        relocated = root / "Folder With Spaces/TomorrowStar.bundle-verification"
        shutil.copytree(app, relocated, symlinks=True)
        resources = relocated / "Contents/Resources"
        manifest = json.loads((resources / "build-manifest.json").read_text())
        if "cua_driver" in manifest:
            helper = resources / "cua-driver/cua-driver"
            assert (
                hashlib.sha256(helper.read_bytes()).hexdigest() == manifest["cua_driver"]["sha256"]
            )
            assert (helper.parent / "LICENSE.md").is_file()
        for name, expected in manifest["engine_files"].items():
            assert (
                hashlib.sha256((resources / "system" / name).read_bytes()).hexdigest() == expected
            )
        applications = root / "synthetic-applications"
        applications.mkdir()
        career = root / "synthetic-career"
        career.mkdir()
        subprocess.run(["git", "init", "--quiet", str(career)], check=True)
        (career / "reports").mkdir()
        (career / "reports/demo.md").write_text(
            "# Synthetic Demo\n\n## Technology\nPython, SQL\n\nDocumentary fixture only.\n"
        )
        environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(root),
            "TMPDIR": str(root),
            "LANG": "en_US.UTF-8",
        }
        python = resources / "python/bin/python3.13"
        # The retired HTML renderer must fail before producing any resume material.
        subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                "-c",
                "import sys\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "from career_evidence_graph.application_resume import render_resume\n"
                "from career_evidence_graph.career_portal_data import PortalDataError\n"
                "try:\n"
                "    render_resume({})\n"
                "except PortalDataError as error:\n"
                "    assert error.code == 'resume_html_retired' and error.status == 410\n"
                "else:\n"
                "    raise AssertionError('Retired resume renderer remained available')\n",
                str(resources / "system/src"),
            ],
            cwd="/",
            env=environment,
            check=True,
            capture_output=True,
            timeout=30,
        )
        # Handoff checks use a retained synthetic LaTeX PDF, not a renderer test.
        resume_pdf = root / "synthetic-latex-resume.pdf"
        shutil.copyfile(
            Path(__file__).resolve().parents[1]
            / "tests/fixtures/pdf-export/tectonic-compressed.pdf",
            resume_pdf,
        )
        resume_pdf.chmod(0o600)
        worker_help = subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                str(resources / "system/scripts/run_application_worker.py"),
                "--help",
            ],
            cwd="/",
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert "--cua-click-route" in worker_help.stdout
        handoff_help = subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                str(resources / "system/scripts/run_codex_handoff.py"),
                "--help",
            ],
            cwd="/",
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert "--root" in handoff_help.stdout and "readback" in handoff_help.stdout
        support = root / "Library/Application Support/TomorrowStar"
        handoff_root = support / "codex-handoff"
        lab_root = support / "application-automation-lab"
        assert not handoff_root.exists() and not lab_root.exists()

        def start_backend(*mode):
            return subprocess.Popen(
                [
                    str(python),
                    "-I",
                    "-B",
                    "-u",
                    str(resources / "server.py"),
                    "--applications",
                    str(applications),
                    "--career-workspace",
                    str(career),
                    *mode,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd="/",
                env=environment,
            )

        def request(method, path, body=None, headers=None):
            connection = HTTPConnection(address.hostname, address.port, timeout=10)
            try:
                connection.request(method, path, body=body, headers=headers or {})
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                connection.close()

        process = start_backend()
        try:
            assert select.select([process.stdout], [], [], 15)[0], "No backend readiness"
            ready = json.loads(process.stdout.readline())
            assert ready["status"] == "ready"
            address = urlsplit(ready["url"])
            assert address.scheme == "http" and address.hostname == "127.0.0.1"
            assert address.fragment == "flow"

            assert ready["capabilities"]["worker"] is False
            status, _, body = request("GET", "/api/flow/state")
            assert status == 200
            default_mode = verify_flow_mode(json.loads(body), support, preparation=True)
            status, _, body = request("GET", "/api/worker/state")
            assert status == 200 and json.loads(body)["enabled"] is False
            process.stdin.close()
            assert process.wait(timeout=5) == 0
            assert process.stderr.read() == ""

            process = start_backend("--single-job-flow")
            assert select.select([process.stdout], [], [], 15)[0], "No single-job readiness"
            ready = json.loads(process.stdout.readline())
            assert ready["status"] == "ready" and ready["capabilities"]["worker"] is True
            address = urlsplit(ready["url"])
            assert address.scheme == "http" and address.hostname == "127.0.0.1"
            assert address.fragment == "flow"

            status, headers, body = request("GET", "/")
            assert status == 200 and "default-src 'self'" in headers["Content-Security-Policy"]
            assert "职业工作台" in body.decode()
            assert request("GET", "/static/app.js")[0] == 200
            assert request("GET", "/static/handoff.js")[0] == 200
            assert request("GET", "/static/handoff.css")[0] == 200
            assert request("GET", "/static/application_flow.js")[0] == 200
            status, _, body = request("GET", "/api/state")
            assert status == 200
            state = json.loads(body)
            assert len(state["evidence"]) == 1 and state["applications"] == []
            status, _, body = request("GET", "/api/worker/state")
            worker = json.loads(body)
            # Flow owns the worker. The old unbound control endpoint stays disabled.
            assert status == 200 and worker["enabled"] is False
            assert not lab_root.exists()
            status, _, body = request("GET", "/api/flow/state")
            flow = json.loads(body)
            assert status == 200
            single_job_mode = verify_flow_mode(flow, support, preparation=False)
            status, _, body = request("GET", "/api/handoff/state")
            handoff = json.loads(body)
            assert status == 200 and handoff["enabled"] is False
            assert not handoff_root.exists()
            assert (resources / "system/scripts/run_application_worker.py").is_file()
            assert (resources / "system/scripts/run_codex_handoff.py").is_file()
            assert {"playwright", "greenlet", "pyee"} <= manifest["dependencies"].keys()
            assert request("GET", "/api/evidence/" + state["evidence"][0]["id"])[0] == 200
            status, _, body = request("GET", "/api/interview/protocol")
            assert status == 200 and "项目介绍" in body.decode()
            assert request("GET", "/api/public-site")[0] == 404
            public_source = career / "reports/public-site/site-content.json"
            public_source.parent.mkdir()
            public_source.write_text(
                json.dumps(
                    {
                        "schema_version": "public-site-source/v1",
                        "publication_status": "public",
                        "profile": {"name": "Synthetic Public Person"},
                    }
                )
            )
            status, _, body = request("GET", "/api/public-site")
            public_site = json.loads(body)
            assert status == 200 and public_site["profile"]["name"] == "Synthetic Public Person"
            assert public_site["authority"] == "public-presentation"
            assert request("GET", "/api/state", headers={"Host": "attacker.invalid"})[0] == 403
            payload = {
                "company": "Synthetic Company",
                "role_title": "Research Engineer",
                "status": "applied",
                "linked_evidence": [state["evidence"][0]["id"]],
            }
            raw = json.dumps(payload).encode()
            assert request("POST", "/api/applications", body=raw)[0] == 403
            write_headers = {
                "Content-Type": "application/json",
                "Origin": urlunsplit((address.scheme, address.netloc, "", "", "")),
                "X-CSRF-Token": state["csrf_token"],
            }
            status, _, body = request("POST", "/api/applications", body=raw, headers=write_headers)
            assert status == 201, body
            created = json.loads(body)["application"]
            changes = json.dumps(
                {"status": "interview_scheduled", "revision": created["revision"]}
            ).encode()
            assert (
                request(
                    "PATCH",
                    "/api/applications/" + created["id"],
                    body=changes,
                    headers=write_headers,
                )[0]
                == 200
            )
            status, _, body = request("GET", "/api/export.csv")
            assert status == 200 and b"Synthetic Company" in body
            draft = json.dumps(
                {
                    "company": "Synthetic Draft",
                    "role_title": "Engineer",
                    "url": "https://boards.greenhouse.io/example/jobs/123",
                    "application_strategy": "batch",
                }
            ).encode()
            status, _, body = request(
                "POST", "/api/applications", body=draft, headers=write_headers
            )
            assert status == 201
            saved = json.loads(body)["application"]
            task_body = json.dumps(
                {"application_id": saved["id"], "revision": saved["revision"]}
            ).encode()
            assert request("POST", "/api/automation/prepare", body=task_body)[0] == 403
            status, _, body = request(
                "POST", "/api/automation/prepare", body=task_body, headers=write_headers
            )
            assert status == 200, body
            task = json.loads(body)
            assert task["mode"] == "review_only" and task["executed"] is False
            assert task["prompt"].startswith("$job-apply:job-apply")
            status, _, body = request("GET", "/api/applications/" + saved["id"])
            assert (
                status == 200 and json.loads(body)["application"]["revision"] == saved["revision"]
            )

            # The backup lane is opt-in and uses its own store after the flow server closes.
            process.stdin.close()
            assert process.wait(timeout=5) == 0
            assert process.stderr.read() == ""
            process = start_backend("--codex-handoff")
            assert select.select([process.stdout], [], [], 15)[0], "No handoff readiness"
            ready = json.loads(process.stdout.readline())
            address = urlsplit(ready["url"])
            assert ready["status"] == "ready" and address.fragment == "handoff"
            status, _, body = request("GET", "/api/state")
            state = json.loads(body)
            write_headers = {
                "Content-Type": "application/json",
                "Origin": urlunsplit((address.scheme, address.netloc, "", "", "")),
                "X-CSRF-Token": state["csrf_token"],
            }
            status, _, body = request("GET", "/api/handoff/state")
            handoff = json.loads(body)
            assert status == 200 and handoff["enabled"] is True
            assert handoff["execution_lane"] == "codex" and handoff["active_task"] is None
            assert handoff["tasks"] == [] and handoff_root.is_dir()

            # These are synthetic executor reports and human assertions. No ATS page is opened.
            job_url = "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789abc"
            status, _, body = request(
                "POST",
                "/api/applications",
                body=json.dumps(
                    {
                        "company": "Synthetic Handoff",
                        "role_title": "Synthetic Engineer",
                        "url": job_url,
                        "application_strategy": "manual",
                    }
                ).encode(),
                headers=write_headers,
            )
            assert status == 201, body
            application = json.loads(body)["application"]

            def handoff_request(action, payload):
                status, _, raw = request(
                    "POST",
                    "/api/handoff/" + action,
                    body=json.dumps(payload).encode(),
                    headers=write_headers,
                )
                assert status == 200, raw
                return json.loads(raw)

            approved_pdf = resume_pdf.read_bytes()
            approved_sha = hashlib.sha256(approved_pdf).hexdigest()
            assert len(approved_pdf) <= 700_000
            handoff = handoff_request(
                "prepare",
                {
                    "application_id": application["id"],
                    "revision": application["revision"],
                    "country": "CHE",
                    "filename": resume_pdf.name,
                    "file_base64": base64.b64encode(approved_pdf).decode(),
                    "acknowledge": True,
                },
            )
            task = handoff["active_task"]
            task_id = task["id"]
            assert task["status"] == "prepared"
            assert task["file_sha256"] == approved_sha
            assert Path(task["file_path"]).read_bytes() == approved_pdf
            assert "不点击 Submit/Send" in task["prompt"]
            handoff_statuses = [task["status"]]
            handoff = handoff_request(
                "claim",
                {
                    "task_id": task_id,
                    "task_revision": task["revision"],
                    "owner": "synthetic-package-acceptance",
                },
            )
            token = handoff["claim_token"]
            task = handoff["active_task"]
            assert task["status"] == "claimed"
            handoff_statuses.append(task["status"])
            status, _, body = request("GET", "/api/handoff/state")
            assert status == 200 and token.encode() not in body
            handoff = handoff_request(
                "readback",
                {
                    "task_id": task_id,
                    "task_revision": task["revision"],
                    "claim_token": token,
                    "result": "ready",
                    "page_url": job_url,
                    "source": "Synthetic package fixture; no ATS page was opened",
                    "fields": [{"question": "Full name", "value": "Synthetic Person"}],
                    "attachment": {"filename": resume_pdf.name, "sha256": approved_sha},
                    "missing": [],
                },
            )
            task = handoff["active_task"]
            assert task["status"] == "ready_for_review"
            handoff_statuses.append(task["status"])
            status, _, body = request(
                "POST",
                "/api/handoff/submitted",
                body=json.dumps(
                    {
                        "task_id": task_id,
                        "task_revision": task["revision"],
                        "acknowledge": True,
                        "source": "Synthetic rejected submission before human review",
                    }
                ).encode(),
                headers=write_headers,
            )
            assert status == 409 and json.loads(body)["error"] == "human_review_required"
            for action, expected, application_status in (
                ("review", "reviewed", "drafting"),
                ("submitted", "submitted", "applied"),
                ("receipt", "confirmed", "confirmation_received"),
            ):
                handoff = handoff_request(
                    action,
                    {
                        "task_id": task_id,
                        "task_revision": task["revision"],
                        "acknowledge": True,
                        "source": "Synthetic human assertion; no actual ATS submission",
                        **(
                            {"locator": "Synthetic package receipt-42"}
                            if action == "receipt"
                            else {}
                        ),
                    },
                )
                task = next(item for item in handoff["tasks"] if item["id"] == task_id)
                assert task["status"] == expected
                handoff_statuses.append(task["status"])
                status, _, body = request("GET", "/api/applications/" + application["id"])
                assert status == 200
                assert json.loads(body)["application"]["status"] == application_status
            assert task["review"]["kind"] == "human_assertion"
            assert task["submission"]["kind"] == "human_assertion"
            assert task["receipt"]["kind"] == "human_assertion"
            assert handoff["active_task"] is None
            assert task["pending_sync"] is None and not task["release_pending"]
            assert not lab_root.exists()
            process.stdin.close()
            assert process.wait(timeout=5) == 0
            assert process.stderr.read() == ""
            try:
                HTTPConnection(address.hostname, address.port, timeout=1).connect()
            except OSError:
                pass
            else:
                raise AssertionError("Backend port remained open after parent EOF")

            # Reopen the same disposable roots to verify durable task and note readback.
            process = start_backend("--codex-handoff")
            assert select.select([process.stdout], [], [], 15)[0], "No backend restart readiness"
            ready = json.loads(process.stdout.readline())
            assert ready["status"] == "ready"
            address = urlsplit(ready["url"])
            assert address.scheme == "http" and address.hostname == "127.0.0.1"
            status, _, body = request("GET", "/api/handoff/state")
            assert status == 200 and token.encode() not in body
            persisted = json.loads(body)
            task = next(item for item in persisted["tasks"] if item["id"] == task_id)
            assert task["status"] == "confirmed" and persisted["active_task"] is None
            assert len(task["readbacks"]) == 1
            assert task["file_sha256"] == approved_sha
            assert Path(task["file_path"]).read_bytes() == approved_pdf
            status, _, body = request("GET", "/api/applications/" + application["id"])
            assert status == 200
            assert json.loads(body)["application"]["status"] == "confirmation_received"
            status, _, body = request("GET", "/api/worker/state")
            assert status == 200 and json.loads(body)["enabled"] is False
            assert not lab_root.exists()
            process.stdin.close()
            assert process.wait(timeout=5) == 0
            assert process.stderr.read() == ""
            subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", str(relocated)], check=True
            )
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    return {
        "autofill_handoff": "verified-review-only",
        "signature": "verified",
        "signature_after_document_reads": "verified",
        "relocation": "passed",
        "bundled_runtime": "passed",
        "bundled_playwright_dependencies": "present",
        "resume_pdf_export": "not-run-latex-service-required",
        "bundled_worker_entrypoint": "passed",
        "bundled_handoff_entrypoint": "passed-read-only-help",
        "default_execution_lane": default_mode["mode"],
        "automatic_worker_enabled": default_mode["worker_enabled"],
        "launch_modes": {"default": default_mode, "explicit_single_job": single_job_mode},
        "isolated_automation_lab_created": False,
        "codex_handoff_lifecycle": {
            "source": "synthetic-loopback-http",
            "states": handoff_statuses,
            "approved_pdf_copy": "byte-verified",
            "persistence_after_restart": "passed",
        },
        "manual_submit_boundary": "human-assertions-only; no actual ATS submission",
        "worker_autostart": False,
        "application_create_edit_export": "passed",
        "public_website_projection": "passed",
        "host_csrf_guards": "passed",
        "parent_eof_shutdown": "passed",
        "personal_data_used": False,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify(args.app.resolve(strict=True))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        for name in ("stdout", "stderr"):
            output = getattr(error, name)
            if output:
                if isinstance(output, bytes):
                    output = output.decode("utf-8", errors="replace")
                error.add_note(f"Captured {name}:\n{output}")
        raise
    text = json.dumps(result, indent=2) + "\n"
    if args.report:
        with args.report.open("x") as handle:
            handle.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
