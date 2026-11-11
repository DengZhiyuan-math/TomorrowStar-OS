"""Dispatch decisions use the retained worker page, intent and independent result."""

import base64
from types import SimpleNamespace

import pytest
from test_cua_worker import SyntheticControls
from test_dom_combobox import COMBOBOX, confirm_country
from test_generic_worker import FIELDS, native_form
from test_hosted_ats import PDF
from worker_preview_support import advance_until

from career_evidence_graph.career_portal_data import PortalDataError


class UnknownCuaSelection(SyntheticControls):
    """A synthetic lost-result boundary, never a native timing implementation."""

    def fill(self, page, question, value, *, check, pump):
        check()
        self.actions.append("open")
        page.get_by_role("combobox").click()
        raise PortalDataError("cua_result_unknown", "Synthetic lost result after opening", 409)


@pytest.mark.worker_browser
def test_dom_dispatch_records_reason_executor_intent_and_readback(tmp_path, monkeypatch):
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        advance_until(
            service,
            runner,
            lambda row: any(
                event.get("action") == "fill" and event.get("verified")
                for event in row["observations"]
            ),
        )
        page = runner.pages[job["application_id"]]
        page_id = runner.page_ids[page]
        current = service.store.load()["jobs"][0]
        fill = next(o for o in current["observations"] if o.get("action") == "fill")
        assert fill["executor"] == "playwright"
        assert fill["input_route"] == "dom"
        assert fill["route_reason"] == "supported_dom_field"
        assert fill["verified"] is True
        assert fill["intent"]["executor"] == "playwright"
        assert fill["intent"]["route_reason"] == "supported_dom_field"
        assert fill["intent"]["page_id"] == page_id
        assert fill["intent"]["attempt_id"]
        assert fill["intent"]["answer_ref"]["revision"]
        assert page.get_by_label("Full name", exact=False).input_value() == "Synthetic Person"
        assert runner.pages[job["application_id"]] is page
        assert current["intent"] is None
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("route", ["dom", "cua"])
def test_supported_route_keeps_actual_executor_and_reason_with_the_same_page(
    tmp_path, monkeypatch, route
):
    html = COMBOBOX if route == "dom" else COMBOBOX.replace(" aria-controls='countries'", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + html + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        controls = SyntheticControls()
        runner.cua = controls
        advance_until(
            service,
            runner,
            lambda row: any(
                event.get("action") == "fill"
                and event.get("intent", {}).get("fact") == "question:application country"
                for event in row["observations"]
            ),
        )
        page = runner.pages[job["application_id"]]
        current = service.store.load()["jobs"][0]
        fill = next(
            o
            for o in current["observations"]
            if o.get("intent", {}).get("fact") == "question:application country"
        )
        executor = "playwright" if route == "dom" else "cua_driver"
        assert fill["executor"] == fill["intent"]["executor"] == executor
        assert (
            fill["route_reason"] == fill["intent"]["route_reason"] == f"supported_{route}_readonly"
        )
        assert fill["verified"] is True
        assert fill["intent"]["page_id"] == runner.page_ids[page]
        assert fill["intent"]["answer_ref"]["revision"]
        assert current["intent"] is None
        assert page.get_by_role("combobox").input_value() == "Switzerland"
        assert len(controls.actions) == (0 if route == "dom" else 1)
        assert len(runner.pages) == 1 and posts == []


@pytest.mark.worker_browser
def test_not_sent_manual_preflight_can_reselect_after_explicit_existing_recheck(
    tmp_path, monkeypatch
):
    from career_evidence_graph.application_execution import automated_owner, require_execution

    unlinked = COMBOBOX.replace(" aria-controls='countries'", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + unlinked + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        page = runner.pages[job["application_id"]]
        page_id = runner.page_ids[page]
        before = service.store.load()
        owner = automated_owner(service.store.root, before["batch_id"], job["application_id"])
        require_execution(service.store.applications, job["application_id"], owner, "automated")
        decision = before["jobs"][0]["observations"][-1]
        assert decision["dispatch"] == "not_sent"
        assert before["jobs"][0]["intent"] is None
        service.request("review", {"application_id": job["application_id"], "acknowledge": True})
        runner.tick()
        assert service.store.load()["jobs"][0]["handoff"]["status"] == "complete"
        page.get_by_role("combobox").evaluate("e=>e.setAttribute('aria-controls','countries')")
        service.request(
            "recheck",
            {
                "application_id": job["application_id"],
                "acknowledge": True,
                "reclaim": True,
                "handoff_source": "Synthetic user verified unchanged original page and inputs",
            },
        )
        runner.tick()
        advance_until(
            service,
            runner,
            lambda row: any(
                event.get("action") == "fill"
                and event.get("intent", {}).get("fact") == "question:application country"
                for event in row["observations"]
            ),
        )
        after = service.store.load()["jobs"][0]
        assert after["intent"] is None and after["status"] == "filling"
        assert any(o.get("action") == "inputs_rechecked" for o in after["observations"])
        selected = after["observations"][-1]
        assert selected["executor"] == "playwright" and selected["verified"] is True
        assert selected["route_reason"] == "supported_dom_readonly"
        assert runner.pages[job["application_id"]] is page and runner.page_ids[page] == page_id
        assert len(runner.pages) == 1
        assert page.evaluate("window.comboEvents") == ["open", "choose"]
        require_execution(service.store.applications, job["application_id"], owner, "automated")
        assert posts == []


@pytest.mark.worker_browser
def test_unavailable_route_stops_before_click_and_hands_off_the_same_page(tmp_path, monkeypatch):
    unlinked = COMBOBOX.replace(" aria-controls='countries'", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + unlinked + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        page = runner.pages[job["application_id"]]
        page_id = runner.page_ids[page]
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "cua_unavailable"
        assert current["intent"] is None
        assert page.evaluate("window.comboEvents") == []
        decision = next(o for o in current["observations"] if o["action"] == "route_decision")
        assert decision["stage"] == "fill"
        assert decision["selected_executor"] == "manual"
        assert decision["executor"] is None
        assert decision["dispatch"] == "not_sent"
        assert decision["route_reason"] == "cua_unavailable"
        assert decision["page_id"] == page_id
        assert decision["answer_ref"]["revision"]
        service.request("resume", {"controller": "synthetic-controller"})
        for _ in range(3):
            runner.tick()
        assert service.store.load()["jobs"][0]["observations"] == current["observations"]
        service.request("review", {"application_id": job["application_id"], "acknowledge": True})
        runner.tick()
        handed_off = service.store.load()["jobs"][0]
        assert handed_off["manual_intervention"] is True
        assert handed_off["handoff"]["status"] == "complete"
        assert handed_off["status"] == "needs_recheck"
        assert runner.pages[job["application_id"]] is page
        assert runner.page_ids[page] == page_id
        assert len(runner.pages) == 1
        assert page.evaluate("window.comboEvents") == []
        assert page.get_by_label("Full name", exact=False).input_value() == "Synthetic Person"
        assert posts == []


@pytest.mark.worker_browser
def test_readonly_plain_field_is_manual_before_an_intent_is_admitted(tmp_path, monkeypatch):
    fields = FIELDS.replace(
        "<input name='person' required>", "<input name='person' readonly required>"
    )
    with native_form(tmp_path, monkeypatch, "<form>" + fields + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        runner.context.set_default_timeout(200)
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "unsupported_control"
        assert current["intent"] is None
        assert (
            runner.pages[job["application_id"]].get_by_label("Full name", exact=False).input_value()
            == ""
        )
        assert not any(o.get("action") == "fill" for o in current["observations"])
        assert current["observations"][-1]["dispatch"] == "not_sent"
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("resolve_not_applied", [False, True])
def test_unknown_cua_cannot_switch_to_dom_even_after_user_not_applied(
    tmp_path, monkeypatch, resolve_not_applied
):
    unlinked = COMBOBOX.replace(" aria-controls='countries'", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + unlinked + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        controls = UnknownCuaSelection()
        runner.cua = controls
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        current = service.store.load()["jobs"][0]
        assert current["reason"] == "cua_result_unknown"
        original_intent = current["intent"]
        page = runner.pages[job["application_id"]]
        page_id = runner.page_ids[page]
        page.get_by_role("combobox").evaluate("e=>e.setAttribute('aria-controls','countries')")
        if resolve_not_applied:
            assert page.get_by_role("combobox").input_value() == ""
            service.request(
                "resolve-action",
                {
                    "application_id": job["application_id"],
                    "intent_ref": original_intent["attempt_id"],
                    "conclusion": "not_applied",
                    "source": "Synthetic blank field; transport dispatch remains unknown",
                },
            )
            service.request(
                "recheck", {"application_id": job["application_id"], "acknowledge": True}
            )
        else:
            with pytest.raises(PortalDataError) as error:
                service.request(
                    "recheck", {"application_id": job["application_id"], "acknowledge": True}
                )
            assert error.value.code == "action_unresolved"
        service.request("resume", {"controller": "synthetic-controller"})
        if resolve_not_applied:
            runner.tick()
            advance_until(service, runner, lambda row: row["reason"] == "route_change_forbidden")
        else:
            for _ in range(4):
                runner.tick()
        after = service.store.load()["jobs"][0]
        assert after["status"] == "needs_recheck"
        if resolve_not_applied:
            assert after["reason"] == "route_change_forbidden"
            assert after["action_resolutions"][-1]["intent"] == original_intent
            decision = after["observations"][-1]
            assert decision["route_reason"] == "route_change_forbidden"
            assert decision["dispatch"] == "not_sent"
            assert decision["prior_intent_ref"] == original_intent["attempt_id"]
        else:
            assert after["intent"] == original_intent
        assert controls.actions == ["open"]
        assert page.evaluate("window.comboEvents") == ["open"]
        assert page.get_by_role("combobox").input_value() == ""
        assert runner.pages[job["application_id"]] is page and runner.page_ids[page] == page_id
        assert len(runner.pages) == 1
        assert posts == []


@pytest.mark.worker_browser
def test_capability_changed_after_intent_is_rechecked_before_field_dispatch(tmp_path, monkeypatch):
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        runner.context.set_default_timeout(200)
        original_authorize = runner.authorize

        def change_after_intent(current, batch_id, intent):
            accepted = original_authorize(current, batch_id, intent)
            if accepted and intent["action"] == "fill":
                runner.pages[job["application_id"]].locator("[name=person]").evaluate(
                    "e=>e.readOnly=true"
                )
            return accepted

        monkeypatch.setattr(runner, "authorize", change_after_intent)
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "question_changed"
        assert current["intent"]["executor"] == "playwright"
        assert not any(o.get("action") == "fill" for o in current["observations"])
        assert (
            runner.pages[job["application_id"]].get_by_label("Full name", exact=False).input_value()
            == ""
        )
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "change", ["input_route", "missing_executor", "missing_input_route", "same"]
)
def test_not_applied_preserves_the_exact_prior_route_or_declines_the_proposal(
    tmp_path, monkeypatch, change
):
    unlinked = COMBOBOX.replace(" aria-controls='countries'", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + unlinked + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        controls = UnknownCuaSelection()
        runner.cua = controls
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        if change.startswith("missing_"):
            state = service.store.load()
            state["jobs"][0]["intent"].pop(change.removeprefix("missing_"))
            service.store.save(state)
        original = service.store.load()["jobs"][0]["intent"]
        if change == "input_route":
            # Configuration semantics only; this double proves no native trusted readiness.
            controls.click_route = "trusted"
        service.request(
            "resolve-action",
            {
                "application_id": job["application_id"],
                "intent_ref": original["attempt_id"],
                "conclusion": "not_applied",
                "source": "Synthetic blank field after unknown attempt",
            },
        )
        service.request("recheck", {"application_id": job["application_id"], "acknowledge": True})
        runner.tick()
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck"
        assert current["action_resolutions"][-1]["intent"] == original
        if change == "same":
            assert current["reason"] == "cua_result_unknown"
            assert current["intent"]["attempt_id"] != original["attempt_id"]
            assert current["intent"]["input_route"] == "dom_event"
            assert controls.actions == ["open", "open"]
        else:
            assert current["reason"] == "route_change_forbidden"
            assert current["intent"] is None
            assert controls.actions == ["open"]
            decision = current["observations"][-1]
            assert decision["prior_intent_ref"] == original["attempt_id"]
            assert decision["dispatch_scope"] == "proposed_fill"
        assert len(runner.pages) == 1 and posts == []


@pytest.mark.worker_browser
def test_legacy_current_matches_settles_without_replaying_or_route_inference(tmp_path, monkeypatch):
    unlinked = COMBOBOX.replace(" aria-controls='countries'", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + unlinked + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        controls = UnknownCuaSelection()
        runner.cua = controls
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        state = service.store.load()
        original = state["jobs"][0]["intent"]
        original.pop("executor")
        original.pop("input_route")
        service.store.save(state)
        page = runner.pages[job["application_id"]]
        page.get_by_role("combobox").evaluate("""e=>{
          e.value='Switzerland';e.ariaExpanded='false';e.setAttribute('aria-controls','countries');
        }""")
        service.request(
            "resolve-action",
            {
                "application_id": job["application_id"],
                "intent_ref": original["attempt_id"],
                "conclusion": "current_matches",
                "source": "Synthetic independently verified field",
            },
        )
        service.request("recheck", {"application_id": job["application_id"], "acknowledge": True})
        runner.tick()
        current = service.store.load()["jobs"][0]
        assert current["intent"] is None
        assert current["reason"] != "route_change_forbidden"
        assert not any(
            o.get("route_reason") == "route_change_forbidden" for o in current["observations"]
        )
        assert controls.actions == ["open"]
        assert runner.pages[job["application_id"]] is page
        assert page.get_by_role("combobox").input_value() == "Switzerland"
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("unavailable", ["unsupported", "failed_driver"])
def test_unavailable_capability_cannot_probe_by_dom_or_cua_writes(
    tmp_path, monkeypatch, unavailable
):
    if unavailable == "unsupported":
        extra = "<label>Preferred time *<input type='time' required></label>"
    else:
        extra = COMBOBOX.replace(" aria-controls='countries'", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + extra + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        controls = SyntheticControls()
        runner.cua = controls
        if unavailable == "unsupported":
            service.store.answers.put_answer(
                {
                    "question": "Preferred time",
                    "value": "09:00",
                    "scope": {},
                    "state": "confirmed",
                }
            )
        else:
            confirm_country(service)
            controls.client = SimpleNamespace(failed=True)
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        current = service.store.load()["jobs"][0]
        assert current["status"] == "needs_recheck" and current["intent"] is None
        assert current["reason"] == (
            "unsupported_control" if unavailable == "unsupported" else "cua_unavailable"
        )
        assert current["observations"][-1]["dispatch"] == "not_sent"
        page = runner.pages[job["application_id"]]
        if unavailable == "unsupported":
            assert page.get_by_label("Preferred time", exact=False).input_value() == ""
        else:
            assert page.evaluate("window.comboEvents") == []
        assert controls.actions == [] and posts == []


@pytest.mark.worker_browser
def test_unknown_dom_cannot_replay_through_cua_after_user_not_applied(tmp_path, monkeypatch):
    broken = COMBOBOX.replace("combo.value='Switzerland';", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + broken + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        controls = SyntheticControls()
        runner.cua = controls
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        current = service.store.load()["jobs"][0]
        # The retained control recheck rejects the missing selected value first.
        assert current["reason"] == "question_changed"
        original = current["intent"]
        assert original["executor"] == "playwright"
        page = runner.pages[job["application_id"]]
        page.get_by_role("combobox").evaluate("e=>e.removeAttribute('aria-controls')")
        service.request(
            "resolve-action",
            {
                "application_id": job["application_id"],
                "intent_ref": original["attempt_id"],
                "conclusion": "not_applied",
                "source": "Synthetic independent blank field readback",
            },
        )
        service.request("recheck", {"application_id": job["application_id"], "acknowledge": True})
        runner.tick()
        advance_until(service, runner, lambda row: row["reason"] == "route_change_forbidden")
        after = service.store.load()["jobs"][0]
        assert after["status"] == "needs_recheck" and after["reason"] == "route_change_forbidden"
        assert after["action_resolutions"][-1]["intent"] == original
        assert after["observations"][-1]["prior_intent_ref"] == original["attempt_id"]
        assert controls.actions == []
        assert page.evaluate("window.comboEvents") == ["open", "choose"]
        assert runner.pages[job["application_id"]] is page
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize("next_case", ["same_job", "different_job", "different_field"])
def test_new_batch_preserves_prior_unknown_route_without_blocking_unrelated_work(
    tmp_path, monkeypatch, next_case
):
    unlinked = COMBOBOX.replace(" aria-controls='countries'", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + unlinked + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        controls = UnknownCuaSelection()
        runner.cua = controls
        advance_until(service, runner, lambda row: row["status"] == "needs_recheck")
        original = service.store.load()["jobs"][0]["intent"]
        old_page = runner.pages[job["application_id"]]
        service.request(
            "resolve-action",
            {
                "application_id": job["application_id"],
                "intent_ref": original["attempt_id"],
                "conclusion": "not_applied",
                "source": "Synthetic original field is blank",
            },
        )
        service.request("recheck", {"application_id": job["application_id"], "acknowledge": True})
        service.request("cancel", {"controller": "synthetic-controller"})
        service.request("release", {"application_id": job["application_id"]})
        runner.tick()
        assert old_page.is_closed() and not runner.pages
        record = service.store.applications.get_application(job["application_id"])
        if next_case == "different_job":
            record = service.store.applications.create_application(
                {
                    "company": "Synthetic",
                    "role_title": "Engineer",
                    "status": "drafting",
                    "url": job["job_url"].replace("42", "43"),
                    "application_strategy": "batch",
                }
            )
        if next_case == "different_field":
            service.store.answers.put_answer(
                {
                    "question": "Application territory",
                    "value": "Switzerland",
                    "scope": {},
                    "state": "confirmed",
                }
            )
        runner.context.add_init_script(
            "document.addEventListener('DOMContentLoaded',()=>{"
            "const e=document.querySelector('[role=combobox]');"
            "e.setAttribute('aria-controls','countries');"
            + (
                "e.parentNode.childNodes[0].textContent='Application territory *';"
                if next_case == "different_field"
                else ""
            )
            + "});"
        )
        service.request(
            "prepare",
            {
                "jobs": [
                    {
                        "application_id": record["id"],
                        "revision": record["revision"],
                        "country": "CHE",
                        "filename": "resume.pdf",
                        "file_base64": base64.b64encode(PDF).decode(),
                    }
                ]
            },
        )
        service.request("resume", {"controller": "synthetic-controller"})
        advance_until(
            service,
            runner,
            lambda row: (
                row["reason"] == "route_change_forbidden"
                if next_case == "same_job"
                else any(
                    event.get("action") == "fill"
                    and event.get("route_reason") == "supported_dom_readonly"
                    for event in row["observations"]
                )
            ),
        )
        state = service.store.load()
        current = state["jobs"][0]
        page = runner.pages[record["id"]]
        assert page is not old_page and len(runner.pages) == 1
        assert state["batch_history"][-1]["jobs"][0]["action_resolutions"][-1]["intent"] == original
        if next_case == "same_job":
            assert (
                current["status"] == "needs_recheck"
                and current["reason"] == "route_change_forbidden"
            )
            assert current["observations"][-1]["prior_intent_ref"] == original["attempt_id"]
            assert page.evaluate("window.comboEvents") == []
        else:
            assert current["status"] == "filling", current["reason"]
            assert current["observations"][-1]["route_reason"] == "supported_dom_readonly"
            assert page.evaluate("window.comboEvents") == ["open", "choose"]
        assert controls.actions == ["open"]
        assert posts == []
