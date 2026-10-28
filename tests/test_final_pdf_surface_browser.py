"""The default PDF surface reads real retained LaTeX archives without repeating work."""

import json
import sys
from types import SimpleNamespace

import pytest
from test_application_resume import task_resume as task_resume
from test_automatic_material_editor_browser import serving
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_full_latex_generation import full_latex as full_latex
from test_job_explanation_browser import open_internal_management
from test_portal_workflow_browser import browser_page as browser_page

pytestmark = pytest.mark.worker_browser


@pytest.fixture(autouse=True)
def isolated_model_context(tmp_path, monkeypatch):
    codex_home = tmp_path / "synthetic-codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", sys.executable)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def read_only_browser(page):
    writes = []
    page.on(
        "request",
        lambda request: (
            writes.append(request.url) if request.method not in {"GET", "HEAD", "OPTIONS"} else None
        ),
    )
    return writes


@pytest.mark.parametrize("complete_portal", [{"preparation_only": True}], indirect=True)
@pytest.mark.parametrize(
    "variant", ["normal", "uploaded", "application_prism", "stale", "existing_latex_pending"]
)
def test_saved_pdf_is_primary_on_open_and_reload_without_material_calls(
    complete_portal, browser_page, variant
):
    from playwright.sync_api import expect

    page = browser_page
    page.set_viewport_size({"width": 1280, "height": 900})
    server, store, task, generations = complete_portal
    with serving(server) as origin:
        instance = SimpleNamespace(server=server, origin=origin)
        work = {"calls": generations, "exports": store.prism_client.calls}
        before = instance.server.application_flow_service.snapshot()["active_task"]
        calls = len(work["calls"])
        if variant != "normal":
            # This consumer contract fixture changes only the browser's read response.
            # Real handoff integrity and reopening are covered by existing-handoff tests.
            def reported_upload(route):
                response = route.fetch()
                state = response.json()
                if variant in {"stale", "existing_latex_pending"}:
                    if variant == "stale":
                        state["active_explanation"]["materials_fresh"] = False
                    else:
                        state["active_task"]["origin"] = "existing_latex"
                    route.fulfill(response=response, body=json.dumps(state))
                    return
                if variant == "application_prism":
                    state["mode"] = "application"
                    state["active_task"]["prism"] = {"source_revision": "synthetic"}
                    state.pop("prism", None)
                    route.fulfill(response=response, body=json.dumps(state))
                    return
                state["active_task"]["codex_handoff_ref"] = {
                    "kind": "executor_report",
                    "status": "ready_for_review",
                    "filename": "Synthetic_Final_CV.pdf",
                    "job_url": "https://example.invalid/jobs/synthetic",
                }
                state["active_task"]["status"] = "ready_for_review"
                route.fulfill(response=response, body=json.dumps(state))

            page.route("**/api/flow/state", reported_upload)
        writes = read_only_browser(page)
        page.goto(instance.origin + "/#flow")
        for iteration in range(2):
            surface = page.locator("#flow-final-pdf")
            expect(surface).to_be_visible()
            expect(page.locator("#flow-pdf-link")).to_be_visible()
            expect(page.locator("#flow-pdf-link")).to_have_attribute(
                "href", f"/api/flow/resumes/{task['resume_id']}/pdf"
            )
            expect(page.locator("#flow-final-pdf-preview")).to_be_visible()
            expect(page.locator("#flow-final-pdf-preview")).to_have_attribute(
                "src", f"/api/flow/resumes/{task['resume_id']}/pdf"
            )
            if variant == "existing_latex_pending":
                expect(surface.get_by_role("heading")).to_have_text("已保存简历 PDF")
                expect(surface.locator(".flow-error").first).to_be_visible()
                expect(page.locator("#flow-pdf-link")).to_contain_text("打开已保存 PDF")
            details = page.locator("#flow-system-details")
            if variant == "uploaded":
                expect(details).to_have_count(0)
            else:
                expect(details).not_to_have_attribute("open", "")
            for selector in ("#flow-draft", "#flow-latex-base", "#flow-export-pdf"):
                expect(page.locator(selector)).not_to_be_visible()
            if variant == "uploaded":
                expect(page.locator("#flow-existing-handoff")).to_contain_text("最终 Submit")
            if not iteration:
                if variant == "normal":
                    page.wait_for_load_state("networkidle")
                    page.screenshot(path="/private/tmp/final-pdf-synthetic.png")
                page.reload()
        assert not writes
        assert len(work["calls"]) == calls and len(work["exports"]) == 1
        assert instance.server.application_flow_service.snapshot()["active_task"] == before


@pytest.mark.parametrize(
    "complete_portal", [{"preparation_only": True, "stop_before_export": True}], indirect=True
)
def test_no_pdf_shows_honest_status_and_keeps_existing_controls_collapsed(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    server, store, _task, generations = complete_portal
    with serving(server) as origin:
        instance = SimpleNamespace(server=server, origin=origin)
        work = {"calls": generations, "exports": store.prism_client.calls}
        calls = len(work["calls"])
        writes = read_only_browser(page)
        page.goto(instance.origin + "/#flow")
        surface = page.locator("#flow-final-pdf")
        expect(surface).to_contain_text("最终 PDF 尚未生成")
        expect(page.locator("#flow-final-pdf-preview")).to_have_count(0)
        expect(page.locator("#flow-pdf-link")).to_have_count(0)
        expect(page.locator("#flow-system-details")).not_to_have_attribute("open", "")
        expect(page.locator("#flow-draft")).not_to_be_visible()
        open_internal_management(page)
        page.locator("#flow-system-details > summary").click()
        expect(page.locator("#flow-draft")).to_be_visible()
        expect(page.locator("#flow-start-resume")).to_be_visible()
        page.reload()
        expect(page.locator("#flow-system-details")).not_to_have_attribute("open", "")
        assert len(work["calls"]) == calls and not work["exports"] and not writes


@pytest.mark.parametrize("complete_portal", [{"preparation_only": True}], indirect=True)
def test_invalid_pdf_remains_an_explicit_warning_without_final_preview(
    complete_portal, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    server, store, task, generations = complete_portal
    with serving(server) as origin:
        instance = SimpleNamespace(server=server, origin=origin)
        work = {"calls": generations, "exports": store.prism_client.calls}
        pdf = store.root / task["resume_id"] / "resume.pdf"
        assert pdf.is_file()
        pdf.write_bytes(b"Corrupted synthetic saved file")
        calls = len(work["calls"])
        writes = read_only_browser(page)
        page.goto(instance.origin + "/#flow")
        expect(page.locator("#flow-final-pdf .flow-error").first).to_be_visible()
        expect(page.locator("#flow-final-pdf-preview")).to_have_count(0)
        expect(page.locator("#flow-system-details")).not_to_have_attribute("open", "")
        page.reload()
        expect(page.locator("#flow-final-pdf .flow-error").first).to_be_visible()
        assert len(work["calls"]) == calls and len(work["exports"]) == 1 and not writes
