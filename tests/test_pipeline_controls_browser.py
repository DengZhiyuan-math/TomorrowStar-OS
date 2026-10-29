"""Local service failures do not hide the current pipeline or its stop control."""

import pytest
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_job_explanation_browser import reveal_control
from test_portal_workflow_browser import browser_page as browser_page
from test_worker_backend_recovery import backend as backend

pytestmark = pytest.mark.worker_browser


def pipeline_state(**updates):
    return {
        "enabled": True,
        "control": "paused",
        "status": "idle",
        "active_task_id": None,
        "items": [],
        **updates,
    }


@pytest.mark.parametrize(
    "control,status,button_id",
    [
        ("paused", "needs_input", "flow-pipeline-start"),
        ("running", "waiting_for_mail", "flow-pipeline-pause"),
    ],
)
@pytest.mark.parametrize("notice_change", [False, True])
def test_pipeline_poll_retains_keyboard_control(
    portal, browser_page, control, status, button_id, notice_change
):
    from playwright.sync_api import expect

    page = browser_page
    reads = []

    def read(route):
        reads.append(len(reads) + 1)
        route.fulfill(
            json=pipeline_state(
                id="synthetic-pipeline",
                control=control,
                status=status,
                updated_at=reads[-1],
                notification={"message": "Captured recommendations: " + str(reads[-1])}
                if notice_change
                else None,
            )
        )

    page.route("**/api/pipeline/state", read)
    page.goto(portal.origin + "/#flow")
    control_button = page.locator("#" + button_id)
    expect(control_button).to_be_enabled()
    control_button.focus()
    page.evaluate("window.syntheticPipelineControl = document.activeElement")
    page.clock.install()
    with page.expect_response("**/api/pipeline/state"):
        page.clock.fast_forward(1500)
    expect(control_button).to_be_focused()
    if not notice_change:
        assert page.evaluate("window.syntheticPipelineControl.isConnected")
    assert len(reads) >= 2


def test_invalid_cli_shows_local_repair_without_hiding_saved_data(
    portal, browser_page, tmp_path, monkeypatch
):
    from playwright.sync_api import expect

    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(tmp_path / "missing-codex"))
    with _running_portal(
        portal.applications, portal.career, flow_root=tmp_path / "flow"
    ) as instance:
        page = browser_page
        page.goto(instance.origin + "/#flow")
        expect(page.locator("#flow-task")).to_contain_text("可执行文件不可用")
        expect(page.locator("#flow-task")).to_contain_text("TOMORROWSTAR_CODEX_EXECUTABLE")
        expect(page.locator("#flow-task")).to_contain_text("--codex-executable")
        expect(page.locator("#flow-manual")).to_be_enabled()
        expect(page.locator("#flow-observe")).to_be_enabled()
        assert instance.state()["applications"] == portal.state()["applications"]


def test_history_view_can_rejoin_and_keep_following_current_job(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    state = portal.state()
    state["applications"] = [
        {
            "id": name,
            "company": name,
            "role_title": "Engineer",
            "status": "drafting",
            "revision": name,
        }
        for name in ("Historical", "Current", "Next")
    ]
    tasks = [
        {
            "id": "task-" + name,
            "application_id": name,
            "status": "draft",
            "revision": name,
            "job_description": "Saved JD for " + name,
            "stages": {"analysis": {"status": "pending"}, "resume": {"status": "pending"}},
        }
        for name in ("Historical", "Current", "Next")
    ]
    pipeline = pipeline_state(id="synthetic-pipeline", active_task_id="task-Current")
    reads, writes = [], []

    def read(route):
        target = route.request.url.rsplit("/", 1)[-1]
        reads.append(target)
        route.fulfill(
            json={
                "enabled": True,
                "mode": "application",
                "tasks": tasks,
                "active_task": next(
                    task
                    for task in tasks
                    if task["id"] == (target if target != "state" else "task-Current")
                ),
            }
        )

    page.on(
        "request", lambda request: writes.append(request.url) if request.method == "POST" else None
    )
    page.route("**/api/state", lambda route: route.fulfill(json=state))
    page.route("**/api/pipeline/state", lambda route: route.fulfill(json=pipeline))
    page.route("**/api/flow/*", read)
    page.goto(portal.origin + "/#flow")
    expect(page.locator("#flow-task")).to_have_attribute("data-task-id", "task-Current")
    reveal_control(page, page.locator("#flow-task-list button").first)
    page.locator("#flow-task-list button").filter(has_text="Historical").click()
    expect(page.locator("#flow-task")).to_have_attribute("data-task-id", "task-Historical")
    page.locator("#flow-observe").click()
    expect(page.locator("#flow-task")).to_have_attribute("data-task-id", "task-Historical")
    page.locator("#flow-pipeline-current").click()
    expect(page.locator("#flow-task")).to_have_attribute("data-task-id", "task-Current")
    pipeline["active_task_id"] = "task-Next"
    page.locator("#flow-observe").click()
    expect(page.locator("#flow-task")).to_have_attribute("data-task-id", "task-Next")
    assert "task-Historical" in reads and "task-Next" in reads
    assert writes == []


def test_mail_read_failure_keeps_current_pipeline_and_pause_available(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    pipeline = pipeline_state(control="running", status="waiting_for_mail")
    pauses = []
    page.route("**/api/pipeline/state", lambda route: route.fulfill(json=pipeline))
    page.route(
        "**/api/recommendations/state",
        lambda route: route.fulfill(status=503, json={"message": "Synthetic mail unavailable"}),
    )

    def pause(route):
        pauses.append(route.request.post_data_json)
        pipeline.update(control="paused", status="paused")
        route.fulfill(json=pipeline)

    page.route("**/api/pipeline/pause", pause)
    page.goto(portal.origin + "/#flow")
    expect(page.locator("#flow-pipeline-pause")).to_be_enabled(timeout=2500)
    page.locator("#flow-pipeline-pause").click()
    expect(page.locator("#flow-automation")).to_contain_text("自动流程已暂停")
    expect(page.locator("#flow-observe")).to_be_enabled()
    assert pauses == [{}]


def test_unknown_start_response_still_allows_idempotent_pause(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    pipeline = pipeline_state()
    requests = []
    page.route("**/api/pipeline/state", lambda route: route.fulfill(json=pipeline))

    def start(route):
        requests.append(("start", route.request.post_data_json))
        pipeline.update(control="running", status="reading_email")
        route.abort()

    def pause(route):
        requests.append(("pause", route.request.post_data_json))
        pipeline.update(control="paused", status="paused")
        route.fulfill(json=pipeline)

    page.route("**/api/pipeline/start", start)
    page.route("**/api/pipeline/pause", pause)
    page.goto(portal.origin + "/#flow")
    page.locator("#flow-pipeline-start").click()
    expect(page.locator("#flow-notice")).to_contain_text("尚未核验")
    expect(page.locator("#flow-pipeline-pause")).to_be_enabled(timeout=2500)
    page.locator("#flow-pipeline-pause").click()
    expect(page.locator("#flow-automation")).to_contain_text("自动流程已暂停")
    assert [action for action, _payload in requests] == ["start", "pause"]
    assert requests[1][1] == {}


def test_current_pipeline_uses_one_continue_skip_and_direct_return(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    pipeline = pipeline_state(
        id="synthetic-pipeline",
        queue_mode=True,
        status="needs_input",
        current_recommendation_id="rec-one",
        items=[{"recommendation_id": "rec-one", "company": "First", "status": "needs_input"}],
    )
    actions = []
    page.route("**/api/pipeline/state", lambda route: route.fulfill(json=pipeline))

    def command(route):
        action = route.request.url.rsplit("/", 1)[-1]
        actions.append((action, route.request.post_data_json))
        if action == "continue":
            pipeline.update(control="running", status="filling")
        elif action == "skip":
            pipeline.update(
                control="running", status="selecting_job", current_recommendation_id=None
            )
            pipeline["items"][0]["status"] = "skipped"
        elif action == "return":
            pipeline.update(
                control="paused", status="needs_input", current_recommendation_id="rec-one"
            )
            pipeline["items"][0]["status"] = "needs_input"
        route.fulfill(json=pipeline)

    for action in ("continue", "skip", "return"):
        page.route(f"**/api/pipeline/{action}", command)
    page.goto(portal.origin + "/#flow")
    expect(page.locator("#flow-pipeline-start")).to_have_text("继续当前岗位")
    page.locator("#flow-pipeline-start").click()
    expect(page.locator("#flow-pipeline-skip")).to_be_enabled()
    page.locator("#flow-pipeline-skip").click()
    page.get_by_role("button", name="返回此岗位", exact=True).click()
    expect(page.locator("#flow-pipeline-start")).to_be_enabled()
    assert [action for action, _ in actions] == ["continue", "skip", "return"]
    assert actions[-1][1]["application_id"] == "rec-one"
    assert all(len(payload["request_id"]) == 32 for _, payload in actions)


def test_hung_start_times_out_without_replay_and_pause_still_works(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    pipeline = pipeline_state()
    requests = []
    page.route("**/api/pipeline/state", lambda route: route.fulfill(json=pipeline))

    def start(route):
        requests.append(("start", route.request.post_data_json))
        pipeline.update(id="pending-start", control="running", status="reading_email")
        # The local service received the request, but its response never arrives.

    def pause(route):
        requests.append(("pause", route.request.post_data_json))
        pipeline.update(control="paused", status="paused")
        route.fulfill(json=pipeline)

    page.route("**/api/pipeline/start", start)
    page.route("**/api/pipeline/pause", pause)
    page.goto(portal.origin + "/#flow")
    expect(page.locator("#flow-pipeline-start")).to_be_enabled()
    page.clock.install()
    with page.expect_request("**/api/pipeline/start"):
        page.locator("#flow-pipeline-start").click()
    page.clock.fast_forward(30001)
    expect(page.locator("#flow-notice")).to_contain_text("超时")
    expect(page.locator("#flow-notice")).to_contain_text("尚未核验")
    expect(page.locator("#flow-pipeline-pause")).to_be_enabled()
    page.locator("#flow-pipeline-pause").click()
    expect(page.locator("#flow-automation")).to_contain_text("自动流程已暂停")
    assert [action for action, _ in requests] == ["start", "pause"]


def test_stale_pipeline_read_blocks_new_work_until_readback_recovers(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    failing = False

    def read(route):
        if failing:
            route.fulfill(status=503, json={"message": "Synthetic pipeline unavailable"})
        else:
            route.fulfill(json=pipeline_state())

    page.route("**/api/pipeline/state", read)
    page.goto(portal.origin + "/#flow")
    expect(page.locator("#flow-pipeline-start")).to_be_enabled()
    failing = True
    page.locator("#flow-observe").click()
    expect(page.locator("#flow-notice")).to_contain_text("Synthetic pipeline unavailable")
    expect(page.locator("#flow-pipeline-start")).to_be_disabled()
    expect(page.locator("#flow-observe")).to_be_enabled()
    failing = False
    page.locator("#flow-observe").click()
    expect(page.locator("#flow-pipeline-start")).to_be_enabled()


def test_unknown_old_job_does_not_lock_next_job_after_explicit_skip(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    pipeline = pipeline_state(
        id="synthetic-pipeline",
        queue_mode=True,
        status="needs_input",
        current_recommendation_id="rec-one",
    )
    page.route("**/api/pipeline/state", lambda route: route.fulfill(json=pipeline))
    continues = []

    def resume(route):
        continues.append(pipeline["current_recommendation_id"])
        route.abort()

    def skip(route):
        pipeline.update(current_recommendation_id="rec-two")
        route.fulfill(json=pipeline)

    def restore(route):
        pipeline.update(current_recommendation_id="rec-one")
        route.fulfill(json=pipeline)

    pipeline["items"] = [{"recommendation_id": "rec-one", "status": "skipped"}]
    page.route("**/api/pipeline/continue", resume)
    page.route("**/api/pipeline/skip", skip)
    page.route("**/api/pipeline/return", restore)
    page.goto(portal.origin + "/#flow")
    page.locator("#flow-pipeline-start").click()
    expect(page.locator("#flow-notice")).to_contain_text("尚未核验")
    expect(page.locator("#flow-pipeline-start")).to_be_disabled()
    page.locator("#flow-pipeline-skip").click()
    expect(page.locator("#flow-pipeline-start")).to_be_enabled()
    page.get_by_role("button", name="返回此岗位", exact=True).click()
    expect(page.locator("#flow-pipeline-start")).to_be_disabled()
    assert continues == ["rec-one"]


def test_unreadable_flow_retains_answer_draft_without_autosaving(backend, browser_page):
    from threading import Thread

    from playwright.sync_api import expect

    owner, _, runner, _ = backend
    state = runner.store.load()
    state["control"] = "paused"
    state["jobs"][0].update(
        status="needs_input", questions=[{"id": "start", "question": "Start date", "options": []}]
    )
    runner.store.save(state)
    thread = Thread(target=owner.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        page = browser_page
        page.goto(f"http://127.0.0.1:{owner.server_port}/#flow")
        answer = page.get_by_label("Start date · 补充信息")
        expect(answer).to_be_visible()
        writes = []
        page.on(
            "request",
            lambda request: (
                writes.append(request)
                if request.url.endswith("/api/flow/worker-action") and request.method == "POST"
                else None
            ),
        )
        page.route(
            "**/api/flow/*",
            lambda route: (
                route.fulfill(status=503, json={"message": "Synthetic flow unreadable"})
                if route.request.method == "GET"
                else route.continue_()
            ),
        )
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-notice")).to_contain_text("Synthetic flow unreadable")
        answer.fill("2026-11-01")
        page.locator("#flow-title").click()
        expect(answer).to_have_value("2026-11-01")
        assert not writes
        assert not runner.store.library()
        page.unroute("**/api/flow/*")
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-notice")).to_contain_text("已自动保存到信息库")
        assert len(writes) == 1
        assert runner.store.library()[0]["value"] == "2026-11-01"
        assert runner.store.load()["control"] == "paused"
    finally:
        owner.shutdown()
        thread.join(3)
