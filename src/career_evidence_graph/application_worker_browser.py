"""Sequential, separately launched Playwright process with no final-action API."""

from __future__ import annotations

import argparse
import base64
import collections
import fcntl
import hashlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
from contextlib import ExitStack, contextmanager, suppress
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import Error, Page, TimeoutError, sync_playwright

from . import application_form_runner as form_flow
from . import hosted_ats
from ._vendor.job_apply_store import StoreError, normalize_question
from .application_automation import validate_application_target
from .application_codex_assist import CodexAdapter, CodexAssistConfig
from .application_execution import automated_owner, release_execution, require_execution
from .application_information import fact_for
from .application_page_scope import PAGE_SCOPE
from .application_takeover_budget import DEFAULT_BUDGET, TakeoverBudget
from .application_takeover_record import settle_unstarted_stop, stop_evidence_proven
from .application_worker import (
    CONTROLLER_HANDOFF_INSPECTION,
    OWNED_PAGE_OBSERVATION,
    WorkerStore,
    adopt_assistance_outcome,
    adopt_assistance_report,
    adopt_assistance_stop,
    assistance_backend_permitted,
    assistance_binding,
    assistance_binding_resumed_only,
    assistance_completion,
    assistance_reference,
    assistance_stop_pending,
    backend_recovery_timely,
    default_scope,
    diagnostic_url,
    effective_action_results,
    handoff_binding,
    latest_action_resolutions,
    manual_submission_unresolved,
    mark_assistance_backend_lost,
    material_edit_pending,
    native_field_fact,
    precision_preparation_pending,
    record_takeover_failure,
    revoke_assistance,
    script_writes_allowed,
    start_run,
    takeover_pending_intent,
    validate_native_assistance_policy,
    validate_native_assistance_scope,
    worker_lock_is_held,
)
from .application_worker import (
    failed_write as _failed_write,  # noqa: F401 -- compatible control predicate export
)
from .application_worker import (
    unresolved_write_failure as _unresolved_write_failure,
)
from .ashby_drafts import DraftSession
from .ashby_drafts import supports as supports_ashby_drafts
from .ats_forms import FORMS, form_for
from .career_portal_data import ApplicationStore, PortalDataError
from .cua_driver import managed_cua_browser, native_handoff_port, sync_login_state
from .loaded_code import load_worker_modules, loaded_runtime_revision
from .owned_browser_cdp import OwnedCDP, browser_budget, pause_browser_budget, pump_events
from .owned_browser_cdp import screenshot as owned_screenshot
from .owned_page_observation import INSPECT as INSPECT_OWNED_PAGE
from .validation.hashing import record_digest as digest
from .workable_uploads import ResumeUpload, job_shortcode
from .worker_process_identity import process_identity

# A checkbox or radio state is admitted only from the field's own confirmed fact, so
# Codex cannot tick consents nobody saved (2026-11-03 audit).
NATIVE_AFFIRMATIVE_FACT_VALUES = frozenset(
    {"yes", "true", "y", "ja", "agree", "agreed", "accept", "accepted", "同意", "是"}
)
NATIVE_NEGATIVE_FACT_VALUES = frozenset(
    {"no", "false", "n", "nein", "disagree", "decline", "不同意", "否"}
)

# 2026-11-03: Codex set a consent "Yes" radio by its AX name, which names the option,
# not the question, so `fact_for("Yes")` found no fact and admission stopped the run.
# Delivery already binds each fact to its DOM controls (`field_ids`); admission reuses
# that binding: the delivered controls whose own label equals the AX name and whose
# kind matches the AX role must all map to exactly one confirmed fact. A Yes/No option
# must also agree with that fact's polarity. Anything else stays refused.
NATIVE_TEXT_FIELD_TYPES = frozenset(
    {"", "text", "email", "tel", "url", "number", "search", "textarea"}
)


def _native_control_kind(field):
    role = str(field.get("role") or "").strip().casefold()
    kind = str(field.get("type") or "").strip().casefold()
    for value in (role, kind):
        if value in {"radio", "checkbox", "date"}:
            return value
        if value in {"combobox", "select", "select-one", "select-multiple"}:
            return "combobox"
    return "textbox" if role in {"", "textbox"} and kind in NATIVE_TEXT_FIELD_TYPES else None


def _native_polarity(text):
    word = text.strip().casefold()
    if word in NATIVE_AFFIRMATIVE_FACT_VALUES:
        return "true"
    if word in NATIVE_NEGATIVE_FACT_VALUES:
        return "false"
    return None


# A resume file input's own name, on a page whose script found no questions.
NATIVE_RESUME_LABEL = re.compile(r"\b(?:cv|resume|résumé|curriculum vitae|lebenslauf)\b")

NATIVE_DONE_STATES = frozenset(
    {
        "filled",
        "selected",
        "uploaded",
        "checked",
        "set",
        "resolved",
        "done",
        "completed",
        "verified",
    }
)


def native_cover_letter_controls(page_context):
    """Cover-letter file inputs and textareas a zero-question page shows, as questions.

    Each pair is (question, page field). The question is the script's own observed
    shape, so the existing letter policy can prepare it (2026-11-03: onlyfy had a
    "Cover letter" input but no parsed question, so no letter was delivered).
    """
    from .application_materials import material_kind

    pairs = []
    for field in ((page_context or {}).get("data") or {}).get("fields", []):
        target = field.get("material_target")
        if not isinstance(target, dict):
            continue
        kind = (
            "file"
            if target.get("type") == "file"
            else "textarea"
            if target.get("tag") == "textarea"
            else None
        )
        text = " ".join(
            str(field.get("question") or field.get("label") or target.get("label") or "").split()
        )
        if kind is None or not text:
            continue
        if material_kind({"type": kind, "question": text}) != "cover_letter":
            continue
        identifier = (
            target.get("id")
            or target.get("name")
            or field.get("id")
            or field.get("name")
            or "native-" + digest({"question": text, "type": kind})[:16]
        )
        question = {
            "id": identifier,
            "type": kind,
            "question": text,
            "required": bool(target.get("required")),
            "draft_path": target.get("draft_path", ""),
            "multiple": False,
            "accept": target.get("accept", ""),
            "max_length": target.get("max_length"),
            "value": "" if kind == "file" else str(field.get("value") or ""),
            "valid": field.get("valid") is not False,
            "filename": "",
            "file_sha256": None,
            "resume": False,
        }
        pairs.append((question, field))
    identifiers = [question["id"] for question, _ in pairs]
    return [pair for pair in pairs if identifiers.count(pair[0]["id"]) == 1]


def native_resume_deliveries(job, document):
    """Native resume deliveries the ledger observed on this document, by bytes and name."""
    return native_material_deliveries(job, document, job.get("file_sha256"), job.get("filename"))


def native_material_deliveries(job, document, sha256, filename):
    """Native file deliveries of these bytes and name the ledger observed on this document.

    r11: an upload widget may clear its input after change (2026-11-03, onlyfy); the
    driver then proves the delivered name shown beside it (``filename_shown``), with
    no FileList entry left to count.
    """
    if not sha256:
        return []
    return [
        call
        for run in job.get("native_handoff_runs", [])
        if (run.get("scope") or {}).get("document") == document
        for event in run.get("events", [])
        for call in (event.get("receipt") or {}).get("calls", [])
        if call.get("tool") == "browser_deliver_material"
        and call.get("status") == "observed"
        and (call.get("material_resolution") or {}).get("kind") == "file"
        and call["material_resolution"].get("sha256") == sha256
        and (call.get("material_readback") or {}).get("sha256") == sha256
        and call["material_readback"].get("filename") == filename
        and (
            call["material_readback"].get("file_count") == 1
            or call["material_readback"].get("proof") == "filename_shown"
        )
    ]


def native_resume_delivered(job, document):
    """A native resume delivery the ledger observed on this document."""
    return bool(native_resume_deliveries(job, document))


def native_remaining_message(claimed, fields, verification, delivered=()):
    """Name the controls the native turn left (labels/ids only), for the user's choice.

    ``delivered`` are the file inputs the ledger observed a delivery into; Codex's own
    word for them ("attached", 2026-11-05 Harmattan's CV) does not reopen them.
    """
    done = {
        value
        for call in delivered
        for value in (
            (call.get("target_descriptor") or {}).get(key) for key in ("id", "name", "worker_field")
        )
        if value
    }
    named = [(claimed.get("next_step") or {}).get("field_id")] + [
        row.get("field_id")
        for row in claimed.get("fields", [])
        if str(row.get("state", "")).strip().casefold() not in NATIVE_DONE_STATES
    ]
    if not any(name not in done for name in named if name):
        # Codex named nothing; the Worker's own read names the required empty ones.
        named = [row["id"] for row in verification if row["required"] and row["value_empty"]]
    named = [name for name in named if name not in done]
    names = []
    for identifier in dict.fromkeys(name for name in named if name):
        rows = [row for row in fields if identifier in {row.get("id"), row.get("name")}]
        text = " ".join(str(rows[0].get("label") or "").split()) if len(rows) == 1 else ""
        name = f"{text}（{identifier}）" if text and text != identifier else identifier
        names.append(name[:80])
    listed = "：" + "、".join(names[:10]) + ("等" if len(names) > 10 else "") if names else ""
    return (
        f"原生接管未能完成本页剩余控件{listed}。"
        "请在专用浏览器手动完成后人工提交，或按“继续”重试原生接管。"
    )


def _native_label(text):
    # A required marker or line break in the AX name or label does not change the field.
    return " ".join(re.sub(r"[✱*]", " ", str(text or "")).split()).casefold()


def native_control_fact_values(delivery, field_hint):
    """Return the one confirmed fact value bound to the AX-named control, else []."""

    label = _native_label
    name = label(field_hint.get("name"))
    role = str(field_hint.get("role") or "").strip().casefold()
    if not name or role not in {"radio", "checkbox", "combobox", "date", "textbox"}:
        return []
    fields = ((delivery.get("page_context") or {}).get("data") or {}).get("fields", [])
    ids = [
        field.get("id")
        for field in fields
        if label(field.get("label")) == name and _native_control_kind(field) == role
    ]
    facts = (delivery.get("answers") or {}).get("facts", [])
    bound = []
    for field_id in ids:
        owners = [fact for fact in facts if field_id and field_id in (fact.get("field_ids") or [])]
        if not owners:
            return []
        bound.extend(owner for owner in owners if owner not in bound)
    if len(bound) != 1:
        return []
    fact = bound[0]
    value = fact.get("value")
    if fact.get("status") != "confirmed" or not isinstance(value, str):
        return []
    if role == "radio":
        option, answer = _native_polarity(name), _native_polarity(value)
        if (
            (option or answer)
            and option != answer
            and _native_choice_key(name) != _native_choice_key(value)
        ):
            return []
    elif role == "checkbox":
        option, answer = _native_polarity(name), _native_polarity(value)
        if option and answer and option != answer:
            return []
    return [value]


def _native_words(text):
    return " ".join(str(text or "").split()).casefold()


# Edge punctuation an option label may add to or drop from its answer: ASCII, quotes,
# brackets and full-width forms. Only the ends; nothing inside a label is ignored.
_NATIVE_CHOICE_EDGE = (
    ".,:;!?"
    "\"'`\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f\u00ab\u00bb\u2039\u203a"
    "()[]{}<>"
    "\u3002\uff0c\uff1a\uff1b\uff01\uff1f\u3001\uff0e"
    "\uff08\uff09\uff3b\uff3d\uff5b\uff5d\u3010\u3011\u300c\u300d\u300e\u300f"
    "\u300a\u300b\u3008\u3009\uff02\uff07"
)


def _native_choice_key(text):
    """An option label compared with a confirmed answer (combobox and radio options).

    2026-11-03: the listed option "Mr." and the confirmed "Mr" differed only by a
    final period. Case, edge and inner whitespace, and edge punctuation are ignored;
    nothing fuzzier. Text-input hashes never use this.
    """
    words = _native_words(text)
    while True:
        stripped = words.strip(_NATIVE_CHOICE_EDGE).strip()
        if stripped == words:
            return words
        words = stripped


def native_choice_fact_value(delivery, field_hint):
    """The one confirmed delivered answer a custom combobox's AX name maps to, else None."""
    name = str(field_hint.get("name") or "")
    if not name.strip():
        return None
    expected = fact_for(name)
    values = {
        fact["value"]
        for fact in (delivery.get("answers") or {}).get("facts", [])
        if fact.get("fact") == expected
        and fact.get("status") == "confirmed"
        and isinstance(fact.get("value"), str)
    } or set(native_control_fact_values(delivery, {"role": "combobox", "name": name}))
    return values.pop() if len(values) == 1 else None


def native_combobox_choice_kept(delivery, call, value, *, page_reopened=False):
    """r7: why a combobox shown as a choice may not be expanded, or None to admit it.

    The driver names the shown value it was asked to expect. A delivered empty value
    is a placeholder (INSPECT's ``shown()``); a shown value equal to the confirmed
    fact needs no change of answer. On a page this Worker run reopened and no takeover
    has yet touched, the shown value the Worker delivered is the page's own default
    (2026-11-03: a collapsed button combobox showed "Select title..." with no
    placeholder marker), so it may be expanded while it still shows that value.
    On a retained page any other shown choice belongs to the user or page.
    """
    shown = (call.get("expected_target") or {}).get("value", "")
    if not shown or _native_words(shown) == _native_words(value):
        return None
    name = _native_label((call.get("field_hint") or {}).get("name"))
    fields = [
        field
        for field in ((delivery.get("page_context") or {}).get("data") or {}).get("fields", [])
        if _native_label(field.get("label")) == name and _native_control_kind(field) == "combobox"
    ]
    if fields and all(field.get("value") == "" for field in fields):
        return None
    if not fields or any(
        _native_words(field.get("value")) != _native_words(shown) for field in fields
    ):
        return "shown_changed"
    return None if page_reopened else "existing_choice"


def native_click_denial(delivery, calls, call, *, page_reopened=False):
    """Why a click is refused, or None: admit only a delivered-fact combobox or its fact option.

    An option row names only the option; its field is the combobox whose observed
    click immediately precedes it in this handoff's ledger (the driver's owner rule).
    A pre-ledger refusal row was never sent and is no mutation for that rule.
    """
    hint = call.get("field_hint") or {}
    role = str(hint.get("role") or "").strip().casefold()
    if role == "combobox":
        value = native_choice_fact_value(delivery, hint)
        if value is None:
            return "unbound_fact"
        return native_combobox_choice_kept(delivery, call, value, page_reopened=page_reopened)
    if role != "option":
        # APP-11: a native click opens a combobox or picks its option, nothing else.
        # Buttons and links (Submit, Apply, Send) are refused here, never by name.
        return "role_not_clickable"
    previous = sorted(
        (
            row
            for row in calls
            if row.get("mutation") is True
            and "refusal" not in row
            and row.get("call_id") != call.get("call_id")
            and row.get("sequence", 0) < call.get("sequence", 0)
        ),
        key=lambda row: row["sequence"],
    )
    owner = previous[-1] if previous else {}
    owner_hint = owner.get("field_hint") or {}
    if (
        owner.get("tool") != "browser_click"
        or owner.get("status") != "observed"
        or str(owner_hint.get("role") or "").strip().casefold() != "combobox"
    ):
        return "option_owner_unproven"
    value = native_choice_fact_value(delivery, owner_hint)
    if value is None or _native_choice_key(value) != _native_choice_key(hint.get("name")):
        return "option_not_fact"
    return None


# APP-11 at the action layer: while the Worker or a native takeover acts on a page,
# no form there may submit, whether by a submit button, implicit Enter, a page
# script's requestSubmit() or form.submit(). Unlocked documents (the default, the
# user's handed-off and sign-in pages, popups) behave natively. A first capture
# listener stops a submit event before any page or framework handler sees it.
SUBMIT_LOCK_INSTALL = """(() => {
  const key = Symbol.for('tomorrowstar.submitLock');
  if (window[key]) return;
  const lock = {locked: false};
  Object.defineProperty(window, key, {value: lock});
  window.addEventListener('submit', event => {
    if (lock.locked) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  const proto = HTMLFormElement.prototype;
  for (const name of ['submit', 'requestSubmit']) {
    const original = proto[name];
    proto[name] = function(...args) { if (!lock.locked) return original.apply(this, args); };
  }
})()"""
SUBMIT_LOCK_SET = (
    "locked => {" + SUBMIT_LOCK_INSTALL + ";"
    " window[Symbol.for('tomorrowstar.submitLock')].locked = locked; }"
)

# Fixed DOM reads. Page text and model output never become executable code.
INSPECT = FORMS["lever"].inspect_script()

# Add semantic locator hints only to JSON handoff; keep the v1 image payload stable.
INSPECT_ASSISTANCE_CONTEXT = (
    "() => { const data = ("
    + INSPECT_OWNED_PAGE
    + ")();"
    + r"""
    const controls = [...document.querySelectorAll(
      'input,textarea,select,[role=combobox],[role=checkbox],[role=radio]')]
      .filter(e=>!['hidden','submit','button','reset'].includes(e.type));
    // A custom combobox has no form value: its choice is aria-valuetext, the selected
    // option of its one listbox, or its shown text unless that is a placeholder.
    const shown=e=> {
      const text=x=>String(x?.textContent??'').replace(/\s+/g,' ').trim();
      if(e.hasAttribute('aria-valuetext')) return e.getAttribute('aria-valuetext');
      const ids=(e.getAttribute('aria-controls')||'').split(/\s+/).filter(Boolean);
      const box=ids.length===1?document.getElementById(ids[0]):null;
      if(box?.querySelector('[role=option]')) {
        return text(box.querySelector('[role=option][aria-selected=true]'));
      }
      if(e.querySelector('[data-placeholder],[class*=placeholder i]')) return '';
      const value=text(e);
      return value===(e.getAttribute('placeholder')||e.dataset.placeholder||'').trim()
        ? '' : value;
    };
    // The nearest ancestor id names a control's form item; a hidden native select
    // beside a custom combobox (Radix) changes with it. Identity only, never values.
    const place=e=> {
      let c=e.parentElement;
      while(c&&!c.id) c=c.parentElement;
      return {container_id:String(c?.id||'').slice(0,200),
        hidden:Boolean(e.closest('[aria-hidden=true]'))||!e.getClientRects().length||
          getComputedStyle(e).visibility==='hidden'};
    };
    data.fields.forEach((field,index)=> {
      const e=controls[index];
      Object.assign(field,place(e));
      field.role=(e.getAttribute('role')||'').slice(0,200);
      if(field.role==='combobox'&&!['INPUT','SELECT','TEXTAREA'].includes(e.tagName)&&
         !field.value) field.value=String(shown(e)).slice(0,4000);
      if(['radio','checkbox'].includes(field.type)) {
        // A choice's own label is its option ("Yes"); the group carries the question.
        const group=e.closest('[role=radiogroup],[role=group],fieldset');
        const text=e.getAttribute('description')||(group?.getAttribute('aria-labelledby')||'')
          .split(/\s+/).filter(Boolean).map(id=>document.getElementById(id)?.textContent||'')
          .join(' ')||group?.getAttribute('aria-label')||
          group?.querySelector('legend')?.textContent||'';
        const question=text.replace(/[✱*]/g,'').trim().replace(/\s+/g,' ').slice(0,4000);
        if(question) field.question=question;
      }
      if(field.type==='file'&&!field.label.trim()) {
        // An unlabelled (often hidden) file input: its nearest short container text
        // names it ("Upload your CV"); a long one is a whole section and names nothing.
        let node=e.parentElement;
        for(let depth=0;node&&depth<4;depth++,node=node.parentElement) {
          const text=String(node.textContent||'').replace(/[✱*]/g,'').replace(/\s+/g,' ').trim();
          if(text) { if(text.length<=300) field.question=text; break; }
        }
      }
      const tag=e.tagName.toLowerCase(),type=tag==='textarea'?'textarea':String(e.type||'');
      if(tag==='textarea'||tag==='input'&&['text','file'].includes(type)) {
        try {
        const bounded=(value,limit)=> {
          value=String(value??'');
          if([...value].length>limit) throw Error('material_target_limit');
          return value;
        };
        field.material_target={tag,id:bounded(e.id,200),name:bounded(e.name,200),type,
          label:bounded([...e.labels||[]].map(x=>x.textContent).join(' ')||
            e.getAttribute('aria-label')||(e.getAttribute('aria-labelledby')||'').split(/\s+/)
              .map(id=>document.getElementById(id)?.textContent||'').join(' '),1000),
          frame:'main',worker_field:bounded(e.getAttribute('data-ts-worker-field')||'',200),
          draft_path:bounded(e.closest('[data-field-path]')?.dataset.fieldPath||'',1000),
          required:Boolean(e.required||e.getAttribute('aria-required')==='true'),
          disabled:Boolean(e.disabled),readonly:Boolean(e.readOnly),
          value_empty:type==='file'?e.files.length===0:e.value==='',
          accept:bounded(type==='file'?e.accept:'',1000),multiple:Boolean(e.multiple),
          max_length:e.hasAttribute('maxlength')?e.maxLength:null,
          file_count:type==='file'?e.files.length:0};
        if(field.material_target.max_length!==null&&field.material_target.max_length<0||
           field.material_target.file_count>20) delete field.material_target;
        } catch (_) {
          // An unrepresentable material target does not disable ordinary context.
          // A material call still requires the complete, untruncated descriptor.
          delete field.material_target;
        }
      }
    });
    // A button-based combobox is often precisely the control the script could not fill.
    const extra=[...document.querySelectorAll('button[role=combobox]')];
    if(data.fields.length+extra.length>500) throw Error('observation_field_limit');
    for(const e of extra) {
      const trim=(value,n=4000)=>String(value??'').slice(0,n);
      data.fields.push({id:trim(e.id,200),name:trim(e.name,200),type:'combobox',
        role:'combobox',label:trim([...e.labels||[]].map(x=>x.textContent).join(' ')||
          e.getAttribute('aria-label')||(e.getAttribute('aria-labelledby')||'').split(/\s+/)
            .map(id=>document.getElementById(id)?.textContent||'').join(' '),1000),
        value:trim(shown(e)),redacted:false,
        required:e.getAttribute('aria-required')==='true',disabled:Boolean(e.disabled),
        readonly:false,valid:null,aria_invalid:e.getAttribute('aria-invalid'),
        visible:Boolean(e.getClientRects().length)&&getComputedStyle(e).visibility!=='hidden',
        files:[],...place(e)});
    }
    return data;
    }"""
)


def readonly_combobox_target(page, question: dict) -> str:
    """Admit only an explicit single-listbox relationship, never a page-wide guess."""
    if question["type"] != "combobox":
        return ""
    return hosted_ats.control(page, question).evaluate(
        r"""e => {
          const ids=(e.getAttribute('aria-controls')||'').trim().split(/\s+/).filter(Boolean);
          return (e.readOnly || e.tagName==='BUTTON') && ids.length===1 ? ids[0] : '';
        }"""
    )


def select_fill_route(page, question: dict, cua) -> dict:
    """Read current support before admitting a field action; never probe by writing."""
    route = {"executor": "playwright", "input_route": "dom", "route_reason": "supported_dom_field"}
    if question["type"] == "combobox":
        target = readonly_combobox_target(page, question)
        if target:
            return {**route, "route_reason": "supported_dom_readonly", "dom_target": target}
        if hosted_ats.control(page, question).is_editable():
            return route
        if (
            cua is not None
            and callable(getattr(cua, "fill", None))
            and not getattr(getattr(cua, "client", None), "failed", False)
        ):
            return {
                "executor": "cua_driver",
                "input_route": cua.click_route,
                "route_reason": "supported_cua_readonly",
            }
        reason = "cua_unavailable"
    elif question["type"] in {"text", "email", "tel", "url", "number", "date", "textarea"}:
        if hosted_ats.control(page, question).is_editable():
            return route
        reason = "unsupported_control"
    elif question["type"] in {"select", "radio", "checkbox"} and not question.get("multiple"):
        return route
    else:
        reason = "unsupported_control"
    return {"executor": "manual", "input_route": None, "route_reason": reason}


def fill_readonly_combobox(page, field, value: str, target: str, *, check) -> None:
    """Expand once, choose one exact visible option, and leave result verification to the runner."""
    check()
    field.click(timeout=3000)
    listbox = page.locator(f'[id={json.dumps(target)}][role="listbox"]')
    listbox.wait_for(state="visible", timeout=5000)
    option = listbox.get_by_role("option", name=value, exact=True)
    if option.count() > 1:
        raise PortalDataError("ambiguous_option", "选项不唯一，请人工选择。", 409)
    option.wait_for(state="visible", timeout=5000)
    if option.count() != 1:
        raise PortalDataError("ambiguous_option", "选项不唯一，请人工选择。", 409)
    original = option.element_handle()
    if original is None:
        raise PortalDataError("question_changed", "选项已变更。", 409)
    try:
        check()
        if not option.evaluate_all(
            "(nodes, original) => original.isConnected && "
            "nodes.length === 1 && nodes[0] === original",
            original,
        ):
            raise PortalDataError("question_changed", "选项已变更。", 409)
        # A retained node cannot silently bind to a replacement during auto-wait.
        original.click(timeout=3000)
        check(after_write=True)
    finally:
        original.dispose()


@contextmanager
def browser_deadline(seconds: float):
    """Bound ordinary calls; owned reads suspend the alarm within this budget."""

    def expired(_signum, _frame):
        raise Error("native_operation_timeout")

    with browser_budget(seconds) as budget:
        remaining = budget.end - time.monotonic()
        if remaining <= 0:
            raise Error("native_operation_timeout")
        handler = signal.signal(signal.SIGALRM, expired)
        previous = signal.setitimer(signal.ITIMER_REAL, 0)
        started = time.monotonic()
        signal.setitimer(
            signal.ITIMER_REAL, min(remaining, previous[0]) if previous[0] else remaining
        )
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, handler)
            if previous[0]:
                remaining = previous[0] - (time.monotonic() - started - budget.paused)
                if remaining <= 0:
                    raise Error("native_operation_timeout")
                signal.setitimer(signal.ITIMER_REAL, remaining, previous[1])


@contextmanager
def pause_browser_deadline():
    """Model calls keep their own deadline; restore the unspent browser budget."""
    with pause_browser_budget():
        remaining = signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, *remaining)


def _material_refusal(code, message, condition):
    """A material destination the Worker cannot prove, naming the unmet condition."""
    error = PortalDataError(code, message, 409)
    error.condition = condition
    return error


@contextmanager
def _fetch_without_redirects(route):
    """Browser redirect hops may bypass routing; never forward an unchecked hop."""
    response = route.fetch(max_redirects=0, max_retries=0, timeout=10000)
    try:
        if 300 <= response.status < 400:
            raise ValueError("redirect_result_unverified")
        yield response
    finally:
        response.dispose()


def _manual_submission_target(job, binding, *, document_url=None):
    """Recognize a concrete original-job endpoint, separately from a final operation."""
    if not isinstance(binding, dict):
        return False
    request, expected = urlsplit(binding.get("request_url", "")), urlsplit(job["job_url"])
    if (
        binding.get("job_url") != job["job_url"]
        or binding.get("method") != "POST"
        or request.scheme != "https"
        or request.netloc != expected.netloc
        or not hosted_ats.matches_page(binding.get("page_url", ""), job, document_url=document_url)
    ):
        return False
    if job["platform"] == "lever":
        return request.path.rstrip("/") == expected.path.rstrip("/") + "/apply"
    if job["platform"] == "greenhouse":
        return request.path.rstrip("/") == expected.path.rstrip("/")
    # A generic GraphQL operation name alone carries no verified job identity.
    return False


# A slow original-page read, repeated before it fails: a timed-out read's detach can
# replace its timeout with the outer one, and the ordinary call deadline is another.
SLOW_READS = frozenset(
    {"owned_browser_read_timeout", "owned_browser_outer_timeout", "native_operation_timeout"}
)


def _abort(route) -> None:
    # A request whose page or frame already closed has nothing left to block; its
    # failed abort is not a lost browser connection (seen on a job board, 2026-10-31).
    with suppress(Error):
        route.abort("blockedbyclient")


# How often an unconfirmed takeover stop is re-read (a status read, never a resend).
STOP_RECHECK_INTERVAL = 2.0


def _log_admission_denial(call, condition):
    """Private log of why the Worker denied a native call; never its arguments."""
    print(
        "native_admission_denied: "
        + json.dumps(
            {
                "tool": call.get("tool"),
                "role": (call.get("field_hint") or {}).get("role"),
                "condition": condition,
            }
        ),
        flush=True,
    )


def _log_typing_denial(call, fact, confirmed, condition):
    """Private log of a denied native write: its fact and role, never a value."""
    hint = call.get("field_hint") or {}
    print(
        "native_type_admission_denied: "
        + json.dumps(
            {
                "tool": call.get("tool"),
                "role": hint.get("role"),
                "label": str(hint.get("label") or "")[:80],
                "fact": fact,
                "confirmed_values": confirmed,
                "condition": condition,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def _callers(depth=4):
    """The nearest worker functions on this stack, for the private log only."""
    import traceback

    frames = [
        frame.name
        for frame in traceback.extract_stack()[:-2]
        if frame.filename.endswith("application_worker_browser.py")
    ]
    return frames[-depth:]


def _require_owned_document(session, expected_document):
    """Require the original document's token through an owned CDP session."""
    # CDP property descriptors do not invoke a page-defined getter.
    result = session.send(
        "Runtime.evaluate",
        {"expression": "this", "silent": True, "returnByValue": False},
    )
    handle = result.get("result", {}).get("objectId")
    if result.get("exceptionDetails") or not isinstance(handle, str):
        raise PortalDataError("page_observation_changed", "原页文档不能核验。", 409)
    try:
        properties = session.send(
            "Runtime.getProperties", {"objectId": handle, "ownProperties": True}
        ).get("result", [])
        descriptor = next(
            (row for row in properties if row.get("name") == "__tomorrowstarMaterialDocument"),
            {},
        )
        value = descriptor.get("value") or {}
        if (
            "get" in descriptor
            or "set" in descriptor
            or value.get("type") != "string"
            or value.get("value") != expected_document
        ):
            raise PortalDataError("page_observation_changed", "原页文档已改变。", 409)
    finally:
        with browser_deadline(1):
            session.send("Runtime.releaseObject", {"objectId": handle})


class ApplicationRunner:
    def __init__(
        self,
        store: WorkerStore,
        context,
        fixture_origin: str = "",
        *,
        cua=None,
        native_assistance_policy=None,
    ):
        self.store, self.context, self.origin = store, context, fixture_origin
        self.cua = cua
        self.native_assistance_policy = validate_native_assistance_policy(native_assistance_policy)
        self.codex_assist = None
        self._assistance_run = None
        # Native calls this page thread is admitting or recording right now.
        self._native_work = 0
        self._last_scope_check = None
        self._permit_failure = None
        self._assistance_baseline = None
        self._servicing_assistance_stop = False
        # (run_id, next attempt, delay): an unconfirmed stop is retried, not every tick.
        self._assistance_stop_retry = (None, 0.0, 0.0)
        self._dispatched: set[tuple[str, str]] = set()
        self.pages: dict[str, Page] = {}
        self.guards: dict[str, object] = {}
        self.temporary: dict = {}
        self.batch_id = self.store.load()["batch_id"]
        self.live = self.store.load()["mode"] == "live"
        self.handed_off_pages: set = set()
        # Pages waiting for the user's own sign-in; the script does not write there.
        self.login_pages: set = set()
        self.upload_job: dict | None = None
        self.bound_material_read = None
        self.blocked_pages: dict[Page, str] = {}
        # Each page's job id, URL and platform for the request guard (never changes).
        self.page_targets: dict[Page, dict] = {}
        self.document_urls: dict[Page, str] = {}
        self.drafts: dict[Page, DraftSession] = {}
        self.workable: dict[Page, ResumeUpload] = {}
        self.transports: list[dict] = []
        self.requests: dict = {}
        self.request_sequence = 0
        self.sent_requests: set[tuple[str, str, str]] = set()
        self.run_id = self.store.load().get("runtime", {}).get("id")
        self._page_thread = threading.get_ident()
        self._page_source = ((self.store.load().get("runtime") or {}).get("source") or {}).get(
            "sha256"
        )
        self.events: list[dict] = []
        self.page_faults: dict[Page, str] = {}
        self.page_ids: dict[Page, str] = {}
        self.shared_fault = ""
        self.storage_stopped = False
        self.stopped_serial = 0
        self.action_timeout = 35.0
        self.work_progressed = False
        if context is not None:
            context.on("close", lambda *_: self.event("context_closed"))
            if context.browser is not None:
                context.browser.on("disconnected", lambda *_: self.event("browser_disconnected"))
        if context is not None:
            context.on("request", lambda request: self.transport(request, "request"))
            context.on(
                "response",
                lambda response: self.transport(response.request, "response", response.status),
            )
            context.on(
                "requestfinished", lambda request: self.transport(request, "requestfinished")
            )
            context.on("requestfailed", lambda request: self.transport(request, "requestfailed"))
        if hasattr(context, "add_init_script"):  # synthetic context doubles omit it
            context.add_init_script(SUBMIT_LOCK_INSTALL)
        if self.live and context is not None:
            context.route("**/*", self._live_guard)
            context.route_web_socket("**/*", lambda ws: self._websocket_guard(None, ws))
            context.on("requestfinished", self._draft_finished)

    def track_request(self, request, job: dict, kind: str) -> bool:
        if hosted_ats.is_final_submission(request, job):
            return False
        intent = job.get("intent")
        if intent:
            attempt = intent.get("attempt_id") or digest(intent)
            permit = (job["application_id"], attempt, kind)
            if permit in self.sent_requests or any(
                event.get("stage") == "dispatch_authorized"
                and event.get("attempt_id") == attempt
                and event.get("kind") == kind
                for event in job["observations"]
            ):
                return False
            # Consume before dispatch, including when the response later fails.
            self.sent_requests.add(permit)
            record = {
                "application_id": job["application_id"],
                "run_id": self.run_id,
                "attempt_id": attempt,
                "action": intent["action"],
                "intent": deepcopy(intent),
                "batch_id": self.batch_id,
                "kind": kind,
            }
            self.requests[request] = record
            # This is permission to dispatch, not proof of remote application.
            self.transports.append({**record, "stage": "dispatch_authorized", "at": time.time()})
            return True
        return False

    def request_diagnostic(
        self, request, page, job, state, stage, reason, *, sequence, caused_stop=False
    ):
        """Retain a blocked final operation in the private checkpoint, never its body."""
        intent = deepcopy(job.get("intent"))
        self.transports.append(
            {
                "action": "request_diagnostic",
                "request_id": uuid4().hex,
                "sequence": sequence,
                "stage": stage,
                "method": request.method,
                **dict(zip(("url", "query_keys"), diagnostic_url(request.url), strict=True)),
                "resource_type": request.resource_type,
                "purpose": "unknown",
                "dispatch": "not_sent" if stage == "request_blocked" else "unknown",
                "application_id": job["application_id"],
                "batch_id": state["batch_id"],
                "run_id": self.run_id,
                "page_id": self.page_ids.get(page),
                "attempt_id": (intent or {}).get("attempt_id"),
                "field_id": (intent or {}).get("field_id"),
                "intent": intent,
                "reason": reason,
                "caused_stop": caused_stop,
                "at": time.time(),
            }
        )

    def transport(self, request, stage: str, status=None) -> None:
        record = self.requests.get(request)
        if record:
            if record.get("kind") == "native_material_upload":
                self._native_upload_answer(record, stage, status)
            if stage == "response":
                record["http_status"] = status
            row = {
                **record,
                "stage": stage,
                "at": time.time(),
                **({"http_status": status} if status is not None else {}),
            }
            if stage == "requestfailed":
                # ``http_status`` stays the earlier response's (an Ashby 204 ACK then
                # ERR_ABORTED is acknowledged); the browser's reason is kept beside it,
                # which a 200 S3 PUT followed by requestfailed lacked (2026-11-03).
                with suppress(Exception):
                    row["failure"] = str(request.failure or "")[:200]
            self.transports.append(row)
            if stage in {"requestfinished", "requestfailed"}:
                self.requests.pop(request, None)

    def record_transports(self, state: dict) -> None:
        for event in self.transports:
            job = next(
                (j for j in state["jobs"] if j["application_id"] == event["application_id"]), None
            )
            if job and event not in job["observations"]:
                job["observations"].append(event)
                if _unresolved_write_failure(event, job, state):
                    # A local DOM read may finish before the remote failure arrives.
                    # Keep that history, but retain the attempt for explicit recovery.
                    if job["intent"] is None:
                        job["intent"] = deepcopy(event["intent"])
                    job.update(
                        status="needs_recheck",
                        reason=event.get("reason")
                        or (
                            "upload_result_unknown"
                            if event["intent"]["action"] == "upload"
                            else "draft_result_unknown"
                        ),
                    )
                    page = self.pages.get(job["application_id"])
                    if page is not None:
                        self.blocked_pages[page] = job["reason"]
                        if page in self.workable:
                            self.workable[page].failed = True

    def persist(self, state: dict) -> None:
        try:
            self.record_transports(state)
            self.store.save(state)
            self.transports.clear()
        except (OSError, ValueError, TypeError):
            self.unsaved_state = deepcopy(state)
            self.storage_stopped = True
            self.stopped_serial = state.get("resume_serial", 0)
            self.store.block_storage()
            raise

    def permitted(self, state: dict, page=None) -> bool:
        return (
            not self.shared_fault
            and not self.storage_stopped
            and not self.store.stop_reason()
            and page not in self.page_faults
            and page not in self.blocked_pages
            and not any(
                _unresolved_write_failure(event, job, state)
                for event in self.transports
                for job in state["jobs"]
                if (
                    "current_job_id" not in state
                    or job["application_id"] == state["current_job_id"]
                )
                and (page is None or self.pages.get(job["application_id"]) is page)
            )
            and (
                page is None
                or "current_job_id" not in state
                or self.pages.get(state["current_job_id"]) is page
            )
            and state["control"] == "running"
            and script_writes_allowed(state)
            and state.get("applications_root") == str(self.store.applications.root)
            and (not self.run_id or state.get("runtime", {}).get("id") == self.run_id)
        )

    def _native_material_network_permitted(self, state, job, page):
        """Allow a sealed original attempt without granting general script writes."""
        assistance = job.get("assistance") or {}
        if assistance.get("protocol") != "codex-assistance/native/v1":
            return False
        reference = assistance_reference(assistance)
        intent = self.store.native_material_intent(state, job, reference)
        if (
            not intent
            or state.get("control") != "running"
            or job["status"] != "filling"
            or job.get("handed_off")
            or self.pages.get(job["application_id"]) is not page
            or any(
                _unresolved_write_failure(event, job, state)
                for event in [*job["observations"], *self.transports]
            )
        ):
            return False
        native = intent["native_material"]
        run = next(
            row for row in job["native_handoff_runs"] if row["request_id"] == native["request_id"]
        )
        receipt = next(
            (
                event["receipt"]
                for event in reversed(run["events"])
                if event.get("receipt") is not None
            ),
            {},
        )
        call = next(
            (row for row in receipt.get("calls", []) if row["call_id"] == native["call_id"]), None
        )
        if (
            receipt.get("revoked")
            or call is None
            or any(row.get("status") == "unknown" for row in receipt.get("calls", []))
            or call.get("status") not in {"awaiting_host", "in_flight", "observed"}
            or call.get("material_resolution") != native["resolution"]
        ):
            return False
        try:
            original, check = self._assistance_page_checker(reference)
            check()  # Store/handle checks only; never wait on the busy renderer.
            return original is page
        except (PortalDataError, OSError, StoreError, ValueError):
            return False

    def event(self, kind: str, page=None, identifier=None) -> None:
        # Callbacks only collect facts. Authorization sees them immediately.
        if page is None:
            self.shared_fault = kind
        else:
            self.page_faults[page] = kind
        self.events.append(
            {
                "event": kind,
                "run_id": self.run_id,
                "page_id": self.page_ids.get(page),
                "application_id": identifier,
                "at": time.time(),
            }
        )

    def pump(self, idle_ms: int = 250) -> None:
        if self.shared_fault:
            time.sleep(0.25)
            return
        try:
            # A local timer and owned task keep control moving without throwing
            # SIGALRM into Playwright's dispatcher, including under an outer scope.
            pump_events(self.context, 5 if self.work_progressed else idle_ms)
        except TimeoutError:
            pass
        except Error as error:
            if getattr(error, "message", "") == "owned_browser_read_timeout":
                # A busy page (many blocked requests) overran this idle wait; the
                # browser is still connected and the wait settles on its own.
                return
            if not self.shared_fault:
                # The private log keeps the cause; the job record keeps only the event.
                print("browser_connection_unknown: " + repr(error)[:500], flush=True)
                self.event("browser_connection_unknown")

    def drain_events(self, state: dict) -> None:
        for event in self.events:
            identifier = event["application_id"]
            if identifier is None:
                state.update(control="paused", worker_error=event["event"])
                state.setdefault("observations", []).append(event)
                for job in state["jobs"]:
                    job["page_observation"] = event
                    if job["status"] != "cancelled":
                        job.update(status="needs_recheck", reason=event["event"])
                continue
            job = next((j for j in state["jobs"] if j["application_id"] == identifier), None)
            if job is None:
                continue
            job["page_observation"] = event
            job["observations"].append(event)
            job["page_open"] = False
            if job["status"] != "cancelled":
                job.update(status="needs_recheck", reason=event["event"])
            page = self.pages.get(identifier)
            if page:
                self._forget_page(identifier, page)
        self.events.clear()

    def _draft_finished(self, request) -> None:
        # Parse only after the body has finished. A slow body stays in the bounded draft wait.
        response = request.response()
        if response is not None:
            self._draft_response(response)

    def _draft_response(self, response) -> None:
        page = None
        try:
            page = response.request.frame.page
            if page in self.drafts:
                self.drafts[page].response(response)
            if page in self.workable:
                self.workable[page].response(response)
        except (Error, ValueError, TypeError, KeyError, IndexError):
            if page is not None:
                self.blocked_pages[page] = "draft_result_unverified"
                if page in self.drafts:
                    self.drafts[page].failed = True
                if page in self.workable:
                    self.workable[page].failed = True
                    self.blocked_pages[page] = "upload_result_unknown"

    def observe(self, page: Page, job: dict) -> dict:
        with self.store.measurements.stage(
            "form_scan",
            episode_id=job.get("measurement_id"),
            application_id=job["application_id"],
            run_id=self.run_id,
        ):
            observed = self._observe(page, job)
            draft = self.drafts.get(page)
            if draft:
                for question in observed["fields"]:
                    entry = draft.fields.get(question.get("draft_path"), {})
                    if entry.get("isRequired") and not entry.get("isHidden"):
                        question["required"] = True
            if self.live:
                from .application_materials import material_kind

                for question in observed["fields"]:
                    if material_kind(question) == "cover_letter":
                        question.update(
                            hosted_ats.control(page, question).evaluate(
                                "e => ({accept:e.getAttribute('accept') || '',"
                                "max_length:e.maxLength >= 0 ? e.maxLength : null})"
                            )
                        )
            return observed

    def _observe(self, page: Page, job: dict) -> dict:
        if page in self.page_faults or self.shared_fault:
            raise PortalDataError(
                self.page_faults.get(page, self.shared_fault), "页面需要核验。", 409
            )
        if self.live:
            if page in self.blocked_pages:
                state = self.store.load()
                current = next(
                    row for row in state["jobs"] if row["application_id"] == job["application_id"]
                )
                intent = deepcopy(current.get("intent"))
                blocked = next(
                    (
                        row
                        for row in reversed([*current["observations"], *self.transports])
                        if row.get("action") == "request_diagnostic"
                        and row.get("stage")
                        in {
                            "request_blocked",
                            "public_read_response_rejected",
                            "request_response_rejected",
                        }
                        and row.get("caused_stop") is True
                        and row.get("reason") == self.blocked_pages[page]
                        and row.get("application_id") == current["application_id"]
                        and row.get("batch_id") == state["batch_id"]
                        and row.get("run_id") == self.run_id
                        and row.get("page_id") == self.page_ids.get(page)
                    ),
                    {},
                )
                self.transports.append(
                    {
                        "action": "readback_diagnostic",
                        "stage": "before_dom_read",
                        "request_id": blocked.get("request_id"),
                        "reason": self.blocked_pages[page],
                        "application_id": current["application_id"],
                        "batch_id": state["batch_id"],
                        "run_id": self.run_id,
                        "page_id": self.page_ids.get(page),
                        "attempt_id": (intent or {}).get("attempt_id"),
                        "field_id": (intent or {}).get("field_id"),
                        "intent": intent,
                        "at": time.time(),
                    }
                )
                raise PortalDataError(self.blocked_pages[page], "页面发送路径需要人工核验。", 409)
            if page in self.document_urls:
                return hosted_ats.observe(page, job, document_url=self.document_urls[page])
            return hosted_ats.observe(page, job)
        form = form_for(job)
        if page.is_closed() or page.url != self.origin + form.page_path(job["application_id"]):
            raise PortalDataError("page_changed", "页面已关闭或岗位来源已变更。", 409)
        result = page.evaluate(form.inspect_script())
        identity = result["identity"]
        if identity != {
            "company": job["company"],
            "role": job["role_title"],
            "jobUrl": job["job_url"],
        }:
            raise PortalDataError("identity_changed", "公司、岗位或表单身份已变更。", 409)
        fields = result["fields"]
        if (
            not fields
            or len({q["id"] for q in fields}) != len(fields)
            or any(
                not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,99}", q["id"])
                or not q["question"]
                or q.get("multiple", False)
                or q["type"]
                not in {"text", "email", "tel", "url", "date", "textarea", "select", "file"}
                for q in fields
            )
        ):
            raise PortalDataError("unsupported_structure", "表单结构需要人工核验。", 409)
        files = [q for q in fields if q["type"] == "file"]
        if len(files) != 1 or files[0]["id"] != "resume":
            raise PortalDataError("unsupported_attachments", "附件结构未验证。", 409)
        return result

    def check_inputs(self, job: dict, *, material_required: bool | None = None) -> None:
        if material_required is None:
            material_required = (
                job.get("workflow") != "single"
                or (job.get("intent") or {}).get("action") == "upload"
            )
        state = self.store.load()
        fixed_qualification = (
            self.store.check_single(job, state, material_required=material_required) is True
        )
        self.store.check_generic_enabled(job, state)
        app = self.store.applications.get_application(job["application_id"])
        task = validate_application_target(
            self.store.applications,
            job["application_id"],
            job["revision"],
            allow_generic=state.get("generic_enabled") is True,
        )
        if app["status"] != "drafting" or task["job_url"] != job["job_url"]:
            raise PortalDataError("input_changed", "原申请记录已变更。", 409)
        if self.live and not fixed_qualification:
            # The checked single binding owns the delivered P04 qualification.
            # Legacy deliveries retain their language adapter.
            self.store.check_language_requirement(app, country=job["country"])
        if material_required:
            if (
                hashlib.sha256(Path(job["file_path"]).read_bytes()).hexdigest()
                != job["file_sha256"]
            ):
                raise PortalDataError("file_changed", "所选简历版本已变更。", 409)
            for material in job.get("materials", []):
                if material.get("status") == "ready":
                    self.store.verify_material(material, job)

    def _guard(self, identifier: str, platform: str = "lever"):
        if self.live:
            return self._live_guard

        def guard(route):
            request = route.request
            if hosted_ats.is_final_submission(request, None):
                page = self.pages.get(identifier)
                if page is not None:
                    self.blocked_pages[page] = "manual_submit_required"
                route.abort("blockedbyclient")
                return
            allowed = request.url.startswith(self.origin + "/") and (
                request.method == "GET"
                or request.url == self.origin + FORMS[platform].upload_path(identifier)
                and request.method == "POST"
            )
            if allowed and request.method != "GET":
                try:
                    state = self.store.load()
                    current = next(j for j in state["jobs"] if j["application_id"] == identifier)
                    self.check_inputs(current)
                    allowed = (
                        self.permitted(state, self.pages.get(identifier))
                        and not current["handed_off"]
                        and current["status"] == "filling"
                        and current["intent"] is not None
                        and current["intent"]["action"] == "upload"
                    )
                except (PortalDataError, OSError, StoreError, ValueError, KeyError, StopIteration):
                    self.storage_stopped = True
                    self.store.block_storage()
                    allowed = False
            if allowed and request.method != "GET":
                allowed = self.track_request(request, current, "upload")
            if allowed:
                try:
                    with _fetch_without_redirects(route) as response:
                        route.fulfill(response=response)
                except (Error, ValueError, TypeError, KeyError, OSError):
                    page = self.pages.get(identifier)
                    if page is not None:
                        self.blocked_pages[page] = (
                            "upload_result_unknown"
                            if request.method != "GET"
                            else "public_read_result_unknown"
                        )
                    route.abort("blockedbyclient")
            else:
                route.abort("blockedbyclient")

        return guard

    def _live_guard(self, route) -> None:
        try:
            self._live_guard_request(route)
        except (OSError, StoreError, PortalDataError, ValueError, KeyError, StopIteration):
            self.storage_stopped = True
            self.store.block_storage()
            _abort(route)

    def _page_target(self, page):
        """The page's job identity (id, URL, platform), cached: it never changes."""
        target = self.page_targets.get(page)
        if target is None:
            job = next(
                (
                    row
                    for row in self.store.load()["jobs"]
                    if self.pages.get(row["application_id"]) is page
                ),
                None,
            )
            if job is None:
                return None
            target = self.page_targets[page] = {
                key: job[key] for key in ("application_id", "job_url", "platform")
            }
        return target

    def _live_guard_request(self, route) -> None:
        """Observe the user's Submit, stop a known final operation, register own writes.

        Every other page request (analytics, captcha, POST reads, draft autosave,
        logs) passes and never stops the job: none submitted an application on ten
        real sites (survey 2026-11-04). APP-11 is kept at the action layer.
        """
        request = route.request
        try:
            page = request.frame.page
        except Error:
            _abort(route)
            return
        if page in self.handed_off_pages:
            state = self.store.load()
            job = next(
                (row for row in state["jobs"] if self.pages.get(row["application_id"]) is page),
                None,
            )
            if job and hosted_ats.is_final_submission(request, job):
                record = {
                    "action": "manual_submit_observed",
                    "request_id": uuid4().hex,
                    "kind": "manual_submit",
                    "target_binding": {
                        "job_url": job["job_url"],
                        "request_url": request.url,
                        "method": request.method,
                        "page_url": getattr(page, "url", ""),
                    },
                    "application_id": job["application_id"],
                    "run_id": self.run_id,
                    "batch_id": state["batch_id"],
                    "page_id": self.page_ids.get(page),
                }
                # Observation failure must not prevent the human's own request.
                # Without a tracked response the result remains unknown.
                with suppress(TypeError):
                    self.requests[request] = record
                self.transports.append(record | {"stage": "request", "at": time.time()})
            route.continue_()
            return
        target = self._page_target(page)
        if hosted_ats.is_final_submission(request, target):
            _abort(route)
            if page in self.login_pages or target is None:
                return
            previous_stop = self.blocked_pages.get(page)
            self.blocked_pages[page] = "manual_submit_required"
            state = self.store.load()
            job = next(
                row for row in state["jobs"] if row["application_id"] == target["application_id"]
            )
            self.request_sequence += 1
            self.request_diagnostic(
                request,
                page,
                job,
                state,
                "request_blocked",
                "manual_submit_required",
                sequence=self.request_sequence,
                caused_stop=previous_stop != "manual_submit_required",
            )
            return
        upload_page = self.upload_job and page is self.pages.get(self.upload_job["application_id"])
        if page in self.login_pages or not (
            page in self.drafts or page in self.workable or upload_page
        ):
            route.continue_()
            return
        self._route_own_write(route, request, page)

    def _route_own_write(self, route, request, page) -> None:
        """Register a request that carries the system's own pending write (APP-13).

        Lever resume parsing, an Ashby draft save and a Workable upload are tracked
        so their unknown or failed result stops the job; anything else continues.
        """
        state = self.store.load()
        owned_job = next(
            (job for job in state["jobs"] if page is self.pages.get(job["application_id"])),
            None,
        )
        editing_material = bool(
            precision_preparation_pending(owned_job)
            or owned_job
            and material_edit_pending(owned_job)
        )
        if self.upload_job and page is self.pages.get(self.upload_job["application_id"]):
            current = next(
                j for j in state["jobs"] if j["application_id"] == self.upload_job["application_id"]
            )
            if (
                not editing_material
                and self.permitted(state, page)
                and not current["handed_off"]
                and current["status"] == "filling"
                and current["intent"] is not None
                and current["intent"]["action"] == "upload"
                and hosted_ats.is_resume_parse(request, self.upload_job)
            ):
                try:
                    self.check_inputs(current)
                    self.track_request(request, current, "resume_parse")
                except PortalDataError as error:
                    self.blocked_pages[page] = error.code
                    _abort(route)
                    return
        draft = self.drafts.get(page)
        if (
            draft
            and owned_job
            and owned_job["platform"] == "generic"
            and not draft.track_public(request)
            and not editing_material
        ):
            current = owned_job
            native_material = (
                self._native_material_network_permitted(state, current, page)
                and request.frame is page.main_frame
                and request.redirected_from is None
            )
            if (
                (self.permitted(state, page) or native_material)
                and current["status"] == "filling"
                and draft.active
                and current["intent"] == draft.active["intent"]
            ):
                try:
                    self.check_inputs(current)
                    ref = current["intent"].get("answer_ref")
                    if ref and ref["key"] != "one-use" and ref.get("source") != "system_material":
                        record = self.store.answers_for(current).get_answer(ref["key"])
                        if record is None or digest(record) != ref["revision"]:
                            raise ValueError
                    if draft.allows(request):
                        self.track_request(request, current, draft.pending[request][0])
                except (PortalDataError, OSError, ValueError):
                    pass
        workable = self.workable.get(page)
        if not (workable and workable.sensitive(request)):
            route.continue_()
            return
        # Workable storage requests are the system's own upload protocol: one is
        # sent only for the pending upload and its answer is checked before use.
        workable_kind = None
        current = owned_job
        if (
            current
            and not editing_material
            and request.frame == page.main_frame
            and request.redirected_from is None
            and page.url == current["job_url"]
            and self.permitted(state, page)
            and not current["handed_off"]
            and current["status"] == "filling"
            and current["intent"] == workable.active
            and current["intent"] is not None
            and current["intent"]["action"] == "upload"
            and current["intent"].get("sha256") == current["file_sha256"]
            and current["intent"].get("page_id") == self.page_ids.get(page)
        ):
            try:
                require_execution(
                    self.store.applications,
                    current["application_id"],
                    automated_owner(self.store.root, state["batch_id"], current["application_id"]),
                    "automated",
                )
                self.check_inputs(current)
                kind = workable.allows(request)
                if kind and self.track_request(request, current, kind):
                    workable_kind = kind
            except (PortalDataError, OSError, ValueError, TypeError, KeyError):
                workable.failed = True
        read = self.bound_material_read or {}
        if (
            not workable_kind
            and current
            and read.get("page") is page
            and read.get("application_id") == current["application_id"]
            and read.get("material_update_id") == (current.get("material_update") or {}).get("id")
            and (current.get("material_update") or {}).get("status")
            in {"inspect_pending", "page_verified", "bound"}
            and state.get("control") in {"paused", "running"}
            and current.get("intent") == read.get("intent")
            and not manual_submission_unresolved(
                {**current, "observations": [*current["observations"], *self.transports]}
            )
            and not any(
                _unresolved_write_failure(event, current, state) for event in self.transports
            )
            and (
                read.get("intent") is None
                or self.permitted(state, page)
                and current["status"] == "filling"
                and not current["handed_off"]
            )
            and workable.reading
            and workable.handle
            and request.frame == page.main_frame
            and request.redirected_from is None
            and request.method == "GET"
            and request.url == workable.handle["downloadUrl"]
            and request.post_data_buffer is None
            and request.resource_type in {"fetch", "xhr"}
            and (state.get("runtime") or {}).get("id") == self.run_id
            and self.page_ids.get(page) == (current.get("page_observation") or {}).get("page_id")
        ):
            workable_kind = workable.allows(request)
            if workable_kind != "workable_readback":
                workable_kind = None
        if not workable_kind:
            workable.failed = True
            _abort(route)
            return
        # Fetch the exact request once, refusing redirects/retries, and check its
        # actual response before the page can consume it.
        try:
            with _fetch_without_redirects(route) as response:
                workable.response(response, request=request)
                route.fulfill(response=response)
        except (Error, ValueError, TypeError, KeyError, OSError):
            workable.failed = True
            self.blocked_pages[page] = "upload_result_unknown"
            _abort(route)

    def _websocket_guard(self, page, websocket) -> None:
        if getattr(self, "synthetic_browser", False):
            # Synthetic pages stay local.
            websocket.on_message(lambda _message: None)
            return
        websocket.connect_to_server()

    @staticmethod
    def _submit_lock(page, locked: bool) -> None:
        """Lock (before automated work) or unlock (handoff, sign-in) every frame's forms.

        A new document starts unlocked; the next automated send locks it again.
        """
        # Synthetic page doubles without frames have no forms to lock.
        for frame in getattr(page, "frames", ()):
            with suppress(Error):
                frame.evaluate(SUBMIT_LOCK_SET, locked)

    def _forget_page(self, identifier: str, page: Page) -> None:
        self.pages.pop(identifier, None)
        self.guards.pop(identifier, None)
        self.drafts.pop(page, None)
        self.workable.pop(page, None)
        self.document_urls.pop(page, None)
        self.blocked_pages.pop(page, None)
        self.handed_off_pages.discard(page)
        self.login_pages.discard(page)
        self.page_ids.pop(page, None)
        self.page_targets.pop(page, None)
        self.page_faults.pop(page, None)
        for request, record in list(self.requests.items()):
            if record["application_id"] == identifier:
                self.requests.pop(request)

    def commands(self, state: dict) -> None:
        retained = []
        for command in state["commands"]:
            job = next(
                (row for row in state["jobs"] if row["application_id"] == command.get("id")),
                None,
            )
            if (
                command["action"] == "recover-backend"
                and job
                and job.get("assistance")
                and not assistance_stop_pending(job)
            ):
                # The original persistent command remains until the unlocked
                # read-only service has conditionally saved its observation.
                self._backend_recovery_candidate = deepcopy(command)
                retained.append(command)
                continue
            if not script_writes_allowed(state, command.get("id")):
                retained.append(command)
                continue
            try:
                with browser_deadline(5):
                    self._command(state, command)
            except (Error, PortalDataError, ValueError, KeyError, TypeError) as exc:
                job = next(
                    (j for j in state["jobs"] if j["application_id"] == command.get("id")), None
                )
                if command["action"] == "recover-backend":
                    receipt = state.get("backend_recovery") or {}
                    if receipt.get("request_id") == command.get("request_id"):
                        receipt.update(
                            status="needs_recheck",
                            reason=getattr(exc, "code", "backend_recovery_failed"),
                        )
                    state["control"] = "paused"
                    continue
                if job:
                    if command["action"] == "inspect-handoff":
                        receipt = (state.get("runtime") or {}).get("controller_handoff") or {}
                        if receipt.get("request_id") == command.get("request_id"):
                            receipt.update(
                                status="failed",
                                captured_at=time.time(),
                                reason=getattr(exc, "code", "handoff_capture_failed"),
                                execution_authority=False,
                            )
                        continue
                    if command["action"] == "observe-page":
                        receipt = job.get("owned_page_inspection") or {}
                        if receipt.get("request_id") == command.get("request_id"):
                            receipt.update(
                                status="failed",
                                at=time.time(),
                                reason=getattr(exc, "code", "page_observation_failed"),
                            )
                        continue
                    if command["action"] == "observe-result":
                        (job.get("submission_observation") or {}).update(
                            status="observed",
                            conclusion="unknown",
                            reason=getattr(exc, "code", "page_command_failed"),
                        )
                        continue
                    if command["action"] == "continue-current":
                        (job.get("continuation") or {}).update(
                            status="needs_recheck",
                            reason=getattr(exc, "code", "page_command_failed"),
                        )
                        state["control"] = "paused"
                    if job["status"] != "cancelled":
                        job.update(
                            status="needs_recheck",
                            reason=getattr(exc, "code", "page_command_failed"),
                        )
                    job["observations"].append(
                        {
                            "event": "page_command_failed",
                            "run_id": self.run_id,
                            "stage": command["action"],
                            "reason": getattr(exc, "code", "page_command_failed"),
                            "at": time.time(),
                        }
                    )
                    if command["action"] == "review":
                        job["handed_off"] = True
                        job["handoff"] = {
                            "status": "unknown",
                            "run_id": self.run_id,
                            "at": time.time(),
                            "source": "user_requested_handoff",
                        }
        state["commands"] = retained

    def service_backend_recovery(self):
        """Read an original stopped Codex page outside the business write lock."""
        command = getattr(self, "_backend_recovery_candidate", None)
        self._backend_recovery_candidate = None
        if command is None:
            return None
        identifier = command.get("id")
        with self.store.applications.write_lock():
            state = self.store.load()
            job = next((row for row in state["jobs"] if row["application_id"] == identifier), None)
            receipt = state.get("backend_recovery") or {}
            if command not in state["commands"]:
                return None
            if (
                receipt.get("request_id") != command.get("request_id")
                or receipt.get("status") != "pending"
            ):
                state["commands"] = [row for row in state["commands"] if row != command]
                self.store.save(state)
                return None
            if not job or not job.get("assistance") or assistance_stop_pending(job):
                return None
            reference = assistance_reference(job["assistance"])
            if digest(receipt.get("assistance_ref")) != digest(reference):
                receipt.update(
                    status="needs_recheck",
                    reason="backend_recovery_unbound"
                    if "assistance_ref" not in receipt
                    else "assistance_generation_changed",
                )
                state["commands"] = [row for row in state["commands"] if row != command]
                self.store.save(state)
                return deepcopy(receipt)
            binding = deepcopy(receipt["binding"])
            expected_lock = deepcopy(receipt.get("worker_lock"))
            page = self.pages.get(identifier)

        def validate(current):
            current_job = next(
                (row for row in current["jobs"] if row["application_id"] == identifier), None
            )
            current_receipt = current.get("backend_recovery") or {}
            if current_job:
                require_execution(
                    self.store.applications,
                    identifier,
                    automated_owner(self.store.root, current["batch_id"], identifier),
                    "automated",
                )
            descriptor = getattr(self.store, "worker_lock_descriptor", None)
            actual_lock = None
            if descriptor is not None:
                observed = os.fstat(descriptor)
                actual_lock = {"device": observed.st_dev, "inode": observed.st_ino}
            runtime = current.get("runtime") or {}
            if (
                not current_job
                or not current_job.get("assistance")
                or assistance_stop_pending(current_job)
                or digest(assistance_reference(current_job["assistance"])) != digest(reference)
                or digest(assistance_binding(current, current_job)) != digest(reference["binding"])
                or current_receipt.get("request_id") != command.get("request_id")
                or current_receipt.get("status") != "pending"
                or digest(current_receipt.get("assistance_ref")) != digest(reference)
                or current_receipt.get("binding") != binding
                or not backend_recovery_timely(current_receipt)
                or current["control"] != "paused"
                or current.get("current_job_id") != identifier
                or current.get("controller") != current_receipt.get("controller")
                or handoff_binding(current, current_job) != binding
                or runtime.get("id") != self.run_id
                or runtime.get("pid") != os.getpid()
                or runtime.get("source", {}).get("sha256") != self._page_source
                or current.get("worker_pid") != os.getpid()
                or actual_lock is None
                or actual_lock != expected_lock
                or not worker_lock_is_held(self.store.root, actual_lock)
                or not (
                    current_job["status"] in {"queued", "filling"}
                    and not current_job.get("reason")
                    or current_job["status"] == "needs_recheck"
                    and current_job.get("reason") == "backend_authority_lost"
                    and current_job["assistance"].get("backend_loss")
                )
                or current_job.get("intent")
                or current_job.get("handed_off")
                or not current_job["page_open"]
                or manual_submission_unresolved(
                    {
                        **current_job,
                        "observations": [*current_job["observations"], *self.transports],
                    }
                )
                or self.shared_fault
                or self.storage_stopped
                or self.store.stop_reason()
                or page is None
                or self.pages.get(identifier) is not page
                or page.is_closed()
                or page.context is not self.context
                or page.url != reference["binding"]["step"]
                or self.context is None
                or not self.context.browser
                or not self.context.browser.is_connected()
                or self.page_ids.get(page) != reference["binding"].get("page_id")
                or page in self.blocked_pages
                or page in self.page_faults
                or page in self.handed_off_pages
            ):
                raise PortalDataError(
                    "backend_owner_unverified", "原接管页面或停止范围尚不能核验。", 409
                )

        def check():
            with self.store.applications.write_lock():
                validate(self.store.load())

        capture, failure = None, None
        try:
            check()
            with browser_deadline(5):
                capture = self._capture_owned_page(
                    page, check, expected_document=reference["binding"]["document_token"]
                )
            check()
        except (Error, OSError, PortalDataError, ValueError, KeyError, TypeError) as error:
            failure = getattr(error, "code", "backend_page_readback_failed")
        with self.store.applications.write_lock():
            current = self.store.load()
            current_receipt = current.get("backend_recovery") or {}
            if (
                current_receipt.get("request_id") == command.get("request_id")
                and current_receipt.get("status") == "pending"
            ):
                try:
                    validate(current)
                except (OSError, PortalDataError, ValueError, KeyError, TypeError) as error:
                    failure = getattr(error, "code", "backend_owner_unverified")
                current_receipt.update(
                    status="needs_recheck", reason=failure or "assistance_handoff_required"
                )
                if capture is not None and failure is None:
                    current_receipt.update(
                        page_verified=True,
                        verified_at=max(time.time(), capture["at"]),
                        run_id=self.run_id,
                        page_verification={
                            "protocol": "backend-page-verification/v1",
                            "at": capture["at"],
                            "assistance_ref": reference,
                            "document": capture["document"],
                            "data": capture["data"],
                            "worker_source": self._page_source,
                        },
                    )
            current["commands"] = [row for row in current["commands"] if row != command]
            self.store.save(current)
            return deepcopy(current_receipt)

    def _command(self, state: dict, command: dict) -> None:
        identifier = command.get("id")
        page = self.pages.get(identifier)
        job = next((j for j in state["jobs"] if j["application_id"] == identifier), None)
        if command["action"] == "inspect-material-update":
            from .application_bound_materials import inspect_runner

            try:
                inspect_runner(self, state, job, page, command)
            except (PortalDataError, OSError, ValueError, KeyError, TypeError) as error:
                if job:
                    job["material_update"].update(
                        status="needs_recheck",
                        error_code=getattr(error, "code", "bound_material_page_unknown"),
                    )
                raise
            return
        if command["action"] == "recover-backend":
            receipt = state.get("backend_recovery") or {}
            if (
                receipt.get("request_id") != command.get("request_id")
                or receipt.get("status") != "pending"
            ):
                return
            if job and job.get("assistance"):
                receipt.update(
                    status="needs_recheck",
                    reason="assistance_stop_pending"
                    if assistance_stop_pending(job)
                    else "assistance_handoff_required",
                )
                state["control"] = "paused"
                return
            if not backend_recovery_timely(receipt):
                receipt.update(status="needs_recheck", reason="backend_recovery_expired")
                state["control"] = "paused"
                return
            descriptor = getattr(self.store, "worker_lock_descriptor", None)
            lock_evidence = None
            if descriptor is not None:
                stat = os.fstat(descriptor)
                lock_evidence = {"device": stat.st_dev, "inode": stat.st_ino}
            if (
                not job
                or state["control"] != "paused"
                or state.get("current_job_id") != identifier
                or state.get("controller") != receipt.get("controller")
                or (state.get("runtime") or {}).get("id") != self.run_id
                or state.get("worker_pid") != os.getpid()
                or not worker_lock_is_held(self.store.root, lock_evidence)
                or handoff_binding(state, job) != receipt["binding"]
                or job["status"] not in {"queued", "filling"}
                or job.get("reason")
                or job.get("intent")
                or job.get("handed_off")
                or manual_submission_unresolved(
                    {**job, "observations": [*job["observations"], *self.transports]}
                )
                or self.shared_fault
                or self.storage_stopped
                or self.store.stop_reason()
                or page in self.blocked_pages
                or page in self.page_faults
                or job["page_open"]
                and (
                    page is None
                    or page.is_closed()
                    or page.context is not self.context
                    or self.page_ids.get(page) != (job.get("page_observation") or {}).get("page_id")
                )
            ):
                receipt.update(status="needs_recheck", reason="backend_owner_unverified")
                return
            self.check_inputs(job)
            if page is not None:
                observed = self.observe(page, job)
                # Read the retained original page before remaining work can write.
                # These are the same manual-value boundaries as one Continue.
                job["manual_fields"] = {
                    field["id"]: deepcopy(field)
                    for field in observed["fields"]
                    if field["type"] != "file"
                    and field.get("valid")
                    and field.get("value") not in (None, "", [])
                }
                job["manual_attachments"] = [
                    deepcopy(field) for field in observed["fields"] if field["type"] == "file"
                ]
                if manual_submission_unresolved(
                    {**job, "observations": [*job["observations"], *self.transports]}
                ):
                    receipt.update(status="needs_recheck", reason="submission_result_unknown")
                    return
            if not backend_recovery_timely(receipt):
                receipt.update(status="needs_recheck", reason="backend_recovery_expired")
                state["control"] = "paused"
                return
            receipt.update(
                status="verified",
                verified_at=time.time(),
                run_id=self.run_id,
                worker_lock=lock_evidence,
            )
            state.update(control="running", heartbeat_at=time.time())
            return
        if command["action"] == "inspect-handoff":
            runtime = state.get("runtime") or {}
            receipt = runtime.get("controller_handoff") or {}
            identity = process_identity(os.getpid())
            worker_lock = None
            descriptor = getattr(self.store, "worker_lock_descriptor", None)
            if descriptor is not None:
                try:
                    held = os.fstat(descriptor)
                    current = (self.store.root / ".worker.lock").lstat()
                    if (held.st_dev, held.st_ino) == (current.st_dev, current.st_ino):
                        worker_lock = {"device": held.st_dev, "inode": held.st_ino}
                        if not worker_lock_is_held(self.store.root, worker_lock):
                            worker_lock = None
                except OSError:
                    pass
            valid = bool(
                job
                and worker_lock is not None
                and state["control"] == "paused"
                and not self.shared_fault
                and not self.storage_stopped
                and not self.store.stop_reason()
                and runtime.get("id") == self.run_id
                and runtime.get("pid") == os.getpid()
                and receipt.get("protocol") == CONTROLLER_HANDOFF_INSPECTION
                and receipt.get("status") == "pending"
                and receipt.get("request_id") == command.get("request_id")
                and receipt.get("binding") == handoff_binding(state, job)
                and identity is not None
                and identity == receipt.get("process_identity")
                and 0 <= time.time() - receipt.get("requested_at", 0) < 10
                and page is not None
                and not page.is_closed()
                and self.page_ids.get(page) == receipt["binding"]["page"]["page_id"]
                and page.context is self.context
                and self.context.browser.is_connected()
            )
            receipt.update(
                status="captured" if valid else "failed",
                captured_at=time.time(),
                execution_authority=False,
                worker_lock=worker_lock,
            )
            if not valid:
                receipt["reason"] = "handoff_binding_unverified"
                return
            if not hosted_ats.matches_page(
                page.url, job, document_url=self.document_urls.get(page)
            ):
                raise PortalDataError("handoff_page_changed", "原页已离开当前岗位。", 409)
            # Reuse the original isolated-world/owner capture without changing the job.
            observed_job = deepcopy(job)
            target = {
                "batch_id": state["batch_id"],
                "run_id": self.run_id,
                "page_id": self.page_ids[page],
            }
            observed_job["owned_page_inspection"] = {
                "request_id": receipt["request_id"],
                "status": "pending",
                "requested_at": receipt["requested_at"],
                "binding": target,
            }
            self.observe_owned_page(
                state,
                observed_job,
                page,
                {
                    "request_id": receipt["request_id"],
                    "binding": target,
                },
            )
            if not hosted_ats.matches_page(
                page.url, job, document_url=self.document_urls.get(page)
            ):
                raise PortalDataError("handoff_page_changed", "原页已离开当前岗位。", 409)
            receipt["page_snapshot"] = observed_job["owned_page_inspection"]
            receipt["captured_at"] = receipt["page_snapshot"]["at"]
            receipt["capture_scope"] = "url_document_dom_file_metadata_at_capture"
            return
        if command["action"] == "observe-page":
            self.observe_owned_page(state, job, page, command)
            return
        if command["action"] == "observe-result":
            receipt = (job or {}).get("submission_observation") or {}
            if (
                receipt.get("request_id") != command.get("request_id")
                or receipt.get("status") != "pending"
            ):
                return
            if (
                not job
                or state.get("current_job_id") != identifier
                or not page
                or page.is_closed()
                or page.context is not self.context
                or receipt.get("run_id") != self.run_id
                or receipt.get("page_id") != self.page_ids.get(page)
            ):
                raise PortalDataError(
                    "page_changed", "结果观察的原页已变化，不能推断提交成功。", 409
                )
            data = self.read_submission_page(page, job)
            events = [
                row
                for row in [*job["observations"], *self.transports]
                if row.get("kind") == "manual_submit"
                and row.get("application_id") == identifier
                and row.get("run_id") == self.run_id
                and row.get("page_id") == self.page_ids.get(page)
            ]
            latest_request = next(
                (row for row in reversed(events) if row.get("stage") == "request"), {}
            )
            response = next(
                (
                    row
                    for row in reversed(events)
                    if row.get("stage") == "response"
                    and (
                        not latest_request
                        or row.get("request_id") == latest_request.get("request_id")
                    )
                ),
                {},
            )
            target_verified = _manual_submission_target(
                job,
                (latest_request or response).get("target_binding") or {},
                document_url=self.document_urls.get(page),
            )
            expected, actual = urlsplit(job["job_url"]), urlsplit(data["url"])
            # The original Page/run and observed final request bind the target;
            # confirmation redirects may omit the job ID from their path.
            bound_url = actual.scheme == "https" and actual.hostname == expected.hostname
            messages = [
                re.sub(r"\s+", " ", text).strip().lower() for text in data.get("messages", [])
            ]
            positive = any(
                re.fullmatch(
                    r"(?:your application (?:has been|was) (?:successfully )?submitted|"
                    r"application (?:successfully )?submitted|we have received your application|"
                    r"thank you for applying)[.!]?",
                    text,
                )
                for text in messages
            )
            negative = any(
                re.fullmatch(
                    r"(?:application (?:could not be|was not|not) submitted|"
                    r"(?:we )?(?:could not|couldn't|cannot) submit your application|"
                    r"application submission failed)[.!]?",
                    text,
                )
                for text in messages
            )
            status = response.get("http_status", 0)
            conclusion = (
                "success"
                if target_verified
                and bound_url
                and job["handed_off"]
                and positive
                and not negative
                and 200 <= status < 400
                and not data.get("has_form")
                else "rejected"
                if target_verified and bound_url and job["handed_off"] and negative
                else "awaiting_submit"
                if not events and not positive and not negative and data.get("has_form")
                else "unknown"
            )
            receipt.update(
                status="observed",
                conclusion=conclusion,
                data=data,
                response=deepcopy(response),
                manual_request_id=latest_request.get("request_id"),
                target_verified=target_verified,
                at=time.time(),
            )
            if conclusion == "success":
                job["manual_submission"] = {
                    "source": "read_only_browser_result",
                    "request_id": receipt["request_id"],
                    "at": time.time(),
                }
                job["pending_status"] = "applied"
                self.store.sync(job, "原申请页和人工提交响应已确认成功，等待接收证据。")
            return
        if command["action"] == "continue-current":
            receipt = (job or {}).get("continuation") or {}
            if (
                receipt.get("request_id") != command.get("request_id")
                or receipt.get("status") != "pending"
            ):
                return
            if (
                not job
                or job.get("status") == "cancelled"
                or state.get("controller") != command.get("controller")
                or state.get("current_job_id") != identifier
                or state["control"] != "paused"
                or not page
                or page.is_closed()
                or page.context is not self.context
                or receipt.get("run_id") != self.run_id
                or receipt.get("page_id") != self.page_ids.get(page)
            ):
                raise PortalDataError("page_changed", "继续时原岗位或原页已变化。", 409)
            if manual_submission_unresolved(
                {**job, "observations": [*job["observations"], *self.transports]}
            ):
                receipt["status"] = "needs_recheck"
                job.update(status="needs_recheck", reason="submission_result_unknown")
                return
            self.check_inputs(job)
            from .application_bound_materials import verify_original_page

            already_current_material = verify_original_page(self, page, job)
            observed = self.observe_pending(page, job)
            form_flow.capture(
                self,
                page,
                job,
                state["batch_id"],
                observed,
                acknowledge=True,
                current_state=state,
            )
            receipt.update(observed=deepcopy(observed), at=time.time())
            if job["intent"]:
                form_flow.inspect_pending(self, page, job, observed)
            if job["intent"]:
                receipt["status"] = "needs_recheck"
                job.update(status="needs_recheck", reason="action_result_unknown")
                return
            if material_edit_pending(job):
                raise PortalDataError(
                    "material_edit_needs_recheck", "材料编辑尚未完成，请保留原稿核验。", 409
                )
            precision = job.get("precision_preparation") or {}
            if precision.get("status") == "ready":
                from .application_bound_materials import attachment_snapshot, document_token

                if (
                    precision.get("run_id") != self.run_id
                    or precision.get("page_id") != self.page_ids.get(page)
                    or precision.get("document_token") != document_token(page)
                ):
                    raise PortalDataError(
                        "page_changed", "精准调整的原文档已变化，请保留材料核验。", 409
                    )
                precision["resume_before_continue"] = attachment_snapshot(self, page, job, observed)
            job["manual_fields"] = {
                field["id"]: deepcopy(field)
                for field in observed["fields"]
                if field["type"] != "file"
                and field.get("valid")
                and field.get("value") not in (None, "", [])
            }
            job["manual_attachments"] = [
                deepcopy(field) for field in observed["fields"] if field["type"] == "file"
            ]
            if (job.get("material_update") or {}).get("status") == "bound":
                from .application_bound_materials import refreshed_contact_fields

                refreshed_contact_fields(self, job)
                if already_current_material:
                    job["material_update"]["status"] = "complete"
            self.handed_off_pages.discard(page)
            if precision.get("status") == "ready":
                precision.update(status="released", request_id=command["request_id"])
            job.update(handed_off=False, status="queued", reason="")
            receipt["status"] = "verified"
            state.update(
                control="running",
                controller=command["controller"],
                heartbeat_at=time.time(),
                resume_serial=state.get("resume_serial", 0) + 1,
            )
            return
        if job and command["action"] in {"review", "recheck"}:
            self.store.check_generic_enabled(job, state)
        if command["action"] == "one-use" and job and job["status"] != "cancelled":
            value = {
                "key": "one-use",
                "question": command["fact"],
                "value": command["value"],
                "scope": {"application_id": identifier},
                "state": "confirmed",
            }
            self.temporary.setdefault(identifier, {})[command["fact"]] = value
        elif (
            command["action"] == "review"
            and page
            and not page.is_closed()
            and job
            and job["status"] != "cancelled"
            and (job["status"] == "ready_for_review" or job.get("manual_intervention"))
        ):
            if not job.get("manual_intervention") and assistance_completion(job) is None:
                observed = self.observe(page, job)
                form_flow.capture(self, page, job, state["batch_id"], observed, current_state=state)
                form_flow.check_ready(job, observed)
            job["handed_off"] = True
            job["handoff"] = {
                "status": "pending",
                "run_id": self.run_id,
                "at": time.time(),
                "source": "automatic_submit_wait"
                if command.get("actor") == "system"
                else "user_requested_handoff",
                "actor": command.get("actor", "user"),
                "human_reviewed": False,
            }
            self.persist(state)
            if self.cua is not None:
                self.cua.review(page, pump=self.pump)
            page.unroute("**/*", self.guards[identifier])
            self._submit_lock(page, False)
            self.handed_off_pages.add(page)
            page.bring_to_front()
            job["handoff"]["status"] = "complete"
        elif command["action"] == "review" and job:
            if job["status"] != "cancelled":
                job.update(handed_off=True, status="needs_recheck", reason="handoff_unknown")
            job["handoff"] = {
                "status": "unknown",
                "run_id": self.run_id,
                "at": time.time(),
                "source": "automatic_submit_wait"
                if command.get("actor") == "system"
                else "user_requested_handoff",
                "actor": command.get("actor", "user"),
                "human_reviewed": False,
            }
        elif command["action"] == "release" and job:
            if page:
                page.close()
                self._forget_page(identifier, page)
            if job:
                job["page_open"] = False
                if job["status"] == "cancelled" and not job["intent"]:
                    release_execution(
                        self.store.applications,
                        identifier,
                        automated_owner(self.store.root, state["batch_id"], identifier),
                        "automated",
                    )
                if job["status"] == "ready_for_review" and not job.get("manual_submission"):
                    job.update(status="needs_recheck", reason="page_released")
        elif command["action"] == "recheck" and job and job["status"] != "cancelled":
            if command.get("authentication"):
                if not page or page.is_closed():
                    job.update(status="needs_recheck", reason="page_lost", page_open=False)
                    return
                observed_page = job.get("page_observation") or {}
                if (
                    page.context is not self.context
                    or observed_page.get("page_id") != self.page_ids.get(page)
                    or observed_page.get("run_id") != self.run_id
                ):
                    raise PortalDataError(
                        "page_changed", "登录等待的原页面已变更，请核验保留页面。", 409
                    )
                # Continue checks the actual retained page; it never reopens it or
                # promotes a login wait into permission to replay an unknown action.
                self.check_inputs(job)
                hosted_ats.observe(page, job, document_url=self.document_urls.get(page))
            self.handed_off_pages.discard(page)
            self.blocked_pages.pop(page, None)
            if page and not page.is_closed() and not self.live:
                page.unroute("**/*", self.guards[identifier])
                page.route("**/*", self.guards[identifier])
            if (
                self.live
                and job.get("form_state")
                and (
                    not page
                    or page.is_closed()
                    or page.context is not self.context
                    or not self.run_id
                    or not self.page_ids.get(page)
                    or job["form_state"].get("binding", {}).get("run_id") != self.run_id
                    or job["form_state"].get("binding", {}).get("page_id") != self.page_ids[page]
                )
            ):
                raise PortalDataError("page_changed", "原申请页不能核验，请保留当前记录。", 409)
            if page in self.drafts and job.get("action_resolutions"):
                self.drafts[page].refresh(page, self.effective_action_results(job))
            if self.live and job.get("form_state"):
                observed = self.observe_pending(page, job)
                form_flow.capture(
                    self,
                    page,
                    job,
                    state["batch_id"],
                    observed,
                    acknowledge=True,
                    current_state=state,
                )
            job["handed_off"] = False
        elif command["action"] == "answers-changed":
            for existing in state["jobs"]:
                if existing["status"] != "ready_for_review" or existing.get("manual_submission"):
                    continue
                for ref in existing["answer_refs"]:
                    if ref["key"] == "one-use" or ref.get("source") == "system_material":
                        continue
                    record = self.store.answers_for(existing).get_answer(ref["key"])
                    if record is None or digest(record) != ref["revision"]:
                        existing.update(status="needs_recheck", reason="answer_changed")
                        self.store.sync(existing, "答案已变更：请核验待复核页面后重新接管。")
                        break

    @staticmethod
    def read_submission_page(page, job):
        """Read stable status messages from the retained handle; never navigate or submit."""
        script = """() => ({url: location.href,
          messages: [...document.querySelectorAll(
            'h1,h2,[role=status],[role=alert],.application-confirmation,.application-success'
          )].filter(e => e.getClientRects().length)
            .map(e => e.innerText.trim()).filter(Boolean).slice(0,40),
          has_form: !!document.querySelector('form input, form textarea')})"""
        first = page.evaluate(script)
        if page.evaluate(script) != first:
            raise PortalDataError("submission_page_changed", "观察期间结果页已变化。", 409)
        return first

    def observe_owned_page(self, state: dict, job: dict | None, page, command: dict) -> None:
        receipt = (job or {}).get("owned_page_inspection") or {}
        if (
            receipt.get("request_id") != command.get("request_id")
            or receipt.get("status") != "pending"
        ):
            return  # A superseded request cannot overwrite its successor.
        binding = command["binding"]

        def check():
            client = getattr(self.cua, "client", None)
            if (
                not job
                or state["control"] != "paused"
                or self.store.stop_reason()
                or state.get("worker_error", "") not in {"", "control_connection_lost"}
                or self.shared_fault
                or self.storage_stopped
                or not page
                or page.is_closed()
                or page in self.page_faults
                or self.pages.get(job["application_id"]) is not page
                or page.context is not self.context
                or not self.context.browser
                or not self.context.browser.is_connected()
                or getattr(client, "failed", False)
                or client is not None
                and client.process.poll() is not None
                or binding
                != {
                    "batch_id": state["batch_id"],
                    "run_id": self.run_id,
                    "page_id": self.page_ids.get(page),
                }
                or binding != receipt.get("binding")
                or (job.get("page_observation") or {}).get("run_id") != self.run_id
                or (job.get("page_observation") or {}).get("page_id") != binding["page_id"]
                or (job.get("page_observation") or {}).get("event") != "observed"
                or not 0 <= time.time() - receipt.get("requested_at", 0) < 10
                or state.get("runtime", {}).get("id") != self.run_id
                or OWNED_PAGE_OBSERVATION not in state.get("runtime", {}).get("capabilities", [])
            ):
                raise PortalDataError(
                    "page_observation_owner_lost", "所属原页或控制连接已失效。", 409
                )

        captured = self._capture_owned_page(page, check)
        receipt.update(
            **captured,
            worker_source=state["runtime"]["source"]["sha256"],
        )

    def _capture_owned_page(
        self, page, check, *, expected_document=None, include_screenshot=True, owner=None
    ):
        """Read one retained handle; callers keep state checks outside Page IO."""
        if threading.get_ident() != self._page_thread:
            raise PortalDataError(
                "page_observation_thread_changed", "原页只能在所属执行线程读取。", 409
            )
        check()
        if owner is not None:
            # The caller's check already bound the owner (a post-stop reclaim re-bound it).
            pass
        elif self.cua is None:
            owner = {"status": "not_used", "transport": "retained-playwright"}
        elif getattr(self.cua.client, "handoff_active", False):
            # The yielded session belongs to the peer; check() still binds its driver.
            owner = {"status": "yielded", "transport": "retained-playwright"}
        else:
            owner = self.cua.observe_owner(pump=self.pump)
        check()
        url = page.url
        session = OwnedCDP(page).__enter__()
        try:
            frame = session.send("Page.getFrameTree")["frameTree"]["frame"]

            def read_document():
                if expected_document is not None:
                    _require_owned_document(session, expected_document)

            read_document()
            execution = session.send(
                "Page.createIsolatedWorld",
                {
                    "frameId": frame["id"],
                    "worldName": "tomorrowstar-owned-page-observation",
                },
            )["executionContextId"]

            def read_dom():
                result = session.send(
                    "Runtime.evaluate",
                    {
                        "expression": "("
                        + (INSPECT_OWNED_PAGE if include_screenshot else INSPECT_ASSISTANCE_CONTEXT)
                        + ")()",
                        "contextId": execution,
                        "returnByValue": True,
                        "silent": True,
                    },
                )
                if result.get("exceptionDetails") or not isinstance(
                    result.get("result", {}).get("value"), dict
                ):
                    raise PortalDataError("page_observation_failed", "原页只读内容不能核验。", 409)
                return result["result"]["value"]

            data = read_dom()
            screenshot = owned_screenshot(page, session.deadline) if include_screenshot else None
            if owner["status"] == "accepted":
                owner = self.cua.observe_owner(pump=self.pump)
            if read_dom() != data:
                raise PortalDataError("page_observation_changed", "观察期间原页字段已变更。", 409)
            read_document()
            check()
            after = session.send("Page.getFrameTree")["frameTree"]["frame"]
            if (
                page.url != url
                or data["url"] != url
                or any(after.get(key) != frame.get(key) for key in ("id", "loaderId", "url"))
            ):
                raise PortalDataError("page_observation_changed", "观察期间原页已变更。", 409)
            if (
                include_screenshot
                and expected_document is not None
                and (
                    not isinstance(screenshot, bytes)
                    or not screenshot.startswith(b"\x89PNG\r\n\x1a\n")
                )
            ):
                raise PortalDataError("page_observation_failed", "原页图像格式不能核验。", 409)
            if (
                include_screenshot
                and len(screenshot) > 2_000_000
                or len(json.dumps(data).encode()) > 2_000_000
            ):
                raise PortalDataError("page_observation_limit", "观察内容超过限额。", 409)
            check()
            return {
                "status": "captured",
                "at": time.time(),
                "data": data,
                **(
                    {
                        "screenshot": {
                            "mime_type": "image/png",
                            "base64": base64.b64encode(screenshot).decode("ascii"),
                        }
                    }
                    if include_screenshot
                    else {}
                ),
                "executor": "retained-page-isolated-world/v1",
                "owner": owner,
                "document": {
                    "frame_id": frame.get("id"),
                    "loader_id": frame.get("loaderId"),
                    "url": frame.get("url"),
                },
            }
        finally:
            with browser_deadline(1):
                session.detach()

    def _assistance_page_checker(self, assistance_ref, *, after_stop=False):
        """Bind short state checks to the original handle without collecting content.

        ``after_stop`` is the read-only post-stop path: the scope must be proven
        stopped, its writer still Codex, and the native session already reclaimed.
        """
        if threading.get_ident() != self._page_thread:
            raise PortalDataError(
                "page_observation_thread_changed", "原页只能在所属执行线程读取。", 409
            )
        if not isinstance(assistance_ref, dict) or not isinstance(
            assistance_ref.get("binding"), dict
        ):
            raise PortalDataError("assistance_binding_changed", "原页接管引用无效。", 409)
        identifier = assistance_ref["binding"].get("application_id")
        page = self.pages.get(identifier)

        def same_document():
            """Re-read an only-expired observation's original document on this thread."""
            if page is None or page.is_closed() or self.pages.get(identifier) is not page:
                return False
            binding = assistance_ref["binding"]
            state = self.store.load()
            job = next((row for row in state["jobs"] if row["application_id"] == identifier), None)
            observation = (job or {}).get("page_observation") or {}
            runs = (job or {}).get("native_handoff_runs") or [{}]
            current = PAGE_SCOPE.current(state, job)
            if (
                # Only a granted native handoff's own Worker work (a file admission and
                # its delivery, 2026-11-04) holds this thread past the window.
                runs[-1].get("phase") != "granted"
                or runs[-1].get("assistance_ref") != assistance_ref
                or not (current.valid or PAGE_SCOPE.only_expired(current))
                or (state.get("runtime") or {}).get("id") != self.run_id
                or observation.get("run_id") != self.run_id
                or binding.get("run_id") != self.run_id
                or observation.get("page_id") != binding.get("page_id")
                or self.page_ids.get(page) != binding.get("page_id")
                or not isinstance(binding.get("document_token"), str)
                or not binding["document_token"]
            ):
                return False
            if current.valid:
                # Still current when this thread looked: the check right after may
                # renew it although its own reload of a 9 MB checkpoint let the
                # window pass (2026-11-05: BCG's takeover was revoked at 6.4 s).
                return True
            receipt = (runs[-1].get("events") or [{}])[-1].get("receipt") or {}
            if self._native_work or receipt.get("active_calls", 0) >= 1:
                # This Worker's own admitted native call on this page and document is
                # in progress: its admission read verified the document, and a CDP
                # re-read now would wait on the renderer the call holds (2026-11-04:
                # a CV delivery with active_calls 1 was revoked at 6.2 s).
                return True
            try:
                with browser_deadline(2):
                    session = OwnedCDP(page).__enter__()
                    try:
                        _require_owned_document(session, binding["document_token"])
                    finally:
                        with browser_deadline(1):
                            session.detach()
                return True
            except (Error, PortalDataError) as error:
                # A busy, unreadable or changed document stays a lost scope.
                print(
                    "scope_renewal_unverified: "
                    + json.dumps(
                        {"error": type(error).__name__, "code": getattr(error, "code", None)}
                    ),
                    flush=True,
                )
                return False

        def check():
            # Only this page thread's own re-read of the same run, page and document
            # renews an observation that its own Worker work let expire; a changed
            # document, page or run still fails below as a changed binding.
            started = time.monotonic()
            renewable = same_document()
            renewed = time.monotonic()
            with self.store.applications.write_lock():
                locked = time.monotonic()
                state = self.store.load()
                loaded = time.monotonic()
                if loaded - started > 1:
                    # Private timing of a slow scope check (2026-11-05).
                    print(
                        "scope_check_slow: "
                        + json.dumps(
                            {
                                "same_document_s": round(renewed - started, 2),
                                "lock_wait_s": round(locked - renewed, 2),
                                "load_s": round(loaded - locked, 2),
                            }
                        ),
                        flush=True,
                    )
                job = next(
                    (row for row in state["jobs"] if row["application_id"] == identifier), None
                )
                assistance = (job or {}).get("assistance")
                runtime = state.get("runtime") or {}
                now = time.time()
                current = PAGE_SCOPE.current(state, job, now)
                if (
                    job
                    and page is not None
                    and not page.is_closed()
                    and PAGE_SCOPE.refresh_due(state, job, now)
                    and (current.valid or renewable and PAGE_SCOPE.only_expired(current))
                    and PAGE_SCOPE.refresh(state, job, now, run_id=self.run_id)
                ):
                    # This page thread holds the original handle: each check before and
                    # after a read renews a still-current observation, so a slow read
                    # (page age P95 7.2 s, 2026-11-02) is not mistaken for a lost scope.
                    # An observation that already expired is never renewed here.
                    # The local checkpoint write is not browser time: SIGALRM fired
                    # inside json.dump of this save (2026-11-03).
                    with pause_browser_deadline():
                        self.persist(state)
                scope = PAGE_SCOPE.current(state, job, now)
                if (
                    not job
                    or not assistance
                    or assistance.get("status") != ("stopped" if after_stop else "claimed")
                    or after_stop
                    and (
                        (assistance.get("stop") or {}).get("stop_status") != "stopped"
                        or assistance_stop_pending(job)
                        or material_edit_pending(job)
                    )
                    or assistance.get("active_writer") != "codex"
                    or not assistance_backend_permitted(state, assistance)
                    or digest(assistance_reference(assistance)) != digest(assistance_ref)
                    or digest(assistance_binding(state, job)) != digest(assistance_ref["binding"])
                    and not (
                        after_stop
                        and assistance_binding_resumed_only(
                            assistance_binding(state, job), assistance_ref["binding"]
                        )
                    )
                    or state["control"] != "running"
                    or state.get("current_job_id") != identifier
                    or job["status"] == "cancelled"
                    or job.get("handed_off")
                    or job.get("manual_submission")
                    or runtime.get("id") != self.run_id
                    or (runtime.get("source") or {}).get("sha256") != self._page_source
                    or not self._page_source
                    or not scope.valid
                    or state.get("worker_error")
                ):
                    # The private log keeps which part of the page scope changed,
                    # and what last checked it before the window passed (2026-11-05).
                    last = self._last_scope_check
                    print(
                        "assistance_binding_changed: "
                        + json.dumps(
                            {
                                "since_last_check": last and round(time.monotonic() - last[0], 1),
                                "last_check_by": last and last[1],
                                "check_by": _callers(),
                                "status": (assistance or {}).get("status"),
                                "writer": (assistance or {}).get("active_writer"),
                                "backend": bool(
                                    assistance and assistance_backend_permitted(state, assistance)
                                ),
                                "reference": bool(assistance)
                                and digest(assistance_reference(assistance))
                                == digest(assistance_ref),
                                "binding": bool(job)
                                and digest(assistance_binding(state, job))
                                == digest(assistance_ref["binding"]),
                                "control": state["control"],
                                "current": state.get("current_job_id") == identifier,
                                "run": runtime.get("id") == self.run_id,
                                "source": (runtime.get("source") or {}).get("sha256")
                                == self._page_source,
                                "scope_changed": scope.changed,
                                "runtime_age": scope.runtime_age and round(scope.runtime_age, 1),
                                "page_age": scope.page_age and round(scope.page_age, 1),
                                "worker_error": state.get("worker_error"),
                            }
                        ),
                        flush=True,
                    )
                    raise PortalDataError(
                        "assistance_binding_changed", "原页、材料或接管范围已改变。", 409
                    )
                self._last_scope_check = (time.monotonic(), _callers())
                require_execution(
                    self.store.applications,
                    identifier,
                    automated_owner(self.store.root, state["batch_id"], identifier),
                    "automated",
                )
            client = getattr(self.cua, "client", None)
            binding = assistance_ref["binding"]
            # Ordered as before: a later condition may assume an earlier one held.
            conditions = (
                ("store_stopped", lambda: self.store.stop_reason()),
                ("shared_fault", lambda: self.shared_fault),
                ("storage_stopped", lambda: self.storage_stopped),
                ("page_missing", lambda: page is None or page.is_closed()),
                ("page_replaced", lambda: self.pages.get(identifier) is not page),
                ("context_changed", lambda: page.context is not self.context),
                (
                    "browser_disconnected",
                    lambda: (
                        self.context is None
                        or not self.context.browser
                        or not self.context.browser.is_connected()
                    ),
                ),
                ("page_id_changed", lambda: self.page_ids.get(page) != binding.get("page_id")),
                ("page_url_changed", lambda: page.url != binding.get("step")),
                ("page_fault", lambda: page in self.page_faults),
                ("page_blocked", lambda: page in self.blocked_pages),
                ("page_handed_off", lambda: page in self.handed_off_pages),
                (
                    "driver_failed",
                    lambda: (
                        getattr(client, "failed", False)
                        or client is not None
                        and client.process.poll() is not None
                    ),
                ),
                (
                    "native_handoff_active",
                    lambda: after_stop and getattr(client, "handoff_active", False),
                ),
            )
            lost = next((name for name, failed in conditions if failed()), None)
            if lost:
                # The private log names the condition only, never page content.
                detail = {"condition": lost}
                if lost == "page_blocked":
                    detail["reason"] = self.blocked_pages.get(page)
                print("page_observation_owner_lost: " + json.dumps(detail), flush=True)
                raise PortalDataError(
                    "page_observation_owner_lost", "所属原页或控制连接已失效。", 409
                )

        return page, check

    def _reclaim_native_session(self):
        """Take the yielded native session back once; an owned session is a no-op."""
        client = getattr(self.cua, "client", None)
        if client is None or not getattr(client, "handoff_active", False):
            return False
        client.resume_after_handoff(pump=self.pump)
        return True

    def assistance_read_permitted(self, assistance_ref, *, document=None, after_stop=False):
        """Cheap current-scope check for the read-only protocol event pump.

        ``self._permit_failure`` keeps why the last check failed: "document_changed",
        a slow read's message, or the refusing code (2026-11-05: a takeover start
        failed as assistance_binding_changed with nothing naming why).
        """
        self._permit_failure = None
        try:
            page, check = self._assistance_page_checker(assistance_ref, after_stop=after_stop)
            check()
            if document is not None:
                with browser_deadline(2):
                    session = OwnedCDP(page).__enter__()
                    try:
                        frame = session.send("Page.getFrameTree")["frameTree"]["frame"]
                        if document != {
                            "frame_id": frame.get("id"),
                            "loader_id": frame.get("loaderId"),
                            "url": frame.get("url"),
                        }:
                            self._permit_failure = "document_changed"
                            return False
                        check()
                    finally:
                        with browser_deadline(1):
                            session.detach()
                check()
            return True
        except (
            Error,
            OSError,
            StoreError,
            PortalDataError,
            ValueError,
            KeyError,
            TypeError,
        ) as error:
            self._permit_failure = getattr(error, "code", None) or getattr(
                error, "message", type(error).__name__
            )
            return False

    def observe_assistance_page(self, assistance_ref):
        """Observe a claimed original page without adopting state or granting writes."""
        page, check = self._assistance_page_checker(assistance_ref)
        with browser_deadline(5):
            captured = self._capture_owned_page(
                page, check, expected_document=assistance_ref["binding"].get("document_token")
            )
        captured.update(
            binding=deepcopy(assistance_ref["binding"]),
            worker_source=self._page_source,
            image_url="data:image/png;base64," + captured["screenshot"]["base64"],
            page_writes_enabled=False,
        )
        check()
        return captured

    def _renew_assistance_context(self, assistance_ref, context) -> bool:
        """Let a captured context follow the page observation the last check renewed."""
        identifier = assistance_ref["binding"]["application_id"]
        state = self.store.load()
        job = next((row for row in state["jobs"] if row["application_id"] == identifier), None)
        return PAGE_SCOPE.renew_snapshot(context, state, job, run_id=self.run_id)

    def _renew_own_observation(self, reference):
        """Advance the page observation after this thread's own verified native work."""
        identifier = reference["binding"]["application_id"]
        page = self.pages.get(identifier)
        if page is None or page.is_closed():
            return
        with self.store.applications.write_lock():
            state = self.store.load()
            job = next((row for row in state["jobs"] if row["application_id"] == identifier), None)
            if (
                job
                and (job.get("page_observation") or {}).get("page_id") == self.page_ids.get(page)
                and PAGE_SCOPE.refresh(state, job, time.time(), run_id=self.run_id)
            ):
                with pause_browser_deadline():
                    self.persist(state)

    def _observe_settling_context(self, reference, *, after_stop=False):
        """Read the JSON context of a page that may still be settling or answer slowly.

        A hidden page answers slowly as a takeover starts (2026-11-01) and after it
        stops (2026-11-02: the return's one read timed out and the whole return was
        refused); this read-only observation is repeated before it fails.
        """
        for attempt in range(3):
            try:
                return self.observe_assistance_context(reference, after_stop=after_stop)
            except (PortalDataError, Error) as error:
                # A timed-out read's detach can itself time out and replace the read
                # timeout with the outer one (2026-11-03); both are the same slow read.
                if attempt == 2 or (
                    getattr(error, "code", None) != "page_observation_changed"
                    and getattr(error, "message", None) not in SLOW_READS
                ):
                    raise
                # A slow read can outlast the observation window; the check after it
                # refreshes the window first (seen 2026-11-02: 7.4 s).
                # A post-stop scope is checked as stopped, never as a live claim
                # (2026-11-03: every post-stop retry was refused as a changed binding).
                if not self.pump_codex_events(reference, after_stop=after_stop):
                    raise PortalDataError(
                        "assistance_binding_changed", "原页、材料或接管范围已改变。", 409
                    ) from error
        raise AssertionError("unreachable")

    def observe_assistance_context(self, assistance_ref, *, after_stop=False):
        """Read JSON locator context from the original Page without taking a screenshot."""
        page, check = self._assistance_page_checker(assistance_ref, after_stop=after_stop)
        with browser_deadline(5):
            captured = self._capture_owned_page(
                page,
                check,
                expected_document=assistance_ref["binding"].get("document_token"),
                include_screenshot=False,
                # The reclaim just re-bound the owner; two more driver state reads
                # (seconds each, 2026-11-03) would spend this read's 5 s budget.
                owner={"status": "reclaimed", "transport": "retained-playwright"}
                if after_stop
                else None,
            )
        fields = captured["data"]["fields"]
        for field in fields:
            field["locator_hint"] = {
                key: field.get(key, "") for key in ("id", "name", "role", "label")
            }
        captured["data"]["validation_errors"] = [
            {
                "field_hint": deepcopy(field["locator_hint"]),
                "valid": field.get("valid"),
                "aria_invalid": field.get("aria_invalid"),
            }
            for field in fields
            if field.get("valid") is False or field.get("aria_invalid") not in (None, "", "false")
        ]
        captured.update(
            binding=deepcopy(assistance_ref["binding"]),
            worker_source=self._page_source,
            observed_at=captured["at"],
            page_writes_enabled=False,
        )
        if len(json.dumps(captured, allow_nan=False).encode()) > 2_000_000:
            raise PortalDataError("page_observation_limit", "观察内容超过限额。", 409)
        check()
        return captured

    def _read_native_material_field(self, reference, worker_field, *, document, after_stop=False):
        """Read one original field's actual bytes, never dispatch or replay its action."""
        if not isinstance(worker_field, str) or not worker_field or len(worker_field) > 200:
            raise PortalDataError("material_readback_unknown", "原材料字段不能核验。", 409)
        page, check = self._assistance_page_checker(reference, after_stop=after_stop)
        expression = (
            "(async () => { const marker="
            + json.dumps(worker_field)
            + "; const inspect=("
            + INSPECT_ASSISTANCE_CONTEXT
            + ");"
            + r"""
            const fields=inspect().fields.filter(f=>f.material_target?.worker_field===marker);
            const nodes=[...document.querySelectorAll('[data-ts-worker-field]')]
              .filter(e=>e.getAttribute('data-ts-worker-field')===marker);
            if(fields.length!==1||nodes.length!==1) throw Error('material_target_changed');
            const field=fields[0],e=nodes[0];
            let result={field,sha256:null,size_bytes:0,filename:null,value:null};
            let originalFile=null;
            if(e.type==='file') {
              if(e.files.length>1) throw Error('material_file_count');
              if(e.files.length===1) {
                const file=e.files[0];
                originalFile=file;
                if(file.size<1||file.size>700000) throw Error('material_file_size');
                const raw=await Blob.prototype.arrayBuffer.call(file);
                if(raw.byteLength!==file.size||e.files.length!==1||e.files[0]!==file)
                  throw Error('material_file_changed');
                result.sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),
                  b=>b.toString(16).padStart(2,'0')).join('');
                result.size_bytes=raw.byteLength; result.filename=file.name;
              }
            } else {
              if(!['text','textarea'].includes(e.type)) throw Error('material_control_type');
              result.value=e.value;
              result.size_bytes=new TextEncoder().encode(result.value).length;
              if(result.size_bytes>20000) throw Error('material_text_size');
            }
            const again=inspect().fields.filter(f=>f.material_target?.worker_field===marker);
            if(again.length!==1||JSON.stringify(again[0])!==JSON.stringify(field)||
                !e.isConnected||e.getAttribute('data-ts-worker-field')!==marker||
                e.type==='file'&&(e.files.length!==(originalFile?1:0)||
                  originalFile&&e.files[0]!==originalFile))
              throw Error('material_field_changed');
            return result;
            })()"""
        )
        with browser_deadline(3), OwnedCDP(page) as session:
            check()
            frame = session.send("Page.getFrameTree")["frameTree"]["frame"]
            if document != {
                "frame_id": frame.get("id"),
                "loader_id": frame.get("loaderId"),
                "url": frame.get("url"),
            }:
                raise PortalDataError("material_readback_unknown", "原材料文档已变化。", 409)
            execution = session.send(
                "Page.createIsolatedWorld",
                {
                    "frameId": frame["id"],
                    "worldName": "tomorrowstar-material-readback",
                },
            )["executionContextId"]
            raw = session.send(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "contextId": execution,
                    "returnByValue": True,
                    "awaitPromise": True,
                    "silent": True,
                },
            )
            result = raw.get("result", {}).get("value")
            after = session.send("Page.getFrameTree")["frameTree"]["frame"]
            check()
            if (
                raw.get("exceptionDetails")
                or not isinstance(result, dict)
                or set(result) != {"field", "sha256", "size_bytes", "filename", "value"}
                or any(after.get(key) != frame.get(key) for key in ("id", "loaderId", "url"))
                or not isinstance(result.get("field"), dict)
            ):
                raise PortalDataError(
                    "material_readback_unknown", "当前材料的实际回读不能核验。", 409
                )
            if result["value"] is not None:
                result["sha256"] = hashlib.sha256(result["value"].encode()).hexdigest()
            return result

    def _native_filename_shown(self, page, filename, *, document, target=None):
        """Whether the resume's name is shown in its form item, or else in its form.

        An upload widget may clear its input and show the name elsewhere (2026-11-03,
        onlyfy), or re-render and unmount the input itself. So the fixed read starts
        from the delivery's stable identity in the ledger: the element with the
        descriptor's ``id`` (a ``...-form-item`` wrapper there) or its
        ``[data-field-path]`` group; then the form holding it, or with no such element
        the form holding a file input or combobox. It reads the exact document and
        returns only whether the name is shown, at which scope, and whether that scope
        shows an error (2026-11-03: the name stood above "That didn't work. Please try
        again."). Failure is unshown.
        """
        unshown = {"shown": False, "scope": "", "error": False}
        if page is None or not isinstance(filename, str) or not filename.strip():
            return unshown
        target = target or {}
        wanted = {
            "filename": filename,
            "id": str(target.get("id") or "")[:200],
            "draft_path": str(target.get("draft_path") or "")[:1000],
        }
        expression = (
            "(() => { const wanted="
            + json.dumps(wanted)
            + ";"
            + r"""
            const norm=t=>String(t||'').replace(/\s+/g,' ').trim().toLowerCase();
            const want=norm(wanted.filename);
            // An error message the widget shows in that scope; empty regions do not count.
            const error=scope=>[...scope.querySelectorAll(
              '[role=alert],[aria-invalid=true],[aria-errormessage],[aria-live]')]
              .some(e=>norm(e.textContent));
            if(!want) return {shown:false,scope:'',error:false};
            let item=wanted.id?document.getElementById(wanted.id):null;
            if(!item&&wanted.draft_path) item=[...document.querySelectorAll('[data-field-path]')]
              .find(e=>e.getAttribute('data-field-path')===wanted.draft_path)||null;
            if(item&&norm(item.textContent).includes(want))
              return {shown:true,scope:'container',error:error(item)};
            const form=item?item.closest('form'):[...document.querySelectorAll('form')]
              .find(f=>f.querySelector('input[type=file],[role=combobox]'));
            if(form&&norm(form.textContent).includes(want))
              return {shown:true,scope:'form',error:error(form)};
            return {shown:false,scope:'',error:Boolean(item&&error(item))};
            })()"""
        )
        try:
            with browser_deadline(3), OwnedCDP(page) as session:
                frame = session.send("Page.getFrameTree")["frameTree"]["frame"]
                if document != {
                    "frame_id": frame.get("id"),
                    "loader_id": frame.get("loaderId"),
                    "url": frame.get("url"),
                }:
                    return unshown
                execution = session.send(
                    "Page.createIsolatedWorld",
                    {"frameId": frame["id"], "worldName": "tomorrowstar-filename-shown"},
                )["executionContextId"]
                raw = session.send(
                    "Runtime.evaluate",
                    {
                        "expression": expression,
                        "contextId": execution,
                        "returnByValue": True,
                        "silent": True,
                    },
                )
        except (PortalDataError, Error, TimeoutError, OSError, KeyError, TypeError):
            return unshown
        result = raw.get("result", {}).get("value")
        if (
            raw.get("exceptionDetails")
            or not isinstance(result, dict)
            or set(result) != {"shown", "scope", "error"}
            or type(result["shown"]) is not bool
            or type(result["error"]) is not bool
            or result["scope"] not in (("container", "form") if result["shown"] else ("",))
        ):
            result = unshown
        print("native_filename_shown: " + json.dumps(result), flush=True)
        return result

    def _resolve_native_material_call(self, reference, call, context):
        """Match the native control to one prepared field without altering the Page."""
        from .cua_driver import validate_native_material_metadata

        try:
            validate_native_material_metadata(call)
        except ValueError as error:
            raise _material_refusal(
                "material_destination_unverified", "原生材料控件不能核验。", "metadata"
            ) from error
        target = call["target_descriptor"]
        snapshot = next(
            (
                (row.get("form_state") or {}).get("snapshot") or {}
                for row in self.store.load()["jobs"]
                if row["application_id"] == reference["binding"]["application_id"]
            ),
            None,
        )
        if snapshot is not None and not snapshot.get("fields"):
            # One delivery projection per admission: each waits on the shared write
            # lock (2026-11-05: Harmattan's CV admission waited on it twice).
            entries = [
                row
                for row in self.store.assistance_delivery(reference, page_context=context)[
                    "materials"
                ]
                if row.get("material_ref") == call["material_ref"]
            ]
            if len(entries) == 1 and entries[0].get("kind") == "cover_letter":
                return self._resolve_unparsed_cover_letter_call(
                    reference, call, context, entries[0]
                )
            return self._resolve_unparsed_resume_call(reference, call, context, entries)
        fields = [
            field
            for field in context.get("data", {}).get("fields", [])
            if field.get("material_target", {}).get("worker_field") == target["worker_field"]
        ]
        if (
            not target["worker_field"]
            or call["scope"]["expected_document"] != context.get("document")
            or len(fields) != 1
            or fields[0].get("material_target") != target
            or not target["value_empty"]
            or target["file_count"] != 0
            or target["type"] != "file"
            and fields[0].get("value", "") != ""
        ):
            raise _material_refusal(
                "material_destination_unverified",
                "当前原页材料字段已变化或尚未准备。",
                "document"
                if call["scope"]["expected_document"] != context.get("document")
                else "fields!=1"
                if len(fields) != 1
                else "target",
            )
        with self.store.applications.write_lock():
            state = self.store.load()
            job = next(
                (
                    row
                    for row in state["jobs"]
                    if row["application_id"] == reference["binding"]["application_id"]
                ),
                None,
            )
            questions = [
                question
                for question in ((job or {}).get("form_state", {}).get("snapshot") or {}).get(
                    "fields", []
                )
                if question.get("control_ids") == [target["worker_field"]]
                and question.get("draft_path", "") == target["draft_path"]
            ]
            if len(questions) != 1:
                raise _material_refusal(
                    "material_destination_unverified", "固定材料没有唯一的当前字段。", "question!=1"
                )
            question = deepcopy(questions[0])

            # Preparation owns field meaning. A retained marker cannot authorize a
            # newly relabelled salary, legal declaration or other application field.
            def normalize(value):
                return " ".join(re.sub(r"[✱*]", "", value).split()).casefold()

            if normalize(target["label"]) != normalize(question["question"]):
                raise _material_refusal(
                    "material_field_changed", "材料字段含义已改变，请保留当前原页。", "label"
                )
            return self.store.resolve_bound_material(
                reference, call["material_ref"], question=question, page_context=context
            )

    def _resolve_unparsed_resume_call(self, reference, call, context, entries):
        """The job's resume into the one resume file input of a page with no script questions.

        Preparation owns field meaning; here no prepared question exists, so the
        Worker itself proves the destination: the exact current document, one empty
        single-file input matching the descriptor, labelled as a CV/resume and not as a
        cover letter or other document, and no other file input on the page labelled
        as a CV/resume too. Other attachments may sit beside it (2026-11-03: a CV and
        an "Other documents" input). Any other field is refused.
        """
        from .application_materials import material_kind

        target = call["target_descriptor"]
        fields = [
            field
            for field in context.get("data", {}).get("fields", [])
            if field.get("material_target") == target
        ]

        def words(values):
            return [
                " ".join(re.sub(r"[✱*_\-\[\]]", " ", str(text or "")).split()).casefold()
                for text in values
            ]

        def resume_input(values):
            return any(NATIVE_RESUME_LABEL.search(text) for text in values) and not any(
                material_kind({"type": "file", "question": text}) != "unknown" for text in values
            )

        def autofill_input(values):
            # Ashby's "Autofill from resume" parses a CV to prefill fields; it is not
            # the application's resume field (2026-11-05: Harmattan AI's CV refused).
            return any("autofill" in text for text in values)

        others = [
            words(
                [
                    *(field["material_target"].get(key) for key in ("label", "name", "id")),
                    *(field.get(key) for key in ("label", "question")),
                ]
            )
            for field in context.get("data", {}).get("fields", [])
            if (field.get("material_target") or {}).get("type") == "file"
            and field.get("material_target") != target
        ]
        texts = [target["label"], target["name"], target["id"], call["field_hint"]["name"]]
        if len(fields) == 1:
            texts += [str(fields[0].get(key) or "") for key in ("label", "question")]
        texts = words(texts)
        unproven = next(
            (
                name
                for name, failed in (
                    ("document", call["scope"]["expected_document"] != context.get("document")),
                    ("fields!=1", len(fields) != 1),
                    (
                        "resume_inputs!=1",
                        any(resume_input(other) and not autofill_input(other) for other in others),
                    ),
                    (
                        "target",
                        target["type"] != "file"
                        or target["tag"] != "input"
                        or not target["value_empty"]
                        or target["file_count"] != 0
                        or any(target[key] for key in ("disabled", "readonly", "multiple")),
                    ),
                )
                if failed
            ),
            None,
        )
        if unproven:
            raise _material_refusal(
                "material_destination_unverified", "当前原页没有唯一的空简历附件字段。", unproven
            )
        if not resume_input(texts):
            raise _material_refusal("material_field_changed", "此字段不是简历附件入口。", "label")
        if len(entries) != 1 or entries[0].get("kind") != "resume":
            raise _material_refusal(
                "material_reference_invalid", "固定材料引用不是本岗位简历。", "delivery_entry"
            )
        with self.store.applications.write_lock():
            state = self.store.load()
            job = next(
                row
                for row in state["jobs"]
                if row["application_id"] == reference["binding"]["application_id"]
            )
            self.store.check_single(job, state, material_required=True)
            raw = self.store._read_bound_resume(job, state["batch_id"])
        accept = {
            value.strip().casefold() for value in target["accept"].split(",") if value.strip()
        }
        if accept and not accept & {".pdf", "application/pdf", "*", "*/*"}:
            raise _material_refusal(
                "material_format_unsupported", "当前字段不接受简历 PDF。", "accept"
            )
        if hashlib.sha256(raw).hexdigest() != job["file_sha256"] or not 1 <= len(raw) <= 700000:
            raise _material_refusal("material_changed", "简历文件不能核验。", "resume_file")
        return {
            "kind": "file",
            "bytes": raw,
            "sha256": job["file_sha256"],
            "filename": job["filename"],
            "material_id": "resume",
            "material_ref": call["material_ref"],
            "question": None,
            "material": deepcopy(entries[0]),
        }

    def _resolve_unparsed_cover_letter_call(self, reference, call, context, entry):
        """The prepared letter into the one cover-letter control of a zero-question page.

        As for the resume, the Worker proves the destination itself: the exact current
        document, one empty control matching the descriptor, labelled as a cover letter,
        no second cover-letter control of the same kind, and the field the letter
        policy selected and prepared for this page.
        """
        from .application_materials import check_cover_letter_text

        target = call["target_descriptor"]
        fields = [
            field
            for field in context.get("data", {}).get("fields", [])
            if field.get("material_target") == target
        ]
        pairs = native_cover_letter_controls(context)
        owned = [question for question, field in pairs if len(fields) == 1 and field is fields[0]]
        unproven = next(
            (
                name
                for name, failed in (
                    ("document", call["scope"]["expected_document"] != context.get("document")),
                    ("fields!=1", len(fields) != 1),
                    (
                        "target",
                        any(target[key] for key in ("disabled", "readonly", "multiple"))
                        or target["type"] == "file"
                        and (
                            target["tag"] != "input"
                            or not target["value_empty"]
                            or target["file_count"] != 0
                        )
                        or target["type"] != "file"
                        and (target["tag"] != "textarea" or not target["value_empty"]),
                    ),
                )
                if failed
            ),
            None,
        )
        if unproven:
            raise _material_refusal(
                "material_destination_unverified", "当前原页没有唯一的空求职信字段。", unproven
            )
        if len(owned) != 1:
            raise _material_refusal("material_field_changed", "此字段不是求职信入口。", "label")
        question = owned[0]
        if sum(other["type"] == question["type"] for other, _ in pairs) != 1 or not entry.get(
            "material_id"
        ):
            raise _material_refusal(
                "material_destination_unverified", "当前原页有多个求职信入口。", "letter_inputs!=1"
            )
        state = self.store.load()
        job = next(
            row
            for row in state["jobs"]
            if row["application_id"] == reference["binding"]["application_id"]
        )
        if [question["id"], question["draft_path"]] not in (
            job.get("cover_letter_delivery") or {}
        ).get("selected_fields", []):
            raise _material_refusal(
                "material_destination_unverified", "当前字段不是已准备的求职信入口。", "selected"
            )
        material = self.store.field_material(question, job)
        if (
            material is None
            or material.get("id") != entry["material_id"]
            or digest(material) != entry["revision"]
        ):
            raise _material_refusal("material_not_ready", "当前求职信材料尚不能发送。", "material")
        result = {
            "material_id": material["id"],
            "material_ref": call["material_ref"],
            "question": None,
            "material": deepcopy(entry),
        }
        if question["type"] == "file":
            if not material.get("file_path"):
                raise _material_refusal("material_not_ready", "求职信没有已完成附件。", "file")
            raw = self.store._read_bound_material_file(
                Path(material["file_path"]), material["sha256"]
            )
            return {
                **result,
                "kind": "file",
                "bytes": raw,
                "sha256": material["sha256"],
                "filename": material["filename"],
            }
        check_cover_letter_text(question, material["text"])
        return {
            **result,
            "kind": "text",
            "text": material["text"],
            "sha256": material["text_sha256"],
        }

    def _prepare_native_cover_letter(self, job, batch_id, page):
        """Prepare the adopted letter for a zero-question page's own letter control.

        The script could not parse this page, so its letter delivery was never derived
        and the native takeover had no letter to deliver (2026-11-03). The same policy
        runs on questions read from the page with the takeover's own context read,
        before the takeover's reference binds the job's materials. The caller owns the
        job's status; a letter that cannot be prepared is logged, never fatal.
        """
        from .application_materials import SupplementalMaterials

        if job.get("workflow") != "single" or page is None:
            return
        try:
            with browser_deadline(5):
                data = page.evaluate(INSPECT_ASSISTANCE_CONTEXT)
        except (Error, TimeoutError):
            return
        questions = [q for q, _ in native_cover_letter_controls({"data": data})]
        if not questions:
            return

        def update(job, batch_id, **changes):
            changes.pop("status", None)
            changes.pop("reason", None)
            if changes:
                self.update(job, batch_id, **changes)

        materials = SupplementalMaterials(
            self.store,
            allowed=lambda state, identifier: self.permitted(state, self.pages.get(identifier)),
            update=update,
            persist=self.persist,
            model_context=pause_browser_deadline,
        )
        try:
            materials.prepare_cover_letter(
                job,
                batch_id,
                {"fields": questions},
                temporary=self.temporary,
                page_binding={"run_id": self.run_id, "page_id": self.page_ids.get(page)},
            )
        except (PortalDataError, Error, OSError, ValueError, StoreError) as error:
            code = getattr(error, "code", None) or type(error).__name__
            print("native_cover_letter_unprepared: " + json.dumps({"code": code}), flush=True)

    def _prepare_native_material_call(
        self, reference, call, context, *, request_id, scope, receipt
    ):
        """Seal this field's fixed material only after saving its original send intent."""
        from .cua_driver import validate_fixed_material_resolution

        resolved = self._resolve_native_material_call(reference, call, context)
        question = resolved["question"]
        kind = resolved["kind"]
        raw = resolved["text"].encode() if kind == "text" else resolved["bytes"]
        attempt_id = uuid4().hex
        payload = {
            "protocol": "fixed-material/v1",
            "resolution_id": attempt_id,
            "material_ref": resolved["material_ref"],
            "kind": kind,
            "sha256": resolved["sha256"],
            "size_bytes": len(raw),
        }
        if kind == "text":
            payload["text"] = resolved["text"]
        else:
            payload.update(
                bytes_base64=base64.b64encode(raw).decode("ascii"),
                filename=resolved["filename"],
                mime_type="application/pdf",
            )
        payload = validate_fixed_material_resolution(payload, material_ref=call["material_ref"])
        manifest = {
            key: value for key, value in payload.items() if key not in {"text", "bytes_base64"}
        }
        if question is None:
            # No prepared question carries a field intent; the persisted ledger row is
            # the attempt record and its observed FileList readback the result.
            with self.store.applications.write_lock():
                state = self.store.load()
                job = next(
                    row
                    for row in state["jobs"]
                    if row["application_id"] == reference["binding"]["application_id"]
                )
                # The same material already observed on this document is not resent;
                # another material (a letter after the CV) is its own attempt.
                document = call["scope"]["expected_document"]
                delivered = (
                    native_resume_delivered(job, document)
                    if resolved["material_id"] == "resume"
                    else any(
                        row.get("tool") == "browser_deliver_material"
                        and row.get("status") == "observed"
                        and (row.get("material_resolution") or {}).get("sha256")
                        == resolved["sha256"]
                        for run in job.get("native_handoff_runs", [])
                        if (run.get("scope") or {}).get("document") == document
                        for event in run.get("events", [])
                        for row in (event.get("receipt") or {}).get("calls", [])
                    )
                )
                if job.get("intent") is not None or delivered:
                    raise PortalDataError(
                        "material_attempt_unresolved", "材料已发送或原尝试尚未核验。", 409
                    )
                self.store.record_native_handoff(
                    reference, request_id=request_id, phase="granted", scope=scope, receipt=receipt
                )
            return payload
        with self.store.applications.write_lock():
            state = self.store.load()
            job = next(
                row
                for row in state["jobs"]
                if row["application_id"] == reference["binding"]["application_id"]
            )
            if job.get("intent") is not None:
                raise PortalDataError(
                    "material_attempt_unresolved", "原发送结果尚未核验，保留原尝试。", 409
                )
            if any(
                previous.get("form_binding") == job["form_state"]["binding"]
                and previous.get("run_id") == reference["binding"]["run_id"]
                and previous.get("page_id") == reference["binding"]["page_id"]
                and previous.get("action") == ("fill" if kind == "text" else "upload")
                and previous.get("field_id") == question["id"]
                and previous.get("draft_path", "") == question.get("draft_path", "")
                and (previous.get("material_id") or "resume") == resolved["material_id"]
                and previous.get("sha256") == resolved["sha256"]
                for previous in self.verified_intents(job)
            ):
                raise PortalDataError(
                    "recovered_result_not_visible",
                    "已核验材料被清空，保留原结果且不重复发送。",
                    409,
                )
            intent = {
                "action": "fill" if kind == "text" else "upload",
                "field_id": question["id"],
                "draft_path": question.get("draft_path", ""),
                "material_id": resolved["material_id"],
                "sha256": resolved["sha256"],
                "form_protocol": "form-state/v1",
                "form_binding": deepcopy(job["form_state"]["binding"]),
                "attempt_id": attempt_id,
                "run_id": reference["binding"]["run_id"],
                "page_id": reference["binding"]["page_id"],
                "prepared_at": time.time(),
                "input_refs": {"revision": job["revision"], "file_sha256": job["file_sha256"]},
                "native_material": {
                    "protocol": "fixed-material/v1",
                    "request_id": request_id,
                    "handoff_id": receipt["handoff_id"],
                    "assistance_ref_digest": digest(reference),
                    "resolution": manifest,
                    **{
                        key: call[key]
                        for key in ("call_id", "arguments_digest", "generation", "sequence")
                    },
                },
            }
            intent.update(
                {"expected_value": resolved["text"]}
                if kind == "text"
                else {"filename": resolved["filename"]}
            )
            page = self.pages.get(job["application_id"])
            if kind == "file" and page in self.workable:
                raise PortalDataError(
                    "unsupported_attachment_transport", "该平台的原生附件路径尚未核验。", 409
                )
            draft = self.drafts.get(page)
            if draft:
                material = {"id": resolved["material_id"], "sha256": resolved["sha256"]}
                if kind == "file":
                    material["filename"] = resolved["filename"]
                draft.begin(
                    question,
                    resolved["text"] if kind == "text" else len(raw),
                    intent,
                    material=material,
                )
            # The draft observer alone is never permission. A failed atomic save
            # leaves no matching durable intent, so the network guard stays closed.
            try:
                self.store.record_native_handoff(
                    reference,
                    request_id=request_id,
                    phase="granted",
                    scope=scope,
                    receipt=receipt,
                    material_intent=intent,
                )
            except (ValueError, TypeError) as error:
                if self.store.storage_error:
                    raise StoreError("Native material checkpoint failed") from error
                raise
        return payload

    def _reconcile_native_material(self, reference, receipt, *, request_id, after_stop=False):
        """Complete only an observed original attempt with independent current readback."""
        calls = receipt.get("calls", [])
        if any(call.get("status") == "in_flight" for call in calls):
            return False
        state = self.store.load()
        job = next(
            (
                row
                for row in state["jobs"]
                if row["application_id"] == reference["binding"]["application_id"]
            ),
            None,
        )
        if not job:
            return False
        intent = self.store.native_material_intent(state, job, reference, request_id=request_id)
        if not intent:
            return False
        call = next(
            (row for row in calls if row["call_id"] == intent["native_material"]["call_id"]), None
        )
        if (
            call is None
            or call.get("status") != "observed"
            or not self.store.native_material_intent(
                state, job, reference, request_id=request_id, call=call
            )
        ):
            return False
        try:
            # The live call keeps its original signature; after a stop only
            # readback is possible, so no admission or dispatch exists here.
            options = {"after_stop": True} if after_stop else {}
            page, check = self._assistance_page_checker(reference, **options)
            check()
            actual = self._read_native_material_field(
                reference,
                call["target_descriptor"]["worker_field"],
                document=call["scope"]["expected_document"],
                **options,
            )
        except (PortalDataError, Error):
            # The physical native receipt is already durable. An unavailable
            # readback leaves its business intent unresolved, not a failed save.
            return False
        target = actual["field"].get("material_target", {})
        manifest = intent["native_material"]["resolution"]
        file = manifest["kind"] == "file"
        if (
            any(
                target.get(key) != value
                for key, value in call["target_descriptor"].items()
                if key not in {"value_empty", "file_count"}
            )
            or actual["sha256"] != manifest["sha256"]
            or actual["size_bytes"] != manifest["size_bytes"]
            or actual["field"].get("valid") is not True
            or actual["field"].get("aria_invalid") not in (None, "", "false")
            or file
            and (target.get("file_count") != 1 or actual["filename"] != manifest["filename"])
            or not file
            and actual["value"] != intent["expected_value"]
        ):
            return False
        questions = [
            row
            for row in job["form_state"]["snapshot"]["fields"]
            if row["id"] == intent["field_id"] and row.get("draft_path", "") == intent["draft_path"]
        ]
        if len(questions) != 1:
            return False
        question = deepcopy(questions[0])
        material = {"id": intent["material_id"], "sha256": manifest["sha256"]}
        if file:
            material["filename"] = manifest["filename"]
            question.update(filename=manifest["filename"], file_sha256=manifest["sha256"])
        draft = self.drafts.get(page)
        if draft and not draft.native_material_verified(intent, question, material):
            return False
        # A local value does not turn a failed or missing network response into
        # remote success. Draft proof above is tied to this attempt's own requests.
        if any(
            _unresolved_write_failure(event, job, state)
            for event in [*job["observations"], *self.transports]
            if event.get("intent") == intent
        ):
            return False
        with self.store.applications.write_lock():
            try:
                check()
            except PortalDataError:
                return False
            current_state = self.store.load()
            current = next(
                row
                for row in current_state["jobs"]
                if row["application_id"] == job["application_id"]
            )
            if (
                self.store.native_material_intent(
                    current_state, current, reference, request_id=request_id, call=call
                )
                != intent
            ):
                return False
            form_flow.note_write(
                current,
                question,
                manifest["filename"] if file else actual["value"],
                {
                    "source": "system_material",
                    "material_id": intent["material_id"],
                    "revision": manifest["sha256"],
                },
            )
            try:
                updated = self.update(
                    current,
                    current_state["batch_id"],
                    completed_intent=intent,
                    intent=None,
                    form_state=current["form_state"],
                )
            except (ValueError, TypeError) as error:
                if self.storage_stopped:
                    raise StoreError("Native material checkpoint failed") from error
                raise
            saved = next(
                row
                for row in self.store.load()["jobs"]
                if row["application_id"] == current["application_id"]
            )
            return updated and saved.get("intent") is None

    def _native_page_reopened(self, reference):
        """This run reopened the job's page (APP-13 Continue) and no takeover touched it.

        The marker is the Worker's own ``page_reopen`` record, started by this run for
        this application, with the current page observed by this run. Any earlier
        native handoff on the page may have left user edits, so it ends the default.
        """
        state = self.store.load()
        job = next(
            row
            for row in state["jobs"]
            if row["application_id"] == reference["binding"]["application_id"]
        )
        reopen = state.get("page_reopen") or {}
        return bool(
            self.run_id
            and reopen.get("status") == "started"
            and reopen.get("run_id") == self.run_id
            and reopen.get("application_id") == job["application_id"]
            and (job.get("page_observation") or {}).get("run_id") == self.run_id
            and not job.get("native_handoff_runs")
        )

    def start_native_assistance(self, assistance_ref, *, request_id):
        """Deliver JSON, then let the original native session execute its own tools."""
        reference = deepcopy(assistance_ref)
        policy = self.native_assistance_policy
        # The Adapter gets only the session's narrow handoff Interface.
        port = native_handoff_port(getattr(self.cua, "client", None))
        executable = port and port.driver_executable
        if (
            policy is None
            or self.codex_assist is None
            or reference.get("protocol") != "codex-assistance/native/v1"
            or reference.get("page_writes_enabled") is not True
            or reference.get("native_policy_digest") != digest(policy)
            or port is None
            or port.driver_sha256 != policy["driver_sha256"]
            or executable is None
        ):
            print("native_assistance_unavailable: worker capability", flush=True)
            raise PortalDataError(
                "native_assistance_unavailable", "原生原页接管能力尚不可用。", 409
            )
        executable = Path(executable)
        if (
            not executable.is_absolute()
            or executable.is_symlink()
            or not executable.is_file()
            or hashlib.sha256(executable.read_bytes()).hexdigest() != policy["driver_sha256"]
        ):
            raise PortalDataError("native_assistance_unavailable", "原生驱动身份已改变。", 409)
        page, check = self._assistance_page_checker(reference)
        check()
        context = self._observe_settling_context(reference)
        native_scope = self.cua.native_page_scope(page, pump=self.pump)
        native_scope["application_ref_digest"] = digest(reference)
        validate_native_assistance_scope(native_scope, reference)
        context["native_scope"] = native_scope
        # Startup work (page context, native scope, Codex launch) can outlast the
        # observation window; each check first refreshes it (seen 2026-10-31: 6.2 s).
        # A slow read is retried, as the context read is; a changed document is not.
        for attempt in range(3):
            if self.pump_codex_events(reference, document=context["document"]):
                break
            failure = self._permit_failure
            print(f"assistance_start_check_failed: {failure}"[:200], flush=True)
            if attempt == 2 or failure not in SLOW_READS:
                raise PortalDataError(
                    "assistance_binding_changed", "原页文档已改变，保留当前现场。", 409
                )
        # That pump re-read the original frame against the captured document and
        # renewed the page observation; the context follows it, since the status
        # read behind the attestation outlasts the window (seen 2026-11-02).
        self._renew_assistance_context(reference, context)
        page_reopened = self._native_page_reopened(reference)
        delivery = self.store.assistance_delivery(reference, page_context=context)
        # 2026-11-03: a report claimed consent answers were missing and no ready
        # material_ref was supplied, but the delivery could not be checked. Keys,
        # statuses and counts only; never values or referenced content.
        print(
            "native_handoff_delivery: "
            + json.dumps(
                {
                    "facts": [
                        [fact.get("fact"), fact.get("status"), len(fact.get("field_ids") or [])]
                        for fact in (delivery.get("answers") or {}).get("facts", [])
                    ],
                    "materials": [
                        [item.get("kind"), item.get("material_id"), item.get("status")]
                        for item in delivery["materials"]
                    ],
                    "remaining": len(delivery["progress"]["remaining"]),
                    "completed": len(delivery["progress"]["completed"]),
                    "pending": len(delivery["pending_actions"]),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        document = deepcopy(context["document"])
        journal_scope = {"native_scope": deepcopy(native_scope), "document": document}
        call_scope = {
            "target_id": native_scope["target_id"],
            "tab_id": native_scope["tab_id"],
            "expected_document": document,
        }
        latest = {}

        def permitted(*, service_stop=True):
            # A slow read is checked again, as at the start: one 2 s frame read that
            # timed out denied a write or the yield and revoked the takeover
            # (2026-11-05, Harmattan). A changed document still fails at once.
            for attempt in range(3):
                if self.pump_codex_events(reference, document=document, service_stop=service_stop):
                    return True
                if attempt < 2 and self._permit_failure in SLOW_READS:
                    print(f"assistance_check_retried: {self._permit_failure}", flush=True)
                    continue
                return False
            return False

        def before_yield(intent):
            if (
                intent.get("application_ref_digest") != digest(reference)
                or intent.get("scope") != call_scope
                or intent.get("request_id") != request_id
                or not permitted()
            ):
                raise PortalDataError("assistance_binding_changed", "原生交接范围已改变。", 409)
            self.store.record_native_handoff(
                reference,
                request_id=request_id,
                phase="prepared",
                scope=journal_scope,
                expected_worker_source=self._page_source,
            )

        refusals_logged = set()

        def after_yield(receipt):
            self._native_work += 1
            try:
                record_receipt(receipt)
            finally:
                self._native_work -= 1

        def record_receipt(receipt):
            latest.update(deepcopy(receipt))
            calls = receipt.get("calls", [])
            # r7 writes pre-ledger refusals as not_sent rows; make each visible once.
            for row in calls:
                if "refusal" in row and row.get("call_id") not in refusals_logged:
                    refusals_logged.add(row.get("call_id"))
                    print(
                        "native_driver_refusal: "
                        + json.dumps(
                            {
                                "tool": row.get("tool"),
                                "role": (row.get("field_hint") or {}).get("role"),
                                "code": row["refusal"],
                                # r10: the core's hit-test geometry, never a value.
                                **(
                                    {"detail": row["refusal_detail"]}
                                    if "refusal_detail" in row
                                    else {}
                                ),
                            }
                        ),
                        flush=True,
                    )
            unknown = any(row.get("status") == "unknown" for row in calls)
            if unknown:
                phase = "unknown"
            elif receipt.get("revoked"):
                phase = (
                    "stopped"
                    if receipt.get("return_ready") is True
                    and receipt.get("local_tools_drained") is True
                    else "stopping"
                )
            else:
                phase = "granted"
            self.store.record_native_handoff(
                reference,
                request_id=request_id,
                phase=phase,
                scope=journal_scope,
                receipt=receipt,
            )
            if phase == "granted":
                # The receipt is this page's own call progress; the observation follows it.
                self._renew_own_observation(reference)
            # A returned receipt is revoked too; reconciliation itself requires an
            # observed original call and exact readback, so stop cannot launder it.
            self._reconcile_native_material(reference, receipt, request_id=request_id)

        def before_native_call(call):
            self._native_work += 1
            try:
                return admit_native_call(call)
            finally:
                self._native_work -= 1

        def admit_native_call(call):
            began = time.monotonic()
            allowed_now = permitted(service_stop=False)
            permitted_s = time.monotonic() - began
            if not allowed_now or call.get("scope") != call_scope or not latest.get("handoff_id"):
                _log_admission_denial(
                    call,
                    f"not_permitted:{self._permit_failure}"
                    if not allowed_now
                    else "scope_changed"
                    if call.get("scope") != call_scope
                    else "handoff_missing",
                )
                return False
            current = next(
                row
                for row in self.store.load()["jobs"]
                if row["application_id"] == reference["binding"]["application_id"]
            )
            if current.get("intent") is not None and not takeover_pending_intent(current):
                _log_admission_denial(call, "intent_pending")
                return False
            self.store.validate_native_answers(reference, delivery["answers"])
            if call.get("tool") in {"browser_type", "browser_set_value"}:
                field_name = (call.get("field_hint") or {}).get("name")
                if not isinstance(field_name, str) or not field_name.strip():
                    _log_typing_denial(call, None, 0, "field_unnamed")
                    return False
                expected_fact = fact_for(field_name)
                values = [
                    fact["value"]
                    for fact in delivery["answers"]["facts"]
                    if fact.get("fact") == expected_fact
                    and fact.get("status") == "confirmed"
                    and isinstance(fact.get("value"), str)
                ]
                if not values:
                    values = native_control_fact_values(delivery, call.get("field_hint") or {})
                allowed = {hashlib.sha256(value.encode()).hexdigest() for value in values}
                if call["tool"] == "browser_set_value":
                    # A checkbox or radio state follows the field's confirmed yes or no.
                    words = {value.strip().casefold() for value in values}
                    for state, vocabulary in (
                        ("true", NATIVE_AFFIRMATIVE_FACT_VALUES),
                        ("false", NATIVE_NEGATIVE_FACT_VALUES),
                    ):
                        if words & vocabulary:
                            allowed.add(hashlib.sha256(state.encode()).hexdigest())
                if call.get("text_sha256") not in allowed:
                    # A denied write revokes the takeover; the log names the field's fact.
                    _log_typing_denial(call, expected_fact, len(values), "value_not_confirmed")
                    return False
            denied = call.get("tool") == "browser_click" and native_click_denial(
                delivery, latest.get("calls", []), call, page_reopened=page_reopened
            )
            if denied:
                # Role and condition only; never a name or value.
                print(
                    "native_click_admission_denied: "
                    + json.dumps(
                        {"role": (call.get("field_hint") or {}).get("role"), "condition": denied}
                    ),
                    flush=True,
                )
                return False
            # Persist the exact native request metadata before the host admits it.
            records = {row["call_id"]: row for row in latest.get("calls", [])}
            records[call["call_id"]] = deepcopy(call)
            receipt = {
                "phase": "active",
                "revoked": False,
                **latest,
                "calls": list(records.values()),
                "active_calls": 1,
                "local_tools_drained": False,
                "return_ready": False,
            }
            if call.get("tool") == "browser_deliver_material":
                # The same settling read as start and return (2026-11-03: a CV's
                # admission read timed out once and revoked the whole takeover).
                # A read that still fails refuses only this delivery.
                material_started = time.monotonic()
                try:
                    context = self._observe_settling_context(reference)
                except (PortalDataError, Error) as error:
                    code = getattr(error, "code", None)
                    if code == "page_observation_changed" or (
                        code is None and getattr(error, "message", None) in SLOW_READS
                    ):
                        raise _material_refusal(
                            code or "read_timeout", "原页读取超时，本次材料未发送。", "page_read"
                        ) from error
                    raise
                # The admission read verified this page's document just now; the
                # snapshot follows that observation, as at the takeover's start
                # (2026-11-05: Harmattan's CV read as an expired JSON context).
                read_s = time.monotonic() - material_started
                self._renew_own_observation(reference)
                self._renew_assistance_context(reference, context)
                renewed = time.monotonic()
                try:
                    return self._prepare_native_material_call(
                        reference,
                        call,
                        context,
                        request_id=request_id,
                        scope=journal_scope,
                        receipt=receipt,
                    )
                finally:
                    # Private timing of a material admission's steps (2026-11-05).
                    print(
                        "native_material_steps: "
                        + json.dumps(
                            {
                                "permitted_s": round(permitted_s, 2),
                                "checks_s": round(material_started - began - permitted_s, 2),
                                "page_read_s": round(read_s, 2),
                                "renew_s": round(renewed - material_started - read_s, 2),
                                "prepare_s": round(time.monotonic() - renewed, 2),
                            }
                        ),
                        flush=True,
                    )
            recorded = time.monotonic()
            self.store.record_native_handoff(
                reference,
                request_id=request_id,
                phase="granted",
                scope=journal_scope,
                receipt=receipt,
            )
            locked = time.monotonic()
            self._submit_lock(page, True)
            print(
                "native_admission_steps: "
                + json.dumps(
                    {
                        "permitted_s": round(permitted_s, 2),
                        "checks_s": round(recorded - began - permitted_s, 2),
                        "record_s": round(locked - recorded, 2),
                        "submit_lock_s": round(time.monotonic() - locked, 2),
                        "frames": len(getattr(page, "frames", ())),
                    }
                ),
                flush=True,
            )
            return True

        def pump():
            # Yield and each new admission verify the full document above.
            # Keep control/revocation moving while native input owns the renderer.
            permitted = self.pump_codex_events(reference)
            if permitted and latest:
                self._reconcile_native_material(reference, latest, request_id=request_id)
            return permitted

        # The one unknown script intent this takeover's dispatch carries, by its
        # delivery action identity; the Adapter refuses any other pending action.
        held = next(
            row
            for row in self.store.load()["jobs"]
            if row["application_id"] == reference["binding"]["application_id"]
        )
        pending_intent = held["intent"] if takeover_pending_intent(held) else None
        # The budget the Worker fixed at dispatch; an older dispatch has the default.
        saved_budget = ((held.get("assistance") or {}).get("dispatch") or {}).get("budget")
        budget = TakeoverBudget.from_dict(saved_budget) if saved_budget else DEFAULT_BUDGET
        try:
            result = self.codex_assist.start_takeover(
                reference,
                request_id=request_id,
                delivery=delivery,
                pending_action_id=pending_intent
                and (pending_intent.get("attempt_id") or digest(pending_intent)),
                native_client=port,
                budget=budget,
                native_scope=call_scope,
                driver_executable=executable,
                before_yield=before_yield,
                after_yield=after_yield,
                before_native_call=before_native_call,
                pump=pump,
            )
        except PortalDataError:
            raise
        except ValueError as error:
            # The adapter's own pre-checks (unresolved run, driver identity) start
            # nothing; that is a capability refusal, not a checkpoint failure.
            print("native_assistance_unavailable: " + repr(error)[:500], flush=True)
            raise PortalDataError(
                "native_assistance_unavailable", "原生原页接管能力尚不可用。", 409
            ) from error
        self._assistance_run = reference, result.run_id
        # The pre-handoff read is the baseline that attributes later page changes.
        self._assistance_baseline = result.run_id, context
        self._service_assistance_stop()
        return result

    def start_json_assistance(self, assistance_ref, *, request_id):
        """Bind JSON context delivery to the existing original-page reservation."""
        reference = deepcopy(assistance_ref)
        if self.codex_assist is None or not self.assistance_read_permitted(reference):
            raise PortalDataError("assistance_read_unavailable", "原页 JSON 交接尚不可用。", 409)
        captured = {}

        def context(current_reference):
            page_context = self.observe_assistance_context(current_reference)
            delivery = self.store.assistance_delivery(current_reference, page_context=page_context)
            captured["document"] = deepcopy(page_context["document"])
            return delivery

        def pump():
            return self.pump_codex_events(reference, document=captured.get("document"))

        result = self.codex_assist.start(
            reference, request_id=request_id, context_handler=context, pump=pump
        )
        self._assistance_run = reference, result.run_id
        self._service_assistance_stop()
        return result

    def start_readonly_assistance(self, assistance_ref, *, request_id):
        """Explicitly bind the passive observer; no model turn or page write is started."""
        reference = deepcopy(assistance_ref)
        if self.codex_assist is None or not self.assistance_read_permitted(reference):
            raise PortalDataError("assistance_read_unavailable", "原页只读接管尚不可用。", 409)
        captured = {}

        def observe(current_reference):
            result = self.observe_assistance_page(current_reference)
            captured["document"] = deepcopy(result["document"])
            return result

        def pump():
            return self.pump_codex_events(reference, document=captured.get("document"))

        result = self.codex_assist.start(
            reference, request_id=request_id, readonly_handler=observe, pump=pump
        )
        self._assistance_run = reference, result.run_id
        self._service_assistance_stop()
        return result

    def _service_assistance_stop(self):
        """Persist revocation before stopping the dedicated process, outside the lock."""
        if self._servicing_assistance_stop:
            return
        if self._assistance_run is None:
            # Unclaimed metadata, or a dispatch this runner refused or never began,
            # started no run. Only its original owner may acknowledge this no-start outcome.
            with self.store.applications.write_lock():
                state = self.store.load()
                changed = False
                for job in state["jobs"]:
                    assistance = job.get("assistance") or {}
                    dispatch = assistance.get("dispatch") or {}
                    if (
                        assistance.get("status") == "stopping"
                        and (
                            assistance.get("claim_request_id") is None
                            or "failed_code" in dispatch
                            or dispatch
                            and (
                                digest(assistance_reference(assistance)),
                                assistance["claim_request_id"],
                            )
                            not in self._dispatched
                        )
                        and assistance.get("binding", {}).get("run_id") == self.run_id
                        and (state.get("runtime") or {}).get("id") == self.run_id
                    ):
                        changed |= settle_unstarted_stop(job)
                        changed |= self._paused_assistance_wait(job)
                if changed:
                    self.persist(state)
            return
        reference, run_id = self._assistance_run
        retry_run, retry_at, delay = self._assistance_stop_retry
        if retry_run == run_id and time.monotonic() < retry_at:
            return
        self._servicing_assistance_stop = True
        request_id = "stop-" + run_id
        try:
            progress = self.codex_assist.progress(run_id)
            permitted = self.assistance_read_permitted(reference)
            with self.store.applications.write_lock():
                state = self.store.load()
                job = next(
                    (
                        item
                        for item in state["jobs"]
                        if item["application_id"] == reference["binding"]["application_id"]
                    ),
                    None,
                )
                assistance = (job or {}).get("assistance")
                matched = assistance and digest(assistance_reference(assistance)) == digest(
                    reference
                )
                if matched:
                    if (
                        permitted
                        and progress.status == "ready"
                        and not progress.tools_revoked
                        and not assistance.get("stop")
                    ):
                        return
                    changed = False
                    backend = assistance_backend_permitted(state, assistance)
                    if not backend:
                        changed = mark_assistance_backend_lost(state, reference)
                    # A normal native turn end revokes tools too; only a clean
                    # completion on the still-valid scope is not a scope loss.
                    completed = (
                        permitted
                        and backend
                        and progress.status == "ready"
                        and getattr(progress, "native_turn_status", None) == "completed"
                        and getattr(progress, "error_code", None) is None
                    )
                    # A run that failed to start is a capability failure, not a lost scope.
                    failed = progress.status == "failed"
                    print(
                        "assistance_progress_stop: "
                        + json.dumps(
                            {
                                "permitted": permitted,
                                "backend": backend,
                                "status": progress.status,
                                "error_code": getattr(progress, "error_code", None),
                                "tools_revoked": progress.tools_revoked,
                                "turn": getattr(progress, "native_turn_status", None),
                                "stop": bool(assistance.get("stop")),
                            }
                        ),
                        flush=True,
                    )
                    reason = (
                        "native_turn_completed"
                        if completed
                        else "assistance_unavailable"
                        if failed
                        else "assistance_scope_lost"
                    )
                    if revoke_assistance(job, reason=reason, request_id=request_id):
                        changed = True
                        if not completed:
                            # Stop the job here; its earlier blocker reason is stale.
                            self._assistance_wait(
                                job,
                                (getattr(progress, "error_code", None) or reason)
                                if failed
                                else reason,
                            )
                    if changed:
                        self.persist(state)
                    request_id = assistance["stop"]["request_id"]
            stopped = self.codex_assist.stop(run_id, request_id=request_id)
            if stopped.stop_status == "stopped":
                self._assistance_stop_retry = (None, 0.0, 0.0)
            else:
                # An unconfirmed stop is only re-read on later ticks; the Adapter
                # sends no second revoke, interrupt or signal (2026-11-02: 379 resends).
                delay = STOP_RECHECK_INTERVAL
                self._assistance_stop_retry = (run_id, time.monotonic() + delay, delay)
            if matched:
                with self.store.applications.write_lock():
                    state = self.store.load()
                    job = next(
                        (
                            item
                            for item in state["jobs"]
                            if item["application_id"] == reference["binding"]["application_id"]
                        ),
                        None,
                    )
                    changed = bool(job) and adopt_assistance_stop(
                        job, reference, asdict(stopped), request_id=request_id
                    )
                    saved = (job or {}).get("assistance") or {}
                    if stopped.report is not None and saved.get("stop") and "report" not in saved:
                        # A claim received before any stop is history; only the
                        # return service can turn a completed turn into an outcome.
                        with suppress(PortalDataError):
                            changed |= adopt_assistance_report(
                                job, reference, stopped.report, request_id=request_id
                            )
                    if job:
                        changed |= self._paused_assistance_wait(job)
                    if changed:
                        self.persist(state)
                    if saved.get("stop", {}).get("stop_status") == "stopped" and (
                        saved["stop"]["reason"]
                        in {"assistance_scope_lost", "assistance_unavailable", "user_paused"}
                        or (saved.get("superseded") or {}).get("reason") == "user_paused"
                    ):
                        # Nothing remains to drive or return. The once-guard still keeps
                        # this claim from restarting; a later claim may start. Backend
                        # stops keep the run so a later tick still records the loss.
                        self._assistance_run = None
                        self._assistance_baseline = None
            elif stop_evidence_proven(asdict(stopped)):
                # The job no longer holds this run's record (archived on Continue or
                # replaced by a new claim) and its stop is proven: release the handle
                # so the job's current claim can start.
                self._assistance_run = None
                self._assistance_baseline = None
        except (OSError, StoreError):
            self.codex_assist.stop(run_id, request_id=request_id)
            raise
        finally:
            self._servicing_assistance_stop = False

    def _paused_assistance_wait(self, job):
        """A takeover stopped by Pause waits, so a later Continue lets the script recheck."""
        assistance = job.get("assistance") or {}
        stop = assistance.get("stop") or {}
        if (
            stop.get("stop_status") != "stopped"
            or "user_paused"
            not in {stop.get("reason"), (assistance.get("superseded") or {}).get("reason")}
            or (job["status"], job.get("reason")) == ("needs_recheck", "assistance_paused")
            or job["status"] == "cancelled"
        ):
            return False
        self._assistance_wait(job, "assistance_paused")
        return True

    def _service_assistance_dispatch(self):
        """Start the current job's claimed system takeover once; a refusal waits.

        A capability failure keeps the page, materials and policy, records its code
        and is never retried here; only a new claim may start another takeover.
        """
        if self._assistance_run is not None or self.codex_assist is None:
            return
        state = self.store.load()
        identifier = state.get("current_job_id")
        job = next((row for row in state["jobs"] if row["application_id"] == identifier), None)
        assistance = (job or {}).get("assistance") or {}
        dispatch = assistance.get("dispatch")
        if (
            assistance.get("protocol") != "codex-assistance/native/v1"
            or assistance.get("status") != "claimed"
            or not isinstance(dispatch, dict)
            or "stop" in assistance
            or "failed_code" in dispatch
            or state["control"] != "running"
            or self.shared_fault
            or self.storage_stopped
            or self.store.stop_reason()
        ):
            return
        reference = assistance_reference(assistance)
        request_id = assistance["claim_request_id"]
        key = digest(reference), request_id
        if key in self._dispatched:
            return
        self._dispatched.add(key)
        try:
            result = self.start_native_assistance(reference, request_id=request_id)
            code = result.error_code if getattr(result, "status", None) == "failed" else None
        except (PortalDataError, Error) as error:
            code = getattr(error, "code", "native_assistance_unavailable")
            if not hasattr(error, "code"):
                import traceback

                print("native_assistance_unavailable: " + repr(error)[:500], flush=True)
                print("".join(traceback.format_exc(limit=-8))[-3000:], flush=True)
            else:
                # The private log keeps the cause behind a coded refusal (2026-11-05:
                # cua_page_unverified named none of its four conditions).
                print(
                    f"native_assistance_failed: {code} cause={error.__cause__!r}"[:600],
                    flush=True,
                )
        if code is None:
            return
        with self.store.applications.write_lock():
            state = self.store.load()
            job = next((row for row in state["jobs"] if row["application_id"] == identifier), None)
            current = (job or {}).get("assistance")
            if not current or digest(assistance_reference(current)) != digest(reference):
                return
            record_takeover_failure(job, request_id=request_id, code=code)
            revoke_assistance(job, reason="assistance_unavailable", request_id="stop-" + request_id)
            self._assistance_wait(job, code)
            self.persist(state)
        self._service_assistance_stop()

    def pump_codex_events(
        self, assistance_ref, *, document=None, after_stop=False, service_stop=True
    ) -> bool:
        """Keep control and browser events alive without executing queued page work.

        ``service_stop=False`` is a native admission's own check: it runs inside the
        Adapter's progress, whose stop service would ask that progress again (1-4.7 s
        per pump, 2026-11-05). Its scope check still refuses a paused, cancelled or
        changed job; the next ordinary pump serves the stop.
        """
        started = time.monotonic()
        self.tick(control_only=True, service_stop=service_stop)
        ticked = time.monotonic()
        if self.context is not None:
            # Codex's own loop paces these calls; an idle wait here only delays a
            # write's admission, which the driver drops after 15 s (2026-11-02).
            self.pump(idle_ms=5)
        pumped = time.monotonic()
        permitted = self.assistance_read_permitted(
            assistance_ref, document=document, after_stop=after_stop
        )
        if time.monotonic() - started > 2:
            # Private timing of a slow pump: an admission waits on it (2026-11-05).
            print(
                "codex_pump_slow: "
                + json.dumps(
                    {
                        "tick_s": round(ticked - started, 2),
                        "pump_s": round(pumped - ticked, 2),
                        "check_s": round(time.monotonic() - pumped, 2),
                        "caller": _callers(3),
                    }
                ),
                flush=True,
            )
        return permitted

    def _fill_route(self, page, question):
        return (
            select_fill_route(page, question, self.cua)
            if self.live
            else {
                "executor": "playwright",
                "input_route": "dom",
                "route_reason": "supported_synthetic_field",
            }
        )

    def _service_assistance_return(self):
        """Adopt one completed native turn only after reclaim and a read-only page check.

        Codex's report is a claim. A check failure keeps it as history and waits;
        another dispatch is not started here. Store save failures still propagate.
        """
        if self._assistance_run is None or self.codex_assist is None:
            return
        reference, run_id = self._assistance_run
        if reference.get("protocol") != "codex-assistance/native/v1":
            return
        identifier = reference["binding"]["application_id"]
        state = self.store.load()
        job = next((row for row in state["jobs"] if row["application_id"] == identifier), None)
        assistance = (job or {}).get("assistance")
        if (
            not assistance
            or digest(assistance_reference(assistance)) != digest(reference)
            or assistance["status"] != "stopped"
            or (assistance.get("stop") or {}).get("reason") != "native_turn_completed"
            or "superseded" in assistance
            or state["control"] != "running"
        ):
            return
        stop = assistance["stop"]
        report = self.codex_assist.progress(run_id).report
        claimed = (report or {}).get("claimed") if isinstance(report, dict) else None
        wait = (
            "assistance_completion_unverified"
            if isinstance(claimed, dict) and claimed.get("status") == "ready_for_review"
            else "assistance_return_unverified"
        )
        try:
            if report is None:
                raise PortalDataError("assistance_report_missing", "接管未给出结构化回报。", 409)
            with self.store.applications.write_lock():
                state = self.store.load()
                job = next(row for row in state["jobs"] if row["application_id"] == identifier)
                if adopt_assistance_report(job, reference, report, request_id=stop["request_id"]):
                    self.persist(state)
            self._reclaim_native_session()
            reclaimed_at = time.time()
            runs = [
                row
                for row in job.get("native_handoff_runs", [])
                if row["assistance_ref"] == reference
            ]
            if not runs:
                raise PortalDataError("native_handoff_missing", "没有该接管的原生记录。", 409)
            run = runs[-1]
            self._reconcile_native_material(
                reference,
                run["events"][-1]["receipt"] or {},
                request_id=run["request_id"],
                after_stop=True,
            )
            job = next(
                row for row in self.store.load()["jobs"] if row["application_id"] == identifier
            )
            if takeover_pending_intent(job):
                # The carried unknown result is settled by readback, never replayed.
                wait, unverified = "assistance_pending_intent", wait
                with browser_deadline(5):
                    self._readback_pending(self.pages[identifier], job, state["batch_id"])
                job = next(
                    row for row in self.store.load()["jobs"] if row["application_id"] == identifier
                )
                if takeover_pending_intent(job):
                    raise PortalDataError(wait, "接管携带的未知结果仍不能核验。", 409)
                wait = unverified
            context = self._observe_settling_context(reference, after_stop=True)
            job = next(
                row for row in self.store.load()["jobs"] if row["application_id"] == identifier
            )
            outcome, writes = self._assistance_outcome(job, run_id, run, context, reclaimed_at)
            script_read = None
            if outcome["kind"] == "script_checkpoint":
                # Native input is trusted; acknowledge it only on attributed controls,
                # as the script does after its own readback, so a return is not an edit.
                with browser_deadline(5):
                    script_read = self.observe(self.pages[identifier], job)
            with self.store.applications.write_lock():
                state = self.store.load()
                job = next(row for row in state["jobs"] if row["application_id"] == identifier)
                outcome["adopted_at"] = time.time()
                adopt_assistance_outcome(state, job, reference, outcome)
                if job["assistance"]["status"] != "released":
                    self._assistance_wait(job, wait)
                elif outcome["kind"] == "script_checkpoint":
                    for question, value, call_id in writes:
                        form_flow.note_write(
                            job,
                            question,
                            value,
                            {
                                "source": "codex_native",
                                "request_id": run["request_id"],
                                "call_id": call_id,
                            },
                            observed=script_read,
                        )
                    if job["status"] != "cancelled":
                        job.update(status="filling", reason="")
                    self.work_progressed = True
                elif job["status"] != "cancelled":
                    message = "已填写并核验：请在专用浏览器复核并人工提交。"
                    # Make the outcome durable before the external App write, so a
                    # lost save leaves the App record for the same re-save (S6).
                    job.update(status="ready_for_review", reason="", pending_sync=message)
                    self.persist(state)
                    self.store.sync(job, message)
                self.persist(state)
        except (PortalDataError, Error) as error:
            # The job keeps only the wait reason; the private log names the check
            # (2026-11-02: a refused return left nothing to diagnose on disk).
            notice = {}
            if getattr(error, "code", None) == "native_controls_remaining":
                # A checked stop, not a refusal: the user finishes or retries natively.
                wait, notice = error.code, {"message": str(error)}
            causes, cause = [], error.__cause__
            while cause is not None and len(causes) < 3:
                causes.append(str(cause)[:200])
                cause = cause.__cause__
            claim = claimed if isinstance(claimed, dict) else {}
            # A bare read timeout names no check; the last application frames do
            # (2026-11-02: owned_browser_read_timeout somewhere after the stop).
            where = [
                f"{Path(frame.filename).stem}:{frame.name}:{frame.lineno}"
                for frame in traceback.extract_tb(error.__traceback__)
                if "career_evidence_graph" in frame.filename
            ][-4:]
            print(
                f"{wait}: "
                + json.dumps(
                    {
                        "check": getattr(error, "code", type(error).__name__),
                        "message": str(error)[:200],
                        "reason": causes,
                        "where": where,
                        "claimed_status": claim.get("status"),
                        "next_step": claim.get("next_step"),
                        "field_states": sorted(
                            collections.Counter(
                                str(row.get("state"))
                                for row in claim.get("fields", [])
                                if isinstance(row, dict)
                            ).items()
                        ),
                        **(
                            {"unattributed": error.unattributed}
                            if hasattr(error, "unattributed")
                            else {}
                        ),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            with self.store.applications.write_lock():
                state = self.store.load()
                job = next(
                    (row for row in state["jobs"] if row["application_id"] == identifier), None
                )
                current = (job or {}).get("assistance")
                if (
                    current
                    and digest(assistance_reference(current)) == digest(reference)
                    and current["status"] == "stopped"
                    and "superseded" not in current
                ):
                    self._assistance_wait(job, wait, **notice)
                    self.persist(state)
        self._assistance_run = None
        self._assistance_baseline = None

    def _assistance_wait(self, job, reason, message="自动填表暂停该岗位：请核验页面、笔记和简历。"):
        if job["status"] != "cancelled":
            job.update(status="needs_recheck", reason=reason)
            self.store.sync(job, message)

    def _assistance_outcome(self, job, run_id, run, context, reclaimed_at):
        """Derive the Worker's own conclusion from the stopped page; never from the claim."""
        assistance = job["assistance"]
        report = assistance.get("report")
        claimed = report["claimed"]
        kind = {
            "blocked_segment_resolved": "script_checkpoint",
            "ready_for_review": "filling_complete",
        }.get(claimed["status"])
        fields = context["data"]["fields"]
        calls = {
            call["call_id"]: call
            for event in run["events"]
            for call in (event["receipt"] or {}).get("calls", [])
        }

        def refused(reason, *, unattributed=None):
            # The job keeps the code; the private log keeps which check refused.
            error = PortalDataError(
                "assistance_outcome_unverified", "接管结果不能核验，保留原页。", 409
            )
            if unattributed is not None:
                error.unattributed = unattributed
            raise error from ValueError(reason)

        blocked = next(
            (
                name
                for name, broken in (
                    ("claimed_status", kind is None),
                    ("unresolved_action_ids", bool(claimed["unresolved_action_ids"])),
                    ("script_intent_pending", bool(job.get("intent"))),
                    ("run_not_stopped", run["phase"] != "stopped"),
                    ("semantic_unknown", bool(run["semantic_unknown"])),
                    (
                        "mutation_unsettled",
                        any(
                            call["mutation"]
                            and call["status"] in {"awaiting_host", "in_flight", "unknown"}
                            for call in calls.values()
                        ),
                    ),
                    ("document_changed", context["document"] != run["scope"]["document"]),
                    (
                        "baseline_missing",
                        not self._assistance_baseline or self._assistance_baseline[0] != run_id,
                    ),
                )
                if broken
            ),
            None,
        )
        if blocked:
            refused(blocked)

        def keys(row):
            target = (row.get("material_target") or {}).get("worker_field", "")
            return {row.get("id", ""), row.get("name", ""), target} - {""}

        def key(index, row):
            return (
                row.get("id")
                or row.get("name")
                or (row.get("material_target") or {}).get("worker_field")
                or f"field-{index}"
            )

        def empty(row):
            if row.get("type") == "file":
                return not row.get("files")
            if row.get("type") == "radio":
                return not any(
                    other.get("type") == "radio"
                    and other.get("name") == row.get("name")
                    and other.get("value") == "true"
                    for other in fields
                )
            return row.get("value") in (None, "") or (
                row.get("type") == "checkbox" and row.get("value") == "false"
            )

        invalid = [
            row
            for row in fields
            if row.get("valid") is False or row.get("aria_invalid") not in (None, "", "false")
        ]
        if kind == "script_checkpoint":
            # A required field left for the script is invalid only because it is still
            # empty (2026-11-05: Harmattan's return refused for its 7 remaining fields);
            # an invalid value already on the page still refuses the return.
            invalid = [row for row in invalid if not empty(row)]
        if invalid:
            refused("validation_errors")

        verification = [
            {
                "id": key(index, row),
                "required": bool(row.get("required")),
                "valid": row.get("valid") is not False
                and row.get("aria_invalid") in (None, "", "false"),
                "value_empty": empty(row),
                "file_count": min(len(row.get("files") or []), 100),
            }
            for index, row in enumerate(fields)
        ]
        before = {
            key(index, row): row
            for index, row in enumerate(self._assistance_baseline[1]["data"]["fields"])
        }

        def norm(value):
            return " ".join(str(value or "").split()).casefold()

        def role(call):
            return norm((call.get("field_hint") or {}).get("role"))

        # The ledger in order; a refusal row was never sent and is no mutation here,
        # as in admission's option-owner rule.
        ledger = sorted(
            (
                call
                for call in calls.values()
                if call["mutation"] and "refusal" not in call and "sequence" in call
            ),
            key=lambda call: call["sequence"],
        )
        owners, collapses, opened = {}, set(), None
        for call in ledger:
            observed_click = call["tool"] == "browser_click" and call["status"] == "observed"
            name = norm((call.get("field_hint") or {}).get("name"))
            if role(call) == "option" and opened is not None:
                # An option belongs to the combobox whose observed click precedes it.
                owners[call["call_id"]] = opened
            if observed_click and role(call) == "combobox" and opened == name:
                # r13: a second click right after the same combobox's expand collapses
                # it; it changes no field value.
                collapses.add(call["call_id"])
                opened = None
            elif observed_click and role(call) == "combobox":
                opened = name
            else:
                opened = None
        observed = [
            call
            for call in ledger
            if call["status"] == "observed" and call["call_id"] not in collapses
        ]

        def bare(value):
            # A page shows a required field as "Email*"; its label is "Email"
            # (2026-11-05: Harmattan's typed Name and Email read as unattributed).
            return norm(value).rstrip("*✱").strip()

        def named(row, name):
            return bare(name) in ({bare(row.get(key)) for key in ("label", "id", "name")} - {""})

        def owned(call):
            """The combobox fields an option click set, with their hidden native twins."""
            owner = owners.get(call["call_id"])
            rows = [
                row
                for row in fields
                if owner and _native_control_kind(row) == "combobox" and named(row, owner)
            ]
            containers = {row["container_id"] for row in rows if row.get("container_id")}
            names = {row["name"] for row in rows if row.get("name")}
            # 2026-11-03: a hidden native select elsewhere on the page names the same
            # fact ("personal_details[country_of_residence]" for "Country of
            # residence"); delivery's own label mapping binds them. Visible controls never.
            facts = {
                fact
                for fact in [native_field_fact({"label": owner})]
                + [native_field_fact(row) for row in rows]
                if fact and not fact.startswith("question:")
            }
            return rows + [
                row
                for row in fields
                if row.get("hidden") is True
                and (
                    row.get("container_id") in containers
                    or row.get("name") in names
                    or native_field_fact(row) in facts
                )
                and all(row is not other for other in rows)
            ]

        def touches(call, row):
            if role(call) == "option":
                return any(row is other for other in owned(call))
            target = call.get("target_descriptor") or {}
            return named(row, norm(call["field_hint"]["name"])) or bool(
                keys(row) & ({target.get("worker_field", ""), target.get("id", "")} - {""})
            )

        attributed, writes, unattributed = [], [], []
        snapshot = ((job.get("form_state") or {}).get("snapshot") or {}).get("fields", [])

        def label(value):
            try:
                return normalize_question(value)
            except (StoreError, TypeError):
                return ""

        def question_for(row):
            matches = [
                question
                for question in snapshot
                if question.get("id") in keys(row)
                or keys(row) & set(question.get("control_ids") or [])
            ]
            if not matches and label(row.get("label")):
                # The form reader keys questions by hosted markers; a row without a
                # material target links only through a label unique on both sides.
                name = label(row.get("label"))
                matches = [q for q in snapshot if label(q.get("question")) == name]
                if sum(label(other.get("label")) == name for other in fields) != 1:
                    matches = []
            return matches[0] if len(matches) == 1 else None

        for index, row in enumerate(fields):
            previous = before.get(key(index, row))
            if previous is not None and all(
                previous.get(name) == row.get(name) for name in ("value", "files")
            ):
                continue
            matches = [call for call in observed if touches(call, row)]
            options = [call for call in matches if role(call) == "option"]
            if options:
                # The chosen option set the value; its expand click only opened the list.
                # A reopened combobox keeps its last choice.
                matches = options[-1:]
            if len(matches) != 1:
                unattributed.append(key(index, row))
                continue
            attributed.append({"field_id": key(index, row), "call_id": matches[0]["call_id"]})
            question = question_for(row)
            if row.get("type") != "file":
                writes.append(
                    (
                        deepcopy(question or {"id": key(index, row), "type": row.get("type")}),
                        row.get("value"),
                        matches[0]["call_id"],
                    )
                )
        outcome = {
            "protocol": "assistance-outcome/v1",
            "kind": kind,
            # The Worker's canonical JSON digest of the saved report.
            "report_sha256": hashlib.sha256(
                json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "stop_request_id": assistance["stop"]["request_id"],
            "session_reclaimed_at": reclaimed_at,
            "page_verification": {
                "at": context["at"],
                "document": deepcopy(context["document"]),
                "fields": verification,
                "worker_source": self._page_source,
            },
            "verified": {"materials": [], "optional_failures": []},
            "attributed_fields": attributed,
            "return_count": job.get("assistance_return_count", 0) + (kind == "script_checkpoint"),
        }
        if kind == "script_checkpoint":
            # One strict return per job; the next pending fields must be script-supported.
            if unattributed:
                # Field ids/names only, never values, so the log names what changed.
                refused("unattributed_change", unattributed=unattributed[:50])
            if job.get("assistance_return_count", 0) != 0:
                refused("return_repeated")
            if not snapshot:
                # No script question exists on this page, so no checkpoint can resume
                # the script; name what the native path left, never its values.
                raise PortalDataError(
                    "native_controls_remaining",
                    native_remaining_message(
                        claimed,
                        fields,
                        verification,
                        native_resume_deliveries(job, context["document"]),
                    ),
                    409,
                )
            done = {row["field_id"] for row in attributed}
            pending = []
            for index, row in enumerate(fields):
                question = question_for(row)
                if (
                    question is not None
                    and question.get("type") != "file"
                    and empty(row)
                    and key(index, row) not in done
                ):
                    pending.append(question)
            following = (claimed.get("next_step") or {}).get("field_id")
            if following is not None:
                # Codex names the field from the handoff page_context (DOM id/name);
                # map it like question_for, else accept an exact script question id.
                named = [row for row in fields if following in {row.get("id"), row.get("name")}]
                question = (
                    question_for(named[0])
                    if len(named) == 1
                    else None
                    if named
                    else next((q for q in pending if q.get("id") == following), None)
                )
                if question is None or all(q is not question for q in pending):
                    refused("next_step_question_unknown")
                following = question["id"]
            page = self.pages.get(job["application_id"])
            with browser_deadline(5):
                if any(self._fill_route(page, q)["executor"] == "manual" for q in pending):
                    refused("next_field_manual_route")
            outcome["checkpoint_field_id"] = following or (pending[0]["id"] if pending else None)
            if not outcome["checkpoint_field_id"]:
                refused("checkpoint_field_missing")
            return outcome, writes
        if any(row["required"] and row["value_empty"] or not row["valid"] for row in verification):
            refused("required_empty_or_invalid")
        verified = self.verified_intents(job)
        materials = outcome["verified"]["materials"]
        visible = {file.get("name") for row in fields for file in row.get("files") or []} | {
            item.get("name") for item in context["data"].get("attachments", [])
        }

        # The job's resume is always checked: a re-rendered upload widget may unmount
        # its file input, which must not skip the check (2026-11-03).
        if job.get("file_sha256"):
            deliveries = native_resume_deliveries(job, context["document"])
            # A native delivery's own form item is read even when a field lists the
            # name: the widget may show the file beside an upload error (2026-11-03).
            page_state = (
                self._native_filename_shown(
                    self.pages.get(job["application_id"]),
                    job.get("filename"),
                    document=context["document"],
                    target=next((call["target_descriptor"] for call in deliveries), None),
                )
                if deliveries or job.get("filename") not in visible
                else {"shown": False, "scope": "", "error": False}
            )
            if (
                job.get("filename") not in visible
                and not page_state["shown"]
                or page_state["error"]
                or not (
                    self.recovered_upload(job)
                    or any(
                        intent.get("action") == "upload" and intent.get("material_id") == "resume"
                        for intent in verified
                    )
                    or deliveries
                )
            ):
                refused("resume_upload_unverified")
            materials.append(
                {
                    "kind": "resume",
                    "filename": job["filename"],
                    "sha256": job["file_sha256"],
                }
            )
        materials.extend(
            {
                "kind": "material",
                "material_id": intent["material_id"],
                "action": intent["action"],
                "field_id": intent.get("field_id", ""),
            }
            for intent in verified
            if intent.get("material_id") not in (None, "resume")
        )
        delivery = job.get("cover_letter_delivery") or {}
        if delivery.get("status") in {"queued", "running"} or (
            delivery.get("status") == "failed" and delivery.get("requirement") != "optional"
        ):
            refused("cover_letter_delivery_unsettled")
        if delivery.get("status") == "failed":
            outcome["verified"]["optional_failures"].append(
                {
                    "material": "cover_letter",
                    "status": "failed",
                    "reason": delivery.get("reason", ""),
                }
            )
        # A natively delivered cover letter gets the resume's page check: its name is
        # shown and its scope shows no upload error (2026-11-04: the letter's input was
        # unmounted after upload, so no verified row named it). An optional letter that
        # fails the check is reported, not blocking; a required one refuses.
        checked = set()
        for letter in job.get("materials", []):
            if (
                letter.get("kind") != "cover_letter"
                or letter.get("status") != "ready"
                or letter.get("sha256") in checked
            ):
                continue
            deliveries = native_material_deliveries(
                job, context["document"], letter.get("sha256"), letter.get("filename")
            )
            if not deliveries:
                continue
            checked.add(letter["sha256"])
            page_state = self._native_filename_shown(
                self.pages.get(job["application_id"]),
                letter["filename"],
                document=context["document"],
                target=deliveries[-1]["target_descriptor"],
            )
            if letter["filename"] not in visible and not page_state["shown"] or page_state["error"]:
                if delivery.get("requirement") == "required":
                    refused("cover_letter_upload_unverified")
                outcome["verified"]["optional_failures"].append(
                    {
                        "material": "cover_letter",
                        "status": "unverified",
                        "reason": "cover_letter_upload_unverified",
                    }
                )
                continue
            materials.append(
                {
                    "kind": "cover_letter",
                    "material_id": letter.get("id", ""),
                    "filename": letter["filename"],
                    "sha256": letter["sha256"],
                }
            )
        return outcome, writes

    def tick(self, *, control_only=False, service_stop=True) -> None:
        self.work_progressed = False
        try:
            started = time.monotonic()
            maintain = getattr(self.cua, "maintain", None)
            if maintain is not None and not self.shared_fault:
                try:
                    maintain(pump=self.pump)
                except PortalDataError as error:
                    print(f"cua_owner_unknown: {error.code} {error}", flush=True)
                    self.event("cua_owner_unknown")
            maintained = time.monotonic()
            if control_only:
                self._tick(control_only=True)
            else:
                self._tick()
            ticked = time.monotonic()
            if service_stop:
                self._service_assistance_stop()
            if control_only and time.monotonic() - started > 1.5:
                # Private timing of a slow control tick inside a takeover (2026-11-05).
                print(
                    "control_tick_slow: "
                    + json.dumps(
                        {
                            "maintain_s": round(maintained - started, 2),
                            "state_s": round(ticked - maintained, 2),
                            "stop_service_s": round(time.monotonic() - ticked, 2),
                        }
                    ),
                    flush=True,
                )
            if not control_only:
                self._service_assistance_dispatch()
                self._service_assistance_return()
                self.service_backend_recovery()
            if not control_only and self.codex_assist is not None:
                self.codex_assist.service_readonly()
                self._service_assistance_stop()
        except (OSError, StoreError, PortalDataError, ValueError, KeyError, TypeError):
            self.storage_stopped = True
            self.store.block_storage()
            if self._assistance_run is not None:
                _, run_id = self._assistance_run
                with suppress(OSError, ValueError):
                    self.codex_assist.stop(run_id, request_id="checkpoint-unavailable-" + run_id)
            # Failed snapshots do not replace the last valid checkpoint.
            print("checkpoint_unavailable: automatic actions stopped", flush=True)

    def _tick(self, *, control_only=False) -> None:
        with self.store.applications.write_lock():
            state = self.store.load()
            if self.batch_id != state["batch_id"]:
                self.batch_id = state["batch_id"]
                self.temporary.clear()
            if (
                self.storage_stopped
                and not self.store.stop_reason()
                and state["control"] == "running"
                and state.get("resume_serial", 0) > self.stopped_serial
            ):
                self.storage_stopped = False
            if self.shared_fault or self.storage_stopped or self.store.stop_reason():
                state.update(
                    control="paused", worker_error=self.shared_fault or "checkpoint_unavailable"
                )
                for job in state["jobs"]:
                    if job["intent"] and job["status"] != "cancelled":
                        job.update(status="needs_recheck", reason="checkpoint_unavailable")
            self.drain_events(state)
            if not control_only:
                self.commands(state)
            self.drain_events(state)
            now = time.time()
            state["worker_heartbeat"] = now
            state["worker_pid"] = os.getpid()
            PAGE_SCOPE.refresh(state, now=now)
            for job in state["jobs"]:
                page = self.pages.get(job["application_id"])
                if page in self.blocked_pages and job["status"] not in {
                    "cancelled",
                    "needs_recheck",
                }:
                    job.update(status="needs_recheck", reason=self.blocked_pages[page])
                    self.store.sync(job, "页面发送路径未验证：请人工核验当前页面。")
                if job.get("reason") != "user_authentication":
                    # Continue (or any other state) ends the sign-in window.
                    self.login_pages.discard(page)
                if page and page.is_closed():
                    self._forget_page(job["application_id"], page)
                    job["page_open"] = False
                    if job["status"] != "cancelled":
                        job.update(status="needs_recheck", reason="page_lost")
                elif page and not self.shared_fault:
                    job["page_observation"] = {
                        "run_id": self.run_id,
                        "page_id": self.page_ids.get(page),
                        "event": "observed",
                        "at": now,
                    }
            if self.transports or not self.store.liveness_only(state):
                # An idle tick that moved only the heartbeat skips the full rewrite.
                self.persist(state)
            if control_only or not self.permitted(state):
                return
            jobs = [
                deepcopy(j)
                for j in state["jobs"]
                if (
                    j["status"] in {"queued", "filling", "needs_input", "ready_for_review"}
                    or j["status"] == "needs_recheck"
                    and (j.get("intent") or {}).get("form_protocol") == "form-state/v1"
                )
                and not j["handed_off"]
                and (
                    "current_job_id" not in state or j["application_id"] == state["current_job_id"]
                )
            ]
            batch_id = state["batch_id"]
        for job in jobs:
            try:
                with (
                    self.store.measurements.stage(
                        "form_step",
                        episode_id=job.get("measurement_id"),
                        application_id=job["application_id"],
                        batch_id=batch_id,
                        run_id=self.run_id,
                    ),
                    browser_deadline(self.action_timeout),
                ):
                    if job["status"] == "ready_for_review":
                        page = self.pages.get(job["application_id"])
                        if page is None or page.is_closed():
                            raise PortalDataError(
                                "page_lost", "原页不可核验，保留终稿和动作。", 409
                            )
                        if assistance_completion(job) is not None:
                            # The adopted outcome already holds the read-only page check.
                            continue
                        observed = self.observe(page, job)
                        delivery = job.get("cover_letter_delivery") or {}
                        if delivery and job.get("workflow") == "single":
                            from .application_materials import material_consistency_status

                            fixed = self.store.material_inputs(job)
                            material_consistency_status(fixed)
                            branch = fixed.get("cover_letter") or {}
                            if branch.get("status") == "needs_recheck" or (
                                delivery.get("status") in {"queued", "running"}
                                and branch.get("status") == "ready"
                                and delivery.get("selected_fields")
                                and not job.get("manual_submission")
                            ):
                                if self.update(job, batch_id, status="filling"):
                                    job["status"] = "filling"
                                    self.process(job, batch_id)
                                continue
                        form_flow.capture(self, page, job, batch_id, observed)
                        form_flow.check_ready(job, observed)
                    else:
                        self.process(job, batch_id)
            except (
                Error,
                OSError,
                PortalDataError,
                ValueError,
                StopIteration,
                KeyError,
                TypeError,
                IndexError,
            ) as exc:
                page = self.pages.get(job["application_id"])
                code = getattr(exc, "code", None)
                if (
                    code in {"unsupported_structure", "unsupported_attachments"}
                    and page is not None
                    and not page.is_closed()
                ):
                    # The native takeover that follows needs the page's letter ready
                    # before its reference binds the job's materials. A page with more
                    # file inputs than the script reads stops as unsupported_attachments.
                    self._prepare_native_cover_letter(job, batch_id, page)
                self.update(
                    job,
                    batch_id,
                    status="needs_recheck",
                    reason=getattr(exc, "code", None)
                    or self.blocked_pages.get(self.pages.get(job["application_id"]))
                    or "browser_result_unknown",
                )
                if (
                    code in {"unsupported_structure", "unsupported_attachments"}
                    and page is not None
                    and not page.is_closed()
                ):
                    with suppress(Error, PortalDataError, OSError, StoreError, StopIteration):
                        form_flow.bind_page(self, page, job, batch_id)
                if getattr(exc, "code", None) == "user_authentication":
                    page = self.pages.get(job["application_id"])
                    if page is not None and not page.is_closed():
                        # Expose the retained page for the user's login. Its requests
                        # pass until the next Continue, except a recognized final
                        # submit (decided 2026-10-31: blocked sign-ins never completed).
                        self.login_pages.add(page)
                        self._submit_lock(page, False)
                        with suppress(Error, PortalDataError):
                            if self.cua is not None:
                                self.cua.review(page, pump=self.pump)
                            page.bring_to_front()
                pending = self.store.load()["jobs"]
                current = next(
                    (j for j in pending if j["application_id"] == job["application_id"]), {}
                )
                intent = current.get("intent")
                if intent and intent.get("attempt_id"):
                    self.store.measurements.event(
                        "action_result",
                        stage=intent["action"],
                        attempt_id=intent["attempt_id"],
                        result="unknown",
                        run_id=self.run_id,
                        episode_id=current.get("measurement_id"),
                        application_id=current["application_id"],
                    )

            finally:
                # Persist native facts before another job can occupy the next action budget.
                if self.events or self.transports:
                    with self.store.applications.write_lock():
                        latest = self.store.load()
                        self.drain_events(latest)
                        self.persist(latest)

    def update(
        self, job: dict, batch_id: str, *, completed_intent: dict | None = None, **changes
    ) -> bool:
        with self.store.applications.write_lock():
            state = self.store.load()
            if state["batch_id"] != batch_id:
                return False
            current = next(j for j in state["jobs"] if j["application_id"] == job["application_id"])
            if "questions" in changes or (
                changes.get("status") == "ready_for_review"
                and completed_intent is None
                and not job.get("intent")
            ):
                # Read-derived waits and readiness do not replace a newer stop,
                # handoff, pending action or saved answer queue.
                if (
                    current["status"] not in {"queued", "filling", "needs_input"}
                    or current.get("intent")
                    or current.get("handed_off")
                    or current.get("manual_submission")
                    or state.get("current_job_id", job["application_id"]) != job["application_id"]
                    or (state.get("runtime") or {}).get("id") != self.run_id
                    or any(
                        current.get("form_state", {}).get(key) != job.get("form_state", {}).get(key)
                        for key in ("binding", "revision", "snapshot_sha256")
                    )
                ):
                    return False
                try:
                    require_execution(
                        self.store.applications,
                        job["application_id"],
                        automated_owner(self.store.root, batch_id, job["application_id"]),
                        "automated",
                    )
                except PortalDataError:
                    return False
                if "questions" in changes:
                    temporary = deepcopy(self.temporary)
                    for command in state["commands"]:
                        if (
                            command.get("action") == "one-use"
                            and command.get("id") == job["application_id"]
                        ):
                            temporary.setdefault(job["application_id"], {})[command["fact"]] = {
                                "key": "one-use",
                                "question": command["fact"],
                                "value": command["value"],
                                "scope": {"application_id": job["application_id"]},
                                "state": "confirmed",
                            }
                    changes["questions"] = [
                        question
                        for question in changes["questions"]
                        if self.store.resolve(question, current, temporary) is None
                    ]
                    if not changes["questions"] and changes.get("reason") == "missing_answers":
                        for key in ("status", "reason", "intent"):
                            changes.pop(key, None)
            cancelled = current["status"] == "cancelled"
            if cancelled:
                # Record an in-flight result without reviving the cancelled job.
                changes = {k: v for k, v in changes.items() if k not in {"status", "reason"}}
            if "observations" in changes:
                changes["observations"] = [
                    *current["observations"],
                    *[o for o in changes["observations"] if o not in current["observations"]],
                ]
            completed_intent = (
                deepcopy(completed_intent if completed_intent is not None else job["intent"])
                if changes.get("intent", "retained") is None
                else None
            )
            blocked = self.blocked_pages.get(self.pages.get(job["application_id"]))
            if completed_intent and blocked and not cancelled and not current["handed_off"]:
                changes.pop("intent", None)
                changes.update(status="needs_recheck", reason=blocked)
                completed_intent = None
            if changes.get("intent", "retained") is None and current["intent"] not in (
                None,
                completed_intent,
            ):
                # A delayed completion does not clear or finish a different attempt.
                changes = {
                    k: v for k, v in changes.items() if k not in {"intent", "status", "reason"}
                }
            if "form_state" in changes and (
                cancelled
                or not completed_intent
                or current.get("intent") != completed_intent
                or current.get("form_state", {}).get("binding")
                != changes["form_state"].get("binding")
                or state.get("current_job_id", job["application_id"]) != job["application_id"]
            ):
                changes.pop("form_state", None)
            current.update(changes)
            if completed_intent:
                current["observations"].append(
                    {
                        "action": "action_result",
                        "intent": completed_intent,
                        "result": "verified",
                        "at": time.time(),
                        "run_id": self.run_id,
                    }
                )
            if changes.get("status") == "ready_for_review":
                self.store.sync(current, "已填写并核验：请在专用浏览器复核并人工提交。")
            elif changes.get("status") == "needs_input":
                self.store.sync(current, "自动填表等待：请补充已确认答案。")
            elif changes.get("status") == "needs_recheck":
                self.store.sync(
                    current,
                    "请在原浏览器完成登录或验证，再点击一次继续。"
                    if current.get("reason") == "user_authentication"
                    else "自动填表暂停该岗位：请核验页面、笔记和简历。",
                )
            self.persist(state)
            if changes.get("status") in {"ready_for_review", "needs_input", "needs_recheck"}:
                self.work_progressed = False
            if completed_intent and current["intent"] is None:
                self.work_progressed = (
                    completed_intent["action"] == "upload"
                    and state["control"] == "running"
                    and current["status"] == "filling"
                )
                self.store.measurements.event(
                    "action_result",
                    stage=completed_intent["action"],
                    attempt_id=completed_intent.get("attempt_id"),
                    result="verified",
                    episode_id=current.get("measurement_id"),
                    application_id=current["application_id"],
                    run_id=self.run_id,
                )
            return True

    @contextmanager
    def dispatch_current(self, job, batch_id, intent, *, observed=None):
        """Keep selection and the exact pending intent stable through one browser send."""
        with self.store.applications.write_lock():
            state = self.store.load()
            current = next(
                row for row in state["jobs"] if row["application_id"] == job["application_id"]
            )
            if (
                state["batch_id"] != batch_id
                or "current_job_id" in state
                and state["current_job_id"] != job["application_id"]
                or not self.permitted(state, self.pages.get(job["application_id"]))
                or current["handed_off"]
                or current["status"] != "filling"
                or current["intent"] != intent
                or material_edit_pending(current)
                or precision_preparation_pending(current)
                and intent["action"] != "open"
                or manual_submission_unresolved(
                    {**current, "observations": [*current["observations"], *self.transports]}
                )
            ):
                raise PortalDataError(
                    "current_action_changed", "当前岗位或待执行动作已变化，保留原动作记录。", 409
                )
            require_execution(
                self.store.applications,
                job["application_id"],
                automated_owner(self.store.root, batch_id, job["application_id"]),
                "automated",
            )
            self.check_inputs(current)
            if observed is not None:
                form_flow.check_snapshot(
                    self, self.pages.get(job["application_id"]), current, observed
                )
            if intent.get("form_protocol") == "form-state/v1":
                intent["dispatch_state"] = "sent"
                current["intent"] = deepcopy(intent)
                self.persist(state)
            self._submit_lock(self.pages.get(job["application_id"]), True)
            yield
            if intent.get("form_protocol") == "form-state/v1":
                latest = self.store.load()
                current = next(
                    row for row in latest["jobs"] if row["application_id"] == job["application_id"]
                )
                if current.get("intent") == intent:
                    intent["dispatch_state"] = "returned"
                    current["intent"] = deepcopy(intent)
                    self.persist(latest)

    def authorize(self, job: dict, batch_id: str, intent: dict) -> bool:
        # The executor has no click/Enter/evaluate/submit action. New operations
        # must establish their non-final meaning before entering this dispatcher.
        if intent.get("action") not in {"open", "fill", "upload", "advance"}:
            raise PortalDataError(
                "unsupported_action", "此动作需核验，最终 Submit 由用户操作。", 409
            )
        with self.store.applications.write_lock():
            state = self.store.load()
            current = next(j for j in state["jobs"] if j["application_id"] == job["application_id"])
            if (
                state["batch_id"] != batch_id
                or "current_job_id" in state
                and state["current_job_id"] != job["application_id"]
            ):
                return False
            if any(_unresolved_write_failure(event, current, state) for event in self.transports):
                self.persist(state)
                return False
            if not script_writes_allowed(state, job["application_id"]):
                return False
            if not self.permitted(state, self.pages.get(job["application_id"])):
                if state["control"] == "running":
                    state.update(
                        control="paused",
                        worker_error=self.shared_fault
                        or self.store.stop_reason()
                        or "control_connection_lost",
                    )
                    self.persist(state)
                return False
            if (
                state["control"] != "running"
                or state["batch_id"] != batch_id
                or "current_job_id" in state
                and state["current_job_id"] != job["application_id"]
            ):
                return False
            current = next(j for j in state["jobs"] if j["application_id"] == job["application_id"])
            if (
                current["status"] not in {"queued", "filling", "needs_input"}
                or current["handed_off"]
            ):
                return False
            if current["intent"] or manual_submission_unresolved(
                {**current, "observations": [*current["observations"], *self.transports]}
            ):
                return False
            require_execution(
                self.store.applications,
                current["application_id"],
                automated_owner(self.store.root, batch_id, current["application_id"]),
                "automated",
            )
            self.check_inputs(
                current,
                material_required=current.get("workflow") != "single"
                or intent["action"] == "upload",
            )
            if (
                material_edit_pending(current)
                or precision_preparation_pending(current)
                and intent["action"] != "open"
            ):
                return False
            if intent["action"] == "advance":
                page = self.pages.get(current["application_id"])
                navigation = intent.get("navigation")
                if (
                    not self.live
                    or page is None
                    or not isinstance(navigation, dict)
                    or set(intent) != {"action", "navigation"}
                    or set(navigation) != {"control_id", "from_step", "to_step"}
                    or any(not isinstance(value, str) or not value for value in navigation.values())
                    or self.observe(page, current).get("navigation") != navigation
                ):
                    raise PortalDataError(
                        "navigation_changed", "下一步的实际目标已变更，请核验原页。", 409
                    )
            if current.get("form_state") and intent["action"] != "open":
                intent.update(
                    form_protocol="form-state/v1",
                    dispatch_state="prepared",
                    form_binding=deepcopy(current["form_state"]["binding"]),
                )
                if intent["action"] == "upload":
                    snapshot = current["form_state"].get("snapshot", {})
                    candidates = list(snapshot.get("fields", []))
                    if not intent.get("material_id"):
                        candidates += [
                            {"type": "file", "resume": True, **row}
                            for row in snapshot.get("retained_resume", [])
                        ]
                    attachments = [
                        row
                        for row in candidates
                        if row.get("type") == "file"
                        and (
                            (
                                intent.get("field_id")
                                and row.get("id") == intent["field_id"]
                                and row.get("draft_path", "") == intent.get("draft_path", "")
                            )
                            or not intent.get("field_id")
                            and row.get("resume", True)
                        )
                    ]
                    intent["before_attachments_sha256"] = digest(attachments)
            intent.update(
                attempt_id=uuid4().hex,
                run_id=self.run_id,
                page_id=self.page_ids.get(self.pages.get(current["application_id"])),
                prepared_at=time.time(),
                input_refs={"revision": current["revision"], "file_sha256": current["file_sha256"]},
            )
            job["revision"] = current["revision"]
            self.store.measurements.event(
                "action_start",
                stage=intent["action"],
                attempt_id=intent["attempt_id"],
                episode_id=current.get("measurement_id"),
                application_id=current["application_id"],
                run_id=self.run_id,
            )
            current.update(intent=intent, status="filling")
            self.persist(state)
            return True

    @staticmethod
    def effective_action_results(job: dict) -> dict[str, dict]:
        """Keep the existing Runner entry point for the Worker-owned pure projection."""
        return effective_action_results(job)

    @staticmethod
    def verified_intents(job: dict) -> list[dict]:
        return [
            row["intent"]
            for row in ApplicationRunner.effective_action_results(job).values()
            if row["conclusion"] == "current_matches"
        ]

    @staticmethod
    def recovered_upload(job: dict) -> bool:
        return any(
            intent["action"] == "upload"
            and not intent.get("material_id")
            and intent.get("kind", "resume") == "resume"
            and intent.get("sha256") == job["file_sha256"]
            for intent in ApplicationRunner.verified_intents(job)
        )

    @staticmethod
    def has_unbound_completion(job: dict) -> bool:
        for index, observation in enumerate(job["observations"]):
            if observation.get("verified") is not True:
                continue
            if observation.get("action") == "fill" and not observation.get("intent"):
                return True
            if observation.get("action") == "select_file":
                completion = next(
                    (
                        item
                        for item in job["observations"][index + 1 :]
                        if item.get("action") in {"action_result", "select_file", "fill"}
                    ),
                    {},
                )
                intent = completion.get("intent") or {}
                if not (
                    completion.get("action") == "action_result"
                    and completion.get("result") == "verified"
                    and intent.get("action") == "upload"
                    and intent.get("attempt_id")
                    and "run_id" in intent
                    and intent.get("page_id")
                    and intent.get("sha256") == observation.get("local_sha256")
                    and intent.get("page_id") == observation.get("page_id")
                    and intent.get("run_id") == observation.get("run_id")
                    and completion.get("run_id") == observation.get("run_id")
                ):
                    return True
        return False

    def advance(self, page, job: dict, batch_id: str, observed: dict) -> None:
        """Perform one explicit forward step through the existing dispatcher."""
        form_flow.check_ready(job, observed)
        navigation = observed["navigation"]
        if any(
            previous["action"] == "advance" and previous.get("navigation") == navigation
            for previous in self.verified_intents(job)
        ):
            raise PortalDataError(
                "recovered_result_not_visible", "已完成的页面步骤不再可见，请核验原页。", 409
            )
        if any(not question["valid"] for question in observed["fields"]):
            raise PortalDataError("readback_failed", "当前页面仍有未通过核验的字段。", 409)
        control = page.locator(
            f"[data-ts-worker-navigation={json.dumps(navigation['control_id'])}]"
        )
        original = control.element_handle()
        if original is None:
            raise PortalDataError("navigation_changed", "下一步按钮已变更。", 409)
        intent = {"action": "advance", "navigation": deepcopy(navigation)}
        document_step = navigation["from_step"].startswith("https://")
        target = page.locator(f"[id={json.dumps(navigation['to_step'])}][role=tabpanel]")
        original_target = None
        try:
            if not document_step:
                original_target = target.element_handle()
                if original_target is None:
                    raise PortalDataError("navigation_changed", "下一步目标已变更。", 409)
            if not self.authorize(job, batch_id, intent):
                return
            with self.store.applications.write_lock():
                state = self.store.load()
                current = next(
                    row for row in state["jobs"] if row["application_id"] == job["application_id"]
                )
                if (
                    state["batch_id"] != batch_id
                    or not self.permitted(state, page)
                    or current["status"] != "filling"
                    or current["handed_off"]
                    or current["intent"] != intent
                ):
                    raise PortalDataError("navigation_changed", "当前页面步骤已失效。", 409)
                self.check_inputs(current)
            fresh = self.observe(page, job)
            if (
                fresh.get("navigation") != navigation
                or fresh["fields"] != observed["fields"]
                or not control.evaluate_all(
                    "(nodes, original) => original.isConnected && "
                    "nodes.length === 1 && nodes[0] === original",
                    original,
                )
                or not document_step
                and not target.evaluate_all(
                    "(nodes, original) => original.isConnected && "
                    "nodes.length === 1 && nodes[0] === original",
                    original_target,
                )
            ):
                raise PortalDataError("navigation_changed", "下一步按钮、字段或目标已变更。", 409)
            field_counter = page.evaluate("window.__tsWorkerNextField || 0") if document_step else 0
            with self.dispatch_current(job, batch_id, intent, observed=observed):
                original.click(timeout=3000)
            if document_step:
                page.wait_for_function(
                    "target => location.href === target && document.readyState !== 'loading'",
                    arg=navigation["to_step"],
                    timeout=5000,
                )
                self.document_urls[page] = navigation["to_step"]
                # The same Page now owns a new document. Allocate new control
                # identities so a completed fill on the old document cannot be
                # confused with a new, empty control that has the same label.
                page.evaluate(
                    "counter => { window.__tsWorkerNextField = "
                    "Math.max(window.__tsWorkerNextField || 0, counter); }",
                    field_counter,
                )
                # Read the new document before settling the existing attempt. Its
                # role/company, fields and requests still pass the ordinary guard.
                try:
                    self.observe(page, job)
                except PortalDataError as error:
                    if error.code == "user_authentication":
                        # The exact GET reached its bound document. Authentication
                        # is an observed wait, not an unknown write or permission
                        # to replay the navigation after the user signs in.
                        self.update(job, batch_id, intent=None, completed_intent=intent)
                    raise
                self.update(job, batch_id, intent=None, completed_intent=intent)
                return
            page.wait_for_function(
                """target => {
                    const panel=document.getElementById(target);
                    return panel?.getAttribute('role') === 'tabpanel' &&
                        Boolean(panel.getClientRects().length) &&
                        getComputedStyle(panel).visibility !== 'hidden';
                }""",
                arg=navigation["to_step"],
                timeout=5000,
            )
            after = self.observe(page, job)
            if after.get("stage") != navigation["to_step"] or not target.evaluate_all(
                "(nodes, original) => original.isConnected && "
                "nodes.length === 1 && nodes[0] === original",
                original_target,
            ):
                raise PortalDataError("navigation_changed", "下一步结果需要核验。", 409)
            self.update(job, batch_id, intent=None, completed_intent=intent)
        finally:
            original.dispose()
            if original_target is not None:
                original_target.dispose()

    def upload_supplement(self, page, job, batch_id, observed):
        """Each supplemental field has its own bytes, intent and readback evidence."""
        from .application_materials import material_kind

        for question in observed["fields"]:
            kind = material_kind(question)
            if (
                question["type"] != "file"
                or question["resume"]
                or (not question["required"] and kind != "cover_letter")
            ):
                continue
            delivery = job.get("cover_letter_delivery") or {}
            if (
                kind == "cover_letter"
                and delivery
                and [question["id"], question.get("draft_path", "")]
                not in delivery.get("selected_fields", [])
            ):
                continue
            manual = next(
                (
                    row
                    for row in job.get("manual_attachments", [])
                    if row["id"] == question["id"] and row.get("filename")
                ),
                None,
            )
            if manual:
                if any(
                    question.get(key) != manual.get(key)
                    for key in ("filename", "file_sha256", "draft_path")
                ):
                    raise PortalDataError(
                        "manual_attachment_changed", "人工附件已改变，请保留原页核验。", 409
                    )
                continue
            material = self.store.field_material(question, job)
            if material is None:
                retained = next(
                    (
                        row
                        for row in job.get("materials", [])
                        if row.get("field_id") == question["id"] and row.get("status") == "manual"
                    ),
                    None,
                )
                if (
                    retained
                    and retained.get("filename") == question.get("filename")
                    and question.get("file_sha256")
                ):
                    continue
                if not question["required"] and not question.get("filename"):
                    continue
                raise PortalDataError(
                    "material_attachment_unverified",
                    "已有必要附件未绑定真实文件，请保留原页核验。",
                    409,
                )
            previous = [
                intent
                for intent in self.verified_intents(job)
                if intent["action"] == "upload"
                and intent.get("material_id") == material["id"]
                and intent.get("field_id") == question["id"]
                and intent.get("draft_path", "") == question.get("draft_path", "")
                and intent.get("sha256") == material["sha256"]
            ]
            draft = self.drafts.get(page)
            if question.get("filename"):
                if (
                    question["filename"] != material["filename"]
                    or question.get("file_sha256")
                    and question["file_sha256"] != material["sha256"]
                ):
                    raise PortalDataError(
                        "upload_mismatch", "当前必要附件与该字段材料版本不符。", 409
                    )
                if (
                    not previous
                    or not question.get("file_sha256")
                    and not (draft and draft.file_verified(question, material))
                ):
                    raise PortalDataError(
                        "upload_result_unknown", "必要附件结果尚未核验；不会自动重传。", 409
                    )
                continue
            if previous:
                raise PortalDataError(
                    "recovered_result_not_visible", "已确认附件不可见；不会重复上传。", 409
                )
            if page in self.workable:
                if not question["required"]:
                    self.update(
                        job,
                        batch_id,
                        cover_letter_delivery={
                            **delivery,
                            "status": "failed",
                            "reason": "unsupported_attachment_transport",
                        },
                    )
                    continue
                raise PortalDataError(
                    "unsupported_attachment_transport",
                    "该平台的附稿发送路径尚未核验，保留当前原页。",
                    409,
                )
            intent = {
                "action": "upload",
                "field_id": question["id"],
                "draft_path": question.get("draft_path", ""),
                "kind": material["kind"],
                "material_id": material["id"],
                "sha256": material["sha256"],
            }
            if not self.authorize(job, batch_id, intent):
                return True
            self.store.verify_material(material, job)
            self.store.verify_material_source(material)
            current_material = self.store.field_material(question, job)
            if current_material is None or digest(current_material) != digest(material):
                raise PortalDataError("material_changed", "发送前求职信材料版本已改变。", 409)
            raw = Path(material["file_path"]).read_bytes()
            if draft:
                draft.begin(question, len(raw), intent, material=material)
            with self.dispatch_current(job, batch_id, intent, observed=observed):
                hosted_ats.control(page, question).set_input_files(
                    {"name": material["filename"], "mimeType": "application/pdf", "buffer": raw}
                )
            if draft:
                draft.wait(page)
            after = self.observe(page, job)
            if after.get("document_token") != observed.get("document_token"):
                raise PortalDataError("upload_result_unknown", "上传期间原文档已变化。", 409)
            actual = next(
                row
                for row in after["fields"]
                if row["id"] == question["id"]
                and row.get("draft_path", "") == question.get("draft_path", "")
            )
            if (
                actual["filename"] != material["filename"]
                or actual.get("file_sha256")
                and actual["file_sha256"] != material["sha256"]
                or not actual.get("file_sha256")
                and not (draft and draft.file_verified(actual, material))
            ):
                raise PortalDataError(
                    "upload_result_unknown", "必要附件选择或服务端回读结果未知。", 409
                )
            form_flow.note_write(
                job,
                actual,
                actual.get("value"),
                {
                    "key": material["id"],
                    "revision": material["sha256"],
                    "source": "system_material",
                },
                observed=after,
            )
            self.update(
                job,
                batch_id,
                form_state=job.get("form_state", {}),
                completed_intent=intent,
                intent=None,
                observations=[
                    *job["observations"],
                    {
                        "action": "select_file",
                        "material_id": material["id"],
                        "field_id": question["id"],
                        "draft_path": question.get("draft_path", ""),
                        "local_sha256": material["sha256"],
                        "verified": True,
                        "run_id": self.run_id,
                        "page_id": self.page_ids.get(page),
                        "at": time.time(),
                    },
                ],
            )
            return True
        return False

    def observe_pending(self, page, job):
        intent = job.get("intent") or {}
        target = intent.get("navigation", {}).get("to_step", "")
        if (
            self.live
            and intent.get("form_protocol") == "form-state/v1"
            and intent.get("action") == "advance"
            and intent.get("run_id") == self.run_id
            and intent.get("page_id") == self.page_ids.get(page)
            and target.startswith("https://")
            and page.url == target
        ):
            result = hosted_ats.observe(page, job, document_url=target)
            self.document_urls[page] = target
            return result
        return self.observe(page, job)

    def _readback_pending(self, page, job, batch_id):
        """Classify a retained unknown intent by independent readback; never replay it."""
        original_intent = deepcopy(job["intent"])
        observed = self.observe_pending(page, job)
        form_flow.capture(self, page, job, batch_id, observed)
        form_flow.inspect_pending(self, page, job, observed)
        with self.store.applications.write_lock():
            state = self.store.load()
            current = next(
                row for row in state["jobs"] if row["application_id"] == job["application_id"]
            )
            if (
                state["batch_id"] == batch_id
                and current.get("intent") == original_intent
                and current["status"] != "cancelled"
            ):
                for key in (
                    "intent",
                    "form_state",
                    "action_resolutions",
                    "pending_action_observations",
                ):
                    if key in job:
                        current[key] = deepcopy(job[key])
                current.update(
                    status="queued" if job.get("intent") is None else "needs_recheck",
                    reason="" if job.get("intent") is None else "action_result_unknown",
                )
                self.persist(state)

    def _enter_application(self, page) -> str | None:
        """Open a job description's one apply entry, as part of opening the job.

        A description page holds nothing to fill or submit, so entering its form
        needs no guard. Returns the application page URL, or None when the page
        already is the form or has no single entry.
        """
        source = page.url
        try:
            for _hop in range(2):
                target = page.evaluate(hosted_ats.SITE_APPLY_LINK)
                if not target or target == page.url:
                    break
                page.goto(target, wait_until="domcontentloaded", timeout=20000)
            entry = page.evaluate(hosted_ats.APPLY_ENTRY)
        except (Error, TimeoutError):
            return page.url if page.url != source else None
        if entry["form"]:
            return page.url if page.url != source else None
        if len(entry["hrefs"]) == 1:
            page.goto(entry["hrefs"][0], wait_until="domcontentloaded", timeout=20000)
        elif not entry["hrefs"] and entry["buttons"] == 1:
            tab = None
            try:
                with page.context.expect_page(timeout=3000) as opened:
                    page.locator("[data-ts-apply-entry='1']").click(timeout=5000)
                tab = opened.value
            except TimeoutError:
                pass
            with suppress(TimeoutError, Error):
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            if tab is not None:
                # An entry opening a new tab is followed in the job's own page.
                with suppress(TimeoutError, Error):
                    tab.wait_for_load_state("domcontentloaded", timeout=10000)
                target = tab.url
                tab.close()
                if target.startswith(("https://", "http://")):
                    page.goto(target, wait_until="domcontentloaded", timeout=20000)
        else:
            return None
        with suppress(TimeoutError):
            page.locator("input[type=email],form,[role=form]").first.wait_for(timeout=10000)
        return page.url if page.url != source else None

    def process(self, job: dict, batch_id: str) -> None:
        require_execution(
            self.store.applications,
            job["application_id"],
            automated_owner(self.store.root, batch_id, job["application_id"]),
            "automated",
        )
        if job["intent"]:
            if job["intent"].get("form_protocol") != "form-state/v1":
                self.update(job, batch_id, status="needs_recheck", reason="action_result_unknown")
                return
            page = self.pages.get(job["application_id"])
            if page is None or page.is_closed():
                self.update(job, batch_id, status="needs_recheck", reason="action_result_unknown")
                return
            self._readback_pending(page, job, batch_id)
            return
        identifier = job["application_id"]
        form = None if self.live else form_for(job)
        page = self.pages.get(identifier)
        if page is None:
            with self.store.applications.write_lock():
                state = self.store.load()
                explicit_current = "current_job_id" in state
                if explicit_current and state["current_job_id"] != identifier:
                    return
                occupied = (
                    sum(identifier == state["current_job_id"] for identifier in self.pages)
                    if explicit_current
                    else len(self.pages)
                )
                if occupied >= state["page_capacity"]:
                    self.update(
                        job,
                        batch_id,
                        reason="page_capacity",
                        **({"status": "needs_input"} if explicit_current else {}),
                    )
                    return
            intent = {"action": "open"}
            if not self.authorize(job, batch_id, intent):
                return
            page = (
                self.context.new_page()
                if self.cua is None
                else self.cua.new_page(self.context, keep_visible=bool(self.handed_off_pages))
            )
            self.pages[identifier] = page
            self.page_ids[page] = uuid4().hex
            page.on("close", lambda *_: self.event("page_closed", page, identifier))
            page.on("crash", lambda *_: self.event("page_crashed", page, identifier))
            if self.live and supports_ashby_drafts(job["job_url"]):
                self.drafts[page] = DraftSession(job)
            if self.live and job_shortcode(job["job_url"]):
                self.workable[page] = ResumeUpload(job)
            if self.live:
                page.route_web_socket("**/*", lambda ws: self._websocket_guard(page, ws))
            self.guards[identifier] = self._guard(identifier, job["platform"])
            if not self.live:
                page.route("**/*", self.guards[identifier])
            page.goto(
                hosted_ats.page_url(job) if self.live else self.origin + form.page_path(identifier),
                wait_until="domcontentloaded",
                timeout=20000 if self.live else 8000,
            )
            if self.live:
                try:
                    page.locator(
                        "input[type=email],form,[role=form]"
                        if job["platform"] == "generic"
                        else "form#application-form,form#application_form"
                    ).first.wait_for(timeout=10000)
                except TimeoutError:
                    # A listing page or an unsupported platform shows no form. The
                    # page stays open; its read leads to a sign-in wait or takeover.
                    if job["platform"] != "generic":
                        raise
            generic_live = self.live and job["platform"] == "generic"
            entry_url = self._enter_application(page) if generic_live else None
            if entry_url:
                # This open's own reads check the page against the job held here.
                job = {**job, "entry_url": entry_url}
                self.document_urls[page] = entry_url
            self.update(
                job,
                batch_id,
                **({"entry_url": entry_url} if entry_url else {}),
                page_open=True,
                page_observation={
                    "run_id": self.run_id,
                    "page_id": self.page_ids.get(page),
                    "event": "observed",
                    "at": time.time(),
                },
                intent=None,
                completed_intent=intent,
            )
        from .application_bound_materials import verify_original_page

        if verify_original_page(self, page, job):
            self.update(
                job,
                batch_id,
                material_update=deepcopy(job["material_update"]) | {"status": "complete"},
            )
            return
        observed = self.observe(page, job)
        unbound = self.has_unbound_completion(job)
        history_jobs = []
        if not unbound:
            with self.store.applications.write_lock():
                state = self.store.load()
                # Stored job URLs are already canonicalized by preparation.
                history_jobs = [
                    previous
                    for batch in state.get("batch_history", [])
                    for previous in batch["jobs"]
                    if previous["application_id"] == identifier
                    or previous.get("job_url") == job["job_url"]
                ]
                unbound = any(self.has_unbound_completion(previous) for previous in history_jobs)
        if unbound:
            raise PortalDataError(
                "recovery_completion_unbound",
                "旧完成证据没有可靠的动作绑定。请人工核验并接管；不会重复动作。",
                409,
            )
        resolutions = latest_action_resolutions(job.get("action_resolutions", []))
        legacy_negative = {
            ref
            for ref, r in resolutions.items()
            if "observation_count" not in r and r["conclusion"] != "current_matches"
        }
        if legacy_negative:
            verified = self.verified_intents(job)
            completed = self.verified_intents({**job, "action_resolutions": []})
            if any(
                (intent.get("attempt_id") or digest(intent)) in legacy_negative
                and intent not in verified
                for intent in completed
            ):
                raise PortalDataError(
                    "recovery_order_unknown",
                    "旧动作完成与处理结论的先后顺序无法确认。请人工核验并接管；不会重复动作。",
                    409,
                )
        draft = self.drafts.get(page)
        if draft:
            draft.job = job
        if self.live and any(q["multiple"] for q in observed["fields"]):
            raise PortalDataError("unsupported_attachments", "多选附件需要人工核验。", 409)
        if self.live:
            from .application_materials import SupplementalMaterials

            materials = SupplementalMaterials(
                self.store,
                allowed=lambda state, identifier: self.permitted(state, self.pages.get(identifier)),
                update=self.update,
                persist=self.persist,
                model_context=pause_browser_deadline,
            )
            if not materials.prepare(
                job,
                batch_id,
                observed,
                temporary=self.temporary,
                page_binding={"run_id": self.run_id, "page_id": self.page_ids.get(page)},
            ):
                return
        if precision_preparation_pending(job):
            from .application_bound_materials import document_token

            with self.store.applications.write_lock():
                state = self.store.load()
                current = next(row for row in state["jobs"] if row["application_id"] == identifier)
                if (
                    not self.permitted(state, page)
                    or current.get("intent")
                    or current.get("handed_off")
                    or not precision_preparation_pending(current)
                    or material_edit_pending(current)
                    or manual_submission_unresolved(
                        {**current, "observations": [*current["observations"], *self.transports]}
                    )
                ):
                    return
                self.check_inputs(current)
                current["precision_preparation"].update(
                    status="ready",
                    run_id=self.run_id,
                    page_id=self.page_ids[page],
                    document_token=document_token(page),
                    observed=deepcopy(observed),
                    materials=deepcopy(current.get("materials", [])),
                )
                current.update(status="needs_input", reason="precision_adjustment")
                state["control"] = "paused"
                self.persist(state)
            return
        form_state = form_flow.capture(self, page, job, batch_id, observed)
        parser = form_state["parser"]
        if parser["status"] == "failed" or form_state.get("intervention_pending"):
            self.update(
                job, batch_id, status="needs_recheck", reason=parser.get("reason") or "form_changed"
            )
            return
        if parser.get("observed_status") == "active":
            self.update(job, batch_id, reason="awaiting_parser")
            return
        if self.finish_materials(page, job, batch_id, observed, [], None, upload_only=True):
            return
        if parser["status"] != "stable":
            self.update(job, batch_id, reason="awaiting_parser")
            return
        missing, resolved = [], []
        with self.store.applications.write_lock():
            for question in observed["fields"]:
                if question["type"] == "file":
                    continue
                answer = self.store.resolve(question, job, self.temporary)
                if answer is None:
                    if question["required"] and (
                        not question.get("value") or not question.get("valid")
                    ):
                        missing.append(
                            {
                                **question,
                                "value": "",
                                "scope": default_scope(fact_for(question["question"]), job),
                            }
                        )
                else:
                    resolved.append((question, *answer))
        resolved, kept = form_flow.plan(
            job,
            observed,
            resolved,
            retry_intents=[
                row["intent"]
                for row in self.effective_action_results(job).values()
                if row["conclusion"] == "not_applied"
            ],
        )
        form_flow.save_plan(self, job, batch_id)
        if not self.update(job, batch_id, questions=missing):
            return

        def expected_for(question, value):
            if draft and question["type"] in {"radio", "select"}:
                return draft.option_value(question, value)
            if question["type"] in {"radio", "checkbox"}:
                i = question["options"].index(value)
                return hosted_ats.control(page, question, i).get_attribute("value")
            return value

        def matches(question, value):
            return (
                question["value"] == value
                and question["valid"]
                and (not draft or draft.saved(question, expected_for(question, value)))
            )

        verified_refs = [
            {**ref, "field_id": question["id"]}
            for question, value, ref in [*resolved, *kept]
            if matches(question, value)
        ]
        self.update(job, batch_id, answer_refs=verified_refs)
        for question, value, ref in resolved:
            if matches(question, value):
                continue
            if any(
                intent["action"] == "fill"
                and intent.get("answer_ref") == ref
                and (
                    intent.get("field_id") == question["id"]
                    or intent.get("draft_path")
                    and intent["draft_path"] == question.get("draft_path")
                    or (
                        intent.get("run_id") != self.run_id
                        or intent.get("page_id") != self.page_ids.get(page)
                    )
                    and intent.get("fact") == fact_for(question["question"])
                )
                for intent in self.verified_intents(job)
            ):
                raise PortalDataError(
                    "recovered_result_not_visible",
                    "已确认保存的结果在当前页面不可核验，请人工处理；不会重复保存。",
                    409,
                )
            route = self._fill_route(page, question)
            if route["executor"] != "manual":
                conflict = next(
                    (
                        previous["intent"]
                        for previous_job in [job, *history_jobs]
                        for previous in self.effective_action_results(previous_job).values()
                        if previous["conclusion"] != "current_matches"
                        and previous["intent"].get("action") == "fill"
                        and (
                            previous["intent"].get("fact") == fact_for(question["question"])
                            or question.get("draft_path")
                            and previous["intent"].get("draft_path") == question["draft_path"]
                            or previous["intent"].get("run_id") == self.run_id
                            and previous["intent"].get("page_id") == self.page_ids.get(page)
                            and previous["intent"].get("field_id") == question["id"]
                            or not previous["intent"].get("fact")
                            and not previous["intent"].get("draft_path")
                        )
                        and any(
                            previous["intent"].get(key) != route[key]
                            for key in ("executor", "input_route")
                        )
                    ),
                    None,
                )
                if conflict is not None:
                    route = {
                        "executor": "manual",
                        "input_route": None,
                        "route_reason": "route_change_forbidden",
                        "prior_intent_ref": conflict.get("attempt_id") or digest(conflict),
                    }
            if route["executor"] == "manual":
                self.update(
                    job,
                    batch_id,
                    status="needs_recheck",
                    reason=route["route_reason"],
                    observations=[
                        {
                            "action": "route_decision",
                            "stage": "fill",
                            "field_id": question["id"],
                            "answer_ref": deepcopy(ref),
                            "selected_executor": "manual",
                            "executor": None,
                            "route_reason": route["route_reason"],
                            "dispatch": "not_sent",
                            "dispatch_scope": "proposed_fill",
                            **(
                                {"prior_intent_ref": route["prior_intent_ref"]}
                                if "prior_intent_ref" in route
                                else {}
                            ),
                            "page_id": self.page_ids.get(page),
                            "run_id": self.run_id,
                            "at": time.time(),
                        }
                    ],
                )
                return
            dom_target = route.get("dom_target", "")
            use_cua = route["executor"] == "cua_driver"
            intent = {
                "action": "fill",
                "field_id": question["id"],
                "answer_ref": ref,
                "fact": fact_for(question["question"]),
                "draft_path": question.get("draft_path", ""),
                "before_value": deepcopy(question.get("value")),
                "expected_value": value,
                "field_type": question["type"],
                "expected_saved_value": expected_for(question, value),
                "field_shape": digest(
                    {
                        key: question.get(key)
                        for key in ("id", "type", "question", "options", "required")
                    }
                ),
                **{key: route[key] for key in ("executor", "input_route", "route_reason")},
            }
            if not self.authorize(job, batch_id, intent):
                return
            # Recheck the actual answer revision after preparing the intent.
            with self.store.applications.write_lock():
                fresh = self.store.resolve(question, job, self.temporary)
                if fresh is None or fresh[1] != ref:
                    return
            fresh_fields = self.observe(page, job)["fields"]
            current_question = next(q for q in fresh_fields if q["id"] == question["id"])
            shape = ("id", "type", "question", "options", "required", "max_length", "maxlength")
            if any(current_question.get(k) != question.get(k) for k in shape) or (
                self.live and select_fill_route(page, current_question, self.cua) != route
            ):
                raise PortalDataError("question_changed", "问题或选项已变更。", 409)
            if current_question.get("value") != question.get("value") or current_question.get(
                "valid"
            ) != question.get("valid"):
                raise PortalDataError("form_changed", "字段已被用户或网站修改，保留现场。", 409)
            fresh_observed = self.observe(page, job)
            if (
                fresh_observed["fields"] != fresh_fields
                or fresh_observed.get("document_token") != observed.get("document_token")
                or fresh_observed.get("user_activity", {}) != observed.get("user_activity", {})
                or fresh_observed.get("parser", {}).get("status") in {"active", "failed"}
            ):
                raise PortalDataError("form_changed", "解析或字段仍在变化，停止写入。", 409)
            field = page.locator("#" + question["id"]) if not self.live else None
            execution = {key: intent[key] for key in ("executor", "input_route", "route_reason")}
            with self.dispatch_current(job, batch_id, intent, observed=fresh_observed):
                if self.live:
                    if draft:
                        draft.begin(question, expected_for(question, value), intent)
                        if question["type"] in {
                            "text",
                            "email",
                            "tel",
                            "url",
                            "number",
                            "date",
                            "textarea",
                        }:
                            hosted_ats.control(page, question).focus()
                    if use_cua or dom_target:
                        if not dom_target and hosted_ats.control(page, question).is_editable():
                            raise PortalDataError("question_changed", "控件已变更。", 409)
                        original = hosted_ats.control(page, question).element_handle()
                        if original is None:
                            raise PortalDataError("question_changed", "控件已变更。", 409)

                        def check_control(
                            after_write=False,
                            value=value,
                            question=question,
                            ref=ref,
                            intent=intent,
                            shape=shape,
                            original=original,
                            dom_target=dom_target,
                        ):
                            with self.store.applications.write_lock():
                                state = self.store.load()
                                current = next(
                                    j for j in state["jobs"] if j["application_id"] == identifier
                                )
                                if (
                                    state["batch_id"] != batch_id
                                    or not self.permitted(state, page)
                                    or current["handed_off"]
                                    or current["status"] != "filling"
                                    or current["intent"] != intent
                                ):
                                    raise PortalDataError(
                                        "dom_action_invalidated"
                                        if dom_target
                                        else "cua_action_invalidated",
                                        "当前动作许可已失效。",
                                        409,
                                    )
                                self.check_inputs(current)
                                answer = self.store.resolve(question, current, self.temporary)
                                if answer is None or answer[1] != ref:
                                    raise PortalDataError("answer_changed", "答案已变更。", 409)
                            fresh = next(
                                q
                                for q in self.observe(page, job)["fields"]
                                if q["id"] == question["id"]
                            )
                            # Compare in the saved handle's main world. Reacquiring an
                            # ElementHandle adds a utility-to-main CDP adoption wait.
                            if (
                                dom_target
                                and readonly_combobox_target(page, fresh) != dom_target
                                or any(fresh.get(k) != question.get(k) for k in shape)
                                or fresh.get("value")
                                != (value if after_write else question.get("value"))
                                or fresh.get("valid")
                                != (True if after_write else question.get("valid"))
                            ) or not hosted_ats.control(page, fresh).evaluate_all(
                                "(nodes, original) => original.isConnected && "
                                "nodes.length === 1 && nodes[0] === original",
                                original,
                            ):
                                raise PortalDataError("question_changed", "控件已变更。", 409)

                        try:
                            if dom_target:
                                fill_readonly_combobox(
                                    page, original, value, dom_target, check=check_control
                                )
                                execution["input_route"] = "dom"
                            else:
                                execution.update(
                                    self.cua.fill(
                                        page, question, value, check=check_control, pump=self.pump
                                    )
                                )
                        finally:
                            original.dispose()
                    else:
                        hosted_ats.fill(page, question, value)
                    if draft:
                        if question["type"] in {
                            "text",
                            "email",
                            "tel",
                            "url",
                            "number",
                            "date",
                            "textarea",
                        }:
                            hosted_ats.control(page, question).blur()
                        draft.wait(page)
                elif question["type"] == "select":
                    field.select_option(label=value, timeout=3000)
                else:
                    field.fill(value, timeout=3000)
                # Finish this control's native change event before acknowledging
                # its readback; a later focus change must not impersonate a user edit.
                if question["type"] in {
                    "text",
                    "email",
                    "tel",
                    "url",
                    "number",
                    "date",
                    "textarea",
                }:
                    (hosted_ats.control(page, question) if self.live else field).blur()
            after = self.observe(page, job)
            actual = next(q for q in after["fields"] if q["id"] == question["id"])
            if actual["value"] != value or not actual["valid"]:
                raise PortalDataError("readback_failed", "字段回读不一致。", 409)
            adopted = form_flow.record_fill(
                self, job, batch_id, intent, actual, value, ref, execution, after
            )
            self.store.measurements.event(
                "action_result",
                stage=intent["action"],
                attempt_id=intent["attempt_id"],
                result="verified" if adopted else "late_readback",
                run_id=self.run_id,
                episode_id=job.get("measurement_id"),
                application_id=identifier,
            )
            return
        if missing:
            self.update(
                job,
                batch_id,
                questions=missing,
                status="needs_input",
                reason="missing_answers",
                intent=None,
            )
            return
        if job["form_state"].get("differences"):
            self.update(job, batch_id, status="needs_input", reason="form_differences")
            return
        if self.live and self.upload_supplement(page, job, batch_id, observed):
            return
        form_flow.check_ready(job, observed)
        self.finish_materials(page, job, batch_id, observed, [*resolved, *kept], expected_for)

    def finish_materials(
        self, page, job, batch_id, observed, resolved, expected_for, *, upload_only=False
    ):
        """Reuse the existing attachment transaction before filling or final handoff."""
        from .application_bound_materials import verify_original_page

        identifier = job["application_id"]
        form = None if self.live else form_for(job)
        draft = self.drafts.get(page)
        workable = self.workable.get(page)
        material_transition = (job.get("material_update") or {}).get("status") == "bound"
        replacement = (
            material_transition and job["material_update"].get("upload_mode") != "first_upload"
        )
        resolutions = latest_action_resolutions(job.get("action_resolutions", []))
        if self.live:
            file_field = next(
                (q for q in observed["fields"] if q["type"] == "file" and q["resume"]), None
            )
            if file_field is None:
                if upload_only:
                    return False
                if observed.get("navigation"):
                    self.advance(page, job, batch_id, observed)
                elif (
                    observed.get("stage")
                    and len(observed.get("retained_resume", [])) == 1
                    and observed["retained_resume"][0]["valid"]
                    and not observed["retained_resume"][0]["multiple"]
                    and observed["retained_resume"][0]["filename"] == job["filename"]
                    and observed["retained_resume"][0]["file_sha256"] == job["file_sha256"]
                    and any(
                        previous["action"] == "upload"
                        and not previous.get("material_id")
                        and previous.get("sha256") == job["file_sha256"]
                        and previous.get("run_id") == self.run_id
                        and previous.get("page_id") == self.page_ids.get(page)
                        for previous in self.verified_intents(job)
                    )
                ):
                    self.check_inputs(job)
                    self.update(job, batch_id, status="ready_for_review", reason="", intent=None)
                else:
                    raise PortalDataError(
                        "resume_control_missing", "当前页面尚无已核验的简历附件。", 409
                    )
                return True
            # A local file selection can survive a failed upload. Retry only after
            # explicit non-application and fresh server readback showing no attachment.
            retry_upload = (
                draft
                and draft.fields.get(file_field.get("draft_path"), {}).get("fieldValue") is None
                and not self.recovered_upload(job)
                and any(
                    row["conclusion"] == "not_applied"
                    and row["intent"]["action"] == "upload"
                    and row["intent"].get("sha256") == job["file_sha256"]
                    and row["intent"].get("draft_path") == file_field.get("draft_path")
                    for row in resolutions.values()
                )
            )
            if not file_field["filename"] or retry_upload or replacement:
                if self.recovered_upload(job) and not replacement:
                    raise PortalDataError(
                        "recovered_result_not_visible",
                        "已确认上传的附件在当前页面不可核验；不会重复上传。",
                        409,
                    )
                intent = {
                    "action": "upload",
                    "kind": "resume",
                    "field_id": file_field["id"],
                    "sha256": job["file_sha256"],
                    "draft_path": file_field.get("draft_path", ""),
                    **(
                        {"material_update_id": job["material_update"]["id"]}
                        if material_transition
                        else {}
                    ),
                    **(
                        {"replaces_sha256": job["material_update"]["old_sha256"]}
                        if replacement
                        else {}
                    ),
                }
                if not self.authorize(job, batch_id, intent):
                    return True
                raw = Path(job["file_path"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != job["file_sha256"]:
                    raise PortalDataError("file_changed", "简历内容版本已变更。", 409)
                self.upload_job = job
                try:
                    if material_transition:
                        verify_original_page(self, page, job, expected_intent=intent)
                        if workable and replacement:
                            self.workable[page] = workable = ResumeUpload(job)
                    if workable:
                        workable.job = job
                    if draft:
                        draft.begin(file_field, len(raw), intent)
                    if workable:
                        workable.begin(file_field, intent, page)
                    with self.dispatch_current(job, batch_id, intent, observed=observed):
                        hosted_ats.control(page, file_field).set_input_files(
                            {"name": job["filename"], "mimeType": "application/pdf", "buffer": raw}
                        )
                    if draft:
                        draft.wait(page)
                    if workable:
                        workable.wait(page)
                        remote = workable.readback(page)
                        with self.store.applications.write_lock():
                            latest = self.store.load()
                            current = next(
                                j for j in latest["jobs"] if j["application_id"] == identifier
                            )
                            if not self.permitted(latest, page) or current["intent"] != intent:
                                raise PortalDataError(
                                    "upload_result_unknown", "附件动作许可已变更，请人工核验。", 409
                                )
                            self.check_inputs(current)
                    if job["platform"] == "lever":
                        page.locator(".resume-upload-working").wait_for(
                            state="hidden", timeout=12000
                        )
                        if page.locator(".resume-upload-failure").is_visible():
                            raise PortalDataError(
                                "upload_result_unknown", "网站解析结果不明，请人工核验附件。", 409
                            )
                finally:
                    self.upload_job = None
                after = self.observe(page, job)
                if after.get("document_token") != observed.get("document_token"):
                    raise PortalDataError("upload_result_unknown", "上传期间原文档已变化。", 409)
                actual = next(q for q in after["fields"] if q["type"] == "file" and q["resume"])
                if actual["filename"] != job["filename"] or (
                    actual.get("file_sha256") and actual["file_sha256"] != job["file_sha256"]
                ):
                    raise PortalDataError(
                        "upload_result_unknown", "附件选择结果不明，请人工核验。", 409
                    )
                if material_transition:
                    replacement_receipt = deepcopy(job["material_update"]) | {
                        "status": "complete",
                        "upload_attempt_id": intent["attempt_id"],
                        "new_attachment": {
                            "field_id": actual["id"],
                            "draft_path": actual.get("draft_path", ""),
                            "sha256": job["file_sha256"],
                            "attempt_id": intent["attempt_id"],
                            **(
                                {
                                    "attachment_id": draft.files.get(
                                        actual.get("draft_path"), {}
                                    ).get("attachment_id")
                                }
                                if draft
                                else {}
                            ),
                            **({"handle": deepcopy(workable.handle)} if workable else {}),
                        },
                    }
                form_flow.note_activity(job, actual["id"], after)
                self.update(
                    job,
                    batch_id,
                    form_state=job.get("form_state", {}),
                    completed_intent=intent,
                    intent=None,
                    **({"material_update": replacement_receipt} if material_transition else {}),
                    observations=[
                        *job["observations"],
                        {
                            "action": "select_file",
                            "local_sha256": job["file_sha256"],
                            "verified": True,
                            "run_id": self.run_id,
                            "page_id": self.page_ids.get(page),
                            "at": time.time(),
                        },
                        *([remote] if workable else []),
                    ],
                )
                return True
            if file_field["filename"] != job["filename"]:
                raise PortalDataError("upload_mismatch", "页面附件与所选版本不符。", 409)
            selected_digest = file_field.get("file_sha256")
            if selected_digest:
                if selected_digest != job["file_sha256"]:
                    raise PortalDataError("upload_mismatch", "页面附件内容版本不符。", 409)
            elif not (
                any(
                    item.get("action") == "select_file"
                    and not item.get("material_id")
                    and item.get("local_sha256") == job["file_sha256"]
                    and item.get("run_id") == self.run_id
                    and item.get("page_id") == self.page_ids.get(page)
                    for item in job["observations"]
                )
                or draft
                and draft.uploaded
                and draft.linked
                and self.recovered_upload(job)
            ):
                raise PortalDataError("upload_result_unknown", "已有附件内容未核验。", 409)
            with self.store.applications.write_lock():
                self.check_inputs(
                    next(j for j in self.store.load()["jobs"] if j["application_id"] == identifier)
                )
            if workable:
                workable.attachment(page)
                if workable.remote_sha256 != job["file_sha256"] or not self.recovered_upload(job):
                    raise PortalDataError(
                        "upload_result_unknown", "远端附件内容未核验，请人工核验。", 409
                    )
            if upload_only:
                return False
            verified = draft.verify(observed, resolved, expected_for) if draft else None
            if observed.get("navigation"):
                self.advance(page, job, batch_id, observed)
                return True
            if any(
                material.get("origin") == "jd"
                and material.get("required")
                and not material.get("field_id")
                for material in job.get("materials", [])
            ):
                self.update(
                    job, batch_id, status="needs_input", reason="material_field_mapping_required"
                )
                return True
            self.update(
                job,
                batch_id,
                status="ready_for_review",
                reason="",
                intent=None,
                **({"observations": [*job["observations"], verified]} if verified else {}),
            )
            return True
        upload = observed["upload"]
        file_field = next((q for q in observed["fields"] if q["type"] == "file"), None)
        if file_field is None:
            raise PortalDataError("resume_control_missing", "未识别简历控件。", 409)
        if not (
            upload.get("state") == "complete"
            and upload.get("sha256") == job["file_sha256"]
            and upload.get("name") == job["filename"]
        ):
            if self.recovered_upload(job) and not replacement:
                raise PortalDataError(
                    "recovered_result_not_visible",
                    "已确认上传的附件在当前页面不可核验；不会重复上传。",
                    409,
                )
            if upload.get("state") not in {"empty", None} and not replacement:
                raise PortalDataError(
                    "upload_result_unknown", "附件结果需要核验，不能自动重传。", 409
                )
            intent = {
                "action": "upload",
                "sha256": job["file_sha256"],
                **(
                    {
                        "material_update_id": job["material_update"]["id"],
                        "replaces_sha256": job["material_update"]["old_sha256"],
                    }
                    if replacement
                    else {}
                ),
            }
            if not self.authorize(job, batch_id, intent):
                return True
            self.observe(page, job)
            raw = Path(job["file_path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != job["file_sha256"]:
                raise PortalDataError("file_changed", "简历内容版本已变更。", 409)
            with self.dispatch_current(job, batch_id, intent, observed=observed):
                page.locator("#" + file_field["id"]).set_input_files(
                    {"name": job["filename"], "mimeType": "application/pdf", "buffer": raw},
                    timeout=3000,
                )
            page.locator(form.upload_status + '[data-state="complete"]').wait_for(timeout=5000)
            after = self.observe(page, job)
            if after.get("document_token") != observed.get("document_token"):
                raise PortalDataError("upload_result_unknown", "上传期间原文档已变化。", 409)
            result = after["upload"]
            if result.get("sha256") != job["file_sha256"] or result.get("name") != job["filename"]:
                raise PortalDataError("upload_mismatch", "上传附件与所选版本不符。", 409)
            form_flow.note_activity(job, file_field["id"], after)
            self.update(
                job,
                batch_id,
                form_state=job.get("form_state", {}),
                intent=None,
                completed_intent=intent,
                **(
                    {
                        "material_update": deepcopy(job["material_update"])
                        | {"status": "complete", "upload_attempt_id": intent["attempt_id"]}
                    }
                    if replacement
                    else {}
                ),
            )
            return True
        if upload_only:
            return False
        # No button click, Enter, form submission or final HTTP action exists here.
        with self.store.applications.write_lock():
            self.check_inputs(
                next(j for j in self.store.load()["jobs"] if j["application_id"] == identifier)
            )
        self.update(job, batch_id, status="ready_for_review", reason="", intent=None)


# Seconds a stop request may wait for the current call before it is interrupted.
STOP_GRACE_SECONDS = 5
PARENT_POLL_SECONDS = 1


def main(argv: list[str] | None = None, *, expected_sources: dict | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent Lever / Greenhouse preview worker")
    parser.add_argument("--applications", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--single-flow-root", type=Path)
    parser.add_argument("--cover-letter-template", type=Path, help="Private letter template")
    parser.add_argument("--pdf-inspect", type=Path, help="Native PDFKit inspector executable")
    parser.add_argument("--package-resources", type=Path)
    parser.add_argument("--expected-package-manifest")
    parser.add_argument("--expected-worker-revision")
    parser.add_argument("--synthetic-browser", type=Path)
    parser.add_argument("--fixture-origin", default="")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--cdp-port", type=int, default=0)
    parser.add_argument("--cua", action="store_true", help="Use a hidden worker-owned Cua browser")
    parser.add_argument("--cua-click-route", choices=("trusted", "dom_event"), default="trusted")
    parser.add_argument("--native-assistance-policy", help="Trusted native handover policy JSON")
    parser.add_argument("--codex-assist-config", help="Trusted metadata-only adapter configuration")
    args = parser.parse_args(argv)
    if args.synthetic_browser is not None:
        from .application_worker_fixtures import browser_fixture_configuration

        try:
            browser_fixture_configuration(args.synthetic_browser)
            if (
                not (args.live and args.cua)
                or args.cua_click_route != "dom_event"
                or args.headless
                or args.cdp_port
                or args.fixture_origin
                or args.codex_assist_config is not None
                or args.native_assistance_policy is not None
                or args.applications != args.synthetic_browser / "applications"
                or args.runtime != args.synthetic_browser / "runtime/single-job-worker"
                or args.single_flow_root
                not in (None, args.synthetic_browser / "runtime/single-job-flow")
            ):
                raise ValueError("synthetic-browser-overrides")
        except (OSError, ValueError, TypeError):
            parser.error("Choose the exact isolated synthetic browser configuration.")
        os.environ.clear()
        os.environ.update(
            {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "en_US.UTF-8",
                "HOME": str(args.synthetic_browser / "home"),
                "TMPDIR": str(args.synthetic_browser / "tmp"),
                "TOMORROWSTAR_CODEX_EXECUTABLE": str(args.synthetic_browser / "codex-fixture"),
            }
        )
    if args.cua and (args.headless or args.cdp_port):
        parser.error("Cua requires a windowed browser and owns its CDP endpoint.")
    if not args.cua and args.cua_click_route != "trusted":
        parser.error("Cua click route requires --cua.")
    if args.live and (args.fixture_origin or args.headless):
        parser.error("Live filling requires a visible browser without fixtures.")
    if not args.live and not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", args.fixture_origin):
        parser.error("This preview accepts only its explicit loopback fixture origin.")
    native_policy = None
    if args.native_assistance_policy is not None:
        try:
            if len(args.native_assistance_policy) > 4096 or not (args.cua and args.live):
                raise ValueError("native handover requires the owned native browser")
            native_policy = validate_native_assistance_policy(
                json.loads(args.native_assistance_policy)
            )
        except (ValueError, TypeError):
            parser.error("Choose the reviewed native handover policy and owned browser.")
    assist_config = None
    if args.codex_assist_config is not None:
        try:
            if len(args.codex_assist_config) > 16384:
                raise ValueError("configuration too large")
            assist_config = CodexAssistConfig.from_dict(json.loads(args.codex_assist_config))
            if assist_config.native_assistance_policy != native_policy:
                raise ValueError("native policy mismatch")
            if assist_config.runtime != args.runtime.resolve() / "codex-assist":
                raise ValueError("runtime mismatch")
        except (OSError, ValueError, TypeError):
            parser.error("Choose the trusted metadata-only configuration for this worker.")
    if native_policy is not None and assist_config is None:
        parser.error("Native handover requires its trusted Codex Adapter configuration.")
    # Complete this executor's role before its one-time loaded-code measurement.
    from . import (  # noqa: F401
        application_bound_materials,
        application_cover_letter,
        application_experience_latex,
        application_materials,
        application_readiness,
        application_single_binding,
    )

    store = WorkerStore(ApplicationStore(args.applications), args.runtime, live=args.live)
    if args.cover_letter_template is not None:
        store.cover_letter_template = args.cover_letter_template.expanduser().absolute()
    if args.pdf_inspect is not None:
        if (
            args.pdf_inspect.is_absolute()
            and args.pdf_inspect.is_file()
            and os.access(args.pdf_inspect, os.X_OK)
        ):
            from .application_pdf import NativePDFInspector

            store.pdf_inspector = NativePDFInspector(args.pdf_inspect)
        else:
            # The private worker log keeps why; letters fall back to the regex check.
            print("pdf_inspect_ignored: not an absolute executable file", file=sys.stderr)
    if args.synthetic_browser is not None:
        from .application_worker_fixtures import browser_fixture_job_url

        state = store.load()
        config = browser_fixture_configuration(args.synthetic_browser)
        job_url = browser_fixture_job_url(config["scenario"])
        if not state.get("generic_enabled") or any(
            job["job_url"] != job_url or job["platform"] != "generic" for job in state["jobs"]
        ):
            parser.error("Synthetic browser records must contain only the fixed synthetic job.")
    descriptor = os.open(store.root / ".worker.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    previous_term = signal.getsignal(signal.SIGTERM)
    stop_requested, runner, looping = False, None, True
    codex_assist = escalation = None
    finished = threading.Event()
    if args.cua:

        def stop_cua(_signum, _frame):
            nonlocal stop_requested, looping, escalation
            if stop_requested:
                # The first request was not honoured in time: leave the stuck call so
                # the browser session still closes its driver and Chrome.
                if looping:
                    looping = False
                    raise KeyboardInterrupt("worker_stop_timeout")
                return
            stop_requested = True
            escalation = threading.Timer(STOP_GRACE_SECONDS, os.kill, (os.getpid(), signal.SIGTERM))
            escalation.daemon = True
            escalation.start()
            if runner is not None:
                runner.event("worker_stopped")
                # A dead Playwright driver leaves the current sync call spinning on
                # its finished dispatcher; only an exception can leave that call.
                fiber = getattr(getattr(runner, "context", None), "_dispatcher_fiber", None)
                if getattr(fiber, "dead", False):
                    looping = False
                    raise KeyboardInterrupt("playwright_dispatcher_dead")

        signal.signal(signal.SIGTERM, stop_cua)
    parent = os.getppid()

    def watch_parent():
        # An orphaned worker stops through its ordinary SIGTERM path.
        while not finished.wait(PARENT_POLL_SECONDS):
            if os.getppid() != parent:
                os.kill(os.getpid(), signal.SIGTERM)
                return

    threading.Thread(target=watch_parent, daemon=True).start()
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("worker_already_running", flush=True)
            return 3
        if assist_config is not None:
            codex_assist = CodexAdapter(assist_config)
        store.restore_single_context(args.single_flow_root)
        store.worker_lock_descriptor = descriptor
        initial = store.load()
        for job in initial["jobs"]:
            if (
                "current_job_id" not in initial
                or job["application_id"] == initial["current_job_id"]
            ):
                store.check_single(job, initial, material_required=False)
        start_run(store, expected_sources=expected_sources)

        # Only the executing worker can describe the code it has actually loaded.
        load_worker_modules()
        with store.applications.write_lock():
            state = store.load()
            state["runtime"]["loaded_engine_revision"] = loaded_runtime_revision("worker")
            state["runtime"]["capabilities"].append(CONTROLLER_HANDOFF_INSPECTION)
            store.save(state)
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        with sync_playwright() as playwright, ExitStack() as stack:
            arguments = [f"--remote-debugging-port={args.cdp_port}"] if args.cdp_port else []
            cua = None
            with store.measurements.stage("runtime_start", batch_id=store.load()["batch_id"]):
                if args.cua:
                    context, cua = stack.enter_context(
                        managed_cua_browser(
                            playwright,
                            store.root,
                            click_route=args.cua_click_route,
                            synthetic_keychain=args.synthetic_browser is not None,
                            **({"native_handoff": True} if native_policy is not None else {}),
                            origins=[
                                args.fixture_origin,
                                *(j["job_url"] for j in store.load()["jobs"]),
                            ],
                        )
                    )
                else:
                    context = playwright.chromium.launch_persistent_context(
                        str(store.root / "browser-profile"),
                        headless=args.headless,
                        args=arguments,
                        service_workers="block",
                        timeout=15000,
                    )
            if args.synthetic_browser is not None:
                from .application_worker_fixtures import isolate_browser_fixture

                context.set_offline(True)
                isolate_browser_fixture(context)
            if codex_assist is not None:
                stack.callback(codex_assist.close)
            context.set_default_timeout(4000)
            with browser_deadline(5):
                for blank in context.pages:
                    if cua is None and blank.url == "about:blank":
                        blank.close()
                runner = ApplicationRunner(
                    store,
                    context,
                    args.fixture_origin,
                    cua=cua,
                    **(
                        {"native_assistance_policy": native_policy}
                        if native_policy is not None
                        else {}
                    ),
                )
                runner.codex_assist = codex_assist
                if args.synthetic_browser is not None:
                    from .application_worker_fixtures import install_browser_fixture

                    install_browser_fixture(context, runner, args.synthetic_browser)
            next_login_save, login_seen = 0.0, None
            while not stop_requested:
                runner.tick()
                # Context waiting pumps native events without depending on the first Page.
                runner.pump()
                if cua is not None and time.monotonic() >= next_login_save:
                    # Keep a login made on the worker's page for later runs.
                    with suppress(Error, OSError, ValueError):
                        login_seen = sync_login_state(store.root, context, login_seen)
                    next_login_save = time.monotonic() + 10
            looping = False
            with store.applications.write_lock():
                state = store.load()
                state.update(control="paused", worker_error="worker_stopped")
                store.save(state)
    except (
        Error,
        OSError,
        StoreError,
        ValueError,
        PortalDataError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as exc:
        if isinstance(exc, StoreError):
            store.block_storage()
        with (
            suppress(OSError, StoreError, PortalDataError, ValueError),
            store.applications.write_lock(),
        ):
            state = store.load()
            state.update(control="paused", worker_error=type(exc).__name__)
            store.save(state)
        print("worker_stopped: " + type(exc).__name__, flush=True)
        # This stream is retained only in the explicitly selected private runtime directory.
        print(str(exc), flush=True)
        return 2
    finally:
        finished.set()
        if escalation is not None:
            escalation.cancel()
        if codex_assist is not None:
            codex_assist.close()
        if args.cua:
            signal.signal(signal.SIGTERM, previous_term)
        os.close(descriptor)


class TimestampedLines(io.TextIOBase):
    """Prefix each line this process writes to worker.log with its UTC time.

    The private log had no time of its own (2026-11-04: a 6.2 s gap could only be
    inferred from receipts); the message after the prefix is unchanged.
    """

    def __init__(self, stream):
        self._stream = stream
        self._line_start = True
        self._lock = threading.Lock()

    def write(self, text):
        with self._lock:
            parts = []
            for piece in text.splitlines(keepends=True):
                if self._line_start:
                    stamp = datetime.now(UTC).isoformat(timespec="milliseconds")
                    parts.append(stamp.replace("+00:00", "Z") + " ")
                parts.append(piece)
                self._line_start = piece.endswith(("\n", "\r"))
            self._stream.write("".join(parts))
        return len(text)

    def flush(self):
        self._stream.flush()

    def writable(self):
        return True

    def fileno(self):
        return self._stream.fileno()

    @property
    def encoding(self):
        return self._stream.encoding


def timestamp_log_lines():
    """Install the line prefix on this Worker process's stdout and stderr."""
    if not isinstance(sys.stdout, TimestampedLines):
        sys.stdout = TimestampedLines(sys.stdout)
    if not isinstance(sys.stderr, TimestampedLines):
        sys.stderr = TimestampedLines(sys.stderr)


if __name__ == "__main__":
    timestamp_log_lines()
    raise SystemExit(main())
