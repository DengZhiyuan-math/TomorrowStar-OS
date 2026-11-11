"""Default complete materials remain editable without per-document approval."""

import time
from contextlib import contextmanager
from threading import Thread

import pytest
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_bound_material_update_browser import choose_email_and_continue
from test_bound_material_update_browser import original_material_page as original_material_page
from test_full_latex_generation import full_latex as full_latex
from test_job_explanation_browser import reveal_control
from test_portal_workflow_browser import browser_page as browser_page

pytestmark = pytest.mark.worker_browser


@contextmanager
def serving(server):
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_default_material_editor_saves_full_source_and_retains_originals(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    server, store, original, generation = complete_portal
    old_draft = store.draft(original["draft_id"])
    old_pdf = store.pdf(original["resume_id"])
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
        browser_page.goto(origin + "/#flow")
        reveal_control(browser_page, "#flow-edit-automatic-source")
        edit = browser_page.get_by_role("button", name="编辑当前简历", exact=True)
        expect(edit).to_be_enabled(timeout=3000)
        edit.click()
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
        assert store.draft(task["draft_id"])["latex_source"] == changed
        assert task["manual_source"]["actor"] == "user"
        assert task["id"] == original["id"] and task["worker_ref"] is None
        assert store.draft(original["draft_id"]) == old_draft
        assert store.pdf(original["resume_id"]) == old_pdf
        assert len(generation) == len(store.prism_client.calls) == 1
        assert writes == ["begin-automatic-edit", "save-automatic-source"]
        expect(
            browser_page.get_by_role("button", name="确认此经历组的事实与责任归属")
        ).to_have_count(0)


def test_saved_source_with_lost_response_recovers_by_readback_without_replaying_save(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    server, store, original, _ = complete_portal
    saves = []

    def lose_response(route):
        saves.append(route.request.post_data_json)
        response = route.fetch()
        assert response.status == 200
        route.abort()

    browser_page.route("**/api/flow/save-automatic-source", lose_response)
    with serving(server) as origin:
        browser_page.goto(origin + "/#flow")
        reveal_control(browser_page, "#flow-edit-automatic-source")
        browser_page.get_by_role("button", name="编辑当前简历", exact=True).click()
        source = browser_page.get_by_label("完整简历 LaTeX 源文", exact=True)
        expect(source).to_be_editable()
        changed = source.input_value().replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        )
        source.fill(changed)
        browser_page.get_by_role("button", name="保存简历修改", exact=True).click()
        expect(browser_page.locator("#flow-notice")).to_contain_text("操作结果尚未核验")
        expect(source).to_have_value(changed)
        browser_page.locator("#flow-observe").click()
        expect(browser_page.get_by_role("button", name="保存简历修改", exact=True)).to_be_enabled()
        expect(source).to_have_value(changed)
        task = server.application_flow_service.snapshot(original["id"])["active_task"]
        assert store.draft(task["draft_id"])["latex_source"] == changed
        assert len(saves) == 1


def test_default_full_materials_expose_current_pdf_without_approval(complete_portal, browser_page):
    from playwright.sync_api import expect

    server, store, original, generation = complete_portal
    with serving(server) as origin:
        browser_page.goto(origin + "/#flow")
        link = browser_page.locator("#flow-pdf-link")
        expect(link).to_have_attribute(
            "href", f"/api/flow/resumes/{original['resume_id']}/pdf", timeout=3000
        )
        response = browser_page.request.get(origin + link.get_attribute("href"))
        assert response.status == 200 and response.body() == store.pdf(original["resume_id"])
        expect(
            browser_page.get_by_role("button", name="确认此经历组的事实与责任归属")
        ).to_have_count(0)
        assert len(generation) == len(store.prism_client.calls) == 1


@pytest.mark.parametrize("change", ["running", "unreadable"])
def test_pipeline_changes_stop_existing_source_editor_and_preserve_its_draft(
    complete_portal, browser_page, change
):
    from playwright.sync_api import expect

    server, _store, original, _generation = complete_portal
    state = {
        "enabled": True,
        "id": "synthetic-pipeline",
        "control": "paused",
        "status": "needs_input",
        "active_task_id": original["id"],
        "items": [],
    }
    readable = True

    def read_pipeline(route):
        if readable:
            route.fulfill(json=state)
        else:
            route.fulfill(status=503, json={"message": "Synthetic pipeline read unavailable"})

    browser_page.route("**/api/pipeline/state", read_pipeline)
    with serving(server) as origin:
        browser_page.goto(origin + "/#flow")
        reveal_control(browser_page, "#flow-edit-automatic-source")
        browser_page.get_by_role("button", name="编辑当前简历", exact=True).click()
        source = browser_page.get_by_label("完整简历 LaTeX 源文", exact=True)
        expect(source).to_be_editable()
        changed = source.input_value() + "\n% pending manual layout\n"
        source.fill(changed)
        if change == "running":
            state.update(control="running", status="generating_resume")
        else:
            readable = False
        browser_page.locator("#flow-observe").click()
        expect(source).to_be_disabled()
        expect(browser_page.get_by_role("button", name="保存简历修改", exact=True)).to_be_disabled()
        expect(source).to_have_value(changed)
        readable = True
        state.update(control="paused", status="needs_input")
        browser_page.locator("#flow-observe").click()
        expect(source).to_be_editable()
        expect(source).to_have_value(changed)


def test_source_conflict_preserves_local_edit_and_allows_explicit_current_version_rebase(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    server, store, original, _generation = complete_portal
    flow = server.application_flow_service
    with serving(server) as origin:
        browser_page.goto(origin + "/#flow")
        reveal_control(browser_page, "#flow-edit-automatic-source")
        browser_page.get_by_role("button", name="编辑当前简历", exact=True).click()
        source = browser_page.get_by_label("完整简历 LaTeX 源文", exact=True)
        expect(source).to_be_editable()
        initial = source.input_value()
        changed = initial.replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        )
        source.fill(changed)
        task = flow.snapshot(original["id"])["active_task"]
        other = flow.save_automatic_source(
            task["id"],
            task["revision"],
            task["prism"]["source_revision"],
            initial.replace(
                "Analyzed strategy; built 6 Python services.",
                "Built 6 Python services. Analyzed strategy.",
            ),
        )
        browser_page.locator("#flow-observe").click()
        expect(source).to_have_value(changed)
        expect(browser_page.get_by_role("button", name="保存简历修改", exact=True)).to_be_disabled()
        browser_page.get_by_role("button", name="保留编辑并采用当前源版本", exact=True).click()
        expect(source).to_have_value(changed)
        browser_page.get_by_role("button", name="保存简历修改", exact=True).click()
        expect(browser_page.locator("#flow-notice")).to_contain_text("简历修改已保存")
        current = flow.snapshot(original["id"])["active_task"]
        assert store.draft(current["draft_id"])["latex_source"] == changed
        assert (
            "Built 6 Python services. Analyzed strategy."
            in store.draft(other["draft_id"])["latex_source"]
        )


@pytest.mark.parametrize("phase", ["preparing", "needs_recheck"])
def test_reported_pending_material_update_is_readonly_even_when_pipeline_is_paused(
    complete_portal, browser_page, phase
):
    from playwright.sync_api import expect

    server, store, _original, _generation = complete_portal
    reported = False

    def flow_readback(route):
        response = route.fetch()
        body = response.json()
        if reported:
            task = body["active_task"]
            task["material_update"] = {
                "status": phase,
                "editable_draft": store.draft(task["draft_id"]),
            }
        route.fulfill(response=response, json=body)

    browser_page.route("**/api/flow/state", flow_readback)
    with serving(server) as origin:
        browser_page.goto(origin + "/#flow")
        reveal_control(browser_page, "#flow-edit-automatic-source")
        browser_page.get_by_role("button", name="编辑当前简历", exact=True).click()
        source = browser_page.get_by_label("完整简历 LaTeX 源文", exact=True)
        expect(source).to_be_editable()
        changed = source.input_value() + "\n% pending local draft\n"
        source.fill(changed)
        reported = True
        browser_page.locator("#flow-observe").click()
        expect(source).to_be_disabled()
        expect(source).to_have_value(changed)
        expect(browser_page.get_by_role("button", name="保存简历修改", exact=True)).to_be_disabled()


def test_saved_source_repaint_preserves_the_users_collapsed_editor(complete_portal, browser_page):
    from playwright.sync_api import expect

    server, _store, original, _generation = complete_portal
    flow = server.application_flow_service
    with serving(server) as origin:
        browser_page.goto(origin + "/#flow")
        reveal_control(browser_page, "#flow-edit-automatic-source")
        browser_page.get_by_role("button", name="编辑当前简历", exact=True).click()
        source = browser_page.get_by_label("完整简历 LaTeX 源文", exact=True)
        expect(source).to_be_editable()
        current = source.input_value()
        details = browser_page.locator("#flow-automatic-source-editor")
        details.locator("summary").click()
        expect(details).not_to_have_attribute("open", "")
        task = flow.snapshot(original["id"])["active_task"]
        flow.save_automatic_source(
            task["id"],
            task["revision"],
            task["prism"]["source_revision"],
            current.replace(
                "Analyzed strategy; built 6 Python services.",
                "Built 6 Python services; analyzed strategy.",
            ),
        )
        browser_page.locator("#flow-observe").click()
        expect(browser_page.locator("#flow-notice")).to_contain_text("已读取持久状态")
        expect(details).not_to_have_attribute("open", "")


@pytest.mark.parametrize("continue_after_save", [False, True])
def test_staged_original_page_source_edit_keeps_human_changes_and_continues_only_when_requested(
    original_material_page, continue_after_save
):
    from playwright.sync_api import expect

    from career_evidence_graph.application_information import put_information_answer

    server, store, calls, runner, ats_page, posts = original_material_page
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )

    def finish_current(*, email_difference=False):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            pipeline._tick()
            runner.tick()
            state = pipeline.snapshot()
            if state["status"] in {"ready_for_review", "needs_recheck", "needs_input"}:
                break
        if email_difference:
            state = choose_email_and_continue(
                server,
                runner,
                ats_page,
                current_value="job@example.invalid",
                proposed_value="updated@example.invalid",
                request_id="adopt-email-after-explicit-source-edit",
            )
        assert state["status"] == "ready_for_review", state

    original = flow.snapshot()["active_task"]
    old_pdf = store.pdf(original["resume_id"])
    old_draft = store.draft(original["draft_id"])
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    job = store.applications.get_application(original["application_id"])
    staged = flow.update_inputs(original["id"], original["revision"], job["revision"])
    assert staged["material_update"]["status"] == "staged"
    assert "editable_draft" not in staged["material_update"]
    context = ats_page.context.browser.new_context()
    external, errors, continues = [], [], []

    def local_only(route):
        from urllib.parse import urlsplit

        target = urlsplit(route.request.url)
        builtin_pdf = (
            target.scheme == "chrome-extension"
            and target.netloc == "mhjfbmdgcfjbbpaeojofohoefgiehjai"
        ) or (target.scheme == "chrome" and target.netloc == "resources")
        if target.hostname not in {"127.0.0.1", "localhost"} and not builtin_pdf:
            external.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    context.route("**/*", local_only)
    ui = context.new_page()
    ui.on("pageerror", lambda error: errors.append(str(error)))
    ui.on(
        "request",
        lambda request: (
            continues.append(request.post_data_json)
            if request.method == "POST" and request.url.endswith("/api/pipeline/continue")
            else None
        ),
    )
    try:
        with serving(server) as origin:
            ui.goto(origin + "/#flow")
            reveal_control(ui, "#flow-edit-automatic-source")
            ui.get_by_role("button", name="编辑当前简历", exact=True).click()
            source = ui.get_by_label("完整简历 LaTeX 源文", exact=True)
            expect(source).to_be_editable()
            changed = source.input_value().replace("job@example.invalid", "updated@example.invalid")
            changed = changed.replace(
                "Analyzed strategy; built 6 Python services.",
                "Built 6 Python services; analyzed strategy.",
            )
            source.fill(changed)
            expect(ui.locator("#flow-pipeline-start")).to_be_disabled()
            ui.get_by_role("button", name="保存简历修改", exact=True).click()
            expect(ui.locator("#flow-notice")).to_contain_text("简历修改已保存")
            candidate = flow.snapshot(original["id"])["active_task"]
            assert candidate["resume_id"] == original["resume_id"]
            assert candidate["worker_ref"] == original["worker_ref"]
            assert worker.store.load()["control"] == "paused"
            assert store.draft(original["draft_id"]) == old_draft
            assert candidate["material_update"]["editable_draft"]["latex_source"] == changed
            if not continue_after_save:
                assert store.pdf(original["resume_id"]) == old_pdf
                assert ats_page.locator("#notes").input_value() == "Retain this human text."
                assert (
                    ats_page.locator("#certificate").evaluate("e => e.files[0].name")
                    == "human-certificate.pdf"
                )
                assert continues == posts == external == errors == []
                assert len(calls) == len(store.prism_client.calls) == 1
                return
            ui.locator("#flow-pipeline-start").click()
            finish_current(email_difference=True)
            current = flow.snapshot(original["id"])["active_task"]
            assert current["worker_ref"]["batch_id"] == original["worker_ref"]["batch_id"]
            assert runner.pages[job["id"]] is ats_page
            assert store.read_export(current["resume_id"])["latex_source"] == changed
            assert store.pdf(original["resume_id"]) == old_pdf
            assert ats_page.locator("#notes").input_value() == "Retain this human text."
            assert (
                ats_page.locator("#certificate").evaluate("e => e.files[0].name")
                == "human-certificate.pdf"
            )
            assert len(continues) == len(calls) == 1
            assert posts == external == errors == []
            first_pdf = store.pdf(current["resume_id"])
            first_resume_id = current["resume_id"]
            pipeline.pause()
            ui.locator("#flow-observe").click()
            edit = ui.get_by_role("button", name="编辑当前简历", exact=True)
            expect(edit).to_be_enabled(timeout=3000)
            edit.click()
            source = ui.get_by_label("完整简历 LaTeX 源文", exact=True)
            expect(source).to_be_editable()
            second = source.input_value().replace(
                "Built 6 Python services; analyzed strategy.",
                "Built 6 Python services. Analyzed strategy.",
            )
            assert second != source.input_value()
            source.fill(second)
            ui.get_by_role("button", name="保存简历修改", exact=True).click()
            expect(ui.locator("#flow-notice")).to_contain_text("简历修改已保存")
            ui.locator("#flow-pipeline-start").click()
            finish_current()
            final = flow.snapshot(original["id"])["active_task"]
            assert store.read_export(final["resume_id"])["latex_source"] == second
            assert store.pdf(first_resume_id) == first_pdf
            assert store.pdf(original["resume_id"]) == old_pdf
            assert runner.pages[job["id"]] is ats_page
            assert len(continues) == 2 and len(calls) == 1
            assert posts == external == errors == []
    finally:
        context.close()
