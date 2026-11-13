"""The real intake store drives one current job and continues capture while waiting."""

import time
from copy import deepcopy

import pytest
from test_application_intake import message, page, ready
from test_application_pipeline import Flow, Worker

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.career_portal_data import ApplicationStore


@pytest.fixture
def queue_environment(tmp_path):
    (tmp_path / "applications").mkdir()
    apps = ApplicationStore(tmp_path / "applications")
    reads, fetches = [], []
    messages = [
        message(f"mail-{index}", [f"https://www.linkedin.com/jobs/view/{10000 + index}"])
        for index in range(16)
    ]

    def reader(_directory, **options):
        token = options.get("page_token")
        offset = int(token or 0)
        reads.append(token)
        return {
            "status": "readable",
            "emails": messages[offset : offset + 3],
            "provenance": {
                "next_page_token": str(offset + 3) if offset + 3 < len(messages) else None
            },
        }

    def fetcher(url):
        fetches.append(url)
        return page(url) | {
            "job_fields": {
                "title": "Systems Engineer",
                "company": "Synthetic Labs",
                "location": "Zurich, Switzerland",
            }
        }

    intake = ApplicationIntakeService(apps, tmp_path / "intake", reader=reader, fetcher=fetcher)
    worker = Worker()
    flow = Flow(tmp_path / "flow", apps, worker)
    original_start = flow.start

    def start(identifier, revision, stage):
        if stage == "analysis":
            return original_start(identifier, revision, stage)
        task = flow.tasks[identifier]
        assert task["automatic_materials"] is True
        flow.calls.append((stage, identifier))
        if stage == "resume":
            task.update(status="draft_ready", draft_id="full-draft", draft_sha256="a" * 64)
        elif stage == "export":
            task.update(status="materials_ready", resume_id="pdf", resume_sha256="b" * 64)
        else:
            pytest.fail(f"Unexpected material stage: {stage}")
        return deepcopy(task)

    flow.start = start
    pipeline = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        yield pipeline, flow, intake, worker, reads, fetches, messages
    finally:
        pipeline.close()
        intake.close()


def poll_due(pipeline):
    """Make the background mail poll due on the next tick."""
    state = pipeline._load()
    state["mail_poll_at"] = 0
    pipeline._save(state)


def drive(pipeline, status):
    for _ in range(100):
        pipeline._tick()
        if pipeline.snapshot()["status"] == status:
            return pipeline.snapshot()
        time.sleep(0.005)
    pytest.fail(str(pipeline.snapshot()))


def test_completed_capture_selects_a_job_before_any_new_background_capture(queue_environment):
    # Installed MC-11: a real capture outlasts the 60 s poll, so the poll restarted it
    # in the very tick selection ran, and selection waited on it again and again.
    import threading

    pipeline, _flow, intake, _worker, reads, _fetches, _messages = queue_environment
    pipeline.start(request_id="select-after-capture")
    drive(pipeline, "selecting_job")
    gate, original = threading.Event(), intake.reader

    def held(directory, **options):
        gate.wait(5)
        return original(directory, **options)

    intake.reader = held
    try:
        poll_due(pipeline)
        before = len(reads)
        current = drive(pipeline, "acquiring_source")
        assert current["current_recommendation_id"]
        assert intake.snapshot()["status"] != "running" and len(reads) == before
    finally:
        gate.set()


def test_paused_selection_starts_no_background_capture_that_continue_would_wait_on(
    queue_environment,
):
    # Installed MC-11: the App opened paused at selection, the poll began a full
    # capture within seconds, and Continue then waited minutes behind it.
    pipeline, _flow, intake, _worker, reads, _fetches, _messages = queue_environment
    pipeline.start(request_id="paused-selection")
    drive(pipeline, "selecting_job")
    pipeline.pause()
    poll_due(pipeline)
    before = len(reads)
    drive(pipeline, "paused")
    assert intake.snapshot()["status"] != "running" and len(reads) == before
    pipeline.continue_current(request_id="continue-paused-selection")
    assert drive(pipeline, "acquiring_source")["current_recommendation_id"]
    assert len(reads) == before


def test_all_mail_pages_captured_but_only_first_job_acquired_and_processed(queue_environment):
    pipeline, flow, intake, worker, reads, fetches, _messages = queue_environment
    pipeline.start(request_id="persistent-queue")
    current = drive(pipeline, "filling")
    records = intake.snapshot()["recommendations"]
    assert len(records) == 16 and reads == [None, "3", "6", "9", "12", "15"]
    assert fetches == ["https://www.linkedin.com/jobs/view/10000"]
    assert current["current_recommendation_id"] == records[0]["id"]
    assert len(current["items"]) == len(flow.tasks) == 1
    assert [name for name, _ in flow.calls if name in {"analysis", "resume", "export"}] == [
        "analysis",
        "resume",
        "export",
    ]
    worker.state["jobs"][0].update(status="ready_for_review", page_open=True)
    waiting = drive(pipeline, "ready_for_review")
    before = deepcopy(flow.calls), deepcopy(worker.state)
    pipeline._tick()
    assert pipeline.snapshot()["items"] == waiting["items"]
    assert (flow.calls, worker.state) == before
    assert len(fetches) == 1


def test_new_mail_captured_automatically_during_submit_wait_without_changing_page(
    queue_environment,
):
    pipeline, flow, intake, worker, _reads, fetches, messages = queue_environment
    pipeline.start(request_id="capture-while-waiting")
    drive(pipeline, "filling")
    worker.state["jobs"][0].update(
        status="ready_for_review",
        page_open=True,
        page_observation={"page_id": "kept"},
        file_path="synthetic-existing.pdf",
        intent=None,
    )
    waiting = drive(pipeline, "ready_for_review")
    before = deepcopy(worker.state), deepcopy(flow.tasks), deepcopy(flow.calls)
    messages.append(message("new-mail", ["https://www.linkedin.com/jobs/view/99999"]))
    poll_due(pipeline)
    polled = time.time()
    pipeline._tick()
    assert len(ready(intake)["recommendations"]) == 17
    # 2026-11-08: the next waiting read is 30 minutes away, not 60 s.
    assert pipeline._load()["mail_poll_at"] >= polled + 1800
    after = pipeline.snapshot()
    for key in ("items", "active_task_id", "notification", "status", "control", "worker_batch_id"):
        assert after[key] == waiting[key]
    assert (worker.state, flow.tasks, flow.calls) == before
    assert len(fetches) == 1
    # Duplicate mail changes neither queue length nor execution.
    poll_due(pipeline)
    pipeline._tick()
    assert len(ready(intake)["recommendations"]) == 17 and len(fetches) == 1


def test_previously_saved_pending_note_remains_eligible(queue_environment):
    pipeline, flow, intake, _worker, _reads, fetches, _messages = queue_environment
    intake.refresh(capture_only=True)
    record = ready(intake)["recommendations"][0]
    intake.acquire(record["id"], record["revision"])
    record = ready(intake)["recommendations"][0]
    existing_id = record["existing_application"]["id"]
    assert flow.tasks == {}
    pipeline.start(request_id="adopt-existing-note")
    current = drive(pipeline, "filling")
    assert current["active_task_id"] == existing_id
    assert len(fetches) == 1 and len(flow.applications.list_applications()) == 1


def test_failed_sources_leave_the_queue_and_three_in_a_row_stop_it(queue_environment):
    """2026-11-10: an unreachable page no longer waits for a click; an outage still stops."""
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment

    def failed(url):
        fetches.append(url)
        return page(url, status="unavailable", completeness="unknown")

    intake.fetcher = failed
    pipeline.start(request_id="failed-source")
    waiting = drive(pipeline, "needs_input")
    for _ in range(5):
        pipeline._tick()
    assert len(fetches) == 3 and flow.tasks == {} and worker.state["jobs"] == []
    assert pipeline.snapshot()["current_recommendation_id"] == waiting["current_recommendation_id"]
    assert "网络" in waiting["notice"]["message"]
    left = [row for row in waiting["items"] if row.get("reason") == "source_unavailable"]
    assert len(left) == 2 and all(row["status"] == "skipped" for row in left)


def test_empty_queue_waits_for_mail_without_expiring(queue_environment, monkeypatch):
    pipeline, flow, intake, _worker, _reads, fetches, messages = queue_environment
    messages.clear()
    pipeline.start(request_id="empty-queue")
    waiting = drive(pipeline, "waiting_for_mail")
    assert waiting["control"] == "running" and fetches == [] and flow.tasks == {}
    monkeypatch.setattr(
        "career_evidence_graph.application_pipeline.time.time", lambda: waiting["started_at"] + 3600
    )
    messages.append(message("arrived", ["https://www.linkedin.com/jobs/view/98765"]))
    drive(pipeline, "filling")
    assert fetches == ["https://www.linkedin.com/jobs/view/98765"]


def test_healthy_reopen_continues_current_job_without_replaying_analysis(queue_environment):
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    pipeline.start(request_id="healthy-reopen")
    current = drive(pipeline, "generating_resume")
    before = deepcopy(flow.calls)
    pipeline.close()
    reopened = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        assert reopened.snapshot()["control"] == "running"
        after = drive(reopened, "filling")
        assert after["current_recommendation_id"] == current["current_recommendation_id"]
        assert after["active_task_id"] == current["active_task_id"]
        assert [call for call in flow.calls if call[0] == "analysis"] == [
            call for call in before if call[0] == "analysis"
        ]
        assert len(fetches) == 1
    finally:
        reopened.close()


def test_paused_reopen_retains_current_and_does_not_process_next(queue_environment):
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    pipeline.start(request_id="paused-reopen")
    drive(pipeline, "generating_resume")
    waiting = pipeline.pause()
    pipeline.close()
    reopened = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        before = deepcopy(flow.calls)
        reopened._tick()
        assert reopened.snapshot()["items"] == waiting["items"]
        assert reopened.snapshot()["control"] == "paused" and flow.calls == before
        assert len(fetches) == 1
    finally:
        reopened.close()


def test_unknown_acquisition_dispatch_never_repeats_or_moves_to_next(
    queue_environment, monkeypatch
):
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    original = intake.acquire

    def lost_response(identifier, revision):
        original(identifier, revision)
        raise OSError("Synthetic dispatch result lost")

    monkeypatch.setattr(intake, "acquire", lost_response)
    pipeline.start(request_id="unknown-source-dispatch")
    waiting = drive(pipeline, "needs_recheck")
    ready(intake)
    for _ in range(3):
        pipeline._tick()
    assert len(fetches) == 1 and flow.tasks == {} and worker.state["jobs"] == []
    assert waiting["source_receipt"]["status"] == "needs_recheck"
    pipeline.close()
    reopened = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        reopened._tick()
        assert (
            reopened.snapshot()["current_recommendation_id"] == waiting["current_recommendation_id"]
        )
        assert reopened.snapshot()["control"] == "paused" and len(fetches) == 1
    finally:
        reopened.close()


def test_a_language_conflict_does_not_stop_the_current_job(queue_environment):
    """2026-11-08 (user decision): a language-level gap only lowers the match score."""
    from career_evidence_graph.application_worker import WorkerStore

    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    worker.store = WorkerStore(flow.applications, flow.root.parent / "language-worker")
    original = intake.fetcher
    intake.fetcher = lambda url: (
        original(url) | {"body_text": "German B2 required. Python engineering."}
    )
    for question, value in [("German level", "B2"), ("German proficiency CEFR", "C1")]:
        worker.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
    pipeline.start(request_id="current-language")
    current = drive(pipeline, "filling")
    assert len(fetches) == len(flow.tasks) == 1
    assert current["items"][0].get("reason_code") != "language_information_required"


def test_retained_unknown_source_checkpoint_holds_without_another_fetch(queue_environment):
    pipeline, flow, intake, worker, _reads, fetches, _messages = queue_environment
    intake.refresh(capture_only=True)
    record = ready(intake)["recommendations"][0]
    # This durable admission represents an interrupted source operation with no response.
    assert intake.store.begin_acquisition(record["id"], record["revision"])["status"] == "fetch"
    pipeline.start(request_id="retained-unknown-source")
    waiting = drive(pipeline, "needs_recheck")
    assert waiting["current_recommendation_id"] == record["id"]
    assert fetches == [] and flow.tasks == {} and worker.state["jobs"] == []
    for _ in range(3):
        pipeline._tick()
    assert fetches == []


def test_paused_empty_queue_one_continue_restores_saved_mail_wait(queue_environment):
    pipeline, flow, _intake, _worker, reads, fetches, messages = queue_environment
    messages.clear()
    pipeline.start(request_id="empty-pause")
    waiting = drive(pipeline, "waiting_for_mail")
    pipeline.pause()
    resumed = pipeline.continue_current(request_id="continue-empty-mail-wait")
    assert resumed["status"] == "waiting_for_mail" and resumed["control"] == "running"
    assert resumed["id"] == waiting["id"] and resumed["current_recommendation_id"] is None
    assert pipeline.continue_current(request_id="continue-empty-mail-wait") == resumed
    assert reads == [None] and fetches == [] and flow.tasks == {}


def test_a_job_tiered_for_approval_by_an_older_rule_is_tiered_again(queue_environment, monkeypatch):
    from career_evidence_graph import application_pipeline

    # 2026-11-11: jobs tiered "approve" while 55-75 still asked no longer wait.
    pipeline, flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    tiers = ["approve"]
    monkeypatch.setattr(
        application_pipeline,
        "score_tier",
        lambda score, needs_review=False: tiers.pop(0) if tiers else "auto",
    )
    pipeline.start(request_id="retier")
    current = drive(pipeline, "filling")
    assert current.get("wait_reason") != "score_approval"
    assert all(row.get("score_tier") != "approve" for row in current["items"])


def test_low_score_is_skipped_and_a_middle_score_waits_for_one_continue(
    queue_environment, monkeypatch
):
    from career_evidence_graph import application_pipeline

    # Decided 2026-10-31: below the skip line the job is set aside; in the approval band
    # it waits after analysis, before materials, until one Continue approves it.
    pipeline, flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    tiers = ["skip"]
    monkeypatch.setattr(
        application_pipeline,
        "score_tier",
        lambda score, needs_review=False: tiers.pop(0) if tiers else "approve",
    )
    pipeline.start(request_id="tiers")
    waiting = drive(pipeline, "needs_input")
    skipped = [row for row in waiting["items"] if row["status"] == "skipped"]
    assert [row["reason"] for row in skipped] == ["low_match_score"]
    assert skipped[0]["retained_status"] == "matched"
    assert waiting["wait_reason"] == "score_approval"
    assert not any(call[0] == "resume" for call in flow.calls)
    pipeline.continue_current(request_id="approve-score")
    drive(pipeline, "filling")
    assert [call[0] for call in flow.calls].count("resume") == 1


def test_a_closed_posting_leaves_unrecorded_and_easy_apply_with_its_reason(
    queue_environment, monkeypatch
):
    from career_evidence_graph import job_listing_links

    # Decided 2026-10-31: a LinkedIn job is read once before matching; an Easy Apply
    # one keeps LinkedIn and is set aside. 2026-11-05: a closed posting creates no
    # application record and is not listed; the queue still never picks it again.
    pipeline, flow, intake, _worker, _reads, _fetches, _messages = queue_environment
    statuses = {"10000": ("closed", None), "10001": ("easy_apply", None)}
    monkeypatch.setattr(
        job_listing_links,
        "posting_status",
        lambda url, read=None: statuses.get(url.rstrip("/").rsplit("/", 1)[-1], (None, None)),
    )
    before = {row["id"] for row in flow.applications.list_applications()}
    pipeline.start(request_id="postings")
    filling = drive(pipeline, "filling")
    closed = next(
        row["id"]
        for row in intake.snapshot()["recommendations"]
        if row["url"].rstrip("/").endswith("10000")
    )
    assert filling["closed_postings"] == [closed]
    assert closed not in {row["recommendation_id"] for row in filling["items"]}
    assert closed not in {row["id"] for row in filling["pending_recommendations"]}
    skipped = [row for row in filling["items"] if row["status"] == "skipped"]
    assert [row["reason"] for row in skipped] == ["easy_apply_only"]
    created = {row["id"] for row in flow.applications.list_applications()} - before
    assert skipped[0]["application_id"] in created
    assert all(
        not row["url"].rstrip("/").endswith("10000")
        for row in flow.applications.list_applications()
    )
    assert flow.applications.get_application(skipped[0]["application_id"])["status"] == "drafting"


def test_a_removed_or_already_recorded_job_leaves_before_any_analysis(
    queue_environment, monkeypatch
):
    from career_evidence_graph import job_listing_links

    # 2026-11-11 (user decision): before matching, the employer's page is read for a
    # removal and the records for the same job; neither costs analysis or materials.
    # An unreadable page is not a removal and goes on.
    pipeline, flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    employer = "https://careers.example.com/jobs/"
    recorded = flow.applications.create_application(
        {
            "company": "Synthetic Labs",
            "role_title": "Systems Engineer",
            "url": employer + "10001",
            "location": "Zurich, Switzerland",
            "job_description": "Python",
        }
    )
    flow.applications.update_application(
        recorded["id"], {"status": "applied"}, recorded["revision"]
    )
    monkeypatch.setattr(
        job_listing_links,
        "posting_status",
        lambda url, read=None: ("open", employer + url.rstrip("/").rsplit("/", 1)[-1]),
    )
    monkeypatch.setattr(job_listing_links, "employer_url", lambda target: target)
    read = []
    monkeypatch.setattr(
        job_listing_links,
        "posting_gone",
        lambda url: read.append(url) or url.endswith("10000"),
    )
    pipeline.start(request_id="removed")
    filling = drive(pipeline, "filling")
    left = {
        flow.applications.get_application(row["application_id"])["url"]: row
        for row in filling["items"]
        if row["status"] in {"skipped", "excluded"}
    }
    assert left[employer + "10000"]["reason"] == "posting_not_found"
    assert left[employer + "10001"]["status"] == "excluded"
    assert all(row["task_id"] is None for row in left.values())
    assert read[:3] == [employer + "10000", employer + "10001", employer + "10002"]
    current = next(row for row in filling["items"] if row["status"] not in {"skipped", "excluded"})
    assert flow.applications.get_application(current["application_id"])["url"] == (
        employer + "10002"
    )


def test_an_indeed_apply_job_leaves_the_queue_with_its_reason(queue_environment, monkeypatch):
    from career_evidence_graph import indeed_job_source, job_listing_links

    # 2026-11-05: Indeed names the apply route on the page read at intake; an
    # Indeed Apply job keeps Indeed and is set aside like an Easy Apply one.
    pipeline, flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    monkeypatch.setattr(job_listing_links, "posting_status", lambda url, read=None: (None, None))
    monkeypatch.setattr(
        indeed_job_source,
        "apply_route",
        lambda record: "indeed_apply" if record["url"].rstrip("/").endswith("10000") else "",
    )
    pipeline.start(request_id="indeed-apply")
    filling = drive(pipeline, "filling")
    skipped = [row for row in filling["items"] if row["status"] == "skipped"]
    assert [row["reason"] for row in skipped] == ["indeed_apply_only"]
    application = flow.applications.get_application(skipped[0]["application_id"])
    assert application["status"] == "drafting" and "Indeed Apply" in application["next_action"]


@pytest.mark.parametrize(("upper", "skipped"), [(40, True), (60, False)])
def test_a_job_needing_an_account_goes_on_only_from_a_good_match(
    queue_environment, monkeypatch, upper, skipped
):
    """2026-11-09: a sign-in leaves the automatic path; below 55 it is not worth it."""
    from career_evidence_graph import application_pipeline

    pipeline, flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    score = {"lower": upper, "upper": upper, "coverage": 100, "eligibility": "not_specified"}
    monkeypatch.setattr(application_pipeline, "combined_score", lambda *_: (dict(score), None))
    monkeypatch.setattr(application_pipeline, "score_tier", lambda *_, **__: "auto")
    checked = []

    def check(url, directory, learned=()):
        checked.append(url)
        return {"status": "account" if len(checked) == 1 else "direct", "by": "page"}

    pipeline.account_check = check
    pipeline.start(request_id="accounts")
    current = drive(pipeline, "filling")
    first = current["items"][0]
    assert first.get("account_check", {}).get("status") == "account"
    if skipped:
        assert first["status"] == "skipped" and first["reason"] == "account_low_match"
        assert current["active_task_id"] != first["task_id"]
    else:
        assert current["active_task_id"] == first["task_id"]


def test_a_high_value_job_waits_for_the_resume_plan_and_feedback_plans_again(
    queue_environment, monkeypatch
):
    """2026-11-12 (user decision): a high match, target company or high salary stops
    before any experience is written; Continue confirms, written feedback plans again."""
    from career_evidence_graph import application_pipeline

    pipeline, flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    tiers = ["manual"]
    monkeypatch.setattr(
        application_pipeline,
        "score_tier",
        lambda score, needs_review=False: tiers.pop(0) if tiers else "auto",
    )
    plans, feedback, attempts, pending, selected = {}, [], [], set(), set()
    original = flow.start

    def start(identifier, revision, stage, **_options):
        if stage != "resume":
            return original(identifier, revision, stage)
        task = flow.tasks[identifier]
        plan = plans.setdefault(
            identifier, {"assignments": [{"experience_id": "exp-a"}, {"experience_id": "exp-b"}]}
        )
        pending.discard(identifier)  # The planner runs before any review.
        attempts.append(identifier)
        allowed = flow.callbacks["plan_allowed"]
        if (
            identifier not in selected
            and not allowed(identifier, None)
            or not allowed(identifier, plan)
        ):
            flow.calls.append((stage, identifier))
            task.update(status="failed")
            task["stages"] = {
                "resume": {
                    "status": "failed",
                    "error_code": "resume_plan_review_required",
                    "attempt_id": f"attempt-{len(attempts)}",
                }
            }
            task["revision"] += "v"
            return deepcopy(task)
        task.pop("stages", None)
        return original(identifier, revision, stage)

    flow.start = start
    flow.resume_plan = lambda task_id: (
        None
        if task_id in pending
        else {
            "plan": None,
            "overview": {
                "stage": "selection",
                "requirements": [{"index": 0, "evidence": ["exp-a"]}],
                "selected": [row["experience_id"] for row in plans[task_id]["assignments"]],
            },
        }
        if task_id not in selected
        else {
            "plan": plans[task_id],
            "overview": {
                "stage": "points",
                "chosen": [
                    {"title": row["experience_id"]} for row in plans[task_id]["assignments"]
                ],
            },
        }
    )

    def replan(task_id, text):
        feedback.append(text)
        plans[task_id] = {"assignments": [{"experience_id": "exp-b"}]}
        pending.add(task_id)

    flow.replan_resume = replan
    selections, points = [], []

    def select(task_id, evidence, experiences):
        selections.append((evidence, experiences))
        plans[task_id] = {"assignments": [{"experience_id": eid} for eid in experiences]}
        selected.add(task_id)
        pending.add(task_id)
        return {"mapping_required": True}

    def edit(task_id, changes):
        points.append(changes)
        for row in plans[task_id]["assignments"]:
            row["writing_requirements"] = changes.get(row["experience_id"], [])

    flow.select_resume_experiences = select
    flow.reopen_resume_selection = selected.discard
    flow.edit_resume_points = edit
    pipeline.start(request_id="precision")
    waiting = drive(pipeline, "needs_input")
    assert waiting["wait_reason"] == "resume_plan_review"
    assert waiting["plan_review"]["reasons"] == ["匹配分达到 75 以上"]
    # 2026-11-12 (user decision): first each requirement's evidence and the experiences.
    assert waiting["plan_review"]["stage"] == "selection"
    current = next(row for row in waiting["items"] if row["task_id"] == waiting["active_task_id"])
    assert current["precision_selection"] == ["匹配分达到 75 以上"]

    # A review saved before the evidence step: Continue shows the current step instead.
    state = pipeline._load()
    state["plan_review"] = {"chosen": [{"title": "exp-a"}]}
    pipeline._save(state)
    pipeline.continue_current(request_id="stale-review")
    assert pipeline.snapshot()["plan_review"]["stage"] == "selection"
    assert not selected

    chosen = {"evidence": {"0": ["exp-stoa"]}, "experiences": ["exp-stoa", "exp-a"]}
    pipeline.continue_current(request_id="select", plan_selection=chosen)
    shown = drive(pipeline, "needs_input")["plan_review"]
    assert shown["stage"] == "points"
    assert [row["title"] for row in shown["chosen"]] == ["exp-stoa", "exp-a"]
    assert selections == [({"0": ["exp-stoa"]}, ["exp-stoa", "exp-a"])]
    # Going back shows the choice again; Continue there keeps the shown choice.
    pipeline.continue_current(request_id="reselect", plan_reselect=True)
    assert drive(pipeline, "needs_input")["plan_review"]["stage"] == "selection"
    pipeline.continue_current(request_id="keep-selection")
    assert drive(pipeline, "needs_input")["plan_review"]["stage"] == "points"
    assert selections[-1] == ({"0": ["exp-a"]}, ["exp-stoa", "exp-a"])

    pipeline.continue_current(request_id="replan", plan_feedback="Only keep exp-b.")
    # 2026-11-12, G-Research: the restart after a re-plan was lost; with no plan to show
    # yet, the queue restarts planning instead of stopping with nothing to review.
    state = pipeline._load()
    assert state.pop("resume_author_retry", None) is not None
    pipeline._save(state)
    again = drive(pipeline, "needs_input")
    assert feedback == ["Only keep exp-b."]
    assert again["wait_reason"] == "resume_plan_review"
    assert [row["title"] for row in again["plan_review"]["chosen"]] == ["exp-b"]

    # 2026-11-12: a redone job kept the cancelled task's Worker batch, so this Continue
    # took the Worker path and did nothing.
    state = pipeline._load()
    state.update(
        worker_batch_id="cancelled-batch",
        transmission_authorization={"task_id": "cancelled-task"},
        computer_use={"run_id": "cancelled-run", "company": "Synthetic Labs"},
    )
    pipeline._save(state)
    pipeline.continue_current(request_id="confirm-plan", plan_points={"exp-b": ["Lead."]})
    assert points == [{"exp-b": ["Lead."]}]
    confirmed = pipeline.snapshot()
    assert "worker_batch_id" not in confirmed or confirmed["worker_batch_id"] != "cancelled-batch"
    filling = drive(pipeline, "filling")
    assert "plan_review" not in filling
    assert len(attempts) == 6


@pytest.mark.parametrize(("high", "waits"), [(250_000, True), (150_000, False)])
def test_researched_pay_from_200k_chf_makes_a_job_high_value(queue_environment, high, waits):
    """2026-11-12 (user decision): a yearly pay of 200,000 CHF or more is high value."""
    pipeline, _flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    item = {"recommendation_id": "r1", "salary_research": {"yearly_high_chf": high}}
    reasons = pipeline._precision_reasons(item, "auto")
    assert bool(reasons) is waits
    if waits:
        assert reasons == ["薪资上限约 250,000 CHF"]
    assert pipeline._precision_reasons({"recommendation_id": "r2"}, "auto") == []


def test_a_high_value_job_waits_for_its_bullets_and_revises_one_experience(
    queue_environment, monkeypatch
):
    """2026-11-12 (user decision): the drafted bullets are reviewed with the user before
    the résumé is generated; feedback or edits revise one experience, Continue confirms."""
    from career_evidence_graph import application_pipeline

    pipeline, flow, _intake, _worker, _reads, _fetches, _messages = queue_environment
    tiers = ["manual"]
    monkeypatch.setattr(
        application_pipeline,
        "score_tier",
        lambda score, needs_review=False: tiers.pop(0) if tiers else "auto",
    )
    plan = {"assignments": [{"experience_id": "exp-a"}, {"experience_id": "exp-b"}]}
    bullets = {
        "exp-a": [{"id": "a1", "text": "Built the thing at scale."}],
        "exp-b": [{"id": "b1", "text": "Studied the other thing."}],
    }
    revisions, approved, attempts = [], set(), []
    original = flow.start

    def start(identifier, revision, stage, **_options):
        if stage != "resume":
            return original(identifier, revision, stage)
        attempts.append(identifier)
        task = flow.tasks[identifier]
        blocked = (
            "resume_plan_review_required"
            if not flow.callbacks["plan_allowed"](identifier, plan)
            else "resume_wording_review_required"
            if flow.callbacks["wording_review_required"](identifier) and approved != set(bullets)
            else None
        )
        if blocked:
            flow.calls.append((stage, identifier))
            task.update(status="failed")
            task["stages"] = {
                "resume": {
                    "status": "failed",
                    "error_code": blocked,
                    "attempt_id": f"attempt-{len(attempts)}",
                }
            }
            task["revision"] += "v"
            return deepcopy(task)
        task.pop("stages", None)
        return original(identifier, revision, stage)

    def revise(task_id, experience_id, *, feedback=None, items=None):
        revisions.append((experience_id, feedback, items))
        approved.discard(experience_id)
        if items:
            bullets[experience_id] = [{"id": key, "text": text} for key, text in items.items()]

    flow.start = start
    flow.resume_plan = lambda task_id: {"plan": plan, "overview": {"chosen": []}}
    flow.resume_wording = lambda task_id: {
        "experiences": [
            {
                "experience_id": eid,
                "title": eid,
                "items": items,
                "feedback": [],
                "confirmed": eid in approved,
            }
            for eid, items in bullets.items()
        ]
    }
    flow.revise_resume_wording = revise
    flow.approve_resume_wording = lambda task_id, experience_id=None: approved.update(
        [experience_id] if experience_id else bullets
    )
    pipeline.start(request_id="wording")
    assert drive(pipeline, "needs_input")["wait_reason"] == "resume_plan_review"
    pipeline.continue_current(request_id="confirm-plan")
    waiting = drive(pipeline, "needs_input")
    assert waiting["wait_reason"] == "resume_wording_review"
    assert waiting["wording_review"]["experiences"][0]["items"][0]["text"] == (
        "Built the thing at scale."
    )
    assert waiting["wording_review"]["reasons"] == ["匹配分达到 75 以上"]

    pipeline.continue_current(
        request_id="rewrite-a",
        wording_changes={"exp-a": {"feedback": "Name the method instead."}},
    )
    assert drive(pipeline, "needs_input")["wait_reason"] == "resume_wording_review"
    pipeline.continue_current(
        request_id="edit-a",
        wording_changes={"exp-a": {"items": {"a1": "Designed the estimator."}}},
    )
    edited = drive(pipeline, "needs_input")
    assert edited["wording_review"]["experiences"][0]["items"][0]["text"] == (
        "Designed the estimator."
    )
    assert revisions == [
        ("exp-a", "Name the method instead.", None),
        ("exp-a", None, {"a1": "Designed the estimator."}),
    ]
    assert not approved
    # 2026-11-12: leaving an experience out goes back to the selection, not a rewrite.
    reopened = []
    flow.reopen_resume_selection = reopened.append
    pipeline.continue_current(request_id="reselect", plan_reselect=True)
    assert reopened == [edited["active_task_id"]]
    assert drive(pipeline, "needs_input")["wait_reason"] == "resume_wording_review"
    # Headline, summary and skills are written again only when the user asks.
    regenerated = []
    flow.regenerate_resume_global = regenerated.append
    pipeline.continue_current(request_id="regenerate", regenerate_global=True)
    assert regenerated == [edited["active_task_id"]]
    assert drive(pipeline, "needs_input")["wait_reason"] == "resume_wording_review"
    # One experience at a time: confirming exp-a keeps the job waiting on exp-b.
    pipeline.continue_current(request_id="confirm-a", wording_changes={"exp-a": {"confirm": True}})
    one = pipeline.snapshot()
    assert one["status"] == "needs_input" and one["wait_reason"] == "resume_wording_review"
    assert [row["confirmed"] for row in one["wording_review"]["experiences"]] == [True, False]
    pipeline.continue_current(request_id="confirm-b", wording_changes={"exp-b": {"confirm": True}})
    filling = drive(pipeline, "filling")
    assert approved == {"exp-a", "exp-b"} and "wording_review" not in filling
