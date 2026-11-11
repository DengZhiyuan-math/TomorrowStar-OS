"""The single Education Record authority and the application values derived from it."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationError, model_validator

from ._vendor import job_apply_store as helper
from .application_resume_content import Contract, Source, Text
from .application_storage import private_root
from .career_portal_data import ApplicationStore, PortalDataError

Month = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}(?:-(?:0[1-9]|1[0-2]))?$")]
_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


class EducationRecord(Contract):
    id: Text
    level: Literal["bachelor", "master", "doctorate", "other"]
    degree: Text
    field: Text
    institution: Text
    location: Text | None = None
    start: Month | None = None
    # For a degree in progress, ``end`` is the expected completion.
    end: Month | None = None
    status: Literal["awarded", "in_progress", "discontinued"]
    details: list[Text]
    sources: list[Source] = Field(min_length=1)


class EducationRecords(Contract):
    schema_version: Literal["education-records/v1"]
    revision: Text
    records: list[EducationRecord]

    @model_validator(mode="after")
    def validate_identity(self):
        identities = [record.id for record in self.records]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate education ID")
        return self


def _revision(value):
    raw = json.dumps(
        {key: item for key, item in value.items() if key != "revision"},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EducationStore:
    """Versioned education records beside the experience store, with immutable history."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.base = self.root / ".tomorrowstar-education"

    def read(self):
        path = self.base / "records.json"
        if not path.exists():
            return None
        try:
            value = EducationRecords.model_validate(
                helper.read_json_object(path, "education records")
            ).model_dump(mode="json")
        except (helper.StoreError, ValidationError) as error:
            raise PortalDataError("education-invalid", "学历记录不能核验。", 409) from error
        if value["revision"] != _revision(value):
            raise PortalDataError("education-invalid", "学历记录不能核验。", 409)
        return value

    def save(self, records, *, expected_revision, actor):
        try:
            value = EducationRecords.model_validate(
                {"schema_version": "education-records/v1", "revision": "-", "records": records}
            ).model_dump(mode="json")
        except ValidationError as error:
            raise PortalDataError("education-invalid", "学历记录格式不正确。", 400) from error
        value["revision"] = _revision(value)
        with ApplicationStore(self.root).write_lock():
            current = self.read()
            if (current or {}).get("revision") != expected_revision:
                raise PortalDataError("revision-conflict", "学历记录已更新，请刷新后重试。", 409)
            history = private_root(self.base / "history")
            event = {
                "actor": actor,
                "previous_revision": expected_revision,
                "saved_at": datetime.now(UTC).isoformat(),
                "records": value,
            }
            with (history / f"{value['revision']}.json").open("x", encoding="utf-8") as handle:
                json.dump(event, handle, ensure_ascii=False, sort_keys=True)
            helper.atomic_write_json(self.base / "records.json", value)
        return value


def _month(value, *, short=False):
    year, _, month = (value or "").partition("-")
    name = _MONTHS[int(month) - 1][: 3 if short else None] if month else ""
    return f"{name} {year}".strip()


def education_text(record):
    """One literal statement per degree for matching; quotes must come from it."""
    status = {
        "awarded": "awarded",
        "in_progress": f"in progress; expected completion {_month(record['end'])}",
        "discontinued": "discontinued",
    }[record["status"]]
    period = " to ".join(part for part in (record["start"], record["end"]) if part)
    # The level leads, so a national label such as "M2" is read as the degree it is.
    level = {
        "doctorate": "Doctoral degree (PhD): ",
        "master": "Master's degree: ",
        "bachelor": "Bachelor's degree: ",
    }.get(record["level"], "")
    text = f"{level}{record['degree']}, {record['institution']}, {period} ({status})."
    return " ".join([text, *record["details"]])


def education_answers(collection):
    """Answer values the Information Library used to keep as separate copies."""
    current = [row for row in collection["records"] if row["status"] == "in_progress"]
    if len(current) != 1 or not current[0]["end"] or "-" not in current[0]["end"]:
        return {}
    row = current[0]
    year, month = row["end"].split("-")
    label = {"doctorate": "PhD", "master": "Master's degree", "bachelor": "Bachelor's degree"}
    return {
        "academic_degree": (
            f"{label.get(row['level'], row['degree'])} "
            f"(in progress; expected graduation {_MONTHS[int(month) - 1]} {year})"
        ),
        "graduation_date": f"{month}/{year}",
    }


def education_profile(collection):
    """The earlier profile shape still read by qualification checks."""

    def period(row):
        expected = "Expected " if row["status"] == "in_progress" else ""
        return f"{_month(row['start'], short=True)} - {expected}{_month(row['end'], short=True)}"

    return {
        "education": [
            {
                "degree": row["degree"],
                "institution": row["institution"],
                "period": period(row),
                "detail": " ".join(row["details"]),
            }
            for row in collection["records"]
        ],
        "source": {
            "id": "education-records",
            "revision": collection["revision"],
            "source_name": ".tomorrowstar-education/records.json",
        },
    }
