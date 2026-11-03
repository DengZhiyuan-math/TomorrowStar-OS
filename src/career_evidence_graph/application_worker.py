"""Private, file-backed control shared by Lever and Greenhouse."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import logging
import math
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import nullcontext, suppress
from copy import deepcopy
from pathlib import Path
from urllib.parse import urldefrag
from uuid import uuid4

from . import application_takeover_record as takeover_record
from ._vendor import job_apply_store as helper
from .application_automation import (
    _job_identity,
    validate_application_target,
)
from .application_execution import (
    automated_owner,
    reject_mixed_execution_root,
    release_execution,
    require_execution,
    reserve_execution,
)
from .application_information import COUNTRIES, fact_for, scope_matches
from .application_page_scope import PAGE_SCOPE
from .application_storage import private_root
from .application_takeover_budget import DEFAULT_BUDGET
from .application_takeover_record import (  # noqa: F401 - the record's names stay importable here
    ASSISTANCE_CONTROL_REASONS,
    ASSISTANCE_HISTORY_LIMIT,
    ASSISTANCE_REPORT,
    TAKEOVER_CODES,
    TAKEOVER_REASONS,
    TAKEOVER_ROUTE_REASONS,
    TAKEOVER_UNKNOWN_REASONS,
    archive_stopped_assistance,
    assistance_stop_pending,
    record_takeover_failure,
    revoke_assistance,
    valid_assistance_report,
    valid_assistance_stop,
    valid_takeover_dispatch,
)
from .application_takeover_record import bounded_text as _bounded_text
from .application_takeover_record import canonical_sha256 as _canonical_sha256
from .application_takeover_record import takeover_slot as _takeover_slot
from .application_takeover_record import valid_takeover_blocker as _valid_takeover_blocker
from .application_takeover_record import valid_timestamp as _timestamp
from .career_portal_data import ApplicationStore, PortalDataError
from .job_screening import LEVELS, screen_applications
from .validation.hashing import record_digest as digest
from .worker_measurement import MeasurementLog
from .worker_process_identity import process_identity, valid_process_identity

PUBLIC_ROOT = Path(__file__).resolve().parents[2]
HELPER_SHA256 = "aeff412145497a87929c04b712a2f87bf4521256c67c98f6b4bc0271c5655d03"
STATUSES = {"queued", "filling", "needs_input", "needs_recheck", "ready_for_review", "cancelled"}
OWNED_PAGE_OBSERVATION = "owned-page-observation/v1"
CONTROLLER_HANDOFF_INSPECTION = "controller-handoff-inspection/v1"
CODEX_ASSISTANCE = "codex-assistance/v1"
CODEX_NATIVE_ASSISTANCE = "codex-assistance/native/v1"
MATERIAL_COMMIT_FIELDS = (
    "single_binding",
    "file_path",
    "file_sha256",
    "filename",
    "material_update",
)
CODEX_BACKEND_AUTHORITY = "codex-backend-authority/v1"
ASSISTANCE_OUTCOME = "assistance-outcome/v1"


def script_writes_allowed(state, application_id=None):
    """A reserved assistance writer never inherits the script's browser authority."""
    selected = application_id or state.get("current_job_id")
    return all(
        "assistance" not in job or job["assistance"].get("active_writer") == "script"
        for job in state["jobs"]
        if selected is None or job["application_id"] == selected
    )


def assistance_reference(assistance):
    return (
        {
            key: deepcopy(assistance[key])
            for key in ("id", "generation", "binding", "page_writes_enabled")
        }
        | (
            {"backend_authority": deepcopy(assistance["backend_authority"])}
            if "backend_authority" in assistance
            else {}
        )
        | (
            {
                "protocol": CODEX_NATIVE_ASSISTANCE,
                "native_policy_digest": assistance["native_policy_digest"],
            }
            if assistance.get("protocol") == CODEX_NATIVE_ASSISTANCE
            else {}
        )
    )


def validate_native_assistance_policy(value):
    """Use the native host's reviewed policy; never create a session grant."""
    from .cua_driver import validate_native_assistance_policy as validate_native_policy

    return validate_native_policy(value)


def validate_native_assistance_scope(value, expected_ref):
    """Validate host-attested metadata, never create or transfer a native grant."""
    if (
        not isinstance(expected_ref, dict)
        or expected_ref.get("protocol") != CODEX_NATIVE_ASSISTANCE
        or not isinstance(value, dict)
        or set(value)
        != {
            "target_id",
            "tab_id",
            "cdp_target_id",
            "binding_generation",
            "tab_generation",
            "process_fingerprint",
            "process_identity",
            "application_ref_digest",
        }
        or any(
            not isinstance(value[k], str) or not value[k] or len(value[k]) > 4000
            for k in ("target_id", "tab_id", "cdp_target_id")
        )
        or any(
            type(value[k]) is not int or not 0 <= value[k] < 2**64
            for k in ("binding_generation", "tab_generation")
        )
        or not valid_process_identity(value["process_identity"])
        or value["application_ref_digest"] != digest(expected_ref)
    ):
        raise ValueError("Invalid native original-page scope")
    native = value["process_fingerprint"]
    kernel = value["process_identity"]
    if (
        not isinstance(native, dict)
        or set(native) != {"pid", "start_time", "executable"}
        or type(native["pid"]) is not int
        or native["pid"] != kernel["pid"]
        or native["start_time"] is not None
        and (type(native["start_time"]) is not int or not 0 <= native["start_time"] < 2**64)
        or native["executable"] is not None
        and native["executable"] != kernel["executable"]
    ):
        raise ValueError("Native browser process identity changed")


def _validate_assistance_page_context(value, expected_ref):
    if not isinstance(value, dict) or set(value) - {
        "status",
        "at",
        "observed_at",
        "data",
        "document",
        "binding",
        "worker_source",
        "page_writes_enabled",
        "executor",
        "owner",
    } - ({"native_scope"} if expected_ref.get("protocol") == CODEX_NATIVE_ASSISTANCE else set()):
        raise ValueError("Invalid original-page JSON context")
    if "native_scope" in value:
        validate_native_assistance_scope(value["native_scope"], expected_ref)
    binding = expected_ref.get("binding") or {}
    document = value.get("document")
    data = value.get("data")
    if (
        value.get("status") != "captured"
        or value.get("binding") != binding
        or value.get("page_writes_enabled") is not False
        or not isinstance(document, dict)
        or set(document) != {"frame_id", "loader_id", "url"}
        or any(not isinstance(document[k], str) or not document[k] for k in document)
        or urldefrag(document["url"])[0] != urldefrag(binding.get("step", ""))[0]
        or not isinstance(data, dict)
        or data.get("url") != binding.get("step")
        or not isinstance(data.get("fields"), list)
        or len(data["fields"]) > 500
        or any(not isinstance(row, dict) for row in data["fields"])
        or not isinstance(data.get("attachments", []), list)
        or len(data.get("attachments", [])) > 100
        or not isinstance(value.get("worker_source"), str)
        or re.fullmatch(r"[a-f0-9]{64}", value["worker_source"]) is None
    ):
        raise ValueError("Original-page JSON context binding changed")
    if set(data) - {
        "url",
        "title",
        "fields",
        "attachments",
        "validation_errors",
        "remote_save_verified",
    } or any(
        set(row)
        - {
            "id",
            "name",
            "type",
            "role",
            "label",
            "value",
            "redacted",
            "required",
            "disabled",
            "readonly",
            "valid",
            "aria_invalid",
            "visible",
            "files",
            "locator_hint",
            "material_target",
            "question",
        }
        for row in data["fields"]
    ):
        raise ValueError("Unexpected original-page JSON content")
    if not isinstance(data.get("title", ""), str) or len(data.get("title", "")) > 1000:
        raise ValueError("Invalid original-page title")
    for field in data["fields"]:
        if "material_target" in field:
            from .cua_driver import validate_native_material_target

            validate_native_material_target(field["material_target"])
        if any(
            not isinstance(field[k], str) or len(field[k]) > 4000
            for k in ("id", "name", "type", "role", "label", "value", "question")
            if k in field
        ):
            raise ValueError("Invalid original-page field text")
        if any(
            type(field[k]) is not bool
            for k in ("redacted", "required", "disabled", "readonly", "visible")
            if k in field
        ):
            raise ValueError("Invalid original-page field flag")
        if "valid" in field and field["valid"] is not None and type(field["valid"]) is not bool:
            raise ValueError("Invalid original-page validity")
        hint = field.get("locator_hint")
        if hint is not None and (
            not isinstance(hint, dict)
            or set(hint) != {"id", "name", "role", "label"}
            or any(not isinstance(v, str) or len(v) > 4000 for v in hint.values())
        ):
            raise ValueError("Invalid original-page locator hint")
    attachments = data.get("attachments", [])
    if any(
        not isinstance(row, dict)
        or set(row) - {"name", "source"}
        or not isinstance(row.get("name"), str)
        or len(row["name"]) > 1000
        or row.get("source") != "visible_filename"
        for row in attachments
    ):
        raise ValueError("Invalid original-page attachment summary")
    for field in data["fields"]:
        files = field.get("files", [])
        if (
            not isinstance(files, list)
            or len(files) > 20
            or any(
                not isinstance(row, dict)
                or set(row) != {"name", "size", "type"}
                or not isinstance(row["name"], str)
                or len(row["name"]) > 500
                or not isinstance(row["type"], str)
                or len(row["type"]) > 200
                or type(row["size"]) is not int
                or row["size"] < 0
                for row in files
            )
        ):
            raise ValueError("Invalid original-page file summary")
    errors = data.get("validation_errors", [])
    if not isinstance(errors, list) or len(errors) > 500:
        raise ValueError("Invalid original-page validation errors")
    for error in errors:
        if not isinstance(error, dict) or set(error) != {"field_hint", "valid", "aria_invalid"}:
            raise ValueError("Invalid original-page validation error")
        hint = error["field_hint"]
        if (
            not isinstance(hint, dict)
            or set(hint) != {"id", "name", "role", "label"}
            or any(not isinstance(v, str) or len(v) > 4000 for v in hint.values())
            or error["valid"] is not None
            and type(error["valid"]) is not bool
            or (error["aria_invalid"] is not None and not isinstance(error["aria_invalid"], str))
        ):
            raise ValueError("Invalid original-page validation error details")
    for key in ("at", "observed_at"):
        at = value.get(key)
        if (
            type(at) not in (int, float)
            or not math.isfinite(at)
            or not 0 <= time.time() - at < PAGE_SCOPE.window
        ):
            raise ValueError("Original-page JSON context expired")
    if any(
        row.get("type") == "password" and row.get("value") not in (None, "")
        for row in data["fields"]
    ):
        raise ValueError("Password values cannot be delivered")


# Section headings an ATS joins into a personal control's accessible label
# ("Personal details Salutation", onlyfy 2026-11-03). Other sections, such as an
# emergency or reference contact, keep their own question identity.
_PERSONAL_SECTIONS = (
    "personal details",
    "personal information",
    "personal data",
    "contact details",
    "contact information",
    "persönliche angaben",
    "persönliche daten",
    "kontaktdaten",
)


def _native_label_fact(text, information_fact):
    """Map one label; a known personal-section heading before it is not the question."""
    fact = information_fact(text)
    if fact.startswith("question:"):
        normalized = helper.normalize_question(text)
        for section in _PERSONAL_SECTIONS:
            if normalized.startswith(section + " "):
                stripped = information_fact(normalized[len(section) + 1 :])
                return fact if stripped.startswith("question:") else stripped
    return fact


def _validate_native_answers(answers):
    if (
        not isinstance(answers, dict)
        or set(answers) != {"library_status", "facts", "revision"}
        or (
            not isinstance(answers["library_status"], str)
            or answers["library_status"]
            not in {"available", "unavailable", "unconfigured", "not_requested"}
            or not isinstance(answers["facts"], list)
            or len(answers["facts"]) > 64
            or answers["revision"] != digest({k: v for k, v in answers.items() if k != "revision"})
        )
    ):
        raise ValueError("Invalid native saved answers")
    for fact in answers["facts"]:
        if (
            not isinstance(fact, dict)
            or set(fact)
            not in (
                {"fact", "field_ids", "status"},
                {"fact", "field_ids", "status", "value", "references"},
            )
            or not isinstance(fact.get("fact"), str)
            or not fact["fact"]
            or len(fact["fact"]) > 4000
            or (
                not isinstance(fact["field_ids"], list)
                or len(fact["field_ids"]) > 500
                or any(
                    not isinstance(field_id, str) or len(field_id) > 4000
                    for field_id in fact["field_ids"]
                )
                or not isinstance(fact["status"], str)
                or fact["status"]
                not in {
                    "confirmed",
                    "missing",
                    "conflict",
                    "inferred",
                    "scope_required",
                    "source_unavailable",
                    "unsupported_value",
                }
            )
        ):
            raise ValueError("Invalid native saved fact shape")
        if fact["status"] == "confirmed":
            if (
                not isinstance(fact.get("value"), str)
                or not fact["value"].strip()
                or len(fact["value"]) > 20_000
                or not isinstance(fact.get("references"), list)
                or not fact["references"]
            ):
                raise ValueError("Native confirmed facts require saved strings and references")
            if any(
                not isinstance(ref, dict)
                or set(ref) != {"key", "revision", "fact"}
                or ref["fact"] != fact["fact"]
                or not isinstance(ref["key"], str)
                or not isinstance(ref["revision"], str)
                or re.fullmatch(r"[a-f0-9]{64}", ref["revision"]) is None
                for ref in fact["references"]
            ):
                raise ValueError("Invalid native saved answer reference")
        elif "value" in fact or "references" in fact:
            raise ValueError("Unconfirmed native answers cannot disclose values")


def validate_assistance_delivery(value, expected_ref):
    """Validate an already-built JSON handoff before a transport emits it."""
    native = (
        isinstance(expected_ref, dict) and expected_ref.get("protocol") == CODEX_NATIVE_ASSISTANCE
    )
    if (
        not isinstance(value, dict)
        or set(value) - ({"answers"} if native else set())
        != {
            "schema_version",
            "assistance_ref",
            "progress",
            "blocker",
            "pending_actions",
            "page_context",
            "materials",
            "next_step",
        }
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise ValueError("Invalid JSON assistance delivery")
    if not isinstance(expected_ref, dict) or value.get("assistance_ref") != expected_ref:
        raise ValueError("JSON assistance reference changed")
    if (
        not isinstance(value["progress"], dict)
        or set(value["progress"]) != {"completed", "remaining"}
        or any(not isinstance(value["progress"][k], list) for k in ("completed", "remaining"))
        or not isinstance(value["blocker"], dict)
        or not isinstance(value["next_step"], dict)
        or not isinstance(value["pending_actions"], list)
        or not isinstance(value["materials"], list)
        or any(
            not isinstance(row, dict)
            for rows in (
                value["progress"]["completed"],
                value["progress"]["remaining"],
                value["pending_actions"],
                value["materials"],
            )
            for row in rows
        )
    ):
        raise ValueError("Invalid JSON assistance progress")
    if native:
        _validate_native_answers(value.get("answers"))
    context = value["page_context"]
    if isinstance(context, dict) and context.get("status") == "unavailable":
        if context != {"status": "unavailable", "binding": expected_ref.get("binding")}:
            raise ValueError("Invalid missing original-page context")
    else:
        _validate_assistance_page_context(context, expected_ref)
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ValueError("Assistance delivery must be finite JSON") from error
    if len(raw) > 512_000:
        raise ValueError("Assistance delivery exceeds JSON limit")


def _native_handoff_receipt(value):
    """A journaled handoff receipt, held to the driver's one receipt rule."""
    if value is None:
        return None
    from .cua_driver import HANDOFF_GRANT_FIELDS, validate_handoff_receipt

    try:
        if isinstance(value, dict) and "yielded" in value:
            raise ValueError("A journaled grant keeps no driver yield flag")
        return validate_handoff_receipt(
            value, grant=isinstance(value, dict) and set(value) == HANDOFF_GRANT_FIELDS
        )
    except (ValueError, TypeError, RecursionError) as error:
        raise PortalDataError(
            "native_handoff_receipt_invalid", "原生交接回执不能核验。", 409
        ) from error


# The driver's proof that a handoff is over is the takeover record's one rule.
_native_stop_proven = takeover_record.native_return_proven


def _validate_native_handoff_runs(runs):
    if not isinstance(runs, list) or any(not isinstance(row, dict) for row in runs):
        raise PortalDataError("native_handoff_invalid", "原生交接历史不能核验。", 409)
    required = {
        "request_id",
        "assistance_ref",
        "scope",
        "worker_source",
        "phase",
        "semantic_unknown",
        "created_at",
        "events",
    }
    for previous in runs:
        if (
            not required <= set(previous)
            or set(previous) - required - {"handoff_id", "generation"}
            or not isinstance(previous["phase"], str)
            or previous["phase"] not in {"prepared", "granted", "stopping", "stopped", "unknown"}
            or type(previous["semantic_unknown"]) is not bool
            or not isinstance(previous["events"], list)
            or not previous["events"]
            or any(
                not isinstance(event, dict) or set(event) != {"phase", "receipt", "at"}
                for event in previous["events"]
            )
            or previous["events"][-1]["phase"] != previous["phase"]
        ):
            raise PortalDataError(
                "native_handoff_invalid", "原生交接历史不完整，不能派发新操作。", 409
            )
        for old_event in previous["events"]:
            _native_handoff_receipt(old_event["receipt"])
        if previous["phase"] == "stopped" and not _native_stop_proven(
            previous["events"][-1]["receipt"]
        ):
            raise PortalDataError(
                "native_handoff_invalid", "原生停止历史缺少完整排空与交回证明。", 409
            )
        if not previous["semantic_unknown"] and any(
            event["phase"] == "unknown"
            or any(
                call["mutation"] and call["status"] == "unknown"
                for call in (event["receipt"] or {}).get("calls", [])
            )
            for event in previous["events"]
        ):
            raise PortalDataError(
                "native_handoff_invalid", "原生历史中的未知结果不能由停止快照清除。", 409
            )


def valid_backend_authority(value, *, reference=False):
    fields = {"instance_id", "process"}
    if not reference:
        fields |= {"protocol", "status", "published_at", "revoked_at"}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or not isinstance(value["instance_id"], str)
        or re.fullmatch(r"[a-f0-9]{32}", value["instance_id"]) is None
        or not valid_process_identity(value["process"])
    ):
        return False
    return reference or bool(
        value["protocol"] == CODEX_BACKEND_AUTHORITY
        and value["status"] in ("active", "revoked")
        and type(value["published_at"]) in (int, float)
        and math.isfinite(value["published_at"])
        and value["published_at"] > 0
        and (
            value["status"] == "active"
            and value["revoked_at"] is None
            or value["status"] == "revoked"
            and type(value["revoked_at"]) in (int, float)
            and math.isfinite(value["revoked_at"])
            and value["revoked_at"] >= value["published_at"]
        )
    )


def assistance_backend_permitted(state, assistance):
    """Check the bound backend kernel generation; UI polling is unrelated."""
    authority = state.get("backend_authority")
    bound = assistance.get("backend_authority") if isinstance(assistance, dict) else None
    if (
        not valid_backend_authority(authority)
        or authority["status"] != "active"
        or not valid_backend_authority(bound, reference=True)
        or digest(bound) != digest({key: authority[key] for key in ("instance_id", "process")})
    ):
        return False
    try:
        current = process_identity(bound["process"]["pid"])
        return valid_process_identity(current) and digest(current) == digest(bound["process"])
    except (OSError, ValueError, TypeError):
        return False


def revoke_backend_authority(state, *, reference=None):
    authority = state.get("backend_authority")
    if reference is not None:
        bound = reference.get("backend_authority") if isinstance(reference, dict) else None
        if (
            not valid_backend_authority(authority)
            or not valid_backend_authority(bound, reference=True)
            or digest(bound) != digest({key: authority[key] for key in ("instance_id", "process")})
        ):
            return False
    if authority and authority["status"] == "active":
        authority.update(status="revoked", revoked_at=max(time.time(), authority["published_at"]))
        return True
    return False


def valid_backend_page_verification(receipt):
    """Validate a bounded historical readback, without granting execution."""
    try:
        proof = receipt["page_verification"]
        reference = proof["assistance_ref"]
        binding = reference["binding"]
        original = receipt["binding"]
        document = proof["document"]
        data = proof["data"]
        return bool(
            receipt["page_verified"] is True
            and isinstance(proof, dict)
            and set(proof)
            == {"protocol", "at", "assistance_ref", "document", "data", "worker_source"}
            and proof["protocol"] == "backend-page-verification/v1"
            and type(proof["at"]) in (int, float)
            and math.isfinite(proof["at"])
            and proof["at"] > 0
            and type(receipt["verified_at"]) in (int, float)
            and math.isfinite(receipt["verified_at"])
            and receipt["verified_at"] >= proof["at"]
            and isinstance(reference, dict)
            and set(reference)
            in (
                {"id", "generation", "binding", "page_writes_enabled"},
                {"id", "generation", "binding", "page_writes_enabled", "backend_authority"},
                {
                    "id",
                    "generation",
                    "binding",
                    "page_writes_enabled",
                    "protocol",
                    "native_policy_digest",
                },
                {
                    "id",
                    "generation",
                    "binding",
                    "page_writes_enabled",
                    "backend_authority",
                    "protocol",
                    "native_policy_digest",
                },
            )
            and isinstance(reference["id"], str)
            and re.fullmatch(r"[a-f0-9]{32}", reference["id"])
            and type(reference["generation"]) is int
            and reference["generation"] > 0
            and (
                reference["page_writes_enabled"] is False
                and "protocol" not in reference
                or reference.get("protocol") == CODEX_NATIVE_ASSISTANCE
                and reference["page_writes_enabled"] is True
                and isinstance(reference.get("native_policy_digest"), str)
                and re.fullmatch(r"[a-f0-9]{64}", reference["native_policy_digest"])
            )
            and (
                "assistance_ref" not in receipt
                or digest(reference) == digest(receipt["assistance_ref"])
            )
            and (
                "backend_authority" not in reference
                or valid_backend_authority(reference["backend_authority"], reference=True)
            )
            and isinstance(binding, dict)
            and binding["application_id"] == original["application_id"]
            and binding["batch_id"] == original["batch_id"]
            and binding["run_id"] == receipt["run_id"] == original["runtime"]["id"]
            and binding["page_id"] == original["page"]["page_id"]
            and isinstance(binding["document_token"], str)
            and bool(binding["document_token"])
            and isinstance(document, dict)
            and set(document) == {"frame_id", "loader_id", "url"}
            and all(isinstance(value, str) and bool(value) for value in document.values())
            and isinstance(data, dict)
            and isinstance(data.get("url"), str)
            and data["url"] == binding["step"]
            # CDP Page.Frame.url omits fragments; DOM/Page keep the exact step.
            and urldefrag(data["url"])[0] == urldefrag(document["url"])[0]
            and isinstance(data["fields"], list)
            and len(data["fields"]) <= 500
            and len(json.dumps(data, allow_nan=False).encode()) <= 2_000_000
            and isinstance(proof["worker_source"], str)
            and re.fullmatch(r"[a-f0-9]{64}", proof["worker_source"])
            and proof["worker_source"] == original["runtime"]["source"]["sha256"]
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def valid_assistance(assistance, application_id):
    fields = {
        "protocol",
        "id",
        "generation",
        "request_id",
        "claim_request_id",
        "status",
        "active_writer",
        "binding",
        "page_writes_enabled",
    }
    if (
        not isinstance(assistance, dict)
        or not fields <= set(assistance)
        or set(assistance)
        - fields
        - {"stop", "backend_authority", "backend_loss", "report", "outcome", "superseded"}
        - {"retired"}
        - (
            {"native_policy_digest", "dispatch"}
            if assistance.get("protocol") == CODEX_NATIVE_ASSISTANCE
            else set()
        )
        or "dispatch" in assistance
        and not valid_takeover_dispatch(assistance["dispatch"], assistance)
        or "backend_authority" in assistance
        and not valid_backend_authority(assistance["backend_authority"], reference=True)
        or "backend_loss" in assistance
        and (
            "stop" not in assistance
            or not valid_assistance_backend_loss(assistance["backend_loss"])
        )
    ):
        return False
    binding = assistance["binding"]
    if not isinstance(binding, dict) or set(binding) != {
        "application_id",
        "batch_id",
        "run_id",
        "page_id",
        "document_token",
        "step",
        "controller",
        "resume_serial",
        "material_revision",
        "answer_revision",
    }:
        return False
    return bool(
        (
            assistance["protocol"] == CODEX_ASSISTANCE
            and assistance["page_writes_enabled"] is False
            or assistance["protocol"] == CODEX_NATIVE_ASSISTANCE
            and assistance["page_writes_enabled"] is True
            and isinstance(assistance.get("native_policy_digest"), str)
            and re.fullmatch(r"[a-f0-9]{64}", assistance["native_policy_digest"])
        )
        and isinstance(assistance["id"], str)
        and re.fullmatch(r"[a-f0-9]{32}", assistance["id"])
        and type(assistance["generation"]) is int
        and assistance["generation"] > 0
        and isinstance(assistance["request_id"], str)
        and 1 <= len(assistance["request_id"]) <= 200
        and (
            assistance["status"] == "requested"
            and assistance["active_writer"] == "none"
            and assistance["claim_request_id"] is None
            or assistance["status"] == "claimed"
            and assistance["active_writer"] == "codex"
            and isinstance(assistance["claim_request_id"], str)
            and 1 <= len(assistance["claim_request_id"]) <= 200
            or isinstance(assistance["status"], str)
            and assistance["status"] in {"stopping", "stopped", "stop_unknown"}
            and assistance["active_writer"]
            == ("codex" if assistance["claim_request_id"] is not None else "none")
            and (
                assistance["claim_request_id"] is None
                or isinstance(assistance["claim_request_id"], str)
                and 1 <= len(assistance["claim_request_id"]) <= 200
            )
            or assistance["status"] == "released"
            and assistance["protocol"] == CODEX_NATIVE_ASSISTANCE
            and assistance["active_writer"] == "script"
            and isinstance(assistance["claim_request_id"], str)
            and 1 <= len(assistance["claim_request_id"]) <= 200
            and "superseded" not in assistance
            and valid_assistance_report(assistance.get("report"))
            and valid_assistance_outcome(
                assistance.get("outcome"),
                report=assistance["report"],
                stop=assistance.get("stop"),
            )
        )
        and (
            "stop" not in assistance
            and assistance["status"] in {"requested", "claimed"}
            or "stop" in assistance
            and valid_assistance_stop(
                assistance["stop"],
                "stopped" if assistance["status"] == "released" else assistance["status"],
            )
        )
        and ("report" not in assistance or assistance["status"] != "requested")
        and ("report" not in assistance or valid_assistance_report(assistance["report"]))
        and ("outcome" not in assistance or assistance["status"] == "released")
        and (
            "superseded" not in assistance
            or "stop" in assistance
            and isinstance(assistance["superseded"], dict)
            and set(assistance["superseded"]) == {"reason", "at"}
            and assistance["superseded"]["reason"] in ASSISTANCE_CONTROL_REASONS
            and type(assistance["superseded"]["at"]) in (int, float)
            and math.isfinite(assistance["superseded"]["at"])
            and assistance["superseded"]["at"] > 0
        )
        and binding["application_id"] == application_id
        and all(
            isinstance(binding[key], str) and bool(binding[key])
            for key in (
                "application_id",
                "batch_id",
                "run_id",
                "page_id",
                "document_token",
                "step",
                "controller",
            )
        )
        and type(binding["resume_serial"]) is int
        and binding["resume_serial"] >= 0
        and all(
            isinstance(binding[key], str) and re.fullmatch(r"[a-f0-9]{64}", binding[key])
            for key in ("material_revision", "answer_revision")
        )
    )


def native_unparsed_resume_resolution(job, call):
    """A sealed resume for a page the script parsed to zero questions (no field intent).

    Such a page has no prepared question to carry a send intent, so the Worker admits
    only the job's own bound resume bytes; the ledger row itself is the attempt record.
    """
    resolution = call.get("material_resolution") or {}
    return bool(
        not ((job.get("form_state") or {}).get("snapshot") or {}).get("fields")
        and resolution.get("kind") == "file"
        and resolution.get("sha256") == job.get("file_sha256")
        and resolution.get("filename") == job.get("filename")
    )


def takeover_pending_intent(job):
    """The exact unknown intent a current takeover carries, or None; it is never cleared here."""
    ref = ((job.get("assistance") or {}).get("dispatch") or {}).get("pending_intent_ref")
    intent = job.get("intent")
    return ref if ref and isinstance(intent, dict) and digest(intent) == ref else None


def technical_blocker(state, job, policy):
    """Read a current script blocker that may dispatch one native Codex takeover, or None."""
    reason = job.get("reason")
    binding = assistance_binding(state, job)
    intent = job.get("intent")
    unknown = reason in TAKEOVER_UNKNOWN_REASONS
    if (
        policy is None
        or binding is None
        or state["control"] != "running"
        or state.get("current_job_id") != job["application_id"]
        or job.get("workflow") != "single"
        or job["status"] != "needs_recheck"
        or reason not in TAKEOVER_CODES
        or job.get("handed_off")
        or job.get("manual_submission")
        or manual_submission_unresolved(job)
        or material_edit_pending(job)
        or (job.get("form_state") or {}).get("intervention_pending")
        or state.get("worker_error")
        or state["commands"]
        or not unknown
        and (
            intent
            or any(unresolved_write_failure(event, job, state) for event in job["observations"])
        )
    ):
        return None
    if reason in TAKEOVER_ROUTE_REASONS:
        decision = next(
            (
                row
                for row in reversed(job["observations"])
                if row.get("action") == "route_decision"
                and row.get("run_id") == binding["run_id"]
                and row.get("page_id") == binding["page_id"]
            ),
            {},
        )
        if decision.get("route_reason") != reason or decision.get("dispatch") != "not_sent":
            return None
    field_id = (intent or {}).get("field_id")
    if not intent:
        field_id = next(
            (
                row.get("field_id")
                for row in reversed(job["observations"])
                if row.get("action") == "route_decision"
                and row.get("route_reason") == reason
                and row.get("run_id") == binding["run_id"]
                and row.get("page_id") == binding["page_id"]
            ),
            None,
        )
    blocker = {
        "code": reason,
        "field_id": field_id if isinstance(field_id, str) else None,
        "page_id": binding["page_id"],
        "run_id": binding["run_id"],
        "observed_at": (job.get("page_observation") or {}).get("at"),
    }
    if not _valid_takeover_blocker(blocker, binding) or not _takeover_slot(state, job, blocker):
        return None
    return blocker


def valid_assistance_backend_loss(loss):
    return bool(
        isinstance(loss, dict)
        and set(loss) == {"at", "was_running", "automatic_recovery"}
        and type(loss["at"]) in (int, float)
        and math.isfinite(loss["at"])
        and loss["at"] > 0
        and type(loss["was_running"]) is bool
        and type(loss["automatic_recovery"]) is bool
        and (not loss["automatic_recovery"] or loss["was_running"])
    )


def valid_assistance_outcome(outcome, *, report, stop):
    """The Worker's own post-stop read-only conclusion for exactly one saved report."""
    try:
        verification = outcome["page_verification"]
        checkpoint = outcome["kind"] == "script_checkpoint"
        return bool(
            isinstance(outcome, dict)
            and set(outcome)
            == {
                "protocol",
                "kind",
                "report_sha256",
                "stop_request_id",
                "session_reclaimed_at",
                "page_verification",
                "verified",
                "attributed_fields",
                "return_count",
                "adopted_at",
            }
            | ({"checkpoint_field_id"} if checkpoint else set())
            and outcome["protocol"] == ASSISTANCE_OUTCOME
            and outcome["kind"] in {"script_checkpoint", "filling_complete"}
            and valid_assistance_report(report)
            and outcome["report_sha256"] == _canonical_sha256(report)
            and valid_assistance_stop(stop, "stopped")
            and outcome["stop_request_id"] == stop["request_id"]
            and isinstance(verification, dict)
            and set(verification) == {"at", "document", "fields", "worker_source"}
            and isinstance(verification["document"], dict)
            and set(verification["document"]) == {"frame_id", "loader_id", "url"}
            and all(_bounded_text(v, 20_000) for v in verification["document"].values())
            and isinstance(verification["fields"], list)
            and len(verification["fields"]) <= 500
            and all(
                isinstance(row, dict)
                and set(row) == {"id", "required", "valid", "value_empty", "file_count"}
                and _bounded_text(row["id"], 512)
                and all(type(row[k]) is bool for k in ("required", "valid", "value_empty"))
                and type(row["file_count"]) is int
                and 0 <= row["file_count"] <= 100
                for row in verification["fields"]
            )
            and isinstance(verification["worker_source"], str)
            and re.fullmatch(r"[a-f0-9]{64}", verification["worker_source"])
            and isinstance(outcome["verified"], dict)
            and set(outcome["verified"]) == {"materials", "optional_failures"}
            and all(
                isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
                for rows in outcome["verified"].values()
            )
            and isinstance(outcome["attributed_fields"], list)
            and all(
                isinstance(row, dict)
                and set(row) == {"field_id", "call_id"}
                and _bounded_text(row["field_id"], 512)
                and _bounded_text(row["call_id"], 128)
                for row in outcome["attributed_fields"]
            )
            and (not checkpoint or _bounded_text(outcome["checkpoint_field_id"], 512))
            and type(outcome["return_count"]) is int
            and 0 <= outcome["return_count"] <= 1
            and (not checkpoint or outcome["return_count"] == 1)
            and all(_timestamp(outcome[k]) for k in ("session_reclaimed_at", "adopted_at"))
            and _timestamp(verification["at"])
            and _timestamp(stop["observed_at"])
            and stop["observed_at"]
            <= outcome["session_reclaimed_at"]
            <= verification["at"]
            <= outcome["adopted_at"]
            and report["received_at"] <= outcome["adopted_at"]
            and len(json.dumps(outcome, allow_nan=False)) <= 2_000_000
        )
    except (KeyError, TypeError, ValueError, RecursionError):
        return False


def mark_assistance_backend_lost(state, reference):
    """Retain an unavailable backend generation without confusing it with UI silence."""
    if not isinstance(reference, dict) or not isinstance(reference.get("binding"), dict):
        return False
    binding = reference["binding"]
    job = next(
        (row for row in state["jobs"] if row["application_id"] == binding.get("application_id")),
        None,
    )
    assistance = (job or {}).get("assistance")
    authority = state.get("backend_authority")
    bound = reference.get("backend_authority")
    if (
        not assistance
        or digest(assistance_reference(assistance)) != digest(reference)
        or not valid_backend_authority(authority)
        or not valid_backend_authority(bound, reference=True)
        or digest(bound) != digest({key: authority[key] for key in ("instance_id", "process")})
    ):
        return False
    try:
        observed = process_identity(bound["process"]["pid"])
    except (OSError, ValueError, TypeError):
        observed = None
    if valid_process_identity(observed) and digest(observed) == digest(bound["process"]):
        return False
    current_execution = (
        state.get("current_job_id") == job["application_id"]
        and state["batch_id"] == binding["batch_id"]
        and (state.get("runtime") or {}).get("id") == binding["run_id"]
    )
    current_scope = (
        current_execution
        and state.get("controller") == binding["controller"]
        and type(state.get("resume_serial", 0)) is int
        and state.get("resume_serial", 0) == binding["resume_serial"]
    )
    changed = False
    if "backend_loss" not in assistance:
        was_running = current_scope and state["control"] == "running"
        assistance["backend_loss"] = {
            "at": time.time(),
            "was_running": was_running,
            "automatic_recovery": was_running,
        }
        changed = True
    changed = revoke_assistance(job, reason="backend_authority_lost") or changed
    changed = revoke_backend_authority(state, reference=reference) or changed
    if current_execution and state["control"] == "running":
        state["control"] = "paused"
        if job["status"] in {"queued", "filling"} and not job.get("reason"):
            job.update(status="needs_recheck", reason="backend_authority_lost")
        changed = True
    return changed


def assistance_completion(job):
    """The adopted Codex filling-complete outcome, or None for every other job."""
    assistance = job.get("assistance")
    if (
        not assistance
        or not valid_assistance(assistance, job["application_id"])
        or assistance["status"] != "released"
        or assistance["outcome"]["kind"] != "filling_complete"
    ):
        return None
    return deepcopy(assistance["outcome"])


def adopt_assistance_stop(job, assistance_ref, progress, *, request_id):
    """Conditionally retain stop evidence; it never resolves a page effect."""
    assistance = job.get("assistance")
    stop = (assistance or {}).get("stop")
    if (
        not assistance
        or not stop
        or not isinstance(assistance_ref, dict)
        or digest(assistance_ref) != digest(assistance_reference(assistance))
        or stop["request_id"] != request_id
        or not isinstance(progress, dict)
    ):
        raise PortalDataError("assistance_stop_changed", "接管停止引用已改变，保留原占用。", 409)
    if stop["stop_status"] == "stopped":
        # A proven stop is final; a later snapshot (e.g. after the Worker reclaimed
        # the native session) is never adopted, so it cannot raise a storage stop.
        return False
    fields = (
        "tools_revoked",
        "local_tools_drained",
        "process_stopped",
        "native_turn_id",
        "native_turn_status",
        "stop_status",
    )
    candidate = {**stop, **{key: progress.get(key) for key in fields}}
    status = (
        {
            "stopping": "stopping",
            "stopped": "stopped",
            "unknown": "stop_unknown",
        }.get(candidate["stop_status"])
        if isinstance(candidate["stop_status"], str)
        else None
    )
    if not valid_assistance_stop(candidate, status):
        raise PortalDataError("assistance_stop_invalid", "接管停止结果尚不能核验。", 409)
    if stop["native_turn_id"] is not None:
        if candidate["native_turn_id"] not in (None, stop["native_turn_id"]):
            raise PortalDataError("assistance_stop_changed", "原生运行引用已改变。", 409)
        candidate["native_turn_id"] = stop["native_turn_id"]
    terminals = {"completed", "interrupted", "failed"}
    if stop["native_turn_status"] in terminals:
        if (
            candidate["native_turn_status"] in terminals
            and candidate["native_turn_status"] != stop["native_turn_status"]
        ):
            raise PortalDataError("assistance_stop_changed", "原生停止结论存在冲突。", 409)
        candidate["native_turn_status"] = stop["native_turn_status"]
    for key in ("local_tools_drained", "process_stopped"):
        candidate[key] = stop[key] or candidate[key]
    if candidate["process_stopped"] and candidate["native_turn_status"] == "running":
        candidate["native_turn_status"] = "unknown"
    if stop["stop_status"] == "unknown" and candidate["stop_status"] == "stopping":
        return False
    if all(stop[key] == candidate[key] for key in fields):
        return False
    candidate["observed_at"] = time.time()
    assistance.update(status=status, stop=candidate)
    return True


def adopt_assistance_report(job, assistance_ref, report, *, request_id):
    """Keep one stopped turn's Codex claim as history; it adopts nothing by itself."""
    assistance = job.get("assistance")
    stop = (assistance or {}).get("stop")
    if (
        not assistance
        or not stop
        or not isinstance(assistance_ref, dict)
        or digest(assistance_ref) != digest(assistance_reference(assistance))
        or stop["request_id"] != request_id
    ):
        raise PortalDataError(
            "assistance_report_changed", "接管引用已改变，不保存为本次回报。", 409
        )
    if not valid_assistance_report(report):
        raise PortalDataError("assistance_report_invalid", "接管回报不符合结构化契约。", 409)
    saved = assistance.get("report")
    if saved is not None:
        if _canonical_sha256(saved) != _canonical_sha256(report):
            raise PortalDataError("assistance_outcome_conflict", "已保存另一份接管回报。", 409)
        return False
    assistance["report"] = deepcopy(report)
    return True


def _assistance_outcome_rejection(state, job, assistance_ref, outcome):
    assistance = job.get("assistance") or {}
    stop = assistance.get("stop") or {}
    report = assistance.get("report")
    if not assistance or digest(assistance_ref) != digest(assistance_reference(assistance)):
        return "assistance_generation_changed"
    if assistance["protocol"] != CODEX_NATIVE_ASSISTANCE:
        return "assistance_protocol_unsupported"
    if "superseded" in assistance:
        return "assistance_superseded"
    if report is None:
        return "assistance_report_missing"
    try:
        runs = job.get("native_handoff_runs", [])
        _validate_native_handoff_runs(runs)
        proven = all(
            row["phase"] == "stopped" and not row["semantic_unknown"]
            for row in runs
            if row["assistance_ref"] == assistance_ref
        )
    except PortalDataError:
        proven = False
    if assistance["status"] != "stopped" or not proven:
        return "assistance_stop_unproven"
    if stop["reason"] != "native_turn_completed" or stop["native_turn_status"] != "completed":
        return "assistance_stop_reason"
    if stop["native_turn_id"] is None or report["native_turn_id"] != stop["native_turn_id"]:
        return "assistance_report_turn_changed"
    if (
        state["control"] != "running"
        or state.get("current_job_id") != job["application_id"]
        or job["status"] == "cancelled"
        or job.get("handed_off")
        or job.get("manual_submission")
    ):
        return "assistance_control_changed"
    current = assistance_binding(state, job)
    saved_binding = assistance["binding"]
    if takeover_pending_intent(job):
        return "assistance_pending_intent"
    if (
        digest(current) != digest(saved_binding)
        and not assistance_binding_resumed_only(current, saved_binding)
        or material_edit_pending(job)
        or job.get("intent")
    ):
        return "assistance_scope_changed"
    if manual_submission_unresolved(job):
        return "manual_submission_unresolved"
    if any(unresolved_write_failure(row, job, state) for row in job["observations"]):
        return "unresolved_write_failure"
    verification = outcome.get("page_verification") or {}
    document = verification.get("document") or {}
    if (
        verification.get("worker_source")
        != (state.get("runtime") or {}).get("source", {}).get("sha256")
        or not isinstance(document.get("url"), str)
        or urldefrag(document["url"])[0] != urldefrag(assistance["binding"]["step"])[0]
    ):
        return "assistance_page_changed"
    if outcome["kind"] == "script_checkpoint" and job.get("assistance_return_count", 0) >= 1:
        return "assistance_return_limit"
    return None


def assistance_binding_resumed_only(current, saved):
    """A lost outcome save is retried after Continue: only the serial may advance."""
    return (
        current is not None
        and current["resume_serial"] > saved["resume_serial"]
        and digest(current | {"resume_serial": saved["resume_serial"]}) == digest(saved)
    )


def adopt_assistance_outcome(state, job, assistance_ref, outcome):
    """Release the writer to the script for one checked report, or keep it as history."""
    assistance = job.get("assistance") or {}
    report = assistance.get("report")
    sha = outcome.get("report_sha256") if isinstance(outcome, dict) else None
    previous = job.get("assistance_return_count", 0)
    if (
        not isinstance(sha, str)
        or re.fullmatch(r"[a-f0-9]{64}", sha) is None
        or outcome.get("kind") not in {"script_checkpoint", "filling_complete"}
        or type(previous) is not int
        or previous not in (0, 1)
    ):
        raise PortalDataError("assistance_outcome_invalid", "接管结果不符合结构化契约。", 409)
    saved = assistance.get("outcome")
    if saved is not None or report is not None and sha != _canonical_sha256(report):
        if saved is None or saved["report_sha256"] != sha:
            raise PortalDataError("assistance_outcome_conflict", "接管结果对应另一份回报。", 409)
        return False
    reason = _assistance_outcome_rejection(state, job, assistance_ref, outcome)
    if reason is not None:
        if any(
            row.get("action") == "assistance_report_not_adopted" and row.get("report_sha256") == sha
            for row in job["observations"]
        ):
            return False
        job["observations"].append(
            {
                "action": "assistance_report_not_adopted",
                "reason": reason,
                "report_sha256": sha,
                "at": time.time(),
            }
        )
        return True
    if not valid_assistance_outcome(outcome, report=report, stop=assistance["stop"]) or (
        outcome["return_count"] != previous + (outcome["kind"] == "script_checkpoint")
    ):
        raise PortalDataError("assistance_outcome_invalid", "接管结果不符合结构化契约。", 409)
    assistance.update(status="released", active_writer="script", outcome=deepcopy(outcome))
    if outcome["kind"] == "script_checkpoint":
        job["assistance_return_count"] = outcome["return_count"]
    return True


def assistance_binding(state, job):
    """Reference saved original-page facts, without observing or granting execution."""
    runtime = state.get("runtime") or {}
    page = job.get("page_observation") or {}
    form = (job.get("form_state") or {}).get("binding") or {}
    if (
        not runtime.get("id")
        or not job.get("page_open")
        or page.get("event") != "observed"
        or page.get("run_id") != runtime["id"]
        or form.get("run_id") != runtime["id"]
        or not page.get("page_id")
        or form.get("page_id") != page["page_id"]
        or not isinstance(form.get("document_token"), str)
        or not form["document_token"]
        or not isinstance(form.get("step"), str)
        or not form["step"]
    ):
        return None
    return {
        "application_id": job["application_id"],
        "batch_id": state["batch_id"],
        "run_id": runtime["id"],
        "page_id": page["page_id"],
        "document_token": form["document_token"],
        "step": form["step"],
        "controller": state.get("controller"),
        "resume_serial": state.get("resume_serial", 0),
        "material_revision": digest(
            {
                "file_sha256": job["file_sha256"],
                "single_binding": job.get("single_binding"),
                "materials": job.get("materials", []),
            }
        ),
        "answer_revision": digest(job.get("answer_refs", [])),
    }


def handoff_binding(state, job):
    """Bind an inspection to the original run, page, attachment and answer boundary."""
    runtime = deepcopy(state.get("runtime") or {})
    runtime.pop("observed_at", None)
    runtime.pop("controller_handoff", None)
    return {
        "runtime": runtime,
        "batch_id": state["batch_id"],
        "single_context": state.get("single_context"),
        "application_id": job["application_id"],
        "page": {
            key: (job.get("page_observation") or {}).get(key)
            for key in ("run_id", "page_id", "event")
        },
        "file_sha256": job["file_sha256"],
        "single_binding": deepcopy(job.get("single_binding")),
        "intent": deepcopy(job.get("intent")),
        "answer_refs": deepcopy(job.get("answer_refs")),
    }


def worker_lock_is_held(root, evidence):
    """Check the challenge's original lock inode without waiting or taking ownership."""
    if not isinstance(evidence, dict):
        return False
    try:
        descriptor = os.open(root / ".worker.lock", os.O_RDONLY | os.O_NOFOLLOW)
        try:
            observed = os.fstat(descriptor)
            if evidence != {"device": observed.st_dev, "inode": observed.st_ino}:
                return False
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return False
        finally:
            os.close(descriptor)
    except OSError:
        return False


def source_manifest(expected_sources: dict | None = None) -> dict:
    """Capture startup source once. Never relabel a running worker from disk."""
    files = {
        str(Path(module.__file__).resolve().relative_to(PUBLIC_ROOT)): hashlib.sha256(
            Path(module.__file__).read_bytes()
        ).hexdigest()
        for name, module in list(sys.modules.items())
        if name.startswith("career_evidence_graph")
        and getattr(module, "__file__", None)
        and Path(module.__file__).resolve().is_relative_to(PUBLIC_ROOT)
    }
    if expected_sources is not None and any(
        expected_sources.get(path) != value for path, value in files.items()
    ):
        raise ValueError("Worker source changed during startup.")
    return {"sha256": digest(files), "files": files}


def backend_recovery_timely(receipt):
    requested = receipt.get("requested_at")
    return (
        type(requested) in {int, float}
        and math.isfinite(requested)
        and 0 <= time.time() - requested <= 15
    )


def unopened_single_queue(store, state):
    """A cold owner can continue only a queue with no browser or action history."""
    jobs = state["jobs"]
    return bool(
        len(jobs) == 1
        and state.get("current_job_id") == jobs[0]["application_id"]
        and jobs[0].get("workflow") == "single"
        and jobs[0]["status"] == "queued"
        and not jobs[0].get("reason")
        and not any(
            jobs[0].get(key)
            for key in (
                "page_open",
                "page_observation",
                "intent",
                "observations",
                "answer_refs",
                "handed_off",
                "manual_submission",
                "submission_observation",
                "pending_status",
                "pending_sync",
                "sync_error",
                "manual_fields",
                "manual_attachments",
                "assistance",
            )
        )
        and not (store.root / "browser-profile").exists()
        and not store.stop_reason()
        and not state.get("worker_error")
        and all(c["action"] == "recover-backend" for c in state["commands"])
    )


def start_run(store, *, expected_sources: dict | None = None) -> str:
    with store.applications.write_lock():
        state = store.load()
        previous = state.get("runtime")
        if previous:
            state.setdefault("runtime_history", []).append(deepcopy(previous))
        recovering = state["worker_pid"] is not None
        backend_recovery = state.get("backend_recovery") or {}
        unopened = unopened_single_queue(store, state)
        cold_continue = unopened and (
            state["control"] == "running"
            or state["control"] == "paused"
            and (
                backend_recovery.get("status") == "pending"
                and backend_recovery_timely(backend_recovery)
            )
        )
        # A Continue that reopens a lost page (APP-13) starts this run for that job.
        reopen = state.get("page_reopen") or {}
        reopening = reopen.get("status") == "pending" and state["control"] == "running"
        if recovering or cold_continue:
            state.update(
                control="running" if cold_continue or reopening else "paused", worker_error=""
            )
        run_id = uuid4().hex
        now = time.time()
        for job in state["jobs"]:
            if assistance_stop_pending(job):
                revoke_assistance(job, reason="worker_restarted")
                job["assistance"].update(status="stop_unknown")
                job["assistance"]["stop"].update(stop_status="unknown", observed_at=now)
                revoke_backend_authority(state)
                state["control"] = "paused"
            if job["status"] != "cancelled" or job["page_open"] or job["intent"]:
                reserve_execution(
                    store.applications,
                    job["application_id"],
                    automated_owner(store.root, state["batch_id"], job["application_id"]),
                    "automated",
                )
            if (
                job["page_open"]
                or job["intent"]
                or recovering
                and not unopened
                and job["status"] != "cancelled"
                and not (reopening and job["application_id"] == reopen["application_id"])
            ):
                job.setdefault("observations", []).append(
                    {
                        "action": "historical_page",
                        "run_id": (previous or {}).get("id"),
                        "at": now,
                        "page_open": job["page_open"],
                    }
                )
                if job["status"] != "cancelled":
                    job.update(status="needs_recheck", reason="worker_restarted")
            job["page_open"] = False
        state["commands"] = (
            [] if recovering else [c for c in state["commands"] if c["action"] != "one-use"]
        )
        if reopening:
            reopen.update(status="started", run_id=run_id)
        state.update(worker_pid=os.getpid(), worker_heartbeat=now)
        state["runtime"] = {
            "id": run_id,
            "applications_root": str(store.applications.root),
            "started_at": now,
            "pid": os.getpid(),
            "source": source_manifest(expected_sources),
            "observed_at": now,
            "capabilities": [OWNED_PAGE_OBSERVATION],
        }
        if unopened and backend_recovery.get("status") == "suspended":
            # A child launched before close may start late. It owns no page and waits
            # for a reopened backend to issue a fresh, timed owner verification.
            state.setdefault("backend_recovery_history", []).append(
                {
                    **deepcopy(backend_recovery),
                    "superseded_at": now,
                    "supersession": "unopened_owner_started_paused",
                }
            )
            backend_recovery["binding"] = handoff_binding(state, state["jobs"][0])
        elif backend_recovery.get("status") == "pending" and not backend_recovery_timely(
            backend_recovery
        ):
            backend_recovery.update(status="needs_recheck", reason="backend_recovery_expired")
        if cold_continue and backend_recovery.get("status") == "pending":
            backend_recovery.update(
                status="verified",
                run_id=run_id,
                verified_at=now,
                source="never_opened_single_queue",
            )
        store.save(state)
        return run_id


def latest_action_resolutions(resolutions: list[dict]) -> dict[str, dict]:
    """Keep the last recorded human conclusion for each action attempt."""
    return {row["intent_ref"]: row for row in resolutions}


def effective_action_results(job: dict) -> dict[str, dict]:
    """Keep the latest resolution or subsequent completion for each attempt."""
    results = latest_action_resolutions(job.get("action_resolutions", []))
    settled = set(results)
    for index, observation in enumerate(job["observations"]):
        intent = observation.get("intent")
        failed = failed_write(observation)
        if intent and (
            failed
            or (
                observation.get("action") == "action_result"
                and observation.get("result") == "verified"
                or observation.get("action") == "fill"
                and observation.get("verified") is True
            )
        ):
            reference = intent.get("attempt_id") or digest(intent)
            if failed and reference in settled:
                continue
            resolution = results.get(reference)
            if resolution and (
                index < resolution["observation_count"]
                if "observation_count" in resolution
                else observation.get("at", 0) < resolution.get("at", 0)
            ):
                continue
            # Append order survives wall-clock corrections. Legacy checkpoints
            # use their existing time evidence; equal times favor completion.
            if failed:
                results.pop(reference, None)
            else:
                results[reference] = {"intent": intent, "conclusion": "current_matches"}
    return results


def email_correction_readback(state: dict, job: dict) -> dict | None:
    """Project a recorded fill of the latest correction; never claim a live field value."""
    corrections = job.get("email_corrections", [])
    if not corrections:
        return None
    correction = corrections[-1]
    binding = correction.get("binding") or {}
    page = job.get("page_observation") or {}
    if (
        not all(binding.get(key) for key in ("application_id", "run_id", "page_id", "field_id"))
        or binding["application_id"] != job["application_id"]
        or binding["run_id"] != (state.get("runtime") or {}).get("id")
        or any(binding[key] != page.get(key) for key in ("run_id", "page_id"))
    ):
        return None
    reference = {
        "key": "one-use",
        "revision": digest(
            {
                "key": "one-use",
                "question": "email",
                "value": correction["value"],
                "scope": {"application_id": job["application_id"]},
                "state": "confirmed",
            }
        ),
        "fact": "email",
    }
    if reference | {"field_id": binding["field_id"]} not in job["answer_refs"]:
        return None
    queued_at = None
    result = None
    for event in job["observations"]:
        at = event.get("at")
        if type(at) not in (int, float) or not math.isfinite(at) or at < 0:
            continue
        if (
            event.get("action") == "email_correction_queued"
            and event.get("correction_id") == correction["id"]
            and event.get("binding") == binding
        ):
            queued_at = at
            result = None
        intent = event.get("intent") or {}
        if (
            queued_at is not None
            and at >= queued_at
            and event.get("action") == "fill"
            and event.get("verified") is True
            and event.get("run_id") == binding["run_id"]
            and event.get("field_id") == binding["field_id"]
            and intent.get("action") == "fill"
            and intent.get("fact") == "email"
            and all(intent.get(key) == binding[key] for key in ("run_id", "page_id", "field_id"))
            and intent.get("answer_ref") == reference
        ):
            result = {"at": at, "binding": deepcopy(binding), "source": "worker_verified_fill"}
    return result


def manual_submission_unresolved(job):
    """An unknown human final request never grants another automated write."""
    observed = job.get("submission_observation") or {}
    latest = next(
        (
            row
            for row in reversed(job.get("observations", []))
            if row.get("kind") == "manual_submit"
            and row.get("stage") == "request"
            and row.get("application_id") == job["application_id"]
        ),
        None,
    )
    return observed.get("conclusion") == "unknown" or bool(
        latest
        and (
            observed.get("status") != "observed"
            or observed.get("manual_request_id") != latest.get("request_id")
            or observed.get("conclusion") not in {"rejected", "success"}
        )
    )


def precision_preparation_pending(job):
    return bool(
        job
        and job.get("precision_preparation")
        and job["precision_preparation"].get("status") != "released"
    )


def material_edit_pending(job):
    return (job.get("material_edit") or {}).get("status") in {"preparing", "needs_recheck"}


def checked_material_preparation_job(
    state, application_id, *, expected_batch_id, expected_task_id=None
):
    """Read-only permission for preparing a successor to this paused execution."""
    job = next(
        (row for row in state.get("jobs", []) if row["application_id"] == application_id),
        None,
    )
    if (
        not isinstance(expected_batch_id, str)
        or not expected_batch_id
        or state.get("control") != "paused"
        or state.get("batch_id") != expected_batch_id
        or state.get("current_job_id") != application_id
        or not job
        or expected_task_id is not None
        and (job.get("single_binding") or {}).get("task_id") != expected_task_id
        or job.get("status") == "cancelled"
        or job.get("intent")
        or job.get("manual_submission")
        or manual_submission_unresolved(job)
        or material_edit_pending(job)
        or assistance_stop_pending(job)
    ):
        raise PortalDataError(
            "bound_material_pause_required", "请保持当前原岗位暂停并先核验未知动作。", 409
        )
    return job


def cancel_continuation(job, reason):
    receipt = job.get("continuation") or {}
    if receipt.get("status") == "pending":
        receipt.update(status="cancelled", reason=reason, cancelled_at=time.time())


def default_scope(fact: str, job: dict) -> dict:
    if fact in {
        "name",
        "first_name",
        "last_name",
        "email",
        "phone",
        "github_url",
        "linkedin_url",
        "language_french_cefr",
        "language_german_cefr",
    }:
        return {}
    if fact in {"sponsorship_now_future", "work_authorization_now"}:
        scope = {"country": job["country"]}
        if job["country"] == "OTHER":
            scope["application_id"] = job["application_id"]
        return scope
    return {"application_id": job["application_id"]}


def question_scope(question: dict, job: dict) -> dict:
    scope = default_scope(fact_for(question["question"]), job)
    if question.get("sensitivity", "none") != "none":
        scope["application_id"] = job["application_id"]
    return scope


def _input_items(state: dict) -> list[dict]:
    """Group current questions without changing jobs or producing observations."""
    grouped = {}
    for job in state["jobs"]:
        if job["status"] not in {"queued", "filling", "needs_input"}:
            continue
        for question in job["questions"]:
            scope = question_scope(question, job)
            group_id = digest([fact_for(question["question"]), scope, question["options"]])
            item = grouped.setdefault(
                group_id,
                {
                    "id": group_id,
                    "question": question["question"],
                    "options": question["options"],
                    "scope": scope,
                    "jobs": [],
                },
            )
            item["jobs"].append(
                {
                    "id": job["application_id"],
                    "question_id": question["id"],
                    "company": job["company"],
                    "role_title": job["role_title"],
                    "original_question": question["question"],
                }
            )
    return list(grouped.values())


# Per-request guard rows a job board repeats. A row that stopped the job, a rejected
# response, or one another row names is never routine.
ROUTINE_REQUEST_STAGES = frozenset(
    {"request_blocked", "request_permitted", "request_redirect_not_followed"}
)
# The job record keeps this many recent routine rows and counts every one it drops
# (9,374 routine rows were 13 MB of one 19 MB checkpoint, 2026-11-03).
ROUTINE_OBSERVATION_WINDOW = 200
# An idle Worker tick that moves only liveness timestamps forward writes at most
# this often; readers' scope window is 6 s, and page reads always write.
LIVENESS_SAVE_INTERVAL = 2.0


def compact_native_runs(runs):
    """Store each distinct native call once; event receipts repeat earlier calls.

    Lossless: ``receipt["calls"] == [run["calls"][i] for i in receipt["call_refs"]]``.
    """
    compacted = []
    for run in runs:
        if not isinstance(run, dict) or "calls" in run or not isinstance(run.get("events"), list):
            compacted.append(run)
            continue
        calls, index, events = [], {}, []
        for event in run["events"]:
            receipt = event.get("receipt") if isinstance(event, dict) else None
            if isinstance(receipt, dict) and isinstance(receipt.get("calls"), list):
                refs = []
                for call in receipt["calls"]:
                    key = json.dumps(call, sort_keys=True, default=str)
                    if key not in index:
                        index[key] = len(calls)
                        calls.append(call)
                    refs.append(index[key])
                receipt = {
                    **{k: v for k, v in receipt.items() if k != "calls"},
                    "call_refs": refs,
                }
                event = {**event, "receipt": receipt}
            events.append(event)
        compacted.append({**run, "events": events, "calls": calls})
    return compacted


def compact_observations(job: dict) -> None:
    """Bound routine request rows; keep stops, referenced rows and per-kind drop counts."""
    rows = job.get("observations")
    if not isinstance(rows, list):
        return
    for row in rows:
        if (
            isinstance(row, dict)
            and row.get("action") == "page_reopen_requested"
            and isinstance(row.get("retired_native_handoff_runs"), list)
        ):
            row["retired_native_handoff_runs"] = compact_native_runs(
                row["retired_native_handoff_runs"]
            )

    def routine(row):
        return (
            isinstance(row, dict)
            and row.get("action") == "request_diagnostic"
            and row.get("stage") in ROUTINE_REQUEST_STAGES
            and row.get("caused_stop") is not True
        )

    routine_rows = [row for row in rows if routine(row)]
    excess = len(routine_rows) - ROUTINE_OBSERVATION_WINDOW
    if excess <= 0:
        return
    referenced = {
        row.get("request_id") for row in rows if isinstance(row, dict) and not routine(row)
    }
    dropped = set()
    for row in routine_rows:
        if len(dropped) == excess:
            break
        if row.get("request_id") not in referenced:
            dropped.add(id(row))
    counts = job.setdefault("observation_counts", {})
    kept = []
    for row in rows:
        if id(row) in dropped:
            kind = "/".join(str(row.get(key)) for key in ("action", "stage", "reason"))
            counts[kind] = counts.get(kind, 0) + 1
        else:
            kept.append(row)
    rows[:] = kept


def _liveness_values(state: dict) -> list:
    runtime = state.get("runtime")
    values = [
        state.get("worker_heartbeat"),
        state.get("heartbeat_at"),
        runtime.get("observed_at") if isinstance(runtime, dict) else None,
    ]
    values += [
        job["page_observation"].get("at")
        for job in state.get("jobs", [])
        if isinstance(job, dict) and isinstance(job.get("page_observation"), dict)
    ]
    if any(value is not None and type(value) not in {int, float} for value in values):
        raise TypeError("liveness timestamp is not a number")
    return values


def _liveness_free(state: dict) -> str:
    """The checkpoint content without the timestamps that only prove liveness."""
    runtime = state.get("runtime")
    jobs = [
        {**job, "page_observation": {**job["page_observation"], "at": None}}
        if isinstance(job, dict) and isinstance(job.get("page_observation"), dict)
        else job
        for job in state.get("jobs", [])
    ]
    return json.dumps(
        {
            **state,
            "jobs": jobs,
            "worker_heartbeat": None,
            "heartbeat_at": None,
            "runtime": {**runtime, "observed_at": None} if isinstance(runtime, dict) else runtime,
        },
        sort_keys=True,
        default=str,
    )


def failed_write(event: dict) -> bool:
    # Chromium can emit ERR_ABORTED after a fulfilled, bodyless Ashby upload ACK.
    # Its required 204 is conclusive for this transport; file linking is verified separately.
    acknowledged_upload = event.get("kind") == "upload" and event.get("http_status") == 204
    return (event.get("intent") or {}).get("action") in {"fill", "upload"} and (
        event.get("stage") == "request_response_rejected"
        or event.get("stage") == "requestfailed"
        and not acknowledged_upload
        or event.get("stage") == "response"
        and event.get("http_status", 0) >= 400
    )


def unresolved_write_failure(event: dict, job: dict, state: dict) -> bool:
    intent = event.get("intent") or {}
    reference = intent.get("attempt_id") or digest(intent)
    return (
        failed_write(event)
        and not job["handed_off"]
        and job["status"] != "cancelled"
        and event.get("application_id") == job["application_id"]
        and event.get("run_id") == (state.get("runtime") or {}).get("id")
        and event.get("batch_id") == state["batch_id"]
        and job["intent"] in (None, intent)
        and reference not in latest_action_resolutions(job.get("action_resolutions", []))
    )


class WorkerStore:
    """One state document, the upstream answer store, and the original note writer."""

    def __init__(
        self,
        applications: ApplicationStore,
        root: Path,
        *,
        live: bool = False,
        single_flow_root=None,
        single_career_root=None,
        legacy_roots=(),
        single_validator=None,
        single_material_source_provider=None,
    ):
        self.applications = applications
        self.single_flow_root = (
            Path(single_flow_root).expanduser().absolute() if single_flow_root is not None else None
        )
        self.single_career_root = (
            Path(single_career_root).expanduser().absolute()
            if single_career_root is not None
            else None
        )
        self.legacy_roots = tuple(Path(path).expanduser().absolute() for path in legacy_roots)
        self.single_validator = single_validator
        self.single_material_source_provider = single_material_source_provider
        self.root = private_root(root)
        self.path = self.root / "run.json"
        reject_mixed_execution_root(self.root, "handoff.json")
        self.measurements = MeasurementLog(self.root)
        self.stop_path = self.root / ".worker-stop.json"
        self.storage_error = ""
        helper_path = Path(helper.__file__)
        if hashlib.sha256(helper_path.read_bytes()).hexdigest() != HELPER_SHA256:
            raise ValueError("The pinned Job Apply helper has changed.")
        legacy = self.root / ".legacy-import-disabled"
        if legacy.exists():
            raise ValueError("Legacy import is disabled for this worker.")
        self.answers = helper.Store(self.root / "answer-library", legacy_profile=legacy)
        with applications.write_lock():
            if self.path.exists():
                existing = helper.read_json_object(self.path, "worker state")
                self.check_applications_root(existing)
            self.answers.initialize()
            if not self.path.exists():
                self.save(
                    {
                        "schemaVersion": 1,
                        "applications_root": str(applications.root),
                        "batch_id": "",
                        "control": "paused",
                        "controller": "",
                        "heartbeat_at": 0,
                        "jobs": [],
                        "commands": [],
                        "worker_pid": None,
                        "worker_error": "",
                        "lease_seconds": 60,
                        "page_capacity": 3,
                        "mode": "live" if live else "synthetic",
                        "generic_enabled": False,
                        "worker_heartbeat": 0,
                    }
                )
            if self.load()["mode"] != ("live" if live else "synthetic"):
                raise ValueError("Keep live and synthetic worker stores separate.")

    def load(self) -> dict:
        state = helper.read_json_object(self.path, "worker state")
        self.check_applications_root(state)
        if state.get("schemaVersion") != 1 or state.get("control") not in {
            "paused",
            "running",
            "cancelled",
        }:
            raise ValueError("Invalid worker state.")
        if "backend_authority" in state and not valid_backend_authority(state["backend_authority"]):
            raise ValueError("Invalid worker backend authority.")
        recovery = state.get("backend_recovery") or {}
        if any(key in recovery for key in ("page_verified", "page_verification")) and not (
            valid_backend_page_verification(recovery)
        ):
            raise ValueError("Invalid worker backend page verification.")
        if not isinstance(state.get("jobs"), list) or any(
            not isinstance(job, dict) or job.get("status") not in STATUSES for job in state["jobs"]
        ):
            raise ValueError("Invalid worker jobs.")
        if (
            any(
                not isinstance(state.get(key), (int, float))
                or not math.isfinite(state[key])
                or state[key] < 0
                for key in ("heartbeat_at", "worker_heartbeat", "lease_seconds")
            )
            or not isinstance(state.get("commands"), list)
            or any(
                not isinstance(command, dict)
                or command.get("action")
                not in {
                    "one-use",
                    "review",
                    "release",
                    "recheck",
                    "answers-changed",
                    "observe-page",
                    "inspect-handoff",
                    "recover-backend",
                    "continue-current",
                    "inspect-material-update",
                    "observe-result",
                }
                for command in state["commands"]
            )
        ):
            raise ValueError("Invalid worker control.")
        if any(
            not isinstance(job.get("page_open"), bool)
            or not isinstance(job.get("handed_off"), bool)
            or not isinstance(job.get("observations"), list)
            or job.get("intent") is not None
            and (
                not isinstance(job["intent"], dict)
                or job["intent"].get("action") not in {"open", "fill", "upload", "advance"}
                or job["intent"].get("action") == "advance"
                and (
                    not isinstance(job["intent"].get("navigation"), dict)
                    or set(job["intent"]["navigation"]) != {"control_id", "from_step", "to_step"}
                    or any(
                        not isinstance(value, str) or not value.strip()
                        for value in job["intent"]["navigation"].values()
                    )
                    or job["intent"]["navigation"]["from_step"]
                    == job["intent"]["navigation"]["to_step"]
                )
            )
            for job in state["jobs"]
        ):
            raise ValueError("Invalid worker checkpoint.")
        if "current_job_id" in state and (
            state["current_job_id"] is not None
            and state["current_job_id"] not in {job["application_id"] for job in state["jobs"]}
            or any(job.get("workflow") != "single" for job in state["jobs"])
        ):
            raise PortalDataError(
                "worker_current_invalid", "当前岗位记录不能核验，请保留原任务和原页。", 409
            )
        if any(
            "assistance" in job
            and not valid_assistance(job["assistance"], job["application_id"])
            or not takeover_record.valid_generation_counter(job)
            or "assistance_history" in job
            and (
                not takeover_record.valid_history(job["assistance_history"])
                or any(
                    not valid_assistance(row, job["application_id"])
                    or row["status"] not in {"stopped", "released"}
                    and not takeover_record.valid_retirement(row.get("retired"))
                    for row in job["assistance_history"]
                )
            )
            for job in state["jobs"]
        ):
            raise ValueError("Invalid worker assistance metadata.")
        runtime = state.get("runtime")
        if runtime is not None:
            try:
                valid = (
                    isinstance(runtime["id"], str)
                    and bool(runtime["id"])
                    and runtime.get("applications_root") == state["applications_root"]
                    and isinstance(runtime["pid"], int)
                    and all(
                        isinstance(runtime[k], (int, float))
                        and math.isfinite(runtime[k])
                        and runtime[k] >= 0
                        for k in ("started_at", "observed_at")
                    )
                    and re.fullmatch(r"[a-f0-9]{64}", runtime["source"]["sha256"])
                    and isinstance(runtime["source"]["files"], dict)
                    and isinstance(runtime.get("capabilities", []), list)
                    and all(isinstance(value, str) for value in runtime.get("capabilities", []))
                    and bool(runtime["source"]["files"])
                    and all(
                        not Path(path).is_absolute()
                        and ".." not in Path(path).parts
                        and re.fullmatch(r"[a-f0-9]{64}", value)
                        for path, value in runtime["source"]["files"].items()
                    )
                )
            except (KeyError, TypeError):
                valid = False
            if not valid:
                raise ValueError("Invalid worker runtime.")
        return state

    def check_applications_root(self, state: dict) -> None:
        if state.get("applications_root") != str(self.applications.root):
            raise PortalDataError(
                "runtime_applications_mismatch",
                "旧运行未绑定当前投递目录。请使用独立 worker 目录；旧页面和运行记录已保留。",
                409,
            )

    def check_generic_enabled(self, job: dict, state: dict | None = None) -> None:
        if (
            job["platform"] == "generic"
            and (state or self.load()).get("generic_enabled") is not True
        ):
            raise PortalDataError("generic_disabled", "当前已关闭通用岗位自动填写。", 409)

    def single_context(self) -> dict:
        if self.single_flow_root is None or self.single_career_root is None:
            raise PortalDataError("single_context_missing", "单岗位执行尚未绑定资料目录。", 409)
        return {
            "flow_root": str(self.single_flow_root),
            "career_root": str(self.single_career_root),
            "applications_root": str(self.applications.root),
            "legacy_roots": [str(path) for path in self.legacy_roots],
        }

    def restore_single_context(self, flow_root: Path | None) -> None:
        """Restore the server-authored context only when the child has its explicit root."""
        state = self.load()
        if not any(job.get("workflow") == "single" for job in state["jobs"]):
            return
        try:
            context = state["single_context"]
            if (
                (len(state["jobs"]) != 1 and "current_job_id" not in state)
                or any(job.get("workflow") != "single" for job in state["jobs"])
                or flow_root is None
                or set(context) != {"flow_root", "career_root", "applications_root", "legacy_roots"}
                or context["applications_root"] != str(self.applications.root)
                or str(Path(flow_root).expanduser().absolute()) != context["flow_root"]
                or not isinstance(context["legacy_roots"], list)
            ):
                raise ValueError("invalid context")
            for value in (context["flow_root"], context["career_root"], *context["legacy_roots"]):
                path = Path(value)
                if not path.is_absolute() or any(
                    part.is_symlink() for part in (path, *path.parents)
                ):
                    raise ValueError("unsafe context")
            self.single_flow_root = Path(context["flow_root"])
            self.single_career_root = Path(context["career_root"])
            self.legacy_roots = tuple(Path(value) for value in context["legacy_roots"])
        except (KeyError, TypeError, ValueError) as error:
            raise PortalDataError(
                "single_context_changed", "单岗位资料目录绑定不能核验。", 409
            ) from error

    def check_single(
        self, job: dict, state: dict | None = None, *, allow_unbound=False, material_required=True
    ) -> bool:
        if job.get("workflow") != "single":
            return False
        state = self.load() if state is None else state
        if state.get("single_context") != self.single_context():
            raise PortalDataError("single_context_changed", "单岗位资料目录绑定已改变。", 409)
        validator = self.single_validator
        if validator is None:
            from .application_single_binding import check_single_binding

            validator = check_single_binding
        return validator(
            self.applications,
            self.single_flow_root,
            self.single_career_root,
            job,
            state["batch_id"],
            allow_unbound=allow_unbound,
            legacy_roots=self.legacy_roots,
            worker_root=self.root,
            material_required=material_required,
        )

    def save(self, state: dict) -> None:
        self.check_applications_root(state)
        for job in state.get("jobs", []):
            compact_observations(job)
        try:
            helper.atomic_write_json(self.path, state)
        except (OSError, ValueError, TypeError):
            self._last_write = None
            self.block_storage()
            raise
        self._last_write = None
        with suppress(OSError, TypeError, ValueError):
            info = self.path.stat()
            self._last_write = (
                _liveness_free(state),
                _liveness_values(state),
                (info.st_mtime_ns, info.st_size),
                time.monotonic(),
            )
        try:
            self.measurements.track(state)
            waiting = {
                job["application_id"] for job in state["jobs"] if job["status"] == "needs_input"
            }
            if waiting:
                for item in _input_items(state):
                    if waiting.intersection(row["id"] for row in item["jobs"]):
                        self.measurements.request_group(
                            digest([state["batch_id"], item["id"]]),
                            reason="missing_answers",
                            batch_id=state["batch_id"],
                            affected_jobs=[row["id"] for row in item["jobs"]],
                        )
        except Exception:
            logging.getLogger(__name__).warning("worker_measurement_unavailable: checkpoint saved")

    def liveness_only(self, state: dict) -> bool:
        """Whether only forward liveness timestamps changed since this store's recent write.

        An idle Worker tick rewrote the whole checkpoint every tick for a new
        heartbeat (2026-11-03); the tick then skips such a save for a short while.
        """
        written = getattr(self, "_last_write", None)
        if not written or not 0 <= time.monotonic() - written[3] < LIVENESS_SAVE_INTERVAL:
            return False
        try:
            info = self.path.stat()
            values = _liveness_values(state)
            now = time.time()
            return (
                written[2] == (info.st_mtime_ns, info.st_size)
                # The saved Worker timestamps are themselves recent: a skip never
                # leaves an older observation on disk (the backend's lease is index 1).
                and all(
                    old is None or 0 <= now - old < LIVENESS_SAVE_INTERVAL
                    for index, old in enumerate(written[1])
                    if index != 1
                )
                and len(values) == len(written[1])
                and all(
                    old is None
                    and new is None
                    or old is not None
                    and new is not None
                    and new >= old
                    for old, new in zip(written[1], values, strict=True)
                )
                and written[0] == _liveness_free(state)
            )
        except (OSError, TypeError, ValueError):
            return False

    def block_storage(self) -> None:
        self.storage_error = "checkpoint_unavailable"
        # The current process still stops if all writes are unavailable.
        with suppress(OSError):
            helper.atomic_write_json(
                self.stop_path, {"reason": self.storage_error, "at": time.time()}
            )

    def stop_reason(self) -> str:
        return self.storage_error or ("checkpoint_unavailable" if self.stop_path.exists() else "")

    def answers_for(self, application: dict | None = None):
        """Use a declared store only after checking the saved local task binding.

        Legacy jobs retain their original answer store. Web payloads never supply
        a store path; the path must agree with a checksummed task in this flow.
        Material/contact freshness remains enforced by check_single before sends.
        """
        state = self.load()
        job = application
        if job is None or "workflow" not in job:
            identifier = (
                application.get("application_id", application.get("id"))
                if application is not None
                else state.get("current_job_id")
            )
            job = next((row for row in state["jobs"] if row["application_id"] == identifier), None)
        if (job or {}).get("workflow") != "single":
            return self.answers
        binding = job.get("single_binding") or {}
        if not isinstance(binding, dict) or not isinstance(binding.get("inputs", {}), dict):
            raise PortalDataError(
                "single_information_invalid", "单岗位信息库绑定不能核验，请保留原页并核对。", 409
            )
        if not binding.get("inputs", {}).get("information_library_root"):
            return self.answers
        from .application_information import read_information_library
        from .application_single_binding import _read

        try:
            if self.single_flow_root is None or (
                state.get("single_context") is not None
                and state["single_context"] != self.single_context()
            ):
                raise ValueError("changed flow context")
            flow = _read(self.single_flow_root / "flow.json")
            if flow.get("schemaVersion") != 1 or flow.get("applications_root") != str(
                self.applications.root
            ):
                raise ValueError("unbound flow")
            task = next(row for row in flow["tasks"] if row["id"] == binding.get("task_id"))
            if (
                task.get("application_id") != job["application_id"]
                or task.get("revision")
                != digest({key: value for key, value in task.items() if key != "revision"})
                or any(
                    binding.get(key) != task.get(key)
                    for key in (
                        "inputs",
                        "analysis_id",
                        "resume_id",
                        "resume_sha256",
                        "job_binding",
                    )
                )
            ):
                raise ValueError("changed task binding")
            path = Path(task["inputs"]["information_library_root"])
            if not path.is_absolute() or read_information_library(path)["status"] != "available":
                raise ValueError("unavailable declared information")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as error:
            raise PortalDataError(
                "single_information_invalid", "单岗位信息库绑定不能核验，请保留原页并核对。", 409
            ) from error
        return helper.Store(path, legacy_profile=self.root / ".legacy-import-disabled")

    def validate_native_answers(self, expected_ref, answers):
        """Recheck initial confirmed values without refreshing the original DOM snapshot."""
        from .application_information import (
            information_context,
            read_information_library,
            validate_information_references,
        )

        try:
            _validate_native_answers(answers)
        except (TypeError, ValueError, KeyError, RecursionError) as error:
            raise PortalDataError(
                "native_answers_invalid", "原生接管的初始答案记录无效。", 409
            ) from error
        with self.applications.write_lock():
            state = self.load()
            binding = expected_ref.get("binding") if isinstance(expected_ref, dict) else None
            job = next(
                (
                    item
                    for item in state["jobs"]
                    if isinstance(binding, dict)
                    and item["application_id"] == binding.get("application_id")
                ),
                None,
            )
            assistance = (job or {}).get("assistance") or {}
            if (
                not isinstance(expected_ref, dict)
                or expected_ref.get("protocol") != CODEX_NATIVE_ASSISTANCE
                or not assistance
                or assistance.get("status") != "claimed"
                or assistance.get("active_writer") != "codex"
                or digest(assistance_reference(assistance)) != digest(expected_ref)
                or digest(assistance_binding(state, job)) != digest(binding)
                or not assistance_backend_permitted(state, assistance)
                or state["control"] != "running"
                or state.get("current_job_id") != job["application_id"]
                or job["status"] == "cancelled"
                or job.get("handed_off")
                or job.get("manual_submission")
                or material_edit_pending(job)
                or state.get("worker_error")
                or self.stop_reason()
            ):
                raise PortalDataError(
                    "native_answers_changed", "原生接管范围已改变，不能采用旧答案。", 409
                )
            selected = [fact for fact in answers["facts"] if fact["status"] == "confirmed"]
            if not selected:
                return True
            library = read_information_library(self.answers_for(job).root)
            context = information_context(
                job, library, fact_keys=[fact["fact"] for fact in selected]
            )
            try:
                for fact in selected:
                    records = validate_information_references(
                        context,
                        [{**reference, "value": fact["value"]} for reference in fact["references"]],
                    )
                    if (
                        fact["fact"] in {"sponsorship_now_future", "work_authorization_now"}
                        and job["country"] == "OTHER"
                        and not all(
                            record.get("scope", {}).get("application_id") == job["application_id"]
                            for record in records
                        )
                    ):
                        raise PortalDataError(
                            "native_answers_changed", "资格答案缺少当前申请范围。", 409
                        )
            except PortalDataError as error:
                raise PortalDataError(
                    "native_answers_changed", "已保存答案已更正、撤回、冲突或不再适用。", 409
                ) from error
            return True

    def _checked_native_material_intent(self, intent, job, expected_ref, row, call):
        """Match payload-free native identity to the existing ordinary intent schema."""
        from .cua_driver import validate_native_material_metadata

        required = {
            "action",
            "field_id",
            "draft_path",
            "material_id",
            "sha256",
            "form_protocol",
            "form_binding",
            "attempt_id",
            "run_id",
            "page_id",
            "prepared_at",
            "input_refs",
            "native_material",
        }
        if not isinstance(intent, dict) or intent.get("action") not in {"fill", "upload"}:
            raise ValueError("Invalid native material intent")
        native = intent.get("native_material")
        if (
            set(intent)
            != required | ({"expected_value"} if intent["action"] == "fill" else {"filename"})
            or not isinstance(native, dict)
            or set(native)
            != {
                "protocol",
                "request_id",
                "handoff_id",
                "call_id",
                "arguments_digest",
                "generation",
                "sequence",
                "assistance_ref_digest",
                "resolution",
            }
            or native.get("protocol") != "fixed-material/v1"
            or native.get("request_id") != row["request_id"]
            or native.get("handoff_id") != row.get("handoff_id")
            or native.get("generation") != row.get("generation")
            or native.get("assistance_ref_digest") != digest(expected_ref)
            or any(
                native.get(key) != call.get(key)
                for key in ("call_id", "arguments_digest", "generation", "sequence")
            )
            or call.get("tool") != "browser_deliver_material"
            or call.get("scope")
            != {
                "target_id": row["scope"]["native_scope"]["target_id"],
                "tab_id": row["scope"]["native_scope"]["tab_id"],
                "expected_document": row["scope"]["document"],
            }
            or intent.get("form_protocol") != "form-state/v1"
            or intent.get("form_binding") != (job.get("form_state") or {}).get("binding")
            or any(
                intent.get(key) != expected_ref["binding"].get(key) for key in ("run_id", "page_id")
            )
            or intent.get("input_refs")
            != {"revision": job["revision"], "file_sha256": job["file_sha256"]}
            or not isinstance(intent.get("attempt_id"), str)
            or re.fullmatch(r"[a-f0-9]{32}", intent["attempt_id"]) is None
            or any(
                not isinstance(intent.get(key), str) or not intent[key]
                for key in ("field_id", "material_id")
            )
            or not isinstance(intent.get("draft_path"), str)
            or type(intent.get("prepared_at")) not in (int, float)
            or not math.isfinite(intent["prepared_at"])
            or intent["prepared_at"] <= 0
            or not isinstance(native.get("resolution"), dict)
        ):
            raise ValueError("Native material intent identity changed")
        manifest = native["resolution"]
        validate_native_material_metadata({**call, "material_resolution": manifest})
        if (
            call.get("material_resolution", manifest) != manifest
            or manifest["sha256"] != intent["sha256"]
            or manifest["kind"] != ("text" if intent["action"] == "fill" else "file")
            or call["target_descriptor"]["draft_path"] != intent["draft_path"]
            or call["target_descriptor"]["type"]
            not in ({"text", "textarea"} if intent["action"] == "fill" else {"file"})
        ):
            raise ValueError("Native material seal changed")
        if intent["action"] == "fill":
            if not isinstance(intent["expected_value"], str):
                raise ValueError("Invalid material text intent")
            raw = intent["expected_value"].encode()
            if (
                len(raw) != manifest["size_bytes"]
                or hashlib.sha256(raw).hexdigest() != manifest["sha256"]
            ):
                raise ValueError("Material text intent changed")
        elif intent["filename"] != manifest["filename"]:
            raise ValueError("Material file intent changed")
        return intent

    @staticmethod
    def _native_material_call_follows(previous, current):
        return bool(
            all(previous[key] == current.get(key) for key in previous if key != "status")
            and current.get("status")
            in {
                "awaiting_host": {"awaiting_host", "in_flight", "observed", "not_sent", "unknown"},
                "in_flight": {"in_flight", "observed", "unknown"},
                "observed": {"observed"},
                "not_sent": {"not_sent"},
                "unknown": {"unknown"},
            }.get(previous.get("status"), set())
        )

    def native_material_intent(self, state, job, expected_ref, *, request_id=None, call=None):
        """Return only this current job's original native material intent, or False."""
        try:
            current = next(
                row
                for row in state["jobs"]
                if row["application_id"] == expected_ref["binding"]["application_id"]
            )
            intent = job.get("intent")
            native = (intent or {}).get("native_material") or {}
            request_id = request_id or native.get("request_id")
            if (
                current != job
                or state.get("current_job_id") != job["application_id"]
                or expected_ref.get("protocol") != CODEX_NATIVE_ASSISTANCE
                or assistance_reference(job.get("assistance") or {}) != expected_ref
                or assistance_binding(state, job) != expected_ref["binding"]
            ):
                return False
            runs = job.get("native_handoff_runs", [])
            _validate_native_handoff_runs(runs)
            matching = [
                row
                for row in runs
                if row["request_id"] == request_id and row["assistance_ref"] == expected_ref
            ]
            if len(matching) != 1:
                return False
            row = matching[0]
            latest = {
                saved["call_id"]: saved
                for event in row["events"]
                for saved in (event["receipt"] or {}).get("calls", [])
            }.get(native.get("call_id"))
            if latest is None:
                return False
            self._checked_native_material_intent(intent, job, expected_ref, row, latest)
            if call is not None:
                self._checked_native_material_intent(intent, job, expected_ref, row, call)
                if not self._native_material_call_follows(latest, call):
                    return False
            return deepcopy(intent)
        except (PortalDataError, KeyError, TypeError, ValueError, StopIteration, UnicodeError):
            return False

    def record_native_handoff(
        self,
        expected_ref,
        *,
        request_id,
        phase,
        scope,
        receipt=None,
        expected_worker_source=None,
        material_intent=None,
    ):
        """Conditionally journal one native execution; never grant, retry or change control."""
        if (
            not isinstance(request_id, str)
            or not 1 <= len(request_id) <= 128
            or not request_id.isprintable()
            or not isinstance(phase, str)
            or phase not in {"prepared", "granted", "stopping", "stopped", "unknown"}
            or not isinstance(expected_ref, dict)
            or expected_ref.get("protocol") != CODEX_NATIVE_ASSISTANCE
            or not isinstance(scope, dict)
            or set(scope) != {"native_scope", "document"}
            or material_intent is not None
            and (not isinstance(material_intent, dict) or phase != "granted")
        ):
            raise PortalDataError("native_handoff_invalid", "原生交接执行范围无效。", 409)
        try:
            validate_native_assistance_scope(scope["native_scope"], expected_ref)
        except ValueError as error:
            raise PortalDataError(
                "native_handoff_invalid", "原生交接的原页范围不能核验。", 409
            ) from error
        document = scope["document"]
        if (
            not isinstance(document, dict)
            or set(document) != {"frame_id", "loader_id", "url"}
            or any(not isinstance(v, str) or not v or len(v) > 20_000 for v in document.values())
            or urldefrag(document["url"])[0] != urldefrag(expected_ref["binding"]["step"])[0]
        ):
            raise PortalDataError("native_handoff_invalid", "原生交接文档范围已改变。", 409)
        sanitized = _native_handoff_receipt(receipt)
        with self.applications.write_lock():
            state = self.load()
            job = next(
                (
                    row
                    for row in state["jobs"]
                    if row["application_id"] == expected_ref["binding"]["application_id"]
                ),
                None,
            )
            if job is None:
                raise PortalDataError("native_handoff_scope_changed", "原交接岗位不存在。", 409)
            runs = job.get("native_handoff_runs", [])
            _validate_native_handoff_runs(runs)
            matching = [row for row in runs if row.get("request_id") == request_id]
            if len(matching) > 1:
                raise PortalDataError("native_handoff_invalid", "原生交接记录不唯一。", 409)
            row = matching[0] if matching else None
            if row is not None and (
                row.get("assistance_ref") != expected_ref or row.get("scope") != scope
            ):
                raise PortalDataError("native_handoff_conflict", "原交接标识不能更换范围。", 409)
            assistance = job.get("assistance") or {}
            runtime = state.get("runtime") or {}
            now = time.time()
            retained_material = (
                self.native_material_intent(state, job, expected_ref, request_id=request_id)
                if job.get("intent")
                else False
            )
            carried = takeover_pending_intent(job)
            current = bool(
                assistance
                and digest(assistance_reference(assistance)) == digest(expected_ref)
                and digest(assistance_binding(state, job)) == digest(expected_ref["binding"])
                and assistance.get("status") == "claimed"
                and assistance.get("active_writer") == "codex"
                and assistance_backend_permitted(state, assistance)
                and state["control"] == "running"
                and state.get("current_job_id") == job["application_id"]
                and job["status"] != "cancelled"
                and not job.get("handed_off")
                and not job.get("manual_submission")
                and not material_edit_pending(job)
                and not state.get("worker_error")
                and not self.stop_reason()
                and (not job.get("intent") or retained_material or carried)
                and not state["commands"]
                and not manual_submission_unresolved(job)
                and not any(
                    unresolved_write_failure(event, job, state)
                    and not (
                        carried
                        and isinstance(event.get("intent"), dict)
                        and digest(event["intent"]) == carried
                    )
                    for event in job["observations"]
                )
                and PAGE_SCOPE.current(state, job, now).valid
            )
            if phase == "prepared":
                from .cua_driver import reviewed_native_assistance_policy

                policy = reviewed_native_assistance_policy()
                if (
                    not current
                    or not isinstance(expected_worker_source, str)
                    or re.fullmatch(r"[a-f0-9]{64}", expected_worker_source) is None
                    or expected_worker_source != runtime.get("source", {}).get("sha256")
                    or digest(policy) != expected_ref.get("native_policy_digest")
                    or receipt is not None
                ):
                    raise PortalDataError(
                        "native_handoff_scope_changed", "原生交接派发前范围已改变。", 409
                    )
                if row is not None:
                    if (
                        row.get("phase") != "prepared"
                        or row.get("semantic_unknown")
                        or row.get("worker_source") != expected_worker_source
                    ):
                        raise PortalDataError(
                            "native_handoff_unresolved", "原交接已有结果，不能重新派发。", 409
                        )
                    return deepcopy(row)
                if any(
                    previous.get("phase") != "stopped" or previous.get("semantic_unknown")
                    for previous in runs
                ):
                    raise PortalDataError(
                        "native_handoff_unresolved", "前次原生交接尚未停止或结果仍未知。", 409
                    )
                row = {
                    "request_id": request_id,
                    "assistance_ref": deepcopy(expected_ref),
                    "scope": deepcopy(scope),
                    "worker_source": expected_worker_source,
                    "phase": "prepared",
                    "semantic_unknown": False,
                    "created_at": now,
                    "events": [{"phase": "prepared", "at": now, "receipt": None}],
                }
                job.setdefault("native_handoff_runs", []).append(row)
                self.save(state)
                return deepcopy(row)
            if row is None:
                raise PortalDataError("native_handoff_missing", "没有该原生交接的已保存意图。", 409)
            if material_intent is not None:
                try:
                    if (
                        not current
                        or job.get("intent")
                        or phase != "granted"
                        or row["phase"] != "granted"
                        or row["semantic_unknown"]
                        or row.get("worker_source") != runtime.get("source", {}).get("sha256")
                    ):
                        raise ValueError("Material admission is not current")
                    candidate_calls = [
                        call
                        for call in (sanitized or {}).get("calls", [])
                        if call.get("call_id")
                        == material_intent.get("native_material", {}).get("call_id")
                    ]
                    if len(candidate_calls) != 1:
                        raise ValueError("Material awaiting call is not unique")
                    candidate = candidate_calls[0]
                    if (
                        candidate["status"] != "awaiting_host"
                        or "material_resolution" in candidate
                        or "material_readback" in candidate
                    ):
                        raise ValueError("Material call already dispatched")
                    self._checked_native_material_intent(
                        material_intent, job, expected_ref, row, candidate
                    )
                    calls = {
                        call["call_id"]: call
                        for event in row["events"]
                        for call in (event["receipt"] or {}).get("calls", [])
                    }
                    calls.update(
                        {call["call_id"]: call for call in (sanitized or {}).get("calls", [])}
                    )
                    if any(
                        call["mutation"]
                        and call["status"] in {"awaiting_host", "in_flight", "unknown"}
                        and call["call_id"] != candidate["call_id"]
                        for call in calls.values()
                    ):
                        raise ValueError("Another mutation remains unresolved")
                    fields = [
                        q
                        for q in (job.get("form_state", {}).get("snapshot") or {}).get("fields", [])
                        if q.get("id") == material_intent["field_id"]
                        and q.get("draft_path", "") == material_intent["draft_path"]
                    ]
                    if (
                        len(fields) != 1
                        or fields[0].get("control_ids")
                        != [candidate["target_descriptor"]["worker_field"]]
                        or fields[0].get("type") != candidate["target_descriptor"]["type"]
                    ):
                        raise ValueError("Material destination changed")
                    entries = [
                        entry
                        for entry in self.assistance_delivery(expected_ref)["materials"]
                        if entry.get("material_ref") == candidate["material_ref"]
                    ]
                    if (
                        len(entries) != 1
                        or (
                            "resume"
                            if entries[0]["kind"] == "resume"
                            else entries[0].get("material_id")
                        )
                        != material_intent["material_id"]
                    ):
                        raise ValueError("Fixed material is no longer ready")
                    if material_intent["material_id"] == "resume":
                        from .application_materials import material_kind

                        raw = self._read_bound_resume(job, state["batch_id"])
                        if (
                            material_intent["action"] != "upload"
                            or material_intent["filename"] != job["filename"]
                            or material_kind(fields[0]) != "resume"
                        ):
                            raise ValueError("Resume delivery changed")
                    else:
                        material = next(
                            item
                            for item in job.get("materials", [])
                            if item.get("id") == material_intent["material_id"]
                        )
                        if (
                            material.get("field_id") != material_intent["field_id"]
                            or material.get("draft_path", "") != material_intent["draft_path"]
                        ):
                            raise ValueError("Material field changed")
                        raw = (
                            material["text"].encode()
                            if material_intent["action"] == "fill"
                            else self._read_bound_material_file(
                                Path(material["file_path"]), material["sha256"]
                            )
                        )
                        if (
                            material_intent["action"] == "upload"
                            and material_intent["filename"] != material["filename"]
                        ):
                            raise ValueError("Material filename changed")
                    manifest = material_intent["native_material"]["resolution"]
                    if (
                        hashlib.sha256(raw).hexdigest() != manifest["sha256"]
                        or len(raw) != manifest["size_bytes"]
                    ):
                        raise ValueError("Fixed material payload changed")
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                    StopIteration,
                    OSError,
                    UnicodeError,
                ) as error:
                    raise PortalDataError(
                        "native_material_intent_invalid", "原生材料发送意图不能核验。", 409
                    ) from error
            if phase == "granted" and row.get("phase") not in {"prepared", "granted"}:
                raise PortalDataError(
                    "native_handoff_unresolved", "旧交接已撤销或结果未知，不能恢复写者。", 409
                )
            if sanitized is not None:
                if (
                    phase == "granted"
                    and row.get("semantic_unknown")
                    and any(
                        call["mutation"] and call["status"] == "awaiting_host"
                        for call in sanitized.get("calls", [])
                    )
                ):
                    raise PortalDataError(
                        "native_handoff_unresolved", "原生动作结果未明，不能允许后续写入。", 409
                    )
                previous_calls = {
                    call["call_id"]: call
                    for old_event in row["events"]
                    for call in (old_event["receipt"] or {}).get("calls", [])
                }
                for call in sanitized.get("calls", []):
                    if call["scope"] != {
                        "target_id": scope["native_scope"]["target_id"],
                        "tab_id": scope["native_scope"]["tab_id"],
                        "expected_document": scope["document"],
                    }:
                        raise PortalDataError(
                            "native_handoff_conflict", "原生调用不属于原页交接范围。", 409
                        )
                    old_call = previous_calls.get(call["call_id"])
                    if old_call and (
                        not self._native_material_call_follows(old_call, call)
                        if old_call["tool"] == "browser_deliver_material"
                        else any(
                            old_call[key] != call.get(key) for key in old_call if key != "status"
                        )
                    ):
                        raise PortalDataError(
                            "native_handoff_conflict", "原生调用标识不能更换参数或代次。", 409
                        )
                    protected = (job.get("intent") or {}).get("native_material") or {}
                    protected_call = (
                        protected.get("protocol") == "fixed-material/v1"
                        and protected.get("request_id") == request_id
                        and protected.get("assistance_ref_digest") == digest(expected_ref)
                        and protected.get("handoff_id") == row.get("handoff_id")
                        and all(
                            protected.get(key) == call.get(key)
                            for key in ("call_id", "arguments_digest", "generation", "sequence")
                        )
                    )
                    if protected_call and call.get(
                        "material_resolution", protected.get("resolution")
                    ) != protected.get("resolution"):
                        raise PortalDataError(
                            "native_handoff_conflict", "原生材料封存身份不能更换。", 409
                        )
                    if (
                        call["tool"] == "browser_deliver_material"
                        and "material_resolution" in call
                        and not protected_call
                        and not native_unparsed_resume_resolution(job, call)
                        and (old_call or {}).get("material_resolution")
                        != call["material_resolution"]
                    ):
                        raise PortalDataError(
                            "native_material_intent_missing",
                            "原生材料调用缺少已保存的发送意图。",
                            409,
                        )
                for key in ("handoff_id", "generation"):
                    if key in row and key in sanitized and row[key] != sanitized[key]:
                        raise PortalDataError(
                            "native_handoff_conflict", "原生交接回执身份已改变。", 409
                        )
                if phase == "granted" and not (
                    "handoff_id" in sanitized
                    and "generation" in sanitized
                    and (
                        row.get("phase") == "granted"
                        or sanitized.get("local_tools_drained") is True
                    )
                ):
                    raise PortalDataError(
                        "native_handoff_receipt_invalid", "原生交接授权回执不完整。", 409
                    )
            elif phase in {"granted", "stopped"}:
                raise PortalDataError(
                    "native_handoff_receipt_invalid", "原生交接结果需要实际回执。", 409
                )
            if phase == "stopped" and not _native_stop_proven(sanitized):
                raise PortalDataError("native_handoff_not_drained", "原生调用尚未真正排空。", 409)
            late_grant = phase == "granted" and (
                not current or row.get("worker_source") != runtime.get("source", {}).get("sha256")
            )
            actual_phase = "unknown" if late_grant else phase
            if row.get("phase") == "stopped" and phase == "stopping":
                if _native_stop_proven(sanitized):
                    actual_phase = "stopped"
                elif any(
                    call["mutation"] and call["status"] == "unknown"
                    for call in (sanitized or {}).get("calls", [])
                ):
                    actual_phase = "unknown"
                else:
                    return deepcopy(row)
            semantic_unknown = (
                row.get("semantic_unknown", False)
                or actual_phase == "unknown"
                or any(
                    call["mutation"] and call["status"] == "unknown"
                    for call in (sanitized or {}).get("calls", [])
                )
            )
            event = {"phase": actual_phase, "receipt": sanitized}
            previous_event = row["events"][-1]
            if event == {
                k: previous_event[k] for k in ("phase", "receipt")
            } and semantic_unknown == row.get("semantic_unknown"):
                if material_intent is not None:
                    job["intent"] = deepcopy(material_intent)
                    self.save(state)
                return deepcopy(row)
            row["phase"] = actual_phase
            row["semantic_unknown"] = semantic_unknown
            if sanitized:
                row.update(
                    {
                        key: sanitized[key]
                        for key in ("handoff_id", "generation")
                        if key in sanitized
                    }
                )
            row["events"].append({**event, "at": now})
            if len(json.dumps(row, allow_nan=False).encode()) > 512_000:
                raise PortalDataError(
                    "native_handoff_receipt_invalid", "原生交接历史超过本次回执上限。", 409
                )
            for call in (sanitized or {}).get("calls", []):
                if (
                    call["mutation"]
                    and call["status"] == "unknown"
                    and not any(
                        old.get("action") == "native_handoff_unknown"
                        and old.get("request_id") == request_id
                        and old.get("call_id") == call["call_id"]
                        for old in job["observations"]
                    )
                ):
                    job["observations"].append(
                        {
                            "action": "native_handoff_unknown",
                            "request_id": request_id,
                            "call_id": call["call_id"],
                            "native_tool": call["tool"],
                            "arguments_digest": call["arguments_digest"],
                            "handoff_id": (sanitized or {}).get("handoff_id"),
                            "generation": call["generation"],
                            "at": now,
                        }
                    )
            if material_intent is not None:
                job["intent"] = deepcopy(material_intent)
            self.save(state)
            if late_grant:
                raise PortalDataError(
                    "native_handoff_scope_changed", "交接期间范围已改变，必须撤销原生授权。", 409
                )
            return deepcopy(row)

    def _native_assistance_answers(self, job, page_context):
        """Deliver only current DOM-relevant saved facts, with their original references."""
        from .application_information import (
            CONTACT_FACTS,
            information_context,
            information_fact,
            read_information_library,
            validate_information_references,
        )

        selected = {}
        for field in (page_context.get("data") or {}).get("fields", []):
            if (
                field.get("type") in {"password", "hidden", "file"}
                or field.get("visible") is False
                or field.get("disabled") is True
            ):
                continue
            label = field.get("label") or ""
            name = field.get("name") or field.get("id") or ""
            # A choice's own text ("Yes") is an option; its group's question is the fact.
            candidates = [
                text
                for text in (field.get("question") or "", label, name.replace("_", " "))
                if text.strip() and helper.normalize_question(text)
            ]
            if not candidates:
                continue
            facts = [_native_label_fact(text, information_fact) for text in candidates]
            fact = next((f for f in facts if not f.startswith("question:")), facts[0])
            if not label and name in CONTACT_FACTS:
                fact = name
            selected.setdefault(fact, []).append(field.get("id", ""))
        if len(selected) > 64:
            raise PortalDataError("assistance_answer_limit", "当前页面事实范围超过交接上限。", 409)
        if not selected:
            result = {"library_status": "not_requested", "facts": []}
            return {**result, "revision": digest(result)}
        library = read_information_library(self.answers_for(job).root)
        context = information_context(job, library, fact_keys=list(selected))
        facts = []
        for item in context["facts"]:
            row = {
                "fact": item["fact"],
                "field_ids": selected[item["fact"]],
                "status": item["status"],
            }
            if library["status"] != "available":
                row["status"] = "source_unavailable"
            elif item["status"] == "confirmed":
                references = [{**ref, "fact": item["fact"]} for ref in item["references"]]
                records = validate_information_references(context, references)
                if (
                    item["fact"] in {"sponsorship_now_future", "work_authorization_now"}
                    and job["country"] == "OTHER"
                    and not all(
                        record.get("scope", {}).get("application_id") == job["application_id"]
                        for record in records
                    )
                ):
                    row["status"] = "scope_required"
                elif (
                    not isinstance(item["value"], str)
                    or not item["value"].strip()
                    or len(item["value"]) > 20_000
                ):
                    row["status"] = "unsupported_value"
                else:
                    row.update(value=item["value"], references=references)
            facts.append(row)
        result = {"library_status": library["status"], "facts": facts}
        return {**result, "revision": digest(result)}

    def assistance_delivery(self, expected_ref, *, page_context=None):
        """Project JSON context from the original records; never observe, save or dispatch."""
        with self.applications.write_lock():
            state = self.load()
            binding = expected_ref.get("binding") if isinstance(expected_ref, dict) else None
            job = next(
                (
                    row
                    for row in state["jobs"]
                    if isinstance(binding, dict)
                    and row["application_id"] == binding.get("application_id")
                ),
                None,
            )
            assistance = (job or {}).get("assistance")
            runtime = state.get("runtime") or {}
            now = time.time()
            if (
                not assistance
                or assistance.get("status") not in {"requested", "claimed"}
                or digest(assistance_reference(assistance)) != digest(expected_ref)
                or digest(assistance_binding(state, job)) != digest(binding)
                or not assistance_backend_permitted(state, assistance)
                or state["control"] != "running"
                or state.get("current_job_id") != job["application_id"]
                or job["status"] == "cancelled"
                or job.get("handed_off")
                or job.get("manual_submission")
                or material_edit_pending(job)
                or state.get("worker_error")
                or self.stop_reason()
                or not PAGE_SCOPE.current(state, job, now).valid
            ):
                raise PortalDataError(
                    "assistance_binding_changed",
                    "原页、材料或接管范围已改变，不能交付旧上下文。",
                    409,
                )
            context = (
                deepcopy(page_context)
                if page_context is not None
                else {"status": "unavailable", "binding": deepcopy(binding)}
            )
            if page_context is not None:
                try:
                    _validate_assistance_page_context(context, expected_ref)
                except ValueError as error:
                    raise PortalDataError(
                        "assistance_context_invalid", "当前原页的 JSON 上下文不能核验。", 409
                    ) from error
                if context["worker_source"] != runtime["source"]["sha256"]:
                    raise PortalDataError(
                        "assistance_context_invalid", "页面上下文的执行源码身份已改变。", 409
                    )
            form = job.get("form_state") or {}
            fields = (context.get("data") or {}).get("fields", [])
            field_source = "current_page"
            if page_context is None:
                fields = (form.get("snapshot") or {}).get("fields", [])
                field_source = "saved_form_snapshot"
            remaining = []
            remaining_ids = set()
            for field in fields:
                if (
                    field.get("valid") is False
                    or field.get("aria_invalid") not in (None, "", "false")
                    or field.get("required") is True
                    and field.get("value") in (None, "", [])
                ):
                    hint = {
                        key: deepcopy(field[key])
                        for key in ("id", "name", "role", "label", "question", "type")
                        if key in field
                    }
                    identity = ("id", hint["id"]) if hint.get("id") else ("hint", digest(hint))
                    if identity not in remaining_ids:
                        remaining_ids.add(identity)
                        remaining.append(
                            {
                                "field_hint": hint,
                                "status": "needs_inspection",
                                "source": field_source,
                            }
                        )
            for error in (context.get("data") or {}).get("validation_errors", []):
                hint = deepcopy(error["field_hint"])
                identity = ("id", hint["id"]) if hint.get("id") else ("hint", digest(hint))
                if identity not in remaining_ids:
                    remaining_ids.add(identity)
                    remaining.append(
                        {"field_hint": hint, "status": "needs_inspection", "source": field_source}
                    )
            results = effective_action_results(job)
            completed = []
            pending = {}

            def action_row(intent, source):
                return {
                    "action_id": intent.get("attempt_id") or digest(intent),
                    "kind": intent.get("action"),
                    "field_id": intent.get("field_id"),
                    "scope": {
                        key: deepcopy(intent[key])
                        for key in ("run_id", "page_id", "document_token", "form_binding")
                        if key in intent
                    },
                    "source_ref": source,
                }

            for action_id, result in results.items():
                if result.get("conclusion") != "current_matches":
                    continue
                intent = result["intent"]
                form_binding = intent.get("form_binding") or {}
                scope = {
                    key: intent.get(key, form_binding.get(key))
                    for key in ("run_id", "page_id", "document_token")
                }
                foreign = any(
                    scope[key] is not None and scope[key] != binding[key] for key in scope
                )
                foreign = (
                    foreign
                    or "form_binding" in intent
                    and intent["form_binding"] != form.get("binding")
                    or "step" in intent
                    and intent["step"] != binding["step"]
                    or any(
                        key in intent and intent[key] != binding[key]
                        for key in ("material_revision", "answer_revision")
                    )
                    or intent.get("sha256", job["file_sha256"]) != job["file_sha256"]
                )
                current_scope = not foreign and all(scope[key] == binding[key] for key in scope)
                readback = False
                if current_scope and page_context is not None and intent.get("action") == "fill":
                    from .application_form_state import equivalent

                    matching = [
                        field for field in fields if field.get("id") == intent.get("field_id")
                    ]
                    readback = bool(
                        len(matching) == 1
                        and "expected_value" in intent
                        and matching[0].get("valid") is not False
                        and matching[0].get("aria_invalid") in (None, "", "false")
                        and equivalent(
                            matching[0], matching[0].get("value"), intent["expected_value"]
                        )
                    )
                completed.append(
                    {
                        **action_row(
                            intent, {"record": "effective_action_results", "action_id": action_id}
                        ),
                        "status": "historical_verified"
                        if foreign
                        else "verified"
                        if current_scope and readback
                        else "verified_scope_unknown",
                        "current_scope": current_scope,
                    }
                )
            for index, event in enumerate(job["observations"]):
                intent = event.get("intent")
                if not isinstance(intent, dict):
                    continue
                action_id = intent.get("attempt_id") or digest(intent)
                if action_id not in results and (
                    failed_write(event)
                    or event.get("action") in {"late_fill_result", "late_action_result"}
                    or event.get("result") == "unknown"
                ):
                    pending[action_id] = {
                        **action_row(intent, {"record": "observations", "index": index}),
                        "status": "unknown",
                        "reason": event.get("reason") or event.get("stage") or "unverified_result",
                    }
            intent = job.get("intent")
            if intent is not None:
                action_id = intent.get("attempt_id") or digest(intent)
                if action_id not in results:
                    pending[action_id] = {
                        **action_row(intent, {"record": "intent"}),
                        "status": "unknown",
                        "reason": "saved_intent_without_verified_result",
                    }
            if expected_ref.get("protocol") == CODEX_NATIVE_ASSISTANCE:
                runs = job.get("native_handoff_runs", [])
                _validate_native_handoff_runs(runs)
                for run_index, native_run in enumerate(runs):
                    latest_calls = {}
                    for event_index, native_event in enumerate(native_run["events"]):
                        for call in (native_event["receipt"] or {}).get("calls", []):
                            latest_calls[call["call_id"]] = (event_index, call)
                    scope = deepcopy(native_run["scope"])
                    scope["assistance_ref_digest"] = digest(native_run["assistance_ref"])
                    current_scope = bool(
                        native_run["assistance_ref"] == expected_ref
                        and context.get("status") == "captured"
                        and native_run["scope"]["document"] == context.get("document")
                    )
                    for call_id, (event_index, call) in latest_calls.items():
                        if call["status"] not in {"awaiting_host", "in_flight", "unknown"}:
                            continue
                        pending[f"native:{native_run['request_id']}:{call_id}"] = {
                            "action_id": f"native:{native_run['request_id']}:{call_id}",
                            "kind": "native_call",
                            "call_id": call_id,
                            "status": call["status"],
                            "native_tool": call["tool"],
                            "semantic_verified": False,
                            "handoff_id": native_run.get("handoff_id"),
                            "generation": call["generation"],
                            "scope": scope,
                            "current_scope": current_scope,
                            "field_hint": deepcopy(call.get("field_hint")),
                            "source_ref": {
                                "record": "native_handoff_runs",
                                "index": run_index,
                                "event_index": event_index,
                                "call_id": call_id,
                            },
                        }
                    if (
                        native_run["phase"] in {"prepared", "unknown"}
                        or native_run["semantic_unknown"]
                    ) and not any(
                        call["status"] in {"in_flight", "unknown"}
                        for _, call in latest_calls.values()
                    ):
                        pending[f"native:{native_run['request_id']}"] = {
                            "action_id": f"native:{native_run['request_id']}",
                            "kind": "native_handoff",
                            "status": "unknown",
                            "scope": scope,
                            "current_scope": current_scope,
                            "handoff_id": native_run.get("handoff_id"),
                            "generation": native_run.get("generation"),
                            "source_ref": {"record": "native_handoff_runs", "index": run_index},
                        }
            materials = [
                {
                    "kind": "resume",
                    "sha256": job["file_sha256"],
                    "filename": job["filename"],
                    "source_ref": {"record": "job", "field": "file_sha256"},
                    "binding_revision": binding["material_revision"],
                }
            ]
            materials.extend(
                {
                    "kind": item.get("kind"),
                    "material_id": item.get("id"),
                    "field_id": item.get("field_id"),
                    "status": "ready",
                    "revision": digest(item),
                    "source_ref": {"record": "materials", "index": index},
                }
                for index, item in enumerate(job.get("materials", []))
                if item.get("status") == "ready"
            )
            if expected_ref.get("protocol") == CODEX_NATIVE_ASSISTANCE:
                materials = self._native_material_catalog(job, expected_ref, materials)
            blocker = {
                "code": job.get("reason")
                or (form.get("parser") or {}).get("reason")
                or "script_blocked",
                "message": "脚本需要接续处理当前原页；操作前核对当前控件与已有内容。",
                "field_hint": deepcopy(remaining[0]["field_hint"]) if remaining else None,
            }
            delivery = {
                "schema_version": 1,
                "assistance_ref": deepcopy(expected_ref),
                "progress": {"completed": completed, "remaining": remaining},
                "blocker": blocker,
                "pending_actions": list(pending.values()),
                "page_context": context,
                "materials": materials,
                "next_step": {
                    "kind": "complete_remaining_fields"
                    if job.get("assistance_return_count", 0) >= 1
                    else "reconcile_pending_actions"
                    if pending
                    else "inspect_control_and_continue",
                    "field_id": (blocker["field_hint"] or {}).get("id"),
                },
            }
            if expected_ref.get("protocol") == CODEX_NATIVE_ASSISTANCE:
                delivery["answers"] = self._native_assistance_answers(job, context)
            try:
                validate_assistance_delivery(delivery, expected_ref)
            except ValueError as error:
                # The private worker log keeps which check refused; the job keeps the code.
                print(
                    "assistance_delivery_invalid: "
                    + json.dumps(
                        {
                            "check": str(error),
                            "bytes": len(json.dumps(delivery, ensure_ascii=False, default=str)),
                            "fields": len((context.get("data") or {}).get("fields", [])),
                            "remaining": len(remaining),
                            "completed": len(completed),
                            "pending": len(pending),
                            "facts": len((delivery.get("answers") or {}).get("facts", [])),
                        }
                    ),
                    flush=True,
                )
                raise PortalDataError(
                    "assistance_delivery_invalid", "当前岗位的 JSON 交接记录不能核验。", 409
                ) from error
            return delivery

    def _native_material_catalog(self, job, expected_ref, materials):
        """Add opaque fixed-delivery tokens and preserve non-actionable preparation states."""
        from .application_materials import KNOWN_COVER_LETTER_PDF_FAILURES

        projection = job.get("cover_letter_delivery") or {}
        requirements = {
            "requirement": projection.get("requirement"),
            "selected_fields": deepcopy(projection.get("selected_fields", [])),
            "fields": [
                {
                    key: deepcopy(field[key])
                    for key in ("field_id", "draft_path", "method", "required", "selected")
                    if key in field
                }
                for field in projection.get("fields", [])
            ],
        }
        fixed = None
        if job.get("workflow") == "single" and (
            projection or any(row.get("letter_content") for row in job.get("materials", []))
        ):
            fixed = self.material_inputs(job)
        branch = (fixed or {}).get("cover_letter") or {}
        consistency = None
        if fixed is not None:
            from .application_materials import material_consistency_status

            consistency = material_consistency_status(fixed)
        materials.extend(
            {
                "kind": item.get("kind"),
                "material_id": item.get("id"),
                "field_id": item.get("field_id"),
                "status": item.get("status"),
                "reason": item.get("error_code") or item.get("status") or "material_not_ready",
                "revision": digest(item),
                "source_ref": {"record": "materials", "index": index},
            }
            for index, item in enumerate(job.get("materials", []))
            if item.get("status") != "ready"
        )
        for entry in materials:
            entry.setdefault("status", "ready")
            if entry["kind"] == "cover_letter":
                entry.update(deepcopy(requirements))
                original = job["materials"][entry["source_ref"]["index"]]
                entry.update(
                    required=original.get("required"), draft_path=original.get("draft_path", "")
                )
                if projection.get("reason") == "retained_page":
                    entry.update(status="manual", reason="retained_page")
                elif branch and branch.get("status") != "ready":
                    entry.update(
                        status=branch.get("status") or "waiting",
                        reason=branch.get("error_code") or "cover_letter_pending",
                    )
                elif consistency in {"queued", "running"}:
                    entry.update(status=consistency, reason="material_consistency_pending")
                elif projection.get("status") in {"failed", "needs_input", "needs_recheck"}:
                    entry.update(
                        status=projection["status"],
                        reason=projection.get("reason") or "material_not_ready",
                    )
                elif original.get("letter_content") and (
                    branch.get("result", {}).get("content_revision")
                    != original.get("content_revision")
                ):
                    entry.update(status="waiting", reason="material_changed")
                if (
                    entry["status"] == original.get("status") == "failed"
                    and original.get("letter_content")
                    and original.get("error_code") in KNOWN_COVER_LETTER_PDF_FAILURES
                    and (
                        original["error_code"] != "cover_letter_file_limit_invalid"
                        or original.get("file_build_started") is False
                    )
                ):
                    entry["recovery"] = {
                        "operation": "retry-cover-letter-file",
                        "inputs": {
                            "application_id": job["application_id"],
                            "material_id": original["id"],
                            "expected_material_revision": digest(original),
                        },
                        "requires_paused": True,
                        "requires_no_unknown_actions": True,
                        "requires_native_handoff_returned": True,
                        "requires_request_id": True,
                    }
            if entry["status"] == "ready":
                try:
                    if entry["kind"] == "resume":
                        self.check_single(job, material_required=True)
                        self._read_bound_resume(job, expected_ref["binding"]["batch_id"])
                    else:
                        original = job["materials"][entry["source_ref"]["index"]]
                        self.verify_material_source(original)
                        self.verify_material(original, job)
                        if original.get("file_path"):
                            self._read_bound_material_file(
                                Path(original["file_path"]), original["sha256"]
                            )
                except (PortalDataError, OSError, ValueError, TypeError, KeyError) as error:
                    entry.update(
                        status="needs_recheck", reason=getattr(error, "code", "material_changed")
                    )
                else:
                    entry["material_ref"] = digest(
                        {"assistance_ref": expected_ref, "material": entry}
                    )
        if projection and not any(row["kind"] == "cover_letter" for row in materials):
            status = projection.get("status") or branch.get("status") or "waiting"
            reason = projection.get("reason") or branch.get("error_code")
            if reason == "retained_page":
                status = "manual"
            elif not projection.get("selected_fields"):
                status, reason = "unavailable", "no_delivery_field"
            elif status == "ready":
                status, reason = "waiting", "material_not_ready"
            materials.append(
                {
                    "kind": "cover_letter",
                    "status": status,
                    "reason": reason or "cover_letter_pending",
                    "source_ref": {"record": "cover_letter_delivery"},
                    **deepcopy(requirements),
                }
            )
        for entry in materials:
            if entry["kind"] == "cover_letter" and entry["status"] in {"unknown", "needs_recheck"}:
                entry["recovery"] = {
                    "description": "请核对原尝试及其已有结果；结果未知时不会重新生成或重新发送。",
                }
                if entry.get("material_id") is not None:
                    entry["recovery"].update(
                        material_id=entry["material_id"],
                        expected_material_revision=entry["revision"],
                    )
        return materials

    def resolve_bound_material(self, expected_ref, material_ref, *, question, page_context):
        """Read one fixed delivery for an owner-observed field, without preparing it."""
        from .application_materials import (
            check_cover_letter_file,
            check_cover_letter_text,
            material_kind,
        )

        with self.applications.write_lock():
            delivery = self.assistance_delivery(expected_ref, page_context=page_context)
            if (
                expected_ref.get("protocol") != CODEX_NATIVE_ASSISTANCE
                or not isinstance(material_ref, str)
                or re.fullmatch(r"[a-f0-9]{64}", material_ref) is None
            ):
                raise PortalDataError("material_reference_invalid", "固定材料引用不能核验。", 409)
            matching = [
                row for row in delivery["materials"] if row.get("material_ref") == material_ref
            ]
            if len(matching) != 1:
                raise PortalDataError("material_reference_invalid", "固定材料引用已改变。", 409)
            entry = matching[0]
            if (
                not isinstance(question, dict)
                or any(
                    not isinstance(question.get(key), str) or not question[key]
                    for key in ("id", "question", "type")
                )
                or not isinstance(question.get("draft_path", ""), str)
                or not isinstance(page_context, dict)
                or page_context.get("status") != "captured"
            ):
                raise PortalDataError(
                    "material_destination_unverified", "当前材料字段不能核验。", 409
                )
            fields = [
                row
                for row in page_context["data"]["fields"]
                if isinstance(row.get("material_target"), dict)
                and (question.get("control_ids") or [])
                == [row["material_target"].get("worker_field")]
            ]
            if len(fields) != 1:
                raise PortalDataError(
                    "material_destination_unverified", "当前材料字段不能核验。", 409
                )
            target = fields[0]["material_target"]
            if (
                target.get("frame") != "main"
                or target.get("draft_path") != question.get("draft_path", "")
                or target.get("type") != question["type"]
                or target.get("tag") != ("textarea" if question["type"] == "textarea" else "input")
                or question["type"] not in {"textarea", "text", "file"}
                or target.get("required") != bool(question.get("required"))
                or any(target.get(key) is not False for key in ("disabled", "readonly", "multiple"))
                or target.get("accept") != question.get("accept", "")
                or target.get("max_length") != question.get("max_length", question.get("maxlength"))
                or question["type"] != "file"
                and fields[0].get("value", "") != question.get("value", "")
            ):
                raise PortalDataError(
                    "material_destination_unverified", "当前材料字段或限制不能核验。", 409
                )
            if question["type"] == "file" and target.get("file_count") != 0:
                raise PortalDataError(
                    "material_human_content", "当前字段已有附件，请保留并核对。", 409
                )
            state = self.load()
            job = next(
                row
                for row in state["jobs"]
                if row["application_id"] == expected_ref["binding"]["application_id"]
            )
            self.check_single(job, state, material_required=True)
            if entry["kind"] == "resume":
                if question["type"] != "file" or material_kind(question) != "resume":
                    raise PortalDataError("material_field_changed", "此字段不是简历附件入口。", 409)
                raw = self._read_bound_resume(job, state["batch_id"])
                accept = {
                    value.strip().casefold()
                    for value in question.get("accept", "").split(",")
                    if value.strip()
                }
                if accept and not accept.intersection({".pdf", "application/pdf", "*", "*/*"}):
                    raise PortalDataError(
                        "material_format_unsupported", "当前字段不接受简历 PDF。", 409
                    )
                maximum = question.get("max_bytes")
                if maximum is not None and (type(maximum) is not int or maximum < 0):
                    raise PortalDataError(
                        "material_file_limit_invalid", "当前附件大小限制不能核验。", 409
                    )
                if not 1 <= len(raw) <= min(maximum or 700000, 700000):
                    raise PortalDataError(
                        "material_file_too_large", "简历附件超过当前字段限制。", 409
                    )
                return {
                    "kind": "file",
                    "bytes": raw,
                    "sha256": job["file_sha256"],
                    "filename": job["filename"],
                    "material_id": "resume",
                    "material_ref": material_ref,
                    "question": deepcopy(question),
                    "material": deepcopy(entry),
                }
            if entry["kind"] == "cover_letter" and [
                question["id"],
                question.get("draft_path", ""),
            ] not in (job.get("cover_letter_delivery") or {}).get("selected_fields", []):
                raise PortalDataError(
                    "material_destination_unverified", "当前字段不是已准备的求职信入口。", 409
                )
            try:
                material = self.field_material(question, job)
            except (OSError, ValueError, TypeError, KeyError) as error:
                raise PortalDataError(
                    "material_changed", "固定材料文件或内容不能核验。", 409
                ) from error
            if material is None:
                original = next(
                    (
                        row
                        for row in job.get("materials", [])
                        if row.get("id") == entry["material_id"]
                    ),
                    None,
                )
                if original is not None and material_kind(question) == "cover_letter":
                    if question["type"] == "file" and original.get("file_path"):
                        check_cover_letter_file(question, material=original)
                    elif question["type"] != "file":
                        if question.get("value") and question["value"] != original.get("text"):
                            raise PortalDataError(
                                "material_human_content",
                                "当前字段已有人工正文，请保留并核对。",
                                409,
                            )
                        check_cover_letter_text(question, original["text"])
                raise PortalDataError("material_not_ready", "当前字段材料尚不能发送。", 409)
            if material.get("id") != entry["material_id"] or digest(material) != entry["revision"]:
                raise PortalDataError(
                    "material_reference_invalid", "字段与固定材料引用不一致。", 409
                )
            if question["type"] != "file":
                if question.get("value") and question["value"] != material.get("text"):
                    raise PortalDataError(
                        "material_human_content", "当前字段已有人工正文，请保留并核对。", 409
                    )
                check_cover_letter_text(question, material["text"])
            metadata = deepcopy(entry)
            metadata.update(
                {
                    key: deepcopy(material[key])
                    for key in (
                        "draft_path",
                        "content_revision",
                        "text_sha256",
                        "tex_sha256",
                        "actor",
                        "template_revision",
                        "letter_attempt_id",
                        "attempt_id",
                    )
                    if key in material
                }
            )
            result = {
                "material_id": material["id"],
                "material_ref": material_ref,
                "question": deepcopy(question),
                "material": metadata,
            }
            if question["type"] == "file":
                if not material.get("file_path"):
                    raise PortalDataError("material_not_ready", "该固定材料没有已完成附件。", 409)
                raw = self._read_bound_material_file(
                    Path(material["file_path"]), material["sha256"]
                )
                return {
                    **result,
                    "kind": "file",
                    "bytes": raw,
                    "sha256": material["sha256"],
                    "filename": material["filename"],
                }
            return {
                **result,
                "kind": "text",
                "text": material["text"],
                "sha256": material["text_sha256"],
            }

    def _read_bound_resume(self, job, batch_id):
        path = Path(job["file_path"])
        expected_paths = {
            self.root / "attachments" / batch_id / job["application_id"] / job["filename"]
        }
        resume_id = (job.get("single_binding") or {}).get("resume_id")
        if (
            self.single_flow_root is not None
            and isinstance(resume_id, str)
            and re.fullmatch(r"[a-f0-9]{32}", resume_id)
        ):
            expected_paths.add(self.single_flow_root / "resumes" / resume_id / "resume.pdf")
        if path not in expected_paths:
            raise PortalDataError("file_changed", "所选简历路径已变更。", 409)
        return self._read_bound_material_file(path, job["file_sha256"])

    def _read_bound_material_file(self, path, expected_sha256):
        try:
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                raise ValueError("redirected bound material")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected_sha256:
                raise ValueError("changed bound material bytes")
            return raw
        except (OSError, ValueError) as error:
            raise PortalDataError("material_changed", "固定附件内容或路径已改变。", 409) from error

    def library(self, application: dict | None = None) -> list[dict]:
        return list(self.answers_for(application)._load_answers_document()["answers"].values())

    def language_levels(self, application: dict | None = None) -> dict[str, str | None]:
        from .application_information import applicable_answers

        result = {}
        records = self.library(application)
        if application is None:
            records = [record for record in records if record["scope"] == {}]
        for language, fact in (
            ("French", "language_french_cefr"),
            ("German", "language_german_cefr"),
        ):
            applicable = applicable_answers(records, fact, application or {})
            values = {str(record["value"]).strip().upper() for record in applicable}
            if len(values) == 1 and values.issubset(LEVELS):
                result[language] = values.pop()
            elif application is not None and applicable:
                result[language] = None
        return result

    def check_language_requirement(self, application: dict, *, country: str | None = None) -> None:
        if country in COUNTRIES:
            application = application | {"country": country}
        screening = screen_applications(
            [application], language_levels=self.language_levels, allow_generic=True
        )[0]["screening"]
        if screening["language_needs_input"]:
            raise PortalDataError(
                "language_information_required", "适用语言信息有冲突或缺少明确等级，请核对。", 409
            )
        if screening["language_mismatch"]:
            raise PortalDataError(
                "job_requirement_mismatch",
                "明确语言要求与已确认水平不匹配，请选择其他岗位。",
                409,
            )

    def material_inputs(self, job):
        """Consume fixed P04 delivery for a single job; keep the legacy adapter separate."""
        if job.get("workflow") != "single":
            return {
                "application": self.applications.get_application(job["application_id"]),
                "sources": self.material_sources(),
            }
        self.check_single(job, material_required=False)
        from .application_single_binding import read_delivered_material_inputs

        provider = self.single_material_source_provider or read_delivered_material_inputs
        return provider(self.applications, self.single_flow_root, job)

    def material_sources(self, job=None):
        if job is not None and job.get("workflow") == "single":
            return self.material_inputs(job)["sources"]
        from .application_resume import career_source_snapshot
        from .career_portal_data import CareerCatalog

        if self.single_career_root is None:
            raise PortalDataError(
                "material_sources_required", "必要附稿尚未绑定职业事实目录。", 409
            )
        return career_source_snapshot(CareerCatalog(self.single_career_root))

    def verify_material(self, material, job):
        from .application_materials import application_binding

        if material.get("status") != "ready":
            raise PortalDataError("material_not_ready", "该字段的材料尚未完成。", 409)
        fixed = self.material_inputs(job) if job.get("workflow") == "single" else None
        application = (
            fixed["application"]
            if fixed
            else self.applications.get_application(job["application_id"])
        )
        binding = material.get("source_binding", {})
        if binding.get("application") != application_binding(application):
            raise PortalDataError("material_input_changed", "附稿对应岗位事实已改变。", 409)
        if material.get("letter_content") is not None:
            from .application_cover_letter import validate_letter

            content = material["letter_content"]
            try:
                validate_letter(content, application=application)
            except ValueError as error:
                raise PortalDataError(
                    "material_changed", "求职信内容契约不能核验。", 409
                ) from error
            if (
                content.get("application_id") != job["application_id"]
                or content.get("revision") != material.get("content_revision")
                or hashlib.sha256(material["text"].encode()).hexdigest()
                != material.get("text_sha256")
            ):
                raise PortalDataError("material_changed", "求职信正文或采用版本已改变。", 409)
        if material.get("actor") == "system":
            snapshot = fixed["sources"] if fixed else self.material_sources()
            packet = (fixed or {}).get("material_packet")
            if material.get("letter_content") and isinstance(packet, dict) and "sources" in packet:
                from .application_material_sources import source_records

                current = source_records(
                    dict(
                        snapshot, material_packet=packet, material_packet_sources=packet["sources"]
                    )
                )
            else:
                current = {item["source_id"]: item for item in snapshot["items"]}
            for source in binding.get("sources", []):
                if source["source_id"] == "jd":
                    continue
                if current.get(source["source_id"]) != source:
                    raise PortalDataError(
                        "material_input_changed", "附稿使用的职业事实已改变。", 409
                    )
            if hashlib.sha256(material["text"].encode()).hexdigest() != material["text_sha256"]:
                raise PortalDataError("material_changed", "附稿正文版本已改变。", 409)
        if material.get("file_path"):
            path = Path(material["file_path"])
            if (
                not path.resolve().is_relative_to((self.root / "materials").resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != material["sha256"]
            ):
                raise PortalDataError("material_changed", "必要附件内容版本已改变。", 409)
        return material

    def verify_material_source(self, material):
        """Check active delivery source without making old immutable PDFs unreadable."""
        if (
            material.get("file_path")
            and material.get("letter_content")
            and material.get("tex_sha256")
        ):
            try:
                tex = Path(material["tex_path"])
                if (
                    tex.is_symlink()
                    or any(parent.is_symlink() for parent in tex.parents)
                    or not tex.resolve().is_relative_to((self.root / "materials").resolve())
                    or hashlib.sha256(tex.read_bytes()).hexdigest() != material["tex_sha256"]
                ):
                    raise ValueError("letter TeX source differs from its build")
            except (OSError, KeyError, ValueError, TypeError) as error:
                raise PortalDataError(
                    "cover_letter_tex_changed",
                    "求职信 LaTeX 已修改或来源不能核验，正文、源文件与原 PDF 已保留。",
                    409,
                ) from error
        return material

    def field_material(self, question, job):
        from .application_materials import (
            check_cover_letter_file,
            check_cover_letter_text,
            material_kind,
        )

        found = [
            item
            for item in job.get("materials", [])
            if item.get("field_id") == question["id"]
            and item.get("draft_path", "") == question.get("draft_path", "")
        ]
        retained_letter = bool(
            found
            and material_kind(question) == "cover_letter"
            and question.get("type") != "file"
            and found[0].get("kind") == "motivation_text"
            and material_kind({"question": found[0].get("question", ""), "type": "textarea"})
            == "cover_letter"
        )
        if found and (
            found[0].get("question") != question["question"]
            or found[0].get("kind") != material_kind(question)
            and not retained_letter
        ):
            raise PortalDataError("material_field_changed", "必要材料字段的含义已改变。", 409)
        if len(found) == 1 and found[0].get("status") == "ready":
            self.verify_material_source(found[0])
        if (
            len(found) == 1
            and found[0].get("status") == "ready"
            and found[0].get("letter_content")
            and job.get("workflow") == "single"
        ):
            fixed = self.material_inputs(job)
            from .application_materials import material_consistency_status

            if material_consistency_status(fixed) in {"queued", "running"}:
                return None
            branch = fixed.get("cover_letter") or {}
            if branch.get("status") != "ready" or branch.get("result", {}).get(
                "content_revision"
            ) != found[0].get("content_revision"):
                raise PortalDataError(
                    "material_changed", "当前发送材料未对应已采用求职信版本。", 409
                )
        if len(found) != 1 or found[0].get("status") != "ready":
            return None
        material = self.verify_material(found[0], job)
        if (
            question.get("type") == "file"
            and material_kind(question) == "cover_letter"
            and material.get("file_path")
        ):
            try:
                check_cover_letter_file(question, material=material)
            except PortalDataError as error:
                if not question.get("required") and error.code in {
                    "cover_letter_format_unsupported",
                    "letter_file_too_large",
                }:
                    return None
                raise
        if question.get("type") != "file" and material_kind(question) == "cover_letter":
            if question.get("value") and question["value"] != material.get("text"):
                return None
            try:
                check_cover_letter_text(question, material["text"])
            except PortalDataError as error:
                if not question.get("required") and error.code == "cover_letter_text_too_long":
                    return None
                raise
        return material

    def resolve(self, question: dict, job: dict, temporary: dict | None = None):
        from .application_information import applicable_answers
        from .application_materials import material_kind

        if material_kind(question) == "cover_letter" and question.get("type") != "file":
            material = self.field_material(question, job)
            return (
                (
                    material["text"],
                    {
                        "key": material["id"],
                        "revision": material["text_sha256"],
                        "fact": "cover_letter",
                        "source": "system_material",
                        "field_id": question["id"],
                        "draft_path": question.get("draft_path", ""),
                    },
                )
                if material
                else None
            )

        fact = fact_for(question["question"])
        one_use = (temporary or {}).get(job["application_id"], {}).get(fact)
        records = [one_use] if one_use else applicable_answers(self.library(job), fact, job)
        records = [r for r in records if r is not None]
        if (
            fact in {"sponsorship_now_future", "work_authorization_now"}
            and job["country"] == "OTHER"
        ):
            records = [
                r
                for r in records
                if r.get("scope", {}).get("application_id") == job["application_id"]
            ]
        prefer_edit = not one_use and any(
            row.get("actor") == "user"
            and row.get("source_binding", {}).get("manual_edit")
            and row.get("field_id") == question["id"]
            and row.get("draft_path", "") == question.get("draft_path", "")
            for row in job.get("materials", [])
        )
        if not records or prefer_edit:
            material = self.field_material(question, job)
            if material and material["kind"] == "motivation_text":
                return material["text"], {
                    "key": material["id"],
                    "revision": material["text_sha256"],
                    "fact": fact,
                    "source": "system_material",
                    "field_id": question["id"],
                    "draft_path": question.get("draft_path", ""),
                }
            if not records:
                return None
        if len({digest(r["value"]) for r in records}) != 1:
            return None
        record = records[-1]
        value = record["value"]
        if not isinstance(value, str) or not value.strip():
            return None
        options = question.get("options", [])
        if fact == "data_processing_consent" and value == "Yes" and value not in options:
            # Standing agreement: a lone consent box is ticked by its own label,
            # and a localized Yes/No choice takes its one affirmative option.
            agree = (
                options
                if question.get("type") == "checkbox" and len(options) == 1
                else [o for o in options if o.strip().casefold() in {"yes", "ja", "oui", "sì"}]
            )
            if len(agree) == 1:
                value = agree[0]
        if options and value not in options:
            return None
        return value, {"key": record["key"], "revision": digest(record), "fact": fact}

    def sync(self, job: dict, next_action: str) -> None:
        with self.measurements.stage(
            "sync", episode_id=job.get("measurement_id"), application_id=job["application_id"]
        ) as measured:
            self._sync(job, next_action)
            if job.get("sync_error"):
                measured.update(result="failed", reason=job["sync_error"])

    def _sync(self, job: dict, next_action: str) -> None:
        """Keep pending sync separate. A retry does not repeat browser actions."""
        self.load()
        job["pending_sync"] = next_action
        try:
            changes = {"next_action": next_action, "needs_action": True}
            if job.get("pending_status"):
                changes["status"] = job["pending_status"]
            updated = self.applications.update_application(
                job["application_id"],
                changes,
                job["revision"],
            )
            job["revision"] = updated["revision"]
            job["pending_sync"] = ""
            job["sync_error"] = ""
            job["pending_status"] = ""
        except (PortalDataError, OSError) as exc:
            job["sync_error"] = getattr(exc, "code", "write_failed")


class WorkerService:
    def __init__(
        self,
        applications: ApplicationStore,
        root: Path,
        *,
        fixture_origin: str = "",
        headless: bool = False,
        cdp_port: int = 0,
        live: bool = False,
        generic: bool = False,
        cua: bool = False,
        cua_click_route: str = "trusted",
        single_flow_root=None,
        single_career_root=None,
        legacy_roots=(),
        single_validator=None,
        single_material_source_provider=None,
        synthetic_browser_root: Path | None = None,
        codex_assist_config: dict | None = None,
        native_assistance_policy: dict | None = None,
    ):
        self.native_assistance_policy = validate_native_assistance_policy(native_assistance_policy)
        self.takeover_budget = DEFAULT_BUDGET
        if self.native_assistance_policy is not None and (
            not live or not cua or synthetic_browser_root is not None
        ):
            raise ValueError("Native assistance requires explicit native Cua worker mode")
        self.synthetic_browser_root = synthetic_browser_root
        self._backend_closed = False
        self._backend_instance_id = uuid4().hex
        self.write_preflight = None
        self.validate_write_preflight = None
        self.write_admitted = None
        self.packaged_startup_identity = None
        if synthetic_browser_root is not None:
            from .application_worker_fixtures import browser_fixture_configuration

            config = browser_fixture_configuration(synthetic_browser_root)
            if (
                not (live and generic and cua)
                or cua_click_route != "dom_event"
                or fixture_origin
                or headless
                or cdp_port
                or applications.root != synthetic_browser_root / "applications"
                or root != synthetic_browser_root / "runtime/single-job-worker"
                or single_flow_root
                not in (None, synthetic_browser_root / "runtime/single-job-flow")
                or single_career_root not in (None, synthetic_browser_root / "career")
                or legacy_roots
                or config["applications"] != str(applications.root)
            ):
                raise ValueError("Synthetic browser mode requires its exact isolated worker roots.")
        if cua and (headless or cdp_port):
            raise ValueError("Cua requires a windowed browser and owns its CDP endpoint.")
        if (
            cua_click_route not in {"trusted", "dom_event"}
            or not cua
            and cua_click_route != "trusted"
        ):
            raise ValueError("Cua click route requires explicit Cua mode.")
        if generic and not live:
            raise ValueError("Generic forms require explicit live mode.")
        if live and (headless or fixture_origin):
            raise ValueError("Live filling requires a visible browser without fixtures.")
        self.store = WorkerStore(
            applications,
            root,
            live=live,
            single_flow_root=single_flow_root,
            single_career_root=single_career_root,
            legacy_roots=legacy_roots,
            single_validator=single_validator,
            single_material_source_provider=single_material_source_provider,
        )
        self.codex_assist_config = None
        if codex_assist_config is not None:
            from .application_codex_assist import CodexAssistConfig

            if synthetic_browser_root is not None or not isinstance(codex_assist_config, dict):
                raise ValueError("Codex assistance requires a trusted worker configuration")
            try:
                runtime = Path(codex_assist_config.get("runtime", ""))
            except TypeError as error:
                raise ValueError("Codex assistance runtime is invalid") from error
            expected = self.store.root / "codex-assist"
            if not runtime.is_absolute() or runtime.is_symlink() or runtime.resolve() != expected:
                raise ValueError("Codex assistance runtime must belong to this worker")
            expected.mkdir(mode=0o700, exist_ok=True)
            self.codex_assist_config = CodexAssistConfig.from_dict(codex_assist_config).to_dict()
            if (
                self.codex_assist_config.get("native_assistance_policy")
                != self.native_assistance_policy
            ):
                raise ValueError("Native adapter and worker policies differ")
        self.live = live
        self.generic = generic
        with applications.write_lock():
            state = self.store.load()
            if state.get("generic_enabled") != generic:
                state["generic_enabled"] = generic
                self.store.save(state)
        self.fixture_origin = fixture_origin
        self.headless = headless
        self.cdp_port = cdp_port
        self.cua, self.cua_click_route = cua, cua_click_route
        self.process: subprocess.Popen | None = None
        self.process_run_id: str | None = None
        self.process_started_at = 0.0

    def _page_current(self, state: dict, job: dict, *, now: float | None = None) -> bool:
        """Identify a live retained handle, independently of preparation success."""
        runtime = state.get("runtime")
        page = job.get("page_observation")
        if not runtime or not isinstance(page, dict):
            return False
        now = time.time() if now is None else now
        exited = bool(
            self.process
            and self.process.pid == runtime["pid"]
            and self.process_run_id == runtime["id"]
            and self.process.poll() is not None
        )
        return bool(
            not exited
            and job.get("reason") not in {"page_lost", "page_closed", "page_crashed"}
            and PAGE_SCOPE.runtime_current(state, now)
            and page.get("run_id") == runtime["id"]
            and page.get("event") == "observed"
            and isinstance(page.get("page_id"), str)
            and page["page_id"].strip()
        )

    def readiness_facts(self, state: dict, job: dict | None) -> dict:
        """Read-only process, page and file facts for readiness; no spawn or page action."""
        runtime = state.get("runtime") or {}
        process = "unknown"
        if (
            self.process
            and self.process.pid == runtime.get("pid")
            and self.process_run_id in {None, runtime.get("id")}
            and runtime.get("started_at", 0) >= self.process_started_at
        ):
            process = "exited" if self.process.poll() is not None else "managed"
        pending = self.store.root / "prepare-pending.json"
        return {
            "root": self.store.root,
            "paths": (
                self.store.stop_path,
                pending,
                self.store.answers.answers_path,
                self.store.answers.profile_path,
            ),
            "pending_prepare": pending.exists(),
            "owned_process_alive": bool(self.process and self.process.poll() is None),
            "process": process,
            "page_target": self._page_inspection_target(state, job) if job else None,
        }

    def _page_inspection_target(self, state: dict, job: dict) -> dict | None:
        runtime = state.get("runtime") or {}
        if (
            state["control"] != "paused"
            or self.store.stop_reason()
            or OWNED_PAGE_OBSERVATION not in runtime.get("capabilities", [])
            or not self._page_current(state, job)
            or state.get("worker_error", "") not in {"", "control_connection_lost"}
            or not PAGE_SCOPE.page_current(job)
        ):
            return None
        return {
            "batch_id": state["batch_id"],
            "run_id": runtime["id"],
            "page_id": job["page_observation"]["page_id"],
        }

    def _email_correction_target(
        self, state: dict, job: dict, *, queued_field: str | None = None
    ) -> dict | None:
        if (
            state["control"] != "paused"
            or job.get("workflow") != "single"
            or job["status"] == "cancelled"
            or job.get("manual_submission")
            or not self._page_current(state, job)
        ):
            return None
        page = job["page_observation"]
        refs = [ref for ref in job["answer_refs"] if ref.get("fact") == "email"]
        fields = {ref.get("field_id") for ref in refs}
        intent = job["intent"]
        if intent and intent.get("action") == "fill" and intent.get("fact") == "email":
            if intent.get("run_id") != page["run_id"] or intent.get("page_id") != page["page_id"]:
                return None
            fields.add(intent.get("field_id"))
        else:
            evidence = [
                event.get("intent", {})
                for event in job["observations"]
                if event.get("action") == "fill"
                and event.get("verified") is True
                and event.get("run_id") == page["run_id"]
            ] + [
                row.get("intent", {})
                for row in latest_action_resolutions(job.get("action_resolutions", [])).values()
                if row.get("conclusion") == "current_matches"
                and row.get("run_id") == page["run_id"]
            ]
            if any(
                not any(
                    record.get("action") == "fill"
                    and record.get("fact") == "email"
                    and record.get("run_id") == page["run_id"]
                    and record.get("page_id") == page["page_id"]
                    and record.get("field_id") == ref.get("field_id")
                    and record.get("answer_ref")
                    == {k: v for k, v in ref.items() if k != "field_id"}
                    for record in evidence
                )
                for ref in refs
            ):
                return None
        # A queued correction already established its field before clearing the
        # old intent. Keep that field only on the same current runtime and page.
        if not fields and queued_field is not None:
            fields.add(queued_field)
        if len(fields) != 1 or not all(
            isinstance(field, str) and field.strip() for field in fields
        ):
            return None
        return {
            "application_id": job["application_id"],
            "task_id": job.get("single_binding", {}).get("task_id"),
            "batch_id": state["batch_id"],
            "job_url": job["job_url"],
            "run_id": page["run_id"],
            "page_id": page["page_id"],
            "field_id": next(iter(fields)),
        }

    def snapshot(self) -> dict:
        with self.store.applications.write_lock():
            state = deepcopy(self.store.load())
            if self.store.stop_reason():
                state.update(control="paused", worker_error=self.store.stop_reason())
            state["enabled"] = True
            state["library"] = self.store.library()
            for record in state["library"]:
                record["content_revision"] = digest(record)
            state["model_mode"] = "reviewed_aliases_only"
            state["live_enabled"] = self.live
            state["generic_enabled"] = self.generic and state.get("generic_enabled") is True
            state["cua_enabled"] = self.cua
            state["cua_click_route"] = self.cua_click_route
            runtime = state.get("runtime")
            now = time.time()
            if (
                self.process
                and runtime
                and self.process.pid == runtime["pid"]
                and runtime["started_at"] >= self.process_started_at
                and self.process_run_id is None
            ):
                self.process_run_id = runtime["id"]
            managed = bool(
                self.process
                and runtime
                and self.process.pid == runtime["pid"]
                and self.process_run_id == runtime["id"]
            )
            exit_code = self.process.poll() if managed else None
            age = now - (runtime or {}).get("observed_at", 0)
            observation = (
                "exited"
                if managed and exit_code is not None
                else "current"
                if runtime and 0 <= age < PAGE_SCOPE.window
                else "stale"
                if runtime
                else "historical"
            )
            state["runtime_status"] = {
                "observation": observation,
                "observed_at": now,
                "process": "exited"
                if exit_code is not None
                else "managed"
                if managed
                else "unknown",
                "exit_code": exit_code,
                "source_matches_disk": bool(
                    runtime
                    and all(
                        (PUBLIC_ROOT / path).is_file()
                        and hashlib.sha256((PUBLIC_ROOT / path).read_bytes()).hexdigest()
                        == expected
                        for path, expected in runtime["source"]["files"].items()
                    )
                ),
            }
            state["process_observation"] = (
                {
                    "pid": self.process.pid,
                    "run_id": self.process_run_id,
                    "started_at": self.process_started_at,
                    "observed_at": now,
                    "exit_code": self.process.poll(),
                }
                if self.process
                else None
            )
            for job in state["jobs"]:
                job.pop("file_path", None)
                for material in job.get("materials", []):
                    material["material_revision"] = digest(material)
                if job["intent"]:
                    job["intent_ref"] = job["intent"].get("attempt_id") or digest(job["intent"])
                job["page_current"] = self._page_current(state, job, now=now)
                job["page_inspection_target"] = self._page_inspection_target(state, job)
                inspection = job.get("owned_page_inspection") or {}
                if inspection:
                    pending = inspection.get("status") == "pending"
                    if pending:
                        inspection_state = (
                            "pending"
                            if 0 <= now - inspection.get("requested_at", 0) < 10
                            and inspection.get("binding") == job["page_inspection_target"]
                            else "timed_out"
                        )
                    elif inspection.get("status") == "captured":
                        inspection_state = (
                            "current"
                            if 0 <= now - inspection.get("at", 0) < 10
                            and inspection.get("binding") == job["page_inspection_target"]
                            and inspection.get("worker_source")
                            == (runtime or {}).get("source", {}).get("sha256")
                            else "historical"
                        )
                    else:
                        inspection_state = "failed"
                    job["owned_page_inspection_state"] = inspection_state
                job["email_correction_target"] = self._email_correction_target(state, job)
                corrections = job.get("email_corrections", [])
                if corrections:
                    job["email_correction_status"] = (
                        "queued"
                        if any(
                            event.get("action") == "email_correction_queued"
                            and event.get("correction_id") == corrections[-1]["id"]
                            for event in job["observations"]
                        )
                        else "staged"
                    )
                    job["email_correction_readback"] = email_correction_readback(state, job)
            state["measurement_incomplete"] = (
                self.store.measurements.incomplete
                or (self.store.root / ".measurement-incomplete").exists()
            )
            state["input_items"] = _input_items(state)
            return state

    def spawn(self) -> None:
        if self._backend_closed or self.process and self.process.poll() is None:
            return
        descriptor = os.open(
            self.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
        finally:
            os.close(descriptor)
        launcher = PUBLIC_ROOT / "scripts/run_application_worker.py"
        env = dict(os.environ)
        if self.synthetic_browser_root is not None:
            env = {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "en_US.UTF-8",
                "HOME": str(self.synthetic_browser_root / "home"),
                "TMPDIR": str(self.synthetic_browser_root / "tmp"),
            }
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        args = [
            sys.executable,
            "-B",
            str(launcher),
            "--applications",
            str(self.store.applications.root),
            "--runtime",
            str(self.store.root),
        ]
        if self.codex_assist_config is not None:
            args.extend(["--codex-assist-config", json.dumps(self.codex_assist_config)])
        if self.native_assistance_policy is not None:
            args.extend(["--native-assistance-policy", json.dumps(self.native_assistance_policy)])
        if self.packaged_startup_identity is not None:
            identity = self.packaged_startup_identity
            if not all(identity.get(key) for key in ("resources", "manifest", "worker")):
                raise PortalDataError(
                    "installed_worker_identity_unverified", "请保持暂停并核验安装包。", 409
                )
            args.extend(
                [
                    "--package-resources",
                    identity["resources"],
                    "--expected-package-manifest",
                    identity["manifest"],
                    "--expected-worker-revision",
                    identity["worker"],
                ]
            )
        if any(job.get("workflow") == "single" for job in self.store.load()["jobs"]):
            context = self.store.single_context()
            args.extend(["--single-flow-root", context["flow_root"]])
        args.extend(["--live"] if self.live else ["--fixture-origin", self.fixture_origin])
        if self.headless:
            args.append("--headless")
        if self.cdp_port:
            args.extend(["--cdp-port", str(self.cdp_port)])
        if self.cua:
            args.extend(["--cua", "--cua-click-route", self.cua_click_route])
        if self.synthetic_browser_root is not None:
            args.extend(["--synthetic-browser", str(self.synthetic_browser_root)])
        log = self.store.root / "worker.log"
        fd = os.open(log, os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            self.process_started_at = time.time()
            self.process_run_id = None
            self.process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=fd,
                stderr=fd,
                env=env,
                start_new_session=True,
            )
        finally:
            os.close(fd)

    def stop_process(self, record=lambda event: None, *, timeout: float = 10) -> None:
        """Stop this backend's worker: SIGTERM lets it close its driver and Chrome first."""
        # A closing backend starts no replacement worker.
        self._backend_closed = True
        process = self.process
        if process is None or process.poll() is not None:
            return
        record("worker_terminate_requested")
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            process.wait(timeout)
        except subprocess.TimeoutExpired:
            record("worker_kill_requested")
            # The worker leads its own session; this also ends its unreaped helpers.
            with suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                record("worker_stop_unconfirmed")
                return
        record("worker_exit_confirmed")

    def suspend_backend(self, *, pipeline_id, controller, batch_id, application_id):
        """Stop writes and revoke old recovery commands before each backend exit."""
        with self.store.applications.write_lock():
            state = self.store.load()
            previous = state.get("backend_recovery") or {}
            resuspending = (
                state["control"] == "paused"
                and previous.get("status") in {"suspended", "pending"}
                and previous.get("pipeline_id") == pipeline_id
                and previous.get("controller") == controller
            )
            if (
                state["control"] != "running"
                and not resuspending
                or state.get("controller") != controller
                or state["batch_id"] != batch_id
                or state.get("current_job_id") != application_id
            ):
                return None
            state["control"] = "paused"
            revoke_backend_authority(state)
            if previous.get("status") in {"suspended", "pending", "verified"}:
                state.setdefault("backend_recovery_history", []).append(
                    {
                        **deepcopy(previous),
                        "revoked_at": time.time(),
                        "revocation": "backend_closed",
                    }
                )
                state["commands"] = [
                    command
                    for command in state["commands"]
                    if command["action"] != "recover-backend"
                    or command.get("request_id") != previous.get("request_id")
                ]
                previous.update(status="cancelled", reason="backend_closed")
            job = self._job(state, application_id)
            revoke_assistance(job, reason="backend_closed")
            receipt = None
            if (
                job.get("workflow") == "single"
                and job["status"] in {"queued", "filling"}
                and not job.get("reason")
                and not job.get("intent")
                and not job.get("handed_off")
                and not manual_submission_unresolved(job)
                and not state["commands"]
                and not self.store.stop_reason()
                and not state.get("worker_error")
            ):
                receipt = {
                    "request_id": uuid4().hex,
                    "pipeline_id": pipeline_id,
                    "controller": controller,
                    "status": "suspended",
                    "at": time.time(),
                    "binding": handoff_binding(state, job),
                    "worker_lock": None,
                }
                if job.get("assistance"):
                    receipt["assistance_ref"] = assistance_reference(job["assistance"])
                lock_path = self.store.root / ".worker.lock"
                if lock_path.exists():
                    observed = lock_path.stat(follow_symlinks=False)
                    receipt["worker_lock"] = {"device": observed.st_dev, "inode": observed.st_ino}
                state["backend_recovery"] = receipt
            self.store.save(state)
            return deepcopy(receipt)

    def begin_backend_close(self):
        """Revoke this backend before waiting for schedulers, preserving recovery input."""
        self._backend_closed = True
        try:
            with self.store.applications.write_lock():
                state = self.store.load()
                authority = state.get("backend_authority")
                if authority and authority["instance_id"] != self._backend_instance_id:
                    return False
                changed = revoke_backend_authority(state)
                for job in state["jobs"]:
                    changed = revoke_assistance(job, reason="backend_closed") or changed
                if changed:
                    self.store.save(state)
                return True
        except (OSError, ValueError, KeyError, TypeError, PortalDataError, helper.StoreError):
            self.store.block_storage()
            raise

    def close_backend(self):
        """Fence this controller, retaining pages, recovery receipts and uncertain effects."""
        if not self.begin_backend_close():
            return
        try:
            with self.store.applications.write_lock():
                state = self.store.load()
                authority = state.get("backend_authority")
                if authority and authority["instance_id"] != self._backend_instance_id:
                    return
                if state["control"] == "running":
                    state["control"] = "paused"
                    self.store.save(state)
        except (OSError, ValueError, KeyError, TypeError, PortalDataError, helper.StoreError):
            self.store.block_storage()
            raise

    def recover_backend(self, request_id, pipeline_id):
        """Ask the original owner to verify; spawn only a provably unopened queue."""
        launch = False
        with self.store.applications.write_lock():
            state = self.store.load()
            receipt = state.get("backend_recovery") or {}
            if receipt.get("request_id") != request_id or receipt.get("pipeline_id") != pipeline_id:
                return None
            if receipt.get("status") in {"suspended", "pending"}:
                job = self._job(state, receipt["binding"]["application_id"])
                if assistance_stop_pending(job):
                    unknown = (job["assistance"].get("stop") or {}).get("stop_status") == "unknown"
                    receipt.update(
                        status="needs_recheck" if unknown else "suspended",
                        reason="assistance_stop_unknown" if unknown else "assistance_stop_pending",
                    )
                    state["commands"] = [
                        command
                        for command in state["commands"]
                        if command["action"] != "recover-backend"
                        or command.get("request_id") != request_id
                    ]
                    self.store.save(state)
                    return deepcopy(receipt)
                assistance = job.get("assistance")
                if assistance and digest(receipt.get("assistance_ref")) != digest(
                    assistance_reference(assistance)
                ):
                    receipt.update(
                        status="needs_recheck",
                        reason="backend_recovery_unbound"
                        if "assistance_ref" not in receipt
                        else "assistance_generation_changed",
                    )
                    state["commands"] = [
                        command
                        for command in state["commands"]
                        if command["action"] != "recover-backend"
                        or command.get("request_id") != request_id
                    ]
                    self.store.save(state)
                    return deepcopy(receipt)
            if receipt["status"] == "suspended":
                binding = receipt["binding"]
                if (
                    state["control"] != "paused"
                    or state.get("controller") != receipt["controller"]
                    or state.get("current_job_id") != binding["application_id"]
                    or state["batch_id"] != binding["batch_id"]
                    or state["commands"]
                ):
                    receipt.update(status="needs_recheck", reason="backend_recovery_changed")
                else:
                    receipt.pop("reason", None)
                    receipt.update(status="pending", requested_at=time.time())
                    state["commands"].append(
                        {
                            "action": "recover-backend",
                            "id": binding["application_id"],
                            "request_id": request_id,
                        }
                    )
            if receipt["status"] == "pending" and not backend_recovery_timely(receipt):
                receipt.update(status="needs_recheck", reason="backend_owner_unresponsive")
            if receipt["status"] == "pending" and not worker_lock_is_held(
                self.store.root, receipt.get("worker_lock")
            ):
                if unopened_single_queue(self.store, state) and not receipt.get(
                    "cold_start_requested"
                ):
                    receipt["cold_start_requested"] = True
                    launch = True
                elif not receipt.get("cold_start_requested"):
                    receipt.update(status="needs_recheck", reason="backend_owner_unavailable")
            self.store.save(state)
            result = deepcopy(receipt)
        if launch:
            self.spawn()
        return result

    def assistance_context(self, application_id: str) -> dict:
        """Read ownership metadata; it cannot inspect or write the browser page."""
        with self.store.applications.write_lock():
            state = self.store.load()
            job = self._job(state, application_id)
            assistance = job.get("assistance")
            return {
                "binding": assistance_binding(state, job),
                "assistance_ref": assistance_reference(assistance) if assistance else None,
                "page_writes_enabled": bool(assistance and assistance["page_writes_enabled"]),
            }

    def assistance_delivery(self, application_id, expected_ref, *, page_context=None):
        if (
            not isinstance(expected_ref, dict)
            or not isinstance(expected_ref.get("binding"), dict)
            or expected_ref["binding"].get("application_id") != application_id
        ):
            raise PortalDataError("assistance_binding_changed", "交接岗位引用不一致。", 409)
        return self.store.assistance_delivery(expected_ref, page_context=page_context)

    def record_assistance_stop(self, application_id, assistance_ref, progress, *, request_id):
        """Save original-owner stop evidence without changing control or page effects."""
        with self.store.applications.write_lock():
            state = self.store.load()
            job = self._job(state, application_id)
            if adopt_assistance_stop(job, assistance_ref, progress, request_id=request_id):
                self.store.save(state)
            return self.snapshot()

    def prepare_execution(
        self, application_id, application_revision, single_binding, *, pdf_reader
    ):
        """Prepare a trusted Flow delivery, or reuse its unpublished unopened job."""
        binding = deepcopy(single_binding)
        if not isinstance(binding, dict) or not isinstance(binding.get("task_id"), str):
            raise PortalDataError("single_binding_invalid", "单岗材料绑定无效。", 409)
        with self.store.applications.write_lock():
            validate_application_target(
                self.store.applications,
                application_id,
                application_revision,
                allow_generic=self.generic,
            )
            state = self.store.load()
            matching = next(
                (
                    job
                    for job in state["jobs"]
                    if job["application_id"] == application_id
                    and job.get("workflow") == "single"
                    and job.get("single_binding") == binding
                ),
                None,
            )
            if matching is not None:
                if (
                    state["control"] != "paused"
                    or matching["status"] != "queued"
                    or matching.get("page_open")
                    or matching.get("intent")
                ):
                    raise PortalDataError(
                        "worker_execution_changed", "已有执行不能作为未开页准备复用。", 409
                    )
                self.store.check_single(matching, state, allow_unbound=True)
            else:
                raw = pdf_reader(binding["resume_id"])
                self.request(
                    "prepare",
                    {
                        "workflow": "single",
                        "send_confirmed": True,
                        "jobs": [
                            {
                                "application_id": application_id,
                                "revision": application_revision,
                                "country": binding["country"],
                                "filename": "resume.pdf",
                                "file_base64": base64.b64encode(raw).decode(),
                                "single_binding": binding,
                            }
                        ],
                    },
                )
            return self.execution_reference(application_id, binding["task_id"])

    def control_execution(self, reference, operation, payload):
        """Apply an existing control only to the exact task, batch and run."""
        operations = {
            "resume",
            "pause",
            "heartbeat",
            "answer",
            "provide-material",
            "retry-cover-letter-file",
            "recheck-cover-letter-file",
            "correct-email",
            "resolve-form-differences",
            "review",
            "recheck",
            "release",
            "retry-sync",
            "resolve-action",
            "cancel-job",
            "settle-cancelled",
            "observe-page",
            "inspect-handoff",
            "verify-handoff",
            "continue-current",
            "reopen-current",
            "observe-result",
        }
        if operation not in operations:
            raise PortalDataError("worker_control_invalid", "执行控制或固定引用无效。", 409)
        return self._control_execution(reference, operation, payload)

    def select_execution(self, reference, operation, payload):
        """Let the coordinator select or skip a fixed existing execution."""
        if operation not in {"skip-current", "select-current"}:
            raise PortalDataError("worker_control_invalid", "执行选择操作无效。", 409)
        return self._control_execution(reference, operation, payload)

    def _control_execution(self, reference, operation, payload):
        if (
            not isinstance(reference, dict)
            or set(reference) != {"application_id", "task_id", "batch_id", "run_id"}
            or not isinstance(payload, dict)
            or "application_id" in payload
        ):
            raise PortalDataError("worker_control_invalid", "执行控制或固定引用无效。", 409)
        reference, payload = deepcopy(reference), deepcopy(payload)
        with self.store.applications.write_lock():
            current = self.execution_reference(
                reference["application_id"],
                reference["task_id"],
                expected_batch_id=reference["batch_id"],
                expected_run_id=reference["run_id"],
            )
            if current["reference"] != reference or (
                operation in {"resume", "pause", "heartbeat"} and not current["view"]["current"]
            ):
                raise PortalDataError("worker_execution_changed", "执行任务或原运行已改变。", 409)
            self.request(operation, payload | {"application_id": reference["application_id"]})
            return self.execution_reference(reference["application_id"], reference["task_id"])

    def check_material_preparation(self, application_id, task_id, *, expected_batch_id):
        """Verify preparation permission without issuing a command or changing execution."""
        if not isinstance(task_id, str) or not task_id:
            raise PortalDataError("bound_material_pause_required", "准备任务引用不能核验。", 409)
        with self.store.applications.write_lock():
            checked_material_preparation_job(
                self.store.load(),
                application_id,
                expected_batch_id=expected_batch_id,
                expected_task_id=task_id,
            )

    def execution_reference(
        self, application_id, task_id, *, expected_batch_id=None, expected_run_id=None
    ):
        """Read one single-task execution without loading materials or creating work."""
        state = self.store.load()
        job = self._bound_execution_job(
            state,
            application_id,
            expected_batch_id=state["batch_id"] if expected_batch_id is None else expected_batch_id,
            expected_run_id=expected_run_id,
            expected_task_id=task_id,
        )
        if job.get("workflow") != "single" or not isinstance(task_id, str) or not task_id:
            raise PortalDataError("worker_execution_changed", "执行任务已改变。", 409)
        return {
            "reference": {
                "application_id": job["application_id"],
                "task_id": task_id,
                "batch_id": state["batch_id"],
                "run_id": (state.get("runtime") or {}).get("id"),
            },
            "view": {
                "status": job["status"],
                "reason": job.get("reason", ""),
                "handed_off": bool(job.get("handed_off")),
                "page_open": bool(job.get("page_open")),
                "control": state["control"],
                "current": state.get("current_job_id", job["application_id"])
                == job["application_id"],
            },
        }

    def _bound_execution_job(
        self, state, application_id, *, expected_batch_id, expected_run_id, expected_task_id=None
    ):
        run_id = (state.get("runtime") or {}).get("id")
        if state["batch_id"] != expected_batch_id or (
            expected_run_id is not None and run_id != expected_run_id
        ):
            raise PortalDataError("worker_execution_changed", "执行批次或原运行已改变。", 409)
        job = self._job(state, application_id)
        task_id = (job.get("single_binding") or {}).get("task_id")
        if expected_task_id is not None and task_id != expected_task_id:
            raise PortalDataError("worker_execution_changed", "执行任务已改变。", 409)
        return job

    def _backend_recovery_candidate(self, state, job):
        assistance = job.get("assistance")
        if not assistance or job["status"] == "cancelled" or state["control"] != "paused":
            return None
        try:
            require_execution(
                self.store.applications,
                job["application_id"],
                automated_owner(self.store.root, state["batch_id"], job["application_id"]),
                "automated",
            )
        except PortalDataError:
            return None
        reference = assistance_reference(assistance)
        binding = reference["binding"]
        if "backend_authority" in reference:
            authority = state.get("backend_authority")
            if not valid_backend_authority(authority) or digest(
                reference["backend_authority"]
            ) != digest({key: authority[key] for key in ("instance_id", "process")}):
                return None
        if (
            state.get("current_job_id") != job["application_id"]
            or state["batch_id"] != binding["batch_id"]
            or (state.get("runtime") or {}).get("id") != binding["run_id"]
            or state.get("controller") != binding["controller"]
            or type(state.get("resume_serial", 0)) is not int
            or state.get("resume_serial", 0) != binding["resume_serial"]
        ):
            return None
        receipt = state.get("backend_recovery") or {}
        suspended = bool(
            (
                receipt.get("status") in {"suspended", "pending"}
                or receipt.get("status") == "needs_recheck"
                and receipt.get("reason") == "backend_recovery_unbound"
            )
            and receipt.get("controller") == state.get("controller")
            and receipt.get("binding") == handoff_binding(state, job)
            and (
                "assistance_ref" not in receipt
                or digest(receipt["assistance_ref"]) == digest(reference)
            )
        )
        loss = assistance.get("backend_loss") or {}
        if not suspended and not loss.get("automatic_recovery"):
            return None
        candidate = {
            "application_id": job["application_id"],
            "batch_id": state["batch_id"],
            "run_id": (state.get("runtime") or {}).get("id"),
            "task_id": (job.get("single_binding") or {}).get("task_id"),
            "assistance_ref": reference,
            "reason": "backend_closed" if suspended else "backend_authority_lost",
        }
        if suspended:
            if "assistance_ref" in receipt:
                candidate["recovery_request_id"] = receipt["request_id"]
            else:
                candidate["reason"] = "backend_recovery_unbound"
        return candidate

    def backend_recovery_candidate(
        self, application_id, *, expected_batch_id, expected_run_id, expected_task_id=None
    ):
        """Read one eligible recovery intent without publishing an authority or challenge."""
        with self.store.applications.write_lock():
            state = self.store.load()
            job = self._bound_execution_job(
                state,
                application_id,
                expected_batch_id=expected_batch_id,
                expected_run_id=expected_run_id,
                expected_task_id=expected_task_id,
            )
            return self._backend_recovery_candidate(state, job)

    def request_backend_recovery(
        self,
        application_id,
        *,
        pipeline_id,
        expected_batch_id,
        expected_run_id,
        expected_assistance_ref,
        request_id,
        automatic=True,
        expected_task_id=None,
    ):
        """Publish an original-owner read challenge, never a replacement authority."""
        with self.store.applications.write_lock():
            if self._backend_closed or self.store.stop_reason():
                raise PortalDataError("backend_closed", "控制服务不能创建恢复请求。", 409)
            state = self.store.load()
            job = self._bound_execution_job(
                state,
                application_id,
                expected_batch_id=expected_batch_id,
                expected_run_id=expected_run_id,
                expected_task_id=expected_task_id,
            )
            assistance = job.get("assistance")
            require_execution(
                self.store.applications,
                application_id,
                automated_owner(self.store.root, state["batch_id"], application_id),
                "automated",
            )
            if (
                not assistance
                or not isinstance(expected_assistance_ref, dict)
                or digest(assistance_reference(assistance)) != digest(expected_assistance_ref)
                or not isinstance(pipeline_id, str)
                or not 1 <= len(pipeline_id) <= 200
                or not pipeline_id.isprintable()
                or not isinstance(request_id, str)
                or not 1 <= len(request_id) <= 200
                or not request_id.isprintable()
                or type(automatic) is not bool
            ):
                raise PortalDataError("backend_recovery_changed", "原接管恢复引用不能核验。", 409)
            reference = assistance_reference(assistance)
            binding = handoff_binding(state, job)
            previous = state.get("backend_recovery") or {}
            same_previous = bool(
                previous.get("pipeline_id") == pipeline_id
                and previous.get("controller") == state.get("controller")
                and previous.get("binding") == binding
                and (
                    "assistance_ref" in previous
                    and digest(previous["assistance_ref"]) == digest(reference)
                )
            )
            legacy_previous = bool(
                previous
                and "assistance_ref" not in previous
                and previous.get("pipeline_id") == pipeline_id
                and previous.get("controller") == state.get("controller")
                and previous.get("binding") == binding
                and (
                    previous.get("status") in {"suspended", "pending"}
                    or previous.get("status") == "needs_recheck"
                    and previous.get("reason") == "backend_recovery_unbound"
                )
            )
            if previous.get("request_id") == request_id:
                if not same_previous:
                    raise PortalDataError("backend_recovery_changed", "原恢复请求已改变。", 409)
                return deepcopy(previous)
            if same_previous and previous.get("status") in {"suspended", "pending"}:
                return deepcopy(previous)
            if automatic and self._backend_recovery_candidate(state, job) is None:
                raise PortalDataError(
                    "backend_recovery_not_automatic", "原运行保留人工等待，不自动恢复。", 409
                )
            if previous.get("status") in {"suspended", "pending"} and not legacy_previous:
                raise PortalDataError("backend_recovery_changed", "已有原运行恢复请求。", 409)
            if state["control"] != "paused" or state.get("current_job_id") != application_id:
                raise PortalDataError("backend_recovery_changed", "请保留当前岗位的暂停现场。", 409)
            lock_path = self.store.root / ".worker.lock"
            lock_evidence = None
            if lock_path.exists():
                observed = lock_path.stat(follow_symlinks=False)
                lock_evidence = {"device": observed.st_dev, "inode": observed.st_ino}
            reason = ""
            if job.get("intent") or manual_submission_unresolved(job):
                reason = "action_result_unknown"
            elif job.get("reason") not in (None, "", "backend_authority_lost"):
                reason = job["reason"]
            elif job["status"] == "cancelled" or job.get("handed_off"):
                reason = "application_closed"
            elif (assistance.get("stop") or {}).get("stop_status") == "unknown":
                reason = "assistance_stop_unknown"
            elif not job["page_open"]:
                reason = "page_lost"
            elif digest(assistance_binding(state, job)) != digest(reference["binding"]):
                reason = "assistance_binding_changed"
            elif material_edit_pending(job):
                reason = "material_edit_needs_recheck"
            elif not worker_lock_is_held(self.store.root, lock_evidence):
                reason = "backend_owner_unavailable"
            if previous:
                state.setdefault("backend_recovery_history", []).append(deepcopy(previous))
                if legacy_previous:
                    state["commands"] = [
                        command
                        for command in state["commands"]
                        if command["action"] != "recover-backend"
                        or command.get("request_id") != previous.get("request_id")
                    ]
            receipt = {
                "request_id": request_id,
                "pipeline_id": pipeline_id,
                "controller": state.get("controller"),
                "status": "needs_recheck" if reason else "suspended",
                "at": time.time(),
                "binding": binding,
                "assistance_ref": reference,
                "worker_lock": lock_evidence,
                "source": "backend_authority_lost",
            }
            if reason:
                receipt["reason"] = reason
            state["backend_recovery"] = receipt
            self.store.save(state)
        return self.recover_backend(request_id, pipeline_id)

    def _new_assistance(self, state, job, binding, request_id):
        takeover_record.begin(
            job,
            {
                "protocol": CODEX_ASSISTANCE,
                "id": uuid4().hex,
                "generation": takeover_record.next_generation(job),
                "request_id": request_id,
                "claim_request_id": None,
                "status": "requested",
                "active_writer": "none",
                "binding": binding,
                "page_writes_enabled": False,
            },
        )
        if self.native_assistance_policy is not None:
            job["assistance"].update(
                protocol=CODEX_NATIVE_ASSISTANCE,
                page_writes_enabled=True,
                native_policy_digest=digest(self.native_assistance_policy),
            )
        identity = process_identity(os.getpid())
        if not valid_process_identity(identity):
            raise PortalDataError(
                "backend_authority_unavailable", "后端进程身份不能核验，请保留原运行。", 409
            )
        previous_authority = state.get("backend_authority")
        if (
            previous_authority
            and previous_authority["instance_id"] == self._backend_instance_id
            and digest(previous_authority["process"]) != digest(identity)
        ):
            raise PortalDataError(
                "backend_authority_changed", "后端进程世代已改变，请保留原运行。", 409
            )
        authority = {
            "instance_id": self._backend_instance_id,
            "process": identity,
        }
        state["backend_authority"] = {
            "protocol": CODEX_BACKEND_AUTHORITY,
            **deepcopy(authority),
            "status": "active",
            "published_at": time.time(),
            "revoked_at": None,
        }
        job["assistance"]["backend_authority"] = authority
        return job["assistance"]

    def takeover_candidate(
        self,
        application_id,
        *,
        expected_batch_id,
        expected_run_id,
        expected_task_id=None,
        hypothetical=False,
    ):
        """Read one current technical blocker without reserving a writer.

        ``hypothetical`` asks whether the reviewed policy would take this blocker over,
        for a takeover that is on but could not be configured (MC-22).
        """
        with self.store.applications.write_lock():
            state = self.store.load()
            job = self._bound_execution_job(
                state,
                application_id,
                expected_batch_id=expected_batch_id,
                expected_run_id=expected_run_id,
                expected_task_id=expected_task_id,
            )
            if self._backend_closed or self.store.stop_reason():
                return None
            if hypothetical:
                from .cua_driver import reviewed_native_assistance_policy

                return technical_blocker(state, job, reviewed_native_assistance_policy())
            return technical_blocker(state, job, self.native_assistance_policy)

    def request_takeover(
        self,
        application_id,
        *,
        expected_batch_id,
        expected_run_id,
        blocker,
        request_id,
        expected_task_id=None,
    ):
        """Reserve and system-claim one native Codex writer for the current blocker."""
        if (
            not isinstance(request_id, str)
            or not 1 <= len(request_id) <= 200
            or not request_id.isprintable()
            or not request_id.strip()
            or not isinstance(blocker, dict)
        ):
            raise PortalDataError("assistance_binding_changed", "接管派发请求无效。", 409)

        def identity(value):
            return [value.get(key) for key in ("code", "field_id", "page_id", "run_id")]

        with self.store.applications.write_lock():
            if self._backend_closed or self.store.stop_reason():
                raise PortalDataError("backend_closed", "控制服务不能派发接管。", 409)
            state = self.store.load()
            job = self._bound_execution_job(
                state,
                application_id,
                expected_batch_id=expected_batch_id,
                expected_run_id=expected_run_id,
                expected_task_id=expected_task_id,
            )
            previous = job.get("assistance")
            dispatch = (previous or {}).get("dispatch")
            if dispatch and dispatch["request_id"] == request_id:
                if identity(dispatch["blocker"]) != identity(blocker):
                    raise PortalDataError(
                        "assistance_request_conflict", "同一派发请求对应另一阻塞。", 409
                    )
                return {
                    "assistance_ref": assistance_reference(previous),
                    "dispatch": deepcopy(dispatch),
                }
            if (
                previous
                and previous["status"] in {"requested", "claimed", "stopping", "stop_unknown"}
                or takeover_record.request_conflict(job, request_id)
            ):
                raise PortalDataError(
                    "assistance_request_conflict", "已有接管记录，不能另建操作范围。", 409
                )
            if self.validate_write_preflight:
                self.validate_write_preflight("request-assistance")
            current = technical_blocker(state, job, self.native_assistance_policy)
            if current is None or identity(current) != identity(blocker):
                raise PortalDataError(
                    "assistance_takeover_unavailable", "当前阻塞不能派发接管，保留原页。", 409
                )
            if any(assistance_stop_pending(other) for other in state["jobs"]):
                raise PortalDataError(
                    "assistance_stop_pending", "原接管尚未确认停止，不能创建第二操作范围。", 409
                )
            self.store.check_single(job, state, material_required=False)
            require_execution(
                self.store.applications,
                job["application_id"],
                automated_owner(self.store.root, state["batch_id"], job["application_id"]),
                "automated",
            )
            binding = assistance_binding(state, job)
            assistance = self._new_assistance(state, job, binding, request_id)
            assistance.update(
                status="claimed",
                active_writer="codex",
                claim_request_id=request_id,
                dispatch={
                    "request_id": request_id,
                    "blocker": current,
                    "requested_at": time.time(),
                    "continue_serial": binding["resume_serial"],
                    # Every layer's deadline for this takeover, fixed when it is sent.
                    "budget": self.takeover_budget.to_dict(),
                },
            )
            if current["code"] in TAKEOVER_UNKNOWN_REASONS and job.get("intent"):
                assistance["dispatch"]["pending_intent_ref"] = digest(job["intent"])
            if not valid_assistance(assistance, job["application_id"]):
                raise PortalDataError(
                    "assistance_binding_changed", "原执行引用尚不能建立接管记录。", 409
                )
            self.store.save(state)
            return {
                "assistance_ref": assistance_reference(assistance),
                "dispatch": deepcopy(assistance["dispatch"]),
            }

    def _cancellation_projection(
        self, state, application_id, *, expected_batch_id, expected_run_id, expected_task_id=None
    ):
        job = self._bound_execution_job(
            state,
            application_id,
            expected_batch_id=expected_batch_id,
            expected_run_id=expected_run_id,
            expected_task_id=expected_task_id,
        )
        status = "active"
        if job["status"] == "cancelled":
            if (
                job.get("intent")
                or manual_submission_unresolved(job)
                or any(unresolved_write_failure(row, job, state) for row in job["observations"])
            ):
                status = "unknown"
            else:
                status = "stopping" if assistance_stop_pending(job) else "stopped"
        return {
            "application_id": application_id,
            "batch_id": state["batch_id"],
            "run_id": (state.get("runtime") or {}).get("id"),
            "task_id": (job.get("single_binding") or {}).get("task_id"),
            "status": status,
        }

    def validate_material_successor(self, application_id, *, target, edit, material):
        """Preflight one saved supplemental edit without changing either participant."""
        with self.store.applications.write_lock():
            _, job, old = self._checked_material_successor(application_id, target, edit, material)
            return {"old_material": deepcopy(old), "edit": deepcopy(job["material_edit"])}

    def commit_material_successor(self, application_id, *, target, edit, material):
        """Adopt only this original-page edit's saved human material and history."""
        with self.store.applications.write_lock():
            state, job, old = self._checked_material_successor(
                application_id, target, edit, material
            )
            if job["material_edit"]["status"] == "complete":
                return deepcopy(job["material_edit"])
            job.setdefault("material_history", []).append(deepcopy(old))
            job["materials"] = [
                deepcopy(material) if row.get("id") == old["id"] else row
                for row in job["materials"]
            ]
            job["precision_preparation"]["materials"] = deepcopy(job["materials"])
            job["material_edit"].update(status="complete", text_sha256=material["text_sha256"])
            self.store.save(state)
            return deepcopy(job["material_edit"])

    def _checked_material_successor(self, application_id, target, edit, material):
        state = self.store.load()
        job = self._job(state, application_id)
        precision = job.get("precision_preparation") or {}
        current = job.get("material_edit") or {}
        actual_target = {
            "batch_id": state["batch_id"],
            "task_id": precision.get("task_id"),
            "application_id": application_id,
            "run_id": (state.get("runtime") or {}).get("id"),
            "page_id": (job.get("page_observation") or {}).get("page_id"),
            "document_token": precision.get("document_token"),
        }
        if (
            self._backend_closed
            or self.store.stop_reason()
            or state.get("control") != "paused"
            or state.get("current_job_id") != application_id
            or job.get("status") != "needs_input"
            or job.get("intent")
            or job.get("handed_off")
            or job.get("manual_submission")
            or manual_submission_unresolved(job)
            or assistance_stop_pending(job)
            or any(unresolved_write_failure(row, job, state) for row in job.get("observations", []))
            or precision.get("status") != "ready"
            or precision.get("run_id") != actual_target["run_id"]
            or precision.get("page_id") != actual_target["page_id"]
            or not isinstance(edit, dict)
            or edit.get("status") not in {"preparing", "needs_recheck"}
            or target != actual_target
            or target != edit.get("target")
            or current.get("status") not in {"preparing", "needs_recheck", "complete"}
            or digest(dict(current, status="preparing")) != digest(dict(edit, status="preparing"))
        ):
            raise PortalDataError(
                "material_edit_changed", "原岗或编辑尝试已变化，新版本已保留。", 409
            )
        identifier = edit.get("request_id")
        if not isinstance(identifier, str) or re.fullmatch(r"[a-f0-9]{32}", identifier) is None:
            raise PortalDataError("material_edit_changed", "原附稿编辑标识不能核验。", 409)
        directory = self.store.root / "materials" / identifier
        try:
            if directory.is_symlink() or any(
                (directory / name).is_symlink()
                for name in ("intent.json", "material.json", "draft.txt")
            ):
                raise ValueError("candidate links")
            intent = helper.read_json_object(directory / "intent.json", "material edit intent")
            saved = helper.read_json_object(directory / "material.json", "material edit candidate")
            old = intent["old"]
            candidates = (
                job.get("material_history", [])
                if current["status"] == "complete"
                else job["materials"]
            )
            matching = [row for row in candidates if row.get("id") == edit["old_material_id"]]
            expected = deepcopy(old)
            expected.update(
                id=identifier,
                attempt_id=identifier,
                actor="user",
                human_reviewed=False,
                text=intent["text"],
                text_sha256=edit["text_sha256"],
                parent_material_id=old["id"],
                source_binding=dict(old["source_binding"], manual_edit=True),
            )
            for key in ("checks", "grounding", "paragraphs"):
                expected.pop(key, None)
            if old.get("letter_content"):
                from .application_cover_letter import edit_delivered_letter
                from .application_materials import read_cover_letter_template

                template = read_cover_letter_template(
                    self.store, old["source_binding"]["application"]
                )
                expected.update(
                    edit_delivered_letter(old, intent["text"], template, request_id=identifier)
                )
                for key in (
                    "file_path",
                    "filename",
                    "sha256",
                    "file_sha256",
                    "build",
                    "build_revision",
                    "tex_path",
                    "tex_sha256",
                ):
                    expected.pop(key, None)
            elif old["kind"] == "cover_letter":
                pdf = directory / "letter.pdf"
                if pdf.is_symlink():
                    raise ValueError("candidate pdf link")
                expected.update(
                    file_path=str(pdf),
                    filename="cover-letter.pdf",
                    sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                )
                if "file_sha256" in expected:
                    expected["file_sha256"] = expected["sha256"]
            if (
                intent["edit"] != dict(edit, status="preparing")
                or digest(old) != edit["old_sha256"]
                or len(matching) != 1
                or matching[0] != old
                or saved != material
                or material != expected
                or (directory / "draft.txt").read_text() != intent["text"]
                or hashlib.sha256(intent["text"].encode()).hexdigest() != edit["text_sha256"]
                or current["status"] == "complete"
                and [row for row in job["materials"] if row.get("id") == identifier] != [material]
            ):
                raise ValueError("candidate scope")
            capture = edit.get("captured_source")
            if capture is not None:
                source = Path(capture["path"])
                if (
                    source.is_symlink()
                    or not source.resolve().is_relative_to(
                        (self.store.root / "materials").resolve()
                    )
                    or hashlib.sha256(source.read_bytes()).hexdigest() != capture["sha256"]
                ):
                    raise PortalDataError(
                        "cover_letter_tex_changed", "接回期间 LaTeX 再次变化，新稿已保留。", 409
                    )
        except PortalDataError:
            raise
        except (OSError, ValueError, KeyError, TypeError, helper.StoreError) as error:
            raise PortalDataError(
                "material_changed", "原附稿或已保存的人工后继不能核验。", 409
            ) from error
        self.store.verify_material(old, job)
        self.store.verify_material(material, job)
        return state, job, old

    def _lift_checkpoint_stop(self, state):
        """An explicit Continue lifts the stop only once the unchanged checkpoint is
        durable again; otherwise the pause remains."""
        if not self.store.stop_reason():
            return
        try:
            self.store.check_applications_root(state)
            helper.atomic_write_json(self.store.path, state)
            self.store.stop_path.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError):
            raise PortalDataError(
                "checkpoint_unavailable", "填写记录保存失败，请保留暂停并核验。", 409
            ) from None
        self.store.storage_error = ""

    def lift_checkpoint_stop(self):
        """The Pipeline's explicit Continue, before a material update reads the Worker."""
        with self.store.applications.write_lock():
            self._lift_checkpoint_stop(self.store.load())

    def material_update_progress(self, application_id, update_id, *, expected_batch_id):
        """Read the original-page participant's saved completion without issuing control."""
        from .application_bound_materials import (
            failure,
            page_closed_receipt,
            read_commit_journal,
        )

        with self.store.applications.write_lock():
            if self.store.single_flow_root is None:
                raise failure("bound_material_journal_invalid")
            journal = read_commit_journal(self.store.single_flow_root, update_id)
            state = self.store.load()
            job = self._job(state, application_id)
            expected = journal["new_job"]
            current = {key: deepcopy(job.get(key)) for key in MATERIAL_COMMIT_FIELDS}
            mirror = current.get("material_update") or {}
            status = mirror.get("status")
            if status == "complete":
                attempt_id = mirror.get("upload_attempt_id")

                def original_upload(intent):
                    return (
                        isinstance(intent, dict)
                        and intent.get("action") == "upload"
                        and intent.get("material_update_id") == update_id
                        and (attempt_id is None or intent.get("attempt_id") == attempt_id)
                    )

                if original_upload(job.get("intent")) or any(
                    original_upload(row.get("intent")) and unresolved_write_failure(row, job, state)
                    for row in job["observations"]
                ):
                    raise failure("bound_material_journal_conflict")
                mirror["status"] = "bound"
                attempt_id = mirror.pop("upload_attempt_id", None)
                attachment = mirror.pop("new_attachment", None)
                if attempt_id is not None or attachment is not None:
                    result = effective_action_results(job).get(attempt_id, {})
                    completed = result.get("intent", {})
                    page = expected.get("material_update", {}).get("page_receipt", {})
                    if (
                        not isinstance(attempt_id, str)
                        or not attempt_id
                        or result.get("conclusion") != "current_matches"
                        or completed.get("action") != "upload"
                        or completed.get("material_update_id") != update_id
                        or completed.get("sha256") != expected["file_sha256"]
                        or completed.get("run_id") != page.get("run_id")
                        or completed.get("page_id") != page.get("page_id")
                        or attachment is not None
                        and (
                            not isinstance(attachment, dict)
                            or attachment.get("attempt_id") != attempt_id
                            or attachment.get("sha256") != expected["file_sha256"]
                            or attachment.get("field_id") != completed.get("field_id")
                            or attachment.get("draft_path") != completed.get("draft_path")
                        )
                    ):
                        raise failure("bound_material_journal_conflict")
            receipt = expected.get("material_update", {}).get("page_receipt", {})
            if (
                journal["status"] != "bound"
                or state["batch_id"] != expected_batch_id
                or expected_batch_id != journal["batch_id"]
                or journal["application_id"] != application_id
                or state.get("current_job_id") != application_id
                or job["status"] == "cancelled"
                or status not in {"bound", "complete"}
                or digest(current) != digest(expected)
                or digest(
                    assistance_reference(job["assistance"]) if job.get("assistance") else None
                )
                != digest(journal.get("execution_claim"))
                or "worker_controller" in journal
                and state.get("controller") != journal["worker_controller"]
                or not page_closed_receipt(receipt, job)
                and (
                    receipt.get("run_id") != (state.get("runtime") or {}).get("id")
                    or receipt.get("page_id") != (job.get("page_observation") or {}).get("page_id")
                )
            ):
                raise failure("bound_material_journal_conflict")
            self.store.check_single(job, state)
            if page_closed_receipt(receipt, job):
                # No page holds an upload to replace; the reopened page uses these.
                status = "complete"
            return {
                "application_id": application_id,
                "task_id": journal["task_id"],
                "batch_id": state["batch_id"],
                "run_id": receipt["run_id"],
                "material_update_id": update_id,
                "status": status,
            }

    def validate_material_update(self, application_id, update_id, *, expected_batch_id):
        """Check this journal participant without adopting any material fields."""
        with self.store.applications.write_lock():
            self._checked_material_update(application_id, update_id, expected_batch_id)
            return {
                "application_id": application_id,
                "material_update_id": update_id,
                "status": "ready",
            }

    def commit_material_update(self, application_id, update_id, *, expected_batch_id):
        """Adopt only the retained original-page material journal's Worker fields."""
        with self.store.applications.write_lock():
            current = self._job(self.store.load(), application_id)
            if current.get("material_update", {}).get("status") == "complete":
                return self.material_update_progress(
                    application_id, update_id, expected_batch_id=expected_batch_id
                )
            state, job, new = self._checked_material_update(
                application_id, update_id, expected_batch_id
            )
            if digest({key: job.get(key) for key in new}) != digest(new):
                job.update(deepcopy(new))
                self.store.save(state)
            return {
                "application_id": application_id,
                "material_update_id": update_id,
                "status": "bound",
            }

    def verify_material_update(self, application_id, update_id, *, expected_batch_id):
        """Run the ordinary strict binding check after all journal participants have adopted."""
        with self.store.applications.write_lock():
            state, job, new = self._checked_material_update(
                application_id, update_id, expected_batch_id
            )
            if digest({key: job.get(key) for key in new}) != digest(new):
                from .application_bound_materials import failure

                raise failure("bound_material_journal_conflict")
            self.store.check_single(job, state)
            return {
                "application_id": application_id,
                "material_update_id": update_id,
                "status": "verified",
            }

    def _checked_material_update(self, application_id, update_id, expected_batch_id):
        from .application_bound_materials import failure, read_commit_journal

        if self.store.single_flow_root is None:
            raise failure("bound_material_journal_invalid")
        journal = read_commit_journal(self.store.single_flow_root, update_id)
        state = self.store.load()
        job = self._job(state, application_id)
        fields = set(MATERIAL_COMMIT_FIELDS)
        old, new = journal["old_job"], journal["new_job"]
        if (
            self._backend_closed
            or self.store.stop_reason()
            or expected_batch_id != journal["batch_id"]
            or state["batch_id"] != expected_batch_id
            or state.get("current_job_id") != application_id
            or journal["application_id"] != application_id
            or state["control"] != "paused"
            or job["status"] == "cancelled"
            or job.get("intent")
            or job.get("manual_submission")
            or manual_submission_unresolved(job)
            or assistance_stop_pending(job)
            or digest(assistance_reference(job["assistance"]) if job.get("assistance") else None)
            != digest(journal.get("execution_claim"))
            or "worker_controller" in journal
            and state.get("controller") != journal["worker_controller"]
            or "worker_resume_serial" in journal
            and state.get("resume_serial", 0) != journal["worker_resume_serial"]
            or set(old) != fields
            or set(new) != fields
            or digest({key: job.get(key) for key in fields}) not in {digest(old), digest(new)}
            or job.get("material_update", {}).get("id") != update_id
            or not isinstance(old.get("single_binding"), dict)
            or not isinstance(new.get("single_binding"), dict)
            or not isinstance(old.get("material_update"), dict)
            or not isinstance(new.get("material_update"), dict)
            or new["material_update"].get("id") != update_id
            or new["material_update"].get("status") != "bound"
            or new["material_update"].get("new_sha256") != new["file_sha256"]
            or digest(
                {
                    key: value
                    for key, value in new["material_update"].items()
                    if key not in {"status", "new_sha256"}
                }
            )
            != digest(
                {
                    key: value
                    for key, value in old["material_update"].items()
                    if key not in {"status", "new_sha256"}
                }
            )
            or new["single_binding"].get("task_id") != journal["task_id"]
            or digest(
                {
                    key: value
                    for key, value in new["single_binding"].items()
                    if key not in {"inputs", "resume_id", "resume_sha256"}
                }
            )
            != digest(
                {
                    key: value
                    for key, value in old.get("single_binding", {}).items()
                    if key not in {"inputs", "resume_id", "resume_sha256"}
                }
            )
            or any(
                new["single_binding"].get(key) != journal["new"].get(key)
                for key in ("inputs", "resume_id", "resume_sha256")
            )
            or new["file_sha256"] != journal["new"].get("resume_sha256")
            or new["filename"] != old["filename"]
        ):
            raise failure("bound_material_journal_conflict")
        receipt = new.get("material_update", {}).get("page_receipt", {})
        from .application_bound_materials import page_closed_receipt

        if not page_closed_receipt(receipt, job) and (
            receipt.get("run_id") != (state.get("runtime") or {}).get("id")
            or receipt.get("page_id") != (job.get("page_observation") or {}).get("page_id")
            or not worker_lock_is_held(self.store.root, receipt.get("worker_lock"))
        ):
            raise failure("bound_material_owner_unknown")
        require_execution(
            self.store.applications,
            application_id,
            automated_owner(self.store.root, state["batch_id"], application_id),
            "automated",
        )
        resume_id = new["single_binding"].get("resume_id")
        if (
            not isinstance(resume_id, str)
            or not resume_id
            or Path(resume_id).name != resume_id
            or resume_id in {".", ".."}
        ):
            raise failure("flow_materials_changed")
        path = self.store.single_flow_root / "resumes" / resume_id / "resume.pdf"
        if str(path) != new["file_path"] or path.is_symlink() or path.parent.is_symlink():
            raise failure("flow_materials_changed")
        raw = path.read_bytes()
        if (
            len(raw) > 700000
            or not raw.startswith(b"%PDF-")
            or hashlib.sha256(raw).hexdigest() != new["file_sha256"]
        ):
            raise failure("flow_materials_changed")
        return state, job, new

    def cancellation_progress(
        self, application_id, *, expected_batch_id, expected_run_id=None, expected_task_id=None
    ):
        """Read cancellation facts without resolving effects or issuing control."""
        with self.store.applications.write_lock():
            return self._cancellation_projection(
                self.store.load(),
                application_id,
                expected_batch_id=expected_batch_id,
                expected_run_id=expected_run_id,
                expected_task_id=expected_task_id,
            )

    def cancel_execution(
        self, application_id, *, expected_batch_id, expected_run_id=None, expected_task_id=None
    ):
        """Cancel only the bound execution; stale materials cannot prevent revocation."""
        with self.store.applications.write_lock():
            state = self.store.load()
            self._cancellation_projection(
                state,
                application_id,
                expected_batch_id=expected_batch_id,
                expected_run_id=expected_run_id,
                expected_task_id=expected_task_id,
            )
            result = self._request_guarded("cancel-job", {"application_id": application_id})
            result["execution_cancellation"] = self._cancellation_projection(
                self.store.load(),
                application_id,
                expected_batch_id=expected_batch_id,
                expected_run_id=expected_run_id,
                expected_task_id=expected_task_id,
            )
            return result

    def request(self, operation: str, payload: dict) -> dict:
        preflight = self.write_preflight
        with (
            preflight(operation, payload)
            if preflight
            and operation
            in {
                "prepare",
                "resume",
                "recheck",
                "answer",
                "library",
                "heartbeat",
                "provide-material",
                "retry-cover-letter-file",
                "recheck-cover-letter-file",
                "resolve-form-differences",
                "request-assistance",
                "claim-assistance",
            }
            else nullcontext()
        ):
            return self._measured_request(operation, payload)

    def _measured_request(self, operation: str, payload: dict) -> dict:
        measurements = self.store.measurements
        if operation == "heartbeat":
            return self._request(operation, payload)
        if operation == "prepare" and isinstance(payload.get("jobs"), list):
            payload = deepcopy(payload)
            for item in payload["jobs"]:
                if isinstance(item, dict) and isinstance(item.get("application_id"), str):
                    item["measurement_id"] = measurements.begin(
                        item["application_id"],
                        episode_id=item.get("measurement_id"),
                        resume_source="generated_resume"
                        if item.get("measurement_id")
                        else "preselected_pdf",
                    )
        items = (
            payload.get("jobs", [])
            if operation == "prepare" and isinstance(payload.get("jobs"), list)
            else []
        )
        job = items[0] if len(items) == 1 and isinstance(items[0], dict) else {}
        episode = job.get("measurement_id")
        if not episode and isinstance(payload.get("application_id"), str):
            with self.store.applications.write_lock():
                current = next(
                    (
                        j
                        for j in self.store.load()["jobs"]
                        if j["application_id"] == payload["application_id"]
                    ),
                    {},
                )
                episode = current.get("measurement_id")
        with measurements.stage(
            "worker_request",
            episode_id=episode,
            application_id=job.get("application_id", payload.get("application_id")),
            operation=operation,
        ):
            result = self._request(operation, payload)
            if operation not in {
                "heartbeat",
                "prepare",
                "answer",
                "library",
                "request-assistance",
                "claim-assistance",
            }:
                measurements.event(
                    "user_operation",
                    operation=operation,
                    source="synthetic" if result["mode"] == "synthetic" else "ui",
                )
            return result

    def _request(self, operation: str, payload: dict) -> dict:
        preflight = self.write_preflight
        with (
            (
                preflight(operation, payload)
                if preflight
                and operation
                in {
                    "prepare",
                    "resume",
                    "recheck",
                    "answer",
                    "library",
                    "heartbeat",
                    "provide-material",
                    "retry-cover-letter-file",
                    "recheck-cover-letter-file",
                    "resolve-form-differences",
                    "request-assistance",
                    "claim-assistance",
                }
                else nullcontext()
            ),
            self.store.applications.write_lock(),
        ):
            if self._backend_closed and operation != "pause":
                raise PortalDataError(
                    "backend_closed", "控制服务已关闭，请保留原运行并重新打开。", 409
                )
            return self._request_guarded(operation, payload)

    def _request_guarded(self, operation: str, payload: dict) -> dict:
        if operation in {"request-assistance", "claim-assistance"}:
            state = self.store.load()
            if self.validate_write_preflight:
                self.validate_write_preflight(operation)
            job = self._job(state, payload.get("application_id"))
            binding = assistance_binding(state, job)
            reference = payload.get("assistance_ref")
            supplied_binding = (
                payload.get("binding")
                if operation == "request-assistance"
                else reference.get("binding")
                if isinstance(reference, dict)
                else None
            )
            if (
                state["control"] != "running"
                or state.get("current_job_id") != job["application_id"]
                or job.get("workflow") != "single"
                or job["status"] == "cancelled"
                or job.get("handed_off")
                or job.get("manual_submission")
                or job.get("intent")
                or state["commands"]
                or manual_submission_unresolved(job)
                or any(unresolved_write_failure(event, job, state) for event in job["observations"])
                or material_edit_pending(job)
                or self.store.stop_reason()
                or binding is None
                or supplied_binding != binding
                or not isinstance(payload.get("request_id"), str)
                or not 1 <= len(payload["request_id"]) <= 200
                or not payload["request_id"].strip()
            ):
                raise PortalDataError(
                    "assistance_binding_changed", "原页、材料或未决动作尚不能交接。", 409
                )
            self.store.check_single(job, state, material_required=False)
            require_execution(
                self.store.applications,
                job["application_id"],
                automated_owner(self.store.root, state["batch_id"], job["application_id"]),
                "automated",
            )
            previous = job.get("assistance")
            if operation == "claim-assistance":
                if (
                    previous
                    and previous["protocol"] == CODEX_NATIVE_ASSISTANCE
                    and (
                        self.native_assistance_policy is None
                        or previous["native_policy_digest"] != digest(self.native_assistance_policy)
                    )
                ):
                    raise PortalDataError(
                        "native_assistance_unavailable", "原生接管配置已改变，保留原页。", 409
                    )
                if (
                    not assistance_backend_permitted(state, previous)
                    or previous["backend_authority"]["instance_id"] != self._backend_instance_id
                ):
                    raise PortalDataError(
                        "backend_authority_changed", "原接管后端已失效，请保留原页和占用。", 409
                    )
                if (
                    not previous
                    or reference != assistance_reference(previous)
                    or previous["binding"] != binding
                    or previous["status"] not in {"requested", "claimed"}
                    or previous["claim_request_id"] not in (None, payload["request_id"])
                ):
                    raise PortalDataError(
                        "assistance_claim_changed", "接管记录已改变，保留原操作范围。", 409
                    )
                if previous["status"] == "requested":
                    previous.update(
                        status="claimed",
                        active_writer="codex",
                        claim_request_id=payload["request_id"],
                    )
                    self.store.save(state)
                return self.snapshot()
            if previous:
                if (
                    previous["request_id"] != payload["request_id"]
                    or previous["binding"] != binding
                ):
                    raise PortalDataError(
                        "assistance_request_conflict", "已有接管记录，不能另建操作范围。", 409
                    )
                return self.snapshot()
            if any(assistance_stop_pending(other) for other in state["jobs"]):
                raise PortalDataError(
                    "assistance_stop_pending", "原接管尚未确认停止，不能创建第二操作范围。", 409
                )
            self._new_assistance(state, job, binding, payload["request_id"])
            if not valid_assistance(job["assistance"], job["application_id"]):
                raise PortalDataError(
                    "assistance_binding_changed", "原执行引用尚不能建立接管记录。", 409
                )
            self.store.save(state)
            return self.snapshot()
        if operation in {"inspect-handoff", "verify-handoff"}:
            with self.store.applications.write_lock():
                state = self.store.load()
                job = self._job(state, payload.get("application_id"))
                runtime = state.get("runtime") or {}
                target = self._page_inspection_target(state, job)
                identity = process_identity(runtime.get("pid"))
                if (
                    target is None
                    or payload.get("binding") != target
                    or CONTROLLER_HANDOFF_INSPECTION not in runtime.get("capabilities", ())
                    or identity is None
                    or self.store.stop_reason()
                    or state.get("commands")
                ):
                    raise PortalDataError(
                        "handoff_inspection_unverified", "请保留原运行并核验交接证据。", 409
                    )
                binding = handoff_binding(state, job)
                if operation == "inspect-handoff":
                    receipt = {
                        "protocol": CONTROLLER_HANDOFF_INSPECTION,
                        "request_id": uuid4().hex,
                        "status": "pending",
                        "requested_at": time.time(),
                        "binding": binding,
                        "process_identity": identity,
                        "execution_authority": False,
                    }
                    runtime["controller_handoff"] = receipt
                    state["commands"].append(
                        {
                            "action": "inspect-handoff",
                            "id": job["application_id"],
                            "request_id": receipt["request_id"],
                        }
                    )
                    self.store.save(state)
                else:
                    receipt = runtime.get("controller_handoff") or {}
                    snapshot = receipt.get("page_snapshot") or {}
                    owner = snapshot.get("owner") or {}
                    owner_at = owner.get("observed_at")
                    owner_valid = (
                        owner.get("status") == "accepted"
                        and type(owner.get("pid")) is int
                        and owner["pid"] > 0
                        and type(owner.get("window_id")) is int
                        and owner["window_id"] > 0
                        and isinstance(owner_at, (int, float))
                        and 0 <= time.time() - owner_at < 10
                        and owner.get("driver_version") is not None
                    ) or (
                        not self.cua
                        and owner == {"status": "not_used", "transport": "retained-playwright"}
                    )
                    try:
                        file_matches = (
                            hashlib.sha256(Path(job["file_path"]).read_bytes()).hexdigest()
                            == job["file_sha256"]
                        )
                    except OSError:
                        file_matches = False
                    if (
                        receipt.get("protocol") != CONTROLLER_HANDOFF_INSPECTION
                        or receipt.get("status") != "captured"
                        or not 0 <= time.time() - receipt.get("captured_at", 0) < 10
                        or receipt.get("binding") != binding
                        or receipt.get("process_identity") != identity
                        or snapshot.get("status") != "captured"
                        or snapshot.get("at") != receipt.get("captured_at")
                        or snapshot.get("binding") != target
                        or snapshot.get("worker_source") != runtime["source"]["sha256"]
                        or not (snapshot.get("document") or {}).get("loader_id")
                        or (snapshot.get("document") or {}).get("url")
                        != (snapshot.get("data") or {}).get("url")
                        or not owner_valid
                        or not worker_lock_is_held(self.store.root, receipt.get("worker_lock"))
                        or not file_matches
                    ):
                        raise PortalDataError(
                            "handoff_inspection_unverified",
                            "原运行交接证据已改变，请保持暂停。",
                            409,
                        )
                    # Diagnostic evidence alone never adopts a process or admits execution.
                    receipt["verification"] = {
                        "state": "validated_capture_receipt",
                        "scope": "captured_page_snapshot",
                        "captured_at": snapshot["at"],
                        "current_page_verified": False,
                        "at": time.time(),
                        "execution_authority": False,
                    }
                    self.store.save(state)
            return self.snapshot()
        if operation == "observe-page":
            with self.store.applications.write_lock():
                state = self.store.load()
                job = self._job(state, payload.get("application_id"))
                binding = self._page_inspection_target(state, job)
                if binding is None or payload.get("binding") != binding:
                    raise PortalDataError(
                        "page_observation_unavailable",
                        "请保持暂停并核验原执行器版本、所属原页与连接；不能另开页面代替观察。",
                        409,
                    )
                previous = job.get("owned_page_inspection") or {}
                if (
                    previous.get("status") == "pending"
                    and 0 <= time.time() - previous["requested_at"] < 10
                ):
                    raise PortalDataError(
                        "page_observation_pending", "所属原页观察仍在等待回读。", 409
                    )
                receipt = {
                    "request_id": uuid4().hex,
                    "binding": binding,
                    "status": "pending",
                    "requested_at": time.time(),
                    "controller_protocol": OWNED_PAGE_OBSERVATION,
                }
                job["owned_page_inspection"] = receipt
                state["commands"].append(
                    {
                        "action": "observe-page",
                        "id": job["application_id"],
                        "binding": binding,
                        "request_id": receipt["request_id"],
                    }
                )
                self.store.save(state)
            return self.snapshot()
        with self.store.applications.write_lock():
            state = self.store.load()
            if operation in {"resume", "reopen-current"}:
                self._lift_checkpoint_stop(state)
            admission = None
            if (
                operation
                in {
                    "prepare",
                    "resume",
                    "recheck",
                    "answer",
                    "library",
                    "heartbeat",
                    "provide-material",
                    "retry-cover-letter-file",
                    "recheck-cover-letter-file",
                    "resolve-form-differences",
                }
                and self.validate_write_preflight
            ):
                admission = self.validate_write_preflight(operation)
            if operation == "observe-result":
                job = self._job(state, payload.get("application_id"))
                request_id = payload.get("request_id")
                if (
                    state.get("current_job_id") != job["application_id"]
                    or not isinstance(request_id, str)
                    or not 1 <= len(request_id) <= 100
                ):
                    raise PortalDataError("current_job_changed", "请观察当前岗位原页。", 409)
                observed = job.get("submission_observation") or {}
                if observed.get("request_id") == request_id:
                    return self.snapshot()
                if not self._page_current(state, job) or not job["page_open"]:
                    raise PortalDataError("page_lost", "结果原页不能核验，不能推断提交成功。", 409)
                if observed:
                    job.setdefault("submission_observation_history", []).append(deepcopy(observed))
                job["submission_observation"] = {
                    "request_id": request_id,
                    "status": "pending",
                    "at": time.time(),
                    "run_id": state["runtime"]["id"],
                    "page_id": job["page_observation"]["page_id"],
                }
                state["commands"].append(
                    {
                        "action": "observe-result",
                        "id": job["application_id"],
                        "request_id": request_id,
                    }
                )
            elif operation == "continue-current":
                job = self._job(state, payload.get("application_id"))
                if material_edit_pending(job):
                    raise PortalDataError(
                        "material_edit_needs_recheck", "材料编辑尚未完成，请保留原稿核验。", 409
                    )
                if (
                    "current_job_id" not in state
                    or state["current_job_id"] != job["application_id"]
                ):
                    raise PortalDataError("current_job_changed", "请保留当前岗位原页。", 409)
                request_id, controller = payload.get("request_id"), payload.get("controller")
                if (
                    not isinstance(request_id, str)
                    or not 1 <= len(request_id) <= 100
                    or not isinstance(controller, str)
                    or not 8 <= len(controller) <= 100
                ):
                    raise PortalDataError("controller_required", "继续操作缺少标识。", 409)
                if manual_submission_unresolved(job):
                    raise PortalDataError(
                        "submission_result_unknown",
                        "人工提交结果仍未知，请保留原页继续观察；不会重填或重传。",
                        409,
                    )
                history = job.setdefault("continuation_requests", [])
                if request_id in history:
                    return self.snapshot()
                if job.get("manual_submission") or job["status"] == "cancelled":
                    raise PortalDataError(
                        "already_submitted", "此岗位已有终结结果，保留原记录。", 409
                    )
                if not self._page_current(state, job) or not job["page_open"]:
                    raise PortalDataError(
                        "page_lost", "原页不能核验，保留已有资料与未决动作。", 409
                    )
                history.append(request_id)
                # The runner keeps this command until script writes are allowed again.
                archive_stopped_assistance(job)
                state.update(control="paused", controller=controller)
                if job.get("continuation"):
                    job.setdefault("continuation_history", []).append(deepcopy(job["continuation"]))
                job["continuation"] = {
                    "request_id": request_id,
                    "status": "pending",
                    "run_id": state["runtime"]["id"],
                    "page_id": job["page_observation"]["page_id"],
                    "at": time.time(),
                }
                state["commands"].append(
                    {
                        "action": "continue-current",
                        "id": job["application_id"],
                        "request_id": request_id,
                        "controller": controller,
                    }
                )
            elif operation == "reopen-current":
                # APP-13: the original page is gone with its run; a new run opens the
                # same job on a new page and reuses saved facts. The old page and its
                # form stay history; an unknown action or submission still waits.
                job = self._job(state, payload.get("application_id"))
                request_id, controller = payload.get("request_id"), payload.get("controller")
                if (
                    not isinstance(request_id, str)
                    or not 1 <= len(request_id) <= 100
                    or not isinstance(controller, str)
                    or not 8 <= len(controller) <= 100
                ):
                    raise PortalDataError("controller_required", "继续操作缺少标识。", 409)
                assistance = job.get("assistance") or {}
                # Reopen runs only after the old run exited; its native driver went with
                # it, so a stopped Codex with revoked tools cannot still write.
                stop = assistance.get("stop") or {}
                retired = assistance.get("status") == "stopped" or (
                    stop.get("process_stopped") is True and stop.get("tools_revoked") is True
                )
                # A native handoff that never carried a call could not touch the page.
                # One that did may retire only with its stopped takeover, once tools
                # are revoked and the page is lost; its calls stay in the reopen record.
                native_runs = job.get("native_handoff_runs", [])
                native_calls = any(
                    (event.get("receipt") or {}).get("calls")
                    for run in native_runs
                    for event in run.get("events", [])
                ) and not (retired and stop.get("tools_revoked") is True)
                if (
                    state.get("current_job_id") != job["application_id"]
                    or job["status"] not in {"needs_recheck", "queued"}
                    or job.get("page_open")
                    and job["status"] == "queued"
                    or assistance
                    and assistance.get("active_writer") != "script"
                    and not retired
                    or not takeover_record.capacity_left(job)
                    # Opening the page sends no application data; any other unknown
                    # action still waits for its result.
                    or (job.get("intent") or {}).get("action") not in (None, "open")
                    or job.get("handed_off")
                    or job.get("manual_submission")
                    or manual_submission_unresolved(job)
                    or material_edit_pending(job)
                    or assistance_stop_pending(job)
                    and not retired
                    or native_calls
                    or self._page_current(state, job)
                    or self.process is not None
                    and self.process.poll() is None
                ):
                    raise PortalDataError(
                        "page_lost", "原页不能核验，保留已有资料与未决动作。", 409
                    )
                if (state.get("page_reopen") or {}).get("request_id") == request_id:
                    return self.snapshot()
                # A takeover, stopped or finished, belonged to the closed page.
                retired_stop = takeover_record.retire_for_reopen(job)
                job["observations"].append(
                    {
                        "action": "page_reopen_requested",
                        "request_id": request_id,
                        "previous_page": deepcopy(job.get("page_observation")),
                        "previous_open_intent": deepcopy(job.get("intent")),
                        "retired_takeover_stop": retired_stop,
                        "retired_native_handoff_runs": compact_native_runs(deepcopy(native_runs)),
                        "reason": job.get("reason"),
                        "at": time.time(),
                    }
                )
                if job.get("form_state"):
                    job.setdefault("form_history", []).append(job.pop("form_state"))
                job.update(status="queued", reason="", page_open=False, intent=None)
                if native_runs:
                    job["native_handoff_runs"] = []
                application = self.store.applications.get_application(job["application_id"])
                platform, url = _job_identity(
                    application["url"], allow_generic=state.get("generic_enabled") is True
                )
                if url != job["job_url"]:
                    # The user corrected the link; the new run's binding checks compare
                    # it with the moved send authorization and the unchanged JD.
                    job["observations"].append(
                        {
                            "action": "job_url_corrected",
                            "previous": {key: job[key] for key in ("job_url", "revision")},
                            "at": time.time(),
                        }
                    )
                    job.update(job_url=url, platform=platform, revision=application["revision"])
                    if "job_url" in (job.get("single_binding") or {}):
                        job["single_binding"]["job_url"] = url
                state.update(control="running", controller=controller, worker_error="")
                state["page_reopen"] = {
                    "request_id": request_id,
                    "application_id": job["application_id"],
                    "status": "pending",
                    "at": time.time(),
                }
            elif operation in {"skip-current", "select-current"}:
                if "current_job_id" not in state:
                    raise PortalDataError(
                        "current_job_unavailable", "旧批次须保留原控制方式。", 409
                    )
                job = self._job(state, payload.get("application_id"))
                request_id = payload.get("request_id")
                if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
                    raise PortalDataError("request_id_required", "请保留本次操作标识。", 409)
                requests = state.setdefault("selection_history", [])
                if any(row["request_id"] == request_id for row in requests):
                    return self.snapshot()
                if operation == "skip-current" and state["current_job_id"] != job["application_id"]:
                    raise PortalDataError("current_job_changed", "当前岗位已变化。", 409)
                if operation == "select-current" and state["current_job_id"] not in {
                    None,
                    job["application_id"],
                }:
                    raise PortalDataError(
                        "current_job_exists", "请先跳过当前岗位，再返回旧岗。", 409
                    )
                revoke_assistance(job, reason=operation)
                cancel_continuation(job, operation)
                recovery = state.get("backend_recovery") or {}
                if (
                    recovery.get("status") in {"suspended", "pending"}
                    and recovery.get("binding", {}).get("application_id") == job["application_id"]
                ):
                    recovery.update(status="cancelled", reason=operation)
                state.update(
                    control="paused",
                    current_job_id=None if operation == "skip-current" else job["application_id"],
                )
                requests.append(
                    {
                        "request_id": request_id,
                        "operation": operation,
                        "application_id": job["application_id"],
                        "at": time.time(),
                    }
                )
            elif operation == "prepare":
                self._prepare(
                    state, payload, admission=admission if isinstance(admission, dict) else None
                )
            elif operation == "provide-material":
                self._provide_material(state, payload)
            elif operation == "retry-cover-letter-file":
                self._retry_cover_letter_file(state, payload)
            elif operation == "recheck-cover-letter-file":
                self._recheck_cover_letter_file(state, payload)
            elif operation == "answer":
                self._answer(state, payload)
            elif operation == "resolve-form-differences":
                self._resolve_form_differences(state, payload)
            elif operation == "correct-email":
                job = self._job(state, payload.get("application_id"))
                application = self.store.applications.get_application(job["application_id"])
                if job.get("manual_submission") or application["status"] != "drafting":
                    raise PortalDataError(
                        "already_submitted", "岗位记录已进入后续阶段，不能更正填写。", 409
                    )
                binding = self._email_correction_target(state, job)
                if binding is None or payload.get("binding") != binding:
                    raise PortalDataError(
                        "email_correction_target_changed", "请暂停并核验当前原页与邮箱字段。", 409
                    )
                self.store.check_single(job, state)
                value = payload.get("value")
                if (
                    not isinstance(value, str)
                    or len(value) > 254
                    or re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) is None
                ):
                    raise PortalDataError("email_required", "请输入已确认的完整邮箱。")
                job.setdefault("email_corrections", []).append(
                    {
                        "id": uuid4().hex,
                        "binding": binding,
                        "value": value,
                        "scope": {"application_id": job["application_id"]},
                        "prior_intent": deepcopy(job["intent"]),
                        "prior_answer_refs": deepcopy(job["answer_refs"]),
                        "prior_status": job["status"],
                        "prior_reason": job.get("reason", ""),
                        "at": time.time(),
                    }
                )
                if job["status"] != "needs_recheck":
                    job.update(status="needs_recheck", reason="email_correction_pending")
            elif operation == "library":
                self._edit_library(state, payload)
            elif operation in {"resume", "pause", "heartbeat", "cancel"}:
                controller = payload.get("controller")
                if not isinstance(controller, str) or not 8 <= len(controller) <= 100:
                    raise PortalDataError("controller_required", "请从控制页面操作。")
                if operation == "resume":
                    if state.get("runtime") and state.get("worker_error") in {
                        "context_closed",
                        "browser_disconnected",
                        "browser_connection_unknown",
                    }:
                        raise PortalDataError("runtime_lost", "请先启动新运行，再核验旧进度。", 409)
                    if "current_job_id" in state and state["current_job_id"] is None:
                        raise PortalDataError("current_job_missing", "请先明确选择当前岗位。", 409)
                    if not state["jobs"] or state["control"] == "cancelled":
                        raise PortalDataError("batch_not_ready", "请先准备新批次。", 409)
                    for job in state["jobs"]:
                        if (
                            "current_job_id" in state
                            and job["application_id"] != state["current_job_id"]
                        ):
                            continue
                        archive_stopped_assistance(job)
                        authentication = (
                            job["status"] == "needs_recheck"
                            and job.get("reason") == "user_authentication"
                            and job["intent"] is None
                            and job["page_open"]
                            and not job.get("manual_submission")
                        )
                        if (
                            job["status"] not in {"queued", "filling", "needs_input"}
                            and not authentication
                            or job["handed_off"]
                        ):
                            continue
                        try:
                            fixed_qualification = False
                            if not admission:
                                fixed_qualification = (
                                    self.store.check_single(job, state, material_required=False)
                                    is True
                                )
                            if authentication:
                                require_execution(
                                    self.store.applications,
                                    job["application_id"],
                                    automated_owner(
                                        self.store.root, state["batch_id"], job["application_id"]
                                    ),
                                    "automated",
                                )
                            reserve_execution(
                                self.store.applications,
                                job["application_id"],
                                automated_owner(
                                    self.store.root, state["batch_id"], job["application_id"]
                                ),
                                "automated",
                            )
                            if authentication:
                                app = self._recheck_inputs(state, job, admission)
                            else:
                                self.store.check_generic_enabled(job, state)
                            if not admission and not authentication:
                                validate_application_target(
                                    self.store.applications,
                                    job["application_id"],
                                    job["revision"],
                                    allow_generic=self.generic,
                                )
                            if self.live and not admission and not fixed_qualification:
                                self.store.check_language_requirement(
                                    self.store.applications.get_application(job["application_id"]),
                                    country=job["country"],
                                )
                            if authentication:
                                job["observations"].append(
                                    {
                                        "action": "inputs_rechecked",
                                        "at": time.time(),
                                        "run_id": state.get("runtime", {}).get("id"),
                                        "revision": app["revision"],
                                        "file_sha256": job["file_sha256"],
                                        "source": "user_continued_authentication",
                                    }
                                )
                                job.update(revision=app["revision"], status="queued", reason="")
                                state["commands"].append(
                                    {
                                        "action": "recheck",
                                        "id": job["application_id"],
                                        "authentication": True,
                                    }
                                )
                        except PortalDataError as error:
                            job.update(status="needs_recheck", reason=error.code)
                            self.store.sync(
                                job,
                                "发现相同或疑似相同岗位记录：已暂停该岗位，请先核对投递历史。"
                                if error.code == "duplicate_application"
                                else "自动填表暂停该岗位：请核验页面、笔记和简历。",
                            )
                    state.update(
                        control="running",
                        controller=controller,
                        heartbeat_at=time.time(),
                        worker_error="",
                        resume_serial=state.get("resume_serial", 0) + 1,
                    )
                    if any(
                        job.get("workflow") == "single" and job["status"] == "needs_recheck"
                        for job in state["jobs"]
                        if "current_job_id" not in state
                        or job["application_id"] == state["current_job_id"]
                    ):
                        state["control"] = "paused"
                elif controller != state["controller"] and not (
                    operation == "cancel" and state["control"] == "paused"
                ):
                    raise PortalDataError("controller_changed", "另一窗口已接管批次。", 409)
                elif operation == "heartbeat":
                    state["heartbeat_at"] = time.time()
                elif operation == "pause":
                    state["control"] = "paused"
                    for job in state["jobs"]:
                        revoke_assistance(job, reason="user_paused")
                        cancel_continuation(job, "user_paused")
                    if state.get("backend_recovery"):
                        state["backend_recovery"].update(status="cancelled", reason="user_paused")
                else:
                    state["control"] = "cancelled"
                    for job in state["jobs"]:
                        revoke_assistance(job, reason="cancelled")
                        cancel_continuation(job, "cancelled")
                        job["status"] = "cancelled"
            elif operation in {
                "review",
                "recheck",
                "release",
                "cancel-job",
                "retry-sync",
                "submitted",
                "receipt",
                "resolve-action",
                "settle-cancelled",
            }:
                job = self._job(state, payload.get("application_id"))
                if operation == "resolve-action":
                    intent = job["intent"]
                    source = payload.get("source")
                    conclusion = payload.get("conclusion")
                    if (
                        not intent
                        or payload.get("intent_ref") != (intent.get("attempt_id") or digest(intent))
                        or conclusion not in {"current_matches", "not_applied", "manual_stop"}
                        or not isinstance(source, str)
                        or not 1 <= len(source.strip()) <= 1000
                    ):
                        raise PortalDataError(
                            "action_resolution_required",
                            "请针对当前动作填写具体结论和已核验来源。",
                            409,
                        )
                    job.setdefault("action_resolutions", []).append(
                        {
                            "intent_ref": payload["intent_ref"],
                            "intent": deepcopy(intent),
                            "conclusion": conclusion,
                            "source": source.strip(),
                            "verified_by": "user",
                            "at": time.time(),
                            "observation_count": len(job["observations"]),
                            "run_id": state.get("runtime", {}).get("id"),
                        }
                    )
                    if job["status"] != "cancelled":
                        job.update(status="needs_recheck", reason="action_result_unknown")
                    # This checkpoint retains both the intent and its resolution.
                    # A separate, input-checked recheck may clear the active intent.
                elif operation == "settle-cancelled":
                    if job["status"] != "cancelled":
                        raise PortalDataError("not_cancelled", "只有已取消岗位可以结算。", 409)
                    if payload.get("acknowledge") is not True:
                        raise PortalDataError(
                            "settlement_required", "请明确确认结算已取消岗位。", 409
                        )
                    if job["page_open"]:
                        raise PortalDataError("pages_retained", "请先关闭并释放旧页面。", 409)
                    intent = job["intent"]
                    intent_ref = (intent.get("attempt_id") or digest(intent)) if intent else None
                    if not intent or payload.get("intent_ref") != intent_ref:
                        raise PortalDataError(
                            "action_resolution_required", "请核验当前待结算动作。", 409
                        )
                    resolutions = [
                        r
                        for r in job.get("action_resolutions", [])
                        if r["intent_ref"] == intent_ref
                    ]
                    if not resolutions or resolutions[-1]["conclusion"] not in {
                        "current_matches",
                        "not_applied",
                    }:
                        raise PortalDataError(
                            "action_unresolved", "旧动作仍未知，请先保存具体核验结论和来源。", 409
                        )
                    job["observations"].append(
                        {
                            "action": "cancelled_intent_settled",
                            "intent": deepcopy(intent),
                            "intent_ref": intent_ref,
                            "conclusion": resolutions[-1]["conclusion"],
                            "source": resolutions[-1]["source"],
                            "at": time.time(),
                            "run_id": state.get("runtime", {}).get("id"),
                        }
                    )
                    # Settlement never queues browser work or reclaims a human page.
                    job["intent"] = None
                elif operation == "retry-sync":
                    if payload.get("revision"):
                        if payload.get("acknowledge") is not True:
                            raise PortalDataError(
                                "review_sync", "请先核验原记录与待同步结果。", 409
                            )
                        app = self.store.applications.get_application(job["application_id"])
                        if (
                            app["revision"] != payload["revision"]
                            or _job_identity(
                                app["url"], allow_generic=job["platform"] == "generic"
                            )[1]
                            != job["job_url"]
                        ):
                            raise PortalDataError("conflict", "原记录已再次变更。", 409)
                        if job.get("pending_status") and app["status"] not in {
                            "drafting",
                            "applied",
                            "confirmation_received",
                        }:
                            raise PortalDataError(
                                "status_advanced", "原记录已进入后续阶段，请在原记录中处理。", 409
                            )
                        job["revision"] = app["revision"]
                        if (
                            job.get("pending_status") == "applied"
                            and app["status"] == "confirmation_received"
                        ):
                            job["pending_status"] = ""
                    if job["pending_sync"]:
                        # Preserve the expected revision. An external change still conflicts.
                        self.store.sync(job, job["pending_sync"])
                elif operation == "submitted":
                    if not job["handed_off"] or payload.get("acknowledge") is not True:
                        raise PortalDataError(
                            "human_confirmation_required", "请先人工提交并明确确认。", 409
                        )
                    if not job.get("manual_submission"):
                        job["manual_submission"] = {
                            "source": "user_confirmation",
                            "at": time.time(),
                        }
                        job["pending_status"] = "applied"
                        self.store.sync(job, "已由用户确认人工提交：等待接收证据。")
                elif operation == "receipt":
                    locator = payload.get("locator")
                    if (
                        not job.get("manual_submission")
                        or not isinstance(locator, str)
                        or not 1 <= len(locator.strip()) <= 1000
                    ):
                        raise PortalDataError(
                            "receipt_required", "请先确认人工提交，再填写已核验回执的来源。", 409
                        )
                    job["receipt"] = {
                        "source": "user_verified_receipt",
                        "locator": locator,
                        "at": time.time(),
                    }
                    job["pending_status"] = "confirmation_received"
                    self.store.sync(job, "用户已核验接收证据：等待后续进展。")
                elif operation == "cancel-job":
                    revoke_assistance(job, reason="cancelled")
                    cancel_continuation(job, "cancelled")
                    job["status"] = "cancelled"
                elif operation == "review":
                    partial = (
                        self.live
                        and job["status"] in {"needs_input", "needs_recheck"}
                        and payload.get("acknowledge") is True
                        and self._page_current(state, job)
                    )
                    if job["status"] != "ready_for_review" and not partial:
                        raise PortalDataError("not_ready", "请先完成填表与核验。", 409)
                    self._check_review(job, require_ready_form=not partial)
                    job["manual_intervention"] = partial
                    job["handed_off"] = True
                    automatic = (
                        payload.get("actor") == "system" and payload.get("human_reviewed") is False
                    )
                    job["handoff"] = {
                        "status": "pending",
                        "at": time.time(),
                        "run_id": state.get("runtime", {}).get("id"),
                        "source": "automatic_submit_wait"
                        if automatic
                        else "user_requested_handoff",
                        "actor": "system" if automatic else "user",
                        "human_reviewed": False,
                    }
                    state["commands"].append(
                        {
                            "action": "review",
                            "id": job["application_id"],
                            **({"actor": "system", "human_reviewed": False} if automatic else {}),
                        }
                    )
                elif operation == "release":
                    if not job.get("handed_off") and job["status"] != "cancelled":
                        raise PortalDataError("page_in_use", "请先交接或取消该岗位。", 409)
                    state["commands"].append({"action": "release", "id": job["application_id"]})
                else:
                    if job["status"] == "cancelled":
                        raise PortalDataError("cancelled_job", "取消后请创建新批次。", 409)
                    if job.get("manual_submission"):
                        raise PortalDataError(
                            "already_submitted", "已确认人工提交，不能重新填表。", 409
                        )
                    if job["intent"]:
                        intent_ref = job["intent"].get("attempt_id") or digest(job["intent"])
                        resolutions = [
                            r
                            for r in job.get("action_resolutions", [])
                            if r["intent_ref"] == intent_ref
                        ]
                        if not resolutions or resolutions[-1]["conclusion"] == "manual_stop":
                            raise PortalDataError(
                                "action_unresolved",
                                "旧动作仍未核验。请先保存具体处理结论和来源。",
                                409,
                            )
                    if job["handed_off"] and (
                        payload.get("reclaim") is not True
                        or not isinstance(payload.get("handoff_source"), str)
                        or not 1 <= len(payload["handoff_source"].strip()) <= 1000
                    ):
                        raise PortalDataError(
                            "handoff_review_required",
                            "请明确核验人工交接状态，再允许自动层接管。",
                            409,
                        )
                    if payload.get("acknowledge") is not True:
                        raise PortalDataError("recheck_required", "请先核实页面、笔记和附件。", 409)
                    fixed_qualification = False
                    if not admission:
                        fixed_qualification = self.store.check_single(job, state) is True
                    app = self._recheck_inputs(state, job, admission)
                    if self.live and not admission and not fixed_qualification:
                        self.store.check_language_requirement(app, country=job["country"])
                    corrections = job.get("email_corrections", [])
                    correction = corrections[-1] if corrections else None
                    if correction:
                        queued = any(
                            event.get("action") == "email_correction_queued"
                            and event.get("correction_id") == correction["id"]
                            for event in job["observations"]
                        )
                        target = self._email_correction_target(
                            state,
                            job,
                            queued_field=correction["binding"]["field_id"] if queued else None,
                        )
                        if target != correction["binding"]:
                            raise PortalDataError(
                                "email_correction_target_changed",
                                "邮箱更正绑定的运行、原页或字段已改变，请重新核验。",
                                409,
                            )
                    if correction and not queued:
                        state["commands"].append(
                            {
                                "action": "one-use",
                                "id": job["application_id"],
                                "fact": "email",
                                "value": correction["value"],
                            }
                        )
                        job["observations"].append(
                            {
                                "action": "email_correction_queued",
                                "correction_id": correction["id"],
                                "binding": deepcopy(correction["binding"]),
                                "at": time.time(),
                            }
                        )
                    job.setdefault("observations", []).append(
                        {
                            "action": "inputs_rechecked",
                            "at": time.time(),
                            "run_id": state.get("runtime", {}).get("id"),
                            "revision": app["revision"],
                            "file_sha256": job["file_sha256"],
                            "handoff_source": payload.get("handoff_source", ""),
                            "source": "user_confirmed_recheck",
                        }
                    )
                    job.update(
                        revision=app["revision"],
                        status="queued",
                        reason="",
                        intent=None,
                        handed_off=False,
                    )
                    state["commands"].append({"action": "recheck", "id": job["application_id"]})
            else:
                raise PortalDataError("unknown_operation", "不支持此操作。", 404)
            for job in state["jobs"]:
                if job["status"] == "cancelled" and not job["page_open"] and not job["intent"]:
                    try:
                        release_execution(
                            self.store.applications,
                            job["application_id"],
                            automated_owner(
                                self.store.root, state["batch_id"], job["application_id"]
                            ),
                            "automated",
                        )
                    except PortalDataError as error:
                        if error.code != "execution_missing":
                            raise
            self.store.save(state)
            if self.write_admitted and operation in {"resume", "pause", "cancel"}:
                self.write_admitted(operation, state)
            if operation == "prepare":
                self._settle_pending_prepare(state)
            if operation in {"resume", "reopen-current"}:
                self.store.stop_path.unlink(missing_ok=True)
                self.store.storage_error = ""
        if (
            operation in {"resume", "reopen-current"}
            and state["control"] == "running"
            or operation == "prepare"
            and any(job.get("workflow") != "single" for job in state["jobs"])
        ):
            self.spawn()
        return self.snapshot()

    def _recheck_inputs(self, state: dict, job: dict, admission: dict | None) -> dict:
        app = self.store.applications.get_application(job["application_id"])
        self.store.check_generic_enabled(job, state)
        task = (
            admission["target"]
            if admission
            else validate_application_target(
                self.store.applications,
                job["application_id"],
                app["revision"],
                allow_generic=self.generic,
            )
        )
        if task["job_url"] != job["job_url"]:
            raise PortalDataError("job_changed", "岗位已变更，请准备新批次。", 409)
        if not admission and (
            hashlib.sha256(Path(job["file_path"]).read_bytes()).hexdigest() != job["file_sha256"]
        ):
            raise PortalDataError("file_changed", "简历已变更，请重新选择并准备批次。", 409)
        return app

    @staticmethod
    def _job(state: dict, identifier: object) -> dict:
        for job in state["jobs"]:
            if job["application_id"] == identifier:
                return job
        raise PortalDataError("job_not_found", "批次中不存在此岗位。", 404)

    def _settle_pending_prepare(self, state: dict) -> None:
        """Recover an unpublished reservation only on an explicit prepare request.

        Browser work cannot start before run.json publishes the batch. Keep the
        intent until its ownership and archival writes are known to have finished.
        """
        path = self.store.root / "prepare-pending.json"
        if path.is_symlink():
            raise PortalDataError("prepare_recovery_invalid", "准备恢复记录无效。", 409)
        if not path.exists():
            return
        try:
            pending = helper.read_json_object(path, "pending worker preparation")
        except helper.StoreError as error:
            raise PortalDataError("prepare_recovery_invalid", "准备恢复记录无效。", 409) from error
        batch = pending.get("batch_id")
        identifiers = pending.get("application_ids")
        if (
            pending.get("schemaVersion") != 1
            or pending.get("applications_root") != str(self.store.applications.root)
            or not isinstance(batch, str)
            or re.fullmatch(r"[a-f0-9]{32}", batch) is None
            or not isinstance(identifiers, list)
            or not 1 <= len(identifiers) <= 20
            or any(not isinstance(identifier, str) or not identifier for identifier in identifiers)
        ):
            raise PortalDataError("prepare_recovery_invalid", "准备恢复记录无效。", 409)
        published = (
            batch == state["batch_id"]
            and set(identifiers).issubset({job["application_id"] for job in state["jobs"]})
        ) or any(
            old.get("batch_id") == batch
            and set(identifiers).issubset({job["application_id"] for job in old["jobs"]})
            for old in state.get("batch_history", [])
        )
        recovery = []
        if not published:
            for identifier in identifiers:
                outcome = "released"
                try:
                    release_execution(
                        self.store.applications,
                        identifier,
                        automated_owner(self.store.root, batch, identifier),
                        "automated",
                    )
                except PortalDataError as error:
                    # This batch was never published, so no browser could act.
                    # A missing or different claim belongs to no pending action
                    # of ours and must never be overwritten during recovery.
                    if error.code not in {"execution_missing", "execution_conflict"}:
                        raise
                    outcome = error.code
                recovery.append({"application_id": identifier, "outcome": outcome})
        directory = self.store.root / "prepare-history"
        if directory.is_symlink():
            raise PortalDataError("prepare_recovery_invalid", "准备恢复归档目录无效。", 409)
        directory.mkdir(mode=0o700, exist_ok=True)
        preparation_id = pending.get("preparation_id", batch)
        if (
            not isinstance(preparation_id, str)
            or re.fullmatch(r"[a-f0-9]{32}", preparation_id) is None
        ):
            raise PortalDataError("prepare_recovery_invalid", "准备恢复标识无效。", 409)
        archive = directory / f"{preparation_id}.json"
        if archive.is_symlink():
            raise PortalDataError("prepare_recovery_invalid", "准备恢复归档无效。", 409)
        if not archive.exists():
            helper.atomic_write_json(
                archive,
                {
                    **pending,
                    "resolution": "published" if published else "unpublished_released",
                    "recovery": recovery,
                },
            )
        path.unlink()

    @staticmethod
    def _check_legacy_prepare(state):
        if state["jobs"] and any(job["status"] != "cancelled" for job in state["jobs"]):
            raise PortalDataError("batch_exists", "请先核验现有批次。页面会保留。", 409)
        if any(job["page_open"] for job in state["jobs"]):
            raise PortalDataError("pages_retained", "请保留旧批次页面并核验。", 409)
        if any(job["intent"] for job in state["jobs"]):
            raise PortalDataError("action_unresolved", "请先核验旧批次的未完成动作。", 409)
        if any(assistance_stop_pending(job) for job in state["jobs"]):
            raise PortalDataError(
                "assistance_stop_pending", "原接管尚未确认停止，请保留原占用。", 409
            )

    def check_new_current_job(self, state=None):
        """Shared admission check for one new job, preserving explicitly skipped jobs."""
        state = self.store.load() if state is None else state
        if "current_job_id" not in state:
            self._check_legacy_prepare(state)
            return
        if state["control"] != "paused" or state["current_job_id"] is not None:
            raise PortalDataError("current_job_exists", "当前岗位尚未完成或跳过。", 409)
        if any(job.get("workflow") != "single" for job in state["jobs"]):
            raise PortalDataError("batch_exists", "旧批次须保留原控制方式。", 409)
        if any(assistance_stop_pending(job) for job in state["jobs"]):
            raise PortalDataError(
                "assistance_stop_pending", "原接管尚未确认停止，请保留原占用。", 409
            )
        if state.get("single_context") != self.store.single_context():
            raise PortalDataError("single_context_changed", "单岗位资料目录绑定已改变。", 409)

    def _prepare(self, state: dict, payload: dict, *, admission=None) -> None:
        if admission:
            from .application_single_binding import valid_send_approval

            task, target, country = admission["task"], admission["target"], admission["country"]
            binding = {
                "schemaVersion": 1,
                "task_id": task["id"],
                **{
                    key: task[key]
                    for key in (
                        "job_binding",
                        "inputs",
                        "analysis_id",
                        "resume_id",
                        "resume_sha256",
                    )
                },
                "job_url": target["job_url"],
                "country": country,
                "send_confirmed": True,
                "hard_condition_resolutions": task.get("hard_condition_resolutions", []),
            }
            approval = task.get("send_approval") or {}
            items = payload.get("jobs")
            valid = (
                payload.get("workflow") == "single"
                and payload.get("send_confirmed") is True
                and task.get("worker_ref") is None
                and country in COUNTRIES
                and valid_send_approval(task, self.store.single_flow_root, require_active=True)
                and approval.get("country") == country
                and approval.get("job_url") == target["job_url"]
                and all(
                    approval.get(key) == task[key]
                    for key in ("resume_id", "resume_sha256", "analysis_id", "inputs")
                )
                and isinstance(items, list)
                and len(items) == 1
                and isinstance(items[0], dict)
            )
            if valid:
                item = items[0]
                valid = (
                    item.get("application_id") == target["application_id"]
                    and item.get("revision") == target["revision"]
                    and item.get("country") == country
                    and item.get("single_binding") == binding
                    and isinstance(item.get("filename"), str)
                    and re.fullmatch(r"[^/\\\x00-\x1f]{1,160}\.pdf", item["filename"], re.I)
                )
                try:
                    raw = base64.b64decode(item.get("file_base64", ""), validate=True)
                    valid = (
                        valid
                        and 1 <= len(raw) <= 700_000
                        and raw.startswith(b"%PDF-")
                        and hashlib.sha256(raw).hexdigest() == task["resume_sha256"]
                    )
                except (ValueError, TypeError):
                    valid = False
            if not valid:
                raise PortalDataError(
                    "installed_write_preflight_required", "请保持暂停并核验当前单岗位材料。", 409
                )
        self._settle_pending_prepare(state)
        allow_generic = self.generic and state.get("generic_enabled") is True
        if not self.fixture_origin and not self.live:
            raise PortalDataError("live_disabled", "当前预览只处理隔离合成岗位。", 409)
        append_current = payload.get("workflow") == "single" and "current_job_id" in state
        if append_current:
            self.check_new_current_job(state)
        else:
            self._check_legacy_prepare(state)
        items = payload.get("jobs")
        if self.live and isinstance(items, list) and len(items) > 3:
            raise PortalDataError("pilot_limit", "真实小样本每批最多 3 个岗位。")
        if not isinstance(items, list) or not 1 <= len(items) <= 20:
            raise PortalDataError("invalid_jobs", "请选择 1–20 个岗位。")
        workflow = payload.get("workflow", "batch")
        if not isinstance(workflow, str) or workflow not in {"batch", "precision", "single"}:
            raise PortalDataError("invalid_workflow", "请选择批量或人工精准准备。")
        if workflow == "precision" and (
            len(items) != 1 or payload.get("precision_reviewed") is not True
        ):
            raise PortalDataError(
                "precision_review_required",
                "精准投递须单独准备，并确认 JD、证据和定制简历已复核。",
                409,
            )
        if workflow == "single" and (len(items) != 1 or payload.get("send_confirmed") is not True):
            raise PortalDataError(
                "single_confirmation_required", "单岗位填写须确认一个岗位及材料发送。", 409
            )
        state["single_context"] = self.store.single_context() if workflow == "single" else None
        jobs = []
        for item in items:
            if not isinstance(item, dict) or item.get("country") not in COUNTRIES:
                raise PortalDataError("country_required", "请逐岗位确认申请国家。")
            task = (
                admission["target"]
                if admission
                else validate_application_target(
                    self.store.applications,
                    item.get("application_id"),
                    item.get("revision"),
                    allow_generic=allow_generic,
                )
            )
            app = self.store.applications.get_application(task["application_id"])
            screening = (
                screen_applications(
                    [
                        app
                        | {
                            "country": item["country"],
                            "application_id": task["application_id"],
                            "workflow": workflow,
                            "single_binding": item.get("single_binding"),
                        }
                    ],
                    language_levels=self.store.language_levels,
                    allow_generic=allow_generic,
                )[0]["screening"]
                if self.live and not admission and workflow != "single"
                else {}
            )
            if screening.get("language_needs_input"):
                raise PortalDataError(
                    "language_information_required",
                    "适用语言信息有冲突或缺少明确等级，请核对。",
                    409,
                )
            if screening.get("language_mismatch"):
                raise PortalDataError(
                    "job_requirement_mismatch",
                    "明确语言要求与已确认水平不匹配，请选择其他岗位。",
                    409,
                )
            if self.live and workflow != "single":
                route = screening["application_route"]
                expected = "manual" if workflow == "precision" else "batch"
                if route != expected:
                    raise PortalDataError(
                        "application_route_required",
                        "请先保存岗位分流。批量入口只接收批量岗位；高价值岗位请单独精准准备。",
                        409,
                    )
            if any(j["job_url"] == task["job_url"] for j in jobs):
                raise PortalDataError("duplicate_job", "同一岗位只能选择一次。", 409)
            filename = item.get("filename", "")
            if not isinstance(filename, str) or not re.fullmatch(
                r"[^/\\\x00-\x1f]{1,160}\.pdf", filename, re.I
            ):
                raise PortalDataError("resume_required", "请逐岗位选择 PDF 简历。")
            try:
                raw = base64.b64decode(item["file_base64"], validate=True)
            except (ValueError, KeyError, TypeError) as exc:
                raise PortalDataError("invalid_resume", "无法读取简历。") from exc
            if not 1 <= len(raw) <= 700_000 or not raw.startswith(b"%PDF-"):
                raise PortalDataError("invalid_resume", "请选择不超过 700 KB 的 PDF 简历。")
            jobs.append(
                {
                    "application_id": task["application_id"],
                    "revision": task["revision"],
                    "job_url": task["job_url"],
                    "platform": task["platform"],
                    "company": app["company"],
                    "role_title": app["role_title"],
                    "country": item["country"],
                    "workflow": workflow,
                    "filename": filename,
                    "file_sha256": hashlib.sha256(raw).hexdigest(),
                    "file_path": "",
                    "status": "queued",
                    "reason": "",
                    "measurement_id": item.get("measurement_id"),
                    "questions": [],
                    "answer_refs": [],
                    "intent": None,
                    "pending_sync": "",
                    "pending_status": "",
                    "sync_error": "",
                    "manual_submission": None,
                    "receipt": None,
                    "handed_off": False,
                    "page_open": False,
                    "observations": [],
                }
            )
            if workflow == "single":
                jobs[-1].update(
                    single_binding=deepcopy(item.get("single_binding")), send_confirmed=True
                )
                authorization = (
                    (admission["task"].get("send_approval") or {}).get("authorization")
                    if admission
                    else None
                )
                if authorization and authorization.get("precision_preparation") is True:
                    jobs[-1]["precision_preparation"] = {
                        "status": "preparing",
                        "task_id": admission["task"]["id"],
                        "authorization_id": authorization["authorization_id"],
                    }
                if not admission:
                    fixed_qualification = (
                        self.store.check_single(jobs[-1], state, allow_unbound=True) is True
                    )
                    if self.live and not fixed_qualification:
                        self.store.check_language_requirement(app, country=item["country"])
        if append_current and any(
            job["application_id"] in {old["application_id"] for old in state["jobs"]}
            for job in jobs
        ):
            raise PortalDataError("job_retained", "已有岗位须返回原任务。", 409)
        batch = state["batch_id"] if append_current else uuid4().hex
        # Explicit current-job selection retains the old claim and original page.
        for previous in [] if append_current else state["jobs"]:
            try:
                release_execution(
                    self.store.applications,
                    previous["application_id"],
                    automated_owner(self.store.root, state["batch_id"], previous["application_id"]),
                    "automated",
                )
            except PortalDataError as error:
                if error.code != "execution_missing":
                    raise
        directory = self.store.root / "attachments" / batch
        directory.mkdir(parents=True, mode=0o700, exist_ok=append_current)
        for job, item in zip(jobs, items, strict=True):
            own = directory / job["application_id"]
            own.mkdir(mode=0o700)
            path = own / job["filename"]
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(base64.b64decode(item["file_base64"], validate=True))
            job["file_path"] = str(path)
        helper.atomic_write_json(
            self.store.root / "prepare-pending.json",
            {
                "schemaVersion": 1,
                "applications_root": str(self.store.applications.root),
                "batch_id": batch,
                "preparation_id": uuid4().hex,
                "application_ids": [job["application_id"] for job in jobs],
            },
        )
        reserved = []
        try:
            for job in jobs:
                reserve_execution(
                    self.store.applications,
                    job["application_id"],
                    automated_owner(self.store.root, batch, job["application_id"]),
                    "automated",
                )
                reserved.append(job)
        except Exception:
            for job in reserved:
                release_execution(
                    self.store.applications,
                    job["application_id"],
                    automated_owner(self.store.root, batch, job["application_id"]),
                    "automated",
                )
            raise
        if state["jobs"] and not append_current:
            state.setdefault("batch_history", []).append(
                {"batch_id": state["batch_id"], "jobs": deepcopy(state["jobs"]), "at": time.time()}
            )
        state.update(
            batch_id=batch,
            jobs=[*state["jobs"], *jobs] if append_current else jobs,
            control="paused",
            controller="",
            commands=[],
            heartbeat_at=0,
            worker_error="",
        )
        if workflow == "single":
            state["current_job_id"] = jobs[0]["application_id"]

    def _resolve_form_differences(self, state: dict, payload: dict) -> None:
        job = self._job(state, payload.get("application_id"))
        application = self.store.applications.get_application(job["application_id"])
        form = job.get("form_state")
        if (
            state.get("current_job_id") != job["application_id"]
            or state["control"] == "cancelled"
            or job["status"] == "cancelled"
            or job.get("manual_submission")
            or application["status"] != "drafting"
            or job.get("handed_off")
            or job.get("intent")
            or not job["page_open"]
            or not self._page_current(state, job)
            or not isinstance(form, dict)
            or form.get("schema") != "form-state/v1"
            or form.get("parser", {}).get("status") != "stable"
            or not isinstance(form.get("binding"), dict)
            or form["binding"].get("run_id") != state["runtime"]["id"]
            or form["binding"].get("page_id") != job["page_observation"]["page_id"]
            or not isinstance(form["binding"].get("step"), str)
            or not form["binding"]["step"]
            or payload.get("binding") != form["binding"]
            or type(payload.get("revision")) is not int
            or payload["revision"] != form.get("revision")
            or not isinstance(form.get("snapshot_sha256"), str)
            or re.fullmatch(r"[a-f0-9]{64}", form["snapshot_sha256"]) is None
        ):
            raise PortalDataError(
                "form_differences_changed", "原页或表单已变化，请读取当前差异后集中选择。", 409
            )
        self.store.check_single(job, state)
        differences = form.get("differences")
        choices = payload.get("choices")
        if (
            not isinstance(differences, list)
            or not isinstance(choices, list)
            or not choices
            or len(choices) > len(differences)
        ):
            raise PortalDataError("invalid_form_choices", "请集中选择当前表单差异。")
        selected = {}
        for choice in choices:
            if not isinstance(choice, dict):
                raise PortalDataError("invalid_form_choices", "差异选择格式无效。")
            identifier, action = choice.get("difference_id"), choice.get("action")
            rows = [row for row in differences if row.get("id") == identifier]
            if (
                not isinstance(identifier, str)
                or identifier in selected
                or len(rows) != 1
                or not isinstance(action, str)
                or action not in {"keep", "use", "edit"}
                or set(choice)
                != {"difference_id", "action"} | ({"value"} if action == "edit" else set())
                or action == "edit"
                and (not isinstance(choice.get("value"), str) or len(choice["value"]) > 20000)
            ):
                raise PortalDataError("invalid_form_choices", "差异选择无效或已过期。")
            row = rows[0]
            selected[identifier] = {
                "id": identifier,
                "difference_id": identifier,
                "action": action,
                "value": deepcopy(
                    row["current_value"]
                    if action == "keep"
                    else row["proposed_value"]
                    if action == "use"
                    else choice["value"]
                ),
                "field_id": row["field_id"],
                "current_value": deepcopy(row["current_value"]),
                "proposed_value": deepcopy(row["proposed_value"]),
                "source": deepcopy(row.get("source")),
                "snapshot_sha256": form["snapshot_sha256"],
                "binding": deepcopy(form["binding"]),
                "revision": form["revision"],
                "at": time.time(),
            }
        form.setdefault("choice_history", []).extend(deepcopy(list(selected.values())))
        form.setdefault("choices", {}).update(selected)
        # Saving one batch records local decisions only. Continue re-reads the page.

    @staticmethod
    def _form_choice_current(form: dict, row: dict) -> bool:
        choice = form.get("choices", {}).get(row.get("id"))
        return bool(
            isinstance(choice, dict)
            and not choice.get("expired")
            and choice.get("binding") == form.get("binding")
            and choice.get("field_id") == row.get("field_id")
            and choice.get("source") == row.get("source")
            and choice.get("proposed_value") == row.get("proposed_value")
            and choice.get("action") in {"keep", "use", "edit"}
            and row.get("current_value")
            == (choice.get("current_value") if choice["action"] == "keep" else choice.get("value"))
        )

    def _check_review(self, job: dict, *, require_ready_form=True) -> None:
        if job.get("workflow") == "single" and (
            job.get("cover_letter_delivery") is not None
            or any(material.get("letter_content") for material in job.get("materials", []))
        ):
            from .application_materials import material_consistency_status

            material_consistency_status(self.store.material_inputs(job))
        delivery = job.get("cover_letter_delivery") or {}
        if delivery.get("status") == "needs_recheck" or (
            delivery.get("requirement") == "required" and delivery.get("status") != "ready"
        ):
            raise PortalDataError(
                "cover_letter_review_pending", "必需求职信或未知交付结果尚未核验。", 409
            )
        form = job.get("form_state")
        completion = assistance_completion(job)
        if completion is not None and (
            job.get("intent")
            or any(
                not field["valid"] or field["required"] and field["value_empty"]
                for field in completion["page_verification"]["fields"]
            )
        ):
            raise PortalDataError(
                "form_review_pending", "接管完成的核对结果不完整，请保留原页核对。", 409
            )
        # Fields Codex completed are checked by its verified outcome, not reparsed.
        if (
            require_ready_form
            and completion is None
            and form is not None
            and (
                not isinstance(form, dict)
                or form.get("schema") != "form-state/v1"
                or form.get("parser", {}).get("status") != "stable"
                or form.get("snapshot", {}).get("validation_errors") != []
                or form.get("intervention_pending")
                or any(
                    (field.get("required") or field.get("value") or field.get("filename"))
                    and not field.get("valid")
                    for field in form.get("snapshot", {}).get("fields", [])
                )
                or job.get("intent")
                or any(
                    row.get("important") and not self._form_choice_current(form, row)
                    for row in form.get("differences", [])
                )
            )
        ):
            raise PortalDataError(
                "form_review_pending", "解析、页面校验或重要差异尚未完成，请保留原页核对。", 409
            )
        fixed_qualification = self.store.check_single(job) is True
        self.store.check_generic_enabled(job)
        validate_application_target(
            self.store.applications,
            job["application_id"],
            job["revision"],
            allow_generic=self.generic,
        )
        if self.live and not fixed_qualification:
            self.store.check_language_requirement(
                self.store.applications.get_application(job["application_id"]),
                country=job["country"],
            )
        if hashlib.sha256(Path(job["file_path"]).read_bytes()).hexdigest() != job["file_sha256"]:
            raise PortalDataError("file_changed", "简历已变更，请重新核验。", 409)
        for material in job.get("materials", []):
            if material.get("status") == "ready":
                self.store.verify_material(material, job)
                if material.get("letter_content"):
                    current_field = next(
                        (
                            field
                            for field in (form or {}).get("snapshot", {}).get("fields", [])
                            if field["id"] == material.get("field_id")
                            and field.get("draft_path", "") == material.get("draft_path", "")
                        ),
                        None,
                    )
                    if current_field is not None:
                        self.store.field_material(current_field, job)
        for ref in job["answer_refs"]:
            if ref["key"] == "one-use" or ref.get("source") == "system_material":
                continue
            record = self.store.answers_for(job).get_answer(ref["key"])
            if record is None or digest(record) != ref["revision"]:
                raise PortalDataError("answer_changed", "答案已变更，请重新核验。", 409)

    def _recheck_cover_letter_file(self, state, payload):
        """Adopt an exact completed file receipt without another build."""
        from .application_cover_letter import reconcile_cover_letter_pdf
        from .application_materials import check_cover_letter_file, read_cover_letter_template

        if (
            set(payload)
            != {"application_id", "material_id", "expected_material_revision", "request_id"}
            or not isinstance(payload.get("request_id"), str)
            or re.fullmatch(r"[a-f0-9]{32}", payload["request_id"]) is None
        ):
            raise PortalDataError("invalid_material_recheck", "请提供原文件尝试与准确版本。", 400)
        job = self._job(state, payload["application_id"])
        previous = next(
            (
                row
                for row in job.get("material_file_rechecks", [])
                if row["request_id"] == payload["request_id"]
            ),
            None,
        )
        if previous:
            if previous["payload_revision"] != digest(payload):
                raise PortalDataError("material_recheck_changed", "核验请求已绑定其他尝试。", 409)
            return
        if (
            state["control"] != "paused"
            or state.get("current_job_id", job["application_id"]) != job["application_id"]
            or job.get("intent")
            or job.get("handed_off")
            or job.get("manual_submission")
            or job.get("status") == "cancelled"
            or self.store.stop_reason()
            or manual_submission_unresolved(job)
            or material_edit_pending(job)
            or any(unresolved_write_failure(row, job, state) for row in job.get("observations", []))
        ):
            raise PortalDataError(
                "material_recheck_pause_required", "请暂停同一岗位并先核对未知网页动作。", 409
            )
        self.store.check_single(job, state)
        found = [row for row in job.get("materials", []) if row.get("id") == payload["material_id"]]
        if (
            len(found) != 1
            or digest(found[0]) != payload["expected_material_revision"]
            or found[0].get("kind") != "cover_letter"
            or found[0].get("status") != "needs_recheck"
            or not found[0].get("letter_content")
            or re.fullmatch(r"[a-f0-9]{32}", str(found[0].get("id", ""))) is None
        ):
            raise PortalDataError("material_recheck_changed", "原求职信文件尝试已变化。", 409)
        original = found[0]
        fixed = self.store.material_inputs(job)
        branch = fixed.get("cover_letter") or {}
        if (
            branch.get("status") != "ready"
            or branch.get("result", {}).get("content_revision") != original["content_revision"]
        ):
            raise PortalDataError("material_recheck_changed", "原构建正文不再是本岗采用版本。", 409)
        directory = self.store.root / "materials" / original["id"]
        template = read_cover_letter_template(self.store, fixed["application"])
        inspector = getattr(self.store, "cover_letter_pdf_inspector", None)
        maximum = check_cover_letter_file(original)
        for field in (job.get("form_state") or {}).get("snapshot", {}).get("fields", []):
            if (
                field.get("id") == original["field_id"]
                and field.get("draft_path", "") == original.get("draft_path", "")
                and field.get("type") == "file"
            ):
                maximum = min(maximum, check_cover_letter_file(field))
        built = reconcile_cover_letter_pdf(
            directory,
            original["letter_content"],
            template,
            client=getattr(self.store, "cover_letter_client", None),
            max_bytes=maximum,
            pdf_inspector=inspector,
        )
        candidate = deepcopy(original) | built | {"status": "ready"}
        candidate.pop("error_code", None)
        self.store.verify_material(candidate, job)
        self.store.verify_material_source(candidate)
        job["materials"] = [candidate if row is original else row for row in job["materials"]]
        job.setdefault("material_file_rechecks", []).append(
            {
                "request_id": payload["request_id"],
                "payload_revision": digest(payload),
                "previous_material": deepcopy(original),
                "material_id": candidate["id"],
                "content_revision": candidate["content_revision"],
                "sha256": candidate["sha256"],
            }
        )
        job["cover_letter_delivery"] = {
            **job.get("cover_letter_delivery", {}),
            "status": "queued",
            "reason": "file_result_reconciled",
        }
        job["reason"] = "cover_letter_file_reconciled"

    def _retry_cover_letter_file(self, state, payload):
        """Explicitly retire a known failed file attempt; Continue builds only that file."""
        from .application_materials import KNOWN_COVER_LETTER_PDF_FAILURES

        if (
            set(payload)
            != {"application_id", "material_id", "expected_material_revision", "request_id"}
            or not isinstance(payload.get("request_id"), str)
            or re.fullmatch(r"[a-f0-9]{32}", payload["request_id"]) is None
        ):
            raise PortalDataError("invalid_material_retry", "请提供原文件尝试与准确版本。", 400)
        job = self._job(state, payload["application_id"])
        previous = next(
            (
                r
                for r in job.get("material_retry_requests", [])
                if r["request_id"] == payload["request_id"]
            ),
            None,
        )
        if previous:
            if previous["payload_revision"] != digest(payload):
                raise PortalDataError("material_retry_changed", "重试请求已绑定其他原尝试。", 409)
            return
        if (
            state["control"] != "paused"
            or state.get("current_job_id", job["application_id"]) != job["application_id"]
            or job.get("intent")
            or job.get("handed_off")
            or job.get("manual_submission")
            or job.get("status") == "cancelled"
            or self.store.stop_reason()
            or manual_submission_unresolved(job)
            or material_edit_pending(job)
            or any(unresolved_write_failure(row, job, state) for row in job.get("observations", []))
        ):
            raise PortalDataError(
                "material_retry_pause_required", "请暂停同一岗位并先核对未知动作。", 409
            )
        self.store.check_single(job, state)
        found = [r for r in job.get("materials", []) if r.get("id") == payload["material_id"]]
        if (
            len(found) != 1
            or digest(found[0]) != payload["expected_material_revision"]
            or found[0].get("kind") != "cover_letter"
            or not found[0].get("letter_content")
            or found[0].get("status") != "failed"
            or found[0].get("error_code") not in KNOWN_COVER_LETTER_PDF_FAILURES
            or found[0].get("error_code") == "cover_letter_file_limit_invalid"
            and found[0].get("file_build_started") is not False
        ):
            raise PortalDataError(
                "material_retry_changed", "只能重建原版本的已知失败 PDF，未知结果须先核对。", 409
            )
        job.setdefault("material_history", []).append(deepcopy(found[0]))
        job["materials"] = [r for r in job["materials"] if r is not found[0]]
        job.setdefault("material_retry_requests", []).append(
            {
                "request_id": payload["request_id"],
                "payload_revision": digest(payload),
                "material_id": payload["material_id"],
                "content_revision": found[0]["content_revision"],
            }
        )
        job["cover_letter_delivery"] = {
            **job.get("cover_letter_delivery", {}),
            "status": "queued",
            "reason": "file_retry_requested",
        }
        job["reason"] = "cover_letter_file_retry_pending"

    def _provide_material(self, state, payload):
        from .application_materials import application_binding, jd_material_requirements
        from .application_resume import ApplicationResumeStore

        job = self._job(state, payload.get("application_id"))
        self.store.check_single(job, state)
        if (
            state["control"] != "paused"
            or job.get("intent")
            or job.get("handed_off")
            or job.get("manual_submission")
            or manual_submission_unresolved(job)
            or material_edit_pending(job)
            or job.get("status") == "cancelled"
            or state.get("current_job_id", job["application_id"]) != job["application_id"]
        ):
            raise PortalDataError(
                "material_target_changed", "请暂停当前岗位并保留原页，再提供附件。", 409
            )
        if "requirement_id" in payload:
            application = self.store.applications.get_application(job["application_id"])
            requirement = next(
                (
                    item
                    for item in jd_material_requirements(application)
                    if item["id"] == payload["requirement_id"]
                ),
                None,
            )
            found = [
                row
                for row in job.get("materials", [])
                if (
                    requirement
                    and "field_id" not in payload
                    and "draft_path" not in payload
                    and row.get("origin") == "jd"
                    and not row.get("field_id")
                    and row.get("requirement_id") == requirement["id"]
                    and row.get("kind") == requirement["kind"] == payload.get("kind")
                    and row.get("jd_source")
                    == {key: requirement[key] for key in ("jd_quote", "jd_span", "jd_sha256")}
                    and row.get("required")
                )
            ]
        else:
            found = [
                row
                for row in job.get("materials", [])
                if payload.get("field_id")
                and row.get("field_id") == payload["field_id"]
                and row.get("draft_path", "") == payload.get("draft_path", "")
                and row["kind"] == payload.get("kind")
                and row.get("required")
            ]
        if len(found) != 1 or found[0].get("status") != "needs_input" or found[0].get("filename"):
            raise PortalDataError(
                "material_target_changed", "只能为当前已观察的缺失必填附件提供真实文件。", 409
            )
        identifier = payload.get("request_id")
        filename = payload.get("filename")
        if (
            not isinstance(identifier, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier) is None
            or not isinstance(filename, str)
            or re.fullmatch(r"[^/\\\x00-\x1f]{1,160}\.pdf", filename, re.I) is None
        ):
            raise PortalDataError("material_file_required", "请提供操作标识和真实 PDF 文件。", 409)
        try:
            raw = base64.b64decode(payload["file_base64"], validate=True)
            ApplicationResumeStore._validate_export_pdf(raw)
            if not 1 <= len(raw) <= 700_000:
                raise ValueError("size")
        except (KeyError, ValueError, TypeError) as error:
            raise PortalDataError(
                "material_file_required", "请选择不超过700 KB的真实 PDF。", 409
            ) from error
        directory = self.store.root / "materials" / uuid4().hex
        directory.mkdir(parents=True)
        path = directory / "provided.pdf"
        path.write_bytes(raw)
        material = found[0]
        material.update(
            id=directory.name,
            attempt_id=identifier,
            status="ready",
            actor="user",
            human_reviewed=False,
            filename=filename,
            file_path=str(path),
            sha256=hashlib.sha256(raw).hexdigest(),
            source_binding={
                "application": application_binding(
                    self.store.applications.get_application(job["application_id"])
                ),
                "sources": [],
                "provided_file": True,
            },
        )
        helper.atomic_write_json(directory / "material.json", material)
        job["reason"] = "material_provided"

    def _answer(self, state: dict, payload: dict) -> None:
        job = self._job(state, payload.get("application_id"))
        question = next(
            (q for q in job["questions"] if q["id"] == payload.get("question_id")), None
        )
        if question is None or job["status"] in {"cancelled", "ready_for_review"}:
            raise PortalDataError("question_changed", "补充项已变更，请刷新。", 409)
        value = payload.get("value")
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 4000:
            raise PortalDataError("answer_required", "请输入补充信息。")
        if question.get("options") and value not in question["options"]:
            raise PortalDataError("option_required", "请选择网站提供的选项。")
        request_group = digest(
            [
                state["batch_id"],
                digest(
                    [
                        fact_for(question["question"]),
                        question_scope(question, job),
                        question["options"],
                    ]
                ),
            ]
        )
        minimum_scope = question_scope(question, job)
        if payload.get("only_this") is True:
            minimum_scope = {**minimum_scope, "application_id": job["application_id"]}
        scope = payload.get("scope", minimum_scope)
        if not isinstance(scope, dict) or not scope_matches(scope, job):
            raise PortalDataError("invalid_scope", "适用范围必须包含当前岗位。")
        scope = {**scope, **minimum_scope}
        if (
            fact_for(question["question"]) in {"sponsorship_now_future", "work_authorization_now"}
            and scope.get("country") != job["country"]
        ):
            raise PortalDataError("country_scope", "资格和担保答案必须限定国家。")
        from .application_information import put_information_answer

        put_information_answer(
            self.store.answers_for(job),
            {
                "question": question["question"],
                "scope": scope,
                "value": value,
                "state": "confirmed",
                "source": "user",
                "sensitivity": question.get("sensitivity", "none"),
            },
            remember_sensitive=True,
            source="application-answer",
        )
        self._refresh_waiting(state)
        state["commands"].append({"action": "answers-changed"})
        self.store.measurements.event(
            "user_operation",
            operation="answer",
            source="synthetic" if state["mode"] == "synthetic" else "ui",
            request_group=request_group,
        )

    def _refresh_waiting(self, state: dict) -> None:
        for job in state["jobs"]:
            if job["handed_off"] or job["status"] != "needs_input":
                continue
            missing = [q for q in job["questions"] if self.store.resolve(q, job) is None]
            job["questions"] = missing
            if not missing:
                job.update(status="queued", reason="")

    def _edit_library(self, state: dict, payload: dict) -> None:
        answers = self.store.answers_for()
        record = answers.get_answer(payload.get("key", ""))
        if record is None or digest(record) != payload.get("revision"):
            raise PortalDataError("answer_conflict", "答案已变更，请重新载入。", 409)
        updated = dict(record)
        if "scope" in payload:
            scope = payload["scope"]
            if (
                not isinstance(scope, dict)
                or set(scope) - {"country", "company", "application_id"}
                or any(not isinstance(v, str) or not v for v in scope.values())
            ):
                raise PortalDataError("invalid_scope", "适用范围无效。")
            if "country" in scope and scope["country"] not in COUNTRIES:
                raise PortalDataError("invalid_country", "请选择有效国家。")
            if (
                fact_for(record["question"]) in {"sponsorship_now_future", "work_authorization_now"}
                and "country" not in scope
            ):
                raise PortalDataError("country_scope", "资格和担保答案必须限定国家。")
            updated["scope"] = scope
        if payload.get("withdraw") is True:
            updated.update(state="missing", value=None)
        else:
            value = payload.get("value")
            if not isinstance(value, str) or not value.strip():
                raise PortalDataError("answer_required", "请输入已确认答案。")
            updated.update(value=value, state="confirmed")
        from .application_information import put_information_answer

        put_information_answer(
            answers,
            updated,
            expected_revision=payload["revision"],
            source="answer-withdrawal" if payload.get("withdraw") is True else "answer-correction",
            remember_sensitive=True,
        )
        self._refresh_waiting(state)
        state["commands"].append({"action": "answers-changed"})
