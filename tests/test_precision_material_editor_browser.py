"""Prepared supplemental drafts are readable and editable before their first send."""

from pathlib import Path

import pytest
from test_application_resume import task_resume as task_resume
from test_automatic_material_editor_browser import serving
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex
from test_precision_material_preparation_browser import advance_precision
from test_precision_material_preparation_browser import precision_page as precision_page

pytestmark = pytest.mark.worker_browser


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
def test_first_precision_wait_shows_the_prepared_text_and_checked_pdf(precision_page):
    from playwright.sync_api import expect

    p = precision_page
    state = p.worker.store.load()
    job = state["jobs"][0]
    task = p.flow.snapshot()["active_task"]
    material = next(row for row in job["materials"] if row["kind"] == "cover_letter")
    original_bytes = Path(material["file_path"]).read_bytes()
    with serving(p.server) as origin:
        context = p.browser.new_context()
        context.route(
            "**/*",
            lambda route: (
                route.continue_() if route.request.url.startswith(origin + "/") else route.abort()
            ),
        )
        try:
            page = context.new_page()
            page.goto(origin + "/#flow")
            card = page.locator(f'[data-flow-material-id="{material["id"]}"]')
            expect(card).to_have_count(1)
            card.get_by_text("查看附稿正文", exact=True).click()
            expect(card.locator("pre")).to_have_text(material["text"])
            link = card.get_by_role("link", name="打开附稿 PDF 预览", exact=True)
            target = link.get_attribute("href")
            assert target == f"/api/flow/worker-materials/{task['id']}/{material['id']}/pdf"
            response = context.request.get(origin + target)
            assert response.status == 200 and response.body() == original_bytes
            assert "application/pdf" in response.headers["content-type"]
            assert p.worker.store.load()["control"] == "paused"
            assert p.page.locator("#email").input_value() == ""
            assert p.page.locator("#why").input_value() == ""
            assert p.page.locator("input[type=file]").evaluate_all(
                "nodes=>nodes.every(e=>e.files.length===0)"
            )
            assert p.page.evaluate("window.finalActions") == 0
            assert len(p.material_calls) == 4 and len(p.calls) == 1
        finally:
            context.close()


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
@pytest.mark.parametrize("kind", ["motivation_text", "cover_letter"])
@pytest.mark.parametrize("continue_after_save", [False, True])
def test_human_supplement_edit_is_saved_on_the_same_job_without_sending(
    precision_page, monkeypatch, kind, continue_after_save
):
    from playwright.sync_api import expect

    p = precision_page
    original = p.worker.store.load()["jobs"][0]
    old = next(row for row in original["materials"] if row["kind"] == kind)
    changed = "I would like to contribute to this team.\n\n" + old["text"]
    if continue_after_save and kind == "motivation_text":
        from career_evidence_graph.application_information import put_information_answer

        put_information_answer(
            p.worker.store.answers,
            {
                "question": old["question"],
                "value": "Earlier application answer.",
                "state": "confirmed",
                "scope": {"application_id": original["application_id"]},
            },
        )
    old_file = p.worker.store.root / "materials" / old["id"] / "material.json"
    old_bytes = old_file.read_bytes()
    old_pdf = Path(old["file_path"]).read_bytes() if kind == "cover_letter" else None
    exports = []
    from career_evidence_graph import application_resume

    previous_export = application_resume.export_pdf

    def export_changed(html, pdf):
        exports.append(html.read_text())
        return previous_export(html, pdf)

    monkeypatch.setattr(application_resume, "export_pdf", export_changed)
    with serving(p.server) as origin:
        context = p.browser.new_context()
        context.route(
            "**/*",
            lambda route: (
                route.continue_() if route.request.url.startswith(origin + "/") else route.abort()
            ),
        )
        try:
            page = context.new_page()
            page.goto(origin + "/#flow")
            card = page.locator(f'[data-flow-material-id="{old["id"]}"]')
            expect(card.get_by_text("修改附稿正文", exact=True)).to_be_visible(timeout=3000)
            card.get_by_text("修改附稿正文", exact=True).click()
            editor = card.get_by_label(old["question"] + " · 附稿正文", exact=True)
            expect(editor).to_have_value(old["text"])
            editor.fill(changed)
            expect(page.locator("#flow-pipeline-start")).to_be_disabled()
            card.get_by_role("button", name="保存附稿修改", exact=True).click()
            expect(page.locator("#flow-notice")).to_contain_text("附稿修改已保存")
            current = p.worker.store.load()
            job = current["jobs"][0]
            saved = next(row for row in job["materials"] if row["kind"] == kind)
            assert saved["text"] == changed and saved["actor"] == "user"
            assert saved["id"] != old["id"] and saved["human_reviewed"] is False
            assert current["control"] == "paused"
            assert job["material_history"][-1] == old and old_file.read_bytes() == old_bytes
            assert len(exports) == (1 if kind == "cover_letter" else 0)
            if kind == "cover_letter":
                assert Path(saved["file_path"]).parent != Path(old["file_path"]).parent
                assert Path(old["file_path"]).read_bytes() == old_pdf
                assert "I would like to contribute to this team." in exports[0]
                current_task = p.flow.snapshot()["active_task"]
                for version, expected in (
                    (old, old_pdf),
                    (saved, Path(saved["file_path"]).read_bytes()),
                ):
                    url = f"/api/flow/worker-materials/{current_task['id']}/{version['id']}/pdf"
                    response = context.request.get(origin + url)
                    assert response.status == 200 and response.body() == expected
            assert p.engine.pages[job["application_id"]] is p.page
            assert p.page.locator("#why").input_value() == ""
            assert p.page.locator("input[type=file]").evaluate_all(
                "nodes=>nodes.every(e=>e.files.length===0)"
            )
            assert len(p.material_calls) == 4 and len(p.calls) == 1
            assert p.page.evaluate("window.finalActions") == 0
            if continue_after_save:
                page.locator("#flow-pipeline-start").click()
                result = advance_precision(
                    p,
                    lambda state: (
                        state["status"] in {"ready_for_review", "needs_input", "needs_recheck"}
                    ),
                )
                assert result["status"] == "ready_for_review", result
                if kind == "motivation_text":
                    assert p.page.locator("#why").input_value() == changed
                else:
                    final_job = p.worker.store.load()["jobs"][0]
                    assert any(
                        row.get("intent", {}).get("material_id") == saved["id"]
                        for row in final_job["observations"]
                    )
                assert len(p.material_calls) == 4 and p.page.evaluate("window.finalActions") == 0
        finally:
            context.close()


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
def test_saved_supplement_with_lost_response_is_recovered_by_exact_readback(precision_page):
    from playwright.sync_api import expect

    p = precision_page
    old = next(
        row
        for row in p.worker.store.load()["jobs"][0]["materials"]
        if row["kind"] == "motivation_text"
    )
    changed = "I am interested in this role.\n\n" + old["text"]
    saves = []
    with serving(p.server) as origin:
        context = p.browser.new_context()
        context.route(
            "**/*",
            lambda route: (
                route.continue_() if route.request.url.startswith(origin + "/") else route.abort()
            ),
        )

        def lose_response(route):
            saves.append(route.request.post_data_json)
            response = route.fetch()
            assert response.status == 200
            route.abort()

        context.route("**/api/flow/edit-material", lose_response)
        try:
            page = context.new_page()
            page.goto(origin + "/#flow")
            card = page.locator(f'[data-flow-material-id="{old["id"]}"]')
            card.get_by_text("修改附稿正文", exact=True).click()
            card.get_by_label(old["question"] + " · 附稿正文", exact=True).fill(changed)
            card.get_by_role("button", name="保存附稿修改", exact=True).click()
            expect(page.locator("#flow-notice")).to_contain_text("结果")
            page.locator("#flow-observe").click()
            expect(page.locator("#flow-pipeline-start")).to_be_enabled(timeout=3000)
            current = p.worker.store.load()
            saved = next(
                row for row in current["jobs"][0]["materials"] if row["kind"] == "motivation_text"
            )
            assert saved["text"] == changed and len(saves) == 1
            assert current["jobs"][0]["material_edit"]["request_id"] == saves[0]["request_id"]
            assert current["control"] == "paused" and p.page.locator("#why").input_value() == ""
            assert len(p.material_calls) == 4 and p.page.evaluate("window.finalActions") == 0
        finally:
            context.close()


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
def test_parallel_material_edits_retain_both_texts_and_require_an_explicit_rebase(precision_page):
    from playwright.sync_api import expect

    p = precision_page
    old = next(
        row
        for row in p.worker.store.load()["jobs"][0]["materials"]
        if row["kind"] == "motivation_text"
    )
    local = "My first-window edit.\n\n" + old["text"]
    other = "My second-window edit.\n\n" + old["text"]
    with serving(p.server) as origin:
        context = p.browser.new_context()
        context.route(
            "**/*",
            lambda route: (
                route.continue_() if route.request.url.startswith(origin + "/") else route.abort()
            ),
        )
        try:
            first, second = context.new_page(), context.new_page()
            first.goto(origin + "/#flow")
            first_card = first.locator(f'[data-flow-material-id="{old["id"]}"]')
            first_card.get_by_text("修改附稿正文", exact=True).click()
            first_card.get_by_label(old["question"] + " · 附稿正文", exact=True).fill(local)
            second.goto(origin + "/#flow")
            second_card = second.locator(f'[data-flow-material-id="{old["id"]}"]')
            second_card.get_by_text("修改附稿正文", exact=True).click()
            second_card.get_by_label(old["question"] + " · 附稿正文", exact=True).fill(other)
            second_card.get_by_role("button", name="保存附稿修改", exact=True).click()
            expect(second.locator("#flow-notice")).to_contain_text("附稿修改已保存")
            first.locator("#flow-observe").click()
            expect(first.get_by_label(old["question"] + " · 附稿正文", exact=True)).to_have_value(
                local
            )
            expect(
                first.get_by_role("button", name="保留编辑并采用当前附稿版本", exact=True)
            ).to_be_visible(timeout=3000)
            expect(first.get_by_role("button", name="保存附稿修改", exact=True)).to_be_disabled()
            first.get_by_role("button", name="保留编辑并采用当前附稿版本", exact=True).click()
            first.get_by_role("button", name="保存附稿修改", exact=True).click()
            expect(first.locator("#flow-notice")).to_contain_text("附稿修改已保存")
            current = p.worker.store.load()
            job = current["jobs"][0]
            assert (
                next(row for row in job["materials"] if row["kind"] == "motivation_text")["text"]
                == local
            )
            assert any(row.get("text") == other for row in job["material_history"])
            assert old in job["material_history"]
            assert current["control"] == "paused" and p.page.locator("#why").input_value() == ""
            assert len(p.material_calls) == 4 and p.page.evaluate("window.finalActions") == 0
        finally:
            context.close()


@pytest.mark.parametrize(
    "bound_pipeline", [{"application_strategy": "manual", "stop_at": "needs_input"}], indirect=True
)
@pytest.mark.parametrize(
    "stop,damage", [("pause", None), ("skip", None), ("skip", "missing"), ("skip", "changed")]
)
def test_pending_cover_export_blocks_continue_and_stop_wins_the_late_result(
    precision_page, monkeypatch, stop, damage
):
    from threading import Thread

    from playwright.sync_api import expect

    from career_evidence_graph import application_resume
    from career_evidence_graph.career_portal_data import PortalDataError

    p = precision_page
    old = next(
        row
        for row in p.worker.store.load()["jobs"][0]["materials"]
        if row["kind"] == "cover_letter"
    )
    original_bytes = Path(old["file_path"]).read_bytes()
    previous_export = application_resume.export_pdf
    during, stopped = [], []

    def export_while_user_stops(html, pdf):
        pending = p.worker.store.load()["jobs"][0]["material_edit"]
        assert pending["status"] == "preparing"
        with pytest.raises(PortalDataError) as error:
            p.pipeline.continue_current(request_id="continue-while-editing")
        assert error.value.code == "material_edit_needs_recheck"
        during.append(pending)

        def stop_now():
            stopped.append(
                p.pipeline.pause()
                if stop == "pause"
                else p.pipeline.skip_current(request_id="skip-during-edit")
            )

        thread = Thread(target=stop_now, daemon=True)
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive(), "Local PDF export must not hold the application write lock"
        assert len(stopped) == 1
        return previous_export(html, pdf)

    monkeypatch.setattr(application_resume, "export_pdf", export_while_user_stops)
    with serving(p.server) as origin:
        context = p.browser.new_context()
        context.route(
            "**/*",
            lambda route: (
                route.continue_() if route.request.url.startswith(origin + "/") else route.abort()
            ),
        )
        responses = []
        try:
            page = context.new_page()
            page.on(
                "response",
                lambda response: (
                    responses.append(response.status)
                    if response.url.endswith("/api/flow/edit-material")
                    else None
                ),
            )
            page.goto(origin + "/#flow")
            card = page.locator(f'[data-flow-material-id="{old["id"]}"]')
            card.get_by_text("修改附稿正文", exact=True).click()
            card.get_by_label(old["question"] + " · 附稿正文", exact=True).fill(
                "My considered cover letter.\n\n" + old["text"]
            )
            card.get_by_role("button", name="保存附稿修改", exact=True).click()
            expect(page.locator("#flow-notice")).not_to_have_text("")
            assert responses == [200 if stop == "pause" else 409]
            assert len(during) == 1
            state = p.worker.store.load()
            job = state["jobs"][0]
            assert (
                state["control"] == "paused"
                and Path(old["file_path"]).read_bytes() == original_bytes
            )
            assert (
                p.worker.store.root / "materials" / during[0]["new_material_id"] / "material.json"
            ).exists()
            if stop == "skip":
                assert state["current_job_id"] is None
                assert job["material_edit"]["status"] == "needs_recheck"
                assert old in job["materials"]
            else:
                assert job["material_edit"]["status"] == "complete"
            for _ in range(3):
                p.pipeline._tick()
                p.engine.tick()
            assert p.page.locator("#email").input_value() == ""
            assert p.page.locator("input[type=file]").evaluate_all(
                "nodes=>nodes.every(e=>e.files.length===0)"
            )
            assert len(p.material_calls) == 4 and p.page.evaluate("window.finalActions") == 0
            if stop == "skip":
                p.pipeline.return_to(job["application_id"], request_id="return-after-edit")
                for _ in range(4):
                    p.pipeline._tick()
                    p.engine.tick()
                page.locator("#flow-observe").click()
                check = page.get_by_role("button", name="核验附稿保存结果", exact=True)
                expect(check).to_be_visible(timeout=3000)
                candidate = (
                    p.worker.store.root
                    / "materials"
                    / during[0]["new_material_id"]
                    / "material.json"
                )
                if damage == "missing":
                    candidate.unlink()
                elif damage == "changed":
                    import json

                    damaged = json.loads(candidate.read_text())
                    damaged["text"] += " Unexpected local candidate change."
                    candidate.write_text(json.dumps(damaged))
                check.click()
                if damage:
                    expect(page.locator("#flow-notice")).to_contain_text("未完整核验")
                    state = p.worker.store.load()
                    assert state["control"] == "paused" and old in state["jobs"][0]["materials"]
                    assert state["jobs"][0]["material_edit"]["status"] == "needs_recheck"
                    assert len(during) == 1 and len(p.material_calls) == 4
                    assert (
                        p.page.locator("#email").input_value() == ""
                        and p.page.evaluate("window.finalActions") == 0
                    )
                    return
                expect(page.locator("#flow-notice")).to_contain_text("已核验并保存")
                state = p.worker.store.load()
                restored = state["jobs"][0]
                assert restored["material_edit"]["status"] == "complete"
                assert old in restored["material_history"]
                assert state["control"] == "paused" and p.page.locator("#email").input_value() == ""
                assert len(during) == 1 and len(p.material_calls) == 4
                expect(page.locator("#flow-pipeline-start")).to_be_enabled()
                page.locator("#flow-pipeline-start").click()
                result = advance_precision(
                    p,
                    lambda state: (
                        state["status"] in {"ready_for_review", "needs_input", "needs_recheck"}
                    ),
                )
                assert result["status"] == "ready_for_review", result
                assert len(during) == 1 and p.page.evaluate("window.finalActions") == 0
        finally:
            context.close()
