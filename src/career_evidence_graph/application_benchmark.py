"""Read an explicit private historical reference without changing match scores."""

from __future__ import annotations

import json
import math
import os
import stat
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .validation.hashing import record_digest as digest

Revision = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Percentage = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Score(_StrictModel):
    lower: Percentage
    upper: Percentage
    coverage: Percentage
    eligibility: Literal["not_specified", "supported", "needs_input", "conflict"]

    @model_validator(mode="after")
    def interval(self):
        if self.lower > self.upper or not math.isclose(
            self.upper - self.lower, 100 - self.coverage, rel_tol=0, abs_tol=1e-7
        ):
            raise ValueError("Invalid interval")
        return self


class _Case(_StrictModel):
    case_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    role_title: str = Field(min_length=1)
    jd_revision: Revision
    role: Literal["reference", "holdout", "context"]
    outcome: Literal[
        "interview_invitation",
        "assessment_invitation",
        "actionable_followup",
        "rejected",
        "unknown",
    ]
    evidence_level: Literal["gmail", "tracker"]
    score: _Score
    analysis_id: str = Field(min_length=1)
    limitations: list[str]


class _Baseline(_StrictModel):
    schemaVersion: Annotated[int, Field(ge=1, le=1)]
    revision: Revision
    source_snapshot_revision: Revision
    configuration_revision: Revision
    policy_version: Literal["documentary-match/v1"]
    evaluated_at: str
    historical_materials_available: bool
    protocol: str | None = None
    cases: list[_Case]

    @field_validator("historical_materials_available")
    @classmethod
    def current_materials(cls, value):
        if value is not False:
            raise ValueError("Only current-material re-evaluation is supported")
        return value

    @field_validator("evaluated_at")
    @classmethod
    def evaluation_time(cls, value):
        if datetime.fromisoformat(value).tzinfo is None:
            raise ValueError("Evaluation time requires a timezone")
        return value

    @model_validator(mode="after")
    def unique_cases(self):
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate case identity")
        return self


def _unavailable(status, revision=None):
    messages = {
        "missing": "Historical reference is missing.",
        "invalid": "Historical reference cannot be verified.",
        "stale": "Historical reference uses different materials or model configuration.",
    }
    return {
        "status": status,
        "revision": revision,
        "reference_cases": [],
        "limitations": [
            messages[status],
            "Relative position is unavailable; the documentary score is unchanged.",
        ],
    }


def _read_current(root):
    root = Path(root).expanduser().absolute()
    if root.is_symlink() or root.resolve(strict=True) != root:
        raise ValueError("Invalid private root")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        root_fd = os.open(root, directory_flags)
        stack.callback(os.close, root_fd)
        directory_fd = os.open(".tomorrowstar-match-history", directory_flags, dir_fd=root_fd)
        stack.callback(os.close, directory_fd)
        descriptor = os.open(
            "current.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
        )
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Invalid benchmark file")
            raw = stream.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Benchmark file is too large")
    return json.loads(raw.decode("utf-8"))


def load_benchmark(root: Path, snapshot_revision: str, configuration_revision: str) -> dict:
    """Read only the fixed versioned benchmark in the selected career root."""
    try:
        payload = _read_current(root)
        baseline = _Baseline.model_validate(payload)
        if baseline.revision != digest(
            {key: value for key, value in payload.items() if key != "revision"}
        ):
            return _unavailable("invalid")
    except FileNotFoundError:
        return _unavailable("missing")
    except (OSError, UnicodeError, ValueError, TypeError, ValidationError):
        return _unavailable("invalid")
    if (
        baseline.source_snapshot_revision != snapshot_revision
        or baseline.configuration_revision != configuration_revision
    ):
        return _unavailable("stale", baseline.revision)
    return {
        "status": "ready",
        "revision": baseline.revision,
        "policy_version": baseline.policy_version,
        "source_snapshot_revision": baseline.source_snapshot_revision,
        "configuration_revision": baseline.configuration_revision,
        "evaluated_at": baseline.evaluated_at,
        "historical_materials_available": False,
        "protocol": baseline.protocol,
        "reference_cases": [
            {
                key: value
                for key, value in case.model_dump().items()
                if key in {"case_id", "company", "role_title", "score", "limitations"}
            }
            for case in baseline.cases
            if case.role == "reference"
        ],
        "limitations": [
            "Reference intervals use current materials, not historical application materials. "
            "Scores are unchanged; they do not estimate hiring probability."
        ],
    }


def compare_benchmark(score: dict | None, loaded: dict) -> dict:
    """Compare score intervals without remapping the new or historical numbers."""
    result = {
        "status": loaded["status"],
        "revision": loaded["revision"],
        "reference_range": None,
        "comparisons": [],
        "limitations": deepcopy(loaded["limitations"]),
    }
    if loaded["status"] != "ready":
        return result
    references = loaded["reference_cases"]
    try:
        new_score = _Score.model_validate(score)
    except ValidationError:
        result["status"] = "unavailable"
        result["limitations"].append(
            "A valid new score is unavailable; relative position is unavailable."
        )
        return result
    if not references:
        result["status"] = "unavailable"
        result["limitations"].append(
            "There are no reference cases; holdout and context cases cannot define a range."
        )
        return result
    return {
        "status": "ready",
        "revision": loaded["revision"],
        "reference_range": {
            "lower": min(case["score"]["lower"] for case in references),
            "upper": max(case["score"]["upper"] for case in references),
        },
        "comparisons": [
            {
                key: deepcopy(case[key])
                for key in ("case_id", "company", "role_title", "score", "limitations")
            }
            | {
                "position": "above"
                if new_score.lower > case["score"]["upper"]
                else "below"
                if new_score.upper < case["score"]["lower"]
                else "overlaps"
            }
            for case in references
        ],
        "limitations": deepcopy(loaded["limitations"]),
    }
