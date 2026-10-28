"""A real orphaned synthetic exporter cannot be mistaken for an ended export.

The child copies a fixture after an explicit barrier. This is not native App or
real compiler acceptance. Only the test-created process group is terminated.
"""

import json
import os
import select
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_job_explanations import requirement
from test_pdf_export_flow import export_request

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError

CHILD = """
import json,os,subprocess,sys,threading
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import ApplicationResumeStore
from career_evidence_graph.career_portal_data import ApplicationStore,CareerCatalog
apps,career,resumes,flow_root,pdf_sample,configuration,task_id,release,done=sys.argv[2:]
def compile_latex(binding):
    pdf=Path(resumes)/current_attempt[0]/"resume.pdf"
    code='''import os,sys,time,json
from pathlib import Path
source,destination,release,done=map(Path,sys.argv[1:])
print(json.dumps({'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp()}),flush=True)
deadline=time.monotonic()+20
while not release.exists():
    if time.monotonic()>deadline: raise SystemExit(9)
    time.sleep(.01)
destination.write_bytes(source.read_bytes())
done.write_text('complete')
'''
    child=subprocess.Popen([sys.executable,'-I','-B','-u','-c',code,
        pdf_sample,str(pdf),release,done],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    print(child.stdout.readline(),end='',flush=True)
    child.wait(timeout=22)
    return {"build":{"main":binding["main"],"exit":0,"pdf_updated":True},"pdf":pdf.read_bytes()}
store=ApplicationResumeStore(ApplicationStore(Path(apps)),CareerCatalog(Path(career)),
    Path(resumes))
config=json.loads(configuration)
store.export_configuration=lambda:config['export']
store.configuration=lambda **kwargs:config['resume']
current_attempt=[]
store.prism_client=SimpleNamespace(configuration=lambda:config['export'],compile=compile_latex)
def export(task):
    current_attempt[:]=[task['stages']['export']['attempt_id']]
    return store.export_for_draft(task['draft_id'],task['draft_sha256'],
        task_inputs=task['inputs'],export_id=task['stages']['export']['attempt_id'],
        prism=task['prism'],automatic_materials=True)
flow=ApplicationFlowService(store.applications,Path(flow_root),preparation_only=True,
    callbacks={'prism_source':source_snapshot,
        'verify_draft':lambda task:store._current_export_draft(
        task['draft_id'],task['draft_sha256'],task['inputs']),
        'export':export,
        'prism_export_configuration':store.export_configuration_revision})
task=flow.snapshot(task_id)['active_task']
flow.request('export-pdf',{'task_id':task['id'],'task_revision':task['revision'],
    'draft_id':task['draft_id'],'draft_sha256':task['draft_sha256']})
threading.Event().wait()
"""


def test_backend_killed_with_live_pdf_child_keeps_missing_receipt_unknown(full_latex, tmp_path):
    store, job, sources, analysis, model_calls, project, _, _ = full_latex
    binding = source_snapshot(project, "main.tex")
    analysis = analysis | {
        "requirements": [requirement() | row for row in analysis["requirements"]]
    }
    root = tmp_path / "flow"
    configuration = {"export": store.export_configuration(), "resume": store.configuration()}
    first = ApplicationFlowService(
        store.applications,
        root,
        preparation_only=True,
        callbacks={
            "prism_source": source_snapshot,
            "analysis": lambda _: analysis,
            "resume": lambda task: store.generate_for_task(
                job["id"],
                job["revision"],
                source_snapshot=sources,
                analysis=analysis,
                draft_only=True,
                task_inputs=task["inputs"],
                latex_base=binding,
            ),
            "verify_draft": lambda task: store._current_export_draft(
                task["draft_id"], task["draft_sha256"], task["inputs"]
            ),
        },
    )
    try:
        task = first.create(
            job["id"], job["revision"], inputs={"career_source_revision": sources["revision"]}
        )
        # Restore this fixture under its retained pre-JSON writing contract.
        with first.applications.write_lock():
            saved = first._load()
            first._task(saved, task["id"]).pop("material_contract", None)
            first._save(saved)
        task = first.snapshot(task["id"])["active_task"]
        first.start(task["id"], task["revision"], "analysis")
        task = wait_for(first, task["id"], lambda row: row["status"] == "analysis_ready")
        task = first.prepare_automatic_materials(
            task["id"], task["revision"], str(project), "main.tex"
        )
        first.start(task["id"], task["revision"], "resume")
        task = wait_for(first, task["id"], lambda row: row["status"] == "draft_ready")
    finally:
        first.close()
    release, done = tmp_path / "release", tmp_path / "done"
    backend = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-u",
            "-c",
            CHILD,
            str(Path(__file__).parents[1] / "src"),
            str(store.applications.root),
            str(store.catalog.root),
            str(store.root),
            str(root),
            str(Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"),
            json.dumps(configuration),
            task["id"],
            str(release),
            str(done),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    reopened = None
    try:
        assert select.select([backend.stdout], [], [], 10)[0], "PDF child barrier not reached"
        line = backend.stdout.readline()
        assert line, backend.communicate(timeout=2)[1]
        child = json.loads(line)
        assert child["ppid"] == backend.pid and child["pgid"] == backend.pid
        assert os.getpgid(child["pid"]) == backend.pid
        os.kill(child["pid"], 0)
        backend.kill()
        assert backend.wait(timeout=5) == -signal.SIGKILL
        assert backend.stderr.read() == ""
        os.kill(child["pid"], 0)
        forbidden_calls = []

        def unexpected(row):
            forbidden_calls.append(row)
            raise AssertionError("Recovery must not replay a stage")

        reopened = ApplicationFlowService(
            store.applications,
            root,
            preparation_only=True,
            callbacks={
                "prism_source": source_snapshot,
                "analysis": unexpected,
                "resume": unexpected,
                "export": unexpected,
                "verify_draft": lambda row: store._current_export_draft(
                    row["draft_id"], row["draft_sha256"], row["inputs"]
                ),
                "prism_export_configuration": store.export_configuration_revision,
                "reconcile_export": lambda row: store.reconcile_export(
                    row["stages"]["export"]["attempt_id"],
                    draft_id=row["draft_id"],
                    draft_sha256=row["draft_sha256"],
                    task_inputs=row["inputs"],
                ),
            },
        )
        stopped = reopened.snapshot(task["id"])["active_task"]
        attempt = stopped["stages"]["export"]["attempt_id"]
        directory = store.root / attempt
        intent = (directory / "export-intent.json").read_bytes()
        assert stopped["status"] == "needs_recheck"
        assert stopped["draft_review"] == task["draft_review"]
        assert stopped["inputs"] == task["inputs"]
        assert not (directory / "resume.pdf").exists()
        assert not (directory / "export.json").exists()
        # The exporter is proven alive: absence of a receipt cannot prove failure.
        with pytest.raises(PortalDataError) as error:
            reopened.recheck_export(stopped["id"], stopped["revision"])
        assert error.value.code == "resume_export_needs_recheck"
        assert reopened.snapshot(task["id"])["active_task"] == stopped
        with pytest.raises(PortalDataError) as blocked:
            export_request(reopened, stopped, retry=True)
        assert blocked.value.code == "flow_export_recheck_required"
        release.touch()
        deadline = time.monotonic() + 5
        while not done.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert done.read_text() == "complete"
        assert (directory / "resume.pdf").read_bytes() == (
            Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
        ).read_bytes()
        assert not (directory / "export.json").exists()
        with pytest.raises(PortalDataError) as late:
            reopened.recheck_export(stopped["id"], stopped["revision"])
        assert late.value.code == "resume_export_needs_recheck"
        current = reopened.snapshot(task["id"])["active_task"]
        assert current == stopped
        assert current["resume_id"] is None and not current["materials_confirmed"]
        assert current["worker_ref"] is None
        assert not any(row["stage"] == "export" and row["adopted"] for row in current["artifacts"])
        assert (directory / "export-intent.json").read_bytes() == intent
        assert forbidden_calls == [] and len(model_calls) == 1
    finally:
        if reopened:
            reopened.close()
        # The group was created by this exact Popen and observed at the barrier.
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(backend.pid, signal.SIGKILL)
        if backend.poll() is None:
            backend.wait(timeout=5)
        backend.stdout.close()
        backend.stderr.close()
