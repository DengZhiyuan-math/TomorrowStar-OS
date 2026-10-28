"""Real Flow/Pipeline/Worker composition; all mail and HTTP transport is synthetic."""

import json
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from threading import Thread

import pytest
from test_application_intake import message, ready
from test_ashby_bootstrap import ORG, public_request
from test_ashby_drafts import URL, bounded_route
from test_career_portal_http import Portal
from test_worker_backend_recovery import backend

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.ashby_drafts import DraftSession


@contextmanager
def http_backend(server, tmp_path):
    portal = Portal(
        server, server.application_intake_service.applications.root, tmp_path / "career"
    )
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield portal
    finally:
        server.shutdown()
        thread.join(3)
        assert not thread.is_alive()


def api(portal, path, payload=None):
    status, _, raw = portal.request(
        "GET" if payload is None else "POST",
        path,
        body=None if payload is None else json.dumps(payload).encode(),
        headers={} if payload is None else portal.write_headers(),
    )
    assert status == 200, raw
    return json.loads(raw)


@pytest.fixture
def mail_backend(tmp_path, monkeypatch, request):
    label = getattr(request, "param", "  Synthetic Processed / 已处理  ")
    job_url = URL
    if isinstance(label, dict):
        job_url, label = label["job_url"], label["label"]
    calls, reads = [], []
    actual = {"labeled": False, "archived": False}
    current = {"configured_label": label}

    def reader(*_args, **_options):
        reads.append(True)
        return {
            "status": "readable",
            "emails": [message("incoming", ["https://www.linkedin.com/jobs/view/19999"])],
            "provenance": {"mailbox_identity": "a" * 64, "account_identity_status": "verified"},
        }

    def mailbox(_root, *, operation, label_name, expected_mailbox_identity, **_options):
        assert label_name == label and expected_mailbox_identity == "a" * 64
        saved = current["server"].application_intake_service.snapshot()["recommendations"]
        assert saved[0]["source_messages"][0]["message_id"] == "incoming"
        calls.append(operation)
        if operation == "label":
            actual["labeled"] = True
        if operation == "archive":
            actual["archived"] = True
            raise TimeoutError("Synthetic archive succeeded; reply lost")
        return {"status": "complete", **actual}

    def forbidden(*_args, **_options):
        pytest.fail("Waiting capture must not acquire or analyze another JD")

    def intake_factory(applications, root, **options):
        return ApplicationIntakeService(
            applications,
            root,
            reader=reader,
            mailbox=mailbox,
            fetcher=forbidden,
            extractor=forbidden,
            **options,
        )

    fixture = backend.__wrapped__(
        tmp_path,
        monkeypatch,
        job_url=job_url,
        server_options={
            "worker_generic": True,
            "application_processed_label": label,
            "flow_intake_factory": intake_factory,
        },
    )
    owner, reopen, runner, page = next(fixture)
    current["server"] = owner
    try:
        yield owner, reopen, runner, page, reads, calls, current
    finally:
        fixture.close()


def wait_current(owner, runner, status="needs_recheck"):
    state = runner.store.load()
    state["control"] = "paused"
    state["jobs"][0].update(
        status="filling" if status == "paused" else status,
        intent={"action": "upload", "attempt_id": "retained-unknown"}
        if status == "needs_recheck"
        else None,
    )
    runner.store.save(state)
    pipeline = owner.application_pipeline_service
    policy = pipeline._load()
    policy.update(control="paused", status=status)
    policy["items"] = [
        {
            "recommendation_id": policy["current_recommendation_id"],
            "application_id": state["jobs"][0]["application_id"],
            "task_id": policy["active_task_id"],
            "status": status,
            "score": None,
        }
    ]
    pipeline._save(policy)
    return deepcopy(state), pipeline.snapshot()


@pytest.mark.parametrize("wait_status", ["needs_input", "needs_recheck", "paused"])
def test_real_pipeline_capture_reopen_and_archive_readback_preserve_waiting_job(
    mail_backend, tmp_path, wait_status
):
    owner, reopen, runner, page, reads, calls, current = mail_backend
    worker_before, pipeline_before = wait_current(owner, runner, wait_status)
    task_before = owner.application_flow_service.snapshot()["tasks"]
    original = worker_before["jobs"][0]
    material = Path(original["file_path"]).read_bytes()
    with http_backend(owner, tmp_path) as portal:
        api(portal, "/api/pipeline/capture", {"request_id": "capture-while-current-waits"})
        captured = ready(owner.application_intake_service)
        assert captured["progress"]["mail_needs_recheck"] == 1
        assert captured["progress"]["mail_labeled"] == 1
        assert captured["progress"]["mail_archived"] == 0
        assert len(captured["recommendations"]) == 1
        for _ in range(2):
            api(portal, "/api/recommendations/state")
            api(portal, "/api/pipeline/state")
            owner.application_pipeline_service._tick()
        after = api(portal, "/api/pipeline/state")
        for key in ("active_task_id", "current_recommendation_id", "status", "control", "items"):
            assert after[key] == pipeline_before[key]
        assert runner.store.load() == worker_before
        assert owner.application_flow_service.snapshot()["tasks"] == task_before
        assert calls == ["inspect", "label", "inspect", "archive"]
    owner.server_close()
    owner = reopen()
    current["server"] = owner
    with http_backend(owner, tmp_path) as portal:
        api(portal, "/api/pipeline/capture", {"request_id": "capture-while-current-waits"})
        assert reads == [True] and calls == ["inspect", "label", "inspect", "archive"]
        # The normal application entry uses Pipeline capture. Legacy intake
        # continue remains gated while Pipeline owns the current job.
        api(portal, "/api/pipeline/capture", {"request_id": "explicit-mail-readback"})
        result = ready(owner.application_intake_service)
        assert result["progress"]["mail_archived"] == 1
        assert result["progress"]["mail_needs_recheck"] == 0
        assert len(result["recommendations"]) == 1 and reads == [True, True]
        assert calls == ["inspect", "label", "inspect", "archive", "inspect"]
        after = api(portal, "/api/pipeline/state")
        assert after["active_task_id"] == pipeline_before["active_task_id"]
        assert after["status"] == wait_status and after["control"] == "paused"
        assert runner.store.load()["jobs"] == worker_before["jobs"]
        assert runner.store.load()["runtime"]["id"] == worker_before["runtime"]["id"]
        assert runner.pages[original["application_id"]] is page
        assert Path(original["file_path"]).read_bytes() == material


@pytest.mark.parametrize("mail_backend", [None, "INBOX"], indirect=True)
def test_missing_or_bad_mail_setting_does_not_block_real_current_job_capture(
    mail_backend, tmp_path
):
    owner, _reopen, runner, _page, reads, calls, current = mail_backend
    worker_before, pipeline_before = wait_current(owner, runner)
    with http_backend(owner, tmp_path) as portal:
        api(portal, "/api/pipeline/capture", {"request_id": "capture-with-disabled-processing"})
        captured = ready(owner.application_intake_service)
        assert len(captured["recommendations"]) == 1
        assert captured["progress"]["mail_captured"] == 1
        assert not captured["progress"]["mail_label_configured"]
        assert captured["progress"]["mail_processing_error"] == (
            "" if current["configured_label"] is None else "gmail_processing_invalid"
        )
        assert calls == [] and reads == [True]
        assert (
            api(portal, "/api/pipeline/state")["active_task_id"]
            == pipeline_before["active_task_id"]
        )
        assert runner.store.load() == worker_before


def test_background_mail_poll_captures_without_advancing_real_waiting_job(mail_backend):
    owner, _reopen, runner, page, reads, calls, _current = mail_backend
    worker_before, before = wait_current(owner, runner, "needs_input")
    pipeline = owner.application_pipeline_service
    state = pipeline._load()
    state["mail_poll_at"] = 0
    pipeline._save(state)
    pipeline._tick()
    captured = ready(owner.application_intake_service)
    assert captured["progress"]["mail_needs_recheck"] == 1
    pipeline._tick()
    after = pipeline.snapshot()
    for key in ("active_task_id", "current_recommendation_id", "status", "control", "items"):
        assert after[key] == before[key]
    assert runner.store.load() == worker_before
    assert runner.pages[worker_before["jobs"][0]["application_id"]] is page
    assert reads == [True] and calls == ["inspect", "label", "inspect", "archive"]


def test_ashby_bootstrap_cannot_resolve_unknown_intent_or_replace_skipped_original_page(
    mail_backend, tmp_path
):
    owner, _reopen, runner, page, reads, calls, _current = mail_backend
    worker_before, policy = wait_current(owner, runner)
    original = worker_before["jobs"][0]
    runner.drafts[page] = DraftSession(original)
    route = bounded_route(public_request(page, ORG))
    runner._live_guard(route)
    assert route.outcome == "allowed" and len(route.fetch_calls) == 1
    assert runner.store.load() == worker_before
    with http_backend(owner, tmp_path) as portal:
        assert api(portal, "/api/pipeline/state")["status"] == "needs_recheck"
        skipped = api(portal, "/api/pipeline/skip", {"request_id": "skip-retained-original"})
        assert skipped["status"] == "selecting_job" and skipped["active_task_id"] is None
        assert skipped["current_recommendation_id"] is None
        assert skipped["items"][0]["status"] == "skipped"
        assert runner.store.load()["jobs"][0] == original
        returned = api(
            portal,
            "/api/pipeline/return",
            {
                "request_id": "return-retained-original",
                "application_id": original["application_id"],
            },
        )
        assert returned["active_task_id"] == policy["active_task_id"]
        assert returned["control"] == "paused"
        assert returned["status"] == "needs_recheck"
        assert runner.store.load()["jobs"][0] == original
        assert runner.pages[original["application_id"]] is page
        assert not reads and not calls
    final = bounded_route(
        public_request(
            page,
            "SubmitApplication",
            query="mutation SubmitApplication { submitApplication { id } }",
        )
    )
    runner._live_guard(final)
    assert final.outcome == "blocked" and not final.fetch_calls
    assert runner.store.load()["jobs"][0]["intent"] == original["intent"]


@pytest.mark.parametrize(
    "mail_backend",
    [
        {
            "label": None,
            "job_url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001",
        }
    ],
    indirect=True,
)
@pytest.mark.parametrize("conclusion", ["success", "rejected", "unknown"])
def test_public_result_observation_completes_real_flow_and_selects_next_source(
    mail_backend, tmp_path, monkeypatch, conclusion
):
    import time
    from types import SimpleNamespace

    from career_evidence_graph.application_form_state import COMPLETE_WINDOW, MIN_SAMPLES, sample

    owner, _reopen, runner, page, reads, calls, _current = mail_backend
    pipeline = owner.application_pipeline_service
    state = runner.store.load()
    original = deepcopy(state["jobs"][0])
    pdf = Path(original["file_path"]).read_bytes()
    state["jobs"][0].update(status="ready_for_review", intent=None)
    runner.store.save(state)
    policy = pipeline._load()
    policy["items"] = [
        {
            "recommendation_id": policy["current_recommendation_id"],
            "application_id": original["application_id"],
            "task_id": policy["active_task_id"],
            "status": "matched",
            "score": None,
        }
    ]
    pipeline._save(policy)
    page.url = original["job_url"] + "/apply"
    page.unroute = lambda *_args: None
    page.bring_to_front = lambda: None
    observed = {
        "document_token": "original-submit-document",
        "parser": {"status": "complete"},
        "validation_errors": [],
        "fields": [
            {
                "id": "resume",
                "type": "file",
                "required": True,
                "valid": True,
                "resume": True,
                "filename": original["filename"],
                "file_sha256": original["file_sha256"],
            }
        ],
    }
    readbacks = []

    def observe(actual_page, actual_job):
        assert actual_page is page and actual_job["application_id"] == original["application_id"]
        readbacks.append(actual_page)
        return deepcopy(observed)

    monkeypatch.setattr(runner, "observe", observe)
    binding = {
        "run_id": runner.run_id,
        "page_id": runner.page_ids[page],
        "step": page.url,
        "document_token": observed["document_token"],
    }
    # This fixture starts at a completed, stable form. The actual handoff must
    # still read the same page again before it releases the submission guard.
    form_state = None
    now = time.time()
    for index in range(MIN_SAMPLES):
        form_state = sample(
            form_state,
            observed,
            binding=binding,
            now=now - COMPLETE_WINDOW * (MIN_SAMPLES - index),
        )
    assert form_state["parser"]["status"] == "stable"
    state = runner.store.load()
    state["jobs"][0]["form_state"] = form_state
    runner.store.save(state)
    runner.guards[original["application_id"]] = object()
    with http_backend(owner, tmp_path) as portal:
        api(portal, "/api/pipeline/capture", {"request_id": "capture-before-human-submit"})
        captured = ready(owner.application_intake_service)
        next_id = captured["recommendations"][0]["id"]
        pipeline._tick()
        waiting = api(portal, "/api/pipeline/state")
        assert waiting["status"] == "ready_for_review"
        state = runner.store.load()
        runner.commands(state)
        runner.persist(state)
        assert page in runner.handed_off_pages
        assert readbacks == [page]

        class Request:
            method = "POST"
            url = page.url
            frame = SimpleNamespace(page=page)

        human_request, allowed = Request(), []
        runner._live_guard_request(
            SimpleNamespace(request=human_request, continue_=lambda: allowed.append(True))
        )
        runner.transport(human_request, "response", 302)
        runner.transport(human_request, "requestfinished")
        assert allowed == [True]
        monkeypatch.setattr(
            runner,
            "read_submission_page",
            lambda *_args: {
                "url": "https://jobs.lever.co/confirmation",
                "messages": [
                    {
                        "success": "Your application has been submitted.",
                        "rejected": "Application submission failed.",
                        "unknown": "Please wait.",
                    }[conclusion]
                ],
                "has_form": False,
            },
        )
        api(portal, "/api/pipeline/observe-result", {"request_id": "read-human-submit-result"})
        state = runner.store.load()
        runner.commands(state)
        runner.persist(state)
        pipeline._tick()
        completed = api(portal, "/api/pipeline/state")
        if conclusion == "success":
            assert completed["items"][0]["status"] == "completed"
            assert completed["current_recommendation_id"] == next_id
            assert completed["status"] == "acquiring_source"
            assert completed["active_task_id"] is None
            assert (
                runner.store.load()["jobs"][0]["manual_submission"]["source"]
                == "read_only_browser_result"
            )
        else:
            assert completed["items"][0]["status"] != "completed"
            assert completed["current_recommendation_id"] == policy["current_recommendation_id"]
            assert completed["active_task_id"] == policy["active_task_id"]
            assert completed["status"] == (
                "needs_input" if conclusion == "rejected" else "needs_recheck"
            )
            retained = deepcopy(runner.store.load()["jobs"][0])
            for _ in range(2):
                pipeline._tick()
            assert runner.store.load()["jobs"][0] == retained
        assert len(owner.application_flow_service.snapshot()["tasks"]) == 1
        assert runner.pages[original["application_id"]] is page
        assert Path(original["file_path"]).read_bytes() == pdf
        assert reads == [True] and not calls


@pytest.mark.parametrize("mail_backend", [None], indirect=True)
def test_return_after_selecting_next_source_keeps_real_original_page_and_unknown_intent(
    mail_backend, tmp_path
):
    owner, _reopen, runner, page, reads, calls, _current = mail_backend
    before, policy = wait_current(owner, runner)
    original = before["jobs"][0]
    pdf = Path(original["file_path"]).read_bytes()
    with http_backend(owner, tmp_path) as portal:
        api(portal, "/api/pipeline/capture", {"request_id": "capture-before-skip"})
        captured = ready(owner.application_intake_service)
        next_id = captured["recommendations"][0]["id"]
        api(portal, "/api/pipeline/skip", {"request_id": "skip-before-second-source"})
        owner.application_pipeline_service._tick()
        second = api(portal, "/api/pipeline/state")
        assert second["current_recommendation_id"] == next_id
        assert second["status"] == "acquiring_source" and second["active_task_id"] is None
        returned = api(
            portal,
            "/api/pipeline/return",
            {
                "request_id": "return-after-second-source",
                "application_id": original["application_id"],
            },
        )
        assert returned["current_recommendation_id"] == policy["current_recommendation_id"]
        assert returned["active_task_id"] == policy["active_task_id"]
        assert returned["control"] == "paused" and returned["status"] == "needs_recheck"
        assert (
            next(row for row in returned["items"] if row["recommendation_id"] == next_id)["status"]
            == "skipped"
        )
        assert len(owner.application_flow_service.snapshot()["tasks"]) == 1
        assert runner.store.load()["jobs"][0] == original
        assert runner.pages[original["application_id"]] is page
        assert Path(original["file_path"]).read_bytes() == pdf
        assert reads == [True] and not calls
