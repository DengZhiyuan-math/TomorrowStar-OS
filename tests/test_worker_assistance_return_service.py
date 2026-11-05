"""T08 return service: a stopped native turn returns only after reclaim and readback."""

import hashlib
import json
import time
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_native_takeover import native_page as native_page

from career_evidence_graph import application_form_runner as form_runner
from career_evidence_graph import application_worker_browser as browser
from career_evidence_graph.application_codex_assist import AssistRunProgress
from career_evidence_graph.application_worker import digest, script_writes_allowed

_ = native_page


def sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def field(identifier, label, value="", *, kind="text", required=False, **changes):
    return {
        "id": identifier,
        "name": identifier,
        "type": kind,
        "label": label,
        "value": value,
        "redacted": False,
        "required": required,
        "disabled": False,
        "readonly": False,
        "valid": None if kind == "combobox" else True,
        "aria_invalid": None,
        "visible": True,
        "files": [],
    } | changes


def baseline_fields():
    return [
        field("email", "Email", "synthetic@example.invalid", kind="email", required=True),
        field("country", "Country", kind="combobox", required=True),
        field("phone", "Phone", kind="tel", required=True),
    ]


def make_report(status="blocked_segment_resolved", **changes):
    claimed = {
        "status": status,
        "summary": "Country selected",
        "unresolved_action_ids": [],
        "fields": [{"field_id": "country", "state": "filled"}],
        # The Adapter's schema requires every property; it is null without a next field.
        "next_step": None,
    }
    if status == "blocked_segment_resolved":
        claimed["next_step"] = {"kind": "return_to_script", "field_id": "phone"}
    claimed |= changes
    return {
        "protocol": "assistance-report/v1",
        "request_id": "report-native-run",
        "native_turn_id": "native-turn",
        "received_at": time.time(),
        "claimed": claimed,
        "claimed_sha256": sha(claimed),
    }


def click(call_id, name, role="combobox"):
    return call_id, "browser_click", {"role": role, "name": name}


class Adapter:
    def __init__(self, page, client, *, planned, effect, report, final_status=None, stepwise=False):
        # stepwise publishes the ledger before each call, as the driver does, so an
        # option click's admission sees its observed combobox click.
        self.stepwise = stepwise
        self.page, self.client = page, client
        self.planned, self.effect = planned, effect
        self.report = report
        self.final_status = final_status or {}
        self.kwargs = None

    def start_takeover(self, original, **kwargs):
        self.kwargs = kwargs
        kwargs["before_yield"](
            {
                "application_ref_digest": digest(original),
                "scope": kwargs["native_scope"],
                "request_id": kwargs["request_id"],
            }
        )
        kwargs["after_yield"](
            {"handoff_id": "native-run", "generation": 1, "local_tools_drained": True}
        )
        self.client.handoff_active = True
        records = []
        for sequence, (call_id, tool, hint) in enumerate(self.planned, 1):
            call = {
                "call_id": call_id,
                "tool": tool,
                "arguments_digest": "c" * 64,
                "status": "awaiting_host",
                "generation": 1,
                "sequence": sequence,
                "mutation": True,
                "semantic_verified": False,
                "scope": kwargs["native_scope"],
                "native_ref": "native-ref-" + call_id,
                "field_hint": hint,
            }
            if self.stepwise:
                kwargs["after_yield"](
                    {
                        "handoff_id": "native-run",
                        "generation": 1,
                        "phase": "active",
                        "revoked": False,
                        "return_ready": False,
                        "local_tools_drained": True,
                        "active_calls": 0,
                        "calls": [*records, call],
                    }
                )
            assert kwargs["before_native_call"](call)
            records.append({**call, "status": self.final_status.get(call_id, "observed")})
        self.effect(self.page)
        unknown = any(row["status"] == "unknown" for row in records)
        kwargs["after_yield"](
            {
                "handoff_id": "native-run",
                "generation": 1,
                "phase": "returned",
                "revoked": True,
                "return_ready": not unknown,
                "local_tools_drained": True,
                "active_calls": 0,
                "calls": records,
            }
        )
        return SimpleNamespace(run_id="adapter-native-run")

    def progress(self, run_id):
        return AssistRunProgress(
            run_id=run_id,
            status="ready",
            tools_revoked=True,
            native_turn_id="native-turn",
            native_turn_status="completed",
            report=deepcopy(self.report),
        )

    def stop(self, run_id, *, request_id):
        return AssistRunProgress(
            run_id=run_id,
            status="stopped",
            tools_revoked=True,
            local_tools_drained=True,
            process_stopped=True,
            native_turn_id="native-turn",
            native_turn_status="completed",
            stop_status="stopped",
            report=deepcopy(self.report),
        )

    def service_readonly(self):
        return None


def select_country(page):
    page.fields[1]["value"] = "Switzerland"


@pytest.fixture
def returning(native_page, monkeypatch):
    from test_application_information import answer

    from career_evidence_graph._vendor import job_apply_store as helper

    service, runner, page, ref, calls, _ = native_page
    page.fields = baseline_fields()
    # r6: a combobox click is admitted only for a delivered confirmed answer.
    helper.atomic_write_json(
        service.store.answers.root / "answers.json",
        {
            "schemaVersion": 1,
            "answers": dict([answer("Country", "Switzerland"), answer("Team", "Engineering")]),
            "metadata": {},
        },
    )
    original = page.context.new_cdp_session

    def session(target):
        inner = original(target)

        class Session:
            def send(self, method, arguments=None):
                result = inner.send(method) if arguments is None else inner.send(method, arguments)
                if method == "Runtime.evaluate" and arguments.get("expression") != "this":
                    result["result"]["value"]["fields"] = deepcopy(page.fields)
                return result

            def detach(self):
                return inner.detach()

        return Session()

    page.context.new_cdp_session = session
    client = runner.cua.client
    client.handoff_active = False
    reclaimed = []

    def resume_after_handoff(*, pump):
        reclaimed.append(time.time())
        client.handoff_active = False

    client.resume_after_handoff = resume_after_handoff
    state = service.store.load()
    state["jobs"][0]["form_state"]["snapshot"] = {
        "fields": [
            {"id": "email", "type": "email", "question": "Email", "required": True},
            {"id": "country", "type": "combobox", "question": "Country", "required": True},
            {"id": "phone", "type": "tel", "question": "Phone", "required": True},
        ]
    }
    service.store.save(state)
    supported = {"executor": "playwright", "input_route": "dom", "route_reason": "test"}
    monkeypatch.setattr(runner, "_fill_route", lambda page, question: dict(supported))
    # The script's own form read; native trusted input appears in its activity.
    page.script_activity = {}
    monkeypatch.setattr(
        runner,
        "observe",
        lambda current, job: {
            "fields": [],
            "document_token": current.token,
            "user_activity": dict(current.script_activity),
        },
    )
    return SimpleNamespace(
        service=service, runner=runner, page=page, ref=ref, client=client, reclaimed=reclaimed
    )


COUNTRY_CLICK = (click("native-click", "Country"),)
BOTH_CALLS = (
    *COUNTRY_CLICK,
    ("native-type", "browser_click", {"role": "textbox", "name": "Phone"}),
)


def run_turn(ctx, *, report, planned=COUNTRY_CLICK, effect=select_country, **kw):
    adapter = Adapter(
        ctx.page, ctx.client, planned=list(planned), effect=effect, report=report, **kw
    )
    ctx.runner.codex_assist = adapter
    ctx.runner.start_native_assistance(ctx.ref, request_id="native-return")
    assistance = ctx.service.store.load()["jobs"][0]["assistance"]
    assert assistance["status"] == "stopped"
    assert assistance["stop"]["reason"] == "native_turn_completed"
    return adapter


def current(ctx):
    return ctx.service.store.load()["jobs"][0]


def assert_waiting(ctx, reason):
    job = current(ctx)
    assert job["status"] == "needs_recheck"
    assert job["reason"] == reason
    assert job["assistance"]["status"] == "stopped"
    assert job["assistance"]["active_writer"] == "codex"
    assert "outcome" not in job["assistance"]
    assert not script_writes_allowed(ctx.service.store.load())
    assert ctx.runner._assistance_run is None
    return job


EXPAND = click("native-click", "Country")
OPTION = click("native-option", "Switzerland", role="option")


def with_hidden_select(ctx):
    """Radix: an aria-hidden native select in the combobox's form item changes with it."""
    ctx.page.fields[1]["container_id"] = "country-form-item"
    ctx.page.fields.append(
        field(
            "country-native",
            "",
            kind="select-one",
            container_id="country-form-item",
            hidden=True,
            visible=False,
        )
    )


def select_country_and_twin(page):
    select_country(page)
    page.fields[-1]["value"] = "CH"


@pytest.mark.parametrize(
    ("planned", "hidden", "expected"),
    [
        # The option click set the value; its expand click only opened the list.
        ((EXPAND, OPTION), False, {"country": "native-option"}),
        # The hidden native select in the same form item follows the same option.
        ((EXPAND, OPTION), True, {"country": "native-option", "country-native": "native-option"}),
        # r13: a second click on the open combobox collapses it and touches nothing.
        ((EXPAND, click("native-collapse", "Country")), False, {"country": "native-click"}),
    ],
)
def test_option_clicks_attribute_to_their_combobox_and_its_hidden_twin(
    returning, planned, hidden, expected
):
    ctx = returning
    if hidden:
        with_hidden_select(ctx)
    run_turn(
        ctx,
        report=make_report(),
        planned=planned,
        effect=select_country_and_twin if hidden else select_country,
        stepwise=True,
    )
    ctx.runner._service_assistance_return()
    outcome = current(ctx)["assistance"]["outcome"]
    assert {row["field_id"]: row["call_id"] for row in outcome["attributed_fields"]} == expected


@pytest.mark.parametrize("hidden", [True, False])
def test_option_click_attributes_a_hidden_control_naming_the_same_fact(returning, capsys, hidden):
    # 2026-11-03: the hidden select sat in another container under its own name.
    ctx = returning
    ctx.page.fields[1].update(label="Country of residence", container_id="country-item")
    ctx.page.fields.append(
        field(
            "personal_details[country_of_residence]",
            "",
            kind="select-one",
            container_id="elsewhere",
            hidden=hidden,
            visible=not hidden,
        )
    )
    run_turn(
        ctx,
        report=make_report(),
        planned=(
            click("native-click", "Country of residence"),
            click("native-option", "Switzerland", role="option"),
        ),
        effect=select_country_and_twin,
        stepwise=True,
    )
    capsys.readouterr()
    ctx.runner._service_assistance_return()
    if hidden:
        outcome = current(ctx)["assistance"]["outcome"]
        assert {row["field_id"]: row["call_id"] for row in outcome["attributed_fields"]} == {
            "country": "native-option",
            "personal_details[country_of_residence]": "native-option",
        }
        return
    # A visible control is never bound by the fact mapping alone.
    assert_waiting(ctx, "assistance_return_unverified")
    line = next(
        row
        for row in capsys.readouterr().out.splitlines()
        if row.startswith("assistance_return_unverified: ")
    )
    record = json.loads(line.removeprefix("assistance_return_unverified: "))
    assert record["unattributed"] == ["personal_details[country_of_residence]"]


def test_unattributed_change_names_its_fields_without_values(returning, capsys):
    ctx = returning

    def change_email_too(page):
        select_country(page)
        page.fields[0]["value"] = "other@example.invalid"

    run_turn(
        ctx,
        report=make_report(),
        planned=(EXPAND, OPTION),
        effect=change_email_too,
        stepwise=True,
    )
    capsys.readouterr()
    ctx.runner._service_assistance_return()
    assert_waiting(ctx, "assistance_return_unverified")
    out = capsys.readouterr().out
    line = next(row for row in out.splitlines() if row.startswith("assistance_return_unverified: "))
    record = json.loads(line.removeprefix("assistance_return_unverified: "))
    assert record["reason"] == ["unattributed_change"]
    assert record["unattributed"] == ["email"]
    assert "other@example.invalid" not in out and "Switzerland" not in line


def test_complex_control_returns_to_script_only_after_drain_reclaim_and_readback(
    returning, monkeypatch
):
    ctx = returning
    run_turn(ctx, report=make_report())
    order = []
    runner = ctx.runner
    for name in ("adopt_assistance_report", "adopt_assistance_outcome"):
        original = getattr(browser, name)

        def recorded(*args, _name=name, _original=original, **kwargs):
            order.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(browser, name, recorded)
    for name in (
        "_reclaim_native_session",
        "_reconcile_native_material",
        "observe_assistance_context",
    ):
        original = getattr(runner, name)

        def recorded(*args, _name=name, _original=original, **kwargs):
            order.append((_name, kwargs.get("after_stop")))
            return _original(*args, **kwargs)

        monkeypatch.setattr(runner, name, recorded)

    runner.tick()

    assert order == [
        "adopt_assistance_report",
        ("_reclaim_native_session", None),
        ("_reconcile_native_material", True),
        ("observe_assistance_context", True),
        "adopt_assistance_outcome",
    ]
    assert len(ctx.reclaimed) == 1 and ctx.client.handoff_active is False
    job = current(ctx)
    assistance = job["assistance"]
    outcome = assistance["outcome"]
    assert assistance["status"] == "released"
    assert assistance["active_writer"] == "script"
    assert assistance["report"]["claimed"]["status"] == "blocked_segment_resolved"
    assert outcome["kind"] == "script_checkpoint"
    assert outcome["report_sha256"] == sha(assistance["report"])
    assert outcome["attributed_fields"] == [{"field_id": "country", "call_id": "native-click"}]
    assert outcome["checkpoint_field_id"] == "phone"
    assert outcome["return_count"] == 1 and job["assistance_return_count"] == 1
    assert (
        assistance["stop"]["observed_at"]
        <= outcome["session_reclaimed_at"]
        <= outcome["page_verification"]["at"]
        <= outcome["adopted_at"]
    )
    assert ctx.reclaimed[0] <= outcome["page_verification"]["at"]
    written = job["form_state"]["written_fields"]["country"]
    assert written["value"] == "Switzerland"
    assert written["source"] == {
        "source": "codex_native",
        "request_id": "native-return",
        "call_id": "native-click",
    }
    assert job["status"] == "filling"
    assert runner._assistance_run is None
    state = ctx.service.store.load()
    assert script_writes_allowed(state)
    assert runner.permitted(state)


HOSTED_SNAPSHOT = [
    {
        "id": "hosted-1",
        "control_ids": ["hosted-1-0"],
        "type": "email",
        "question": "Email",
        "required": True,
    },
    {
        "id": "hosted-2",
        "control_ids": ["hosted-2-0"],
        "type": "tel",
        "question": "Phone",
        "required": True,
    },
]


def hosted_snapshot(ctx):
    """The real form reader keys questions by hosted markers; Country is not enumerated."""
    state = ctx.service.store.load()
    state["jobs"][0]["form_state"]["snapshot"] = {"fields": deepcopy(HOSTED_SNAPSHOT)}
    ctx.service.store.save(state)


def report_next(field_id=None):
    report = make_report()
    if field_id is None:
        del report["claimed"]["next_step"]
    else:
        report["claimed"]["next_step"] = {"kind": "return_to_script", "field_id": field_id}
    report["claimed_sha256"] = sha(report["claimed"])
    return report


def test_return_maps_script_questions_with_hosted_ids_by_unique_label(returning, monkeypatch):
    """The real form reader keys its snapshot by hosted markers, not DOM ids.

    Email/tel rows carry no material target, so only the unique label links the
    page row to the script question; the custom combobox is not in the snapshot.
    """
    ctx = returning
    state = ctx.service.store.load()
    state["jobs"][0]["form_state"]["snapshot"] = {
        "fields": [
            {
                "id": "hosted-1",
                "control_ids": ["hosted-1-0"],
                "type": "email",
                "question": "Email",
                "required": True,
            },
            {
                "id": "hosted-2",
                "control_ids": ["hosted-2-0"],
                "type": "tel",
                "question": "Phone",
                "required": True,
            },
        ]
    }
    ctx.service.store.save(state)
    ctx.page.fields[2]["label"] = "Phone *"
    seen = []

    def route(page, question):
        seen.append(question["id"])
        return {"executor": "playwright", "input_route": "dom", "route_reason": "test"}

    monkeypatch.setattr(ctx.runner, "_fill_route", route)
    report = make_report()
    report["claimed"]["next_step"] = None
    report["claimed_sha256"] = sha(report["claimed"])
    run_turn(ctx, report=report)
    ctx.runner._service_assistance_return()
    job = current(ctx)
    outcome = job["assistance"]["outcome"]
    assert job["assistance"]["status"] == "released" and job["status"] == "filling"
    assert outcome["checkpoint_field_id"] == "hosted-2" and seen == ["hosted-2"]
    assert outcome["attributed_fields"] == [{"field_id": "country", "call_id": "native-click"}]


def test_next_step_dom_id_maps_to_script_question(returning):
    """Codex names the next field by its handoff page_context DOM id, not a hosted id."""
    ctx = returning
    hosted_snapshot(ctx)
    run_turn(ctx, report=report_next("phone"))
    ctx.runner._service_assistance_return()
    job = current(ctx)
    assert job["assistance"]["status"] == "released"
    assert job["assistance"]["outcome"]["checkpoint_field_id"] == "hosted-2"


@pytest.mark.parametrize("invalid", ["empty_left_for_script", "filled_value"])
def test_a_script_return_is_refused_only_by_an_invalid_value_on_the_page(returning, invalid):
    """2026-11-05: Harmattan's return to the script was refused because its required
    fields still left for the script were natively invalid while empty."""
    ctx = returning
    hosted_snapshot(ctx)

    def effect(page):
        select_country(page)
        if invalid == "empty_left_for_script":
            page.fields[2]["valid"] = False
        else:
            page.fields[0]["aria_invalid"] = "true"

    run_turn(ctx, report=report_next("phone"), effect=effect)
    ctx.runner._service_assistance_return()
    if invalid == "empty_left_for_script":
        job = current(ctx)
        assert job["assistance"]["status"] == "released"
        assert job["assistance"]["outcome"]["checkpoint_field_id"] == "hosted-2"
    else:
        assert_waiting(ctx, "assistance_return_unverified")


@pytest.mark.parametrize("field_id", ["fax", "email", "duplicate"])
def test_next_step_unknown_filled_or_ambiguous_field_refuses_return(returning, field_id):
    ctx = returning
    hosted_snapshot(ctx)
    if field_id == "duplicate":
        # Two page rows carry the same DOM name: the claim names no single question.
        ctx.page.fields.append(field("phone-2", "Phone", kind="tel", name="duplicate"))
        ctx.page.fields[2]["name"] = "duplicate"
    run_turn(ctx, report=report_next(field_id))
    ctx.runner._service_assistance_return()
    assert_waiting(ctx, "assistance_return_unverified")


def test_return_refuses_an_ambiguous_label_mapping(returning):
    state = returning.service.store.load()
    state["jobs"][0]["form_state"]["snapshot"] = {
        "fields": [
            {
                "id": f"hosted-{n}",
                "control_ids": [f"hosted-{n}-0"],
                "type": "tel",
                "question": "Phone",
                "required": True,
            }
            for n in (1, 2)
        ]
    }
    returning.service.store.save(state)
    report = make_report()
    del report["claimed"]["next_step"]
    report["claimed_sha256"] = sha(report["claimed"])
    run_turn(returning, report=report)
    returning.runner._service_assistance_return()
    assert_waiting(returning, "assistance_return_unverified")


def test_a_required_marker_on_the_native_field_name_still_attributes_it(returning):
    """2026-11-05: the page named Harmattan's fields "Name*" and "Email*" while their
    labels were "Name" and "Email"; both typed values read as unattributed."""
    ctx = returning
    run_turn(ctx, report=make_report(), planned=[click("native-click", "Country*")])
    ctx.runner._service_assistance_return()
    job = current(ctx)
    assert job["assistance"]["status"] == "released"
    assert job["assistance"]["outcome"]["attributed_fields"][0]["field_id"] == "country"


def test_return_acknowledges_native_trusted_input_on_attributed_field(returning):
    """Native typing is trusted input; after return the script must not see it as human."""
    ctx = returning

    def native_input(page):
        select_country(page)
        page.script_activity = {"country": 2}

    run_turn(ctx, report=make_report(), effect=native_input)
    ctx.runner._service_assistance_return()
    job = current(ctx)
    assert job["assistance"]["status"] == "released"
    assert job["form_state"]["ack_activity"] == {"country": 2}
    state = ctx.service.store.load()
    observed = ctx.runner.observe(ctx.page, job)
    form = form_runner.capture(ctx.runner, ctx.page, job, state["batch_id"], observed)
    assert not form.get("intervention_pending")
    # A later trusted edit on the same control is still a human intervention.
    ctx.page.script_activity = {"country": 3}
    observed = ctx.runner.observe(ctx.page, job)
    form = form_runner.capture(ctx.runner, ctx.page, job, state["batch_id"], observed)
    assert form["intervention_pending"] is True


def test_pause_during_running_turn_keeps_received_report_as_history_only(returning):
    """A report received before a pause stops the turn is history, never an outcome."""
    ctx = returning
    report = make_report()

    class RunningAdapter(Adapter):
        def progress(self, run_id):
            return AssistRunProgress(
                run_id=run_id,
                status="ready",
                tools_revoked=False,
                native_turn_id="native-turn",
                native_turn_status="running",
                report=deepcopy(self.report),
            )

        def stop(self, run_id, *, request_id):
            return AssistRunProgress(
                run_id=run_id,
                status="stopped",
                tools_revoked=True,
                local_tools_drained=True,
                process_stopped=True,
                native_turn_id="native-turn",
                native_turn_status="interrupted",
                stop_status="stopped",
                report=deepcopy(self.report),
            )

    ctx.runner.codex_assist = RunningAdapter(
        ctx.page, ctx.client, planned=list(COUNTRY_CLICK), effect=select_country, report=report
    )
    ctx.runner.start_native_assistance(ctx.ref, request_id="native-pause")
    assert "stop" not in current(ctx)["assistance"]
    ctx.service.request("pause", {"controller": "synthetic-controller"})
    for _ in range(3):
        ctx.runner.tick()
    assistance = current(ctx)["assistance"]
    assert assistance["status"] == "stopped" and assistance["active_writer"] == "codex"
    assert assistance["stop"]["reason"] == "user_paused"
    assert assistance["report"] == report
    assert "outcome" not in assistance and "superseded" not in assistance
    assert not script_writes_allowed(ctx.service.store.load())


def test_unattributed_field_change_blocks_return_as_human_edit(returning):
    def human_and_codex(page):
        select_country(page)
        page.fields[0]["value"] = "human@example.invalid"

    run_turn(returning, report=make_report(), effect=human_and_codex)
    returning.runner._service_assistance_return()
    job = assert_waiting(returning, "assistance_return_unverified")
    assert job["assistance"]["report"]["claimed"]["status"] == "blocked_segment_resolved"
    assert "written_fields" not in job["form_state"]


@pytest.mark.parametrize("change", ["navigation", "reload", "unknown_call"])
def test_navigation_or_pending_call_prevents_return_and_waits(returning, change):
    run_turn(
        returning,
        report=make_report(),
        final_status={"native-click": "unknown"} if change == "unknown_call" else None,
    )
    if change == "navigation":
        returning.page.url = returning.page.url + "/next"
    elif change == "reload":
        returning.page.loader = "replacement-loader"
    returning.runner._service_assistance_return()
    assert_waiting(returning, "assistance_return_unverified")


def test_second_return_is_refused_and_waits(returning):
    state = returning.service.store.load()
    state["jobs"][0]["assistance_return_count"] = 1
    returning.service.store.save(state)
    run_turn(returning, report=make_report())
    returning.runner._service_assistance_return()
    job = assert_waiting(returning, "assistance_return_unverified")
    assert job["assistance_return_count"] == 1


def test_next_field_unsupported_does_not_return(returning, monkeypatch):
    seen = []

    def route(page, question):
        seen.append(question["id"])
        if question["id"] == "phone":
            return {
                "executor": "manual",
                "input_route": None,
                "route_reason": "unsupported_control",
            }
        return {"executor": "playwright", "input_route": "dom", "route_reason": "test"}

    monkeypatch.setattr(returning.runner, "_fill_route", route)
    run_turn(returning, report=make_report())
    returning.runner._service_assistance_return()
    assert_waiting(returning, "assistance_return_unverified")
    assert "phone" in seen


def test_late_native_call_after_release_is_refused(returning):
    adapter = run_turn(returning, report=make_report())
    returning.runner._service_assistance_return()
    assert current(returning)["assistance"]["status"] == "released"
    before = deepcopy(current(returning)["native_handoff_runs"])
    late = {
        "call_id": "native-late",
        "tool": "browser_click",
        "arguments_digest": "d" * 64,
        "status": "awaiting_host",
        "generation": 1,
        "sequence": 9,
        "mutation": True,
        "semantic_verified": False,
        "scope": adapter.kwargs["native_scope"],
        "native_ref": "native-ref-late",
        "field_hint": {"role": "textbox", "name": "Phone"},
    }
    assert adapter.kwargs["before_native_call"](late) is False
    assert current(returning)["native_handoff_runs"] == before


def complete_page(ctx, *, resume=True):
    job = current(ctx)
    files = [{"name": job["filename"], "size": 10, "type": "application/pdf"}] if resume else []
    ctx.page.fields.append(field("resume", "Resume", kind="file", required=True, files=files))
    state = ctx.service.store.load()
    state["jobs"][0]["observations"].append(
        {
            "action": "action_result",
            "result": "verified",
            "intent": {
                "action": "upload",
                "attempt_id": "resume-upload",
                "kind": "resume",
                "sha256": state["jobs"][0]["file_sha256"],
            },
            "at": time.time(),
        }
    )
    state["jobs"][0]["form_state"]["snapshot"]["fields"].append(
        {"id": "resume", "type": "file", "question": "Resume", "required": True}
    )
    ctx.service.store.save(state)


def fill_everything(page):
    select_country(page)
    page.fields[2]["value"] = "+41 44 000 00 00"


def set_letter(ctx, **delivery):
    # The letter projection is set after the turn; its production lives elsewhere.
    state = ctx.service.store.load()
    state["jobs"][0]["cover_letter_delivery"] = {"selected_fields": [], **delivery}
    ctx.service.store.save(state)


def finish(ctx, report=None, before_return=None):
    run_turn(
        ctx,
        report=report or make_report("ready_for_review"),
        planned=BOTH_CALLS,
        effect=fill_everything,
    )
    if before_return is not None:
        before_return()
    ctx.runner._service_assistance_return()


def test_codex_filling_complete_saves_verified_result_and_ready_for_review(returning):
    complete_page(returning)
    finish(returning)
    job = current(returning)
    outcome = job["assistance"]["outcome"]
    assert job["assistance"]["status"] == "released"
    assert outcome["kind"] == "filling_complete"
    assert outcome["return_count"] == 0 and "checkpoint_field_id" not in outcome
    assert {row["field_id"] for row in outcome["attributed_fields"]} == {"country", "phone"}
    assert outcome["verified"]["optional_failures"] == []
    assert outcome["verified"]["materials"]
    assert all(
        not row["value_empty"] for row in outcome["page_verification"]["fields"] if row["required"]
    )
    assert job["status"] == "ready_for_review"
    assert not job.get("manual_submission")
    assert not job.get("handed_off")
    assert "人工提交" in (job.get("pending_sync") or "") or not job.get("sync_error")
    assert browser.assistance_completion(job) == outcome
    assert returning.runner._assistance_run is None


@pytest.mark.parametrize(
    "change", ["missing_attachment", "validation_error", "unknown_call", "running_cover_letter"]
)
def test_missing_attachment_validation_error_unknown_call_or_running_cover_letter_blocks_completion(
    returning, change
):
    complete_page(returning, resume=change != "missing_attachment")
    effect = fill_everything
    if change == "validation_error":

        def effect(page):
            fill_everything(page)
            page.fields[2]["aria_invalid"] = "true"

    run_turn(
        returning,
        report=make_report("ready_for_review"),
        planned=BOTH_CALLS,
        effect=effect,
        final_status={"native-type": "unknown"} if change == "unknown_call" else None,
    )
    if change == "running_cover_letter":
        set_letter(returning, status="running", requirement="optional")
    returning.runner._service_assistance_return()
    job = assert_waiting(returning, "assistance_completion_unverified")
    assert not job.get("manual_submission")


def test_optional_cover_letter_failure_is_kept_as_failure_item(returning):
    complete_page(returning)
    finish(
        returning,
        before_return=lambda: set_letter(
            returning,
            status="failed",
            requirement="optional",
            reason="unsupported_attachment_transport",
        ),
    )
    job = current(returning)
    assert job["status"] == "ready_for_review"
    assert job["assistance"]["outcome"]["verified"]["optional_failures"] == [
        {
            "material": "cover_letter",
            "status": "failed",
            "reason": "unsupported_attachment_transport",
        }
    ]


def test_ready_tick_and_review_use_verified_outcome_not_script_parser(returning, monkeypatch):
    complete_page(returning)
    finish(returning)
    runner, page, ref = returning.runner, returning.page, returning.ref
    identifier = ref["binding"]["application_id"]

    def script_parser(*args, **kwargs):
        raise AssertionError("script parser must not re-decide a Codex completion")

    monkeypatch.setattr(browser.form_flow, "capture", script_parser)
    monkeypatch.setattr(browser.form_flow, "check_ready", script_parser)
    monkeypatch.setattr(runner, "observe", script_parser)
    runner.tick()
    assert current(returning)["status"] == "ready_for_review"

    reviewed = []
    runner.cua.review = lambda original, *, pump: reviewed.append(original)
    runner.guards[identifier] = object()
    page.unroute = lambda pattern, guard: None
    page.bring_to_front = lambda: None
    state = returning.service.store.load()
    state["commands"].append({"action": "review", "id": identifier, "actor": "system"})
    returning.service.store.save(state)
    runner.tick()
    job = current(returning)
    assert reviewed == [page]
    assert job["handed_off"] is True
    assert job["handoff"]["source"] == "automatic_submit_wait"
    assert job["handoff"]["status"] == "complete"
    assert not job.get("manual_submission")


def test_prose_only_progress_without_report_never_completes(returning):
    complete_page(returning)
    run_turn(returning, report=None, effect=fill_everything)
    returning.runner._service_assistance_return()
    job = assert_waiting(returning, "assistance_return_unverified")
    assert "report" not in job["assistance"]
    assert job["status"] != "ready_for_review"


def test_lost_completion_save_keeps_app_record_for_the_same_resave(returning, monkeypatch):
    """The App sync follows the durable outcome; a lost save leaves the App unchanged."""
    ctx = returning
    identifier = ctx.ref["binding"]["application_id"]
    complete_page(ctx)
    before = ctx.service.store.applications.get_application(identifier)["revision"]
    save = ctx.service.store.save
    lost = []

    def lose_outcome_save(state):
        if (state["jobs"][0].get("assistance") or {}).get("outcome") and not lost:
            lost.append(True)
            raise OSError("synthetic outcome checkpoint write failure")
        return save(state)

    monkeypatch.setattr(ctx.service.store, "save", lose_outcome_save)
    stop = Adapter.stop

    def stop_after_reclaim(adapter, run_id, *, request_id):
        result = stop(adapter, run_id, request_id=request_id)
        if ctx.reclaimed:
            # The real Adapter cannot re-read a handoff the Worker took back.
            return replace(result, local_tools_drained=False)
        return result

    monkeypatch.setattr(Adapter, "stop", stop_after_reclaim)
    with pytest.raises(OSError):
        finish(ctx)
    assert lost and "outcome" not in current(ctx)["assistance"]
    assert ctx.service.store.applications.get_application(identifier)["revision"] == before
    monkeypatch.setattr(ctx.service.store, "save", save)
    for _ in range(3):
        # The lost save leaves the run pending; later ticks still service its stop.
        ctx.runner.tick()
    ctx.service.request("resume", {"controller": "synthetic-controller"})
    ctx.runner.tick()
    job = current(ctx)
    assert job["assistance"]["status"] == "released"
    assert job["status"] == "ready_for_review" and not job.get("sync_error")
    app = ctx.service.store.applications.get_application(identifier)
    assert job["revision"] == app["revision"] != before


def test_tick_dispatch_runs_one_takeover_and_returns_without_redispatch(returning, monkeypatch):
    from test_worker_native_takeover import dispatch_takeover

    ctx = returning
    dispatch_takeover(ctx.service, monkeypatch)
    adapter = Adapter(
        ctx.page,
        ctx.client,
        planned=list(COUNTRY_CLICK),
        effect=select_country,
        report=make_report(),
    )
    starts = []
    original = adapter.start_takeover

    def start(reference, **kwargs):
        starts.append(kwargs["request_id"])
        return original(reference, **kwargs)

    polled = []
    original_progress = adapter.progress
    adapter.progress = lambda run_id: polled.append(run_id) or original_progress(run_id)
    adapter.start_takeover = start
    ctx.runner.codex_assist = adapter
    ctx.runner.tick()
    job = current(ctx)
    assert starts == ["claim-readonly"]
    assert job["assistance"]["status"] == "released"
    assert job["assistance"]["outcome"]["kind"] == "script_checkpoint"
    supervised = len(polled)
    ctx.runner.tick()
    # The returned run is released: the next tick neither polls it nor starts another.
    assert len(polled) == supervised
    assert starts == ["claim-readonly"]


class RunningAdapter(Adapter):
    """A dispatched turn still running when a control stops it."""

    def progress(self, run_id):
        return AssistRunProgress(
            run_id=run_id,
            status="ready",
            tools_revoked=False,
            native_turn_id="native-turn",
            native_turn_status="running",
        )

    def stop(self, run_id, *, request_id):
        return AssistRunProgress(
            run_id=run_id,
            status="stopped",
            tools_revoked=True,
            local_tools_drained=True,
            process_stopped=True,
            native_turn_id="native-turn",
            native_turn_status="interrupted",
            stop_status="stopped",
        )


def test_pause_mid_takeover_waits_so_continue_lets_script_recheck(returning, monkeypatch):
    from test_worker_codex_assistance import block, expected
    from test_worker_native_takeover import dispatch_takeover

    ctx = returning
    dispatch_takeover(ctx.service, monkeypatch)
    adapter = ctx.runner.codex_assist = RunningAdapter(
        ctx.page, ctx.client, planned=[], effect=lambda page: None, report=make_report()
    )
    stops = []
    original_stop = adapter.stop
    adapter.stop = lambda run_id, **kw: stops.append(run_id) or original_stop(run_id, **kw)
    ctx.runner.tick()
    assert "stop" not in current(ctx)["assistance"]
    ctx.service.request("pause", {"controller": "synthetic-controller"})
    for _ in range(3):
        ctx.runner.tick()
    job = current(ctx)
    assert job["assistance"]["status"] == "stopped"
    assert job["assistance"]["stop"]["reason"] == "user_paused"
    assert (job["status"], job["reason"]) == ("needs_recheck", "assistance_paused")
    # The proven-stopped run is released: later ticks do not stop it again.
    assert stops == ["adapter-native-run"]

    ctx.service.request("resume", {"controller": "synthetic-controller"})
    job = current(ctx)
    assert "assistance" not in job
    assert [row["stop"]["reason"] for row in job["assistance_history"]] == ["user_paused"]
    assert script_writes_allowed(ctx.service.store.load())
    block(ctx.service, "unsupported_control")
    assert ctx.service.takeover_candidate(job["application_id"], **expected(ctx.service))


def unknown_country_intent(ctx):
    state = ctx.service.store.load()
    job = state["jobs"][0]
    snapshot = deepcopy(job["form_state"]["snapshot"]["fields"])
    observed = {key: snapshot[1].get(key) for key in ("id", "type", "question", "options")}
    observed["required"] = snapshot[1]["required"]
    job["intent"] = {
        "form_protocol": "form-state/v1",
        "action": "fill",
        "attempt_id": "unknown-country",
        "field_id": "country",
        "field_type": "combobox",
        "field_shape": browser.digest(observed),
        "before_value": "",
        "expected_value": "Switzerland",
        "dispatch_state": "returned",
        "run_id": ctx.runner.run_id,
        "page_id": ctx.runner.page_ids[ctx.page],
        "form_binding": {"document_token": ctx.page.token, "step": ctx.page.url},
    }
    job.update(status="needs_recheck", reason="action_result_unknown")
    ctx.service.store.save(state)
    return snapshot, deepcopy(job["intent"])


@pytest.mark.parametrize("settled", [True, False])
def test_unknown_result_takeover_settles_referenced_intent_by_readback_without_replay(
    returning, monkeypatch, settled
):
    from test_worker_native_takeover import dispatch_takeover

    ctx = returning
    snapshot, intent = unknown_country_intent(ctx)
    dispatch_takeover(
        ctx.service, monkeypatch, code="action_result_unknown", pending_intent_ref=digest(intent)
    )
    reads = []

    def observe(page, job):
        reads.append(job["intent"] and job["intent"]["attempt_id"])
        # The script's own readback of the retained page; without it the result stays unknown.
        values = {row["id"]: row["value"] for row in page.fields}
        fields = [
            {**row, "value": values[row["id"]], "valid": True}
            for row in snapshot
            if settled or row["id"] != "country"
        ]
        return {
            "fields": fields,
            "document_token": page.token,
            "user_activity": dict(page.script_activity),
        }

    monkeypatch.setattr(ctx.runner, "observe", observe)
    monkeypatch.setattr(
        browser.form_flow, "fill_field", lambda *a, **kw: pytest.fail("replayed"), raising=False
    )
    adapter = Adapter(
        ctx.page,
        ctx.client,
        planned=list(COUNTRY_CLICK),
        effect=select_country,
        report=make_report(),
    )
    ctx.runner.codex_assist = adapter
    ctx.runner.tick()
    job = current(ctx)
    assert adapter.kwargs["request_id"] == "claim-readonly"
    assert "unknown-country" in reads
    if settled:
        assert job["intent"] is None
        resolution = job["action_resolutions"][-1]
        assert (resolution["intent_ref"], resolution["conclusion"]) == (
            "unknown-country",
            "current_matches",
        )
        assert resolution["source"] == "retained_original_page"
        assert job["assistance"]["status"] == "released"
        assert job["assistance"]["outcome"]["kind"] == "script_checkpoint"
    else:
        assert job["intent"] == intent
        assert job["assistance"]["status"] == "stopped"
        assert (job["status"], job["reason"]) == ("needs_recheck", "assistance_pending_intent")
        assert "outcome" not in job["assistance"]


@pytest.mark.parametrize(
    ("report", "reason"),
    [
        (make_report(status="needs_recheck"), "claimed_status"),
        (report_next("fax"), "next_step_question_unknown"),
    ],
    ids=["needs_recheck_claim", "unknown_next_field"],
)
def test_refused_return_names_its_check_in_the_private_log(returning, capsys, report, reason):
    """The job keeps only assistance_return_unverified; the private log says which
    check refused (2026-11-02: a real needs_recheck return left nothing on disk)."""
    ctx = returning
    hosted_snapshot(ctx)
    run_turn(ctx, report=report)
    capsys.readouterr()
    ctx.runner._service_assistance_return()
    assert_waiting(ctx, "assistance_return_unverified")
    line = next(
        row
        for row in capsys.readouterr().out.splitlines()
        if row.startswith("assistance_return_unverified: ")
    )
    record = json.loads(line.removeprefix("assistance_return_unverified: "))
    assert record["check"] == "assistance_outcome_unverified"
    assert record["reason"] == [reason]
    assert record["claimed_status"] == report["claimed"]["status"]
    assert record["field_states"] == [["filled", 1]]
    assert record["where"][-1].startswith("application_worker_browser:refused:")
    assert any(
        frame.startswith("application_worker_browser:_assistance_outcome:")
        for frame in record["where"]
    )


def test_return_rereads_a_slow_post_stop_page_without_owner_reads(returning, monkeypatch):
    """A post-stop read that timed out is retried as a stopped scope; the check
    between reads is not the live claim check (2026-11-03: every retry was refused
    as assistance_binding_changed while the observation was current)."""
    from playwright.sync_api import Error

    ctx = returning
    run_turn(ctx, report=make_report())
    runner, real, attempts, owners = ctx.runner, ctx.runner.observe_assistance_context, [], []

    def observe(reference, **kwargs):
        attempts.append(kwargs.get("after_stop"))
        if len(attempts) == 1:
            raise Error("owned_browser_read_timeout")
        return real(reference, **kwargs)

    def observe_owner(*, pump):
        owners.append(True)
        return {"status": "accepted"}

    monkeypatch.setattr(runner, "observe_assistance_context", observe)
    monkeypatch.setattr(runner.cua, "observe_owner", observe_owner, raising=False)
    runner._service_assistance_return()
    assert attempts == [True, True]
    # The reclaim re-bound the owner; the post-stop read spends no driver state read.
    assert owners == []
    job = current(ctx)
    assert job["assistance"]["status"] == "released"
    assert job["assistance"]["outcome"]["kind"] == "script_checkpoint"
    assert job["status"] == "filling"


def zero_question_page(ctx):
    """An ATS page the script parser could not read: no script question exists."""
    state = ctx.service.store.load()
    state["jobs"][0]["form_state"]["snapshot"] = {"fields": []}
    ctx.service.store.save(state)
    ctx.page.fields.append(field("team", "Team", kind="combobox", required=True))


def fill_native_only(page):
    fill_everything(page)
    # The page-context read reports a button combobox's shown choice as its value.
    page.fields[3]["value"] = "Engineering"
    page.fields.append(
        field(
            "cv",
            "Lebenslauf",
            kind="file",
            required=True,
            files=[{"name": page.resume_name, "size": 10, "type": "application/pdf"}],
        )
    )


def fill_native_cleared_cv(page):
    """r11: the upload widget cleared its input after change and shows the name elsewhere."""
    fill_native_only(page)
    page.fields[-1].update(files=[], required=False)


def native_cv_delivery(ctx, *, status="observed", proof=None):
    """Append the ledger row of one native CV delivery to the stopped turn's receipt."""
    state = ctx.service.store.load()
    job = state["jobs"][0]
    run = job["native_handoff_runs"][-1]
    resolution = {
        "protocol": "fixed-material/v1",
        "resolution_id": "f" * 32,
        "material_ref": "e" * 64,
        "kind": "file",
        "sha256": job["file_sha256"],
        "size_bytes": 10,
        "filename": job["filename"],
        "mime_type": "application/pdf",
    }
    call = {
        "call_id": "native-cv",
        "tool": "browser_deliver_material",
        "arguments_digest": "d" * 64,
        "status": status,
        "generation": 1,
        "sequence": 9,
        "mutation": True,
        "semantic_verified": False,
        "scope": deepcopy(run["events"][-1]["receipt"]["calls"][0]["scope"]),
        "native_ref": "native-ref-cv",
        "field_hint": {"role": "button", "name": "Lebenslauf"},
        "material_ref": "e" * 64,
        "target_descriptor": {
            "tag": "input",
            "type": "file",
            "id": "cv",
            "name": "cv",
            "worker_field": "",
            "label": "Lebenslauf",
            "accept": ".pdf",
            "draft_path": "",
            "frame": "main",
            "required": True,
            "disabled": False,
            "readonly": False,
            "value_empty": True,
            "multiple": False,
            "max_length": None,
            "file_count": 0,
        },
        "material_resolution": resolution,
    }
    if status == "observed":
        call["material_readback"] = {
            "kind": "file_list",
            "sha256": job["file_sha256"],
            "size_bytes": 10,
            "filename": job["filename"],
            "file_count": 1,
        }
        if proof == "filename_shown":
            call["material_readback"].update(proof=proof, file_count=0)
    run["events"][-1]["receipt"]["calls"].append(call)
    ctx.service.store.save(state)


def native_only_turn(ctx, report, *, effect=fill_native_only):
    zero_question_page(ctx)
    ctx.page.resume_name = current(ctx)["filename"]
    run_turn(
        ctx,
        report=report,
        planned=(*BOTH_CALLS, click("native-team", "Team")),
        effect=effect,
    )


def test_ready_for_review_on_zero_question_page_accepts_native_resume_delivery(returning):
    ctx = returning
    native_only_turn(ctx, make_report("ready_for_review"))
    native_cv_delivery(ctx)
    ctx.runner._service_assistance_return()
    job = current(ctx)
    outcome = job["assistance"]["outcome"]
    assert job["status"] == "ready_for_review"
    assert outcome["kind"] == "filling_complete"
    rows = {row["id"]: row for row in outcome["page_verification"]["fields"]}
    assert rows["team"]["value_empty"] is False
    assert outcome["verified"]["materials"][0] == {
        "kind": "resume",
        "filename": job["filename"],
        "sha256": job["file_sha256"],
    }


@pytest.mark.parametrize("shown", [True, False])
def test_filename_shown_readback_completes_only_when_the_page_shows_the_name(
    returning, monkeypatch, capsys, shown
):
    ctx = returning
    native_only_turn(ctx, make_report("ready_for_review"), effect=fill_native_cleared_cv)
    native_cv_delivery(ctx, proof="filename_shown")
    reads = []

    def filename_shown(page, filename, *, document, target=None):
        # r12: the read starts from the delivery row's stable identity in the ledger.
        reads.append((filename, target["id"], target["draft_path"]))
        return {"shown": shown, "scope": "container" if shown else "", "error": False}

    monkeypatch.setattr(ctx.runner, "_native_filename_shown", filename_shown)
    capsys.readouterr()
    ctx.runner._service_assistance_return()
    job = current(ctx)
    # The cleared input lists no file, so the fixed page read decides visibility.
    assert reads == [(job["filename"], "cv", "")]
    if shown:
        assert job["status"] == "ready_for_review"
        assert job["assistance"]["outcome"]["kind"] == "filling_complete"
        return
    assert_waiting(ctx, "assistance_completion_unverified")
    line = next(
        row
        for row in capsys.readouterr().out.splitlines()
        if row.startswith("assistance_completion_unverified: ")
    )
    record = json.loads(line.removeprefix("assistance_completion_unverified: "))
    assert record["reason"] == ["resume_upload_unverified"]


def fill_native_unmounted_cv(page):
    """r12: the re-rendered upload widget unmounted its file input altogether."""
    fill_native_only(page)
    page.fields.pop()


@pytest.mark.parametrize("delivered", [True, False])
def test_resume_is_checked_even_when_the_page_lists_no_file_input(
    returning, monkeypatch, capsys, delivered
):
    ctx = returning
    native_only_turn(ctx, make_report("ready_for_review"), effect=fill_native_unmounted_cv)
    if delivered:
        native_cv_delivery(ctx, proof="filename_shown")
    reads = []

    def filename_shown(page, filename, *, document, target=None):
        reads.append((filename, (target or {}).get("id")))
        return {"shown": True, "scope": "form", "error": False}

    monkeypatch.setattr(ctx.runner, "_native_filename_shown", filename_shown)
    capsys.readouterr()
    ctx.runner._service_assistance_return()
    job = current(ctx)
    assert reads == [(job["filename"], "cv" if delivered else None)]
    if delivered:
        outcome = job["assistance"]["outcome"]
        assert job["status"] == "ready_for_review"
        assert outcome["kind"] == "filling_complete"
        assert {
            "kind": "resume",
            "filename": job["filename"],
            "sha256": job["file_sha256"],
        } in outcome["verified"]["materials"]
        return
    # A shown name without any delivery proof is not the job's upload.
    assert_waiting(ctx, "assistance_completion_unverified")
    line = next(
        row
        for row in capsys.readouterr().out.splitlines()
        if row.startswith("assistance_completion_unverified: ")
    )
    record = json.loads(line.removeprefix("assistance_completion_unverified: "))
    assert record["reason"] == ["resume_upload_unverified"]


@pytest.mark.parametrize("error", [True, False])
def test_shown_resume_beside_an_upload_error_is_unverified(returning, monkeypatch, capsys, error):
    # 2026-11-03: "resume.pdf 27.25 KB" above "That didn't work. Please try again."
    ctx = returning
    native_only_turn(ctx, make_report("ready_for_review"), effect=fill_native_cleared_cv)
    native_cv_delivery(ctx, proof="filename_shown")
    job = current(ctx)
    state = ctx.service.store.load()
    # The native upload's own response, as the guard records it.
    state["jobs"][0]["observations"].append(
        {
            "kind": "native_material_upload",
            "stage": "response",
            "http_status": 200,
            "application_id": job["application_id"],
            "sha256": job["file_sha256"],
        }
    )
    ctx.service.store.save(state)
    monkeypatch.setattr(
        ctx.runner,
        "_native_filename_shown",
        lambda page, filename, *, document, target=None: {
            "shown": True,
            "scope": "container",
            "error": error,
        },
    )
    capsys.readouterr()
    ctx.runner._service_assistance_return()
    if not error:
        resume = current(ctx)["assistance"]["outcome"]["verified"]["materials"][0]
        assert resume["kind"] == "resume" and resume["upload_response"] == 200
        return
    assert_waiting(ctx, "assistance_completion_unverified")
    line = next(
        row
        for row in capsys.readouterr().out.splitlines()
        if row.startswith("assistance_completion_unverified: ")
    )
    record = json.loads(line.removeprefix("assistance_completion_unverified: "))
    assert record["reason"] == ["resume_upload_unverified"]


def test_unobserved_native_resume_delivery_stays_unverified(returning, capsys):
    ctx = returning
    native_only_turn(ctx, make_report("ready_for_review"))
    native_cv_delivery(ctx, status="not_sent")
    capsys.readouterr()
    ctx.runner._service_assistance_return()
    assert_waiting(ctx, "assistance_completion_unverified")
    line = next(
        row
        for row in capsys.readouterr().out.splitlines()
        if row.startswith("assistance_completion_unverified: ")
    )
    record = json.loads(line.removeprefix("assistance_completion_unverified: "))
    assert record["reason"] == ["resume_upload_unverified"]


def test_blocked_segment_on_zero_question_page_waits_naming_remaining_controls(returning, capsys):
    ctx = returning
    report = make_report(
        fields=[
            {"field_id": "country", "state": "filled"},
            {"field_id": "team", "state": "unresolved"},
        ]
    )
    report["claimed_sha256"] = sha(report["claimed"])
    # Country and phone are set; the custom Team combobox and the CV stay open.
    native_only_turn(ctx, report, effect=fill_everything)
    capsys.readouterr()
    ctx.runner._service_assistance_return()
    job = assert_waiting(ctx, "native_controls_remaining")
    assert "assistance_return_unverified" not in capsys.readouterr().out
    message = ctx.service.store.applications.get_application(job["application_id"])["next_action"]
    assert "Phone（phone）" in message and "Team（team）" in message
    assert "Country" not in message
    assert "Engineering" not in message and "+41" not in message
    assert "继续" in message
    assert job.get("assistance_return_count", 0) == 0


LETTER_SHA = "c" * 64


def native_letter_delivery(ctx, monkeypatch, *, requirement="optional"):
    """A ready cover letter delivered natively beside the CV on the same document.

    The fixture's takeover binding predates the letter row; the binding digest is
    not under test here, so it is read without that row.
    """
    from career_evidence_graph import application_worker as worker

    original = worker.assistance_binding

    def binding(state, job):
        rows = [row for row in job.get("materials", []) if row.get("id") != "letter-1"]
        return original(state, {**job, "materials": rows})

    monkeypatch.setattr(worker, "assistance_binding", binding)
    monkeypatch.setattr(browser, "assistance_binding", binding)
    native_cv_delivery(ctx, proof="filename_shown")
    state = ctx.service.store.load()
    job = state["jobs"][0]
    calls = job["native_handoff_runs"][-1]["events"][-1]["receipt"]["calls"]
    letter = deepcopy(calls[-1])
    letter.update(call_id="native-letter", sequence=10, native_ref="native-ref-letter")
    letter["field_hint"] = {"role": "button", "name": "Cover Letter"}
    letter["target_descriptor"].update(id="letter", name="letter", label="Cover Letter")
    for key in ("material_resolution", "material_readback"):
        letter[key].update(sha256=LETTER_SHA, filename="cover-letter.pdf")
    calls.append(letter)
    job.setdefault("materials", []).append(
        {
            "id": "letter-1",
            "kind": "cover_letter",
            "status": "ready",
            "file_path": "/letters/letter.pdf",
            "filename": "cover-letter.pdf",
            "sha256": LETTER_SHA,
        }
    )
    job["cover_letter_delivery"] = {
        "status": "ready",
        "requirement": requirement,
        "selected_fields": [],
    }
    job["observations"].append(
        {
            "kind": "native_material_upload",
            "stage": "response",
            "http_status": 200,
            "application_id": job["application_id"],
            "sha256": LETTER_SHA,
        }
    )
    ctx.service.store.save(state)


@pytest.mark.parametrize(
    ("letter_error", "requirement"),
    [(False, "optional"), (True, "optional"), (True, "required")],
)
def test_native_cover_letter_is_checked_on_the_page_like_the_resume(
    returning, monkeypatch, capsys, letter_error, requirement
):
    # 2026-11-04: both files were uploaded, but verified.materials named only the resume.
    ctx = returning
    native_only_turn(ctx, make_report("ready_for_review"), effect=fill_native_unmounted_cv)
    native_letter_delivery(ctx, monkeypatch, requirement=requirement)
    reads = []

    def filename_shown(page, filename, *, document, target=None):
        reads.append((filename, target["id"]))
        error = letter_error and filename == "cover-letter.pdf"
        return {"shown": True, "scope": "form", "error": error}

    monkeypatch.setattr(ctx.runner, "_native_filename_shown", filename_shown)
    capsys.readouterr()
    ctx.runner._service_assistance_return()
    job = current(ctx)
    assert ("cover-letter.pdf", "letter") in reads
    if requirement == "required":
        assert_waiting(ctx, "assistance_completion_unverified")
        line = next(
            row
            for row in capsys.readouterr().out.splitlines()
            if row.startswith("assistance_completion_unverified: ")
        )
        record = json.loads(line.removeprefix("assistance_completion_unverified: "))
        assert record["reason"] == ["cover_letter_upload_unverified"]
        return
    verified = job["assistance"]["outcome"]["verified"]
    assert job["status"] == "ready_for_review"
    assert verified["materials"][0]["kind"] == "resume"
    letters = [row for row in verified["materials"] if row["kind"] == "cover_letter"]
    if letter_error:
        assert letters == []
        assert verified["optional_failures"] == [
            {
                "material": "cover_letter",
                "status": "unverified",
                "reason": "cover_letter_upload_unverified",
            }
        ]
        return
    assert letters == [
        {
            "kind": "cover_letter",
            "material_id": "letter-1",
            "filename": "cover-letter.pdf",
            "sha256": LETTER_SHA,
            "upload_response": 200,
        }
    ]
    assert verified["optional_failures"] == []
