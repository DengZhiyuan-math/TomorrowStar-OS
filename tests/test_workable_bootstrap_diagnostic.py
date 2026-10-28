"""Offline diagnostic loop; no upstream JavaScript is executed and no I/O is dispatched.

Static evidence: careers.6901cd820c44d775.js SHA256
8d5032a52f953409af0afd95dd11b59095f20bedb669bb4dff32000bbf2cab0f.
API definitions near character offsets 573686/574299/576395 and account/job provider
calls near 724414/743103 establish public bootstrap GETs. Error component 83198
maps Network Error to network_error then the offline title near character offset 617702.
A blocked route is one possible network error; this fixture does not identify
which request actually failed in the retained private browser.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from test_workable_uploads import URL, setup_service

from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.workable_uploads import ResumeUpload

ACCOUNT = "https://apply.workable.com/api/v1/accounts/synthetic-employer?full=true"
JOB = "https://apply.workable.com/api/v2/accounts/synthetic-employer/jobs/SYNTHETIC1"
FORM = "https://apply.workable.com/api/v1/jobs/SYNTHETIC1/form"
JOBS = "https://apply.workable.com/api/v3/accounts/synthetic-employer/jobs"
# Main bundle has Rollbar's configured endpoint; no personal telemetry body is retained.
TELEMETRY = "https://api.rollbar.com/api/1/item/"


class SyntheticPage:
    url = URL

    def __init__(self):
        self.main_frame = SimpleNamespace(page=self)


@dataclass
class GuardDecision:
    method: str
    url: str
    outcome: str
    control: str
    intent: str
    lease_age: float
    blocked_reason: str


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    service = setup_service(tmp_path, monkeypatch)
    page = SyntheticPage()
    runner = ApplicationRunner(service.store, None)
    job = service.store.load()["jobs"][0]
    runner.pages[job["application_id"]] = page
    runner.page_ids[page] = "synthetic-bootstrap-page"
    runner.workable[page] = ResumeUpload(job)
    assert runner.authorize(job, service.store.load()["batch_id"], {"action": "open"})
    return service, runner, page


def decide(bootstrap, url, method="GET", body=None, resource="fetch", headers=None):
    service, runner, page = bootstrap
    request = SimpleNamespace(
        method=method,
        url=url,
        resource_type=resource,
        headers=headers or {"accept": "application/json", "accept-language": "en"},
        post_data_buffer=body,
        frame=page.main_frame,
        redirected_from=None,
        is_navigation_request=lambda: resource == "document",
    )
    route = SimpleNamespace(request=request, outcome="unset")
    route.continue_ = lambda: setattr(route, "outcome", "continued_without_network")
    route.fetch = lambda **_: SimpleNamespace(status=200, dispose=lambda: None)
    route.fulfill = lambda **_: setattr(route, "outcome", "continued_without_network")
    route.abort = lambda reason: setattr(route, "outcome", reason)
    runner._live_guard(route)
    state = service.store.load()
    return GuardDecision(
        method,
        url,
        route.outcome,
        state["control"],
        (state["jobs"][0]["intent"] or {}).get("action", ""),
        time.time() - state["heartbeat_at"],
        runner.blocked_pages.get(page, ""),
    )


def bootstrap_view(decisions):
    """Small explanatory view model, not an executed or rendered Workable client."""
    failed = any(d.outcome != "continued_without_network" for d in decisions)
    return {
        "title": "No internet connection." if failed else "Synthetic application form",
        "form_ready": not failed,
        "decisions": [vars(d) for d in decisions],
    }


def test_public_bootstrap_gets_are_available_in_a_fresh_open_intent(bootstrap):
    decisions = [decide(bootstrap, url) for url in (ACCOUNT, JOB, FORM)]
    shown = bootstrap_view(decisions)
    assert shown["form_ready"], shown
    assert all(not row.blocked_reason for row in decisions)


def test_denied_startup_telemetry_does_not_prevent_public_bootstrap(bootstrap):
    telemetry = decide(
        bootstrap,
        TELEMETRY,
        "POST",
        b'{"data":"synthetic"}',
        headers={"content-type": "application/json"},
    )
    assert telemetry.outcome == "blockedbyclient"
    decisions = [decide(bootstrap, url) for url in (ACCOUNT, JOB, FORM)]
    lease = bootstrap[0].store.load()["lease_seconds"]
    assert all(
        d.control == "running" and d.intent == "open" and 0 <= d.lease_age < lease
        for d in decisions
    )
    assert all(d.blocked_reason == "unverified_send_path" for d in decisions)
    shown = bootstrap_view(decisions)
    assert shown["form_ready"], (
        shown["title"],
        "form_ready=" + str(shown["form_ready"]),
        vars(telemetry),
        shown["decisions"],
    )


@pytest.mark.parametrize("method", ["POST", "OPTIONS"])
def test_unreviewed_non_get_dependencies_are_distinct_from_public_gets(bootstrap, method):
    decision = decide(
        bootstrap,
        JOBS,
        method,
        b"{}" if method == "POST" else None,
        headers={"content-type": "application/json"},
    )
    assert decision.outcome == "blockedbyclient"
    assert decision.blocked_reason == "unverified_send_path"


@pytest.mark.parametrize("change", ["expired_lease", "future_heartbeat", "paused", "not_open"])
@pytest.mark.parametrize("resource", ["fetch", "document"])
def test_new_public_get_respects_actual_control_and_intent_without_ui_age_gate(
    bootstrap, change, resource
):
    service, _, _ = bootstrap
    state = service.store.load()
    if change == "expired_lease":
        state["heartbeat_at"] -= state["lease_seconds"] + 1
    elif change == "future_heartbeat":
        state["heartbeat_at"] += state["lease_seconds"] + 1
    elif change == "paused":
        state["control"] = "paused"
    else:
        state["jobs"][0]["intent"] = None
    service.store.save(state)
    decision = decide(bootstrap, FORM if resource == "fetch" else URL, resource=resource)
    allowed = change in {"expired_lease", "future_heartbeat"}
    assert decision.outcome == ("continued_without_network" if allowed else "blockedbyclient"), (
        vars(decision)
    )


def test_retired_public_grant_cannot_authorize_unknown_workable_or_generic_request(bootstrap):
    service, runner, _ = bootstrap
    body = b'{"query":"synthetic public jobs read"}'
    (service.store.root / "public-read-grants.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "grants": [
                    {
                        "job_url": URL,
                        "url": JOBS,
                        "body_sha256": hashlib.sha256(body).hexdigest(),
                    }
                ],
            }
        )
    )
    decision = decide(bootstrap, JOBS, "POST", body, headers={"content-type": "application/json"})
    assert decision.outcome == "blockedbyclient"
    assert decision.blocked_reason == "unverified_send_path"
    generic = ApplicationRunner(service.store, None)
    page = bootstrap[2]
    generic.pages[service.store.load()["jobs"][0]["application_id"]] = page
    without_workable = decide(
        (service, generic, page), JOBS, "POST", body, headers={"content-type": "application/json"}
    )
    assert without_workable.outcome == "blockedbyclient"
    assert without_workable.blocked_reason == "unverified_send_path"
    for executor in (runner, generic):
        event = executor.transports[-1]
        assert event["stage"] == "request_blocked"
        assert event["purpose"] == "unknown"
        assert event["dispatch"] == "not_sent"


def test_previously_observed_exact_public_get_remains_readable_while_paused(bootstrap):
    service, _, _ = bootstrap
    assert decide(bootstrap, JOB).outcome == "continued_without_network"
    state = service.store.load()
    state["control"] = "paused"
    service.store.save(state)
    assert decide(bootstrap, JOB).outcome == "continued_without_network"
    assert decide(bootstrap, FORM).outcome == "blockedbyclient"


@pytest.mark.parametrize(
    "change",
    [
        "paused",
        "expired_lease",
        "future_heartbeat",
        "runtime_mismatch",
        "global_fault",
        "page_fault",
        "storage_stopped",
        "stop_marker",
        "other_blocked",
        "not_open",
        "fill_intent",
        "not_filling",
        "editing",
    ],
)
def test_sticky_discovery_preserves_required_guards_without_ui_age_gate(bootstrap, change):
    from career_evidence_graph.application_worker import start_run

    service, runner, page = bootstrap
    assert decide(bootstrap, TELEMETRY, "POST", b"{}").outcome == "blockedbyclient"
    state = service.store.load()
    if change == "paused":
        state["control"] = "paused"
    elif change == "expired_lease":
        state["heartbeat_at"] -= state["lease_seconds"] + 1
    elif change == "future_heartbeat":
        state["heartbeat_at"] += state["lease_seconds"] + 1
    elif change == "runtime_mismatch":
        run_id = start_run(service.store)
        state = service.store.load()
        state["jobs"][0]["status"] = "filling"
        runner.run_id = "different-from-" + run_id
    elif change == "global_fault":
        runner.shared_fault = "context_closed"
    elif change == "page_fault":
        runner.page_faults[page] = "page_crashed"
    elif change == "storage_stopped":
        runner.storage_stopped = True
    elif change == "stop_marker":
        service.store.block_storage()
    elif change == "other_blocked":
        runner.blocked_pages[page] = "upload_result_unknown"
    elif change == "not_open":
        state["jobs"][0]["intent"] = None
    elif change == "fill_intent":
        state["jobs"][0]["intent"]["action"] = "fill"
    elif change == "not_filling":
        state["jobs"][0]["status"] = "needs_recheck"
    elif change == "editing":
        runner.editing_pages.add(page)
    service.store.save(state)
    decision = decide(bootstrap, FORM)
    allowed = change in {"expired_lease", "future_heartbeat"}
    assert decision.outcome == ("continued_without_network" if allowed else "blockedbyclient"), (
        vars(decision)
    )


def test_public_get_recovery_keeps_sticky_automatic_action_stop(bootstrap):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, runner, page = bootstrap
    assert decide(bootstrap, TELEMETRY, "POST", b"{}").outcome == "blockedbyclient"
    assert decide(bootstrap, FORM).outcome == "continued_without_network"
    assert runner.blocked_pages[page] == "unverified_send_path"
    assert not runner.permitted(service.store.load(), page)
    job = service.store.load()["jobs"][0]
    with pytest.raises(PortalDataError) as error:
        runner.observe(page, job)
    assert error.value.code == "unverified_send_path"
    assert not runner.authorize(job, service.store.load()["batch_id"], {"action": "fill"})
    assert not runner.authorize(job, service.store.load()["batch_id"], {"action": "upload"})
    assert service.store.load()["jobs"][0]["intent"]["action"] == "open"


@pytest.mark.parametrize(
    "url,method",
    [
        (TELEMETRY, "POST"),
        (JOBS, "POST"),
        (JOBS, "OPTIONS"),
        (
            "https://apply.workable.com/api/v1/jobs/SYNTHETIC1/form/upload/resume?contentType=application%2Fpdf",
            "GET",
        ),
        ("https://apply.workable.com/api/v1/jobs/SYNTHETIC1/apply", "POST"),
        ("https://apply.workable.com/api/v1/jobs/SYNTHETIC1/autofill", "POST"),
    ],
)
def test_read_recovery_never_authorizes_send_or_resume_protocol(bootstrap, url, method):
    assert decide(bootstrap, TELEMETRY, "POST", b"{}").outcome == "blockedbyclient"
    assert decide(bootstrap, FORM).outcome == "continued_without_network"
    decision = decide(
        bootstrap,
        url,
        method,
        b"{}" if method == "POST" else None,
        headers={"content-type": "application/json"},
    )
    assert decision.outcome == "blockedbyclient", vars(decision)
