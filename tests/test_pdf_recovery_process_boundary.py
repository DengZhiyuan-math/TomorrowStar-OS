"""A killed backend preserves a saved synthetic PDF receipt before adoption.

The PDF child copies a fixture. This is neither a compiler nor installed native
App acceptance. Process death is real; renderer configuration is fixed for replay.
"""

import json
import select
import signal
import subprocess
import sys
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
import json,subprocess,sys,threading
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import ApplicationResumeStore
from career_evidence_graph.career_portal_data import ApplicationStore,CareerCatalog
apps,career,resumes,flow_root,pdf_sample,configuration,task_id=sys.argv[2:]
def compile_latex(binding):
    pdf=Path(resumes)/current_attempt[0]/"resume.pdf"
    # A distinct process finishes before the receipt barrier; no orphan is left.
    result=subprocess.run([sys.executable,'-I','-B','-c',
        'import sys;from pathlib import Path;'
        'Path(sys.argv[2]).write_bytes(Path(sys.argv[1]).read_bytes())',
        pdf_sample,str(pdf)],stdin=subprocess.DEVNULL,capture_output=True,timeout=5)
    assert result.returncode==0,result.stderr
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
    result=store.export_for_draft(task['draft_id'],task['draft_sha256'],
        task_inputs=task['inputs'],export_id=task['stages']['export']['attempt_id'],
        prism=task['prism'],automatic_materials=True)
    print(json.dumps({'attempt_id':result['id']}),flush=True)
    # Callback cannot adopt before the controller kills this backend.
    threading.Event().wait()
flow=ApplicationFlowService(store.applications,Path(flow_root),preparation_only=True,
    callbacks={'prism_source':source_snapshot,
        'verify_draft':lambda task:store._current_export_draft(
        task['draft_id'],task['draft_sha256'],task['inputs']),
        'export':export,'prism_export_configuration':store.export_configuration_revision})
task=flow.snapshot(task_id)['active_task']
flow.request('export-pdf',{'task_id':task['id'],'task_revision':task['revision'],
    'draft_id':task['draft_id'],'draft_sha256':task['draft_sha256']})
threading.Event().wait()
"""


def test_backend_killed_after_receipt_reopens_unadopted_then_rechecks_same_attempt(
    full_latex, tmp_path
):
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
    draft_before = {
        str(p.relative_to(store.root)): p.read_bytes()
        for p in (store.root / task["draft_id"]).rglob("*")
        if p.is_file()
    }
    process = subprocess.Popen(
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
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0], "PDF receipt barrier not reached"
        line = process.stdout.readline()
        assert line, process.communicate(timeout=2)[1]
        attempt = json.loads(line)["attempt_id"]
        retained = {p.name: p.read_bytes() for p in (store.root / attempt).iterdir()}
        assert json.loads(retained["export.json"])["status"] == "complete"
        process.kill()
        assert process.wait(timeout=5) == -signal.SIGKILL
        assert process.stderr.read() == ""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()

    forbidden_calls = []

    def unexpected(task):
        forbidden_calls.append(task)
        raise AssertionError("Reopening or rechecking must not rerun a stage")

    def verify_materials(task):
        receipt = store.read_export(task["resume_id"])
        assert receipt["pdf_sha256"] == task["resume_sha256"]

    reopened = ApplicationFlowService(
        store.applications,
        root,
        preparation_only=True,
        callbacks={
            "prism_source": source_snapshot,
            "analysis": unexpected,
            "resume": unexpected,
            "export": unexpected,
            "verify_materials": verify_materials,
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
    try:
        stopped = reopened.snapshot(task["id"])["active_task"]
        assert stopped["status"] == "needs_recheck"
        assert stopped["draft_id"] == task["draft_id"]
        assert stopped["draft_review"] == task["draft_review"]
        assert stopped["inputs"] == task["inputs"]
        assert stopped["resume_id"] is None and not stopped["materials_confirmed"]
        assert stopped["worker_ref"] is None
        assert stopped["stages"]["export"]["attempt_id"] == attempt
        assert stopped["recovery_history"][-1]["attempt_id"] == attempt
        assert not any(row["stage"] == "export" and row["adopted"] for row in stopped["artifacts"])
        assert reopened.snapshot(task["id"])["active_task"] == stopped
        with pytest.raises(PortalDataError) as error:
            export_request(reopened, stopped, retry=True)
        assert error.value.code == "flow_export_recheck_required"
        adopted = reopened.recheck_export(stopped["id"], stopped["revision"])
        assert adopted["status"] == "materials_ready" and adopted["resume_id"] == attempt
        assert adopted["stages"]["export"]["attempt_id"] == attempt
        assert adopted["recovery_history"] == stopped["recovery_history"]
        assert adopted["artifacts"][-1]["reconciled"] is True
        assert adopted["materials_confirmed"] and adopted["worker_ref"] is None
        assert adopted["material_binding"]["pdf_sha256"] == adopted["resume_sha256"]
        assert adopted["material_binding"]["human_reviewed"] is False
        assert not adopted.get("material_reviews")
        assert forbidden_calls == [] and len(model_calls) == 1
        assert {p.name: p.read_bytes() for p in (store.root / attempt).iterdir()} == retained
        assert {
            str(p.relative_to(store.root)): p.read_bytes()
            for p in (store.root / task["draft_id"]).rglob("*")
            if p.is_file()
        } == draft_before
    finally:
        reopened.close()
