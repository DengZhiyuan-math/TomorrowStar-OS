"""Explicit Prism editing retains the successful PDF and local version boundary."""

from copy import deepcopy
from threading import Event, Thread

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_full_latex_flow import bind, candidate
from test_full_latex_flow import latex_flow as latex_flow
from test_full_latex_generation import full_latex as full_latex
from test_p05_generation import fixed as fixed
from test_p06_versions import material as material
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph.application_flow import ApplicationFlowService, local_materials
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def local_flow(latex_flow):
    flow, task, project = latex_flow
    flow.callbacks["resume"] = lambda task: (
        candidate(task)
        | {
            "application_id": task["application_id"],
            "generation_contract": "fixed-writing/v1",
        }
    )
    task = bind(flow, task, project)
    flow.start(task["id"], task["revision"], "resume")
    task = wait_for(flow, task["id"], lambda row: row["status"] == "draft_ready")
    with flow.applications.write_lock():
        state, stored = flow._checked(task["id"], task["revision"])
        stored.update(
            automatic_materials=True,
            resume_id="1" * 32,
            resume_sha256="2" * 64,
            materials_confirmed=True,
            status="materials_ready",
        )
        stored["stages"]["export"] = {"status": "complete", "artifact_id": "1" * 32}
        stored["material_binding"] = {
            "resume_id": stored["resume_id"],
            "pdf_sha256": stored["resume_sha256"],
            "input_revision": digest(stored["inputs"]),
        }
        flow._save(state)
        task = deepcopy(stored)
    calls = []

    def start(task):
        calls.append("begin")
        return {
            "id": "editing-session",
            "status": "editing",
            "parent_draft_id": task["draft_id"],
            "parent_draft_sha256": task["draft_sha256"],
            "task_inputs": task["inputs"],
            "source_checkpoint": task["source_checkpoint"],
            "editor_url": "http://127.0.0.1:12345/",
        }

    def finish(task):
        calls.append("finish")
        return candidate(task) | {
            "id": "manual-version",
            "draft_sha256": "e" * 64,
            "application_id": task["application_id"],
            "material_version_contract": "local-material/v1",
            "prism_edit": task["prism_edit"] | {"status": "complete"},
        }

    def capture(task, export_id):
        calls.append("capture")
        return {
            "id": export_id,
            "kind": "pdf",
            "material_version_contract": "local-material/v1",
            "application_id": task["application_id"],
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
            "task_inputs": task["inputs"],
            "prism_source_revision": task["source_checkpoint"]["source_revision"],
            "source_checkpoint": deepcopy(task["source_checkpoint"]),
            "pdf_sha256": "f" * 64,
        }

    flow.callbacks.update(
        prism_edit_begin=start,
        prism_edit_finish=finish,
        prism_result_capture=capture,
        verify_draft=lambda _: None,
        verify_materials=lambda _: None,
    )
    yield flow, task, calls


def request(flow, task, action):
    return flow.request(action, {"task_id": task["id"], "task_revision": task["revision"]})


def test_explicit_edit_and_return_preserve_final_and_do_not_reenter_content_review(local_flow):
    flow, original, calls = local_flow
    opened = request(flow, original, "begin-prism-edit")
    assert opened["prism_edit"]["status"] == "editing"
    assert opened["resume_id"] == original["resume_id"]
    assert opened["material_binding"] == original["material_binding"]
    assert request(flow, opened, "begin-prism-edit") == opened
    assert flow.snapshot(opened["id"])["active_task"] == opened
    assert calls == ["begin"]
    returned = request(flow, opened, "finish-prism-edit")
    assert returned["draft_id"] == "manual-version"
    assert returned["material_source_state"] == "unexported_changes"
    assert returned["resume_id"] == original["resume_id"]
    assert returned["material_binding"] == original["material_binding"]
    assert request(flow, returned, "finish-prism-edit") == returned
    assert calls == ["begin", "finish"]
    final = request(flow, returned, "capture-prism-result")
    assert final["resume_id"] != original["resume_id"]
    assert final["resume_sha256"] == "f" * 64
    assert final["final_pdf_history"] == [
        {"resume_id": original["resume_id"], "pdf_sha256": original["resume_sha256"]}
    ]
    assert final["material_source_state"] == "current"
    assert final["materials_confirmed"] is True
    assert calls == ["begin", "finish", "capture"]


@pytest.mark.parametrize("action", ["resume", "export", "save", "legacy-edit", "bind"])
def test_active_prism_edit_blocks_all_system_source_and_export_writes(local_flow, action):
    flow, task, calls = local_flow
    task = request(flow, task, "begin-prism-edit")
    with pytest.raises(PortalDataError) as error:
        if action in {"resume", "export"}:
            flow.start(task["id"], task["revision"], action, retry=True)
        elif action == "save":
            flow.save_automatic_source(task["id"], task["revision"], "old", "New text")
        elif action == "legacy-edit":
            flow.begin_automatic_edit(task["id"], task["revision"])
        else:
            flow.bind_latex_base(task["id"], task["revision"], "/synthetic/base", "main.tex")
    assert error.value.code == "prism_edit_active"
    assert calls == ["begin"]


def test_editing_lock_survives_service_reopen_without_implicit_return(local_flow):
    flow, task, calls = local_flow
    task = request(flow, task, "begin-prism-edit")
    flow.close()
    reopened = ApplicationFlowService(
        flow.applications, flow.root, callbacks=flow.callbacks, preparation_only=True
    )
    try:
        saved = reopened.snapshot(task["id"])["active_task"]
        assert saved["prism_edit"]["status"] == "editing"
        assert saved["resume_id"] == task["resume_id"]
        assert calls == ["begin"]
    finally:
        reopened.close()


def test_local_materials_do_not_revalidate_upstream_inputs_or_current_model_settings(local_flow):
    flow, task, _ = local_flow
    flow.input_provider = lambda _: pytest.fail(
        "Delivered material cannot scan live input identity"
    )
    flow.callbacks["prism_export_configuration"] = lambda: pytest.fail(
        "Existing PDF does not depend on current configuration"
    )
    assert local_materials(task)
    assert flow._fresh(task)["id"] == task["application_id"]
    assert flow._export_configuration(task) == "local-material/v1"
    assert request(flow, task, "capture-prism-result")["status"] == "materials_ready"


@pytest.mark.parametrize("status", ["proofreading_unavailable", "source_changed"])
def test_proofreading_failure_preserves_manual_version_and_old_pdf_without_model_retry(
    local_flow, status
):
    flow, task, calls = local_flow
    finish = flow.callbacks["prism_edit_finish"]

    def failed(task):
        result = finish(task)
        result["prism_edit"].update(status=status, warnings=["Manual original retained"])
        return result

    flow.callbacks["prism_edit_finish"] = failed
    task = request(flow, task, "begin-prism-edit")
    task = request(flow, task, "finish-prism-edit")
    assert task["material_source_state"] == status
    assert task["draft_id"] == "manual-version"
    assert task["resume_id"] == "1" * 32
    assert request(flow, task, "finish-prism-edit") == task
    assert calls == ["begin", "finish"]


def test_missing_compile_result_keeps_previous_final_and_can_read_again_without_build(local_flow):
    flow, original, calls = local_flow
    capture = flow.callbacks["prism_result_capture"]

    def waiting(task, export_id):
        raise PortalDataError("prism_result_pending", "Automatic result not ready", 409)

    flow.callbacks["prism_result_capture"] = waiting
    with pytest.raises(PortalDataError, match="not ready"):
        request(flow, original, "capture-prism-result")
    saved = flow.snapshot(original["id"])["active_task"]
    assert saved["resume_id"] == original["resume_id"]
    assert saved["material_binding"] == original["material_binding"]
    assert saved["material_source_state"] == "waiting_for_result"
    flow.callbacks["prism_result_capture"] = capture
    final = request(flow, saved, "capture-prism-result")
    assert final["resume_sha256"] == "f" * 64
    assert calls == ["capture"]


def test_late_compile_readback_does_not_overwrite_newer_manual_version(local_flow):
    flow, original, _ = local_flow
    capture = flow.callbacks["prism_result_capture"]

    def late(task, export_id):
        result = capture(task, export_id)
        with flow.applications.write_lock():
            state = flow._load()
            stored = flow._task(state, task["id"])
            stored["draft_id"] = "newer-manual-version"
            flow._save(state)
        return result

    flow.callbacks["prism_result_capture"] = late
    with pytest.raises(PortalDataError) as error:
        request(flow, original, "capture-prism-result")
    assert error.value.code == "prism_result_changed"
    saved = flow.snapshot(original["id"])["active_task"]
    assert saved["draft_id"] == "newer-manual-version"
    assert saved["resume_id"] == original["resume_id"]


def test_edit_finish_releases_application_lock_but_keeps_the_tex_write_lock(local_flow):
    flow, task, _ = local_flow
    task = request(flow, task, "begin-prism-edit")
    entered, release = Event(), Event()
    finish = flow.callbacks["prism_edit_finish"]
    results = []

    def blocked(request):
        entered.set()
        assert release.wait(3)
        return finish(request)

    flow.callbacks["prism_edit_finish"] = blocked
    thread = Thread(target=lambda: results.append(request(flow, task, "finish-prism-edit")))
    thread.start()
    try:
        assert entered.wait(3)
        saved = flow.snapshot(task["id"])["active_task"]
        assert saved["prism_edit"]["status"] == "finishing"
        assert saved["resume_id"] == task["resume_id"]
        with pytest.raises(PortalDataError) as error:
            flow.start(saved["id"], saved["revision"], "resume", retry=True)
        assert error.value.code == "prism_edit_active"
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive()
    assert results[0]["prism_edit"]["status"] == "complete"


def test_first_fixed_pdf_stage_uses_readback_and_retains_existing_final_until_success(local_flow):
    flow, task, calls = local_flow
    flow.callbacks["export"] = lambda task: flow.callbacks["prism_result_capture"](
        task, task["stages"]["export"]["attempt_id"]
    )
    flow.start(task["id"], task["revision"], "export", retry=True)
    final = wait_for(flow, task["id"], lambda row: row["status"] in {"materials_ready", "failed"})
    assert final["status"] == "materials_ready"
    assert calls == ["capture"]
    assert final["final_pdf_history"][0]["resume_id"] == task["resume_id"]


def configure_existing_result(store):
    import hashlib
    from pathlib import Path
    from types import SimpleNamespace
    from uuid import uuid4

    from career_evidence_graph.application_prism import dependency_snapshot

    calls = []

    class ExistingResult:
        def open(self, binding):
            calls.append("open")
            return "http://127.0.0.1:8799/"

        def compile(self, binding):
            pytest.fail("P06 must read the existing automatic result")

        def read_compiled(self, binding):
            calls.append("read")
            current = dependency_snapshot(
                Path(binding["project_root"]), binding["main"], binding["files"]
            )
            raw = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
            return {
                "binding": current,
                "pdf": raw,
                "build": {
                    "schema_version": "prism-build-result/v1",
                    "status": "complete",
                    "id": uuid4().hex,
                    "main": current["main"],
                    "files": current["files"],
                    "exit": 0,
                    "pdf_updated": True,
                    "cancelled": False,
                    "timed_out": False,
                    "diagnostics": [],
                    "pdf_sha256": hashlib.sha256(raw).hexdigest(),
                },
            }

    def proofreader(*args, **kwargs):
        calls.append("proofread")
        return SimpleNamespace(structured_result={"patches": [], "notices": []})

    store.prism_client = ExistingResult()
    store.model_runner = proofreader
    return calls


def test_portal_prism_return_adopts_actual_manual_store_version_and_existing_result(
    complete_portal, monkeypatch
):
    from pathlib import Path

    server, store, original, _ = complete_portal
    flow = server.application_flow_service
    old_draft = store.draft(original["draft_id"])
    old_pdf = store.pdf(original["resume_id"])
    calls = configure_existing_result(store)
    opened = request(flow, original, "begin-prism-edit")
    source = Path(opened["prism_edit"]["project_root"]) / opened["prism_edit"]["main"]
    changed = source.read_text().replace(
        r"\begin{document}", r"\setlength{\parindent}{7pt}" + "\n" + r"\begin{document}"
    )
    changed += "\n% User-only layout and fact intent remains local.\n"
    source.write_text(changed)
    monkeypatch.setattr(store, "_task_current", lambda *a, **k: pytest.fail("No live sources"))
    returned = request(flow, opened, "finish-prism-edit")
    assert returned["prism_edit"]["status"] == "complete"
    assert store.draft(returned["draft_id"])["latex_source"] == changed
    assert returned["resume_id"] == original["resume_id"]
    assert flow.callbacks["verify_materials"](returned) is None
    final = request(flow, returned, "capture-prism-result")
    assert final["status"] == "materials_ready"
    assert store.read_export(final["resume_id"])["latex_source"] == changed
    assert store.pdf(original["resume_id"]) == old_pdf
    assert store.draft(original["draft_id"]) == old_draft
    assert calls == ["open", "proofread", "read"]


@pytest.mark.worker_browser
def test_pdf_ui_requires_explicit_prism_return_and_keeps_saved_final_visible(
    complete_portal, browser_page
):
    from playwright.sync_api import expect
    from test_automatic_material_editor_browser import serving

    server, store, original, _ = complete_portal
    calls = configure_existing_result(store)
    writes = []
    browser_page.on(
        "request",
        lambda request: (
            writes.append(request.url.rsplit("/", 1)[-1])
            if request.method == "POST" and "/api/flow/" in request.url
            else None
        ),
    )
    with serving(server) as origin:
        # Chromium's built-in PDF viewer loads its own internal resources.
        # Keep the fixture's HTTP network boundary; these do not leave the browser.
        import re

        browser_page.route(
            re.compile(r"^(?:chrome-extension|chrome)://"), lambda route: route.continue_()
        )
        browser_page.goto(origin + "/#flow")
        browser_page.get_by_role("button", name="在 Prism 中编辑", exact=True).click()
        finish = browser_page.get_by_role("button", name="完成编辑，返回校对", exact=True)
        expect(finish).to_be_enabled()
        expect(browser_page.get_by_role("button", name="编辑当前简历", exact=True)).to_have_count(0)
        expect(browser_page.locator("#flow-pdf-link")).to_have_attribute(
            "href", f"/api/flow/resumes/{original['resume_id']}/pdf"
        )
        browser_page.locator("#flow-observe").click()
        expect(finish).to_be_enabled()
        assert calls == ["open"]
        assert writes == ["begin-prism-edit"]
        finish.click()
        expect(
            browser_page.get_by_role("button", name="编译并接回 PDF", exact=True)
        ).to_be_enabled()
        expect(browser_page.locator("#flow-final-pdf")).to_contain_text("有未导出的修改")
        assert calls == ["open", "proofread"]
        browser_page.get_by_role("button", name="编译并接回 PDF", exact=True).click()
        expect(browser_page.locator("#flow-pdf-link")).not_to_have_attribute(
            "href", f"/api/flow/resumes/{original['resume_id']}/pdf"
        )
        assert calls == ["open", "proofread", "read"]
        assert writes == ["begin-prism-edit", "finish-prism-edit", "capture-prism-result"]


def test_cancelled_task_cannot_be_revived_by_a_late_existing_pdf_result(local_flow):
    flow, task, _ = local_flow
    capture = flow.callbacks["prism_result_capture"]
    entered, release = Event(), Event()
    errors = []

    def blocked(request, export_id):
        entered.set()
        assert release.wait(3)
        return capture(request, export_id)

    def read():
        try:
            request(flow, task, "capture-prism-result")
        except PortalDataError as error:
            errors.append(error)

    flow.callbacks["prism_result_capture"] = blocked
    thread = Thread(target=read)
    thread.start()
    try:
        assert entered.wait(3)
        current = flow.snapshot(task["id"])["active_task"]
        cancelled = flow.cancel(current["id"], current["revision"])
        assert cancelled["status"] == "cancelled"
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive()
    assert errors[0].code == "prism_result_changed"
    final = flow.snapshot(task["id"])["active_task"]
    assert final["status"] == "cancelled"
    assert final["resume_id"] == task["resume_id"]
    assert final["artifacts"][-1]["adopted"] is False
    assert final["artifacts"][-1]["result"]["pdf_sha256"] == "f" * 64


def test_failed_prism_open_keeps_source_locked_until_explicit_reconnection(local_flow):
    flow, original, calls = local_flow
    begin = flow.callbacks["prism_edit_begin"]

    def unavailable(_):
        raise PortalDataError("prism_unavailable", "Synthetic editor unavailable", 503)

    flow.callbacks["prism_edit_begin"] = unavailable
    with pytest.raises(PortalDataError, match="unavailable"):
        request(flow, original, "begin-prism-edit")
    task = flow.snapshot(original["id"])["active_task"]
    assert task["prism_edit"]["status"] == "open_failed"
    assert task["resume_id"] == original["resume_id"]
    for write in (
        lambda: flow.start(task["id"], task["revision"], "resume", retry=True),
        lambda: flow.save_automatic_source(task["id"], task["revision"], "old", "new text"),
    ):
        with pytest.raises(PortalDataError) as error:
            write()
        assert error.value.code == "prism_edit_active"
    flow.callbacks["prism_edit_begin"] = begin
    reopened = request(flow, task, "begin-prism-edit")
    assert reopened["prism_edit"]["status"] == "editing"
    assert calls == ["begin"]


def test_input_reset_retires_old_local_contract_before_another_writing_round(local_flow):
    flow, task, _ = local_flow
    task = request(flow, task, "begin-prism-edit")
    task = request(flow, task, "finish-prism-edit")
    old_session = deepcopy(task["prism_edit"])
    app = flow.applications.get_application(task["application_id"])
    updated = flow.update_inputs(
        task["id"], task["revision"], app["revision"], {"sources_revision": "new-round"}
    )
    assert updated["draft_id"] is None
    assert not local_materials(updated)
    assert "prism_edit" not in updated
    assert "material_version_contract" not in updated
    assert updated["material_version_history"][-1]["prism_edit"] == old_session


def test_explicit_regeneration_does_not_inherit_old_local_readback_exemption(local_flow):
    flow, task, _ = local_flow
    task = request(flow, task, "begin-prism-edit")
    task = request(flow, task, "finish-prism-edit")
    task = flow.snapshot(task["id"])["active_task"]
    flow.callbacks["resume"] = lambda task: (
        candidate(task)
        | {
            "id": "fresh-raw-draft",
            "application_id": task["application_id"],
        }
    )
    flow.start(task["id"], task["revision"], "resume", retry=True)
    updated = wait_for(flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
    assert updated["status"] == "draft_ready"
    assert updated["draft_id"] == "fresh-raw-draft"
    assert not local_materials(updated)
    assert "prism_edit" not in updated
    assert "material_version_contract" not in updated
    assert updated["material_version_history"][-1]["draft_id"] == "manual-version"


def test_cancel_during_prism_edit_never_calls_return_proofreader(local_flow):
    flow, task, calls = local_flow
    opened = request(flow, task, "begin-prism-edit")
    cancelled = flow.cancel(opened["id"], opened["revision"])
    assert cancelled["status"] == "cancelled"
    with pytest.raises(PortalDataError) as error:
        request(flow, cancelled, "finish-prism-edit")
    assert error.value.code == "flow_cancelled"
    assert calls == ["begin"]
    assert flow.snapshot(task["id"])["active_task"]["resume_id"] == task["resume_id"]


def test_cancel_during_finishing_waits_for_existing_proofreader_to_settle(local_flow):
    flow, task, calls = local_flow
    task = request(flow, task, "begin-prism-edit")
    entered, release = Event(), Event()
    finish = flow.callbacks["prism_edit_finish"]
    results = []

    def blocked(request):
        entered.set()
        assert release.wait(3)
        return finish(request)

    flow.callbacks["prism_edit_finish"] = blocked
    thread = Thread(target=lambda: results.append(request(flow, task, "finish-prism-edit")))
    thread.start()
    try:
        assert entered.wait(3)
        saved = flow.snapshot(task["id"])["active_task"]
        with pytest.raises(PortalDataError) as error:
            flow.cancel(saved["id"], saved["revision"])
        assert error.value.code == "prism_edit_active"
        assert flow.snapshot(task["id"])["active_task"]["prism_edit"]["status"] == "finishing"
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive()
    assert results[0]["prism_edit"]["status"] == "complete"
    assert calls == ["begin", "finish"]


def test_existing_automatic_final_stays_readable_after_unrelated_live_changes(
    complete_portal, monkeypatch
):
    from pathlib import Path

    server, store, task, _ = complete_portal
    flow = server.application_flow_service
    assert "generation_contract" not in store.draft(task["draft_id"])
    assert "material_version_contract" not in task
    assert not task.get("prism_edit")
    assert local_materials(task)
    original_pdf = store.pdf(task["resume_id"])
    main = Path(task["source_checkpoint"]["project_root"]) / "main.tex"
    main.write_text(main.read_text() + "\n% Later manual modification\n")
    application = flow.applications.get_application(task["application_id"])
    flow.applications.update_application(
        application["id"], {"job_description": "A later different JD"}, application["revision"]
    )
    monkeypatch.setattr(store, "configuration", lambda: pytest.fail("No current model config gate"))
    monkeypatch.setattr(store, "_task_current", lambda *a, **k: pytest.fail("No live source gate"))
    flow.input_provider = lambda *a: pytest.fail("No live input scan for existing final")
    flow.callbacks["prism_export_configuration"] = lambda: pytest.fail("No current export config")
    assert flow.callbacks["verify_materials"](task) is None
    assert store.pdf(task["resume_id"]) == original_pdf
    assert flow._fresh(task)["id"] == application["id"]


@pytest.mark.parametrize(
    "mutation", ["no_draft", "draft_sha", "not_adopted", "no_pdf", "preparation"]
)
def test_unverified_legacy_materials_do_not_gain_local_version_exemption(complete_portal, mutation):
    _, _, original, _ = complete_portal
    task = deepcopy(original)
    if mutation == "no_draft":
        task["draft_id"] = None
    elif mutation == "draft_sha":
        task["draft_sha256"] = "f" * 64
    elif mutation == "not_adopted":
        for row in task["artifacts"]:
            if row["stage"] == "export":
                row["adopted"] = False
    elif mutation == "no_pdf":
        task["resume_id"] = None
        task["resume_sha256"] = None
    else:
        task["automatic_materials"] = False
    assert not local_materials(task)


@pytest.mark.worker_browser
def test_legacy_raw_advanced_editor_keeps_its_original_route_separate_from_prism_return(
    complete_portal, browser_page
):
    import re

    from playwright.sync_api import expect
    from test_automatic_material_editor_browser import serving

    server, store, original, _ = complete_portal
    old_draft = store.draft(original["draft_id"])
    writes = []
    browser_page.route(
        re.compile(r"^(?:chrome-extension|chrome)://"), lambda route: route.continue_()
    )
    browser_page.on(
        "request",
        lambda request: (
            writes.append(request.url.rsplit("/", 1)[-1])
            if request.method == "POST" and "/api/flow/" in request.url
            else None
        ),
    )
    with serving(server) as origin:
        browser_page.goto(origin + "/#flow")
        browser_page.get_by_text("设置与历史", exact=True).click()
        browser_page.get_by_text("系统处理详情与手动编辑", exact=True).click()
        browser_page.get_by_role("button", name="编辑当前简历", exact=True).click()
        source = browser_page.get_by_label("完整简历 LaTeX 源文", exact=True)
        expect(source).to_be_editable()
        changed = source.input_value().replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        )
        assert changed != source.input_value()
        source.fill(changed)
        browser_page.get_by_role("button", name="保存简历修改", exact=True).click()
        expect(browser_page.locator("#flow-notice")).to_contain_text("简历修改已保存")
        task = server.application_flow_service.snapshot(original["id"])["active_task"]
        draft = store.draft(task["draft_id"])
        assert draft["latex_source"] == changed
        assert "material_version_contract" not in draft
        assert not task.get("prism_edit")
        assert store.draft(original["draft_id"]) == old_draft
        assert len(store.prism_client.calls) == 1
        assert writes == ["begin-automatic-edit", "save-automatic-source"]


@pytest.mark.parametrize("complete_portal", [{"preparation_only": True}], indirect=True)
def test_legacy_pdf_validity_and_scoped_qualification_reads_remain_independent(complete_portal):
    from test_application_information import answer, library_with
    from test_job_explanations import requirement

    server, store, original, generation_calls = complete_portal
    flow = server.application_flow_service
    with flow.applications.write_lock():
        state = flow._load()
        task = flow._task(state, original["id"])
        analysis = next(
            row["result"]
            for row in task["artifacts"]
            if row["stage"] == "analysis" and row["adopted"]
        )
        analysis["requirements"] = [
            requirement("Be fluent in English.", judgment="unknown", hard=True)
        ]
        flow._save(state)
        task = deepcopy(task)
    library = library_with(
        answer("English fluency", "yes", scope={"application_id": task["application_id"]})
    )
    reads = []
    flow.information_provider = lambda: reads.append(True) or deepcopy(library)
    state_before = flow.witness()[0]
    pdf_before = store.pdf(task["resume_id"])
    first = flow.snapshot(task["id"])["active_explanation"]
    assert first["qualification"]["status"] == "supported"
    assert local_materials(task)
    assert flow.callbacks["verify_materials"](task) is None
    library["records"].clear()
    second = flow.snapshot(task["id"])["active_explanation"]
    assert second["qualification"]["status"] == "needs_input"
    assert reads == [True, True]
    assert flow.callbacks["verify_materials"](task) is None
    assert store.pdf(task["resume_id"]) == pdf_before
    assert flow.witness()[0] == state_before
    assert len(generation_calls) == len(store.prism_client.calls) == 1


@pytest.mark.parametrize("empty_current_jd", [False, True])
def test_manual_successor_of_fixed_delivery_does_not_read_live_libraries(
    material, fixed, tmp_path, empty_current_jd
):
    store, parent, model_calls = material
    analysis = fixed[0][3]
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    manual = store.finish_prism_edit(session["id"])
    job = store.applications.get_application(parent["application_id"])
    flow = ApplicationFlowService(
        store.applications,
        tmp_path / "fixed-manual-flow",
        preparation_only=True,
        input_provider=lambda *a: pytest.fail("Fixed explanations cannot inspect live inputs"),
        information_provider=lambda: pytest.fail("Fixed explanations cannot read live libraries"),
    )
    try:
        task = flow._new_task(job, manual["task_inputs"])
        task.update(
            automatic_materials=True,
            origin="generated_latex",
            draft_id=manual["id"],
            draft_sha256=manual["draft_sha256"],
            source_checkpoint=manual["source_checkpoint"],
            analysis_id=analysis["id"],
            status="draft_ready",
            stages={
                "analysis": {"status": "complete", "artifact_id": analysis["id"]},
                "resume": {"status": "complete", "artifact_id": manual["id"]},
                "export": {"status": "pending"},
            },
            artifacts=[
                {"stage": "analysis", "adopted": True, "result": analysis},
                {"stage": "resume", "adopted": True, "result": manual},
            ],
        )
        with flow.applications.write_lock():
            state = flow._load()
            state["tasks"].append(task)
            flow._save(state)
        if empty_current_jd:
            flow.applications.update_application(
                job["id"], {"job_description": ""}, job["revision"]
            )
        before = flow.witness()[0]
        current = flow.snapshot(task["id"])
        assert current["active_explanation"]["fresh"]
        assert current["active_task"]["draft_id"] == manual["id"]
        assert flow.witness()[0] == before
        assert len(model_calls) == 1
    finally:
        flow.close()
