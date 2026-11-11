"""Three opt-in Lever rounds against the shared independent worker."""

from __future__ import annotations

import base64
import hashlib
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread

import pytest
from worker_preview_support import Preview, running_preview, stop_worker

from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal import create_server

pytestmark = pytest.mark.worker_browser


def test_workbench_answer_feedback_keeps_paused_batch_explicit(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with running_preview(tmp_path, 1) as preview:
        preview.prepare(["CHE"])
        preview.post("resume", controller=preview.controller)
        preview.wait(lambda state: state["jobs"][0]["status"] == "needs_input")
        before_uploads = preview.events()["uploads"]
        assert len(before_uploads) == 1
        preview.post("pause", controller=preview.controller)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                page = browser.new_page()
                page.goto(preview.origin + "/#applications")
                root = page.locator("#worker-root")
                expect(root).to_be_visible(timeout=10000)
                expect(root).not_to_contain_text("补充后会自动恢复")
                root.get_by_label("已确认答案").select_option("Yes")
                root.get_by_role("button", name="确认并保存", exact=True).click()
                expect(page.locator("#toast")).to_contain_text("批次仍暂停")
                expect(page.locator("#toast")).to_contain_text("开始／继续")
                summary = root.get_by_role("region", name="证据与下一步")
                expect(summary).to_contain_text("下一步：点击开始／继续")
                expect(summary).to_contain_text("页面状态：当前受管原页")
                state = preview.get("/api/worker/state")
                assert state["control"] == "paused"
                assert state["jobs"][0]["status"] == "queued"
                assert preview.events()["uploads"] == before_uploads
                assert preview.events()["submissions"] == []
            finally:
                browser.close()


def test_workbench_keeps_completed_jobs_in_manual_review(tmp_path: Path, monkeypatch) -> None:
    from playwright.sync_api import expect, sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with running_preview(tmp_path, 1) as p:
        p.seed("Will you now or in the future require visa sponsorship?", "No", {"country": "USA"})
        p.prepare(["USA"])
        p.post("resume", controller=p.controller)
        state = p.wait(lambda s: s["jobs"][0]["status"] == "ready_for_review")
        p.post("pause", controller=p.controller)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                page = browser.new_page()
                page.goto(p.origin + "/#applications")
                worker = page.locator("#worker-root")
                # The widget starts after the portal state and its 1.5 s polling cycle.
                expect(worker).to_be_visible(timeout=10000)
                expect(worker.get_by_text("等待人工复核", exact=True)).to_be_visible()
                expect(worker.get_by_role("button", name="开始／继续", exact=True)).to_be_disabled()

                def unavailable(route):
                    route.fulfill(status=503, json={"message": "Synthetic state unavailable"})

                page.route("**/api/worker/state", unavailable)
                historical = worker.get_by_text(
                    "页面状态来自上次记录。worker 未连接，尚未核验页面是否仍打开。", exact=True
                )
                expect(historical).to_be_visible()
                assert p.worker.process.poll() is None
                assert p.store.load()["jobs"][0]["page_open"]
                page.unroute("**/api/worker/state", unavailable)
                expect(historical).to_be_hidden()
                p.post("review", application_id=state["jobs"][0]["application_id"])
                p.wait(lambda s: s["jobs"][0]["handed_off"])
                expect(
                    worker.get_by_text("已转为人工处理，自动填写已停止。", exact=True)
                ).to_be_visible()
                expect(
                    worker.get_by_role("button", name="我已人工提交", exact=True)
                ).to_be_visible()
                assert p.events()["submissions"] == []
                assert len(p.events()["uploads"]) == 1
                assert p.get("/api/worker/state")["jobs"][0]["page_open"]
                stop_worker(p)
                expect(
                    worker.get_by_text(
                        "页面状态来自上次记录。worker 未连接，尚未核验页面是否仍打开。", exact=True
                    )
                ).to_be_visible(timeout=10000)
                p.post(
                    "recheck",
                    application_id=state["jobs"][0]["application_id"],
                    acknowledge=True,
                    reclaim=True,
                    handoff_source="Synthetic current handoff and history verified",
                )
                expect(worker.get_by_role("button", name="开始／继续", exact=True)).to_be_enabled()
            finally:
                browser.close()


def test_workbench_conflict_action_only_syncs_records(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    with running_preview(tmp_path, 1) as preview:
        preview.prepare(["CHE"])
        preview.post("resume", controller=preview.controller)
        preview.wait(lambda state: state["jobs"][0]["status"] == "needs_input")
        before_uploads = preview.events()["uploads"]
        assert len(before_uploads) == 1
        preview.post("pause", controller=preview.controller)
        with preview.store.applications.write_lock():
            state = preview.store.load()
            job = state["jobs"][0]
            preview.store.applications.update_application(
                job["application_id"], {"notes": "Synthetic concurrent edit"}, job["revision"]
            )
            job.update(status="needs_recheck", reason="answer_changed")
            preview.store.sync(job, "Synthetic existing fault page requires human review")
            preview.store.save(state)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            try:
                page = browser.new_page()
                page.goto(preview.origin + "/#applications")
                root = page.locator("#worker-root")
                summary = root.get_by_role("region", name="证据与下一步")
                expect(summary).to_contain_text("核验原记录变化后仅同步")
                root.get_by_role("button", name="核验冲突后同步").click()
                page.get_by_role("button", name="已核验，同步记录", exact=True).click()
                expect(
                    root.get_by_text("原记录同步未完成。浏览器结果已保留。", exact=True)
                ).to_be_hidden()
                state = preview.get("/api/worker/state")
                assert state["control"] == "paused"
                assert state["jobs"][0]["status"] == "needs_recheck"
                assert state["jobs"][0]["page_current"]
                assert not state["jobs"][0]["handed_off"]
                record = preview.store.applications.get_application(job["application_id"])
                assert record["notes"] == "Synthetic concurrent edit"
                assert (
                    record["next_action"] == "Synthetic existing fault page requires human review"
                )
                assert preview.events()["uploads"] == before_uploads
                assert preview.events()["submissions"] == []
            finally:
                browser.close()


def test_round_1_complete_forms_and_bound_attachments(tmp_path: Path) -> None:
    with running_preview(tmp_path, 2) as p:
        p.seed("Will you now or in the future require visa sponsorship?", "Yes", {"country": "CHE"})
        items = p.prepare(["CHE", "CHE"])
        p.post("resume", controller=p.controller)
        state = p.wait(lambda s: all(j["status"] == "ready_for_review" for j in s["jobs"]))
        assert state["input_items"] == []
        assert len(p.events()["uploads"]) == 2
        assert {e["sha256"] for e in p.events()["uploads"]} == {
            hashlib.sha256(base64.b64decode(i["file_base64"])).hexdigest() for i in items
        }
        assert p.events()["submissions"] == []
        assert all(
            a["status"] == "drafting" and "人工提交" in a["next_action"]
            for a in p.get("/api/state")["applications"]
        )
        p.post("review", application_id=state["jobs"][0]["application_id"])
        p.wait(lambda s: s["jobs"][0]["handed_off"])
        p.post("pause", controller=p.controller)
        assert p.get("/api/worker/state")["jobs"][0]["page_open"]
        p.report(
            "round-1-complete",
            state,
            [
                "independent_process",
                "field_readback",
                "per_job_file_digest",
                "zero_final_actions",
                "manual_handoff",
                "pause_retains_page",
            ],
        )


def test_round_2_missing_answer_scope_reuse_and_pause(tmp_path: Path) -> None:
    with running_preview(tmp_path, 3) as p:
        p.seed("Will you now or in the future require visa sponsorship?", "No", {"country": "USA"})
        p.prepare(["CHE", "CHE", "USA"])
        p.post("resume", controller=p.controller)
        state = p.wait(
            lambda s: (
                [j["status"] for j in s["jobs"]]
                == ["needs_input", "needs_input", "ready_for_review"]
            )
        )
        assert len(state["input_items"]) == 1
        assert len(state["input_items"][0]["jobs"]) == 2
        p.post("pause", controller=p.controller)
        uploads_before = len(p.events()["uploads"])
        p.post(
            "answer",
            application_id=state["jobs"][0]["application_id"],
            question_id="sponsorship",
            value="Yes",
            scope={"country": "CHE"},
        )
        paused = p.get("/api/worker/state")
        assert paused["control"] == "paused"
        assert [j["status"] for j in paused["jobs"]] == ["queued", "queued", "ready_for_review"]
        time.sleep(0.6)
        assert len(p.events()["uploads"]) == uploads_before
        p.post("resume", controller=p.controller)
        state = p.wait(lambda s: all(j["status"] == "ready_for_review" for j in s["jobs"]))
        assert state["input_items"] == [] and len(p.events()["uploads"]) == 3
        sponsor = next(r for r in p.store.library() if r["scope"] == {"country": "CHE"})
        p.post("library", key=sponsor["key"], revision=digest(sponsor), value="No")
        changed = p.wait(
            lambda s: (
                [j["status"] for j in s["jobs"]]
                == ["needs_recheck", "needs_recheck", "ready_for_review"]
            )
        )
        assert len(p.events()["uploads"]) == 3
        assert p.events()["submissions"] == []
        p.report(
            "round-2-answer-loop",
            changed,
            [
                "unknown_only_pauses_one_job",
                "equivalent_phrasings_group",
                "country_scope",
                "saved_while_paused_no_browser_action",
                "automatic_waiting_resume",
                "answer_revision_invalidates_handoff",
            ],
        )


def test_round_3_conflict_single_worker_crash_and_ui_heartbeat_gap(tmp_path: Path) -> None:
    with running_preview(tmp_path, 2) as p:
        p.seed("Will you now or in the future require visa sponsorship?", "Yes", {"country": "CHE"})
        p.prepare(["CHE", "CHE"])
        second = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parents[1] / "scripts/run_application_worker.py"),
                "--applications",
                str(p.store.applications.root),
                "--runtime",
                str(p.store.root),
                "--fixture-origin",
                p.worker.fixture_origin,
                "--headless",
            ],
            capture_output=True,
            timeout=15,
        )
        assert second.returncode == 3 and b"worker_already_running" in second.stdout
        first = p.store.load()["jobs"][0]
        p.store.applications.update_application(
            first["application_id"], {"notes": "Synthetic concurrent edit"}, first["revision"]
        )
        p.post("resume", controller=p.controller)
        state = p.wait(
            lambda s: [j["status"] for j in s["jobs"]] == ["needs_recheck", "ready_for_review"]
        )
        assert (
            len(p.events()["uploads"]) == 1
            and state["jobs"][0]["sync_error"] == "revision-conflict"
        )
        p.post("retry-sync", application_id=first["application_id"])
        assert len(p.events()["uploads"]) == 1
        assert (
            "Synthetic concurrent edit"
            in p.store.applications.get_application(first["application_id"])["notes"]
        )
        p.post(
            "recheck",
            application_id=first["application_id"],
            acknowledge=True,
            reclaim=True,
            handoff_source="Synthetic current handoff and history verified",
        )
        state = p.wait(lambda s: all(j["status"] == "ready_for_review" for j in s["jobs"]))
        assert len(p.events()["uploads"]) == 2
        p.post("review", application_id=first["application_id"])
        p.wait(lambda s: s["jobs"][0]["handed_off"])
        stop_worker(p)
        p.worker.spawn()
        state = p.wait(
            lambda s: (
                s["control"] == "paused" and all(j["status"] == "needs_recheck" for j in s["jobs"])
            )
        )
        assert len(p.events()["uploads"]) == 2
        p.post(
            "recheck",
            application_id=first["application_id"],
            acknowledge=True,
            reclaim=True,
            handoff_source="Synthetic current handoff and history verified",
        )
        p.wait(lambda s: not s["jobs"][0]["handed_off"] and s["jobs"][0]["status"] == "queued")
        p.post("resume", controller=p.controller)
        with p.store.applications.write_lock():
            persisted = p.store.load()
            persisted["heartbeat_at"] = time.time() - 86400
            p.store.save(persisted)
        state = p.wait(lambda s: s["jobs"][0]["reason"] == "recovered_result_not_visible")
        assert state["control"] == "running"
        assert state["worker_error"] == ""
        assert time.time() - state["heartbeat_at"] > state["lease_seconds"]
        assert state["jobs"][0]["status"] == "needs_recheck"
        assert len(p.events()["uploads"]) == 2
        p.post("cancel", controller=p.controller)
        assert all(j["status"] == "cancelled" for j in p.get("/api/worker/state")["jobs"])
        assert p.events()["submissions"] == []
        p.report(
            "round-3-recovery",
            state,
            [
                "single_execution_lock",
                "note_revision_conflict",
                "sync_only_retry",
                "explicit_recheck",
                "restart_pauses_without_reupload",
                "healthy_worker_without_ui_heartbeat",
                "unverified_recovery_does_not_reupload",
                "cancellation",
                "zero_final_actions",
            ],
        )


def test_page_capacity_release_does_not_discard_other_jobs(tmp_path: Path) -> None:
    with running_preview(tmp_path, 4) as p:
        p.seed("Will you now or in the future require visa sponsorship?", "Yes", {"country": "CHE"})
        p.prepare(["CHE"] * 4)
        p.post("resume", controller=p.controller)
        state = p.wait(
            lambda s: [j["status"] for j in s["jobs"]] == ["ready_for_review"] * 3 + ["queued"]
        )
        assert state["jobs"][3]["reason"] == "page_capacity"
        first = state["jobs"][0]["application_id"]
        p.post("review", application_id=first)
        p.wait(lambda s: s["jobs"][0]["handed_off"])
        p.post("release", application_id=first)
        state = p.wait(lambda s: s["jobs"][3]["status"] == "ready_for_review")
        assert state["jobs"][0]["status"] == "needs_recheck"
        assert len(p.events()["uploads"]) == 4 and p.events()["submissions"] == []


def test_file_change_stops_before_any_upload(tmp_path: Path) -> None:
    with running_preview(tmp_path, 1) as p:
        p.seed("Will you now or in the future require visa sponsorship?", "Yes", {"country": "CHE"})
        p.prepare(["CHE"])
        state = p.store.load()
        Path(state["jobs"][0]["file_path"]).write_bytes(b"%PDF-1.4 Different unselected version")
        p.post("resume", controller=p.controller)
        state = p.wait(lambda s: s["jobs"][0]["status"] == "needs_recheck")
        assert state["jobs"][0]["reason"] == "file_changed"
        assert p.events()["uploads"] == [] and p.events()["submissions"] == []


def test_backend_exit_pauses_detached_worker_and_retains_page(tmp_path: Path) -> None:
    with running_preview(tmp_path, 2) as p:
        p.seed("Will you now or in the future require visa sponsorship?", "No", {"country": "USA"})
        p.prepare(["CHE", "USA"])
        p.post("resume", controller=p.controller)
        p.wait(lambda s: [j["status"] for j in s["jobs"]] == ["needs_input", "ready_for_review"])
        original_pid = p.worker.process.pid
        original_origin = p.worker.fixture_origin
        with p.store.applications.write_lock():
            state = p.store.load()
            state["lease_seconds"] = 0.5
            state["heartbeat_at"] = time.time()
            p.store.save(state)
        p.server.shutdown()
        p.server.worker_fixtures.shutdown()
        p.server.worker_fixtures.server_close()
        until = time.monotonic() + 5
        while time.monotonic() < until:
            state = p.store.load()
            if state["control"] == "paused":
                break
            time.sleep(0.1)
        assert state["control"] == "paused"
        assert state["jobs"][0]["page_open"]
        assert p.worker.process.poll() is None
        # Restore the normal lease before resuming. The short lease simulated disconnection.
        with p.store.applications.write_lock():
            persisted = p.store.load()
            persisted["lease_seconds"] = 60
            p.store.save(persisted)
        server = create_server(
            p.store.applications.root,
            tmp_path / "career",
            write_admission_policy="development",
            port=0,
            worker_root=p.store.root,
            worker_fixtures=True,
            worker_headless=True,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            restored = Preview(server, tmp_path)
            assert restored.worker.fixture_origin == original_origin
            restored.post("resume", controller="restored-control-window")
            restored.post(
                "answer",
                application_id=state["jobs"][0]["application_id"],
                question_id="sponsorship",
                value="Yes",
                scope={"country": "CHE"},
            )
            complete = restored.wait(
                lambda s: all(j["status"] == "ready_for_review" for j in s["jobs"])
            )
            assert complete["worker_pid"] == original_pid
            assert len(restored.events()["uploads"]) == 2
            assert restored.events()["submissions"] == []
        finally:
            server.shutdown()
            thread.join(10)
            server.server_close()
            server.worker_fixtures.shutdown()
            server.worker_fixtures.server_close()
