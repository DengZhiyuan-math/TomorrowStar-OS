"""Bounded synthetic DOM journey; loopback only, no real Prism or applicant data."""

import re
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from test_career_portal_http import portal as portal
from test_full_latex_http import bind_generate, generated_portal
from test_job_explanation_browser import reveal_control
from test_portal_workflow_browser import browser_page as browser_page
from test_preparation_entry import snapshot

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_worker import digest

pytestmark = pytest.mark.worker_browser


def test_group_review_dom_and_exact_changed_group_inheritance(
    portal, tmp_path, monkeypatch, browser_page
):
    from playwright.sync_api import expect

    with generated_portal(portal, tmp_path, monkeypatch) as (active, task, base, calls, work):
        task = bind_generate(active, task, base)
        store = active.server.application_resume_store
        original = store.draft
        prepared = deepcopy(original(task["draft_id"]))
        working = tmp_path / "group-working"
        working.mkdir()
        main = working / "main.tex"
        main.write_text(
            "\\documentclass{article}\\begin{document}\nA fact.\nB fact.\n\\end{document}"
        )
        source = {
            "source_id": "synthetic-source",
            "title": "Synthetic evidence",
            "text": "A fact. B fact.",
            "locator": "scope",
            "attribution": ["User"],
            "resume_eligible": True,
        }
        prepared.update(
            id=uuid4().hex,
            draft_sha256=digest("prepared"),
            source_checkpoint=source_snapshot(working, "main.tex"),
            group_session={"id": "synthetic-session"},
            group_context_revision="context",
            group_preview=None,
            omitted_groups=[],
            verification_queue=[],
            available_review_sources=[source],
        )
        prepared["review_groups"] = [
            {
                "id": identifier,
                "title": title,
                "original": wording,
                "rewritten": wording,
                "sources": [source],
                "attribution": ["User"],
                "disposition": "include",
                "review_fingerprint": digest(wording),
            }
            for identifier, title, wording in [
                ("one", "First project", "A fact."),
                ("two", "Second project", "B fact."),
            ]
        ]
        drafts = {prepared["id"]: prepared}
        captures = []
        monkeypatch.setattr(
            store, "draft", lambda key: drafts[key] if key in drafts else original(key)
        )
        monkeypatch.setattr(store, "prepare_group_review", lambda *args, **kwargs: prepared)
        monkeypatch.setattr(
            store,
            "group_review_state",
            lambda key: {
                "status": "ready",
                "pending_attempt_id": None,
                "live_source_revision": source_snapshot(working, "main.tex")["source_revision"],
            },
        )

        def capture(identifier, sha256, **kwargs):
            previous = drafts[identifier]
            binding = source_snapshot(working, "main.tex")
            if previous.get("group_preview") and binding == previous["source_checkpoint"]:
                return {"draft": previous, "status": "ready"}
            captures.append(binding["source_revision"])
            revised = deepcopy(previous)
            revised.update(
                id=uuid4().hex,
                draft_sha256=digest([binding, len(captures)]),
                source_checkpoint=binding,
            )
            revised["review_groups"][0]["rewritten"] = (
                "A edited." if "A edited." in main.read_text() else "A fact."
            )
            for group in revised["review_groups"]:
                group["review_fingerprint"] = digest(group["rewritten"])
            revised["verified_unchanged_group_ids"] = [
                group["id"]
                for group in revised["review_groups"]
                if next(old for old in previous["review_groups"] if old["id"] == group["id"])[
                    "review_fingerprint"
                ]
                == group["review_fingerprint"]
            ]
            revised["group_preview"] = {
                "id": uuid4().hex,
                "source_revision": binding["source_revision"],
            }
            drafts[revised["id"]] = revised
            return {"draft": revised, "status": "ready", "preview": revised["group_preview"]}

        monkeypatch.setattr(store, "capture_group_review", capture)
        monkeypatch.setattr(
            store,
            "group_preview_pdf",
            lambda *args: (
                Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
            ).read_bytes(),
        )
        page = browser_page
        page.context.route(
            re.compile(
                r"^(chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/|chrome://resources/)"
            ),
            lambda route: route.continue_(),
        )
        page.goto(active.origin + "/#flow")
        root = page.locator("#flow-root")
        reveal_control(page, "#flow-draft")
        root.get_by_role("button", name="建立独立分组审阅版本", exact=True).click()
        expect(root.locator('[data-group-review="one"]')).to_be_disabled()
        root.get_by_role("button", name="读取并编译当前 LaTeX 预览", exact=True).click()
        expect(root.locator("#flow-grouped-review iframe")).to_be_visible()
        for index, identifier in enumerate(["one", "two"]):
            root.locator("#flow-review-groups > details").nth(index).locator(
                "summary"
            ).first.click()
            root.locator(f'[data-group-review="{identifier}"]').click()
            expect(root.get_by_text("此组当前版本已确认。", exact=True)).to_have_count(index + 1)
        expect(root).to_contain_text("经历组已审核")
        assert len(captures) == 1
        for _ in range(3):
            assert snapshot(active)["active_task"]["factual_review"] == "groups_reviewed"
        assert len(captures) == 1
        main.write_text(main.read_text().replace("A fact.", "A edited."))
        root.get_by_role("button", name="读取最新状态", exact=True).click()
        expect(root).to_contain_text("检测到 Prism 已保存新改动")
        root.get_by_role("button", name="读取并编译当前 LaTeX 预览", exact=True).click()
        expect(root).to_contain_text("沿用此组确认记录")
        root.locator("#flow-review-groups > details").nth(0).locator("summary").first.click()
        expect(root.locator('[data-group-review="one"]')).to_be_enabled()
        expect(root.locator('[data-group-review="two"]')).to_be_disabled()
        root.locator('[data-group-review="one"]').click()
        expect(root).to_contain_text("经历组已审核")
        current = snapshot(active)["active_task"]
        assert current["materials_confirmed"] is False and current["resume_id"] is None
        assert len(captures) == 2 and len(calls) == 1 and not work["exports"]
        assert active.server.worker_service is None
        expect(root.get_by_role("button", name="确认此版本 PDF", exact=True)).to_have_count(0)


def test_fixed_education_is_displayed_as_reused_without_repeat_confirmation(
    portal, tmp_path, monkeypatch, browser_page
):
    from playwright.sync_api import expect
    from test_group_review_presentation_policy import policy_draft
    from test_preparation_entry import post

    with generated_portal(portal, tmp_path, monkeypatch) as (active, task, base, calls, work):
        task = bind_generate(active, task, base)
        store = active.server.application_resume_store
        original = store.draft
        prepared = deepcopy(original(task["draft_id"]))
        education = policy_draft()["review_groups"][0]
        education["title"] = "Documented education"
        prepared.update(
            id=uuid4().hex,
            draft_sha256=digest("fixed education prepared"),
            presentation_policy=policy_draft()["presentation_policy"],
            group_session={"id": "synthetic-session"},
            group_context_revision="context",
            group_preview=None,
            omitted_groups=[],
            verification_queue=[],
        )
        prepared["review_groups"][0]["review_fingerprint"] = digest("tailored work")
        prepared["review_groups"].append(education)
        monkeypatch.setattr(
            store, "draft", lambda key: prepared if key == prepared["id"] else original(key)
        )
        monkeypatch.setattr(store, "prepare_group_review", lambda *args, **kwargs: prepared)
        monkeypatch.setattr(
            store,
            "group_review_state",
            lambda key: {
                "status": "empty",
                "pending_attempt_id": None,
                "live_source_revision": prepared["source_checkpoint"]["source_revision"],
            },
        )
        status, task = post(
            active, "begin-group-review", {"task_id": task["id"], "task_revision": task["revision"]}
        )
        assert status == 200
        page = browser_page
        page.goto(active.origin + "/#flow")
        root = page.locator("#flow-root")
        reveal_control(page, "#flow-draft")
        row = root.locator("#flow-review-groups > details").filter(
            has=page.get_by_text("Documented education", exact=True)
        )
        row.locator("summary").first.click()
        expect(row).to_contain_text("教育经历已按固定记录复用，无需重复事实确认。")
        expect(row.locator("[data-group-review]")).to_have_count(0)
        expect(row.get_by_role("button")).to_have_count(0)
        expect(root.locator('[data-group-review="synthetic"]')).to_have_count(1)
        expect(root.get_by_role("button", name="确认此版本 PDF", exact=True)).to_have_count(0)
        assert snapshot(active)["active_task"]["group_reviews"] == []
        assert snapshot(active)["active_task"]["materials_confirmed"] is False
        assert not work["exports"] and active.server.worker_service is None
        pending = deepcopy(education)
        pending.update(
            id="3" * 64,
            title="Unresolved education status",
            content_policy="education_verification_required",
            disposition="verify",
        )
        changed = deepcopy(prepared)
        changed.update(id=uuid4().hex, draft_sha256=digest("unresolved education version"))
        changed["verification_queue"].append(pending)
        monkeypatch.setattr(
            store,
            "draft",
            lambda key: (
                changed
                if key == changed["id"]
                else (prepared if key == prepared["id"] else original(key))
            ),
        )
        active.server.application_flow_service.callbacks["group_edit"] = lambda *args: changed
        status, task = post(
            active,
            "edit-review-group",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "payload": {"group_id": pending["id"]},
            },
        )
        assert status == 200
        page.reload()
        expect(root).to_contain_text("教育经历存在来源或状态冲突，请先核对已有记录。")
        expect(root).to_contain_text("当前版本不能导出 PDF。")
        reveal_control(page, "#flow-export-pdf")
        expect(root.get_by_role("button", name="绑定完整源与新 PDF", exact=True)).to_be_disabled()
