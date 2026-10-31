"""Read-only single-task gates use synthetic default-policy artifacts."""

import hashlib
import json
from copy import deepcopy

import pytest

from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.application_match import POLICY_VERSION, match_configuration_revision
from career_evidence_graph.application_resume import (
    ApplicationResumeStore,
    career_source_snapshot,
    resume_configuration_revision,
)
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog


@pytest.fixture
def legacy_unbound_run(tmp_path):
    application_root, legacy = tmp_path / "applications", tmp_path / "legacy"
    application_root.mkdir()
    legacy.mkdir()
    applications = ApplicationStore(application_root)
    old = [
        applications.create_application(
            {
                "company": f"Synthetic {index}",
                "role_title": "Engineer",
                "status": "drafting",
                "url": f"https://jobs.lever.co/synthetic/00000000-0000-0000-0000-{index:012d}",
            }
        )
        for index in (1, 2)
    ]
    rows = [
        {
            "application_id": app["id"],
            "revision": app["revision"],
            "job_url": app["url"],
            "status": "needs_recheck",
            "page_open": True,
            "intent": {"action": "fill"},
        }
        for app in old
    ]
    (legacy / "run.json").write_text(
        json.dumps({"schemaVersion": 1, "control": "paused", "jobs": rows})
    )
    (legacy / "retained-resume.pdf").write_bytes(b"%PDF-1.4 synthetic retained attachment")
    (legacy / "retained-answers.json").write_text('{"answers": []}')
    candidate = applications.create_application(
        {
            "company": "Synthetic different target",
            "role_title": "Engineer",
            "status": "drafting",
            "url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000003",
        }
    )
    return applications, legacy, rows, candidate


def test_missing_root_legacy_run_can_protect_verified_targets_without_blocking_a_different_job(
    legacy_unbound_run,
):
    from career_evidence_graph.application_single_binding import check_legacy_roots

    applications, legacy, _, candidate = legacy_unbound_run
    before = {path.name: path.read_bytes() for path in legacy.iterdir()}
    check_legacy_roots(applications, [legacy], candidate["id"], candidate["url"])
    assert {path.name: path.read_bytes() for path in legacy.iterdir()} == before
    assert "applications_root" not in json.loads((legacy / "run.json").read_text())
    assert not (applications.root / ".execution").exists()


@pytest.mark.parametrize("intent", ["unknown", {"action": "unknown"}])
def test_missing_root_adapter_does_not_accept_unknown_action_state(legacy_unbound_run, intent):
    from career_evidence_graph.application_single_binding import check_legacy_roots
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, legacy, _, candidate = legacy_unbound_run
    path = legacy / "run.json"
    record = json.loads(path.read_text())
    record["jobs"][0]["intent"] = intent
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        check_legacy_roots(applications, [legacy], candidate["id"], candidate["url"])
    assert error.value.code == "single_legacy_invalid"
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-id",
        "empty-id",
        "unknown-id",
        "missing-revision",
        "invalid-revision",
        "stale-revision",
        "second-row-stale",
        "current-note-changed",
        "missing-url",
        "different-url",
        "unknown-status",
        "missing-page",
        "missing-intent",
        "empty-jobs",
        "null-root",
        "empty-root",
        "different-root",
        "corrupt",
        "symlink",
        "schema-bool",
        "control",
    ],
)
def test_missing_root_adapter_rejects_any_unverifiable_row_or_explicit_root(
    legacy_unbound_run, mutation
):
    from career_evidence_graph.application_single_binding import check_legacy_roots
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, legacy, _, candidate = legacy_unbound_run
    path = legacy / "run.json"
    record = json.loads(path.read_text())
    row = record["jobs"][0]
    if mutation.startswith("missing-"):
        row.pop(
            {
                "missing-id": "application_id",
                "missing-revision": "revision",
                "missing-url": "job_url",
                "missing-page": "page_open",
                "missing-intent": "intent",
            }[mutation]
        )
    elif mutation == "empty-id":
        row["application_id"] = ""
    elif mutation == "unknown-id":
        row["application_id"] = "unknown-synthetic-id"
    elif mutation == "invalid-revision":
        row["revision"] = "0" * 63
    elif mutation == "stale-revision":
        row["revision"] = "0" * 64
    elif mutation == "second-row-stale":
        record["jobs"][1]["revision"] = "0" * 64
    elif mutation == "current-note-changed":
        app = applications.get_application(row["application_id"])
        applications.update_application(
            app["id"], {"notes": "Changed unrelated synthetic note."}, app["revision"]
        )
    elif mutation == "different-url":
        row["job_url"] = candidate["url"]
    elif mutation == "unknown-status":
        row["status"] = "unknown"
    elif mutation == "empty-jobs":
        record["jobs"] = []
    elif mutation in {"null-root", "empty-root", "different-root"}:
        record["applications_root"] = {
            "null-root": None,
            "empty-root": "",
            "different-root": str(legacy / "different-root"),
        }[mutation]
    elif mutation == "schema-bool":
        record["schemaVersion"] = True
    elif mutation == "control":
        record["control"] = "unknown"
    path.write_text("corrupt" if mutation == "corrupt" else json.dumps(record))
    if mutation == "symlink":
        source = path.with_suffix(".original")
        path.rename(source)
        path.symlink_to(source)
    before = {item.name: item.read_bytes() for item in legacy.iterdir()}
    with pytest.raises(PortalDataError) as error:
        check_legacy_roots(applications, [legacy], candidate["id"], candidate["url"])
    assert error.value.code == "single_legacy_invalid"
    assert {item.name: item.read_bytes() for item in legacy.iterdir()} == before


@pytest.mark.parametrize("same_id", [True, False])
def test_verified_missing_root_run_still_blocks_the_old_active_target(legacy_unbound_run, same_id):
    from career_evidence_graph.application_single_binding import check_legacy_roots
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, legacy, rows, candidate = legacy_unbound_run
    path = legacy / "run.json"
    record = json.loads(path.read_text())
    record["jobs"][0]["job_url"] = rows[0]["job_url"] + "/apply?source=synthetic"
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    target_id = rows[0]["application_id"] if same_id else candidate["id"]
    with pytest.raises(PortalDataError) as error:
        check_legacy_roots(
            applications, [legacy], target_id, rows[0]["job_url"] + "?other=synthetic"
        )
    assert error.value.code == "single_legacy_active"
    assert path.read_bytes() == before


@pytest.mark.parametrize("filename", ["handoff.json", "prepare-pending.json"])
def test_other_legacy_files_do_not_inherit_the_missing_root_run_adapter(
    legacy_unbound_run, filename
):
    from career_evidence_graph.application_single_binding import check_legacy_roots
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, legacy, _, candidate = legacy_unbound_run
    (legacy / "run.json").rename(legacy / filename)
    before = {item.name: item.read_bytes() for item in legacy.iterdir()}
    with pytest.raises(PortalDataError) as error:
        check_legacy_roots(applications, [legacy], candidate["id"], candidate["url"])
    assert error.value.code == "single_legacy_invalid"
    assert {item.name: item.read_bytes() for item in legacy.iterdir()} == before


def test_verified_old_target_scope_never_overrides_an_existing_claim_for_the_new_target(
    legacy_unbound_run,
):
    from career_evidence_graph.application_execution import reserve_execution
    from career_evidence_graph.application_single_binding import check_legacy_roots
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, legacy, _, candidate = legacy_unbound_run
    reserve_execution(applications, candidate["id"], "synthetic-other-executor", "codex")
    claim = next((applications.root / ".execution").glob("*.json"))
    before = claim.read_bytes()
    with pytest.raises(PortalDataError) as error:
        check_legacy_roots(applications, [legacy], candidate["id"], candidate["url"])
    assert error.value.code == "single_legacy_active"
    assert claim.read_bytes() == before


def test_bound_legacy_run_blocks_an_alias_of_its_target_even_with_a_different_application_id(
    legacy_unbound_run,
):
    from career_evidence_graph.application_single_binding import check_legacy_roots
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, legacy, rows, candidate = legacy_unbound_run
    path = legacy / "run.json"
    record = json.loads(path.read_text())
    record["applications_root"] = str(applications.root)
    record["jobs"][0]["job_url"] = rows[0]["job_url"] + "/apply?source=synthetic"
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        check_legacy_roots(
            applications, [legacy], candidate["id"], rows[0]["job_url"] + "?other=synthetic"
        )
    assert error.value.code == "single_legacy_active"
    assert path.read_bytes() == before


@pytest.fixture
def bound_single(tmp_path):
    return make_bound_single(tmp_path)


def make_bound_single(
    tmp_path,
    *,
    job_description="Build Python services.",
    job_url="https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001",
):
    career, flow, applications_root = (
        tmp_path / name for name in ("career", "flow", "applications")
    )
    for path in (career, flow, applications_root):
        path.mkdir()
    applications = ApplicationStore(applications_root)
    app = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": job_description,
            "status": "drafting",
            "url": job_url,
        }
    )
    catalog = CareerCatalog(career)
    snapshot = career_source_snapshot(catalog)
    engine = match_configuration_revision()
    inputs = {
        "jd_revision": job_input_revision(app),
        "sources_revision": snapshot["revision"],
        "analysis_configuration_revision": digest({"engine": engine, "adapter": "default"}),
        "resume_configuration_revision": resume_configuration_revision(),
        "historical_benchmark_revision": digest({"status": "missing", "revision": None}),
    }
    analysis_id, resume_id, task_id, batch_id = (value * 32 for value in "abcd")
    report = {
        "id": analysis_id,
        "application_id": app["id"],
        "jd_revision": job_input_revision(app),
        "source_snapshot_revision": snapshot["revision"],
        "configuration_revision": engine,
        "policy_version": POLICY_VERSION,
        "requirements": [],
        "score": {"lower": 0, "upper": 100, "coverage": 0, "eligibility": "not_specified"},
        "selected_source_ids": [],
    }
    directory = flow / "analyses" / analysis_id
    directory.mkdir(parents=True)
    (directory / "analysis.json").write_text(json.dumps(report))
    resumes = ApplicationResumeStore(applications, catalog, flow / "resumes")
    raw = b"%PDF-1.4 synthetic approved bytes"
    sha = hashlib.sha256(raw).hexdigest()
    directory = flow / "resumes" / resume_id
    directory.mkdir()
    (directory / "resume.pdf").write_bytes(raw)
    draft = {
        "application_id": app["id"],
        "pdf_sha256": sha,
        "generation_policy": resumes.configuration(),
        "analysis_binding": {
            "analysis_id": analysis_id,
            **{
                key: report[key]
                for key in (
                    "jd_revision",
                    "source_snapshot_revision",
                    "configuration_revision",
                    "policy_version",
                )
            },
        },
    }
    (directory / "sources.json").write_text(json.dumps(draft))
    task = {
        "id": task_id,
        "application_id": app["id"],
        "status": "queued",
        "job_binding": job_input_revision(app),
        "inputs": inputs,
        "analysis_id": analysis_id,
        "resume_id": resume_id,
        "resume_sha256": sha,
        "materials_confirmed": True,
        "worker_ref": {"batch_id": batch_id, "job_id": app["id"], "status": "queued"},
        "artifacts": [{"stage": "analysis", "adopted": True, "result": report}],
        "hard_condition_resolutions": [],
    }
    task["artifacts"][0]["inputs"] = deepcopy(inputs)
    task["artifacts"].append(
        {
            "stage": "resume",
            "adopted": True,
            "inputs": deepcopy(inputs),
            "result": {
                "id": resume_id,
                "application_id": app["id"],
                "pdf_sha256": sha,
                "analysis_binding": draft["analysis_binding"],
                "resume_configuration_revision": inputs["resume_configuration_revision"],
            },
        }
    )
    task["send_approval"] = {
        "country": "CHE",
        "job_url": app["url"],
        "resume_id": resume_id,
        "resume_sha256": sha,
        "analysis_id": analysis_id,
        "inputs": deepcopy(inputs),
        "confirmed": True,
        "verified_by": "user",
        "at": 1.0,
    }
    task["revision"] = digest(task)
    (flow / "flow.json").write_text(
        json.dumps(
            {"schemaVersion": 1, "applications_root": str(applications.root), "tasks": [task]}
        )
    )
    binding = {
        "schemaVersion": 1,
        **{
            key: deepcopy(task[key])
            for key in (
                "job_binding",
                "inputs",
                "analysis_id",
                "resume_id",
                "resume_sha256",
                "hard_condition_resolutions",
            )
        },
        "task_id": task_id,
        "job_url": app["url"],
        "country": "CHE",
        "send_confirmed": True,
    }
    job = {
        "application_id": app["id"],
        "job_url": app["url"],
        "country": "CHE",
        "file_sha256": sha,
        "send_confirmed": True,
        "single_binding": binding,
        "workflow": "single",
    }
    return applications, flow, career, job, batch_id


def test_current_default_policy_materials_can_be_checked_without_any_writes(bound_single):
    from career_evidence_graph.application_single_binding import check_single_binding

    applications, flow, career, job, batch = bound_single
    before = {str(path): path.read_bytes() for path in flow.rglob("*") if path.is_file()}
    check_single_binding(applications, flow, career, job, batch)
    after = {str(path): path.read_bytes() for path in flow.rglob("*") if path.is_file()}
    assert after == before
    assert not (applications.root / ".execution").exists()


def test_legacy_paused_page_blocks_same_job_without_initializing_old_services(
    bound_single, tmp_path
):
    from career_evidence_graph.application_single_binding import check_legacy_roots
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, _, _, job, _ = bound_single
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    record = {
        "schemaVersion": 1,
        "applications_root": str(applications.root),
        "control": "paused",
        "jobs": [
            {
                "application_id": job["application_id"],
                "job_url": job["job_url"],
                "status": "cancelled",
                "page_open": True,
                "intent": None,
            }
        ],
    }
    path = legacy / "run.json"
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        check_legacy_roots(applications, [legacy], job["application_id"], job["job_url"])
    assert error.value.code == "single_legacy_active"
    assert path.read_bytes() == before
    assert list(legacy.iterdir()) == [path]


def test_browser_material_gate_keeps_the_original_pdf_after_career_source_changes(
    bound_single, tmp_path, monkeypatch
):
    import base64

    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    applications, flow, career, frozen, _ = bound_single
    path = flow / "flow.json"
    state = json.loads(path.read_text())
    task = state["tasks"][0]
    task.update(worker_ref=None, status="materials_ready")
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    path.write_text(json.dumps(state))
    service = WorkerService(
        applications,
        tmp_path / "worker",
        fixture_origin="http://127.0.0.1:9999",
        single_flow_root=flow,
        single_career_root=career,
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    app = applications.get_application(frozen["application_id"])
    raw = (flow / "resumes" / task["resume_id"] / "resume.pdf").read_bytes()
    item = {
        "application_id": app["id"],
        "revision": app["revision"],
        "country": "CHE",
        "filename": "synthetic.pdf",
        "file_base64": base64.b64encode(raw).decode(),
        "single_binding": frozen["single_binding"],
    }
    prepared = service.request(
        "prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]}
    )
    task.update(
        worker_ref={"batch_id": prepared["batch_id"], "job_id": app["id"], "status": "queued"},
        status="queued",
    )
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    path.write_text(json.dumps(state))
    runner = ApplicationRunner(service.store, None)
    current = service.store.load()["jobs"][0]
    runner.check_inputs(current, material_required=True)
    (career / "contributions").mkdir()
    (career / "contributions" / "changed.md").write_text(
        "# New synthetic source\n\n## Scope\nNew evidence."
    )
    # APP-04: a career source revision keeps the original PDF usable.
    runner.check_inputs(current, material_required=True)


def test_single_binding_accepts_tracking_only_variation_of_the_same_approved_target(bound_single):
    from career_evidence_graph.application_single_binding import check_single_binding

    applications, flow, career, job, batch = bound_single
    job["single_binding"]["job_url"] += "?source=synthetic-tracking"
    check_single_binding(applications, flow, career, job, batch)


def test_material_confirmation_without_task_send_approval_cannot_authorize_filling(bound_single):
    from career_evidence_graph.application_single_binding import check_single_binding
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, flow, career, job, batch = bound_single
    state = json.loads((flow / "flow.json").read_text())
    task = state["tasks"][0]
    task.pop("send_approval")
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    (flow / "flow.json").write_text(json.dumps(state))
    with pytest.raises(PortalDataError) as error:
        check_single_binding(applications, flow, career, job, batch)
    assert error.value.code == "single_binding_invalid"


@pytest.mark.parametrize("mutation", ["analysis-inputs", "resume-unadopted"])
def test_files_without_current_adopted_artifact_lineage_are_not_approved_materials(
    bound_single, mutation
):
    from career_evidence_graph.application_single_binding import check_single_binding
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, flow, career, job, batch = bound_single
    state = json.loads((flow / "flow.json").read_text())
    task = state["tasks"][0]
    if mutation == "analysis-inputs":
        task["artifacts"][0]["inputs"]["sources_revision"] = "stale"
    else:
        task["artifacts"][1]["adopted"] = False
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    (flow / "flow.json").write_text(json.dumps(state))
    with pytest.raises(PortalDataError) as error:
        check_single_binding(applications, flow, career, job, batch)
    assert error.value.code == "single_binding_invalid"


def test_unbound_flow_can_recover_an_exact_published_paused_worker_reservation(
    bound_single, tmp_path
):
    from career_evidence_graph.application_execution import automated_owner, reserve_execution
    from career_evidence_graph.application_single_binding import check_single_binding

    applications, flow, career, job, batch = bound_single
    state = json.loads((flow / "flow.json").read_text())
    task = state["tasks"][0]
    task.update(worker_ref=None, status="materials_ready")
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    (flow / "flow.json").write_text(json.dumps(state))
    runtime = tmp_path / "worker"
    runtime.mkdir()
    from career_evidence_graph._vendor import job_apply_store as helper

    # Published WorkerStore reservations have an initialized existing answer store.
    helper.Store(runtime / "answer-library").initialize()
    prepared = deepcopy(job) | {"status": "queued", "page_open": False, "intent": None}
    context = {
        "applications_root": str(applications.root),
        "flow_root": str(flow),
        "career_root": str(career),
        "legacy_roots": [],
    }
    (runtime / "run.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "applications_root": str(applications.root),
                "control": "paused",
                "batch_id": batch,
                "jobs": [prepared],
                "single_context": context,
                "worker_pid": None,
            }
        )
    )
    reserve_execution(
        applications,
        job["application_id"],
        automated_owner(runtime, batch, job["application_id"]),
        "automated",
    )
    check_single_binding(
        applications, flow, career, job, batch, allow_unbound=True, worker_root=runtime
    )


@pytest.mark.parametrize("kind", ["control", "pending-batch"])
def test_corrupt_legacy_control_and_pending_bindings_fail_closed(bound_single, tmp_path, kind):
    from career_evidence_graph.application_single_binding import check_legacy_roots
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, _, _, job, _ = bound_single
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    record = {"schemaVersion": 1, "applications_root": str(applications.root)}
    if kind == "control":
        record.update(control="corrupt", jobs=[])
        filename = "run.json"
    else:
        record.update(batch_id="unbound", application_ids=["unrelated-synthetic-id"])
        filename = "prepare-pending.json"
    (legacy / filename).write_text(json.dumps(record))
    with pytest.raises(PortalDataError) as error:
        check_legacy_roots(applications, [legacy], job["application_id"], job["job_url"])
    assert error.value.code == "single_legacy_invalid"


@pytest.mark.parametrize(
    "mutation", ["pdf", "analysis", "target", "jd", "country", "batch", "config", "symlink"]
)
def test_changed_materials_and_target_cannot_reuse_an_approved_single_binding(
    bound_single, mutation
):
    from career_evidence_graph.application_single_binding import check_single_binding
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, flow, career, job, batch = bound_single
    if mutation == "pdf":
        (flow / "resumes" / job["single_binding"]["resume_id"] / "resume.pdf").write_bytes(
            b"%PDF-1.4 replaced bytes"
        )
    elif mutation == "analysis":
        path = flow / "analyses" / job["single_binding"]["analysis_id"] / "analysis.json"
        report = json.loads(path.read_text())
        report["limitations"] = ["changed receipt"]
        path.write_text(json.dumps(report))
    elif mutation in {"target", "jd"}:
        app = applications.get_application(job["application_id"])
        changes = (
            {"url": job["job_url"].replace("000001", "000002")}
            if mutation == "target"
            else {"job_description": "Changed synthetic JD."}
        )
        applications.update_application(app["id"], changes, app["revision"])
    elif mutation == "country":
        job["country"] = "USA"
    elif mutation == "batch":
        batch = "e" * 32
    elif mutation == "config":
        job["single_binding"]["inputs"]["analysis_configuration_revision"] = "stale"
    else:
        path = flow / "resumes" / job["single_binding"]["resume_id"] / "resume.pdf"
        path.rename(path.with_suffix(".original"))
        path.symlink_to(path.with_suffix(".original"))
    with pytest.raises(PortalDataError):
        check_single_binding(applications, flow, career, job, batch)


@pytest.mark.parametrize(
    "judgment,eligible,accepted",
    [
        ("unknown", None, True),
        ("partial", None, True),
        ("unknown", True, True),
        ("partial", True, True),
        ("unknown", False, False),
        ("gap", True, False),
    ],
)
def test_hard_condition_clearance_uses_explicit_user_fact_and_never_overrides_known_gap(
    bound_single, judgment, eligible, accepted
):
    from career_evidence_graph.application_single_binding import check_single_binding
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, flow, career, job, batch = bound_single
    path = flow / "flow.json"
    state = json.loads(path.read_text())
    task = state["tasks"][0]
    report = task["artifacts"][0]["result"]
    report["requirements"] = [
        {"text": "Synthetic work eligibility", "judgment": judgment, "hard_condition": True}
    ]
    (flow / "analyses" / report["id"] / "analysis.json").write_text(json.dumps(report))
    resolutions = [
        {
            "analysis_id": report["id"],
            "requirement_index": 0,
            "eligible": eligible,
            "confirmed": True,
            "verified_by": "user",
            "source": "Explicit synthetic user fact.",
            "at": 1.0,
        }
    ]
    if eligible is None:
        resolutions = []
    task["hard_condition_resolutions"] = resolutions
    job["single_binding"]["hard_condition_resolutions"] = deepcopy(resolutions)
    task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
    path.write_text(json.dumps(state))
    if accepted:
        check_single_binding(applications, flow, career, job, batch)
        if eligible is None:
            from career_evidence_graph.application_flow import task_eligibility

            assert task_eligibility(task)["status"] == "needs_input"
            assert not task["hard_condition_resolutions"]
    else:
        with pytest.raises(PortalDataError) as error:
            check_single_binding(applications, flow, career, job, batch)
        assert error.value.code == "single_eligibility_required"


def test_model_setting_changes_keep_original_verified_pdf_and_analysis_binding(
    bound_single, monkeypatch
):
    from career_evidence_graph.application_single_binding import check_single_binding

    applications, flow, career, job, batch = bound_single
    before = {
        str(path): path.read_bytes()
        for root in (flow, career)
        for path in root.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        "career_evidence_graph.application_match.match_configuration_revision",
        lambda: "new-model-settings",
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_resume.resume_configuration_revision",
        lambda: "new-resume-model-settings",
    )
    check_single_binding(applications, flow, career, job, batch)
    assert {
        str(path): path.read_bytes()
        for root in (flow, career)
        for path in root.rglob("*")
        if path.is_file()
    } == before
