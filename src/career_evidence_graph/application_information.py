"""Read existing applicant information without initializing an application worker."""

from __future__ import annotations

import fcntl
import io
import json
import os
import re
import stat
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .career_portal_data import PortalDataError, _write_file
from .job_screening import LEVELS, _language_requirement, application_country
from .validation.hashing import record_digest as digest

COUNTRIES = {"CHE", "USA", "GBR", "DEU", "FRA", "CAN", "OTHER"}
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
CONTACT_FACTS = ("name", "first_name", "last_name", "email", "phone", "github_url", "linkedin_url")
ADDITIONAL_LANGUAGE_FACTS = (
    "language_french_cefr",
    "language_german_cefr",
    "language_japanese_cefr",
)


def fact_for(question: str) -> str:
    """Reviewed aliases only. Unknown semantics remain a question for the user."""
    canonical = canonical_question_fact(question)
    if canonical is not None:
        return canonical
    normalized = helper.normalize_question(question).strip(" *:")
    groups = {
        "name": {"full name", "name", "your full name"},
        "first_name": {"first name", "given name"},
        "last_name": {"last name", "family name", "surname"},
        "email": {"email", "email address", "your email address"},
        "phone": {"phone", "phone number"},
        "github_url": {
            "github",
            "github url",
            "github profile",
            "github profile url",
            "link to your github profile",
        },
        "linkedin_url": {
            "linkedin",
            "linkedin url",
            "linkedin profile",
            "linkedin profile url",
            "link to your linkedin profile",
        },
        "language_french_cefr": {
            "french proficiency cefr",
            "french level",
            "french proficiency",
            "french language level",
        },
        "language_german_cefr": {
            "german proficiency cefr",
            "german level",
            "german proficiency",
            "german language level",
        },
        "sponsorship_now_future": {
            "will you now or in the future require visa sponsorship",
            "do you require visa sponsorship now or in the future",
        },
        "work_authorization_now": {
            "are you currently authorized to work in this country",
            "do you currently have work authorization in this country",
        },
    }
    for fact, aliases in groups.items():
        if normalized in aliases:
            return fact
    return "question:" + normalized


def scope_matches(scope: dict, job: dict) -> bool:
    context = {key: job[key] for key in ("country", "company", "application_id")}
    return all(key in context and context[key] == value for key, value in scope.items())


def material_information_context(application: dict) -> dict:
    """Use a named unique job country for material contacts, without guessing from a city."""
    country = application.get("country")
    if not isinstance(country, str) or country not in COUNTRIES:
        country = application_country(application.get("location")) or "OTHER"
    return {**application, "country": country}


def _information_projection(application, library, facts, *, include_unconfirmed=False):
    return {
        "status": "available" if library.get("status") == "unconfigured" else library.get("status"),
        "records": {
            fact: sorted(
                applicable_answers(
                    library.get("records", []),
                    fact,
                    material_information_context(application),
                    include_unconfirmed=include_unconfirmed,
                ),
                key=lambda record: (str(record.get("key", "")), digest(record)),
            )
            for fact in facts
        }
        if library.get("status") in {"available", "unconfigured"}
        else {},
    }


def material_information_library(application: dict, library: dict) -> dict:
    """Bind material inputs to applicable contact facts, retaining the full private view."""
    return {
        **library,
        "library_revision": library.get("library_revision", library.get("revision")),
        "revision": digest(_information_projection(application, library, CONTACT_FACTS)),
        # Preserve the public read-only projection; this is not a Flow/PDF input.
        "qualification_revision": digest(
            _information_projection(
                application,
                library,
                (*ADDITIONAL_LANGUAGE_FACTS, "language_english_fluent"),
                include_unconfirmed=True,
            )
        ),
    }


_SAVED_QUALIFICATION_QUESTIONS = {
    "current academic degree": "academic_degree",
    "graduation date mm yyyy": "graduation_date",
    "internship start date mm yyyy": "internship_start",
    "internship duration": "internship_duration",
    "first preferred location": "preferred_location",
    "are you fluent in english": "language_english_fluent",
    "do you speak english fluently": "language_english_fluent",
    "english fluency": "language_english_fluent",
    "english proficiency cefr": "language_english_cefr",
    "english level": "language_english_cefr",
    "english language level": "language_english_cefr",
    "japanese proficiency cefr": "language_japanese_cefr",
    "japanese level": "language_japanese_cefr",
    "japanese proficiency": "language_japanese_cefr",
    "japanese language level": "language_japanese_cefr",
}


def _information_fact(question):
    return canonical_question_fact(question) or fact_for(question)


def canonical_question_fact(question: str) -> str | None:
    """Extra saved aliases shared with filling, without invoking its fallback."""
    normalized = helper.normalize_question(question).strip(" *:")
    return _SAVED_QUALIFICATION_QUESTIONS.get(normalized)


def information_fact(question: str) -> str:
    """Share saved-answer semantics; unfamiliar questions retain their own identity."""
    return _information_fact(question)


def information_context(application: dict, library: dict, *, fact_keys=None) -> dict:
    """Expose applicable facts, never infer a requirement judgment or alter the store.

    Records retain their original wording and provenance. A confirmed personal claim
    is not a certificate, a proficiency assessment, or permission outside its scope.
    Withdrawn and uncertain narrow records prevent reuse of a wider old answer.
    """
    context = material_information_context(application)
    records = library.get("records", []) if library.get("status") == "available" else []
    keys = (
        sorted(set(fact_keys))
        if fact_keys is not None
        else sorted(
            {
                information_fact(row["question"])
                for row in records
                if isinstance(row.get("question"), str)
            }
        )
    )
    facts = []
    for fact in keys:
        applicable = sorted(
            applicable_answers(records, fact, context, include_unconfirmed=True),
            key=lambda row: (str(row.get("key", "")), digest(row)),
        )
        values = {digest(row.get("value")) for row in applicable}
        states = {row.get("state") for row in applicable}
        if not applicable or states == {"missing"}:
            status = "missing"
        elif len(values) != 1 or len(states) != 1:
            status = "conflict"
        elif states == {"confirmed"} and applicable[0].get("value") is not None:
            status = "confirmed"
        elif states == {"inferred"}:
            status = "inferred"
        else:
            status = "missing"
        item = {
            "fact": fact,
            "status": status,
            "records": [
                {**deepcopy(row), "revision": digest(row), "fact": fact} for row in applicable
            ],
            "references": [{"key": row["key"], "revision": digest(row)} for row in applicable],
            "basis": "saved_applicant_answer",
            "accepted_as_fact": status == "confirmed",
        }
        if status == "confirmed":
            item["value"] = deepcopy(applicable[0]["value"])
        facts.append(item)
    result = {
        "schema": "application-information-context/v1",
        "library_status": library.get("status", "unavailable"),
        "facts": facts,
    }
    return {**result, "revision": digest(result)}


def validate_information_references(context: dict, references: list[dict]) -> list[dict]:
    """Resolve citations against the current applicable facts, without model guesses.

    Callers must rebuild context from the active library. A citation can optionally
    carry the selected fact and value; either must match exactly when present.
    """
    if not isinstance(references, list) or context.get("library_status") != "available":
        raise PortalDataError("invalid-information-reference", "信息引用不可用。")
    available = {}
    for fact in context.get("facts", []):
        if fact.get("status") == "confirmed":
            for row in fact["records"]:
                available[(row["key"], row["revision"])] = row
    selected = []
    seen = set()
    for reference in references:
        if not isinstance(reference, dict):
            raise PortalDataError("invalid-information-reference", "信息引用无效。")
        identity = (reference.get("key"), reference.get("revision"))
        if not all(isinstance(value, str) for value in identity):
            raise PortalDataError("invalid-information-reference", "信息引用缺少版本。")
        row = available.get(identity)
        if (
            row is None
            or ("fact" in reference and reference["fact"] != row["fact"])
            or ("value" in reference and digest(reference["value"]) != digest(row["value"]))
        ):
            raise PortalDataError("invalid-information-reference", "信息已变更、存在冲突或不适用。")
        if identity not in seen:
            selected.append(deepcopy(row))
            seen.add(identity)
    return selected


def information_source_snapshot(application: dict, library: dict, base_snapshot: dict) -> dict:
    """Add literal confirmed answers for matching, never for résumé generation."""
    snapshot = deepcopy(base_snapshot)
    context = information_context(application, library)
    for fact in context["facts"]:
        if fact["status"] != "confirmed":
            continue
        binding = {
            "fact": fact["fact"],
            "references": fact["references"],
            "context_revision": context["revision"],
        }
        identifier = "confirmed-information:" + digest(
            {"fact": fact["fact"], "references": fact["references"]}
        )
        text = json.dumps(
            {"fact": fact["fact"], "value": fact["value"], "records": fact["records"]},
            ensure_ascii=False,
            sort_keys=True,
        )
        revision = digest(text)
        name = "Applicant information: " + fact["fact"]
        snapshot.setdefault("documents", []).append(
            {
                "id": identifier,
                "source_name": name,
                "kind": "source",
                "source_kind": "confirmed_information",
                "available": True,
                "revision": revision,
                "content": text,
            }
        )
        snapshot.setdefault("items", []).append(
            {
                "title": fact["fact"],
                "text": text,
                "source_id": identifier + ":answer",
                "evidence_id": identifier,
                "source_name": name,
                "source_revision": revision,
                "source_kind": "confirmed_information",
                "locator": "answer",
                "attribution": "Applicant-confirmed personal statement; retain original source.",
                "boundaries": (
                    "Accepted current applicant fact. Preserve its value and application scope."
                ),
                "review_status": "library_fact",
                "application_trusted": True,
                "resume_eligible": False,
                "documentary_only": True,
                "rewrite_allowed": False,
                "confirmed_information": binding,
            }
        )
    snapshot["information_context"] = context
    snapshot.pop("revision", None)
    snapshot["revision"] = digest(snapshot)
    return snapshot


def validate_information_source(application: dict, library: dict, source: dict) -> list[dict]:
    """Rebind a match-only information source to the current scoped answer context."""
    context = information_context(application, library)
    binding = source.get("confirmed_information")
    if (
        source.get("source_kind") != "confirmed_information"
        or not isinstance(binding, dict)
        or binding.get("context_revision") != context["revision"]
        or not isinstance(binding.get("references"), list)
        or not binding["references"]
    ):
        raise PortalDataError("invalid-information-reference", "信息来源已变更或不适用。")
    rows = validate_information_references(context, binding["references"])
    if any(row["fact"] != binding.get("fact") for row in rows):
        raise PortalDataError("invalid-information-reference", "信息来源与事实不符。")
    expected = next(
        (
            item
            for item in information_source_snapshot(application, library, {})["items"]
            if item["confirmed_information"]["fact"] == binding["fact"]
        ),
        None,
    )
    if expected is None or any(
        source.get(key) != expected[key]
        for key in ("source_id", "evidence_id", "source_revision", "text", "confirmed_information")
    ):
        raise PortalDataError("invalid-information-reference", "信息来源正文或版本不符。")
    return rows


def applicable_answers(
    records: list[dict], fact: str, context: dict, *, include_unconfirmed=False
) -> list[dict]:
    """Select scoped facts, with confirmed values by default and explicit job exceptions."""
    country = context.get("country")
    context = {
        "country": country if isinstance(country, str) and country in COUNTRIES else "OTHER",
        "company": context.get("company", ""),
        "application_id": context.get("application_id") or context.get("id", ""),
    }
    applicable = [
        record
        for record in records
        if (include_unconfirmed or record.get("state") == "confirmed")
        and isinstance(record.get("question"), str)
        and _information_fact(record["question"]) == fact
        and isinstance(record.get("scope"), dict)
        and all(isinstance(value, str) and value for value in record["scope"].values())
        and scope_matches(record["scope"], context)
    ]
    if any("application_id" in record["scope"] for record in applicable):
        applicable = [record for record in applicable if "application_id" in record["scope"]]
    # Incomparable scopes remain a real conflict; never use insertion order to decide.
    return [
        record
        for record in applicable
        if not any(record["scope"].items() < other["scope"].items() for other in applicable)
    ]


class _Document:
    """Give the pinned validators one bounded, immutable file snapshot."""

    def __init__(self, raw: str):
        self.raw = raw

    def open(self, *, encoding: str):
        return io.StringIO(self.raw)


def _read_document(path: Path) -> _Document:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Unsafe information library.")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DOCUMENT_BYTES:
            raise ValueError("Invalid information library.")
        raw = source.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("Invalid information library.")
    return _Document(raw.decode("utf-8"))


def read_information_library(root: Path | None) -> dict:
    """Load validated records from an explicitly selected, existing answer store."""
    status = "unconfigured" if root is None else "unavailable"
    if root is not None:
        try:
            path = Path(root).expanduser().absolute()
            if ".." in path.parts or any(part.is_symlink() for part in (path, *path.parents)):
                raise ValueError("Unsafe information library.")
            store = helper.Store(path)
            store.answers_path = _read_document(path / "answers.json")
            records = store._load_answers_document()["answers"]
            profile_path = path / "profile.json"
            preferences = {}
            if profile_path.exists() or profile_path.is_symlink():
                store.profile_path = _read_document(profile_path)
                profile = store._load_profile_document()["profile"]
                preferences = profile.get("preferences", {})
                if not isinstance(preferences, dict):
                    raise ValueError("Invalid information preferences.")
            records = [records[key] for key in sorted(records)]
            return {
                "status": "available",
                "revision": digest({"records": records, "preferences": preferences}),
                "records": records,
                "preferences": preferences,
            }
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError, helper.StoreError):
            pass
    return {
        "status": status,
        "revision": digest({"status": status}),
        "records": [],
        "preferences": {},
    }


def condition_information_binding(requirement, application, library):
    """Bind a manual clarification only to its reviewed, applicable factual meaning."""
    information = condition_from_library(requirement, application, library)
    fact = (information or {}).get("fact")
    if fact not in {
        *ADDITIONAL_LANGUAGE_FACTS,
        "language_english_fluent",
        "additional_language_skills",
    }:
        return None
    return {
        "fact": fact,
        "revision": digest(
            _information_projection(
                application,
                library,
                ADDITIONAL_LANGUAGE_FACTS if fact == "additional_language_skills" else (fact,),
                include_unconfirmed=True,
            )
        ),
    }


def condition_from_library(
    requirement: dict | str, application: dict, library: dict
) -> dict | None:
    """Resolve only reviewed language grammar against confirmed, applicable facts."""
    text = requirement.get("text", "") if isinstance(requirement, dict) else requirement
    if not isinstance(text, str):
        return None
    if " ".join(text.casefold().split()).rstrip(".!?") == "have additional language skills":
        return _additional_languages(application, library)
    if isinstance(requirement, dict) and requirement.get("hard_condition") is False:
        return None
    if " ".join(text.casefold().split()).rstrip(".!?") == "be fluent in english":
        return _english_fluency(application, library)
    saved = _saved_qualification(text, application, library)
    if saved is not None:
        return saved
    recognized = [
        (language, minimum)
        for language in ("French", "German")
        if (minimum := _language_requirement(text, language))
    ]
    languages = [
        language
        for language, names in (("French", r"French|法语"), ("German", r"German|德语"))
        if re.search(names, text, re.I)
    ]
    names = r"(?:French|German|法语|德语)"
    simple_threshold = re.fullmatch(
        rf"\s*(?:(?:at least|minimum)\s+)?(?:{names}\s+"
        r"(?:(?:proficiency|level|CEFR|of)\s+)*(?:(?:at least|minimum)\s+)?[ABC][12]"
        rf"|[ABC][12]\s+(?:level\s+)?(?:in\s+)?{names})"
        r"\s+(?:is\s+)?(?:required|mandatory)\s*[.!]?\s*",
        text,
        re.I,
    )
    if (
        not simple_threshold
        and languages
        and (
            recognized
            or (
                isinstance(requirement, dict)
                and requirement.get("hard_condition") is True
                and re.search(r"[ABC][12]", text, re.I)
            )
        )
    ):
        return {
            "status": "needs_input",
            "explanation": "本条不属于已审核的单语言最低等级条件，需核对完整要求。",
            "fact": f"language_{languages[0].lower()}_cefr"
            if len(languages) == 1
            else "language_cefr",
            "references": [],
        }
    if not recognized:
        return None
    if len(recognized) > 1:
        return {
            "status": "needs_input",
            "explanation": "本条包含多个语言条件，需分别核对。",
            "fact": "language_cefr",
            "references": [],
        }
    language, minimum = recognized[0]
    fact = f"language_{language.lower()}_cefr"
    records = []
    if library.get("status") == "available":
        records = applicable_answers(library.get("records", []), fact, application)
    references = [{"key": record["key"], "revision": digest(record)} for record in records]
    values = {
        record["value"].strip().upper()
        for record in records
        if isinstance(record.get("value"), str)
    }
    result = {"fact": fact, "references": references}
    if not records:
        return {
            **result,
            "status": "needs_input",
            "explanation": "通用信息库尚无适用且已确认的语言信息，需补充。",
        }
    if (
        len(values) != 1
        or not values.issubset(LEVELS)
        or any(not isinstance(record.get("value"), str) for record in records)
    ):
        return {
            **result,
            "status": "needs_input",
            "explanation": "通用信息库中的适用语言信息有冲突或缺少明确 CEFR 等级，需确认。",
        }
    if minimum not in LEVELS:
        return {
            **result,
            "status": "needs_input",
            "explanation": "岗位未给出明确 CEFR 最低等级，需确认语言条件。",
        }
    supported = LEVELS.index(next(iter(values))) >= LEVELS.index(minimum)
    return {
        **result,
        "status": "supported" if supported else "conflict",
        "explanation": (
            "通用信息库中适用且已确认的语言能力达到本条最低要求。"
            if supported
            else "通用信息库中适用且已确认的语言能力低于本条最低要求。"
        ),
    }


def _additional_languages(application, library):
    """An explicit non-English level proves this bounded existential condition."""
    levels, references = [], []
    for fact, label in zip(ADDITIONAL_LANGUAGE_FACTS, ("法语", "德语", "日语"), strict=True):
        records = applicable_answers(
            library.get("records", []) if library.get("status") == "available" else [],
            fact,
            material_information_context(application),
            include_unconfirmed=True,
        )
        references.extend({"key": row["key"], "revision": digest(row)} for row in records)
        values = {
            row["value"].strip().upper() for row in records if isinstance(row.get("value"), str)
        }
        if (
            records
            and all(row.get("state") == "confirmed" for row in records)
            and all(isinstance(row.get("value"), str) for row in records)
            and len(values) == 1
            and values.issubset(LEVELS)
        ):
            levels.append(f"{label} {next(iter(values))}")
    return {
        "fact": "additional_language_skills",
        "references": references,
        "status": "supported" if levels else "needs_input",
        "explanation": "已确认其他语言：" + "、".join(levels) + "。"
        if levels
        else "尚无适用且无冲突的已确认其他语言等级。",
    }


def _english_fluency(application, library):
    """Reuse explicit fluency answers; credentials and documentary prose are not answers."""
    fact = "language_english_fluent"
    records = applicable_answers(
        library.get("records", []) if library.get("status") == "available" else [],
        fact,
        material_information_context(application),
        include_unconfirmed=True,
    )
    result = {
        "fact": fact,
        "references": [{"key": row["key"], "revision": digest(row)} for row in records],
    }
    meanings = {
        "yes": True,
        "true": True,
        "fluent": True,
        "professional": True,
        "professional working proficiency": True,
        "熟练，professional 的水平": True,
        "熟练，professional的水平": True,
        "no": False,
        "false": False,
        "not fluent": False,
    }
    values = [
        row["value"]
        if isinstance(row.get("value"), bool)
        else meanings.get(" ".join(row["value"].casefold().split()))
        if isinstance(row.get("value"), str)
        else None
        for row in records
    ]
    if (
        not records
        or any(row.get("state") != "confirmed" for row in records)
        or None in values
        or len(set(values)) != 1
    ):
        return {
            **result,
            "status": "needs_input",
            "explanation": "英语流利度尚无适用的明确确认，或现有答案有冲突、已撤回。",
        }
    return {
        **result,
        "status": "supported" if values[0] else "conflict",
        "explanation": "已复用信息库中适用且已确认的英语流利度答案。"
        if values[0]
        else "已确认的英语流利度答案与本条要求冲突。",
    }


def _saved_qualification(text, application, library):
    """Review bounded factual conditions without rewriting their documentary analysis."""
    normalized = " ".join(text.casefold().split()).rstrip(".")
    # The confirmed facts describe an in-progress PhD, so only a requirement naming one applies.
    student = re.fullmatch(
        r"be an? (?P<penultimate>penultimate or )?final[- ]year student"
        r" (?:completing|pursuing) an? (?P<degrees>[a-z' ,.]*)degree",
        normalized,
    )
    if student and not re.search(r"\bph\.?d\b|\bdoctoral\b", student["degrees"]):
        student = None
    quantitative = re.fullmatch(
        r"pursue an advanced degree in a quantitative field such as (?P<fields>[a-z ,]+)",
        normalized,
    )
    internship = re.fullmatch(
        r"be available for an? (?P<low>[1-9][0-9]?)(?:\s*[–-]\s*(?P<high>[1-9][0-9]?))?"
        r"[- ]month internship starting in (?P<year>20[0-9]{2})"
        r"(?: at an eligible [a-z0-9&' .-]+ location)?",
        normalized,
    )
    if not (student or quantitative or internship):
        return None
    fact = (
        "internship_availability"
        if internship
        else "education_quantitative_degree"
        if quantitative
        else "education_student_status"
    )
    required = (
        ("internship_start", "internship_duration", "preferred_location")
        if internship
        else ("academic_degree", "graduation_date")
    )
    references, values = [], {}
    context = material_information_context(application)
    for name in required:
        records = applicable_answers(
            library.get("records", []) if library.get("status") == "available" else [],
            name,
            context,
            include_unconfirmed=True,
        )
        references.extend({"key": row["key"], "revision": digest(row)} for row in records)
        distinct = {row["value"].strip() for row in records if isinstance(row.get("value"), str)}
        if (
            not records
            or any(row.get("state") != "confirmed" for row in records)
            or len(distinct) != 1
            or any(not isinstance(row.get("value"), str) for row in records)
        ):
            values[name] = None
        else:
            values[name] = next(iter(distinct))
    result = {"fact": fact, "references": references}
    if any(value is None for value in values.values()):
        return {
            **result,
            "status": "needs_input",
            "explanation": "已有确认信息缺少适用值或存在冲突，暂不能核验本条。",
        }
    now = datetime.now(UTC)
    current_month = now.year * 12 + now.month

    def month(value):
        match = re.fullmatch(r"(0[1-9]|1[0-2])/(20[0-9]{2})", value)
        return int(match[2]) * 12 + int(match[1]) if match else None

    supported = False
    if internship:
        start = month(values["internship_start"])
        year = int(internship["year"])
        low = int(internship["low"])
        high = int(internship["high"] or low)
        duration = re.fullmatch(r"([1-9][0-9]?) months?", values["internship_duration"], re.I)
        location = values["preferred_location"].strip().casefold()
        # An eligible location names a place, not immigration status; only this job's own
        # recorded location can show the confirmed preference is eligible.
        supported = (
            start is not None
            and start >= current_month
            and year * 12 + 1 <= start <= year * 12 + 12
            and duration is not None
            and low <= int(duration[1]) <= high
            and bool(location)
            and location
            in {
                part.strip()
                for part in re.split(r"[,;/|]", str(application.get("location") or "").casefold())
            }
        )
        explanation = ""
        if supported:
            explanation = (
                f"已确认：{values['internship_start']} 开始，实习 {values['internship_duration']}，"
                f"首选 {values['preferred_location']}，符合本条时间与地点要求。"
            )
    else:
        graduation = month(values["graduation_date"])
        degree = re.fullmatch(
            r"Ph\.?D\.? \(in progress; expected graduation ([A-Za-z]+) (20[0-9]{2})\)",
            values["academic_degree"],
            re.I,
        )
        months = [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
        degree_month = (
            int(degree[2]) * 12 + months.index(degree[1].casefold()) + 1
            if degree and degree[1].casefold() in months
            else None
        )
        supported = (
            graduation is not None and graduation == degree_month and graduation > current_month
        )
        if student:
            # "Penultimate or final-year" allows two remaining years; "final-year" only one.
            window = 24 if student["penultimate"] else 12
            supported = supported and graduation - current_month <= window
            explanation = "已确认博士在读及预计毕业时间，属于毕业前两年的在读学生。"
        else:
            profile = library.get("education_profile") or {}
            source = profile.get("source") or {}
            fields = [
                field.strip()
                for field in re.split(r",|\bor\b|\band\b", quantitative["fields"])
                if field.strip()
            ]
            matching = [
                (index, row)
                for index, row in enumerate(profile.get("education", []))
                if isinstance(row, dict)
                and re.match(r"ph\.?d\.?\b", str(row.get("degree", "")), re.I)
                and str(row.get("degree", "")).casefold().rpartition(" in ")[2].strip() in fields
                and degree is not None
                and re.search(
                    rf"expected\s*{degree[1][:3]}(?:[a-z]*)\s*{degree[2]}\b",
                    str(row.get("period", "")),
                    re.I,
                )
            ]
            supported = (
                supported
                and len(matching) == 1
                and bool(source.get("id") and source.get("revision"))
            )
            if supported:
                references.append(
                    {
                        "source_id": source["id"],
                        "source_name": source.get("source_name"),
                        "revision": source["revision"],
                        "locator": f"profile.education[{matching[0][0]}]",
                    }
                )
            explanation = "已确认博士在读；学历库中对应领域的博士记录支持量化领域高等学位要求。"
    return {
        **result,
        "status": "supported" if supported else "needs_input",
        "explanation": explanation
        if supported
        else "已有记录尚不能完整支持本条条件，保留待核验状态。",
    }


def read_information_history(root: Path, *, key: str | None = None) -> list[dict]:
    """Read private correction receipts; answers.json remains the current fact store."""
    history = Path(root) / ".tomorrowstar-answer-history"
    if any(part.is_symlink() for part in (history, *history.parents)):
        raise PortalDataError("unsafe-backup", "信息历史目录不能使用符号链接。")
    events = []
    for path in history.glob("*/requested.json"):
        if path.is_symlink() or path.parent.is_symlink():
            raise PortalDataError("unsafe-backup", "信息历史记录不能使用符号链接。")
        event = json.loads(path.read_text(encoding="utf-8"))
        if key is not None and event["key"] != key:
            continue
        applied = path.parent / "applied.json"
        if applied.is_symlink():
            raise PortalDataError("unsafe-backup", "信息历史记录不能使用符号链接。")
        if applied.is_file():
            event.update(json.loads(applied.read_text(encoding="utf-8")), status="applied")
        else:
            event["status"] = "needs_recheck"
        events.append(event)
    return sorted(events, key=lambda event: (event["at"], event["event_id"]))


def put_information_answer(
    store: helper.Store,
    incoming: dict,
    *,
    expected_revision: str | None = None,
    actor: str = "user",
    source: str = "explicit-answer-update",
    remember_sensitive: bool = False,
) -> dict:
    """Reuse the pinned writer, retaining prior bytes before correction or withdrawal."""
    if not all(isinstance(value, str) and value.strip() for value in (actor, source)):
        raise PortalDataError("invalid-source", "请保留更正来源和操作者。")
    root = Path(store.root).absolute()
    if any(part.is_symlink() for part in (root, *root.parents)):
        raise PortalDataError("unsafe-backup", "信息目录不能使用符号链接。")
    store.initialize()
    descriptor = os.open(
        root / ".tomorrowstar-information-write.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        raw = _read_document(root / "answers.json").raw.encode("utf-8")
        document = json.loads(raw)
        key = incoming.get("key") or helper.answer_key(
            incoming.get("question", ""), incoming.get("scope", {})
        )
        before = document["answers"].get(key)
        if expected_revision is not None and (
            before is None or digest(before) != expected_revision
        ):
            raise PortalDataError("answer_conflict", "答案已变更，请重新载入。", 409)
        history = root / ".tomorrowstar-answer-history"
        if history.is_symlink():
            raise PortalDataError("unsafe-backup", "信息历史目录不能使用符号链接。")
        history.mkdir(exist_ok=True)
        event_dir = history / str(uuid4())
        event_dir.mkdir()
        backup = event_dir / "before.json"
        event = {
            "event_id": event_dir.name,
            "at": datetime.now(UTC).isoformat(),
            "key": key,
            "actor": actor,
            "source": source,
            "before_revision": digest(before) if before else None,
            "backup": backup.relative_to(root).as_posix(),
        }
        _write_file(backup, raw, replace=False)
        _write_file(
            event_dir / "requested.json",
            json.dumps(event, ensure_ascii=False).encode("utf-8"),
            replace=False,
        )
        if _read_document(root / "answers.json").raw.encode("utf-8") != raw:
            raise PortalDataError("answer_conflict", "信息库已变更，请重新载入。", 409)
        record = store.put_answer(incoming, remember_sensitive=remember_sensitive)
        event["after_revision"] = digest(record)
        _write_file(
            event_dir / "applied.json",
            json.dumps(event, ensure_ascii=False).encode("utf-8"),
            replace=False,
        )
        return record
    finally:
        os.close(descriptor)
