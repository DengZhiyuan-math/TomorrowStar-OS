"""Worker-to-native takeover uses JSON and lifecycle callbacks, never action wrappers."""

import hashlib
import json
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
from career_evidence_graph.application_page_scope import PAGE_SCOPE
from career_evidence_graph.application_worker import compact_native_runs, digest
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
        ("owned_browser_outer_timeout", True),
        ("owned_browser_outer_timeout", None),
    ],
)
def test_native_start_rereads_a_page_still_settling(native_page, monkeypatch, failure, starts):
    from playwright.sync_api import Error

    service, runner, page, ref, _, _ = native_page
    if not isinstance(failure, PortalDataError):
        failure = Error(failure or "owned_browser_read_timeout")
    real, attempts, started = runner.observe_assistance_context, [], []

    def observe(reference, **kwargs):
        attempts.append(1)
        if starts is None:
            # Still slow on the third read: the original error stops the start.
            raise failure
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
    if starts is None:
        with pytest.raises(Error) as refused:
            runner.start_native_assistance(ref, request_id="native-settling")
        assert refused.value is failure
        assert len(attempts) == 3 and started == []
    elif starts:
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
                state["runtime"]["observed_at"] = time.time() - PAGE_SCOPE.window - 4
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
                state["runtime"]["observed_at"] = time.time() - PAGE_SCOPE.window - 4
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


@pytest.mark.parametrize(
    ("field", "value", "allowed"),
    [
        ("Email", "saved@example.invalid", True),
        ("Email", "other@example.invalid", False),
        ("Email", "True", False),
        # Data-processing consent saved as "Yes" admits only the checked state.
        ("I consent to the processing of my personal data", "true", True),
        ("I consent to the processing of my personal data", "false", False),
        # No saved fact: neither state is the user's answer.
        ("Subscribe to newsletter", "true", False),
        ("Subscribe to newsletter", "false", False),
    ],
)
def test_native_set_value_admits_only_a_confirmed_fact_or_a_checked_state(
    native_page, monkeypatch, field, value, allowed
):
    from test_application_information import answer

    from career_evidence_graph._vendor import job_apply_store as helper

    service, runner, page, ref, calls, _ = native_page
    page.field_value = ""
    helper.atomic_write_json(
        service.store.answers.root / "answers.json",
        {
            "schemaVersion": 1,
            "answers": dict(
                [
                    answer("Email", "saved@example.invalid"),
                    answer("I consent to the processing of my personal data", " Yes "),
                ]
            ),
            "metadata": {},
        },
    )
    # The synthetic page also shows the consent and newsletter checkboxes.
    answers_for_page = service.store._native_assistance_answers

    def with_checkboxes(job, page_context):
        page_context = deepcopy(page_context)
        page_context["data"]["fields"] += [
            {"id": label, "label": label, "type": "checkbox", "value": "false"}
            for label in (
                "I consent to the processing of my personal data",
                "Subscribe to newsletter",
            )
        ]
        return answers_for_page(job, page_context)

    monkeypatch.setattr(service.store, "_native_assistance_answers", with_checkboxes)
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
            facts = {
                fact["fact"]: fact.get("value") for fact in kwargs["delivery"]["answers"]["facts"]
            }
            assert facts["data_processing_consent"] == " Yes "
            assert facts["email"] == "saved@example.invalid"
            call = {
                "call_id": "native-set-value",
                "tool": "browser_set_value",
                "arguments_digest": "b" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": kwargs["native_scope"],
                "native_ref": "fresh-native-ref",
                "field_hint": {"role": "checkbox", "name": field},
                "text_sha256": hashlib.sha256(value.encode()).hexdigest(),
            }
            admitted.append(kwargs["before_native_call"](call))
            row = service.store.load()["jobs"][0]["native_handoff_runs"][-1]
            recorded = [c["call_id"] for c in row["events"][-1]["receipt"].get("calls", [])]
            assert ("native-set-value" in recorded) is admitted[-1]
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-set-value")
    assert admitted == [allowed]


CONSENT = "I consent to the processing of my personal data"


@pytest.mark.parametrize(
    ("name", "relocation", "allowed"),
    [
        # 2026-11-03: the AX name of a radio is its option; the delivered control binds it.
        ("Yes", False, True),
        ("No", False, False),
        # Two questions each offer a bound "Yes": the name does not identify one fact.
        ("Yes", True, False),
        ("Maybe", False, False),
    ],
)
def test_native_set_value_admits_a_radio_option_through_its_delivered_control(
    native_page, monkeypatch, name, relocation, allowed
):
    from test_application_information import answer

    from career_evidence_graph._vendor import job_apply_store as helper

    service, runner, page, ref, calls, _ = native_page
    page.field_value = ""
    saved = [answer(CONSENT, "Yes"), answer("Are you willing to relocate?", "Yes")]
    helper.atomic_write_json(
        service.store.answers.root / "answers.json",
        {"schemaVersion": 1, "answers": dict(saved), "metadata": {}},
    )
    questions = [CONSENT] + (["Are you willing to relocate?"] if relocation else [])
    delivery_for_page = service.store.assistance_delivery

    def with_radios(expected_ref, *, page_context=None):
        page_context = deepcopy(page_context)
        page_context["data"]["fields"] += [
            {
                "id": f"q{index}-{option}",
                "label": option,
                "type": "radio",
                "question": question,
                "value": "false",
            }
            for index, question in enumerate(questions)
            for option in ("Yes", "No")
        ]
        return delivery_for_page(expected_ref, page_context=page_context)

    monkeypatch.setattr(service.store, "assistance_delivery", with_radios)
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
            facts = {
                fact["fact"]: fact.get("field_ids")
                for fact in kwargs["delivery"]["answers"]["facts"]
            }
            assert facts["data_processing_consent"] == ["q0-Yes", "q0-No"]
            call = {
                "call_id": "native-set-radio",
                "tool": "browser_set_value",
                "arguments_digest": "b" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": 1,
                "mutation": True,
                "semantic_verified": False,
                "scope": kwargs["native_scope"],
                "native_ref": "fresh-native-ref",
                "field_hint": {"role": "radio", "name": name},
                "text_sha256": hashlib.sha256(b"true").hexdigest(),
            }
            admitted.append(kwargs["before_native_call"](call))
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-set-radio")
    assert admitted == [allowed]


@pytest.mark.parametrize(
    ("option", "answer", "same"),
    [
        ("Mr.", "Mr", True),
        ("Switzerland ", "switzerland", True),
        ("Yes!", "yes", True),
        ("\u300c\u662f\u300d\u3002", "\u662f", True),
        ("  New   York ", "new york", True),
        ("Mrs", "Mr", False),
        ("Ms.", "Mr.", False),
        ("U.S.", "US", False),
    ],
)
def test_native_choice_key_ignores_only_case_whitespace_and_edge_punctuation(option, answer, same):
    from career_evidence_graph.application_worker_browser import _native_choice_key

    assert (_native_choice_key(option) == _native_choice_key(answer)) is same


@pytest.mark.parametrize(
    ("steps", "shown", "reopened", "allowed", "condition"),
    [
        # r6: a combobox whose AX name maps to one delivered confirmed fact may open.
        ([("combobox", "Salutation *")], "", False, [True], None),
        ([("combobox", "Favourite colour")], "", False, [False], "unbound_fact"),
        # Its option is admitted only after that observed click, by the exact answer.
        ([("combobox", "Salutation"), ("option", " mr. ")], "", False, [True, True], None),
        (
            [("combobox", "Salutation"), ("option", "Ms.")],
            "",
            False,
            [True, False],
            "option_not_fact",
        ),
        # 2026-11-03: an option differing only by edge punctuation is the answer.
        ([("combobox", "Salutation"), ("option", "(Mr)")], "", False, [True, True], None),
        (
            [("combobox", "Salutation"), ("option", "Mrs")],
            "",
            False,
            [True, False],
            "option_not_fact",
        ),
        # No owning combobox click precedes the option.
        ([("option", "Mr.")], "", False, [False], "option_owner_unproven"),
        # APP-11: a control named like sending the application is never clickable.
        ([("button", "Submit application")], "", False, [False], "submit_like"),
        ([("button", "Submit Application")], "", False, [False], "submit_like"),
        ([("link", "Apply now")], "", False, [False], "submit_like"),
        ([("", "Send")], "", False, [False], "submit_like"),
        ([("button", "Candidature : envoyer")], "", False, [False], "submit_like"),
        ([("button", "提交申请")], "", False, [False], "submit_like"),
        ([("button", "")], "", False, [False], "submit_like"),
        (
            [("combobox", "Salutation"), ("button", "Submit")],
            "",
            False,
            [True, False],
            "submit_like",
        ),
        # 2026-11-07, Ashby: any other named control is the agent's to click.
        ([("button", "No")], "", False, [True], None),
        ([("checkbox", "I agree to the privacy policy")], "", False, [True], None),
        # r7: the driver shows a placeholder, which the delivered context reads as empty.
        (
            [("combobox", "Salutation", "Please select"), ("option", "Mr.")],
            "",
            False,
            [True, True],
            None,
        ),
        # r7: a different existing choice on a retained page belongs to the user or page.
        ([("combobox", "Salutation", "Ms.")], "Ms.", False, [False], "existing_choice"),
        # r7: a shown choice equal to the confirmed fact may be reopened.
        ([("combobox", "Salutation", " mr. ")], "Mr.", False, [True], None),
        # r7: a pre-ledger refusal row between the expand and the option is no mutation.
        (
            [("combobox", "Salutation"), ("refusal", "Salutation"), ("option", "Mr.")],
            "",
            False,
            [True, True],
            None,
        ),
        # 2026-11-03: a page this run reopened shows its own default, unread as a
        # placeholder; it may open while it still shows what the Worker delivered.
        (
            [("combobox", "Salutation", "Select title..."), ("option", "Mr.")],
            "Select title...",
            True,
            [True, True],
            None,
        ),
        # The shown value changed since delivery: not the page default any more.
        (
            [("combobox", "Salutation", "Ms.")],
            "Select title...",
            True,
            [False],
            "shown_changed",
        ),
        # A retained page keeps the rule: a shown default is an existing choice.
        (
            [("combobox", "Salutation", "Select title...")],
            "Select title...",
            False,
            [False],
            "existing_choice",
        ),
    ],
)
def test_native_click_admits_a_delivered_combobox_and_its_confirmed_option(
    native_page, monkeypatch, capsys, steps, shown, reopened, allowed, condition
):
    from test_application_information import answer

    from career_evidence_graph._vendor import job_apply_store as helper

    service, runner, page, ref, calls, _ = native_page
    page.field_value = ""
    helper.atomic_write_json(
        service.store.answers.root / "answers.json",
        {"schemaVersion": 1, "answers": dict([answer("Salutation", "Mr.")]), "metadata": {}},
    )
    if reopened:
        # The Worker's own APP-13 record: this run reopened and observed the page.
        state = service.store.load()
        job = state["jobs"][0]
        state["page_reopen"] = {
            "request_id": "reopen-1",
            "application_id": job["application_id"],
            "status": "started",
            "run_id": runner.run_id,
            "at": time.time(),
        }
        job["page_observation"] = dict(job.get("page_observation") or {}, run_id=runner.run_id)
        service.store.save(state)
    delivery_for_page = service.store.assistance_delivery

    def with_combobox(expected_ref, *, page_context=None):
        page_context = deepcopy(page_context)
        page_context["data"]["fields"].append(
            {
                "id": "salutation",
                "label": "Salutation",
                "type": "combobox",
                "role": "combobox",
                "value": shown,
            }
        )
        return delivery_for_page(expected_ref, page_context=page_context)

    monkeypatch.setattr(service.store, "assistance_delivery", with_combobox)
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
            ledger = []
            for sequence, (role, name, *expected) in enumerate(steps, start=1):
                call = {
                    "call_id": f"native-click-{sequence}",
                    "tool": "browser_click",
                    "arguments_digest": "b" * 64,
                    "status": "awaiting_host",
                    "generation": 1,
                    "sequence": sequence,
                    "mutation": True,
                    "semantic_verified": False,
                    "scope": kwargs["native_scope"],
                    "native_ref": f"ref-{sequence}",
                    "field_hint": {"role": role, "name": name},
                }
                if expected:
                    call["expected_target"] = {"value": expected[0]}
                if role == "refusal":
                    # r7 ledgers the driver's own pre-ledger refusal; it was never sent.
                    call.update(
                        status="not_sent",
                        mutation=False,
                        refusal="handoff_existing_content",
                        field_hint={"role": "combobox", "name": name},
                        # r10: the core's hit-test diagnosis rides the refused row.
                        refusal_detail={"in_viewport": False, "point": {"x": 1, "y": 2}},
                    )
                    ledger.append(call)
                    continue
                kwargs["after_yield"](
                    {
                        "handoff_id": "native-run",
                        "generation": 1,
                        "phase": "active",
                        "revoked": False,
                        "active_calls": 0,
                        "local_tools_drained": True,
                        "return_ready": False,
                        "calls": [*ledger, call],
                    }
                )
                admitted.append(kwargs["before_native_call"](deepcopy(call)))
                ledger.append({**call, "status": "observed" if admitted[-1] else "not_sent"})
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-click")
    assert admitted == allowed
    log = capsys.readouterr().out
    denied = [line for line in log.splitlines() if "native_click_admission_denied" in line]
    assert [line.split('"condition": ')[1] for line in denied] == (
        [f'"{condition}"}}'] if condition else []
    )
    # Role and condition only: never the field name or a value.
    assert not any("Ms." in line or "Salutation" in line for line in denied)
    refused = [line for line in log.splitlines() if line.startswith("native_driver_refusal: ")]
    assert len(refused) == sum(step[0] == "refusal" for step in steps)
    for line in refused:
        assert json.loads(line.split(": ", 1)[1]) == {
            "tool": "browser_click",
            "role": "combobox",
            "code": "handoff_existing_content",
            "detail": {"in_viewport": False, "point": {"x": 1, "y": 2}},
        }


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

    def deliver_events(idle_ms=250):
        delivered.append("browser-events")
        if change == "pause":
            service.request("pause", {"controller": "synthetic-controller"})
        elif change == "page_replaced":
            runner.pages[ref["binding"]["application_id"]] = SimpleNamespace(
                context=page.context, url=page.url, is_closed=lambda: False
            )
        elif change == "expired_owner":
            state = service.store.load()
            state["runtime"]["observed_at"] = time.time() - PAGE_SCOPE.window - 4
            service.store.save(state)

    monkeypatch.setattr(runner, "pump", deliver_events)
    assert callbacks["pump"]() is (change == "unchanged")
    assert delivered == ["browser-events"]
    # An only-expired scope tries one bounded document re-read; a busy renderer
    # leaves it expired, so the pump still refuses (2026-11-04).
    assert calls == ([("busy_renderer_read", None)] if change == "expired_owner" else [])
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
                    "phase": "active",
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
                    "phase": "active",
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
    # Each distinct native call is stored once; every receipt is rebuilt from it.
    assert job["observations"][-1]["retired_native_handoff_runs"] == compact_native_runs(runs)


def test_unconfirmed_stop_is_only_reread_at_a_fixed_interval(native_page, monkeypatch):
    """An unknown stop is a read on later ticks, not a resend backing off to 30 s."""
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
    # Re-read every 2 s: still checked, but not on each tick and never backed off.
    assert stops == pytest.approx([1000.0, 1002.1, 1007.6])
    assert runner._assistance_run is not None


def test_codex_event_pump_does_not_idle_while_a_write_waits(native_page, monkeypatch):
    # The driver drops a write not admitted within 15 s; each idle wait delayed it.
    import career_evidence_graph.application_worker_browser as module

    _, runner, _, ref, _, _ = native_page
    waits = []
    monkeypatch.setattr(module, "pump_events", lambda context, ms: waits.append(ms))
    runner.context = object()
    runner.pump_codex_events(ref)
    assert waits and set(waits) == {5}
    runner.pump()
    assert waits[-1] == 250


def test_native_start_delivers_a_context_captured_before_a_slow_scope_read(
    native_page, monkeypatch
):
    """The status read behind the scope attestation (P95 5.9 s) and the pump before
    delivery (tick P95 1.2 s) outlast the 6 s window the captured context carries.
    The pump renewed the page observation, so the context follows it (real run
    2026-11-02: assistance_delivery_invalid, "Original-page JSON context expired")."""
    service, runner, _, ref, _, scope = native_page
    real_time, skew = time.time, [0.0]
    monkeypatch.setattr(time, "time", lambda: real_time() + skew[0])

    def discover(original, *, pump):
        skew[0] += 5.5  # the driver status read inside the attestation
        return deepcopy(scope["native_scope"])

    real_observe, real_pump, captured, renewed = (
        runner.observe_assistance_context,
        runner.pump_codex_events,
        [],
        [],
    )

    def observe(reference, **kwargs):
        context = real_observe(reference, **kwargs)
        captured.append(context["at"])
        return context

    def pump(reference, **kwargs):
        permitted = real_pump(reference, **kwargs)
        renewed.append(service.store.load()["jobs"][0]["page_observation"]["at"])
        skew[0] += 1.0  # the control tick and store read before the delivery check
        return permitted

    runner.cua.native_page_scope = discover
    monkeypatch.setattr(runner, "observe_assistance_context", observe)
    monkeypatch.setattr(runner, "pump_codex_events", pump)
    delivered = []

    class Adapter:
        def start_takeover(self, original, **kwargs):
            delivered.append(kwargs["delivery"])
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

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    runner.start_native_assistance(ref, request_id="slow-scope-read")
    context = delivered[0]["page_context"]
    assert context["at"] == context["observed_at"] == renewed[0]
    assert renewed[0] - captured[0] == pytest.approx(5.5, abs=0.5)


@pytest.mark.parametrize(
    ("failures", "outcome"),
    [
        (2, "admitted"),
        (3, "read_timeout"),
        ("changed", "page_observation_changed"),
        ("closed", "fatal"),
    ],
)
def test_material_admission_rereads_a_slow_page_and_refuses_only_that_delivery(
    native_page, monkeypatch, failures, outcome
):
    """2026-11-03: the CV admission's one page read timed out and revoked the takeover."""
    from playwright.sync_api import Error

    service, runner, page, ref, calls, _ = native_page
    reads, sealed, results = [], [], []
    original = runner.observe_assistance_context

    def observe(reference, *, after_stop=False):
        if not sealed:
            return original(reference, after_stop=after_stop)
        reads.append(after_stop)
        if failures == "changed":
            raise PortalDataError("page_observation_changed", "synthetic", 409)
        if failures == "closed":
            raise Error("Target page, context or browser has been closed")
        if len(reads) <= failures:
            raise Error("owned_browser_read_timeout")
        return {"document": "synthetic"}

    monkeypatch.setattr(runner, "observe_assistance_context", observe)
    monkeypatch.setattr(
        runner,
        "_prepare_native_material_call",
        lambda reference, call, context, **kwargs: {"sealed": context},
    )

    class Adapter:
        def start_takeover(self, original_ref, **kwargs):
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
            call = {
                "call_id": "native-cv",
                "tool": "browser_deliver_material",
                "status": "awaiting_host",
                "scope": kwargs["native_scope"],
            }
            sealed.append(True)
            try:
                results.append(kwargs["before_native_call"](call))
            except PortalDataError as error:
                results.append(error)
            except Error as error:
                results.append(error)
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-material-read")
    result = results[0]
    if outcome == "admitted":
        assert result == {"sealed": {"document": "synthetic"}}
        assert len(reads) == 3
        return
    if outcome == "fatal":
        # Not a slow read: the admission fails as before and the takeover is revoked.
        assert isinstance(result, Error) and len(reads) == 1
        return
    # Only this delivery is refused; the adapter treats the code as non-fatal.
    from career_evidence_graph.application_codex_assist import MATERIAL_DESTINATION_REFUSALS

    assert isinstance(result, PortalDataError)
    assert (result.code, result.condition) == (outcome, "page_read")
    assert result.code in MATERIAL_DESTINATION_REFUSALS
    assert len(reads) == 3


def test_a_slow_material_read_hands_on_a_context_that_follows_the_renewal(native_page, monkeypatch):
    """2026-11-05: Harmattan's CV admission read took long enough that its snapshot
    reached the delivery as an expired JSON context and revoked the takeover."""
    service, runner, _page, ref, _, _ = native_page
    sealed, received = [], []
    original = runner.observe_assistance_context

    def observe(reference, *, after_stop=False):
        if not sealed:
            return original(reference, after_stop=after_stop)
        page_id = service.store.load()["jobs"][0]["page_observation"]["page_id"]
        stale = time.time() - PAGE_SCOPE.window - 0.5
        return {
            "status": "captured",
            "binding": {"page_id": page_id},
            "at": stale,
            "observed_at": stale,
            "document": "synthetic",
        }

    monkeypatch.setattr(runner, "observe_assistance_context", observe)
    monkeypatch.setattr(
        runner,
        "_prepare_native_material_call",
        lambda reference, call, context, **kwargs: received.append(context) or {"ok": True},
    )

    class Adapter:
        def start_takeover(self, original_ref, **kwargs):
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
            sealed.append(True)
            kwargs["before_native_call"](
                {
                    "call_id": "native-cv",
                    "tool": "browser_deliver_material",
                    "status": "awaiting_host",
                    "scope": kwargs["native_scope"],
                }
            )
            return SimpleNamespace(run_id="adapter-native-run")

        def progress(self, run_id):
            return SimpleNamespace(status="ready", tools_revoked=False)

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-material-stale-context")
    assert received and time.time() - received[0]["at"] < 2
    assert received[0]["observed_at"] == received[0]["at"]


@pytest.mark.parametrize("failure", ["native_operation_timeout", "document_changed"])
def test_an_admission_retries_a_slow_scope_read_but_not_a_changed_document(
    native_page, monkeypatch, failure
):
    """2026-11-05: Harmattan's Name write was denied when one 2 s frame read in its
    scope check timed out, and the denial revoked the takeover."""
    _service, runner, _page, ref, _, _ = native_page
    original = runner.pump_codex_events
    failed, results = [], []

    attempts = []

    def pump(reference, *, document=None, after_stop=False, service_stop=True):
        if not service_stop:
            attempts.append(True)
        if not service_stop and not failed:
            failed.append(True)
            runner._permit_failure = failure
            return False
        return original(
            reference, document=document, after_stop=after_stop, service_stop=service_stop
        )

    monkeypatch.setattr(runner, "pump_codex_events", pump)

    class Adapter:
        def start_takeover(self, original_ref, **kwargs):
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
            results.append(
                kwargs["before_native_call"](
                    {
                        "call_id": "native-click",
                        "tool": "browser_click",
                        "status": "awaiting_host",
                        "scope": kwargs["native_scope"],
                        "field_hint": {"name": "Submit", "role": "button"},
                    }
                )
            )
            return SimpleNamespace(run_id="adapter-native-run")

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-admission-slow-read")
    assert failed == [True] and results == [False]  # a Submit button is never clickable
    # Only a slow read is checked again; a changed document is denied at once.
    assert len(attempts) == (1 if failure == "document_changed" else 2)


def test_a_native_admission_checks_its_scope_without_serving_the_stop(native_page):
    """2026-11-05: each admission's pump served the stop service, which asked the
    Adapter's progress again (1-4.7 s), and writes reached the driver too late."""
    _service, runner, _page, ref, _, _ = native_page
    served, inside = [], []

    def stop_service():
        served.append(bool(inside))

    class Adapter:
        def start_takeover(self, original_ref, **kwargs):
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
            inside.append(True)
            kwargs["before_native_call"](
                {
                    "call_id": "native-type",
                    "tool": "browser_type",
                    "status": "awaiting_host",
                    "scope": kwargs["native_scope"],
                    "field_hint": {"name": "Email", "role": "textbox"},
                    "text_sha256": "0" * 64,
                }
            )
            inside.clear()
            return SimpleNamespace(run_id="adapter-native-run")

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = stop_service
    runner.start_native_assistance(ref, request_id="native-no-stop-service")
    assert served and True not in served


@pytest.mark.parametrize("failure", ["owned_browser_read_timeout", "document_changed"])
def test_a_slow_start_check_is_retried_but_a_changed_document_is_not(
    native_page, monkeypatch, failure
):
    """2026-11-05: a takeover start failed as assistance_binding_changed on one slow
    2 s frame read, with nothing naming why."""
    service, runner, _page, ref, _, _ = native_page
    original = runner.pump_codex_events
    failed = []

    def pump(reference, *, document=None, after_stop=False, service_stop=True):
        if document is not None and not failed:
            failed.append(True)
            runner._permit_failure = failure
            return False
        return original(
            reference, document=document, after_stop=after_stop, service_stop=service_stop
        )

    monkeypatch.setattr(runner, "pump_codex_events", pump)

    class Adapter:
        def start_takeover(self, original_ref, **kwargs):
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
    if failure == "document_changed":
        with pytest.raises(PortalDataError) as error:
            runner.start_native_assistance(ref, request_id="native-start-changed")
        assert error.value.code == "assistance_binding_changed"
        return
    runner.start_native_assistance(ref, request_id="native-start-slow")
    assert failed == [True]
    assert service.store.load()["jobs"][0]["native_handoff_runs"][-1]["phase"] == "granted"


@pytest.mark.parametrize("change", ["unchanged", "document", "run"])
def test_granted_takeover_renews_an_observation_its_own_admission_let_expire(native_page, change):
    """2026-11-04: a CV file admission held the page thread 6.6 s; the next check saw
    only an expired runtime/page observation and revoked an unchanged takeover, so the
    cover letter's admission was refused (handoff_host_did_not_authorize)."""
    service, runner, page, ref, _, _ = native_page

    class Adapter:
        def start_takeover(self, original, **kwargs):
            self.pump = kwargs["pump"]
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

    adapter = runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-expired-own-work")
    assert service.store.load()["jobs"][0]["native_handoff_runs"][-1]["phase"] == "granted"
    # The first material's admission and delivery: the tick that would renew is late.
    stale = time.time() - PAGE_SCOPE.window - 0.6
    state = service.store.load()
    state["runtime"]["observed_at"] = stale
    state["jobs"][0]["page_observation"]["at"] = stale
    if change == "run":
        state["jobs"][0]["page_observation"]["run_id"] = "another-run"
    service.store.save(state)
    if change == "document":
        page.token = "a-new-document"
    # The next check came before any tick renewed the observation (the second
    # material's admission and the stop service both check directly).
    check = runner._assistance_page_checker(ref)[1]
    assert runner.assistance_read_permitted(ref) is (change == "unchanged")
    saved = service.store.load()
    if change == "unchanged":
        assert saved["runtime"]["observed_at"] > stale
        assert saved["jobs"][0]["page_observation"]["at"] > stale
        check()
        assert adapter.pump() is True
    else:
        assert saved["runtime"]["observed_at"] == stale
        with pytest.raises(PortalDataError) as caught:
            check()
        assert caught.value.code == "assistance_binding_changed"


def test_an_observation_current_when_looked_at_is_renewed_after_a_slow_reload(
    native_page, monkeypatch
):
    """2026-11-05: BCG's granted takeover was revoked at 6.4 s. The renewal check saw a
    still-current observation and declined; the check's own reload then let it pass."""
    from career_evidence_graph import application_worker_browser as browser

    service, runner, _page, ref, _, _ = native_page

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
            return SimpleNamespace(run_id="adapter-native-run")

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-slow-reload")
    seen = time.time() - PAGE_SCOPE.window + 0.1
    state = service.store.load()
    state["runtime"]["observed_at"] = seen
    state["jobs"][0]["page_observation"]["at"] = seen
    service.store.save(state)

    class Later:
        # The check's own clock reads after its slow reload: the window has passed.
        def __getattr__(self, name):
            return getattr(time, name)

        def time(self):
            return time.time() + 0.5

    monkeypatch.setattr(browser, "time", Later())
    check = runner._assistance_page_checker(ref)[1]
    check()
    saved = service.store.load()
    assert saved["runtime"]["observed_at"] > seen + PAGE_SCOPE.window - 0.1
    assert saved["jobs"][0]["page_observation"]["at"] > seen + PAGE_SCOPE.window - 0.1


@pytest.mark.parametrize("active_calls", [1, 0])
def test_an_admitted_native_call_in_progress_renews_without_a_renderer_read(
    native_page, active_calls
):
    """2026-11-04 (run 41): a CV delivery with active_calls 1 held the renderer; the 2 s
    document re-read could not answer and the takeover was revoked at 6.2 s."""
    from playwright.sync_api import Error

    service, runner, page, ref, calls, _ = native_page

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
            return SimpleNamespace(run_id="adapter-native-run")

    runner.codex_assist = Adapter()
    runner._service_assistance_stop = lambda: None
    runner.start_native_assistance(ref, request_id="native-active-call")
    stale = time.time() - PAGE_SCOPE.window - 0.2
    state = service.store.load()
    state["jobs"][0]["native_handoff_runs"][-1]["events"][-1]["receipt"]["active_calls"] = (
        active_calls
    )
    state["runtime"]["observed_at"] = stale
    state["jobs"][0]["page_observation"]["at"] = stale
    service.store.save(state)
    calls.clear()

    def busy_renderer(original):
        calls.append(("busy_renderer_read", None))
        raise Error("synthetic renderer is inside the native file delivery")

    page.context.new_cdp_session = busy_renderer
    assert runner.assistance_read_permitted(ref) is bool(active_calls)
    saved = service.store.load()
    if active_calls:
        assert calls == []
        assert saved["runtime"]["observed_at"] > stale
        assert saved["jobs"][0]["page_observation"]["at"] > stale
    else:
        assert calls == [("busy_renderer_read", None)]
        assert saved["runtime"]["observed_at"] == stale
