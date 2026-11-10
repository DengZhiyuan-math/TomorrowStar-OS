"""Fingerprints of fixed loaded Python roles, separate from source-file digests."""

import hashlib
import marshal
import re
import sys
from dataclasses import fields, is_dataclass
from datetime import timezone
from enum import Enum
from importlib import import_module
from types import CodeType, FunctionType, MethodType
from typing import get_args, get_origin

from pydantic import BaseModel
from pydantic_core import PydanticUndefined, SchemaValidator

_PREPARATION_MODULES = (
    "career_portal",
    "application_runtime",
    "career_portal_data",
    "application_flow",
    "application_flow_store",
    "application_input_binding",
    "application_eligibility",
    "application_bound_materials",
    "application_existing_materials",
    "application_material_batch",
    "application_preparation",
    "application_match",
    "application_inference",
    "application_writing",
    "application_proofread",
    "application_resume_versions",
    "application_experience_latex",
    "application_cover_letter",
    "application_resume_author",
    "application_material_consistency",
    "application_matching_pipeline",
    "application_retrieval",
    "application_career_library",
    "application_match_refresh",
    "application_match_recheck",
    "application_draft",
    "resume_presentation",
    "application_resume",
    "application_full_latex",
    "application_group_review",
    "application_prism",
    "application_prism_review",
    "application_pdf",
    "application_pdf_reuse",
    "application_intake",
    "application_gmail",
    "application_job_source",
    "application_recommendations",
    "application_information",
    "career_education",
    "application_explanations",
    "_vendor.job_apply_store",
    # MC-15: page projection and the Flow-path helpers it and the owners above execute.
    "application_flow_view",
    "application_existing_handoff",
    "application_handoff",
    "application_benchmark",
    "application_source_reuse",
    "application_match_scoring",
    "application_second_opinion",
    "job_listing_links",
    "indeed_job_source",
    "employer_page_search",
    "application_job_brief",
    "application_jd_extract",
    "application_input_limits",
    "application_material_sources",
    "application_resume_content",
    "application_resume_render",
    "application_storage",
    "career_experiences",
    "career_experience_import",
    "job_screening",
    "url_safety",
    "validation.hashing",
    # MC-15 review: write-path modules the owners above import lazily, and the startup
    # custody check with its store helpers.
    "application_experience_content",
    "application_content_reconcile",
    "application_material_packet",
    "resume_template",
    "chrome_registration",
    "workspace",
    "validation.store",
)
_RUNTIME_MODULES = {
    "controller": (
        *_PREPARATION_MODULES,
        "application_worker",
        "application_codex_assist",
        # The takeover record, its deadline budget and the original-page scope.
        "application_takeover_record",
        "application_takeover_budget",
        "application_page_scope",
        "application_materials",
        "application_readiness",
        "application_single_binding",
        "application_pipeline",
        "application_material_edit",
        "worker_process_identity",
        "codex_cli",
        "model_call",
        "material_author",
        "application_automation",
        "application_execution",
        "owned_page_observation",
        # MC-15: Worker-domain modules the controller process executes in-process.
        "worker_measurement",
        "cua_driver",
        "owned_browser_cdp",
        "ats_forms",
        "hosted_ats",
        "workable_uploads",
        # MC-15 review: application_worker's fill read-back imports it lazily in-process.
        "application_form_state",
    ),
    "worker": (
        "application_worker_browser",
        "application_codex_assist",
        "application_takeover_record",
        "application_takeover_budget",
        "application_page_scope",
        "application_form_state",
        "application_form_runner",
        "application_bound_materials",
        "application_worker",
        "application_materials",
        "application_cover_letter",
        "application_readiness",
        "application_single_binding",
        "application_experience_latex",
        "career_portal_data",
        "application_automation",
        "application_execution",
        "hosted_ats",
        "ats_forms",
        "cua_driver",
        "ashby_drafts",
        "workable_uploads",
        "owned_page_observation",
        "owned_browser_cdp",
        "worker_measurement",
        "worker_process_identity",
        "_vendor.job_apply_store",
        # MC-15: modules the worker process executes through the role modules above.
        "application_flow",
        "application_flow_store",
        "application_draft",
        "application_full_latex",
        "application_information",
        "application_prism",
        "career_education",
        "application_resume_content",
        "application_resume_render",
        "application_storage",
        "codex_cli",
        "model_call",
        "material_author",
        "job_screening",
        "resume_presentation",
        "url_safety",
        "validation.hashing",
        # MC-20: the rest of the role's static import closure (module-level and function-local),
        # e.g. the delivered-material check's lazy imports. load_worker_modules imports them all
        # before the identity is recorded; controller-side paths are covered, not executed.
        "application_benchmark",
        "application_career_library",
        "application_content_reconcile",
        "application_existing_handoff",
        "application_existing_materials",
        "application_experience_content",
        "application_eligibility",
        "application_explanations",
        "application_group_review",
        "application_handoff",
        "application_inference",
        "application_input_binding",
        "application_input_limits",
        "application_job_brief",
        "application_match",
        "application_match_recheck",
        "application_match_refresh",
        "application_match_scoring",
        "application_second_opinion",
        "application_matching_pipeline",
        "application_material_batch",
        "application_material_consistency",
        "application_material_packet",
        "application_material_sources",
        "application_pdf_reuse",
        "application_preparation",
        "application_prism_review",
        "application_proofread",
        "application_resume",
        "application_resume_author",
        "application_resume_versions",
        "application_retrieval",
        "application_source_reuse",
        "application_writing",
        "career_experience_import",
        "career_experiences",
        "chrome_registration",
        "resume_template",
        "validation.store",
    ),
}
_NAMESPACE = "python-loaded-code/v1"
# Session identifiers and temporary operation scopes are not code/configuration constants.
_RUNTIME_VALUES = {
    "career_evidence_graph.application_flow": {"_PIPELINE_HTTP_ENTRY"},
    "career_evidence_graph.application_resume": {"_DRAFT_VALIDATION"},
    "career_evidence_graph.application_match_refresh": {"_ACTIVE_LOCK", "_ACTIVE_CALLBACKS"},
    "career_evidence_graph.worker_measurement": {"_CLOCK", "_LOG", "_SCOPE"},
    "career_evidence_graph.career_portal": {"_CONFIG", "_STATIC", "_PUBLIC_ROOT"},
    "career_evidence_graph.application_runtime": {"PUBLIC_ROOT"},
    "career_evidence_graph.application_storage": {"PUBLIC_ROOT"},
    "career_evidence_graph.application_single_binding": {"_PREPARATION_TARGET"},
    "career_evidence_graph.application_worker": {"PUBLIC_ROOT"},
    "career_evidence_graph.owned_browser_cdp": {"_ACTIVE_DEADLINE"},
    "career_evidence_graph.career_portal_data": {"_LOCK_STEPS"},
}


def _normalize(value):
    if value is PydanticUndefined:
        return ("pydantic_undefined",)
    if isinstance(value, MethodType):
        if not isinstance(value.__self__, type):
            raise TypeError("An instance-bound callable needs explicit state evidence")
        return ("class_method", _normalize(value.__func__), _normalize(value.__self__))
    origin = get_origin(value)
    if origin is not None:
        name = getattr(origin, "__qualname__", None) or getattr(origin, "_name", None)
        if name is None:
            raise TypeError("Unsupported annotation")
        return ("annotation", origin.__module__, name, _normalize(get_args(value)))
    if isinstance(value, FunctionType):
        return (
            "function",
            _normalize(value.__code__),
            _normalize(value.__defaults__),
            _normalize(value.__kwdefaults__),
            tuple(_normalize(cell.cell_contents) for cell in (value.__closure__ or ())),
        )
    if (
        type(value).__module__ == "pydantic._internal._fields"
        and type(value).__qualname__ == "_general_metadata_cls.<locals>._PydanticGeneralMetadata"
    ):
        return ("pydantic_field_metadata", _normalize(vars(value)))
    if is_dataclass(value) and not isinstance(value, type):
        return (
            "dataclass",
            type(value).__module__,
            type(value).__qualname__,
            tuple((field.name, _normalize(getattr(value, field.name))) for field in fields(value)),
        )
    if isinstance(value, timezone):
        return ("timezone", value.tzname(None), value.utcoffset(None).total_seconds())
    if isinstance(value, Enum):
        return ("enum", type(value).__module__, type(value).__qualname__, _normalize(value.value))
    if isinstance(value, type):
        return ("class", value.__module__, value.__qualname__)
    if isinstance(value, CodeType):
        return value.replace(
            co_filename="",
            co_firstlineno=0,
            co_linetable=b"",
            co_consts=tuple(_normalize(item) for item in value.co_consts),
        )
    if isinstance(value, tuple):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return (
            "set" if isinstance(value, set) else "frozenset",
            tuple(
                sorted(
                    (_normalize(item) for item in value), key=lambda item: marshal.dumps(item, 0)
                )
            ),
        )
    if isinstance(value, list):
        return ("list", tuple(_normalize(item) for item in value))
    if isinstance(value, dict):
        return (
            "dict",
            tuple(
                sorted(
                    ((_normalize(key), _normalize(item)) for key, item in value.items()),
                    key=lambda pair: marshal.dumps(pair[0], 0),
                )
            ),
        )
    if isinstance(value, re.Pattern):
        return ("regex", value.pattern, value.flags)
    if value is None or value is Ellipsis or isinstance(value, (str, bytes, int, float, complex)):
        return value
    raise TypeError("Not a loaded code constant")


def _schema_references(value):
    # Pydantic's schema refs include process-local model addresses, not policy.
    if isinstance(value, dict):
        return {
            key: re.sub(r":\d+(?=\]|,|$)", "", item)
            if key in {"ref", "schema_ref"} and isinstance(item, str)
            else _schema_references(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return tuple(_schema_references(item) for item in value)
    return value


def _model_record(model):
    validator = model.__pydantic_validator__
    if type(validator) is not SchemaValidator:
        raise TypeError("Unsupported compiled model validator")
    constructor, arguments = validator.__reduce__()
    if constructor is not SchemaValidator:
        raise TypeError("Unknown compiled model validator")
    return (
        _normalize(model.model_config),
        _normalize(_schema_references(arguments)),
        tuple(
            (
                name,
                _normalize(field.annotation),
                _normalize(field.default),
                _normalize(field.default_factory),
                _normalize(field.metadata),
                _normalize(field.alias),
                _normalize(field.validation_alias),
                _normalize(field.serialization_alias),
            )
            for name, field in sorted(model.model_fields.items())
        ),
    )


def _module_records(module):
    records = []
    for key, value in sorted(vars(module).items()):
        if key.isupper() and key not in _RUNTIME_VALUES.get(module.__name__, ()):
            records.append((key, "constant", _normalize(value)))
        if (
            isinstance(value, type)
            and value is not BaseModel
            and issubclass(value, BaseModel)
            and value.__module__.startswith(__package__ + ".")
        ):
            records.append((key, "model_policy", _model_record(value)))
        # Calls use this module's current binding, including imported aliases.
        # Checking only the origin module would miss a replaced authorization alias.
        if isinstance(value, FunctionType):
            records.append((key, "bound_function", _normalize(value)))
            continue
        if getattr(value, "__module__", None) != module.__name__:
            continue
        members = vars(value).items() if isinstance(value, type) else ((key, value),)
        for member, function in sorted(members):
            if isinstance(function, (staticmethod, classmethod)):
                function = function.__func__
            if isinstance(function, property):
                function = function.fget
            if not isinstance(function, FunctionType):
                continue
            records.append((key, member, _normalize(function)))
    return tuple(records)


def _revision(role, module_names):
    # Include the actual loaded normalizer and role definitions in every identity.
    modules = [sys.modules.get(f"{__package__}.{name}") for name in module_names]
    if any(module is None for module in modules):
        return None
    try:
        records = tuple((module.__name__, _module_records(module)) for module in modules)
        own = _module_records(sys.modules[__name__])
        payload = (_NAMESPACE, role, (sys.implementation.name, sys.version), own, records)
        # Modern marshal formats encode shared-object references. Import order
        # changes that sharing even when every normalized module is identical.
        # Version 0 encodes values without reference or string-interning tables.
        return hashlib.sha256(marshal.dumps(payload, 0)).hexdigest()
    except (TypeError, ValueError, RecursionError):
        return None


def load_controller_modules() -> None:
    """Explicit startup loading; status reads need only inspect sys.modules."""
    for name in _RUNTIME_MODULES["controller"]:
        import_module(f".{name}", __package__)


def load_worker_modules() -> None:
    """Load lazily imported worker code before the worker records its identity."""
    for name in _RUNTIME_MODULES["worker"]:
        import_module(f".{name}", __package__)


def loaded_runtime_revision(role: str) -> str | None:
    """Return a role-qualified loaded identity; missing executor code stays unknown."""
    if role not in _RUNTIME_MODULES:
        raise ValueError("Unknown loaded runtime role")
    revision = _revision(role, _RUNTIME_MODULES[role])
    return f"{_NAMESPACE}:{role}:{revision}" if revision is not None else None


def loaded_preparation_revision() -> str:
    """Retain preparation's explicit startup import and 64-hex revision contract."""
    for name in _PREPARATION_MODULES:
        import_module(f".{name}", __package__)
    return _revision("preparation", _PREPARATION_MODULES)


def measure_packaged_roles(*, worker_first=False) -> dict:
    """Build-only import probe; never construct a service, store, driver or browser."""
    from pathlib import Path

    roles = ("worker", "controller") if worker_first else ("controller", "worker")
    for role in roles:
        for name in _RUNTIME_MODULES[role]:
            import_module(f".{name}", __package__)
    revisions = {role: loaded_runtime_revision(role) for role in ("controller", "worker")}
    if any(value is None for value in revisions.values()):
        raise ValueError("A packaged loaded role cannot be normalized")
    static = Path(__file__).with_name("portal_static")
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in static.iterdir()
        if path.is_file()
    }
    # Use the same canonical digest as the startup UI snapshot.
    import json

    return {
        **revisions,
        "ui_revision": hashlib.sha256(
            json.dumps(files, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest(),
        "python_runtime": sys.version,
    }
