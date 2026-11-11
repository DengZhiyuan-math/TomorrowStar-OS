"""Synthetic supplemental prose uses documentary facts and durable independent attempts."""

import json
from types import SimpleNamespace

import pytest
from worker_preview_support import advance_until

from career_evidence_graph.career_portal_data import PortalDataError


def source_data():
    return {
        "items": [
            {
                "source_id": "project:Scope",
                "source_revision": "r1",
                "text": "Built Python services for a team of analysts.",
                "title": "Services",
                "resume_eligible": True,
                "boundaries": "No ownership of model training.",
                "attribution": "User",
            }
        ]
    }


def application():
    return {
        "id": "a" * 32,
        "role_title": "Engineer",
        "company": "Synthetic",
        "job_description": "Build Python services for financial analysis.",
    }


def selection(config, prompt, **kwargs):
    assert config.requested_model == "gpt-5.6-luna"
    assert "Build Python services" in prompt
    assert "Built Python services" in prompt
    output = (
        {"supported": True, "reason": "Exact synthetic evidence"}
        if config.output_schema.name == "validation-schema.json"
        else {
            "language": "en",
            "paragraphs": [
                {
                    "kind": "fact",
                    "text": "Built Python services for a team of analysts. No ownership of model"
                    " training.",
                    "source_ids": ["project:Scope"],
                    "source_quotes": ["Built Python services for a team of analysts."],
                }
            ],
        }
    )
    return SimpleNamespace(structured_result=output, model_dump=lambda **kw: {"synthetic": True})


def test_document_and_text_have_separate_cited_system_drafts(tmp_path):
    from career_evidence_graph.application_materials import generate_material

    calls = []

    def runner(*args, **kwargs):
        calls.append(args)
        return selection(*args, **kwargs)

    text = generate_material(
        tmp_path / "text",
        application(),
        source_data(),
        {"id": "why", "question": "Why this company?", "type": "textarea"},
        "motivation_text",
        runner=runner,
    )
    assert text["actor"] == "system" and text["human_reviewed"] is False
    assert "Built Python services" in text["text"]
    assert "No ownership of model training" in text["text"]
    assert text["source_binding"]["sources"][0]["source_id"] == "project:Scope"
    assert (
        json.loads((tmp_path / "text" / "intent.json").read_text())["attempt_id"]
        == text["attempt_id"]
    )
    assert "verified_by" not in json.dumps(text)
    assert len(calls) == 2
    with pytest.raises(PortalDataError) as failure:
        generate_material(
            tmp_path / "text",
            application(),
            source_data(),
            {"id": "why", "question": "Why this company?"},
            "motivation_text",
            runner=runner,
        )
    assert failure.value.code == "material_attempt_exists"
    assert len(calls) == 2


def test_untrusted_model_text_and_unknown_result_never_replay(tmp_path):
    from career_evidence_graph.application_materials import generate_material

    calls = []

    def bad(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(
            structured_result={"source_indices": [0], "text": "Invented achievement"},
            model_dump=lambda **kw: {},
        )

    for _ in range(2):
        with pytest.raises(PortalDataError):
            generate_material(
                tmp_path / "unknown",
                application(),
                source_data(),
                {"id": "cover", "question": "Cover letter"},
                "cover_letter",
                runner=bad,
            )
    assert len(calls) == 1
    assert not (tmp_path / "unknown" / "material.json").exists()
    assert (tmp_path / "unknown" / "intent.json").exists()


@pytest.mark.worker_browser
def test_generic_required_cover_and_motivation_are_independent_and_never_submit(
    tmp_path, monkeypatch
):
    from pathlib import Path

    from test_generic_worker import FIELDS, native_form

    from career_evidence_graph import application_materials

    calls = []

    def runner(config, prompt, **kwargs):
        calls.append(config.output_schema.name)
        return selection(config, prompt, **kwargs)

    monkeypatch.setattr(application_materials, "run_codex_exec", runner)
    from career_evidence_graph import application_resume

    monkeypatch.setattr(
        application_resume,
        "export_pdf",
        lambda html, pdf: pdf.write_bytes(
            (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
        ),
    )
    html = (
        "<form>" + FIELDS + '<label>Cover letter *<input id="cover" name="cover" type="file" '
        'required></label><label>Why this company? *<textarea id="why" '
        'required></textarea></label><button type="submit">Submit '
        "application</button></form>"
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        service.store.material_sources = source_data
        app = service.store.applications.get_application(job["application_id"])
        updated = service.store.applications.update_application(
            job["application_id"],
            {"job_description": application()["job_description"]},
            app["revision"],
        )
        state = service.store.load()
        state["jobs"][0]["revision"] = updated["revision"]
        service.store.save(state)
        current = advance_until(service, engine, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current
        materials = current["materials"]
        assert {row["kind"] for row in materials} == {"cover_letter", "motivation_text"}
        assert all(row["actor"] == "system" and not row["human_reviewed"] for row in materials)
        assert len({row["id"] for row in materials}) == 2
        page = engine.pages[job["application_id"]]
        assert page.locator("#why").input_value().startswith("Built Python")
        assert page.locator("#cover").evaluate("(e)=>e.files[0].name") == "cover-letter.pdf"
        uploads = [
            row["intent"]
            for row in current["observations"]
            if row.get("action") == "action_result" and row["intent"]["action"] == "upload"
        ]
        assert (
            len(uploads) == 2
            and len([row for row in uploads if row.get("kind") == "cover_letter"]) == 1
        )
        assert len(calls) == 4
        assert posts == []
        assert not any("motivation" in row["question"].lower() for row in service.store.library())
        for _ in range(2):
            engine.tick()
        assert len(calls) == 4 and posts == []


@pytest.mark.parametrize(
    "label",
    [
        "Why do you need visa sponsorship?",
        "Why are you leaving your employer?",
        "Why would you agree to this legal declaration?",
        "Why this salary expectation?",
        "Why are you applying after dismissal?",
        "Why do you seek a role after resignation?",
    ],
)
def test_sensitive_questions_are_not_system_motivation(label):
    from career_evidence_graph.application_materials import material_kind

    assert material_kind({"type": "textarea", "question": label}) is None


@pytest.mark.worker_browser
def test_actual_diploma_waits_then_uploads_only_provided_file(tmp_path, monkeypatch):
    import base64
    from pathlib import Path

    from test_generic_worker import FIELDS, native_form

    html = (
        "<form>"
        + FIELDS
        + (
            '<label>Diploma *<input id="diploma" type="file" required></lab'
            'el><button type="submit">Submit</button></form>'
        )
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        for _ in range(3):
            engine.tick()
        waiting = service.store.load()["jobs"][0]
        assert waiting["status"] == "needs_input" and waiting["reason"] == "missing_materials"
        requirement = waiting["materials"][0]
        assert requirement["kind"] == "diploma" and requirement["status"] == "needs_input"
        service.request("pause", {"controller": "synthetic-controller"})
        supplied = service.request(
            "provide-material",
            {
                "application_id": job["application_id"],
                "field_id": requirement["field_id"],
                "draft_path": requirement["draft_path"],
                "kind": "diploma",
                "filename": "real-provided-diploma.pdf",
                "file_base64": base64.b64encode(
                    (
                        Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
                    ).read_bytes()
                ).decode(),
                "request_id": "provide-one",
            },
        )
        assert supplied["control"] == "paused"
        assert supplied["jobs"][0]["materials"][0]["actor"] == "user"
        assert supplied["jobs"][0]["status"] == "needs_input"
        service.request("resume", {"controller": "synthetic-controller"})
        # Observe supplied material after this explicit resume before waiting.
        engine.tick()
        complete = advance_until(service, engine, lambda row: row["status"] == "ready_for_review")
        assert complete["status"] == "ready_for_review", complete
        page = engine.pages[job["application_id"]]
        assert (
            page.locator("#diploma").evaluate("(e)=>e.files[0].name") == "real-provided-diploma.pdf"
        )
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("label,required", [("Supporting file", True), ("Cover letter", False)])
def test_unknown_required_waits_and_optional_cover_keeps_visible_missing_facts(
    tmp_path, monkeypatch, label, required
):
    from test_generic_worker import FIELDS, native_form

    from career_evidence_graph import application_materials

    monkeypatch.setattr(
        application_materials, "run_codex_exec", lambda *_a, **_k: pytest.fail("No model")
    )
    html = (
        "<form>"
        + FIELDS
        + f'<label>{label}<input id="extra" type="file" {"required" if required else ""}>'
        + '</label><button type="submit">Submit</button></form>'
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, _job, posts):
        current = advance_until(
            service,
            engine,
            lambda row: row["status"] == ("needs_input" if required else "ready_for_review"),
        )
        assert current["status"] == ("needs_input" if required else "ready_for_review"), current
        if required:
            assert current["materials"][0]["kind"] == "unknown"
        else:
            assert current["materials"][0]["kind"] == "cover_letter"
            assert current["materials"][0]["status"] == "needs_input"
        assert posts == []


@pytest.mark.worker_browser
def test_human_motivation_is_preserved_without_model_or_fake_confirmation(tmp_path, monkeypatch):
    from test_generic_worker import FIELDS, native_form

    from career_evidence_graph import application_materials

    monkeypatch.setattr(
        application_materials, "run_codex_exec", lambda *_a, **_k: pytest.fail("No model")
    )
    html = (
        "<form>"
        + FIELDS
        + (
            '<label>Why this company? *<textarea required id="why">My own s'
            'aved motivation.</textarea></label><button type="submit">Submi'
            "t</button></form>"
        )
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        current = advance_until(service, engine, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current
        assert (
            engine.pages[job["application_id"]].locator("#why").input_value()
            == "My own saved motivation."
        )
        assert not current.get("materials") and len(service.store.library()) == 2 and posts == []


@pytest.mark.parametrize("unsupported", ["number", "responsibility"])
def test_unsupported_fact_stops_before_export_and_preserves_attempt(tmp_path, unsupported):
    from career_evidence_graph.application_materials import generate_material

    called = []

    def model(config, prompt, **kwargs):
        if config.output_schema.name == "validation-schema.json":
            return SimpleNamespace(
                structured_result={"supported": False, "reason": "Invented ownership"},
                model_dump=lambda **kw: {},
            )
        text = (
            "Built 99 Python services."
            if unsupported == "number"
            else "Led all implementation independently."
        )
        return SimpleNamespace(
            structured_result={
                "language": "en",
                "paragraphs": [
                    {
                        "kind": "fact",
                        "text": text,
                        "source_ids": ["project:Scope"],
                        "source_quotes": ["Built Python services for a team of analysts."],
                    }
                ],
            },
            model_dump=lambda **kw: {},
        )

    with pytest.raises(PortalDataError):
        generate_material(
            tmp_path / unsupported,
            application(),
            source_data(),
            {"id": "cover", "question": "Cover letter"},
            "cover_letter",
            runner=model,
            exporter=lambda *_a: called.append(True),
        )
    assert called == []
    assert (tmp_path / unsupported / "intent.json").exists()
    assert not (tmp_path / unsupported / "material.json").exists()


def test_explicit_french_material_uses_generated_french_with_exact_sources(tmp_path):
    from career_evidence_graph.application_materials import generate_material

    def model(config, prompt, **kwargs):
        assert "French" in prompt
        output = (
            {"supported": True, "reason": "Translation preserves the documentary responsibility"}
            if config.output_schema.name == "validation-schema.json"
            else {
                "language": "fr",
                "paragraphs": [
                    {
                        "kind": "fact",
                        "text": "J’ai développé des services Python pour une équipe d’analystes.",
                        "source_ids": ["project:Scope"],
                        "source_quotes": ["Built Python services for a team of analysts."],
                    }
                ],
            }
        )
        return SimpleNamespace(
            structured_result=output, model_dump=lambda **kw: {"synthetic": True}
        )

    result = generate_material(
        tmp_path / "french",
        application(),
        source_data(),
        {"id": "why", "question": "Why this company? Answer in French."},
        "motivation_text",
        runner=model,
    )
    assert result["language"] == "fr" and result["text"].startswith("J’ai")
    assert result["human_reviewed"] is False


@pytest.mark.worker_browser
def test_pause_during_generation_keeps_result_without_upload_or_second_draft(tmp_path, monkeypatch):
    from pathlib import Path

    from test_generic_worker import FIELDS, native_form

    from career_evidence_graph import application_materials, application_resume

    calls = []
    html = (
        "<form>"
        + FIELDS
        + (
            '<label>Cover letter *<input id="cover" type="file" required></'
            'label><label>Why this company? *<textarea id="why" required></'
            'textarea></label><button type="submit">Submit</button></form>'
        )
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        service.store.material_sources = source_data
        app = service.store.applications.get_application(job["application_id"])
        updated = service.store.applications.update_application(
            job["application_id"],
            {"job_description": application()["job_description"]},
            app["revision"],
        )
        state = service.store.load()
        state["jobs"][0]["revision"] = updated["revision"]
        service.store.save(state)

        def model(config, prompt, **kwargs):
            calls.append(config.output_schema.name)
            if len(calls) == 1:
                service.request("pause", {"controller": "synthetic-controller"})
            return selection(config, prompt, **kwargs)

        monkeypatch.setattr(application_materials, "run_codex_exec", model)
        monkeypatch.setattr(
            application_resume,
            "export_pdf",
            lambda html, pdf: pdf.write_bytes(
                (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
            ),
        )
        engine.tick()
        current = service.store.load()
        assert current["control"] == "paused"
        material = current["jobs"][0]["materials"][0]
        assert material["status"] == "ready" and material["kind"] == "cover_letter"
        assert len(calls) == 2 and len(current["jobs"][0]["materials"]) == 1
        page = engine.pages[job["application_id"]]
        assert page.locator("#cover").evaluate("(e)=>e.files.length") == 0
        assert page.locator("#why").input_value() == ""
        assert (
            len(
                [
                    row
                    for row in current["jobs"][0]["observations"]
                    if row.get("action") == "action_result"
                ]
            )
            == 1
        )
        assert posts == []


@pytest.mark.worker_browser
def test_changed_material_source_prevents_handoff_without_regeneration(tmp_path, monkeypatch):
    from test_generic_worker import FIELDS, native_form

    from career_evidence_graph import application_materials

    calls = []

    def model(config, prompt, **kwargs):
        calls.append(1)
        return selection(config, prompt, **kwargs)

    monkeypatch.setattr(application_materials, "run_codex_exec", model)
    html = (
        "<form>"
        + FIELDS
        + (
            '<label>Why this company? *<textarea id="why" required></textar'
            'ea></label><button type="submit">Submit</button></form>'
        )
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        data = source_data()
        service.store.material_sources = lambda: data
        app = service.store.applications.get_application(job["application_id"])
        updated = service.store.applications.update_application(
            job["application_id"],
            {"job_description": application()["job_description"]},
            app["revision"],
        )
        state = service.store.load()
        state["jobs"][0]["revision"] = updated["revision"]
        service.store.save(state)
        advance_until(service, engine, lambda row: row["status"] == "ready_for_review")
        data["items"][0]["source_revision"] = "corrected-real-source"
        with pytest.raises(PortalDataError) as failure:
            service.request("review", {"application_id": job["application_id"]})
        assert failure.value.code == "material_input_changed"
        assert not service.store.load()["jobs"][0]["handed_off"]
        assert len(calls) == 2 and posts == []


@pytest.mark.worker_browser
def test_late_cover_result_preserves_concurrent_provided_diploma(tmp_path, monkeypatch):
    import base64
    from pathlib import Path

    from test_generic_worker import FIELDS, native_form

    from career_evidence_graph import application_materials, application_resume

    raw = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
    html = (
        "<form>"
        + FIELDS
        + (
            '<label>Diploma *<input id="diploma" type="file" required></lab'
            'el><label>Cover letter *<input id="cover" type="file" required'
            '></label><button type="submit">Submit</button></form>'
        )
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        service.store.material_sources = source_data
        app = service.store.applications.get_application(job["application_id"])
        updated = service.store.applications.update_application(
            job["application_id"],
            {"job_description": application()["job_description"]},
            app["revision"],
        )
        state = service.store.load()
        state["jobs"][0]["revision"] = updated["revision"]
        service.store.save(state)

        def model(config, prompt, **kwargs):
            if config.output_schema.name == "schema.json":
                current = service.store.load()["jobs"][0]
                requirement = next(row for row in current["materials"] if row["kind"] == "diploma")
                service.request("pause", {"controller": "synthetic-controller"})
                service.request(
                    "provide-material",
                    {
                        "application_id": job["application_id"],
                        "field_id": requirement["field_id"],
                        "draft_path": requirement["draft_path"],
                        "kind": "diploma",
                        "filename": "provided-during-model.pdf",
                        "file_base64": base64.b64encode(raw).decode(),
                        "request_id": "concurrent-provide",
                    },
                )
            return selection(config, prompt, **kwargs)

        monkeypatch.setattr(application_materials, "run_codex_exec", model)
        monkeypatch.setattr(
            application_resume, "export_pdf", lambda html, pdf: pdf.write_bytes(raw)
        )
        engine.tick()
        state = service.store.load()
        assert state["control"] == "paused"
        diploma = next(row for row in state["jobs"][0]["materials"] if row["kind"] == "diploma")
        assert (
            diploma["status"] == "ready" and diploma["filename"] == "provided-during-model.pdf"
        ), diploma
        assert (
            next(row for row in state["jobs"][0]["materials"] if row["kind"] == "cover_letter")[
                "status"
            ]
            == "ready"
        )
        assert posts == []


@pytest.mark.worker_browser
def test_unknown_model_attempt_stops_and_never_calls_again(tmp_path, monkeypatch):
    from test_generic_worker import FIELDS, native_form

    from career_evidence_graph import application_materials

    calls = []

    def model(*_args, **_kwargs):
        calls.append(True)
        raise TimeoutError("Synthetic model response lost")

    monkeypatch.setattr(application_materials, "run_codex_exec", model)
    html = (
        "<form>"
        + FIELDS
        + (
            '<label>Cover letter *<input id="cover" type="file" required></'
            'label><button type="submit">Submit</button></form>'
        )
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        service.store.material_sources = source_data
        app = service.store.applications.get_application(job["application_id"])
        updated = service.store.applications.update_application(
            job["application_id"],
            {"job_description": application()["job_description"]},
            app["revision"],
        )
        state = service.store.load()
        state["jobs"][0]["revision"] = updated["revision"]
        service.store.save(state)
        engine.tick()
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        material = current["materials"][0]
        assert material["status"] == "needs_recheck" and material["attempt_id"]
        assert (service.store.root / "materials" / material["id"] / "intent.json").exists()
        service.request("resume", {"controller": "synthetic-controller"})
        for _ in range(3):
            engine.tick()
        assert calls == [True] and posts == []


def test_field_relabel_cannot_reuse_cover_for_diploma(tmp_path, monkeypatch):
    from test_hosted_ats import prepare

    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.career_portal_data import ApplicationStore

    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    job = prepare(service, "https://careers.example.test/jobs/engineer")
    job["materials"] = [
        {
            "field_id": "same-field",
            "draft_path": "",
            "kind": "cover_letter",
            "question": "Cover letter",
            "status": "ready",
        }
    ]
    with pytest.raises(PortalDataError) as failure:
        service.store.field_material(
            {"id": "same-field", "type": "file", "question": "Diploma", "resume": False}, job
        )
    assert failure.value.code == "material_field_changed"


def test_jd_supported_future_motivation_needs_no_invented_past_experience(tmp_path):
    from career_evidence_graph.application_materials import generate_material

    def model(config, prompt, **kwargs):
        output = (
            {"supported": True, "reason": "Future motivation only; actual JD quoted"}
            if config.output_schema.name == "validation-schema.json"
            else {
                "language": "en",
                "paragraphs": [
                    {
                        "kind": "motivation",
                        "text": (
                            "I would welcome the opportunity to build Python services for f"
                            "inancial analysis."
                        ),
                        "source_ids": ["jd"],
                        "source_quotes": ["Build Python services for financial analysis."],
                    }
                ],
            }
        )
        return SimpleNamespace(structured_result=output, model_dump=lambda **kw: {})

    result = generate_material(
        tmp_path / "future",
        application(),
        {"items": []},
        {"id": "why", "question": "Why this company?"},
        "motivation_text",
        runner=model,
    )
    assert result["source_binding"]["sources"][0]["source_id"] == "jd"
    assert result["paragraphs"][0]["kind"] == "motivation" and not result["human_reviewed"]


@pytest.mark.worker_browser
@pytest.mark.parametrize("change_path", [False, True])
def test_old_required_material_does_not_block_current_optional_field(
    tmp_path, monkeypatch, change_path
):
    from test_generic_worker import FIELDS, native_form

    html = (
        "<form>"
        + FIELDS
        + (
            '<label>Diploma<input id="diploma" data-field-path="old-path" t'
            'ype="file" required></label><button type="submit">Submit</butt'
            "on></form>"
        )
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        for _ in range(3):
            engine.tick()
        before = service.store.load()["jobs"][0]
        assert before["reason"] == "missing_materials"
        original = before["materials"][0].copy()
        service.request("pause", {"controller": "synthetic-controller"})
        page = engine.pages[job["application_id"]]
        page.locator("#diploma").evaluate(
            "(e, change) => {e.required=false; if(change)e.dataset.fieldPath='new-path'}",
            change_path,
        )
        service.request("resume", {"controller": "synthetic-controller"})
        engine.tick()
        current = advance_until(service, engine, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current
        assert original in current["materials"]
        assert page.locator("#diploma").evaluate("e=>e.files.length") == 0 and posts == []


@pytest.mark.worker_browser
def test_material_models_suspend_only_browser_timer_and_restore_it_for_export(
    tmp_path, monkeypatch
):
    import signal
    from pathlib import Path

    from test_generic_worker import FIELDS, native_form

    from career_evidence_graph import application_materials, application_resume

    timers = []

    def model(config, prompt, **kwargs):
        timers.append(signal.getitimer(signal.ITIMER_REAL)[0])
        assert timers[-1] == 0, "The model still consumes the browser action deadline"
        assert kwargs["timeout_seconds"] == 180
        return selection(config, prompt, **kwargs)

    def exporter(html, pdf):
        assert 0 < signal.getitimer(signal.ITIMER_REAL)[0] <= 35
        pdf.write_bytes(
            (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
        )

    monkeypatch.setattr(application_materials, "run_codex_exec", model)
    monkeypatch.setattr(application_resume, "export_pdf", exporter)
    html = (
        "<form>"
        + FIELDS
        + (
            '<label>Cover letter *<input id="cover" type="file" required></'
            'label><button type="submit">Submit</button></form>'
        )
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        service.store.material_sources = source_data
        app = service.store.applications.get_application(job["application_id"])
        updated = service.store.applications.update_application(
            job["application_id"],
            {"job_description": application()["job_description"]},
            app["revision"],
        )
        state = service.store.load()
        state["jobs"][0]["revision"] = updated["revision"]
        service.store.save(state)
        current = advance_until(service, engine, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current
        assert timers == [0, 0] and engine.action_timeout == 35
        assert signal.getitimer(signal.ITIMER_REAL)[0] == 0 and posts == []
