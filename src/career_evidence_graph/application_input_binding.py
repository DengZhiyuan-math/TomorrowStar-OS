"""Input binding: which recorded inputs a completed or pending stage may still reuse.

One owner for the rules that decide when a task's saved inputs still describe the
current JD, facts and configuration. Keys fall into three classes:

* semantic keys (JD, sources, information library, prompt/policy/schema versions,
  model settings) participate in every comparison;
* provenance keys (engine and component SHA256, the codex path and executable
  metadata) are recorded beside a configuration but never decide freshness, so an
  App rebuild or a Codex CLI update does not invalidate in-flight work (APP-15);
* operational keys (account context, historical benchmark) and configuration keys
  are retained once the stage that consumed them completed.

Configuration revisions written by this Module carry ``REVISION_PREFIX``. A saved
value without it is a legacy revision that also hashed provenance; it is never
reported as stale, only as needing a one-time rebind to the current value.

Only ``validation.hashing`` is imported: Flow, Analysis, Resume, explanations and
readiness are callers of this Module.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass

from .validation.hashing import record_digest as digest

REVISION_PREFIX = "cfg2:"
# Recorded for provenance, never compared. Any key ending in ``engine_sha256`` is
# also provenance (resume, draft, LaTeX and presentation engines).
PROVENANCE_KEYS = frozenset(
    {
        "engine_sha256",
        "retrieval_engine_sha256",
        "retrieval_component_sha256",
        "executable",
        "resolved_executable",
        "executable_status",
        "executable_metadata_revision",
        "immutable_snapshot",
        "cli_identity",
    }
)
CONFIGURATION_INPUT_KEYS = ("analysis_configuration_revision", "resume_configuration_revision")
OPERATIONAL_INPUT_KEYS = ("historical_benchmark_revision", "account_context_revision")
RETAINED_INPUT_KEYS = frozenset(CONFIGURATION_INPUT_KEYS + OPERATIONAL_INPUT_KEYS)
# Inputs that only material generation consumes; documentary analysis ignores them.
MATERIAL_INPUT_KEYS = frozenset(
    {
        "resume_configuration_revision",
        "qualification_information_revision",
        "presentation_feedback_revision",
    }
)
LIBRARY_INPUT_KEYS = ("sources_revision", "information_library_revision")
FEEDBACK_KEY = "presentation_feedback_revision"
STAGES = frozenset({"analysis", "resume", "export", "materials", "material_update", "readiness"})


def provenance_key(key) -> bool:
    return key in PROVENANCE_KEYS or isinstance(key, str) and key.endswith("engine_sha256")


def semantic_configuration(configuration):
    """Drop provenance keys at every level; the rest decides configuration identity."""
    if isinstance(configuration, dict):
        return {
            key: semantic_configuration(value)
            for key, value in configuration.items()
            if not provenance_key(key)
        }
    return deepcopy(configuration)


def bound_revision(record) -> str:
    """Revision of a record already built from semantic revisions."""
    return REVISION_PREFIX + digest(record)


def configuration_revision(configuration) -> str:
    """Revision of a configuration's semantic part; provenance stays recorded only."""
    return bound_revision(semantic_configuration(configuration))


def legacy_revision(value) -> bool:
    return isinstance(value, str) and not value.startswith(REVISION_PREFIX)


def revision_matches(configuration, revision) -> bool:
    """A recorded configuration still proves its recorded revision, in either format."""
    return revision in (configuration_revision(configuration), digest(configuration))


def record_revision_matches(record, revision) -> bool:
    return revision in (bound_revision(record), digest(record))


def same_revision(saved, current) -> bool:
    """Two configuration revisions agree, or one predates the semantic format.

    A legacy value also hashed provenance and cannot be split again; it is bound
    once to the current revision instead of invalidating saved work.
    """
    return saved == current or (
        isinstance(saved, str)
        and isinstance(current, str)
        and legacy_revision(saved) != legacy_revision(current)
    )


def same_configuration(saved, current) -> bool:
    """Compare two recorded configurations without their provenance."""
    return semantic_configuration(saved) == semantic_configuration(current)


def job_input_revision(application: dict) -> str:
    """Bind the complete JD and job fields without unrelated application notes."""
    return digest(
        {
            key: application.get(key, "")
            for key in ("company", "role_title", "location", "job_description")
        }
    )


def analysis_input_binding(inputs):
    """Keep documentary analysis independent of contact and material-only inputs."""
    material_keys = set(MATERIAL_INPUT_KEYS)
    if "information_library_root" in inputs:
        # Canonical bindings identify the contact projection and its source root.
        # Legacy unscoped library revisions may include qualification facts.
        material_keys |= {"information_library_revision", "information_library_root"}
    return {key: value for key, value in inputs.items() if key not in material_keys}


def resolution_input_revision(inputs) -> str:
    """Legacy hard-condition resolutions bound every input except the resume setting."""
    return digest({k: v for k, v in inputs.items() if k != "resume_configuration_revision"})


def retained_presentation_input(task, inputs):
    """Only a completed attachment receipt can retain its material-only input."""
    value = task["inputs"].get(FEEDBACK_KEY)
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        return
    if any(
        row.get("input_revision") == digest(task["inputs"])
        and row.get(FEEDBACK_KEY) == value
        and row.get("generation_id")
        and row.get("export_id") == task.get("resume_id")
        for row in task.get("material_reconnections", [])
    ):
        inputs[FEEDBACK_KEY] = value


def retained_configuration_inputs(task, inputs, *, completed_stages=None, adopt_libraries=False):
    """Keep completed results bound to the configuration that produced them.

    ``adopt_libraries`` is the user's explicit sync, which takes current library
    revisions; every other caller keeps those of the completed analysis.
    """
    resolved = deepcopy(inputs)
    retained_presentation_input(task, resolved)
    if "qualification_information_revision" in task["inputs"]:
        # Preserve the historical receipt bytes from the former over-broad binding.
        # Current qualification facts are checked live, not as PDF/analysis inputs.
        resolved["qualification_information_revision"] = task["inputs"][
            "qualification_information_revision"
        ]
    if completed_stages is None:
        completed_stages = {
            key
            for key, value in task.get("stages", {}).items()
            if value.get("status") == "complete"
        }
    if "analysis" in completed_stages and not adopt_libraries:
        # Library revisions are provenance once the analysis completed (APP-04,
        # 2026-11-01): revising either library never invalidates a job; re-matching
        # or regenerating is explicit. An analysis still to run reads current data.
        for key in LIBRARY_INPUT_KEYS:
            if key in task["inputs"]:
                resolved[key] = task["inputs"][key]
    if (
        "resume" in completed_stages
        and "information_library_revision" not in task["inputs"]
        and isinstance(task.get("resume_id"), str)
        and bool(task["resume_id"])
        and isinstance(task.get("resume_sha256"), str)
        and re.fullmatch(r"[a-f0-9]{64}", task["resume_sha256"]) is not None
        and not task.get("export_recoveries")
        and task.get("group_read", {}).get("status") not in {"running", "needs_recheck"}
        and not any(
            stage.get("status") in {"queued", "running", "needs_recheck"}
            for stage in task.get("stages", {}).values()
        )
    ):
        # Only known completed PDF bytes can predate this binding. Imported drafts
        # and unknown exports must still compare every newly observed fact input.
        resolved.pop("information_library_revision", None)
        resolved.pop("information_library_root", None)
    unchanged = _without(resolved, RETAINED_INPUT_KEYS) == _without(
        task["inputs"], RETAINED_INPUT_KEYS
    )
    analysis_unchanged = _without(
        analysis_input_binding(resolved), RETAINED_INPUT_KEYS
    ) == _without(analysis_input_binding(task["inputs"]), RETAINED_INPUT_KEYS)
    for stage in ("analysis", "resume"):
        if stage in completed_stages and (unchanged or stage == "analysis" and analysis_unchanged):
            keys = (f"{stage}_configuration_revision",)
            if stage == "analysis":
                # Local credential refreshes are operational changes, not changes
                # to the JD, applicant facts or already generated content.
                keys += OPERATIONAL_INPUT_KEYS
            for key in keys:
                if key in task["inputs"]:
                    resolved[key] = task["inputs"][key]
                else:
                    resolved.pop(key, None)
    return resolved


def latest_preparation_task(tasks, application_id=None):
    """Keep settled cancellations in history without superseding current work."""
    return next(
        (
            row
            for row in reversed(tasks)
            if (application_id is None or row["application_id"] == application_id)
            and (
                row["status"] != "cancelled"
                or row.get("worker_ref")
                or row.get("codex_handoff_ref")
                or row.get("codex_handoff_attempt")
                or row.get("material_binding_error")
                or row.get("material_update", {}).get("status") not in {None, "complete"}
                or row.get("export_recoveries")
                or row.get("group_read", {}).get("status") in {"running", "needs_recheck"}
                or row.get("worker_preparation", {}).get("status") == "pending"
                or any(
                    item["status"] in {"queued", "running", "needs_recheck"}
                    for item in row["stages"].values()
                )
            )
        ),
        None,
    )


@dataclass(frozen=True)
class InputBinding:
    """Whether saved inputs still bind a stage: reusable, stale or needing a rebind."""

    status: str
    changed: tuple[str, ...] = ()
    rebind: tuple[str, ...] = ()

    @property
    def reusable(self) -> bool:
        return self.status == "reusable"

    @property
    def stale(self) -> bool:
        return self.status == "stale"


def stage_inputs(stage, inputs, *, origin=None):
    """The part of a task's inputs that the named stage consumes."""
    if stage not in STAGES:
        raise ValueError(f"unknown input binding stage: {stage}")
    if stage == "analysis":
        return analysis_input_binding(inputs)
    if origin == "existing_latex":
        # An imported LaTeX version owns its generator setting.
        return {k: v for k, v in inputs.items() if k != "resume_configuration_revision"}
    return dict(inputs)


def reusable(stage, saved, current, *, origin=None) -> InputBinding:
    """Compare saved and current inputs under one stage's binding rules.

    ``current`` should already be the retained view of the live inputs
    (``retained_configuration_inputs``). A legacy configuration revision facing
    a current semantic revision asks for a rebind, never for a stale result.
    """
    old = stage_inputs(stage, saved, origin=origin)
    new = stage_inputs(stage, current, origin=origin)
    changed, rebind = [], []
    for key in sorted(set(old) | set(new)):
        if old.get(key) == new.get(key):
            continue
        if (
            key in CONFIGURATION_INPUT_KEYS
            and legacy_revision(old.get(key))
            and not legacy_revision(new.get(key))
            and isinstance(new.get(key), str)
        ):
            rebind.append(key)
        else:
            changed.append(key)
    if changed:
        return InputBinding("stale", tuple(changed), tuple(rebind))
    if rebind:
        return InputBinding("rebind", (), tuple(rebind))
    return InputBinding("reusable")


def rebound_inputs(saved, current, binding: InputBinding):
    """Saved inputs with each legacy configuration revision replaced by the current one."""
    resolved = deepcopy(saved)
    for key in binding.rebind:
        resolved[key] = current[key]
    return resolved


def rebind_record(saved, current, binding: InputBinding, at) -> dict:
    """The history row that records one legacy-to-semantic configuration rebind."""
    return {
        "keys": list(binding.rebind),
        "from": {key: saved.get(key) for key in binding.rebind},
        "to": {key: current.get(key) for key in binding.rebind},
        "reason": "legacy_configuration_revision",
        "at": at,
    }


def _without(inputs, keys):
    return {k: v for k, v in inputs.items() if k not in keys}
