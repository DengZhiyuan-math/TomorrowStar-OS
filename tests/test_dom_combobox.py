"""DOM-first readonly dropdowns through the complete synthetic worker entry."""

from pathlib import Path

import pytest
from test_cua_worker import SyntheticControls
from test_generic_worker import FIELDS, native_form
from worker_preview_support import advance_until

COMBOBOX = """<label>Application country *
<input role='combobox' aria-controls='countries' aria-expanded='false' readonly required>
</label><div role='listbox' id='countries' hidden></div>
<script>
window.comboEvents=[];
const combo=document.querySelector('[role=combobox]');
const list=document.getElementById('countries');
combo.onclick=()=>{
  window.comboEvents.push('open');combo.ariaExpanded='true';list.hidden=false;
  setTimeout(()=>{
    list.innerHTML="<div role='option'>Switzerland</div>";
    list.querySelector('[role=option]').onclick=()=>{
      window.comboEvents.push('choose');combo.value='Switzerland';
      combo.ariaExpanded='false';list.hidden=true;
    };
  },80);
};
</script>"""


def confirm_country(service):
    service.store.answers.put_answer(
        {
            "question": "Application country",
            "value": "Switzerland",
            "scope": {},
            "state": "confirmed",
        }
    )


@pytest.mark.worker_browser
def test_readonly_dropdown_uses_dom_after_async_options_and_independent_readback(
    tmp_path, monkeypatch
):
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + COMBOBOX + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        controls = SyntheticControls()
        runner.cua = controls
        advance_until(service, runner, lambda row: row["status"] == "ready_for_review")
        current = service.store.load()["jobs"][0]
        assert current["status"] == "ready_for_review", current["reason"]
        assert current["intent"] is None
        assert controls.actions == []
        page = runner.pages[job["application_id"]]
        assert page.get_by_role("combobox").input_value() == "Switzerland"
        assert page.evaluate("window.comboEvents") == ["open", "choose"]
        fill = next(
            row
            for row in current["observations"]
            if row.get("intent", {}).get("fact") == "question:application country"
        )
        assert fill["executor"] == "playwright"
        assert fill["verified"] is True
        assert fill["intent"]["attempt_id"]
        assert fill["intent"]["answer_ref"]["revision"]
        assert posts == []


@pytest.mark.worker_browser
def test_changed_listbox_relationship_stops_before_option_selection(tmp_path, monkeypatch):
    html = COMBOBOX.replace(
        "window.comboEvents.push('open');",
        "window.comboEvents.push('open');combo.setAttribute('aria-controls','replacement');",
    )
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + html + "</form>") as (
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
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "question_changed"
        assert current["intent"]["executor"] == "playwright"
        assert current["intent"]["action"] == "fill"
        assert runner.pages[job["application_id"]].evaluate("window.comboEvents") == ["open"]
        assert controls.actions == []
        assert posts == []


@pytest.mark.worker_browser
def test_option_rerender_during_final_recheck_does_not_rebind_to_replacement(tmp_path, monkeypatch):
    html = COMBOBOX.replace(
        "const list=document.getElementById('countries');",
        """const list=document.getElementById('countries');
        new MutationObserver(()=>{
          if(!window.replaceOptionOnScan) return;
          window.replaceOptionOnScan=false;
          const option=list.querySelector('[role=option]');
          const replacement=option.cloneNode(true);
          replacement.onclick=()=>{
            window.comboEvents.push('replacement-selected');combo.value='Switzerland';
            combo.ariaExpanded='false';list.hidden=true;
          };
          option.replaceWith(replacement);
        }).observe(combo,{attributes:true,attributeFilter:['data-ts-worker-field']});""",
    ).replace(
        "list.querySelector('[role=option]').onclick=()=>{",
        "window.replaceOptionOnScan=true;list.querySelector('[role=option]').onclick=()=>{",
    )
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + html + "</form>") as (
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
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "question_changed"
        assert current["intent"]["executor"] == "playwright"
        assert runner.pages[job["application_id"]].evaluate("window.comboEvents") == ["open"]
        assert controls.actions == []
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "options,extra,status,events",
    [
        (
            "<div role='option'>Switzerland</div><div role='option'>Switzerland</div>",
            "",
            "needs_recheck",
            ["open"],
        ),
        (
            "<div role='option'>Switzerland</div>"
            "<div role='option' style='display:none'>Switzerland</div>",
            "",
            "ready_for_review",
            ["open", "choose"],
        ),
        (
            "<div role='option'>Switzerland</div>",
            "<div role='listbox' id='unrelated'><div role='option'>Switzerland</div></div>",
            "ready_for_review",
            ["open", "choose"],
        ),
    ],
)
def test_only_one_exact_visible_option_in_the_linked_listbox_is_admitted(
    tmp_path, monkeypatch, options, extra, status, events
):
    html = COMBOBOX.replace("<div role='option'>Switzerland</div>", options) + extra
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + html + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        controls = SyntheticControls()
        runner.cua = controls
        advance_until(service, runner, lambda row: row["status"] == status)
        current = service.store.load()["jobs"][0]
        assert current["status"] == status, current["reason"]
        if status == "needs_recheck":
            assert current["reason"] == "ambiguous_option"
            assert current["intent"]["executor"] == "playwright"
        assert runner.pages[job["application_id"]].evaluate("window.comboEvents") == events
        assert controls.actions == []
        assert posts == []


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "change,reason",
    [
        ("answer", "answer_changed"),
        ("pause", "dom_action_invalidated"),
        ("file", "file_changed"),
        # A cloned persistent marker is rejected by the snapshot before node comparison.
        ("rerender", "unsupported_structure"),
        ("control", "dom_action_invalidated"),
        ("cancel", ""),
    ],
)
def test_dom_rechecks_answer_permission_inputs_and_original_field_between_actions(
    tmp_path, monkeypatch, change, reason
):
    html = COMBOBOX.replace(
        "window.comboEvents.push('open');",
        "window.comboEvents.push('open');window.changePermission();",
    )
    if change == "rerender":
        html = html.replace(
            "window.changePermission();",
            "combo.replaceWith(combo.cloneNode(true));",
        )
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + html + "</form>") as (
        service,
        runner,
        job,
        posts,
    ):
        confirm_country(service)
        controls = SyntheticControls()
        runner.cua = controls
        runner.tick()
        page = runner.pages[job["application_id"]]
        cancelled_reason = []

        def change_permission():
            if change == "answer":
                service.store.answers.put_answer(
                    {
                        "question": "Application country",
                        "value": "Denmark",
                        "scope": {},
                        "state": "confirmed",
                    }
                )
            elif change == "pause":
                service.request("pause", {"controller": "synthetic-controller"})
            elif change == "file":
                Path(job["file_path"]).write_bytes(b"%PDF-1.4 changed synthetic file")
            elif change == "control":
                with service.store.applications.write_lock():
                    state = service.store.load()
                    state["control"] = "paused"
                    service.store.save(state)
            elif change == "cancel":
                cancelled_reason.append(service.store.load()["jobs"][0]["reason"])
                service.request("cancel", {"controller": "synthetic-controller"})

        page.expose_function("changePermission", change_permission)
        advance_until(
            service,
            runner,
            lambda row: row["status"] == ("cancelled" if change == "cancel" else "needs_recheck"),
        )
        current = service.store.load()["jobs"][0]
        assert current["status"] == ("cancelled" if change == "cancel" else "needs_recheck")
        assert current["reason"] == (cancelled_reason[0] if change == "cancel" else reason)
        assert current["intent"]["executor"] == "playwright"
        assert current["intent"]["action"] == "fill"
        assert page.evaluate("window.comboEvents") == ["open"]
        assert controls.actions == []
        assert posts == []


@pytest.mark.worker_browser
def test_opening_never_rebinds_to_field_replaced_after_permission_check(tmp_path, monkeypatch):
    from playwright.sync_api import ElementHandle

    original_click = ElementHandle.click

    def replaced_before_click(element, *args, **kwargs):
        if element.get_attribute("role") == "combobox":
            element.evaluate("""e=>{
              const replacement=e.cloneNode(true);
              replacement.onclick=()=>window.comboEvents.push('replacement-opened');
              e.replaceWith(replacement);
            }""")
        return original_click(element, *args, **kwargs)

    monkeypatch.setattr(ElementHandle, "click", replaced_before_click)
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + COMBOBOX + "</form>") as (
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
        assert current["status"] == "needs_recheck"
        assert current["reason"] == "browser_result_unknown"
        assert current["intent"]["executor"] == "playwright"
        assert runner.pages[job["application_id"]].evaluate("window.comboEvents") == []
        assert controls.actions == []
        assert posts == []


@pytest.mark.worker_browser
def test_unknown_dom_selection_result_never_replays_through_cua(tmp_path, monkeypatch):
    html = COMBOBOX.replace("combo.value='Switzerland';", "")
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + html + "</form>") as (
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
        assert current["status"] == "needs_recheck"
        # The retained control recheck rejects the missing selected value first.
        assert current["reason"] == "question_changed"
        intent = current["intent"]
        assert intent["action"] == "fill"
        assert intent["executor"] == "playwright"
        assert intent["answer_ref"]["revision"]
        assert not any(
            row.get("verified") and row.get("intent") == intent for row in current["observations"]
        )
        for _ in range(4):
            runner.tick()
        assert service.store.load()["jobs"][0]["intent"] == intent
        assert runner.pages[job["application_id"]].evaluate("window.comboEvents") == [
            "open",
            "choose",
        ]
        assert controls.actions == []
        assert posts == []


@pytest.mark.worker_browser
def test_field_rerender_after_selection_retains_unknown_intent(tmp_path, monkeypatch):
    html = COMBOBOX.replace(
        "combo.ariaExpanded='false';list.hidden=true;",
        "combo.ariaExpanded='false';list.hidden=true;combo.replaceWith(combo.cloneNode(true));",
    )
    with native_form(tmp_path, monkeypatch, "<form>" + FIELDS + html + "</form>") as (
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
        assert current["status"] == "needs_recheck"
        # Snapshot identity validation rejects the clone before field readback.
        assert current["reason"] == "unsupported_structure"
        assert current["intent"]["executor"] == "playwright"
        assert runner.pages[job["application_id"]].evaluate("window.comboEvents") == [
            "open",
            "choose",
        ]
        assert controls.actions == []
        assert posts == []
