"""Explicit single-job selection preserves retained pages, evidence and claims."""

from copy import deepcopy
from pathlib import Path

import pytest
from test_application_worker import job
from test_single_application_worker import single_worker as single_worker

from career_evidence_graph.application_worker import digest
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError


def prepare(service, item):
    return service.request(
        "prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]}
    )


def test_skip_append_return_keeps_original_job_intent_pdf_and_owner(single_worker):
    service, first, _checks, _launches = single_worker
    prepare(service, first)
    before = service.store.load()
    original = before["jobs"][0]
    original.update(
        status="needs_recheck",
        page_open=True,
        intent={"action": "upload", "attempt_id": "unresolved-original"},
        observations=[{"action": "retained-original-evidence"}],
    )
    service.store.save(before)
    pdf = Path(original["file_path"]).read_bytes()
    service.request(
        "skip-current", {"application_id": first["application_id"], "request_id": "skip-one"}
    )
    second = job(service, 2)
    second["single_binding"] = {"task_id": "second-task"}
    prepare(service, second)
    after = service.store.load()
    assert after["batch_id"] == before["batch_id"]
    assert after["current_job_id"] == second["application_id"]
    assert len(after["jobs"]) == 2 and after["jobs"][0] == original
    assert Path(original["file_path"]).read_bytes() == pdf
    service.request(
        "skip-current", {"application_id": second["application_id"], "request_id": "skip-two"}
    )
    service.request(
        "select-current", {"application_id": first["application_id"], "request_id": "return-one"}
    )
    returned = service.store.load()
    assert returned["current_job_id"] == first["application_id"]
    assert returned["jobs"][0] == original and returned["control"] == "paused"
    assert returned["jobs"][0]["status"] != "cancelled"


def test_current_runner_and_dispatcher_ignore_retained_other_jobs(single_worker, monkeypatch):
    service, first, _checks, _launches = single_worker
    prepare(service, first)
    service.request(
        "skip-current", {"application_id": first["application_id"], "request_id": "skip-one"}
    )
    second = job(service, 2)
    second["single_binding"] = {"task_id": "second-task"}
    prepare(service, second)
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    processed = []
    monkeypatch.setattr(
        runner, "process", lambda current, batch: processed.append(current["application_id"])
    )
    runner._tick()
    assert processed == [second["application_id"]]
    assert not runner.authorize(state["jobs"][0], state["batch_id"], {"action": "open"})
    assert service.store.load()["jobs"][0]["intent"] is None


def test_explicit_current_must_be_skipped_before_another_prepare(single_worker):
    service, first, _checks, _launches = single_worker
    prepare(service, first)
    second = job(service, 2)
    second["single_binding"] = {"task_id": "second-task"}
    before = deepcopy(service.store.load())
    with pytest.raises(PortalDataError):
        prepare(service, second)
    assert service.store.load() == before


def retained_page(service, item, *, intent=None):
    from career_evidence_graph.application_worker import start_run

    prepare(service, item)
    run_id = start_run(service.store)
    state = service.store.load()
    state["jobs"][0].update(
        status="needs_input",
        page_open=True,
        intent=intent,
        page_observation={
            "run_id": run_id,
            "page_id": "retained-page",
            "event": "observed",
            "at": state["runtime"]["observed_at"],
        },
    )
    service.store.save(state)
    runner = ApplicationRunner(service.store, None)

    # Page handles must be hashable; identity is tied to the original runner map.
    class Page:
        context = None

        def is_closed(self):
            return False

    page = Page()
    runner.pages[item["application_id"]] = page
    runner.page_ids[page] = "retained-page"
    return runner, page


def test_one_continue_reads_existing_page_and_preserves_manual_fields_and_attachment(
    single_worker, monkeypatch
):
    service, item, _checks, _launches = single_worker
    runner, _page = retained_page(service, item)
    fields = [
        {"id": "name", "type": "text", "value": "Human edited name", "valid": True},
        {"id": "resume", "type": "file", "filename": "user-edited.pdf", "file_sha256": "a" * 64},
    ]
    reads = []
    monkeypatch.setattr(
        runner, "observe", lambda page, current: reads.append(page) or {"fields": deepcopy(fields)}
    )
    payload = {
        "application_id": item["application_id"],
        "controller": "synthetic-controller",
        "request_id": "continue-once",
    }
    service.request("continue-current", payload)
    assert service.store.load()["control"] == "paused"
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    after = service.store.load()
    assert len(reads) == 1 and after["control"] == "running"
    assert after["jobs"][0]["manual_fields"]["name"]["value"] == "Human edited name"
    assert after["jobs"][0]["manual_attachments"] == [fields[1]]
    assert after["jobs"][0]["continuation"]["status"] == "verified"
    service.request("continue-current", payload)
    assert service.store.load()["commands"] == [] and len(reads) == 1


def test_continue_reads_unknown_intent_but_never_clears_or_replays_it(single_worker, monkeypatch):
    service, item, _checks, _launches = single_worker
    intent = {"action": "upload", "attempt_id": "unknown-upload"}
    runner, _page = retained_page(service, item, intent=intent)
    monkeypatch.setattr(runner, "observe", lambda *_: {"fields": []})
    service.request(
        "continue-current",
        {
            "application_id": item["application_id"],
            "controller": "synthetic-controller",
            "request_id": "continue-unknown",
        },
    )
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    after = service.store.load()
    assert after["control"] == "paused" and after["jobs"][0]["intent"] == intent
    assert after["jobs"][0]["status"] == "needs_recheck"
    assert after["jobs"][0]["continuation"]["status"] == "needs_recheck"


@pytest.mark.parametrize(
    "text,status,conclusion",
    [
        ("Your application has been submitted.", 200, "success"),
        ("Application could not be submitted.", 422, "rejected"),
        ("Please wait", 200, "unknown"),
    ],
)
def test_result_observation_reads_only_and_separates_success_rejection_unknown(
    single_worker, monkeypatch, text, status, conclusion
):
    service, item, _checks, _launches = single_worker
    runner, page = retained_page(service, item)
    state = service.store.load()
    current = state["jobs"][0]
    current.update(status="ready_for_review", handed_off=True)
    current["observations"].append(
        {
            "action": "manual_submit_observed",
            "kind": "manual_submit",
            "stage": "response",
            "http_status": status,
            "target_binding": {
                "job_url": current["job_url"],
                "request_url": current["job_url"] + "/apply",
                "method": "POST",
                "page_url": current["job_url"] + "/apply",
            },
            "application_id": item["application_id"],
            "run_id": runner.run_id,
            "batch_id": state["batch_id"],
            "page_id": "retained-page",
        }
    )
    service.store.save(state)
    monkeypatch.setattr(
        runner,
        "read_submission_page",
        lambda *_: {"url": current["job_url"], "messages": [text], "has_form": False},
    )
    service.request(
        "observe-result", {"application_id": item["application_id"], "request_id": "observe-once"}
    )
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    after = service.store.load()
    assert after["jobs"][0]["submission_observation"]["conclusion"] == conclusion
    assert after["control"] == "paused" and after["commands"] == []
    assert after["jobs"][0]["intent"] is None and after["jobs"][0]["handed_off"] is True
    assert bool(after["jobs"][0]["manual_submission"]) == (conclusion == "success")


def test_continue_process_preserves_manual_value_over_library_and_keeps_verified_file(
    single_worker, monkeypatch
):
    service, item, _checks, _launches = single_worker
    # This retained-page fixture has no persisted Flow; deliver its fixed synthetic inputs.
    application = service.store.applications.get_application(item["application_id"])
    monkeypatch.setattr(
        service.store,
        "single_material_source_provider",
        lambda *_: {
            "application": deepcopy(application),
            "sources": {"items": [], "revision": digest({"items": []})},
        },
    )
    runner, _page = retained_page(service, item)
    current = service.store.load()["jobs"][0]
    service.store.answers.put_answer(
        {"question": "Full name", "value": "Older library name", "scope": {}, "state": "confirmed"}
    )
    fields = [
        {
            "id": "name",
            "type": "text",
            "question": "Full name",
            "value": "Human edited name",
            "valid": True,
            "required": True,
            "options": [],
            "multiple": False,
        },
        {
            "id": "resume",
            "type": "file",
            "filename": current["filename"],
            "file_sha256": current["file_sha256"],
            "required": True,
            "resume": True,
            "multiple": False,
        },
    ]
    monkeypatch.setattr(runner, "observe", lambda *_: {"fields": deepcopy(fields)})
    service.request(
        "continue-current",
        {
            "application_id": item["application_id"],
            "controller": "synthetic-controller",
            "request_id": "continue-process",
        },
    )
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    state = service.store.load()
    # The original parser has been quiet across spaced observations.
    parser = state["jobs"][0]["form_state"]["parser"]
    parser.update(
        stable_since=parser["started_at"] - 2, last_sample_at=parser["started_at"] - 1, samples=3
    )
    service.store.save(state)
    runner.process(deepcopy(state["jobs"][0]), state["batch_id"])
    after = service.store.load()["jobs"][0]
    assert after["status"] == "needs_input" and after["reason"] == "form_differences"
    assert after["intent"] is None
    assert after["form_state"]["differences"][0]["current_value"] == "Human edited name"
    assert after["manual_fields"]["name"]["value"] == "Human edited name"
    assert after["manual_attachments"][0]["filename"] == current["filename"]
    assert not any(row.get("action") in {"fill", "select_file"} for row in after["observations"])


def test_success_text_does_not_reuse_an_earlier_response_for_a_new_unknown_submission(
    single_worker, monkeypatch
):
    service, item, _checks, _launches = single_worker
    runner, _page = retained_page(service, item)
    state = service.store.load()
    current = state["jobs"][0]
    current.update(status="ready_for_review", handed_off=True)
    binding = {
        "action": "manual_submit_observed",
        "kind": "manual_submit",
        "application_id": item["application_id"],
        "run_id": runner.run_id,
        "batch_id": state["batch_id"],
        "page_id": "retained-page",
    }
    current["observations"].extend(
        [
            binding | {"stage": "request", "request_id": "old"},
            binding | {"stage": "response", "request_id": "old", "http_status": 200},
            binding | {"stage": "request", "request_id": "new-unknown"},
        ]
    )
    service.store.save(state)
    monkeypatch.setattr(
        runner,
        "read_submission_page",
        lambda *_: {
            "url": current["job_url"],
            "messages": ["Your application has been submitted."],
            "has_form": False,
        },
    )
    service.request(
        "observe-result", {"application_id": item["application_id"], "request_id": "observe-latest"}
    )
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    after = service.store.load()["jobs"][0]
    assert after["submission_observation"]["conclusion"] == "unknown"
    assert after["manual_submission"] is None


@pytest.mark.parametrize(
    "target", ["other-graphql", "unbound-graphql", "other-exact", "other-page"]
)
def test_manual_final_operation_without_original_job_binding_never_records_success(
    single_worker, monkeypatch, target
):
    import json
    from types import SimpleNamespace

    service, item, _checks, _launches = single_worker
    runner, retained = retained_page(service, item)
    state = service.store.load()
    current = state["jobs"][0]
    current.update(status="ready_for_review", handed_off=True)
    service.store.save(state)
    retained.url = current["job_url"] + "/apply"
    if target == "other-page":
        retained.url = "https://jobs.lever.co/other/00000000-0000-0000-0000-000000000099/apply"
    runner.handed_off_pages.add(retained)

    class Request:
        method = "POST"
        frame = SimpleNamespace(page=retained)
        url = (
            "https://jobs.lever.co/api/graphql"
            if "graphql" in target
            else retained.url
            if target == "other-exact"
            else current["job_url"] + "/apply"
        )
        post_data_buffer = json.dumps(
            {
                "operationName": "SubmitApplication",
                "variables": {"jobId": "different-job"} if target == "other-graphql" else {},
            }
        ).encode()

    request = Request()
    # other-exact uses a different job's exact final URL on the original Page.
    if target == "other-exact":
        request.url = "https://jobs.lever.co/other/00000000-0000-0000-0000-000000000099/apply"
    runner._live_guard_request(SimpleNamespace(request=request, continue_=lambda: None))
    runner.transport(request, "response", 200)
    runner.transport(request, "requestfinished")
    monkeypatch.setattr(
        runner,
        "read_submission_page",
        lambda *_: {
            "url": "https://jobs.lever.co/other/confirmation",
            "messages": ["Your application has been submitted."],
            "has_form": False,
        },
    )
    service.request(
        "observe-result",
        {"application_id": item["application_id"], "request_id": "other-job-result"},
    )
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    after = service.store.load()["jobs"][0]
    assert after["submission_observation"]["conclusion"] == "unknown"
    assert after["manual_submission"] is None
    assert (
        service.store.applications.get_application(item["application_id"])["status"] == "drafting"
    )


@pytest.mark.parametrize("action", ["fill", "upload"])
def test_unknown_manual_submit_cannot_be_unlocked_by_continue(single_worker, monkeypatch, action):
    from types import SimpleNamespace

    service, item, _checks, _launches = single_worker
    runner, retained = retained_page(service, item)
    state = service.store.load()
    current = state["jobs"][0]
    current.update(status="ready_for_review", handed_off=True)
    service.store.save(state)
    retained.url = current["job_url"] + "/apply"
    runner.handed_off_pages.add(retained)

    class Request:
        method = "POST"
        url = retained.url
        frame = SimpleNamespace(page=retained)

    request = Request()
    runner._live_guard_request(SimpleNamespace(request=request, continue_=lambda: None))
    runner.transport(request, "requestfailed")
    monkeypatch.setattr(
        runner,
        "read_submission_page",
        lambda *_: {"url": retained.url, "messages": [], "has_form": True},
    )
    service.request(
        "observe-result",
        {"application_id": item["application_id"], "request_id": "manual-result-unknown"},
    )
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    before = deepcopy(service.store.load())
    pdf = Path(before["jobs"][0]["file_path"]).read_bytes()
    with pytest.raises(PortalDataError) as error:
        service.request(
            "continue-current",
            {
                "application_id": item["application_id"],
                "controller": "synthetic-controller",
                "request_id": "continue-after-unknown",
            },
        )
    assert error.value.code == "submission_result_unknown"
    assert service.store.load() == before
    assert Path(before["jobs"][0]["file_path"]).read_bytes() == pdf
    state = service.store.load()
    state["control"] = "running"
    state["jobs"][0].update(status="queued", handed_off=False)
    service.store.save(state)
    assert not runner.authorize(
        state["jobs"][0], state["batch_id"], {"action": action, "field_id": "new-field"}
    )


def test_proven_original_job_rejection_can_continue_without_retrying_submit(
    single_worker, monkeypatch
):
    from types import SimpleNamespace

    service, item, _checks, _launches = single_worker
    runner, retained = retained_page(service, item)
    state = service.store.load()
    current = state["jobs"][0]
    current.update(status="ready_for_review", handed_off=True)
    service.store.save(state)
    retained.url = current["job_url"] + "/apply"
    runner.handed_off_pages.add(retained)

    class Request:
        method = "POST"
        url = retained.url
        frame = SimpleNamespace(page=retained)

    request = Request()
    runner._live_guard_request(SimpleNamespace(request=request, continue_=lambda: None))
    runner.transport(request, "response", 422)
    runner.transport(request, "requestfinished")
    monkeypatch.setattr(
        runner,
        "read_submission_page",
        lambda *_: {
            "url": retained.url,
            "messages": ["Application could not be submitted."],
            "has_form": True,
        },
    )
    service.request(
        "observe-result",
        {"application_id": item["application_id"], "request_id": "proven-rejection"},
    )
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    assert service.store.load()["jobs"][0]["submission_observation"]["conclusion"] == "rejected"
    monkeypatch.setattr(runner, "observe", lambda *_: {"fields": []})
    service.request(
        "continue-current",
        {
            "application_id": item["application_id"],
            "controller": "synthetic-controller",
            "request_id": "continue-after-rejection",
        },
    )
    state = service.store.load()
    runner.commands(state)
    runner.persist(state)
    after = service.store.load()
    assert after["control"] == "running" and after["jobs"][0]["handed_off"] is False
    assert runner.authorize(
        after["jobs"][0], after["batch_id"], {"action": "fill", "field_id": "corrected-field"}
    )
    assert (
        len(
            [
                row
                for row in after["jobs"][0]["observations"]
                if row.get("stage") == "request" and row.get("kind") == "manual_submit"
            ]
        )
        == 1
    )


def test_old_job_manual_submit_transport_does_not_lock_new_current_job(single_worker):
    service, item, _checks, _launches = single_worker
    runner, old_page = retained_page(service, item)
    service.request(
        "skip-current", {"application_id": item["application_id"], "request_id": "skip-old-final"}
    )
    second = job(service, 2)
    second["single_binding"] = {"task_id": "new-current-task"}
    prepare(service, second)
    service.request("resume", {"controller": "synthetic-controller"})
    runner.transports.append(
        {
            "kind": "manual_submit",
            "stage": "request",
            "request_id": "old-manual",
            "application_id": item["application_id"],
            "run_id": runner.run_id,
        }
    )
    state = service.store.load()
    assert not runner.authorize(
        state["jobs"][0], state["batch_id"], {"action": "fill", "field_id": "old-field"}
    )
    assert service.store.load()["control"] == "running"
    assert runner.authorize(
        state["jobs"][1], state["batch_id"], {"action": "fill", "field_id": "new-field"}
    )
    assert runner.pages[item["application_id"]] is old_page


def test_continue_after_lost_page_reopens_the_job_on_a_new_run(single_worker):
    from career_evidence_graph.application_worker import start_run

    service, item, _checks, launches = single_worker
    retained_page(service, item)
    state = service.store.load()
    state["runtime"]["observed_at"] -= 60
    state["jobs"][0].update(
        status="needs_recheck",
        reason="browser_connection_unknown",
        form_state={"binding": {"page_id": "retained-page"}},
    )
    service.store.save(state)
    payload = {
        "application_id": item["application_id"],
        "controller": "synthetic-controller",
        "request_id": "continue-lost",
    }
    with pytest.raises(PortalDataError) as lost:
        service.request("continue-current", payload)
    assert lost.value.code == "page_lost"
    service.request("reopen-current", payload)
    after = service.store.load()
    job = after["jobs"][0]
    assert (job["status"], job["reason"], job["page_open"]) == ("queued", "", False)
    assert "form_state" not in job and job["form_history"][-1]["binding"]["page_id"]
    assert after["control"] == "running" and after["page_reopen"]["status"] == "pending"
    assert launches
    # The new run keeps the job queued so it opens a new page, instead of stopping it.
    run_id = start_run(service.store)
    after = service.store.load()
    assert after["control"] == "running" and after["jobs"][0]["status"] == "queued"
    assert (after["page_reopen"]["status"], after["page_reopen"]["run_id"]) == ("started", run_id)


def test_reopen_refuses_an_unknown_action(single_worker):
    service, item, _checks, _launches = single_worker
    intent = {"action": "upload", "attempt_id": "unknown-upload"}
    retained_page(service, item, intent=intent)
    state = service.store.load()
    state["runtime"]["observed_at"] -= 60
    state["jobs"][0].update(status="needs_recheck", reason="page_lost")
    service.store.save(state)
    with pytest.raises(PortalDataError) as refused:
        service.request(
            "reopen-current",
            {
                "application_id": item["application_id"],
                "controller": "synthetic-controller",
                "request_id": "reopen-unknown",
            },
        )
    assert refused.value.code == "page_lost"
    assert service.store.load()["jobs"][0]["intent"] == intent
