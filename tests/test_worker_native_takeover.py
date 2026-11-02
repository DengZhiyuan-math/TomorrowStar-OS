"""Worker-to-native takeover uses JSON and lifecycle callbacks, never action wrappers."""

import hashlib
import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_bound_material_delivery import bound_material_page as bound_material_page
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_codex_observation import owned_codex_page
from test_worker_native_assistance import journal_scope, native_service
from test_worker_native_material_journal import material_call as _material_journal

from career_evidence_graph import cua_driver
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError

material_journal = _material_journal


@pytest.fixture
def native_page(retained_assistance_page, monkeypatch, tmp_path, request):
    import test_worker_native_assistance as native_tests

    executable = tmp_path / "native-driver"
    executable.write_bytes(b"synthetic reviewed native driver")
    policy = {
        **native_tests.POLICY,
        "driver_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(native_tests, "POLICY", policy)
    monkeypatch.setattr(cua_driver, "_NATIVE_HANDOFF_DRIVER_SHA256", policy["driver_sha256"])
    service, identifier = retained_assistance_page
    service = native_service(service, monkeypatch)
    service, runner, page, ref, calls = owned_codex_page.__wrapped__((service, identifier), request)
    scope = journal_scope(service, ref)
    client = SimpleNamespace(
        native_session=True,
        failed=False,
        process=SimpleNamespace(poll=lambda: None),
        driver_sha256=policy["driver_sha256"],
        driver_executable=executable,
    )

    class Cua:
        def __init__(self):
            self.client = client

        def observe_owner(self, *, pump):
            return {"status": "accepted"}

        def native_page_scope(self, original, *, pump):
            assert original is page
            return deepcopy(scope["native_scope"])

    runner.cua = Cua()
    runner.native_assistance_policy = policy
    return service, runner, page, ref, calls, scope


def test_native_start_delivers_json_and_persists_before_grant(native_page):
    service, runner, page, ref, calls, _ = native_page
    observed = []

    class Adapter:
        def start_takeover(self, original, **kwargs):
            assert original == ref
            packet = kwargs["delivery"]
            assert packet["assistance_ref"] == ref
            assert packet["page_context"]["native_scope"]["application_ref_digest"] == digest(ref)
            assert "screenshot" not in packet["page_context"]
            kwargs["before_yield"](
                {
                    "application_ref_digest": digest(ref),
                    "scope": kwargs["native_scope"],
                    "request_id": kwargs["request_id"],
                }
            )
            prepared = service.store.load()["jobs"][0]["native_handoff_runs"][-1]
            assert prepared["phase"] == "prepared"
            kwargs["after_yield"](
                {"handoff_id": "native-run", "generation": 1, "local_tools_drained": True}
            )
            observed.append(packet)
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    result = runner.start_native_assistance(ref, request_id="native-start")
    assert result.run_id == "adapter-native-run"
    assert runner.pages[ref["binding"]["application_id"]] is page
    assert len(observed) == 1
    assert "screenshot" not in [name for name, _ in calls]
    assert service.store.load()["jobs"][0]["native_handoff_runs"][-1]["phase"] == "granted"


@pytest.mark.parametrize(
    ("failure", "starts"),
    [
        (PortalDataError("page_observation_changed", "synthetic", 409), True),
        (None, True),
        (PortalDataError("page_observation_failed", "synthetic", 409), False),
    ],
)
def test_native_start_rereads_a_page_still_settling(native_page, monkeypatch, failure, starts):
    from playwright.sync_api import Error

    service, runner, page, ref, _, _ = native_page
    failure = failure or Error("owned_browser_read_timeout")
    real, attempts, started = runner.observe_assistance_context, [], []

    def observe(reference, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            # A slow first read outlasts the observation window (2026-11-02: 7.4 s).
            state = service.store.load()
            state["runtime"]["observed_at"] -= 10
            for job in state["jobs"]:
                job["page_observation"]["at"] -= 10
            service.store.save(state)
            raise failure
        return real(reference, **kwargs)

    class Adapter:
        def start_takeover(self, original, **kwargs):
            started.append(original)
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    monkeypatch.setattr(runner, "observe_assistance_context", observe)
    runner.codex_assist = Adapter()
    if starts:
        runner.start_native_assistance(ref, request_id="native-settling")
        assert len(attempts) == 2 and started == [ref]
    else:
        with pytest.raises(PortalDataError) as refused:
            runner.start_native_assistance(ref, request_id="native-settling")
        assert refused.value.code == "page_observation_failed"
        assert len(attempts) == 1 and started == []


@pytest.mark.parametrize(
    "change", ["reload", "page_replaced", "expired_owner", "pause", "checkpoint_failure"]
)
def test_native_yield_rechecks_original_document_and_durable_intent(
    native_page, monkeypatch, change
):
    service, runner, page, ref, _, _ = native_page
    granted = []

    class Adapter:
        def start_takeover(self, original, **kwargs):
            if change == "reload":
                page.loader = "replacement-at-the-same-url"
            elif change == "page_replaced":
                runner.pages[ref["binding"]["application_id"]] = SimpleNamespace(
                    context=page.context, url=page.url, is_closed=lambda: False
                )
            elif change == "expired_owner":
                state = service.store.load()
                state["runtime"]["observed_at"] = time.time() - 10
                service.store.save(state)
            elif change == "pause":
                service.request("pause", {"controller": "synthetic-controller"})
            else:

                def unavailable(*args, **options):
                    raise OSError("synthetic checkpoint unavailable")

                monkeypatch.setattr(service.store, "record_native_handoff", unavailable)
            kwargs["before_yield"](
                {
                    "application_ref_digest": digest(ref),
                    "scope": kwargs["native_scope"],
                    "request_id": kwargs["request_id"],
                }
            )
            granted.append(True)
            raise AssertionError("a changed or unrecorded handover must never grant")

    runner.codex_assist = Adapter()
    with pytest.raises(OSError if change == "checkpoint_failure" else PortalDataError):
        runner.start_native_assistance(ref, request_id="changed-before-yield")
    assert granted == []
    assert not service.store.load()["jobs"][0].get("native_handoff_runs")


def test_native_scope_discovery_cannot_adopt_a_same_url_reload(native_page):
    service, runner, page, ref, _, scope = native_page

    def discover(original, *, pump):
        assert original is page
        page.loader = "new-document-during-native-discovery"
        return deepcopy(scope["native_scope"])

    runner.cua.native_page_scope = discover
    runner.codex_assist = SimpleNamespace(start_takeover=lambda *a, **kw: pytest.fail("grant"))
    with pytest.raises(PortalDataError, match="原页文档已改变"):
        runner.start_native_assistance(ref, request_id="scope-reloaded")
    assert not service.store.load()["jobs"][0].get("native_handoff_runs")


@pytest.mark.parametrize("change", ["old_protocol", "no_policy", "changed_binary"])
def test_native_start_never_upgrades_readonly_or_changed_driver(native_page, change):
    service, runner, _, ref, calls, _ = native_page
    runner.codex_assist = SimpleNamespace(start_takeover=lambda *a, **kw: pytest.fail("grant"))
    if change == "old_protocol":
        ref = {**ref, "protocol": "codex-assistance/v1", "page_writes_enabled": False}
    elif change == "no_policy":
        runner.native_assistance_policy = None
    else:
        runner.cua.client.driver_executable.write_bytes(b"changed candidate")
    with pytest.raises(PortalDataError, match="原生"):
        runner.start_native_assistance(ref, request_id="refused-before-capture")
    assert calls == []
    assert not service.store.load()["jobs"][0].get("native_handoff_runs")


@pytest.mark.parametrize(
    "change",
    [
        "valid",
        "other_field",
        "changed_answer",
        "changed_backend",
        "same_url_reload",
        "page_replaced",
        "expired_owner",
    ],
)
def test_native_mutation_is_recorded_only_after_current_field_and_scope_check(native_page, change):
    from test_application_information import answer

    from career_evidence_graph._vendor import job_apply_store as helper

    service, runner, page, ref, calls, _ = native_page
    page.field_value = ""
    helper.atomic_write_json(
        service.store.answers.root / "answers.json",
        {
            "schemaVersion": 1,
            "answers": dict([answer("Email", "saved@example.invalid")]),
            "metadata": {},
        },
    )
    admitted = []

    class Adapter:
        def start_takeover(self, original, **kwargs):
            kwargs["before_yield"](
                {
                    "application_ref_digest": digest(ref),
                    "scope": kwargs["native_scope"],
                    "request_id": kwargs["request_id"],
                }
            )
            kwargs["after_yield"](
                {"handoff_id": "native-run", "generation": 1, "local_tools_drained": True}
            )
            if change == "changed_answer":
                helper.atomic_write_json(
                    service.store.answers.root / "answers.json",
                    {
                        "schemaVersion": 1,
                        "answers": dict([answer("Email", "corrected@example.invalid")]),
                        "metadata": {},
                    },
                )
            elif change == "same_url_reload":
                page.loader = "replacement-before-awaiting-host-admission"
            elif change == "page_replaced":
                runner.pages[ref["binding"]["application_id"]] = SimpleNamespace(
                    context=page.context, url=page.url, is_closed=lambda: False
                )
            elif change == "expired_owner":
                state = service.store.load()
                state["runtime"]["observed_at"] = time.time() - 10
                service.store.save(state)
            elif change == "changed_backend":
                state = service.store.load()
                state["backend_authority"]["status"] = "revoked"
                state["backend_authority"]["revoked_at"] = time.time()
                service.store.save(state)
            call = {
                "call_id": "native-type",
                "tool": "browser_type",
                "arguments_digest": "b" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": kwargs["native_scope"],
                "native_ref": "fresh-native-ref",
                "field_hint": {
                    "role": "textbox",
                    "name": "Phone" if change == "other_field" else "Email",
                },
                "text_sha256": hashlib.sha256(b"saved@example.invalid").hexdigest(),
            }
            before_intent = service.store.load()["jobs"][0]["native_handoff_runs"][-1]
            before_scope_read = len(calls)
            try:
                admitted.append(kwargs["before_native_call"](call))
            except PortalDataError:
                admitted.append(False)
            if admitted[-1]:
                row = service.store.load()["jobs"][0]["native_handoff_runs"][-1]
                assert row["events"][-1]["receipt"]["calls"][0]["status"] == "awaiting_host"
            else:
                assert service.store.load()["jobs"][0]["native_handoff_runs"][-1] == before_intent
            if change == "same_url_reload":
                assert "Page.getFrameTree" in [name for name, _ in calls[before_scope_read:]]
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-preflight")
    assert admitted == [change == "valid"]


@pytest.mark.parametrize("change", ["unchanged", "pause", "page_replaced", "expired_owner"])
def test_native_control_pump_keeps_progress_while_renderer_scope_read_is_busy(
    native_page, monkeypatch, change
):
    from playwright.sync_api import Error

    service, runner, page, ref, calls, _ = native_page
    callbacks, delivered = {}, []

    class Adapter:
        def start_takeover(self, original, **kwargs):
            callbacks.update(kwargs)
            kwargs["before_yield"](
                {
                    "application_ref_digest": digest(ref),
                    "scope": kwargs["native_scope"],
                    "request_id": kwargs["request_id"],
                }
            )
            kwargs["after_yield"](
                {"handoff_id": "native-run", "generation": 1, "local_tools_drained": True}
            )
            return SimpleNamespace(run_id="adapter-native-run")

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-busy-pump")
    calls.clear()

    def busy_renderer(original):
        assert original is page
        calls.append(("busy_renderer_read", None))
        raise Error("synthetic renderer is inside the native input handler")

    monkeypatch.setattr(page.context, "new_cdp_session", busy_renderer)

    def deliver_events():
        delivered.append("browser-events")
        if change == "pause":
            service.request("pause", {"controller": "synthetic-controller"})
        elif change == "page_replaced":
            runner.pages[ref["binding"]["application_id"]] = SimpleNamespace(
                context=page.context, url=page.url, is_closed=lambda: False
            )
        elif change == "expired_owner":
            state = service.store.load()
            state["runtime"]["observed_at"] = time.time() - 10
            service.store.save(state)

    monkeypatch.setattr(runner, "pump", deliver_events)
    assert callbacks["pump"]() is (change == "unchanged")
    assert delivered == ["browser-events"]
    assert calls == []
    if change == "unchanged":
        assert service.store.load()["jobs"][0]["assistance"]["status"] == "claimed"


def test_returned_native_receipt_still_reconciles_an_observed_material_call(
    native_page, monkeypatch
):
    """A fast peer may return before any granted receipt shows its observed call."""
    service, runner, page, ref, _, _ = native_page
    reconciled = []
    monkeypatch.setattr(
        runner,
        "_reconcile_native_material",
        lambda reference, receipt, *, request_id: reconciled.append(deepcopy(receipt)),
    )

    class Adapter:
        def start_takeover(self, original, **kwargs):
            kwargs["before_yield"](
                {
                    "application_ref_digest": digest(ref),
                    "scope": kwargs["native_scope"],
                    "request_id": kwargs["request_id"],
                }
            )
            kwargs["after_yield"](
                {"handoff_id": "native-run", "generation": 1, "local_tools_drained": True}
            )
            kwargs["after_yield"](
                {
                    "handoff_id": "native-run",
                    "generation": 1,
                    "revoked": True,
                    "return_ready": True,
                    "local_tools_drained": True,
                    "active_calls": 0,
                    "calls": [],
                }
            )
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    runner.start_native_assistance(ref, request_id="native-return")
    assert service.store.load()["jobs"][0]["native_handoff_runs"][-1]["phase"] == "stopped"
    assert [row.get("revoked") for row in reconciled][-1] is True


def stop_native_run(native_page, *, turn="completed", error_code=None, lose_page=False):
    from career_evidence_graph.application_codex_assist import AssistRunProgress

    service, runner, page, ref, _, _ = native_page
    stops = []

    class Adapter:
        def progress(self, run_id):
            return AssistRunProgress(
                run_id=run_id,
                status="ready" if error_code is None else "unknown",
                error_code=error_code,
                tools_revoked=True,
                native_turn_id="native-turn",
                native_turn_status=turn,
            )

        def stop(self, run_id, *, request_id):
            stops.append(request_id)
            return AssistRunProgress(
                run_id=run_id,
                status="stopped",
                tools_revoked=True,
                local_tools_drained=True,
                process_stopped=True,
                native_turn_status=turn,
                stop_status="stopped",
            )

    if lose_page:
        original = runner.pages[ref["binding"]["application_id"]]
        runner.pages[ref["binding"]["application_id"]] = SimpleNamespace(
            context=page.context, url=page.url, is_closed=lambda: False
        )
    runner.codex_assist = Adapter()
    runner._assistance_run = ref, "adapter-native-run"
    runner._service_assistance_stop()
    if lose_page:
        runner.pages[ref["binding"]["application_id"]] = original
    assert stops == ["stop-adapter-native-run"]
    return service.store.load()["jobs"][0]["assistance"]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("completed", "native_turn_completed"),
        ("interrupted", "assistance_scope_lost"),
        ("failed", "assistance_scope_lost"),
        ("transport_failed", "assistance_scope_lost"),
        ("page_replaced", "assistance_scope_lost"),
    ],
)
def test_turn_completion_stop_records_native_turn_completed_reason(native_page, change, reason):
    assistance = stop_native_run(
        native_page,
        turn=change if change in {"interrupted", "failed"} else "completed",
        error_code="transport_failed" if change == "transport_failed" else None,
        lose_page=change == "page_replaced",
    )
    assert assistance["status"] == "stopped"
    assert assistance["active_writer"] == "codex"
    assert assistance["stop"]["reason"] == reason
    assert assistance["stop"]["stop_status"] == "stopped"


def test_after_stop_checker_requires_reclaimed_session_and_stopped_scope(native_page):
    service, runner, _, ref, _, _ = native_page
    client = runner.cua.client
    client.handoff_active = True
    reclaimed = []

    def resume_after_handoff(*, pump):
        assert pump == runner.pump
        reclaimed.append(True)
        client.handoff_active = False

    client.resume_after_handoff = resume_after_handoff

    # A live claimed scope keeps its original checker and is never post-stop.
    _, live = runner._assistance_page_checker(ref)
    live()
    _, after = runner._assistance_page_checker(ref, after_stop=True)
    with pytest.raises(PortalDataError):
        after()

    stop_native_run(native_page)
    _, live = runner._assistance_page_checker(ref)
    with pytest.raises(PortalDataError):
        live()
    _, after = runner._assistance_page_checker(ref, after_stop=True)
    with pytest.raises(PortalDataError, match="控制连接"):
        after()

    runner._reclaim_native_session()
    runner._reclaim_native_session()
    assert reclaimed == [True]
    after()
    assert runner.assistance_read_permitted(ref) is False

    state = service.store.load()
    state["jobs"][0]["material_edit"] = {"status": "preparing"}
    service.store.save(state)
    with pytest.raises(PortalDataError):
        after()


def test_after_stop_checker_accepts_only_a_continue_serial_advance(native_page):
    """A lost outcome save is re-verified after Continue; nothing else may change."""
    service, runner, _, ref, _, _ = native_page
    client = runner.cua.client
    client.handoff_active = False
    stop_native_run(native_page)
    state = service.store.load()
    state["resume_serial"] = state.get("resume_serial", 0) + 1
    service.store.save(state)
    _, after = runner._assistance_page_checker(ref, after_stop=True)
    after()
    state = service.store.load()
    state["jobs"][0]["file_sha256"] = "f" * 64
    service.store.save(state)
    with pytest.raises(PortalDataError):
        after()


def test_pending_material_intent_reconciles_after_stop_without_replay(
    material_journal, monkeypatch
):
    from test_worker_native_material_bridge import prepared_runner
    from test_worker_native_material_journal import sealed_receipt

    from career_evidence_graph.application_worker import (
        adopt_assistance_stop,
        assistance_reference,
        revoke_assistance,
    )

    runner, payload, journal = prepared_runner(material_journal)
    service, reference, scope, _, intent = journal
    observed = sealed_receipt(journal, "observed")
    service.store.record_native_handoff(
        reference, request_id="journal-run", phase="granted", scope=scope, receipt=observed
    )
    state = service.store.load()
    job = state["jobs"][0]
    assert revoke_assistance(job, reason="native_turn_completed", request_id="stop-run")
    assert adopt_assistance_stop(
        job,
        assistance_reference(job["assistance"]),
        {
            "tools_revoked": True,
            "local_tools_drained": True,
            "process_stopped": True,
            "native_turn_id": None,
            "native_turn_status": "completed",
            "stop_status": "stopped",
        },
        request_id="stop-run",
    )
    service.store.save(state)
    before = deepcopy(service.store.load()["jobs"][0]["native_handoff_runs"])
    target = deepcopy(observed["calls"][0]["target_descriptor"])
    target["value_empty"] = False
    actual = {
        "field": {"material_target": target, "valid": True, "aria_invalid": ""},
        "sha256": payload["sha256"],
        "size_bytes": payload["size_bytes"],
        "filename": None,
        "value": payload["text"],
    }
    checks, reads = [], []

    def checker(ref, *, after_stop=False):
        checks.append(after_stop)
        return None, lambda: None

    monkeypatch.setattr(runner, "_assistance_page_checker", checker)
    monkeypatch.setattr(
        runner, "_read_native_material_field", lambda *a, **kw: reads.append(kw) or actual
    )
    monkeypatch.setattr(
        runner, "_prepare_native_material_call", lambda *a, **kw: pytest.fail("replay")
    )
    assert runner._reconcile_native_material(
        reference, observed, request_id="journal-run", after_stop=True
    )
    current = service.store.load()["jobs"][0]
    assert checks and set(checks) == {True}
    assert [row.get("after_stop") for row in reads] == [True]
    assert current["intent"] is None
    assert intent in runner.verified_intents(current)
    assert current["native_handoff_runs"] == before
    assert current["assistance"]["status"] == "stopped"
    assert current["assistance"]["active_writer"] == "codex"


def dispatch_takeover(service, monkeypatch, *, code="unsupported_control", **changes):
    """Attach the agreed system dispatch record to the claimed native assistance."""
    from career_evidence_graph import application_worker as worker

    if not hasattr(worker, "request_takeover"):
        # Until the Worker owns `dispatch`, validate the remaining record unchanged.
        original = worker.valid_assistance

        def without_dispatch(assistance, application_id):
            if isinstance(assistance, dict):
                assistance = {k: v for k, v in assistance.items() if k != "dispatch"}
            return original(assistance, application_id)

        monkeypatch.setattr(worker, "valid_assistance", without_dispatch)
    state = service.store.load()
    assistance = state["jobs"][0]["assistance"]
    binding = assistance["binding"]
    assistance["dispatch"] = {
        "request_id": assistance["claim_request_id"],
        "blocker": {
            "code": code,
            "field_id": "country",
            "page_id": binding["page_id"],
            "run_id": binding["run_id"],
            "observed_at": time.time(),
        },
        "requested_at": time.time(),
        "continue_serial": state.get("resume_serial", 0),
        **changes,
    }
    service.store.save(state)
    return assistance["dispatch"]


class DispatchAdapter:
    def __init__(self, failure=None):
        self.starts, self.polled, self.failure = [], [], failure

    def start_takeover(self, original, **kwargs):
        self.starts.append((original, kwargs["request_id"]))
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(run_id="dispatched-run")

    def progress(self, run_id):
        assert self.failure is None, "a refused start has no run"
        self.polled.append(run_id)
        return SimpleNamespace(status="ready", tools_revoked=False)

    def stop(self, run_id, *, request_id):
        raise AssertionError("a refused start has no run to stop")

    def service_readonly(self):
        return None


def test_tick_starts_claimed_takeover_once(native_page, monkeypatch):
    service, runner, _, ref, _, _ = native_page
    dispatch_takeover(service, monkeypatch)
    adapter = runner.codex_assist = DispatchAdapter()
    for _ in range(3):
        runner.tick()
    # Each tick keeps supervising the one started run instead of starting another.
    assert set(adapter.polled) == {"dispatched-run"} and len(adapter.polled) >= 3
    assert adapter.starts == [(ref, "claim-readonly")]
    assert service.store.load()["jobs"][0]["assistance"]["status"] == "claimed"


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        ("adapter", "codex_app_server_unavailable"),
        ("playwright", "native_assistance_unavailable"),
        ("changed_binary", "native_assistance_unavailable"),
    ],
)
def test_dispatch_capability_failure_keeps_page_and_specific_reason(
    native_page, monkeypatch, failure, code
):
    from playwright.sync_api import Error

    service, runner, page, ref, _, _ = native_page
    dispatch_takeover(service, monkeypatch)
    before = service.store.load()["jobs"][0]
    policy = deepcopy(runner.native_assistance_policy)
    adapter = runner.codex_assist = DispatchAdapter(
        PortalDataError(code, "Codex 不可用。", 409)
        if failure == "adapter"
        else Error("synthetic renderer refused")
        if failure == "playwright"
        else None
    )
    if failure == "changed_binary":
        runner.cua.client.driver_executable.write_bytes(b"changed candidate")
    for _ in range(3):
        runner.tick()
    job = service.store.load()["jobs"][0]
    assistance = job["assistance"]
    assert len(adapter.starts) == (0 if failure == "changed_binary" else 1)
    assert assistance["dispatch"]["failed_code"] == code
    assert assistance["status"] == "stopped"
    assert assistance["stop"]["reason"] == "assistance_unavailable"
    assert assistance["stop"]["stop_status"] == "stopped"
    assert (job["status"], job["reason"]) == ("needs_recheck", code)
    assert job["page_open"] is True
    assert runner.pages[job["application_id"]] is page and not page.is_closed()
    material = ("file_path", "file_sha256", "filename", "answer_refs")
    assert {key: job[key] for key in material} == {key: before[key] for key in material}
    assert runner.native_assistance_policy == policy
    # No run is supervised: DispatchAdapter.progress fails the tick if a refused start is polled.
    assert not job.get("native_handoff_runs")


@pytest.mark.parametrize(
    ("turn", "expected"),
    [("interrupted", "assistance_scope_lost"), ("completed", None)],
)
def test_scope_lost_turn_sets_wait_reason(native_page, turn, expected):
    service = native_page[0]
    before = service.store.load()["jobs"][0]
    assistance = stop_native_run(native_page, turn=turn)
    job = service.store.load()["jobs"][0]
    if expected is None:
        assert (job["status"], job["reason"]) == (before["status"], before["reason"])
    else:
        assert assistance["stop"]["reason"] == expected
        assert (job["status"], job["reason"]) == ("needs_recheck", expected)


@pytest.mark.parametrize("change", ["no_dispatch", "stopped", "failed", "paused"])
def test_no_dispatch_without_dispatch_record_or_when_stopped(native_page, monkeypatch, change):
    from career_evidence_graph.application_worker import revoke_assistance

    service, runner, _, _, _, _ = native_page
    if change != "no_dispatch":
        dispatch_takeover(
            service,
            monkeypatch,
            **({"failed_code": "native_assistance_unavailable"} if change == "failed" else {}),
        )
    if change == "stopped":
        state = service.store.load()
        assert revoke_assistance(state["jobs"][0], reason="user_paused")
        service.store.save(state)
    elif change == "paused":
        state = service.store.load()
        state["control"] = "paused"
        service.store.save(state)
    adapter = runner.codex_assist = DispatchAdapter()
    for _ in range(2):
        runner.tick()
    assert adapter.starts == []
    if change == "stopped":
        # A paused dispatch that never started is acknowledged as stopped and waits.
        job = service.store.load()["jobs"][0]
        assert job["assistance"]["status"] == "stopped"
        assert (job["status"], job["reason"]) == ("needs_recheck", "assistance_paused")


def test_dispatch_failed_start_result_waits_with_its_code_without_retry(native_page, monkeypatch):
    from career_evidence_graph.application_codex_assist import AssistRunProgress

    service, runner, page, ref, _, _ = native_page
    dispatch_takeover(service, monkeypatch)
    starts, stops = [], []

    class Adapter(DispatchAdapter):
        def start_takeover(self, original, **kwargs):
            starts.append(kwargs["request_id"])
            return self.progress("failed-run")

        def progress(self, run_id):
            return AssistRunProgress(
                run_id=run_id, status="failed", error_code="version_unsupported"
            )

        def stop(self, run_id, *, request_id):
            stops.append(request_id)
            return AssistRunProgress(
                run_id=run_id,
                status="stopped",
                error_code="version_unsupported",
                tools_revoked=True,
                local_tools_drained=True,
                process_stopped=True,
                stop_status="stopped",
            )

    runner.codex_assist = Adapter()
    for _ in range(3):
        runner.tick()
    job = service.store.load()["jobs"][0]
    # A cleared run is not stopped again by later ticks.
    assert starts == ["claim-readonly"] and stops == ["stop-failed-run"]
    assert job["assistance"]["dispatch"]["failed_code"] == "version_unsupported"
    assert job["assistance"]["stop"]["reason"] == "assistance_unavailable"
    assert job["assistance"]["status"] == "stopped"
    assert (job["status"], job["reason"]) == ("needs_recheck", "version_unsupported")
    assert job["page_open"] is True and runner.pages[job["application_id"]] is page


def test_proven_stopped_run_is_cleared_but_same_claim_never_restarts(native_page, monkeypatch):
    from career_evidence_graph.application_codex_assist import AssistRunProgress

    service, runner, _, ref, _, _ = native_page
    dispatch_takeover(service, monkeypatch)
    turn = {"status": "running"}

    class Adapter(DispatchAdapter):
        def progress(self, run_id):
            if turn["status"] == "running":
                return SimpleNamespace(status="ready", tools_revoked=False)
            return AssistRunProgress(
                run_id=run_id,
                status="ready",
                tools_revoked=True,
                native_turn_id="native-turn",
                native_turn_status="interrupted",
            )

        def stop(self, run_id, *, request_id):
            return AssistRunProgress(
                run_id=run_id,
                status="stopped",
                tools_revoked=True,
                local_tools_drained=True,
                process_stopped=True,
                native_turn_status="interrupted",
                stop_status="stopped",
            )

    adapter = runner.codex_assist = Adapter()
    stops = []
    original_stop = adapter.stop
    adapter.stop = lambda run_id, **kw: stops.append(run_id) or original_stop(run_id, **kw)
    runner.tick()
    assert adapter.starts == [(ref, "claim-readonly")]
    turn["status"] = "interrupted"
    for _ in range(3):
        runner.tick()
    job = service.store.load()["jobs"][0]
    assert job["assistance"]["stop"]["reason"] == "assistance_scope_lost"
    assert job["assistance"]["stop"]["stop_status"] == "stopped"
    # The proven-stopped run is released: later ticks no longer stop it again.
    assert stops == ["dispatched-run"]
    assert adapter.starts == [(ref, "claim-readonly")]

    # A later, separately claimed takeover of the same reference is not blocked.
    state = service.store.load()
    assistance = state["jobs"][0]["assistance"]
    del assistance["stop"]
    assistance.update(status="claimed", claim_request_id="claim-second")
    assistance["dispatch"]["request_id"] = "claim-second"
    state["jobs"][0].update(status="filling", reason="")
    service.store.save(state)
    turn["status"] = "running"
    runner.tick()
    runner.tick()
    assert adapter.starts == [(ref, "claim-readonly"), (ref, "claim-second")]


@pytest.mark.parametrize("save", ["ok", "fails"])
def test_adapter_precheck_valueerror_is_capability_failure_not_storage_stop(
    native_page, monkeypatch, save
):
    service, runner, page, _, _, _ = native_page
    dispatch_takeover(service, monkeypatch)

    class Adapter(DispatchAdapter):
        def start_takeover(self, original, **kwargs):
            self.starts.append(kwargs["request_id"])
            if save == "fails":

                def unavailable(state):
                    raise ValueError("synthetic save failure")

                monkeypatch.setattr(service.store, "save", unavailable)
            raise ValueError("Codex assistance already has an unresolved run")

    adapter = runner.codex_assist = Adapter()
    for _ in range(3):
        runner.tick()
    assert adapter.starts == ["claim-readonly"]
    if save == "fails":
        # A real checkpoint write failure still takes the storage boundary.
        assert runner.storage_stopped is True
        return
    job = service.store.load()["jobs"][0]
    assert runner.storage_stopped is False
    assert job["assistance"]["dispatch"]["failed_code"] == "native_assistance_unavailable"
    assert job["assistance"]["stop"]["reason"] == "assistance_unavailable"
    assert (job["status"], job["reason"]) == ("needs_recheck", "native_assistance_unavailable")
    assert job["page_open"] is True and runner.pages[job["application_id"]] is page


class PendingAdapter(DispatchAdapter):
    def start_takeover(self, original, **kwargs):
        self.kwargs = kwargs
        return super().start_takeover(original, **kwargs)


@pytest.mark.parametrize("carried", [True, False], ids=["dispatch_ref", "no_dispatch_ref"])
def test_native_start_names_only_the_dispatched_pending_intent(native_page, monkeypatch, carried):
    """A script stop with an unknown result hands its kept intent to Codex by identity."""
    service, runner, _, ref, _, _ = native_page
    state = service.store.load()
    job = state["jobs"][0]
    binding = job["assistance"]["binding"]
    intent = {
        "action": "fill",
        "attempt_id": "script-country-attempt",
        "field_id": "country",
        "expected_value": "Switzerland",
        "executor": "playwright",
        "dispatch_state": "sent",
        "run_id": binding["run_id"],
        "page_id": binding["page_id"],
    }
    job["intent"] = intent
    service.store.save(state)
    dispatch_takeover(
        service,
        monkeypatch,
        code="browser_result_unknown",
        **({"pending_intent_ref": digest(intent)} if carried else {}),
    )
    adapter = runner.codex_assist = PendingAdapter()
    runner.start_native_assistance(ref, request_id="native-start")
    pending = adapter.kwargs["delivery"]["pending_actions"]
    assert [row["action_id"] for row in pending] == ["script-country-attempt"]
    assert pending[0]["source_ref"] == {"record": "intent"}
    assert adapter.kwargs["pending_action_id"] == ("script-country-attempt" if carried else None)


@pytest.mark.parametrize("case", ["retired", "running", "page_current"])
def test_reopen_retires_a_stopped_native_takeover_that_carried_calls(native_page, case):
    service, runner, page, ref, _, scope = native_page
    document = scope["document"]
    call = {
        "call_id": "native-read",
        "tool": "get_browser_state",
        "arguments_digest": "a" * 64,
        "status": "observed",
        "generation": 1,
        "sequence": 1,
        "mutation": False,
        "semantic_verified": False,
        "scope": {
            "target_id": "native-target",
            "tab_id": "native-tab",
            "expected_document": {key: document[key] for key in ("frame_id", "loader_id", "url")},
        },
    }

    class Adapter:
        def start_takeover(self, original, **kwargs):
            kwargs["before_yield"](
                {
                    "application_ref_digest": digest(ref),
                    "scope": kwargs["native_scope"],
                    "request_id": kwargs["request_id"],
                }
            )
            kwargs["after_yield"](
                {
                    "handoff_id": "native-run",
                    "generation": 1,
                    "revoked": True,
                    "return_ready": True,
                    "local_tools_drained": True,
                    "active_calls": 0,
                    "calls": [call],
                }
            )
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    runner.start_native_assistance(ref, request_id="native-reopen")
    if case != "running":
        stop_native_run(native_page)
    state = service.store.load()
    if case != "page_current":
        state["runtime"]["observed_at"] -= 60
    state["jobs"][0].update(status="needs_recheck", reason="browser_disconnected", page_open=False)
    service.store.save(state)
    runs = state["jobs"][0]["native_handoff_runs"]
    assert any((event["receipt"] or {}).get("calls") for run in runs for event in run["events"])
    payload = {
        "application_id": ref["binding"]["application_id"],
        "controller": "synthetic-controller",
        "request_id": "reopen-native",
    }
    if case != "retired":
        # A running takeover or a page still current keeps the original rule.
        with pytest.raises(PortalDataError) as refused:
            service.request("reopen-current", payload)
        assert refused.value.code == "page_lost"
        assert service.store.load()["jobs"][0]["native_handoff_runs"] == runs
        return
    service.request("reopen-current", payload)
    job = service.store.load()["jobs"][0]
    assert job["status"] == "queued" and job["native_handoff_runs"] == []
    assert "assistance" not in job and job["assistance_history"][-1]["status"] == "stopped"
    assert job["observations"][-1]["retired_native_handoff_runs"] == runs


def test_unconfirmed_stop_is_retried_with_backoff_not_every_tick(native_page, monkeypatch):
    from career_evidence_graph import application_worker_browser as browser
    from career_evidence_graph.application_codex_assist import AssistRunProgress

    _, runner, _, ref, _, _ = native_page
    stops, clock = [], [1000.0]
    monkeypatch.setattr(browser.time, "monotonic", lambda: clock[0])

    class Adapter:
        def progress(self, run_id):
            return AssistRunProgress(
                run_id=run_id, status="unknown", error_code="stop_unknown", tools_revoked=True
            )

        def stop(self, run_id, *, request_id):
            stops.append(clock[0])
            return AssistRunProgress(
                run_id=run_id,
                status="unknown",
                error_code="stop_unknown",
                tools_revoked=True,
                process_stopped=True,
                native_turn_status="idle",
                stop_status="unknown",
            )

    runner.codex_assist = Adapter()
    runner._assistance_run = ref, "adapter-native-run"
    for step in [0, 0.5, 0.6, 1.0, 1.5, 4.0]:
        clock[0] += step
        runner._service_assistance_stop()
    # Retried after 1 s, 2 s, then 4 s: still retried, but not on each tick.
    assert stops == pytest.approx([1000.0, 1001.1, 1003.6, 1007.6])
    assert runner._assistance_run is not None
