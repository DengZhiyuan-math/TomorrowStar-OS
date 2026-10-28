"""Actual mail intake, current JSON delivery and Runner share supplemental facts."""

import json
import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_intake import message
from test_application_intake import page as captured_page
from test_canonical_career_sources import canonical as canonical
from test_cover_letter_content import Compiler
from test_cover_letter_delivery import TEMPLATE
from test_j08_flow_combination import finish_json_writing
from test_j08_flow_combination import json_flow as json_flow
from test_j08_material_binding import json_material as json_material
from test_j08_material_binding import recorded_pipeline_clock as recorded_pipeline_clock
from test_resume_export import PDF_SAMPLE
from worker_preview_support import advance_until

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner


@pytest.mark.worker_browser
@pytest.mark.parametrize("certificate", [False, True])
def test_mail_to_canonical_flow_to_real_material_runner(json_material, monkeypatch, certificate):
    from playwright.sync_api import sync_playwright

    from career_evidence_graph import application_materials, application_prism

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    case = json_material
    server, flow = case.server, case.flow
    worker, pipeline = server.worker_service, server.application_pipeline_service
    template = case.project.parent / "cover-letter-template.tex"
    template.write_text(TEMPLATE)
    monkeypatch.setenv("TOMORROWSTAR_COVER_LETTER_TEMPLATE", str(template))
    compiler = Compiler()
    worker.store.cover_letter_client = compiler
    monkeypatch.setattr(
        application_prism,
        "PrismClient",
        lambda *args, **kwargs: pytest.fail("Only the recorded compiler may build this letter"),
    )
    case.job = case.applications.update_application(
        case.job["id"], {"location": "Zurich, Switzerland"}, case.job["revision"]
    )
    url = case.job["url"]
    pipeline.intake.reader = lambda *_a, **_k: {
        "status": "readable",
        "emails": [message(links=["https://www.linkedin.com/jobs/view/424242"])],
        "provenance": {},
    }
    pipeline.intake.fetcher = lambda target: (
        captured_page(target)
        | {
            "final_url": url,
            "redirects": [{"url": target, "status": 302, "location": url}],
            "body_text": case.job["job_description"],
            "job_fields": {
                "title": case.job["role_title"],
                "company": case.job["company"],
                "location": "Zurich, Switzerland",
            },
        }
    )
    flow.callbacks["automatic_latex_base"] = lambda _: source_snapshot(case.project, "main.tex")
    calls = []
    letter_calls = []
    canonical_model = case.store.model_runner

    def flow_model(config, prompt, **kwargs):
        if "cover-letters" in config.workspace.parts:
            letter_calls.append(config.output_schema.name)
            calls.append(config.output_schema.name)
        return canonical_model(config, prompt, **kwargs)

    case.store.model_runner = flow_model

    def material_model(config, prompt, **kwargs):
        calls.append(config.output_schema.name)
        data = json.loads(prompt[prompt.index("{") :])
        if config.output_schema.name == "validation-schema.json":
            output = {"supported": True, "reason": "Exact fact from adopted P04 source archive"}
        else:
            source = next(item for item in data["sources"] if item.get("record_context"))
            context = source["record_context"]
            assert context["status"] == "planned" and context["responsibility"] == "team"
            output = {
                "language": "en",
                "paragraphs": [
                    {
                        "kind": "fact",
                        "text": "Planned team activity: " + source["text"],
                        "source_ids": [source["source_id"]],
                        "source_quotes": [source["text"]],
                    }
                ],
            }
        return SimpleNamespace(
            structured_result=output, model_dump=lambda **kw: {"synthetic": True}
        )

    monkeypatch.setattr(application_materials, "run_codex_exec", material_model)
    pipeline.start(request_id="synthetic-complete-materials")
    deadline = time.monotonic() + 15
    while True:
        pipeline._tick()
        task = flow.snapshot().get("active_task")
        if task and task.get("experience_handoff"):
            break
        assert time.monotonic() < deadline, pipeline.snapshot()
        time.sleep(0.01)
    assert task["material_contract"] == "content-writing/v1"
    task, _ = finish_json_writing(case, task)
    while True:
        pipeline._tick()
        if (
            worker.store.load()["jobs"]
            and pipeline.snapshot()["status"] == "filling"
            and worker.store.load()["control"] == "running"
        ):
            break
        assert time.monotonic() < deadline, pipeline.snapshot()
        time.sleep(0.01)
    state = worker.store.load()
    current = state["jobs"][0]
    assert current["workflow"] == "single"
    worker.store.check_single(current, state)
    fixed_inputs = worker.store.material_inputs(current)
    letter = deepcopy(fixed_inputs["cover_letter"])
    assert letter["status"] == "ready"
    assert letter_calls == ["schema.json", "review-schema.json"]
    assert len(calls) == 2 and compiler.calls == 0
    archive = (
        worker.store.single_flow_root
        / "analyses"
        / current["single_binding"]["analysis_id"]
        / "source-snapshot.json"
    )
    assert fixed_inputs["sources"] == json.loads(archive.read_text())
    html = (
        f"<title>{current['company']} - {current['role_title']}</title>"
        f"<h1>{current['role_title']}</h1>"
        '<form id="application-form"><label>Resume *<input id="resume" type="file" requ'
        'ired></label><label>Cover letter *<input id="cover" type="file'
        '" required></label><label>Why this company? *<textarea id="why'
        '" required></textarea></label><button type="submit">Submit</bu'
        "tton></form>"
    )
    if certificate:
        html = html.replace(
            '<button type="submit">',
            (
                '<label>Certificate *<input id="certificate" type="file" requir'
                'ed></label><button type="submit">'
            ),
        )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            start_run(worker.store)
            engine = ApplicationRunner(worker.store, context)
            posts = []

            def intercept(route):
                def fetch(**options):
                    if route.request.method != "GET":
                        posts.append(route.request.url)
                    return SimpleNamespace(status=200, dispose=lambda: None)

                wrapper = SimpleNamespace(
                    request=route.request,
                    fetch=fetch,
                    fulfill=lambda *, response: route.fulfill(
                        status=200, body=html, content_type="text/html"
                    ),
                    abort=lambda reason: route.abort(reason),
                )
                engine._live_guard(wrapper)

            context.route("**/*", intercept)
            if certificate:
                waiting = advance_until(worker, engine, lambda row: row["status"] == "needs_input")
                assert (
                    waiting["status"] == "needs_input" and waiting["reason"] == "missing_materials"
                )
                controller = worker.store.load()["controller"]
                worker.request("pause", {"controller": controller})
                page = engine.pages[current["application_id"]]
                page.locator("#certificate").set_input_files(
                    {
                        "name": "provided-certificate.pdf",
                        "mimeType": "application/pdf",
                        "buffer": PDF_SAMPLE.read_bytes(),
                    }
                )
                worker.request(
                    "continue-current",
                    {
                        "application_id": current["application_id"],
                        "controller": controller,
                        "request_id": "continue-actual-certificate",
                    },
                )
                # Consume the explicit command before waiting on its saved outcome.
                engine.tick()
            current = advance_until(worker, engine, lambda row: row["status"] == "ready_for_review")
            pipeline._tick()
            assert current["status"] == "ready_for_review", json.dumps(current, ensure_ascii=False)
            assert len(current["materials"]) == (3 if certificate else 2) and len(calls) == 4
            assert letter_calls == ["schema.json", "review-schema.json"]
            assert compiler.calls == 1
            delivered_letter = next(
                row for row in current["materials"] if row["kind"] == "cover_letter"
            )
            assert delivered_letter["content_revision"] == letter["result"]["content_revision"]
            assert delivered_letter["letter_content"] == letter["result"]["content"]
            assert worker.store.material_inputs(current)["cover_letter"] == letter
            assert {row["kind"] for row in current["materials"]} == (
                {"cover_letter", "motivation_text", "certificate"}
                if certificate
                else {"cover_letter", "motivation_text"}
            )
            if certificate:
                retained = next(row for row in current["materials"] if row["kind"] == "certificate")
                assert retained["status"] == "manual" and retained["sha256"]
                assert retained["actor"] == "retained_page" and retained["attempt_id"]
                assert (
                    page.locator("#certificate").evaluate("e=>e.files[0].name")
                    == "provided-certificate.pdf"
                )
            assert all(
                row["source_binding"].get("sources")
                for row in current["materials"]
                if row["kind"] != "certificate"
            )
            worker.store.check_single(current, worker.store.load())
            assert posts == []
            assert pipeline.snapshot()["active_task_id"] == current["single_binding"]["task_id"]
        finally:
            browser.close()
