"""Shutdown races a real bounded subprocess copying a fixed synthetic PDF fixture.

This exercises durable resume exports and flow recovery, not a real PDF compiler,
native application termination, model provider, browser or application worker.
"""

import hashlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from test_application_flow import application as application
from test_existing_latex import authorize, import_existing
from test_existing_latex import existing_latex as existing_latex
from test_pdf_export_flow import export_request

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_input_binding import configuration_revision
from career_evidence_graph.career_portal_data import PortalDataError

PDF_SAMPLE = Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"


@pytest.mark.parametrize("shutdown_point", ["before_pdf_write", "after_export_save"])
def test_late_subprocess_export_stays_unadopted_across_shutdown_and_reopen(
    existing_latex, tmp_path, shutdown_point
):
    first, store, job, project = existing_latex
    entered, saved, release_return = threading.Event(), threading.Event(), threading.Event()
    allow_write = tmp_path / "allow-synthetic-pdf-write"
    child_ready = tmp_path / "synthetic-pdf-child-pid"
    children, exports = [], []
    child_code = """
import os,sys,time
from pathlib import Path
source,destination,release,ready=map(Path,sys.argv[1:])
temporary=ready.with_suffix('.tmp')
temporary.write_text(str(os.getpid()))
temporary.replace(ready)
deadline=time.monotonic()+8
while not release.exists():
    if time.monotonic()>deadline: raise SystemExit(9)
    time.sleep(.01)
destination.write_bytes(source.read_bytes())
"""

    def compile_latex(binding):
        pdf = tmp_path / "subprocess-output.pdf"
        child = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                "-u",
                "-c",
                child_code,
                str(PDF_SAMPLE),
                str(pdf),
                str(allow_write),
                str(child_ready),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(child)
        deadline = time.monotonic() + 3
        while not child_ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert child_ready.exists(), "Synthetic PDF child did not reach its bounded barrier"
        assert int(child_ready.read_text()) == child.pid
        entered.set()
        _, error = child.communicate(timeout=10)
        assert child.returncode == 0, error
        return {
            "build": {"main": binding["main"], "exit": 0, "pdf_updated": True},
            "pdf": pdf.read_bytes(),
        }

    from types import SimpleNamespace

    store.prism_client = SimpleNamespace(
        configuration=lambda: {"renderer": "synthetic-subprocess-latex"},
        compile=compile_latex,
    )

    def export(task):
        exports.append(task["stages"]["export"]["attempt_id"])
        result = store.export_for_draft(
            task["draft_id"],
            task["draft_sha256"],
            task_inputs=task["inputs"],
            export_id=exports[-1],
            prism=first.verify_prism_source(task),
        )
        saved.set()
        assert release_return.wait(8)
        return result

    def verify_materials(task):
        receipt = store.read_export(task["resume_id"])
        assert receipt["pdf_sha256"] == task["resume_sha256"]

    callbacks = first.callbacks
    callbacks.update(
        {
            "export": export,
            "verify_materials": verify_materials,
            "prism_export_configuration": lambda: configuration_revision(
                store.prism_client.configuration()
            ),
        }
    )
    observer = reopened = None
    try:
        task = import_existing(first, job, project)
        task = authorize(first, task)
        draft_bytes = (store.root / task["draft_id"] / "draft.json").read_bytes()
        export_request(first, task)
        assert entered.wait(3)
        attempt = exports[0]
        directory = store.root / attempt
        if shutdown_point == "after_export_save":
            allow_write.touch()
            assert saved.wait(3)
            assert (directory / "export.json").is_file()
        else:
            assert not (directory / "resume.pdf").exists()
        first.close()
        observer = ApplicationFlowService(
            store.applications, first.root, preparation_only=True, callbacks=callbacks
        )
        stopped = observer.snapshot(task["id"])["active_task"]
        assert stopped["id"] == task["id"] and stopped["draft_id"] == task["draft_id"]
        assert stopped["status"] == "needs_recheck"
        assert stopped["stages"]["export"]["attempt_id"] == attempt
        assert stopped["recovery_history"][-1]["attempt_id"] == attempt
        assert stopped["resume_id"] is None and not stopped["materials_confirmed"]
        with pytest.raises(PortalDataError) as blocked:
            export_request(observer, stopped, retry=True)
        assert blocked.value.code == "flow_runtime_busy"
        observer.close()
        observer = None
        allow_write.touch()
        assert saved.wait(3)
        release_return.set()
        first._thread.join(timeout=3)
        assert not first._thread.is_alive()
        first.close()
        retained = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        assert (
            hashlib.sha256(retained["resume.pdf"]).hexdigest()
            == hashlib.sha256(PDF_SAMPLE.read_bytes()).hexdigest()
        )
        assert json.loads(retained["export.json"])["status"] == "complete"
        reopened = ApplicationFlowService(
            store.applications, first.root, preparation_only=True, callbacks=callbacks
        )
        current = reopened.snapshot(task["id"])["active_task"]
        assert current == stopped
        assert current["worker_ref"] is None
        assert not any(a["stage"] == "export" and a["adopted"] for a in current["artifacts"])
        assert exports == [attempt] and store.draft(task["draft_id"])["model_mode"] == "not_used"
        assert all(child.poll() == 0 for child in children)
        with pytest.raises(PortalDataError) as blocked:
            export_request(reopened, current, retry=True)
        assert blocked.value.code == "flow_export_recheck_required"
        assert {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()} == retained
        assert (store.root / task["draft_id"] / "draft.json").read_bytes() == draft_bytes
        adopted = reopened.recheck_export(current["id"], current["revision"])
        assert adopted["resume_id"] == attempt and adopted["status"] == "resume_ready"
        assert not adopted["materials_confirmed"] and adopted["worker_ref"] is None
        assert adopted["export_authorization"]["scope"] == "technical_export"
        assert not adopted.get("material_reviews")
        assert exports == [attempt] and store.draft(task["draft_id"])["model_mode"] == "not_used"
    finally:
        allow_write.touch()
        release_return.set()
        if observer:
            observer.close()
        if reopened:
            reopened.close()
        first.close()
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
