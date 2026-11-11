"""The fixture transport obeys the same final-action boundary as live adapters."""

from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from test_application_worker import job
from test_application_worker import service as service

from career_evidence_graph.application_worker_browser import ApplicationRunner


def test_fixture_transport_blocks_known_final_get_without_changing_checkpoint(service):
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = service.store.load()["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    page = object()
    runner.pages[current["application_id"]] = page
    request = SimpleNamespace(
        method="GET",
        url=service.fixture_origin + "/graphql?op=ApiSubmitSingleApplicationFormAction",
        post_data_buffer=None,
    )
    route = SimpleNamespace(request=request, outcome="")
    route.continue_ = lambda: setattr(route, "outcome", "allowed")
    route.abort = lambda _: setattr(route, "outcome", "blocked")

    runner._guard(current["application_id"])(route)

    assert route.outcome == "blocked"
    assert runner.blocked_pages[page] == "manual_submit_required"
    assert runner.sent_requests == set()
    assert service.store.load() == state


def test_final_after_escaped_block_string_cannot_hide_from_fixture_transport(service):
    service.request("prepare", {"jobs": [job(service)]})
    current = service.store.load()["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    query = (
        'mutation ApiSetFormValue { setFormValue(value: """prefix '
        + chr(92)
        + '""" suffix""") { id } '
        + 'submitSingleApplicationFormAction(value: """end""") { id } }'
    )
    request = SimpleNamespace(
        method="GET",
        url=service.fixture_origin + "/graphql?" + urlencode({"query": query}),
        post_data_buffer=None,
    )
    route = SimpleNamespace(request=request, outcome="")
    route.continue_ = lambda: setattr(route, "outcome", "allowed")
    route.abort = lambda _: setattr(route, "outcome", "blocked")

    runner._guard(current["application_id"])(route)

    assert route.outcome == "blocked"
    assert not runner.sent_requests


def test_read_alias_named_submit_is_not_a_final_action(service):
    service.request("prepare", {"jobs": [job(service)]})
    current = service.store.load()["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    request = SimpleNamespace(
        method="GET",
        url=service.fixture_origin
        + "/graphql?"
        + urlencode({"query": "query ApiJobPosting { jobPosting { submit: id } }"}),
        post_data_buffer=None,
    )
    route = SimpleNamespace(request=request, outcome="")

    def fetch(**kwargs):
        assert kwargs == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
        return SimpleNamespace(status=200, dispose=lambda: None)

    route.fetch = fetch
    route.fulfill = lambda **_: setattr(route, "outcome", "allowed")
    route.abort = lambda _: setattr(route, "outcome", "blocked")

    runner._guard(current["application_id"])(route)

    assert route.outcome == "allowed"
    assert not runner.blocked_pages


def test_late_write_response_failure_retains_attempt_and_invalidates_local_completion(service):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    current = service.store.load()["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    intent = {"action": "upload"}
    assert runner.authorize(current, service.store.load()["batch_id"], intent)
    current = service.store.load()["jobs"][0]
    request = type("Request", (), {"url": service.fixture_origin + "/upload", "method": "POST"})()
    assert runner.track_request(request, current, "resume_parse")
    runner.update(current, service.store.load()["batch_id"], intent=None, completed_intent=intent)
    assert intent in runner.verified_intents(service.store.load()["jobs"][0])

    runner.transport(request, "requestfailed")
    runner.persist(service.store.load())

    saved = service.store.load()["jobs"][0]
    assert saved["intent"] == intent
    assert saved["status"] == "needs_recheck"
    assert saved["reason"] == "upload_result_unknown"
    assert intent not in runner.verified_intents(saved)
    assert any(row.get("result") == "verified" for row in saved["observations"])
    assert not runner.track_request(request, saved, "resume_parse")


def test_completion_after_failed_write_does_not_clear_the_unknown_attempt(service):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    current = service.store.load()["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    page = object()
    runner.pages[current["application_id"]] = page
    intent = {"action": "upload"}
    assert runner.authorize(current, service.store.load()["batch_id"], intent)
    current = service.store.load()["jobs"][0]
    request = type("Request", (), {"url": service.fixture_origin + "/upload", "method": "POST"})()
    assert runner.track_request(request, current, "resume_parse")
    runner.transport(request, "requestfailed")
    runner.persist(service.store.load())

    runner.update(current, service.store.load()["batch_id"], intent=None, completed_intent=intent)

    saved = service.store.load()["jobs"][0]
    assert saved["intent"] == intent
    assert saved["status"] == "needs_recheck"
    assert intent not in runner.verified_intents(saved)


@pytest.mark.parametrize("conclusion", ["current_matches", "not_applied", "manual_stop"])
def test_late_failed_write_preserves_explicit_recovery(service, conclusion):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    current = state["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    intent = {"action": "upload"}
    assert runner.authorize(current, state["batch_id"], intent)
    current = service.store.load()["jobs"][0]
    request = type("Request", (), {"url": service.fixture_origin + "/upload", "method": "POST"})()
    assert runner.track_request(request, current, "resume_parse")
    service.request(
        "resolve-action",
        {
            "application_id": current["application_id"],
            "intent_ref": intent["attempt_id"],
            "conclusion": conclusion,
            "source": "Synthetic explicit readback",
        },
    )
    if conclusion != "manual_stop":
        service.request(
            "recheck", {"application_id": current["application_id"], "acknowledge": True}
        )
    before = service.store.load()["jobs"][0]

    runner.transport(request, "requestfailed")
    runner.persist(service.store.load())

    saved = service.store.load()["jobs"][0]
    assert saved["intent"] == before["intent"]
    assert saved["status"] == before["status"]
    assert saved["reason"] == before["reason"]
    assert saved["action_resolutions"] == before["action_resolutions"]
    assert runner.effective_action_results(saved)[intent["attempt_id"]]["conclusion"] == conclusion


def test_pending_failed_write_blocks_next_dispatch_before_checkpoint_drain(service):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    intent = {"action": "upload"}
    assert runner.authorize(state["jobs"][0], state["batch_id"], intent)
    current = service.store.load()["jobs"][0]
    request = type("Request", (), {"url": service.fixture_origin + "/upload", "method": "POST"})()
    assert runner.track_request(request, current, "resume_parse")
    runner.update(current, state["batch_id"], intent=None, completed_intent=intent)
    runner.transport(request, "requestfailed")
    assert not runner.permitted(service.store.load())
    next_intent = {"action": "fill", "field_id": "next-field"}

    assert not runner.authorize(service.store.load()["jobs"][0], state["batch_id"], next_intent)

    saved = service.store.load()["jobs"][0]
    assert saved["intent"] == intent
    assert saved["status"] == "needs_recheck"
    assert "attempt_id" not in next_intent
    assert service.store.load()["control"] == "running"


@pytest.mark.parametrize("status", [200, 307, 308])
def test_forwarded_response_is_released_on_success_and_rejected_redirect(service, status):
    service.request("prepare", {"jobs": [job(service)]})
    current = service.store.load()["jobs"][0]
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    page = object()
    runner.pages[current["application_id"]] = page
    disposed, forwarded = [], []
    response = SimpleNamespace(status=status, dispose=lambda: disposed.append(status))

    def fetch(**options):
        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
        forwarded.append("fetch")
        return response

    route = SimpleNamespace(
        request=SimpleNamespace(method="GET", url=service.fixture_origin + "/resource"),
        fetch=fetch,
        fulfill=lambda **_: forwarded.append("fulfill"),
        abort=lambda _: forwarded.append("abort"),
    )
    runner._guard(current["application_id"])(route)

    assert disposed == [status]
    assert forwarded == ["fetch", "fulfill" if status == 200 else "abort"]


@pytest.mark.parametrize(
    "changed_context", ["batch", "run", "active_attempt", "cancelled", "handed_off"]
)
def test_late_failed_write_keeps_new_context_and_manual_ownership(service, changed_context):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    intent = {"action": "upload"}
    assert runner.authorize(state["jobs"][0], state["batch_id"], intent)
    current = service.store.load()["jobs"][0]
    request = type("Request", (), {"url": service.fixture_origin + "/upload", "method": "POST"})()
    assert runner.track_request(request, current, "resume_parse")
    runner.update(current, state["batch_id"], intent=None, completed_intent=intent)
    state = service.store.load()
    current = state["jobs"][0]
    if changed_context == "batch":
        runner.requests[request]["batch_id"] = "previous-synthetic-batch"
    elif changed_context == "run":
        runner.requests[request]["run_id"] = "previous-synthetic-run"
    elif changed_context == "active_attempt":
        current["intent"] = {"action": "fill", "attempt_id": "new-synthetic-attempt"}
    elif changed_context == "cancelled":
        current["status"] = "cancelled"
    else:
        current["handed_off"] = True
    before = {key: current[key] for key in ("intent", "status", "reason", "handed_off")}
    service.store.save(state)

    runner.transport(request, "requestfailed")
    runner.persist(service.store.load())

    saved = service.store.load()["jobs"][0]
    assert {key: saved[key] for key in before} == before
    assert saved["observations"][-1]["stage"] == "requestfailed"


@pytest.mark.parametrize(
    "kind,status,unknown",
    [
        ("upload", 204, False),
        ("upload", 200, True),
        ("upload", 503, True),
        ("resume_parse", 204, True),
    ],
)
def test_bodyless_upload_ack_is_distinct_from_unknown_write(service, kind, status, unknown):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    intent = {"action": "upload"}
    assert runner.authorize(state["jobs"][0], state["batch_id"], intent)
    current = service.store.load()["jobs"][0]
    request = type("Request", (), {"url": service.fixture_origin + "/upload", "method": "POST"})()
    assert runner.track_request(request, current, kind)
    runner.update(current, state["batch_id"], intent=None, completed_intent=intent)
    runner.transport(request, "response", status)
    runner.transport(request, "requestfailed")

    runner.persist(service.store.load())

    saved = service.store.load()["jobs"][0]
    assert (saved["intent"] == intent) is unknown
    assert (saved["status"] == "needs_recheck") is unknown
    assert (intent in runner.verified_intents(saved)) is not unknown
    assert not runner.track_request(request, saved, kind)
