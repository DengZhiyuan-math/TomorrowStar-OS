"""Application-local form observations and choices on the retained ATS page."""

import time
from copy import deepcopy

from . import application_form_state as forms
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest


def _matches_readback(field, record):
    if not forms.equivalent(field, field.get("value"), record.get("value")):
        return False
    if field.get("type") == "file" or record.get("type") == "file":
        return field.get("type") == record.get("type") and all(
            field.get(key) == record.get(key) for key in ("filename", "file_sha256", "draft_path")
        )
    return True


def capture(runner, page, job, batch_id, observed, *, acknowledge=False, current_state=None):
    """Save the baseline and sample stability without sleeping.

    A command that owns a locked, loaded state passes that same object so its
    later save retains transport events and unknown results captured here.
    """
    binding = {
        "run_id": runner.run_id,
        "page_id": runner.page_ids.get(page),
        "step": observed.get("stage") or getattr(page, "url", job.get("job_url")),
        "document_token": observed.get("document_token"),
    }
    with runner.store.applications.write_lock():
        state = runner.store.load() if current_state is None else current_state
        current = next(
            row for row in state["jobs"] if row["application_id"] == job["application_id"]
        )
        if (
            state["batch_id"] != batch_id
            or current.get("status") == "cancelled"
            or state.get("current_job_id", job["application_id"]) != job["application_id"]
            or (state.get("runtime") or {}).get("id") != runner.run_id
            or runner.pages.get(job["application_id"]) is not page
        ):
            raise PortalDataError("current_job_changed", "当前申请已变化，保留现场。", 409)
        previous = current.get("form_state") or {}
        sampling = deepcopy(previous)
        if acknowledge and sampling:
            sampling.setdefault("parser_history", []).append(deepcopy(sampling.get("parser", {})))
            sampling["parser"] = {}
        result = forms.sample(sampling, observed, binding=binding, now=time.time())
        if previous and previous.get("binding") != binding:
            current.setdefault("form_history", []).append(deepcopy(previous))
            job["form_history"] = deepcopy(current["form_history"])
        old_fields = {
            field["id"]: field for field in previous.get("snapshot", {}).get("fields", [])
        }
        pending = current.get("intent") or {}
        matching_pending = set()
        if (
            pending.get("form_protocol") == "form-state/v1"
            and pending.get("form_binding") == binding
            and pending.get("action") == "fill"
        ):
            for field in observed["fields"]:
                if (
                    field["id"] == pending.get("field_id")
                    and field.get("valid")
                    and forms.equivalent(field, field.get("value"), pending.get("expected_value"))
                    and pending.get("field_shape")
                    == digest(
                        {
                            key: field.get(key)
                            for key in ("id", "type", "question", "options", "required")
                        }
                    )
                ):
                    matching_pending.add(field["id"])
        observed_changes = []
        confirmed_own = set()
        written = result.get("written_fields", {})
        for field in observed["fields"]:
            own = written.get(field["id"])
            if own and own.get("readback_pending"):
                own["readback_pending"] = False
                if _matches_readback(field, own):
                    confirmed_own.add(field["id"])
            old = old_fields.get(field["id"])
            keys = ("value", "filename", "file_sha256", "valid")
            if old is not None and any(old.get(key) != field.get(key) for key in keys):
                observed_changes.append(
                    {
                        "field_id": field["id"],
                        "before": {key: old.get(key) for key in keys},
                        "after": {key: field.get(key) for key in keys},
                        "confirmed_own_readback": field["id"] in confirmed_own,
                    }
                )
        if observed_changes:
            result.setdefault("value_history", []).append(
                {"fields": observed_changes, "at": time.time()}
            )
        unexpected = []
        if (
            previous.get("binding") == binding
            and previous.get("parser", {}).get("status") == "stable"
        ):
            written = result.get("written_fields", {})
            for field in observed["fields"]:
                old = old_fields.get(field["id"])
                own = written.get(field["id"])
                if (
                    old is None
                    or field["id"] in matching_pending
                    or _matches_readback(field, own if own is not None else old)
                ):
                    continue
                unexpected.append(
                    {
                        "field_id": field["id"],
                        "before": old.get("value"),
                        "after": field.get("value"),
                    }
                )
        activity = observed.get("user_activity", {})
        previous_activity = previous.get("snapshot", {}).get("user_activity", {})
        acknowledgements = result.get("ack_activity", {})
        trusted_changes = [
            key
            for key, sequence in activity.items()
            if sequence > previous_activity.get(key, 0)
            and sequence != acknowledgements.get(key)
            and key not in matching_pending
        ]
        if trusted_changes and previous.get("binding") == binding:
            result.setdefault("change_history", []).append(
                {"trusted_fields": trusted_changes, "at": time.time()}
            )
            result["intervention_pending"] = True
        if unexpected:
            result.setdefault("change_history", []).append(
                {"fields": unexpected, "at": time.time()}
            )
            result["intervention_pending"] = True
        changed_ids = (
            set(trusted_changes)
            | {row["field_id"] for row in unexpected}
            | {
                row["field_id"]
                for row in observed_changes
                if not row["confirmed_own_readback"] and row["field_id"] not in matching_pending
            }
        )
        for choice in result.get("choices", {}).values():
            if choice.get("field_id") in changed_ids:
                choice.update(expired=True, expired_at=time.time())
        if acknowledge:
            result["intervention_pending"] = False
        current["form_state"] = result
        job["form_state"] = deepcopy(result)
        runner.persist(state)
    return result


def bind_page(runner, page, job, batch_id):
    """Bind an original page whose first read found no supported form (decided 2026-10-31).

    A takeover starts only from a saved binding; without one, a listing page or an
    unsupported platform stopped the job with nothing to take over from.
    """
    from .application_bound_materials import document_token

    current = next(
        row for row in runner.store.load()["jobs"] if row["application_id"] == job["application_id"]
    )
    bound = (current.get("form_state") or {}).get("binding") or {}
    if bound.get("run_id") == runner.run_id and bound.get("page_id") == runner.page_ids.get(page):
        return
    capture(runner, page, job, batch_id, {"fields": [], "document_token": document_token(page)})


def choice_for(form, field, proposed, reference):
    """A choice applies only to its field, source proposal and observed value."""
    for choice in reversed(list(form.get("choices", {}).values())):
        if (
            choice.get("expired")
            or choice.get("field_id") != field["id"]
            or choice.get("binding") != form["binding"]
        ):
            continue
        if proposed != choice.get("proposed_value") or reference != choice.get("source"):
            continue
        if forms.equivalent(field, field.get("value"), choice.get("value")):
            return "keep", choice["value"]
        if not choice.get("applied") and field.get("value") == choice.get("current_value"):
            return ("keep" if choice["action"] == "keep" else "fill"), choice["value"]
    return None


def plan(job, observed, answers, *, retry_intents=()):
    """Protect all existing values; collect substantive differences in one list."""
    form = job["form_state"]
    baseline = form.get("baseline", {})
    differences, fills, kept = [], [], []
    for field, proposed, reference in answers:
        choice = choice_for(form, field, proposed, reference)
        written = form.get("written_fields", {}).get(field["id"])
        mode = (
            choice[0]
            if choice
            else "keep"
            if written
            and forms.equivalent(field, field.get("value"), written["value"])
            and forms.equivalent(field, proposed, written["value"])
            else "difference"
            if written
            else forms.decision(
                {
                    **field,
                    "parser_completed": form.get("parser", {}).get("observed_status") == "complete",
                },
                proposed,
                baseline=baseline.get(field["id"]),
            )
        )
        if (
            mode == "keep"
            and proposed not in (None, "", [])
            and choice is None
            and written is None
            and not job.get("intent")
            and not form.get("intervention_pending")
            and form.get("parser", {}).get("status") == "stable"
            and isinstance(form["binding"].get("document_token"), str)
            and bool(form["binding"]["document_token"])
            and all(
                isinstance(form["binding"].get(key), str) and bool(form["binding"][key])
                for key in ("run_id", "page_id")
            )
            and isinstance(reference, dict)
            and all(
                isinstance(reference.get(key), str) and bool(reference[key])
                for key in ("key", "revision")
            )
            and any(
                intent.get("action") == "fill"
                and intent.get("form_protocol") == "form-state/v1"
                and intent.get("form_binding") == form["binding"]
                and intent.get("run_id") == form["binding"].get("run_id")
                and intent.get("page_id") == form["binding"].get("page_id")
                and intent.get("field_id") == field["id"]
                and intent.get("field_type") == field["type"]
                and intent.get("field_shape")
                == digest(
                    {
                        key: field.get(key)
                        for key in ("id", "type", "question", "options", "required")
                    }
                )
                and "before_value" in intent
                and intent["before_value"] in (None, "", [])
                and "expected_value" in intent
                and intent.get("expected_value") == proposed == field.get("value")
                and intent.get("answer_ref") == reference
                for intent in retry_intents
            )
        ):
            # A known unsaved write may save its unchanged own value again.
            # No other nonempty value inherits permission from that attempt.
            mode = "fill"
        if mode == "fill":
            fills.append((field, choice[1] if choice else proposed, reference))
        elif mode == "keep":
            if choice:
                form.get("written_fields", {}).pop(field["id"], None)
            kept.append((field, field.get("value"), reference))
        else:
            detail = {
                "field_id": field["id"],
                "question": field["question"],
                "current_value": field.get("value"),
                "proposed_value": proposed,
                "baseline_value": (baseline.get(field["id"]) or {}).get("value"),
                "source": deepcopy(reference),
                "important": True,
                "reason": "protected_value_changed"
                if baseline.get(field["id"], {}).get("value") not in (None, "", [])
                and not forms.equivalent(
                    field, field.get("value"), baseline[field["id"]].get("value")
                )
                else "nonempty_difference",
            }
            detail["id"] = digest({"binding": form["binding"], **detail})
            differences.append(detail)
    form["differences"] = differences
    return fills, kept


def save_plan(runner, job, batch_id):
    with runner.store.applications.write_lock():
        state = runner.store.load()
        current = next(
            row for row in state["jobs"] if row["application_id"] == job["application_id"]
        )
        if (
            state["batch_id"] != batch_id
            or current.get("status") == "cancelled"
            or state.get("current_job_id", job["application_id"]) != job["application_id"]
            or (state.get("runtime") or {}).get("id") != runner.run_id
        ):
            raise PortalDataError("current_job_changed", "当前申请已变化。", 409)
        latest = current.get("form_state") or {}
        if any(
            latest.get(key) != job["form_state"].get(key)
            for key in ("snapshot_sha256", "binding", "revision")
        ):
            raise PortalDataError("form_changed", "表单现场已变化，请重新读取。", 409)
        latest["differences"] = deepcopy(job["form_state"]["differences"])
        latest["written_fields"] = deepcopy(job["form_state"].get("written_fields", {}))
        job["form_state"] = deepcopy(latest)
        runner.persist(state)


def note_write(job, field, value, reference, *, observed=None):
    for choice in job.get("form_state", {}).get("choices", {}).values():
        if (
            not choice.get("expired")
            and choice.get("field_id") == field["id"]
            and choice.get("value") == value
        ):
            choice.update(applied=True, applied_at=time.time())
    if observed is not None:
        note_activity(job, field["id"], observed)
    job.setdefault("form_state", {}).setdefault("written_fields", {})[field["id"]] = {
        "value": value,
        "readback_pending": True,
        "source": deepcopy(reference),
        "at": time.time(),
        **(
            {
                key: deepcopy(field.get(key))
                for key in ("type", "filename", "file_sha256", "draft_path")
            }
            if field.get("type") == "file"
            else {}
        ),
    }


def check_ready(job, observed):
    form = job.get("form_state") or {}
    if job.get("intent"):
        raise PortalDataError("action_result_unknown", "仍有未核对的动作。", 409)
    if form.get("parser", {}).get("status") != "stable" or form.get("intervention_pending"):
        raise PortalDataError("parser_unstable", "解析或人工修改仍需核对。", 409)
    if observed.get("validation_errors") or any(
        (field.get("required") or field.get("value") or field.get("filename"))
        and not field.get("valid")
        for field in observed["fields"]
    ):
        raise PortalDataError("form_validation_errors", "网站仍有必填或校验错误。", 409)
    if any(item.get("important") for item in form.get("differences", [])):
        raise PortalDataError("form_differences", "请集中选择当前申请的字段差异。", 409)


def inspect_pending(runner, page, job, observed):
    """Classify an existing attempt; no browser send, page creation or retry."""
    intent = job.get("intent") or {}
    binding = intent.get("form_binding") or {}
    navigation = intent.get("navigation") or {}
    reached_document = (
        intent.get("action") == "advance"
        and navigation.get("to_step", "").startswith("https://")
        and getattr(page, "url", None) == navigation["to_step"]
    )
    if (
        intent.get("form_protocol") != "form-state/v1"
        or intent.get("run_id") != runner.run_id
        or intent.get("page_id") != runner.page_ids.get(page)
        or not isinstance(binding.get("document_token"), str)
        or not binding["document_token"]
        or not reached_document
        and binding["document_token"] != observed.get("document_token")
        or binding.get("step")
        != (observed.get("stage") or getattr(page, "url", job.get("job_url")))
        and intent.get("action") != "advance"
    ):
        return "unknown"
    conclusion = "unknown"
    if intent["action"] == "fill":
        field = next(
            (row for row in observed["fields"] if row["id"] == intent.get("field_id")), None
        )
        if (
            field is not None
            and field.get("type") == intent.get("field_type")
            and (
                intent.get("field_shape")
                == digest(
                    {
                        key: field.get(key)
                        for key in ("id", "type", "question", "options", "required")
                    }
                )
            )
        ):
            draft = runner.drafts.get(page)
            saved = not draft or draft.saved(
                field, intent.get("expected_saved_value", intent.get("expected_value"))
            )
            if (
                forms.equivalent(field, field.get("value"), intent.get("expected_value"))
                and field.get("valid")
                and saved
            ):
                conclusion = "current_matches"
                note_write(
                    job, field, field.get("value"), intent.get("answer_ref"), observed=observed
                )
            elif (
                field.get("value") == intent.get("before_value")
                and intent.get("dispatch_state") == "prepared"
            ):
                conclusion = "not_applied"
            elif field.get("value") not in (
                intent.get("before_value"),
                intent.get("expected_value"),
            ):
                conclusion = "third_value"
    elif intent["action"] == "upload":
        is_resume = not intent.get("material_id") and intent.get("kind", "resume") == "resume"
        candidates = list(observed["fields"])
        if is_resume:
            candidates += [
                {"type": "file", "resume": True, **row}
                for row in observed.get("retained_resume", [])
            ]
        actual = [
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
                and is_resume
                and row.get("resume", True)
            )
        ]
        upload = observed.get("upload") or {}
        target_matches = len(actual) == 1 and actual[0].get("file_sha256") == intent.get("sha256")
        draft = runner.drafts.get(page)
        if draft:
            material = (
                next(
                    (
                        row
                        for row in job.get("materials", [])
                        if row.get("id") == intent.get("material_id")
                    ),
                    None,
                )
                if not is_resume
                else {"filename": job.get("filename"), "sha256": intent.get("sha256")}
            )
            target_matches = bool(
                len(actual) == 1 and material and draft.file_verified(actual[0], material)
            )
        workable = getattr(runner, "workable", {}).get(page)
        if workable and is_resume:
            workable.attachment(page)
            target_matches = workable.remote_sha256 == intent.get("sha256")
        if target_matches or (
            is_resume
            and upload.get("state") == "complete"
            and upload.get("sha256") == intent.get("sha256")
        ):
            conclusion = "current_matches"
        elif intent.get("dispatch_state") == "prepared" and digest(actual) == intent.get(
            "before_attachments_sha256"
        ):
            conclusion = "not_applied"
    elif intent["action"] == "advance":
        target = intent.get("navigation", {}).get("to_step")
        if target and (observed.get("stage") == target or page.url == target):
            conclusion = "current_matches"
        elif intent.get("dispatch_state") == "prepared" and observed.get(
            "navigation"
        ) == intent.get("navigation"):
            conclusion = "not_applied"
    record = {
        "intent_ref": intent.get("attempt_id") or digest(intent),
        "intent": deepcopy(intent),
        "conclusion": conclusion,
        "source": "retained_original_page",
        "verified_by": "system_observation",
        "observation_count": len(job["observations"]),
        "at": time.time(),
        "run_id": runner.run_id,
    }
    prior = job.setdefault("pending_action_observations", [])
    if not prior or any(
        prior[-1].get(key) != record.get(key) for key in ("intent_ref", "conclusion")
    ):
        prior.append(record)
    if conclusion in {"current_matches", "not_applied"}:
        job.setdefault("action_resolutions", []).append(record)
        job["intent"] = None
    elif conclusion == "third_value":
        difference = {
            "field_id": field["id"],
            "question": field["question"],
            "intent_ref": record["intent_ref"],
            "baseline_value": intent.get("before_value"),
            "proposed_value": intent.get("expected_value"),
            "current_value": field.get("value"),
            "source": deepcopy(intent.get("answer_ref", {"source": "unknown"})),
            "reason": "action_third_value",
            "important": True,
        }
        difference["id"] = digest({"binding": job["form_state"]["binding"], **difference})
        job["form_state"]["pending_action_difference"] = difference
        job["form_state"]["differences"] = [difference]
        draft = runner.drafts.get(page)
        if (
            intent.get("dispatch_state") in {"prepared", "returned"}
            and job["form_state"]["parser"]["status"] == "stable"
            and not (draft and (draft.active or draft.pending))
        ):
            job.setdefault("action_resolutions", []).append({**record, "conclusion": "superseded"})
            job["intent"] = None
    return conclusion


def check_snapshot(runner, page, job, before):
    """Re-read all protected values and attachments immediately before a send."""
    after = runner.observe(page, job)
    if any(
        after.get(key) != before.get(key)
        for key in ("fields", "retained_resume", "upload", "document_token", "user_activity")
    ) or after.get("parser", {}).get("status") in {"active", "failed"}:
        raise PortalDataError("form_changed", "字段、附件或解析已变化，停止当前写入。", 409)
    return after


def note_activity(job, field_id, observed):
    """Acknowledge only the events on the control whose own write was read back."""
    activity = observed.get("user_activity", {})
    if field_id in activity:
        job.setdefault("form_state", {}).setdefault("ack_activity", {})[field_id] = activity[
            field_id
        ]


def record_fill(runner, job, batch_id, intent, actual, value, reference, execution, observed):
    """Keep late readback history without endorsing a successor form or attempt."""
    page = runner.pages.get(job["application_id"])
    with runner.store.applications.write_lock():
        state = runner.store.load()
        if state["batch_id"] != batch_id:
            return False
        current = next(
            row for row in state["jobs"] if row["application_id"] == job["application_id"]
        )
        binding = intent.get("form_binding")
        adopted = bool(
            current.get("intent") == intent
            and current["status"] == "filling"
            and not current.get("handed_off")
            and state.get("current_job_id", job["application_id"]) == job["application_id"]
            and (state.get("runtime") or {}).get("id") == runner.run_id
            and runner.page_ids.get(page) == intent.get("page_id")
            and current.get("form_state", {}).get("binding") == binding
            and binding
            and binding.get("document_token") == observed.get("document_token")
            and runner.permitted(state, page)
        )
        event = {
            "action": "fill" if adopted else "late_fill_result",
            "field_id": actual["id"],
            "intent": deepcopy(intent),
            "value": value,
            "adopted": adopted,
            "document_token": observed.get("document_token"),
            **execution,
            "at": time.time(),
            "run_id": runner.run_id,
        }
        if adopted:
            current["answer_refs"] = [
                row for row in current["answer_refs"] if row["field_id"] != actual["id"]
            ]
            current["answer_refs"].append({**reference, "field_id": actual["id"]})
            note_write(current, actual, value, reference, observed=observed)
            event["verified"] = True
            current["intent"] = None
        current["observations"].append(event)
        runner.persist(state)
        runner.work_progressed = adopted
        return adopted
