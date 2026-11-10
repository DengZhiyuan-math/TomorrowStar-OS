"""Current text limits and undispatched PDF failures recover without rewriting bodies."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_worker import service as service
from test_cover_letter_content import Compiler
from test_cover_letter_delivery import field, stable_letter_observation
from test_cover_letter_delivery import modern as modern
from test_supplemental_material_module import materials
from test_supplemental_material_module import prepared as prepared

from career_evidence_graph import application_form_runner as form_runner
from career_evidence_graph import application_prism
from career_evidence_graph import application_worker_browser as browser_engine
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("key", ["max_length", "maxlength"])
def test_cached_text_obeys_current_limit_and_recovers_without_rewriting(
    modern, monkeypatch, required, key
):
    ready, fixed = modern
    worker, job, batch = ready
    assert materials(ready).prepare(job, batch, {"fields": [field(required=required)]})
    original = deepcopy(job["materials"][0])
    body = deepcopy(fixed["cover_letter"])
    changed = field(required=required, **{key: len(original["text"]) - 1})
    _, _, observed = stable_letter_observation(worker, job, batch, changed, monkeypatch)
    assert materials(ready).prepare(job, batch, observed) is (not required)
    current = worker.store.load()["jobs"][0]
    assert current["cover_letter_delivery"]["reason"] == "cover_letter_text_too_long"
    assert current["materials"] == [original] and fixed["cover_letter"] == body
    if required:
        with pytest.raises(PortalDataError) as caught:
            worker.store.resolve(changed, current)
        assert caught.value.code == "cover_letter_text_too_long"
    else:
        assert worker.store.resolve(changed, current) is None
    allowed = field(required=required, **{key: len(original["text"])})
    assert materials(ready).prepare(job, batch, {"fields": [allowed]})
    assert worker.store.resolve(allowed, worker.store.load()["jobs"][0])[0] == original["text"]
    assert job["materials"] == [original]


def test_shorter_human_page_text_is_retained_instead_of_old_cached_body(modern):
    ready, fixed = modern
    worker, job, batch = ready
    assert materials(ready).prepare(job, batch, {"fields": [field(required=True)]})
    original = deepcopy(job["materials"][0])
    current_field = field(required=True, value="Human wording.", max_length=20)
    assert materials(ready).prepare(job, batch, {"fields": [current_field]})
    assert worker.store.resolve(current_field, worker.store.load()["jobs"][0]) is None
    assert job["materials"] == [original]


@pytest.mark.worker_browser
@pytest.mark.parametrize("shrink_during_authorize", [False, True])
def test_process_does_not_write_a_cached_letter_into_a_shorter_textarea(
    modern, monkeypatch, shrink_during_authorize
):
    from playwright.sync_api import sync_playwright

    ready, fixed = modern
    worker, job, batch = ready
    monkeypatch.setattr(
        application_prism, "PrismClient", lambda *a, **kw: pytest.fail("No real Prism")
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_resume_versions.TectonicCompiler",
        lambda *a, **kw: pytest.fail("No real Prism"),
    )
    assert materials(ready).prepare(job, batch, {"fields": [field(required=True)]})
    original = deepcopy(job["materials"][0])
    changed = field(
        required=True,
        max_length=10_000 if shrink_during_authorize else 20,
        options=[],
        multiple=False,
    )
    monkeypatch.setattr(browser_engine, "require_execution", lambda *a, **kw: None)
    state = worker.store.load()
    run = "bounded-text-process"
    state["current_job_id"] = job["application_id"]
    state["runtime"] = {
        "id": run,
        "applications_root": state["applications_root"],
        "pid": 1,
        "started_at": 0.0,
        "observed_at": 0.0,
        "source": {"sha256": "a" * 64, "files": {"synthetic.py": "b" * 64}},
    }
    worker.store.save(state)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(
                '<label>Cover letter *<textarea data-ts-worker-field="letter-0" '
                'maxlength="20" aria-required="true"></textarea></label>'
            )
            runner = browser_engine.ApplicationRunner(worker.store, None)
            runner.live = True
            runner.pages[job["application_id"]] = page
            runner.page_ids[page] = "bounded-letter-page"
            if shrink_during_authorize:
                original_authorize = runner.authorize

                def authorize(*args, **kwargs):
                    allowed = original_authorize(*args, **kwargs)
                    page.locator("textarea").evaluate("e=>e.maxLength=20")
                    return allowed

                runner.authorize = authorize
            runner.check_inputs = lambda *a, **kw: None
            runner.finish_materials = lambda *a, **kw: False
            now = [0.0]
            monkeypatch.setattr(form_runner, "time", SimpleNamespace(time=lambda: now[0]))

            def observe(p, j):
                question = changed | {
                    "max_length": int(p.locator("textarea").get_attribute("maxlength")),
                    "value": p.locator("textarea").input_value(),
                    "valid": p.locator("textarea").evaluate("e=>e.validity.valid"),
                }
                return {
                    "fields": [question],
                    "stage": "documents",
                    "document_token": "same-document",
                    "parser": {"status": "complete"},
                    "validation_errors": [],
                }

            runner.observe = observe
            page.locator("textarea").evaluate(
                "(e, value)=>e.maxLength=value", changed["max_length"]
            )
            job = worker.store.load()["jobs"][0]
            for value in [0.0, 0.25, 0.5]:
                now[0] = value
                form_runner.capture(runner, page, job, batch, observe(page, job))
            assert job["form_state"]["parser"]["status"] == "stable"
            if shrink_during_authorize:
                with pytest.raises(PortalDataError) as changed_field:
                    runner.process(job, batch)
                assert changed_field.value.code == "question_changed"
            else:
                runner.process(job, batch)
            assert page.locator("textarea").input_value() == ""
            current = worker.store.load()["jobs"][0]
            if not shrink_during_authorize:
                assert current["cover_letter_delivery"]["reason"] == "cover_letter_text_too_long"
                assert not current.get("intent")
            assert current["materials"] == [original]
        finally:
            browser.close()


@pytest.mark.parametrize("retained", [False, True])
def test_html_text_limit_counts_non_bmp_characters_as_utf16_units(modern, retained):
    ready, fixed = modern
    worker, job, batch = ready
    template = worker.store.cover_letter_template
    template.write_text(template.read_text().replace("Dear Hiring Team", "Dear Hiring Team 💡"))
    if retained:
        assert materials(ready).prepare(job, batch, {"fields": [field(required=True)]})
        text = job["materials"][0]["text"]
        original = deepcopy(job["materials"][0])
    else:
        from career_evidence_graph.application_cover_letter import render_cover_letter
        from career_evidence_graph.application_materials import read_cover_letter_template

        text = render_cover_letter(
            fixed["cover_letter"]["result"]["content"],
            read_cover_letter_template(worker.store, fixed["application"]),
        )["text"]
    assert len(text.encode("utf-16-le")) // 2 > len(text)
    assert not materials(ready).prepare(
        job, batch, {"fields": [field(required=True, max_length=len(text))]}
    )
    assert (
        worker.store.load()["jobs"][0]["cover_letter_delivery"]["reason"]
        == "cover_letter_text_too_long"
    )
    if retained:
        assert job["materials"] == [original]


@pytest.mark.worker_browser
def test_one_public_continue_recovers_corrected_preflight_after_worker_tick(modern, monkeypatch):
    from playwright.sync_api import sync_playwright

    ready, fixed = modern
    worker, job, batch = ready
    client = Compiler()
    worker.store.cover_letter_client = client
    worker.store.check_single = lambda *a, **kw: True
    monkeypatch.setattr(
        application_prism, "PrismClient", lambda *a, **kw: pytest.fail("No real Prism")
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_resume_versions.TectonicCompiler",
        lambda *a, **kw: pytest.fail("No real Prism"),
    )
    monkeypatch.setattr(browser_engine, "require_execution", lambda *a, **kw: None)
    state = worker.store.load()
    state["current_job_id"] = job["application_id"]
    state["jobs"][0]["page_open"] = True
    state["runtime"] = {
        "id": "preflight-original-run",
        "applications_root": state["applications_root"],
        "pid": 1,
        "started_at": 0.0,
        "observed_at": 0.0,
        "source": {"sha256": "a" * 64, "files": {"synthetic.py": "b" * 64}},
    }
    worker.store.save(state)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    cap = [True]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content('<label>Cover letter *<input type="file" accept=".pdf"></label>')
            runner = browser_engine.ApplicationRunner(worker.store, context)
            runner.live = True
            runner.pages[job["application_id"]] = page
            runner.page_ids[page] = "preflight-original-page"
            runner.check_inputs = lambda *a, **kw: None
            runner.finish_materials = lambda *a, **kw: False
            runner.permitted = lambda *a, **kw: True
            runner.observe = lambda *a: {
                "fields": [
                    field(
                        kind="file", required=True, accept=".pdf", max_bytes=cap[0], multiple=False
                    )
                ],
                "stage": "documents",
                "document_token": "same-document",
                "parser": {"status": "complete"},
                "validation_errors": [],
            }
            runner._tick()
            first = worker.store.load()["jobs"][0]
            assert first["status"] == "needs_recheck" and first["intent"] is None
            failed = deepcopy(first["materials"][0])
            assert failed["status"] == "failed" and failed["file_build_started"] is False
            assert client.calls == 0
            cap[0] = 700_000
            worker.request(
                "continue-current",
                {
                    "application_id": job["application_id"],
                    "request_id": "continue-after-page-correction",
                    "controller": "synthetic-control",
                },
            )
            runner._tick()
            current = worker.store.load()["jobs"][0]
            assert current["materials"][0]["status"] == "ready"
            assert current["material_history"] == [failed]
            assert current["continuation"]["status"] == "verified"
            assert client.calls == 1
        finally:
            browser.close()


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("key", ["max_length", "maxlength"])
@pytest.mark.parametrize("cap", [0, -1, None, "exact_fit", "absent"])
def test_zero_and_unbounded_current_text_limits_have_distinct_meanings(modern, required, key, cap):
    ready, fixed = modern
    worker, job, batch = ready
    assert materials(ready).prepare(job, batch, {"fields": [field(required=required)]})
    original = deepcopy(job["materials"][0])
    question = field(required=required)
    if cap != "absent":
        question[key] = (
            len(original["text"].encode("utf-16-le")) // 2 if cap == "exact_fit" else cap
        )
    assert materials(ready).prepare(job, batch, {"fields": [question]}) is (
        not required or cap != 0
    )
    current = worker.store.load()["jobs"][0]
    assert current["materials"] == [original]
    if cap == 0:
        assert current["cover_letter_delivery"]["reason"] == "cover_letter_text_too_long"
        if required:
            with pytest.raises(PortalDataError) as rejected:
                worker.store.resolve(question, current)
            assert rejected.value.code == "cover_letter_text_too_long"
        else:
            assert worker.store.resolve(question, current) is None
    else:
        assert worker.store.resolve(question, current)[0] == original["text"]


@pytest.mark.worker_browser
@pytest.mark.parametrize("native_limit", ["zero", "short", "exact_fit", "absent", "negative"])
def test_production_observer_preserves_zero_text_cap_before_full_process(
    modern, monkeypatch, native_limit
):
    from playwright.sync_api import sync_playwright

    from career_evidence_graph import hosted_ats

    ready, fixed = modern
    worker, job, batch = ready
    monkeypatch.setattr(
        application_prism, "PrismClient", lambda *a, **kw: pytest.fail("No real Prism")
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_resume_versions.TectonicCompiler",
        lambda *a, **kw: pytest.fail("No real Prism"),
    )
    assert materials(ready).prepare(job, batch, {"fields": [field(required=True)]})
    original = deepcopy(job["materials"][0])
    exact_length = len(original["text"].encode("utf-16-le")) // 2
    cap = {"zero": 0, "short": 20, "exact_fit": exact_length, "absent": None, "negative": -1}[
        native_limit
    ]
    monkeypatch.setattr(browser_engine, "require_execution", lambda *a, **kw: None)
    state = worker.store.load()
    state["current_job_id"] = job["application_id"]
    state["runtime"] = {
        "id": "zero-bound-original-run",
        "applications_root": state["applications_root"],
        "pid": 1,
        "started_at": 0.0,
        "observed_at": 0.0,
        "source": {"sha256": "a" * 64, "files": {"synthetic.py": "b" * 64}},
    }
    worker.store.save(state)
    calls = []
    original_fill = hosted_ats.fill

    def fill(*args, **kwargs):
        calls.append(1)
        return original_fill(*args, **kwargs)

    monkeypatch.setattr(hosted_ats, "fill", fill)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            attribute = "" if cap is None else f' maxlength="{cap}"'
            page.set_content(
                '<label>Cover letter *<textarea data-ts-worker-field="letter-0"'
                + attribute
                + ' aria-required="true"></textarea></label>'
            )
            runner = browser_engine.ApplicationRunner(worker.store, None)
            runner.live = True
            runner.pages[job["application_id"]] = page
            runner.page_ids[page] = "zero-bound-original-page"
            runner.check_inputs = lambda *a, **kw: None
            runner.finish_materials = lambda *a, **kw: False
            now = [0.0]
            monkeypatch.setattr(form_runner, "time", SimpleNamespace(time=lambda: now[0]))

            def raw_observe(p, j):
                question = field(
                    required=True,
                    options=[],
                    multiple=False,
                    value=p.locator("textarea").input_value(),
                    valid=p.locator("textarea").evaluate("e=>e.validity.valid"),
                )
                return {
                    "fields": [question],
                    "stage": "documents",
                    "document_token": "same-document",
                    "parser": {"status": "complete"},
                    "validation_errors": [],
                }

            runner._observe = raw_observe
            job = worker.store.load()["jobs"][0]
            for instant in [0.0, 0.25, 0.5]:
                now[0] = instant
                form_runner.capture(runner, page, job, batch, runner.observe(page, job))
            assert job["form_state"]["parser"]["status"] == "stable"
            observed = runner.observe(page, job)
            expected = None if cap is None or cap < 0 else cap
            assert observed["fields"][0]["max_length"] == expected
            assert (
                form_runner.check_snapshot(runner, page, job, observed)["fields"][0]["max_length"]
                == expected
            )
            runner.process(job, batch)
            current = worker.store.load()["jobs"][0]
            if native_limit in {"zero", "short"}:
                assert page.locator("textarea").input_value() == ""
                assert calls == [] and not current.get("intent")
                assert current["cover_letter_delivery"]["reason"] == "cover_letter_text_too_long"
            else:
                assert page.locator("textarea").input_value() == original["text"]
                assert calls == [1]
            assert current["materials"] == [original]
        finally:
            browser.close()


@pytest.mark.parametrize("required", [False, True])
def test_corrected_page_limit_failure_is_recovered_by_the_next_prepare(
    modern, monkeypatch, required
):
    ready, fixed = modern
    worker, job, batch = ready
    client = Compiler()
    worker.store.cover_letter_client = client
    monkeypatch.setattr(
        application_prism, "PrismClient", lambda *a, **kw: pytest.fail("No real Prism")
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_resume_versions.TectonicCompiler",
        lambda *a, **kw: pytest.fail("No real Prism"),
    )
    wrong = field(kind="file", required=required, accept=".pdf", max_bytes=True)
    with pytest.raises(PortalDataError) as caught:
        materials(ready).prepare(job, batch, {"fields": [wrong]})
    assert caught.value.code == "cover_letter_file_limit_invalid"
    failed = deepcopy(worker.store.load()["jobs"][0]["materials"][0])
    assert failed["status"] == "failed"
    # Flow built the one PDF; the page limit is only checked against it.
    assert client.calls == 1
    correct = wrong | {"max_bytes": 700_000}
    assert materials(ready).prepare(job, batch, {"fields": [correct]})
    current = worker.store.load()["jobs"][0]
    assert (
        current["materials"][0]["status"] == "ready"
        and current["materials"][0]["id"] != failed["id"]
    )
    assert current["material_history"] == [failed]
    assert (
        current["materials"][0]["content_revision"]
        == fixed["cover_letter"]["result"]["content_revision"]
    )
    assert client.calls == 1


@pytest.mark.parametrize(
    "failure,code",
    [
        ("metadata_error", "cover_letter_file_limit_invalid"),
        ("timeout", "letter_export_needs_recheck"),
    ],
)
def test_flow_pdf_failure_waits_without_a_material_or_another_build(modern, failure, code):
    ready, _ = modern
    worker, job, batch = ready
    calls = []

    def exporter(*args):
        calls.append(1)
        if failure == "timeout":
            raise TimeoutError("Synthetic lost dispatched result")
        raise PortalDataError(
            "cover_letter_file_limit_invalid", "Synthetic error after dispatch", 409
        )

    worker.store.cover_letter_exporter = exporter
    question = field(kind="file", required=True, accept=".pdf", max_bytes=700_000)
    assert materials(ready).prepare(job, batch, {"fields": [question]}) is False
    assert materials(ready).prepare(job, batch, {"fields": [question]}) is False
    current = worker.store.load()["jobs"][0]
    assert current.get("materials", []) == [] and len(calls) == 1
    assert current["cover_letter_delivery"]["reason"] == code


def test_legacy_ambiguous_unknown_record_is_not_replayed_from_missing_intent(modern):
    """An unknown record without build metadata predates file builds; it stays unknown."""
    ready, fixed = modern
    worker, job, batch = ready
    state = worker.store.load()
    original = {
        "id": "legacy-unknown",
        "kind": "cover_letter",
        "field_id": "letter",
        "draft_path": "",
        "question": "Cover letter",
        "status": "needs_recheck",
        "error_code": "cover_letter_needs_recheck",
        "letter_content": deepcopy(fixed["cover_letter"]["result"]["content"]),
        "content_revision": fixed["cover_letter"]["result"]["content_revision"],
    }
    state["jobs"][0]["materials"] = [original]
    worker.store.save(state)
    job = state["jobs"][0]
    question = field(kind="file", required=True, accept=".pdf")
    with pytest.raises(PortalDataError) as caught:
        materials((worker, job, batch)).prepare(
            job, batch, {"fields": [question | {"max_bytes": 700_000}]}
        )
    assert caught.value.code == "cover_letter_needs_recheck"
    assert worker.store.load()["jobs"][0]["materials"] == [original]
