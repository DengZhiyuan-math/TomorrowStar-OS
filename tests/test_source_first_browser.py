"""Source intake and application review use synthetic loopback inputs only."""

import pytest
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_job_explanation_browser import reveal_control
from test_portal_workflow_browser import browser_page as browser_page

pytestmark = pytest.mark.worker_browser


@pytest.fixture(autouse=True)
def manual_flow_controls(browser_page):
    # These journeys exercise the public manual controls independently of the
    # automatic queue, which otherwise puts legacy stage controls in diagnostics.
    browser_page.route(
        "**/api/pipeline/state", lambda route: route.fulfill(json={"enabled": False})
    )


def test_new_opportunity_pastes_source_and_saves_without_manual_fields(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    received = []
    job = {
        "request_id": "a" * 32,
        "status": "saved",
        "application_id": "b" * 24,
        "fields": {
            "company": "Synthetic Labs",
            "role_title": "Systems Engineer",
            "location": "Zurich",
        },
        "missing_fields": ["salary"],
        "source_kind": "pasted_text",
    }
    source = "Synthetic Labs\nSystems Engineer\nLocation: Zurich\nBuild reliable Python services."
    with _running_portal(portal.applications, portal.career) as instance:

        def ingest(route):
            received.append(route.request.post_data_json)
            job["request_id"] = received[-1]["request_id"]
            route.fulfill(json={"job": job, "status": "complete"})

        page.route("**/api/intake/ingest", ingest)
        page.route(
            "**/api/intake/state",
            lambda route: route.fulfill(json={"job": job, "status": "complete"}),
        )
        page.goto(instance.origin + "/#applications")
        page.locator("#add-application").click()
        dialog = page.locator("#source-intake-dialog")
        expect(dialog).to_be_visible()
        expect(dialog.get_by_label("JD 原文或岗位链接")).to_be_visible()
        expect(dialog.get_by_label("JD 原文或岗位链接")).to_be_focused()
        expect(dialog.locator('[name="company"]')).to_have_count(0)
        dialog.get_by_label("JD 原文或岗位链接").fill(source)
        dialog.get_by_role("button", name="自动整理并保存", exact=True).click()
        expect(dialog.locator("#source-intake-result")).to_contain_text("已保存")
        expect(dialog.locator("#source-intake-result")).to_contain_text("Synthetic Labs")
        expect(dialog.locator("#source-intake-result")).to_contain_text("Zurich")
        expect(dialog.locator("#source-intake-result")).to_contain_text("薪资")
        dialog.get_by_text("查看原文与来源", exact=True).click()
        expect(dialog.locator("#source-intake-result")).to_contain_text(source)
        assert len(received) == 1
        assert received[0]["text"] == source and "url" not in received[0]
        assert len(received[0]["request_id"]) == 32


def test_start_uses_business_api_and_keeps_diagnostics_collapsed(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect
    from test_application_flow_browser import flow_portal, prepare_browser_worker

    page = browser_page
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch, prepare=False)
        expect(page.locator("#flow-check-runtime-readiness")).not_to_be_visible()
        expect(page.locator("#flow-worker-diagnostics")).not_to_have_attribute("open", "")
        expect(page.locator("#flow-start-filling")).to_be_disabled()
        page.get_by_label("此岗位的申请国家").select_option("CHE")
        page.locator("#flow-send-confirmed").check()
        requests = []
        page.on("request", lambda request: requests.append((request.method, request.url)))
        page.locator("#flow-start-filling").click()
        expect(page.locator("#flow-worker")).to_contain_text("填写运行中")
        assert starts == ["spawn"]
        actions = [(method, url.rsplit("/", 1)[-1]) for method, url in requests]
        prepare_index = actions.index(("POST", "prepare-worker"))
        resume_index = actions.index(("POST", "worker-action"))
        assert not any("/readiness/" in url for method, url in requests if method == "GET")
        assert prepare_index < resume_index
        assert service.store.load()["control"] == "running"


def test_unknown_intake_reconciles_locally_without_reingesting_source(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    writes = []
    running = {
        "request_id": "a" * 32,
        "status": "needs_recheck",
        "fields": {},
        "missing_fields": [],
    }
    saved = running | {
        "status": "saved",
        "fields": {"company": "Recovered Synthetic", "role_title": "Engineer"},
    }
    with _running_portal(portal.applications, portal.career) as instance:

        def ingest(route):
            writes.append(route.request.url)
            running["request_id"] = route.request.post_data_json["request_id"]
            saved["request_id"] = running["request_id"]
            route.fulfill(json={"job": running})

        def reconcile(route):
            writes.append(route.request.url)
            route.fulfill(json={"job": saved})

        page.route("**/api/intake/state", lambda route: route.fulfill(json={"job": None}))
        page.route("**/api/intake/ingest", ingest)
        page.route("**/api/intake/reconcile", reconcile)
        page.goto(instance.origin + "/#applications")
        page.locator("#add-application").click()
        page.get_by_label("JD 原文或岗位链接").fill("https://jobs.synthetic.example/engineer")
        page.locator("#source-intake-submit").click()
        expect(page.locator("#source-intake-submit")).to_be_disabled()
        page.locator("#source-intake-recheck").click()
        expect(page.locator("#source-intake-result")).to_contain_text("Recovered Synthetic")
        assert writes == [
            instance.origin + "/api/intake/ingest",
            instance.origin + "/api/intake/reconcile",
        ]


def test_reopened_intake_observes_pending_save_without_starting_another(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    pending = {
        "request_id": "a" * 32,
        "status": "needs_recheck",
        "fields": {},
        "missing_fields": [],
    }
    writes = []
    with _running_portal(portal.applications, portal.career) as instance:
        page.route("**/api/intake/state", lambda route: route.fulfill(json={"job": pending}))
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "POST" else None,
        )
        page.goto(instance.origin + "/#applications")
        page.locator("#add-application").click()
        expect(page.locator("#source-intake-status")).to_contain_text("保存结果待核验")
        expect(page.locator("#source-intake-submit")).to_be_disabled()
        expect(page.locator("#source-intake-input")).to_be_disabled()
        assert writes == []


def test_native_start_uses_current_materials_without_requesting_host_diagnostics(
    portal, tmp_path, browser_page, monkeypatch
):
    import time

    from playwright.sync_api import expect
    from test_application_flow_browser import flow_portal, prepare_browser_worker
    from test_installed_readiness_browser import readiness_receipt

    page = browser_page
    page.add_init_script(
        "window.__checks = []; window.webkit = {messageHandlers: {tomorrowstarNative: {"
        "postMessage(value) { window.__checks.push(value); }}}};"
    )
    writes, reads = [], []
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch, prepare=False)

        def readiness(route):
            reads.append(route.request.url)
            task = instance.server.application_flow_service.snapshot()["active_task"]
            receipt = readiness_receipt(task["revision"])
            receipt["checked_at"] = time.time()
            receipt["worker"]["run_id"] = service.snapshot().get("runtime", {}).get("id")
            route.fulfill(json=receipt)

        page.route("**/api/flow/readiness/*", readiness)
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "POST" else None,
        )
        page.get_by_label("此岗位的申请国家").select_option("CHE")
        page.locator("#flow-send-confirmed").check()
        page.locator("#flow-start-filling").click()
        expect(page.locator("#flow-worker")).to_contain_text("填写运行中")
        assert starts == ["spawn"]
        assert [url.rsplit("/", 1)[-1] for url in writes] == ["prepare-worker", "worker-action"]
        assert reads == [] and page.evaluate("window.__checks") == []
        assert service.store.load()["control"] == "running"


@pytest.mark.parametrize("error_code", ["intake_extraction_failed", "unknown_native_code"])
def test_failed_intake_explains_recovery_and_keeps_codes_in_diagnostics(
    portal, browser_page, error_code
):
    from playwright.sync_api import expect

    page = browser_page
    with _running_portal(portal.applications, portal.career) as instance:
        page.route("**/api/intake/state", lambda route: route.fulfill(json={"job": None}))

        def failed(route):
            route.fulfill(
                json={
                    "job": {
                        "request_id": route.request.post_data_json["request_id"],
                        "status": "failed",
                        "fields": {},
                        "missing_fields": [],
                        "error_code": error_code,
                    }
                }
            )

        page.route("**/api/intake/ingest", failed)
        page.goto(instance.origin + "/#applications")
        page.locator("#add-application").click()
        page.get_by_label("JD 原文或岗位链接").fill("Synthetic incomplete source")
        page.locator("#source-intake-submit").click()
        expect(page.locator("#source-intake-status")).to_contain_text("来源已保留")
        assert error_code not in page.locator("#source-intake-status").inner_text()
        page.locator("#source-intake-diagnostics > summary").click()
        expect(page.locator("#source-intake-diagnostics")).to_contain_text(error_code)


def test_reconciled_pre_save_interruption_requires_a_new_explicit_import(portal, browser_page):
    from playwright.sync_api import expect

    page = browser_page
    ingests = []
    with _running_portal(portal.applications, portal.career) as instance:
        page.route("**/api/intake/state", lambda route: route.fulfill(json={"job": None}))

        def ingest(route):
            payload = route.request.post_data_json
            ingests.append(payload)
            route.fulfill(
                json={
                    "job": {
                        "request_id": payload["request_id"],
                        "status": "needs_recheck" if len(ingests) == 1 else "saved",
                        "fields": {"job_description": payload["text"]},
                        "missing_fields": [],
                    }
                }
            )

        def reconcile(route):
            route.fulfill(
                json={
                    "job": {
                        "request_id": route.request.post_data_json["request_id"],
                        "status": "failed",
                        "error_code": "intake_interrupted_before_save",
                        "fields": {"job_description": ingests[0]["text"]},
                        "missing_fields": [],
                    }
                }
            )

        page.route("**/api/intake/ingest", ingest)
        page.route("**/api/intake/reconcile", reconcile)
        page.goto(instance.origin + "/#applications")
        page.locator("#add-application").click()
        page.get_by_label("JD 原文或岗位链接").fill("Synthetic source retained across interruption")
        page.locator("#source-intake-submit").click()
        expect(page.locator("#source-intake-submit")).to_be_disabled()
        page.locator("#source-intake-recheck").click()
        expect(page.locator("#source-intake-submit")).to_be_enabled()
        assert len(ingests) == 1
        page.locator("#source-intake-submit").click()
        expect(page.locator("#source-intake-result")).to_contain_text("已保存")
        assert len(ingests) == 2
        assert ingests[0]["request_id"] != ingests[1]["request_id"]


def test_conflicting_new_source_blocks_selection_and_removes_pending_batch_choice(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    page = browser_page
    row = {
        "id": "a" * 32,
        "revision": "b" * 64,
        "company": "Conflicting Synthetic",
        "role_title": "Engineer",
        "job_description": "Changed source JD stays available for review.",
        "jd_completeness": "full",
        "acquisition_status": "available",
        "acquisition_checkpoint": "complete",
        "selection_status": "saved",
        "existing_application": {"id": "c" * 24, "status": "drafting"},
    }
    snapshot = {"enabled": True, "status": "complete", "recommendations": [row]}
    writes = []
    with _running_portal(
        portal.applications, portal.career, flow_root=tmp_path / "flow", preparation_only=True
    ) as instance:
        page.route("**/api/recommendations/state", lambda route: route.fulfill(json=snapshot))
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "POST" else None,
        )
        page.goto(instance.origin + "/#flow")
        card = page.locator("#flow-candidates .flow-recommendation")
        management = page.locator(f'[data-recommendation-settings="{row["id"]}"]')
        check = management.get_by_role("checkbox", name="加入材料批次")
        reveal_control(page, management.locator('input[type="checkbox"]'))
        check.check()
        expect(page.locator("#flow-batch-selection-count")).to_contain_text("已勾选 1 个岗位")
        row["selection_status"] = "source_conflict"
        snapshot.update(status="partial", error_code="recommendation_source_conflict")
        page.locator("#flow-observe").click()
        expect(card).to_contain_text("新来源与已有记录冲突")
        expect(card.get_by_role("button", name="打开已有申请任务")).to_be_disabled()
        expect(check).to_be_disabled()
        expect(check).not_to_be_checked()
        expect(page.locator("#flow-batch-selection-count")).to_contain_text("已勾选 0 个岗位")
        expect(page.locator("#flow-batch-create")).to_be_disabled()
        management.get_by_text("邮件与 JD 来源", exact=True).click()
        expect(management).to_contain_text("Changed source JD stays available for review.")
        assert writes == []


@pytest.mark.parametrize("control", ["running", "paused"])
def test_answer_saves_without_refreshing_native_diagnostics_in_either_control_state(
    portal, tmp_path, browser_page, monkeypatch, control
):
    import time

    from playwright.sync_api import expect
    from test_application_flow_browser import flow_portal, prepare_browser_worker
    from test_installed_readiness_browser import readiness_receipt

    page = browser_page
    page.add_init_script(
        "window.__checks = []; window.webkit = {messageHandlers: {tomorrowstarNative: {"
        "postMessage(value) { window.__checks.push(value); }}}};"
    )
    writes = []
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        state.update(control=control, controller="synthetic-controller")
        state["jobs"][0].update(
            status="needs_input",
            questions=[{"id": "start", "question": "Start date", "options": []}],
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        expect(page.get_by_label("Start date · 补充信息")).to_be_visible()

        def readiness(route):
            task = instance.server.application_flow_service.snapshot()["active_task"]
            receipt = readiness_receipt(task["revision"])
            receipt["checked_at"] = time.time()
            receipt["worker"]["run_id"] = service.snapshot().get("runtime", {}).get("id")
            receipt["native_host"] = {
                "state": "verified" if page.evaluate("window.__checks.length") else "unknown",
                "reason": "native_receipt_stale",
                "captured_at": time.time()
                if page.evaluate("window.__checks.length")
                else time.time() - 31,
            }
            route.fulfill(json=receipt)

        page.route("**/api/flow/readiness/*", readiness)
        page.on(
            "request",
            lambda request: (
                writes.append(request.post_data_json)
                if request.method == "POST" and request.url.endswith("/worker-action")
                else None
            ),
        )
        page.get_by_label("Start date · 补充信息").fill("2026-11-01")
        page.locator("#flow-title").click()
        expect(page.locator("#flow-notice")).to_contain_text("已自动保存到信息库")
        assert [row["operation"] for row in writes] == ["answer"]
        assert page.evaluate("window.__checks.length") == 0
        assert service.store.load()["control"] == control and starts == []


def test_running_answer_with_unknown_native_diagnostic_saves_through_real_api(
    portal, tmp_path, browser_page, monkeypatch
):
    from playwright.sync_api import expect
    from test_application_flow_browser import flow_portal, prepare_browser_worker
    from test_installed_readiness_browser import readiness_receipt

    page = browser_page
    page.add_init_script(
        "window.webkit = {messageHandlers: {tomorrowstarNative: {postMessage() {}}}};"
    )
    writes = []
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        state = service.store.load()
        state.update(control="running", controller="synthetic-controller")
        state["jobs"][0].update(
            status="needs_input",
            questions=[{"id": "start", "question": "Start date", "options": []}],
        )
        service.store.save(state)
        page.locator("#flow-observe").click()
        expect(page.get_by_label("Start date · 补充信息")).to_be_visible()
        revision = instance.server.application_flow_service.snapshot()["active_task"]["revision"]
        page.route(
            "**/api/flow/readiness/*", lambda route: route.fulfill(json=readiness_receipt(revision))
        )
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "POST" else None,
        )
        page.get_by_label("Start date · 补充信息").fill("2026-11-01")
        page.locator("#flow-title").click()
        expect(page.locator("#flow-notice")).to_contain_text("已自动保存到信息库")
        assert [url.rsplit("/", 1)[-1] for url in writes] == ["worker-action"]
        assert starts == []
        assert service.store.load()["control"] == "running"
        assert service.store.library()[0]["value"] == "2026-11-01"


@pytest.mark.parametrize("outcome", ["captured", "unknown", "changed"])
def test_explicit_resume_observes_the_same_retained_page_before_one_resume(
    portal, tmp_path, browser_page, monkeypatch, outcome
):
    import time

    from playwright.sync_api import expect
    from test_application_flow_browser import flow_portal, prepare_browser_worker
    from test_installed_readiness_browser import readiness_receipt

    page = browser_page
    actions, readiness_reads = [], []
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        snapshot = instance.server.application_flow_service.snapshot()
        snapshot["worker"] = service.snapshot()
        task = snapshot["active_task"]
        target = {"batch_id": "batch-one", "run_id": "retained-run", "page_id": "exact-page"}
        snapshot["worker"]["runtime"] = {"id": target["run_id"]}
        job = snapshot["worker"]["jobs"][0]
        job.update(
            status="needs_input",
            page_open=True,
            page_current=True,
            page_observation={"page_id": target["page_id"], "at": time.time()},
            page_inspection_target=target.copy(),
            owned_page_inspection={
                "request_id": "a" * 32,
                "status": "captured",
                "binding": target.copy(),
                "at": time.time() - 60,
            },
            owned_page_inspection_state="historical",
        )
        pending_reads = 0

        def flow_state(route):
            nonlocal pending_reads
            if actions == ["observe-page"]:
                pending_reads += 1
                if pending_reads >= 2:
                    job["owned_page_inspection"]["status"] = "captured"
                    job["owned_page_inspection"]["at"] = time.time()
                    job["owned_page_inspection_state"] = (
                        "current" if outcome != "unknown" else "unknown"
                    )
                    if outcome == "changed":
                        job["page_inspection_target"] = target | {"page_id": "another-page"}
            route.fulfill(json=snapshot)

        def action(route):
            payload = route.request.post_data_json
            actions.append(payload["operation"])
            if payload["operation"] == "observe-page":
                assert payload["payload"] == {
                    "application_id": task["application_id"],
                    "binding": target,
                }
                job["owned_page_inspection"] = {
                    "request_id": "b" * 32,
                    "status": "pending",
                    "binding": target.copy(),
                }
                job["owned_page_inspection_state"] = "pending"
            elif payload["operation"] == "resume":
                snapshot["worker"]["control"] = "running"
            route.fulfill(json=task)

        def readiness(route):
            readiness_reads.append(job["owned_page_inspection_state"])
            receipt = readiness_receipt(task["revision"])
            receipt["worker"]["run_id"] = target["run_id"]
            route.fulfill(json=receipt)

        page.route("**/api/flow/" + task["id"], flow_state)
        page.route("**/api/flow/worker-action", action)
        page.route("**/api/flow/readiness/*", readiness)
        page.locator("#flow-observe").click()
        expect(page.locator("#flow-worker-resume")).to_be_enabled()
        page.locator("#flow-worker-resume").click()
        if outcome == "captured":
            expect(page.locator("#flow-worker")).to_contain_text("填写运行中")
            assert actions == ["observe-page", "resume"]
            assert readiness_reads == []
        else:
            expect(page.locator("#flow-notice")).to_contain_text("原页面", timeout=10000)
            assert actions == ["observe-page"]
            assert readiness_reads == []
            assert snapshot["worker"]["control"] == "paused"
        assert starts == []
        assert service.snapshot()["control"] == "paused"


@pytest.mark.parametrize("diagnostic", ["unknown", "stale"])
def test_healthy_resume_posts_real_api_without_native_diagnostic_admission(
    portal, tmp_path, browser_page, monkeypatch, diagnostic
):
    import time

    from playwright.sync_api import expect
    from test_application_flow_browser import flow_portal, prepare_browser_worker
    from test_installed_readiness_browser import readiness_receipt

    page = browser_page
    page.add_init_script(
        "window.__checks = []; window.webkit = {messageHandlers: {tomorrowstarNative: {"
        "postMessage(value) {window.__checks.push(value);}}}};"
    )
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch)
        writes, reads = [], []

        def readiness(route):
            reads.append(route.request.url)
            task = instance.server.application_flow_service.snapshot()["active_task"]
            receipt = readiness_receipt(task["revision"])
            if diagnostic == "stale":
                receipt["native_host"] = {"state": "verified", "captured_at": time.time() - 31}
                receipt["checked_at"] = time.time() - 11
            route.fulfill(json=receipt)

        page.route("**/api/flow/readiness/*", readiness)
        page.on(
            "request",
            lambda request: (
                writes.append(request.post_data_json["operation"])
                if request.method == "POST" and request.url.endswith("/api/flow/worker-action")
                else None
            ),
        )
        page.locator("#flow-worker-resume").click()
        expect(page.locator("#flow-worker")).to_contain_text("填写运行中", timeout=6000)
        assert writes == ["resume"]
        assert starts == ["spawn"] and service.store.load()["control"] == "running"
        assert reads == [] and page.evaluate("window.__checks") == []


def test_valid_native_proof_is_reused_without_leaving_an_async_check_running(
    portal, tmp_path, browser_page, monkeypatch
):
    import time

    from playwright.sync_api import expect
    from test_application_flow_browser import flow_portal, prepare_browser_worker
    from test_installed_readiness_browser import readiness_receipt

    page = browser_page
    page.add_init_script(
        "window.__checks = []; window.webkit = {messageHandlers: {tomorrowstarNative: {"
        "postMessage(value) {window.__checks.push(value);}}}};"
    )
    with flow_portal(portal, tmp_path, worker=True) as (instance, _):
        service, starts = prepare_browser_worker(page, instance, monkeypatch, prepare=False)
        captured = time.time()

        def readiness(route):
            snapshot = instance.server.application_flow_service.snapshot()
            task = snapshot["active_task"]
            receipt = readiness_receipt(task["revision"])
            receipt["native_host"] = {"state": "verified", "captured_at": captured}
            receipt["worker"]["run_id"] = service.snapshot().get("runtime", {}).get("id")
            route.fulfill(json=receipt)

        page.route("**/api/flow/readiness/*", readiness)
        page.get_by_label("此岗位的申请国家").select_option("CHE")
        page.locator("#flow-send-confirmed").check()
        page.locator("#flow-start-filling").click()
        expect(page.locator("#flow-worker")).to_contain_text("填写运行中")
        assert page.evaluate("window.__checks") == []
        assert starts == ["spawn"]
