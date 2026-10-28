"""Read explicitly captured human-accepted material as documentary sources only."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy

from .career_portal_data import PortalDataError, _document_fingerprint
from .validation.hashing import record_digest as digest

MANIFEST_PATH = "sources/retained-resume-sources.json"


def fact_source_projection(snapshot):
    """Keep accepted wording as an archive, never as a newly observed fact.

    This projection does not interpret or strip historical TeX. Unconverted
    wording stays import-pending even when some cited facts already exist.
    Education alone can reuse the independently recorded profile fields.
    """
    projected = deepcopy(snapshot)
    items = []
    retained = projected.setdefault("retained_materials", [])
    for item in projected.get("items", []):
        legacy = item.get("source_kind") in {"accepted_resume", "legacy_tex"}
        education = None
        if item.get("source_kind") == "education":
            try:
                payload = json.loads(item.get("text", ""))
            except (TypeError, ValueError):
                payload = None
            if isinstance(payload, dict) and "accepted_latex" in payload:
                education = payload
        if not legacy and education is None:
            items.append(item)
            continue
        archived = deepcopy(item) | {"import_status": "import_pending"}
        if education is not None:
            correction = item.get("education_profile_correction", {})
            entry = correction.get("profile_record", education.get("profile_record"))
            if isinstance(entry, dict):
                # The retained reader verifies an explicit correction chain.
                # Its corrected profile is authoritative; the old accepted TeX
                # and old degree status remain untouched in the archive.
                fact = deepcopy(item)
                fact["text"] = json.dumps({"profile_record": entry}, ensure_ascii=False)
                fact["education_profile_sha256"] = digest(entry)
                items.append(fact)
                archived["import_status"] = "projected"
        if archived not in retained:
            retained.append(archived)
    projected["items"] = items
    projected.pop("revision", None)
    projected["revision"] = digest(projected)
    return projected


def _invalid():
    return PortalDataError(
        "resume_reuse_invalid", "已接受材料的来源绑定不能核验，请保留原始证据。", 409
    )


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compact_json_document(text):
    """Remove only JSON whitespace, preserving numeric literals and string bytes."""
    try:
        json.loads(text, object_pairs_hook=_object)
    except ValueError:
        return text
    return re.sub(
        r'"(?:\\.|[^"\\])*"|[ \t\r\n]+',
        lambda match: match[0] if match[0].startswith('"') else "",
        text,
    )


def _capture(catalog, capture):
    from .application_prism_review import _read

    if (
        not isinstance(capture, dict)
        or set(capture) != {"path", "sha256"}
        or not isinstance(capture["path"], str)
        or not isinstance(capture["sha256"], str)
        or re.fullmatch(r"[a-f0-9]{64}", capture["sha256"]) is None
    ):
        raise _invalid()
    relative = capture["path"]
    path = catalog.root / relative
    if (
        not relative
        or relative.startswith("/")
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or not relative.split("/")[0].startswith(".")
        or not path.is_relative_to(catalog.root)
    ):
        raise _invalid()
    before = _document_fingerprint(path, catalog.root)
    raw = _read(path, 2_000_000)
    if _document_fingerprint(path, catalog.root) != before or _sha(raw) != capture["sha256"]:
        raise _invalid()
    return raw


def explicit_profile_correction(
    catalog, profile_source, *, previous_revision=None, previous_entry_sha256=None, locator=None
):
    """Read an applied user correction chain back to an exact prior profile revision."""
    record = catalog.get_evidence(profile_source["id"])
    if record["revision"] != profile_source["revision"]:
        return None
    revision = record["revision"]
    events = []
    for event in reversed(record["history"]):
        if event.get("after_revision") != revision:
            continue
        if (
            event.get("status") != "applied"
            or event.get("actor") != "user"
            or event.get("source_name") != profile_source["source_name"]
            or not event.get("source")
        ):
            return None
        raw = _capture(catalog, {"path": event["backup"], "sha256": event["before_revision"]})
        from .application_prism_review import _read

        saved = {}
        for name in ("requested", "applied"):
            path = catalog.root / event["backup"]
            path = path.parent / (name + ".json")
            identity = _document_fingerprint(path, catalog.root)
            encoded = _read(path, 2_000_000)
            if _document_fingerprint(path, catalog.root) != identity:
                return None
            saved[name] = encoded.decode("utf-8")
        expected = {key: value for key, value in event.items() if key != "status"}
        if saved["requested"] != saved["applied"] or json.loads(saved["requested"]) != expected:
            return None
        events.insert(0, event | saved | {"before_content": raw.decode("utf-8")})
        revision = event["before_revision"]
        profile = json.loads(raw)
        match = re.fullmatch(r"profile\.education\[(\d+)\]", locator or "")
        if revision == previous_revision or (
            previous_entry_sha256 is not None
            and match is not None
            and int(match[1]) < len(profile.get("education", []))
            and digest(profile["education"][int(match[1])]) == previous_entry_sha256
        ):
            return {"profile": profile, "events": events}
    return None


def _visible(text):
    text = re.sub(r"(?m)(?<!\\)%.*$", "", text)
    text = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", text)
    return "".join(
        value
        for value in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(value)
    )


def _entry_heading_period(text):
    entries = list(re.finditer(r"\\entry\s*\{", text))
    if len(entries) != 1:
        raise _invalid()
    cursor, values = entries[0].end() - 1, []
    for _ in range(2):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            raise _invalid()
        start, depth = cursor + 1, 1
        cursor += 1
        while cursor < len(text) and depth:
            if text[cursor] in "{}" and text[cursor - 1] != "\\":
                depth += 1 if text[cursor] == "{" else -1
            cursor += 1
        if depth:
            raise _invalid()
        values.append(text[start : cursor - 1])
    return values


def _education_core_matches(text, entry):
    """Bind documentary credential cores; extra narrative detail is not a new fact."""
    if any(
        not isinstance(entry.get(key), str) for key in ("degree", "institution", "period", "detail")
    ):
        return False
    heading, period = _entry_heading_period(text)

    def institution(value):
        tokens = re.findall(r"\w+", _visible(value))
        return {
            "university" if token == "universitat" else token
            for token in tokens
            if token not in {"of", "the", "de", "des"}
        }

    def level(value):
        value = _visible(value).replace(".", "")
        patterns = {
            "doctor": r"\b(?:phd|doctorate|doctor of philosophy)\b",
            "master": r"\b(?:m2|msc|master(?:s)?)\b",
            "bachelor": r"\b(?:bsc|bachelor(?:s)?)\b",
        }
        found = {name for name, pattern in patterns.items() if re.search(pattern, value)}
        return next(iter(found)) if len(found) == 1 else None

    def status(value):
        value = _visible(value)
        not_awarded = r"\bnot(?:\s+yet)?\s+awarded\b"
        affirmative = re.sub(not_awarded, " ", value)
        for clause in re.split(r"[.;\n]", affirmative):
            if re.search(r"\bawarded\b", clause) and re.search(
                r"\b(?:not|never|no|without|hasn['’]t|isn['’]t|wasn['’]t)\b", clause
            ):
                raise _invalid()
        ongoing = bool(
            re.search(r"\bin[\s-]+progress\b|\bcandidate\b|\bexpected\b|" + not_awarded, value)
        )
        completed = bool(re.search(r"\bawarded\b|\bcompleted\b|\bgraduated\b", affirmative))
        return ongoing, completed

    def dates(value):
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
        aliases = {name: name[:3] for name in months} | {name[:3]: name[:3] for name in months}
        tokens = re.findall(r"\d+|[a-z]+", _visible(value))
        result = []
        for token in tokens:
            if token in aliases:
                result.append(aliases[token])
            elif re.fullmatch(r"(?:19|20)\d{2}", token):
                result.append(token)
            elif token not in {"expected", "present", "current", "ongoing", "to", "from"}:
                return None
        return result if any(re.fullmatch(r"\d{4}", value) for value in result) else None

    def expected_completion(value):
        value = _visible(value)
        found = set()
        for marker in re.finditer(r"\bexpected\b", value):
            match = re.match(
                r"\s*(?:(?:completion|graduation)(?:\s+date)?|date)?\s*"
                r"(?:[:\-]\s*)?(?:(?:in|on|by)\s+)?"
                r"(?P<date>(?:[a-z]+\s+)?(?:19|20)\d{2})\b",
                value[marker.end() :],
            )
            if match is None or dates(match["date"]) is None:
                return None
            found.add(tuple(dates(match["date"])))
        return found if len(found) <= 1 else None

    recorded_level, accepted_level = level(entry["degree"]), level(text)
    recorded_text = " ".join(entry[key] for key in ("degree", "period", "detail"))
    recorded_status = status(recorded_text)
    accepted_status = status(text)
    return (
        bool(institution(heading))
        and institution(heading) == institution(entry["institution"])
        and recorded_level is not None
        and recorded_level == accepted_level
        and recorded_status[0] == accepted_status[0]
        and not (any(recorded_status) and all(recorded_status))
        and not (any(accepted_status) and all(accepted_status))
        and not (recorded_status[1] and accepted_status[0])
        and not (accepted_status[1] and recorded_status[0])
        and dates(period) is not None
        and dates(period) == dates(entry["period"])
        and expected_completion(recorded_text) is not None
        and expected_completion(recorded_text) == expected_completion(text)
    )


def retained_material_sources(catalog, manifest_document, profile, profile_source):
    """Fail closed on stale captures; directory names alone never confer acceptance."""
    try:
        return _retained_material_sources(catalog, manifest_document, profile, profile_source)
    except (KeyError, IndexError, TypeError, ValueError, OSError, PortalDataError) as error:
        raise _invalid() from error


def _retained_material_sources(catalog, document, profile, profile_source):
    from .application_flow import ApplicationFlowService
    from .application_full_latex import _body, _education_lines

    current = catalog._record(catalog.root / MANIFEST_PATH, "source", detail=True)
    if any(
        current[key] != document.get(key) for key in ("id", "source_name", "revision", "content")
    ):
        raise _invalid()
    manifest = json.loads(document["content"], object_pairs_hook=_object)
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schema", "captures", "groups"}
        or manifest["schema"] != "retained-resume-sources/v1"
        or not isinstance(manifest["captures"], dict)
        or set(manifest["captures"]) != {"task", "source", "pdf", "approval"}
        or not isinstance(manifest["groups"], list)
        or not manifest["groups"]
    ):
        raise _invalid()
    raw = {key: _capture(catalog, capture) for key, capture in manifest["captures"].items()}
    task = json.loads(raw["task"], object_pairs_hook=_object)
    approval = json.loads(raw["approval"], object_pairs_hook=_object)
    if not isinstance(task, dict):
        raise _invalid()
    receipt = task.get("material_acceptance")
    if (
        not isinstance(receipt, dict)
        or not ApplicationFlowService.valid_material_acceptance(task)
        or task.get("materials_confirmed") is not True
        or task.get("status") != "materials_ready"
        or receipt["source_sha256"] != _sha(raw["source"])
        or receipt["pdf_sha256"] != _sha(raw["pdf"])
        or not raw["pdf"].startswith(b"%PDF-")
        or receipt["approval_record"]["sha256"] != _sha(raw["approval"])
        or not isinstance(approval, dict)
        or approval.get("schema") != "material15-human-material-acceptance/v1"
        or approval.get("actor") != "human-user"
        or approval.get("decision") != "accept_exact_revised_pdf_content_and_layout"
        or not isinstance(approval.get("scope"), list)
        or not {"complete_pdf_content", "pdf_layout"}.issubset(approval["scope"])
        or approval.get("tex_sha256") != receipt["source_sha256"]
        or approval.get("pdf_sha256") != receipt["pdf_sha256"]
        or approval.get("at") != receipt["approval_record"]["accepted_at"]
        or approval.get("user_reply") != receipt["approval_record"]["statement"]
    ):
        raise _invalid()
    source = raw["source"].decode("utf-8")
    prefix, body, _suffix = _body(source)
    lines = source.splitlines(keepends=True)
    body_offset = prefix.count("\n")
    body_lines = set(range(body_offset + 1, body_offset + len(body.splitlines()) + 1))
    education_lines = {line + body_offset for line in _education_lines(body)}
    used, education_bindings, result = set(), set(), []
    fields = {
        "title",
        "start_line",
        "end_line",
        "source_kind",
        "context_source_ids",
        "education_profile_locator",
        "education_profile_sha256",
    }
    for index, group in enumerate(manifest["groups"]):
        if (
            not isinstance(group, dict)
            or set(group) != fields
            or not isinstance(group["title"], str)
            or not group["title"].strip()
            or type(group["start_line"]) is not int
            or type(group["end_line"]) is not int
            or not 1 <= group["start_line"] <= group["end_line"] <= len(lines)
            or group["source_kind"] not in {"education", "accepted_resume"}
            or not isinstance(group["context_source_ids"], list)
            or any(
                not isinstance(value, str) or not value.strip()
                for value in group["context_source_ids"]
            )
            or len(set(group["context_source_ids"])) != len(group["context_source_ids"])
        ):
            raise _invalid()
        span = set(range(group["start_line"], group["end_line"] + 1))
        is_education = group["source_kind"] == "education"
        if (
            not span.issubset(body_lines)
            or used & span
            or (is_education and not span.issubset(education_lines))
            or (not is_education and span & education_lines)
        ):
            raise _invalid()
        used.update(span)
        text = "".join(lines[group["start_line"] - 1 : group["end_line"]])
        if is_education:
            locator = group["education_profile_locator"]
            match = re.fullmatch(r"profile\.education\[(\d+)\]", locator or "")
            if (
                match is None
                or not isinstance(profile_source, dict)
                or locator in education_bindings
            ):
                raise _invalid()
            entry = profile["education"][int(match[1])]
            correction = None
            if digest(entry) != group["education_profile_sha256"]:
                correction = explicit_profile_correction(
                    catalog,
                    profile_source,
                    previous_entry_sha256=group["education_profile_sha256"],
                    locator=locator,
                )
                if correction is not None:
                    entry = correction["profile"]["education"][int(match[1])]
            if (
                not isinstance(entry, dict)
                or digest(entry) != group["education_profile_sha256"]
                or not _education_core_matches(text, entry)
            ):
                raise _invalid()
            education_bindings.add(locator)
            text = json.dumps({"accepted_latex": text, "profile_record": entry}, ensure_ascii=False)
        elif (
            group["education_profile_locator"] is not None
            or group["education_profile_sha256"] is not None
        ):
            raise _invalid()
        original = "".join(lines[group["start_line"] - 1 : group["end_line"]])
        result.append(
            {
                "source_id": document["id"] + f":groups[{index}]",
                "source_name": document["source_name"],
                "source_revision": document["revision"],
                "locator": f"groups[{index}]",
                "source_kind": group["source_kind"],
                "title": group["title"],
                "text": text,
                "attribution": "Documented accepted education; no capability assessment"
                if is_education
                else (
                    "Previously human-accepted resume wording; "
                    "responsibility limited to cited text; no mastery assessment"
                ),
                "resume_eligible": True,
                "rewrite_allowed": not is_education,
                "context_source_ids": group["context_source_ids"],
                "source_receipt_revision": receipt["revision"],
                "retained_receipt_revision": receipt["revision"],
                "retained_source_sha256": receipt["source_sha256"],
                "retained_start_line": group["start_line"],
                "retained_end_line": group["end_line"],
                "retained_text_sha256": _sha(original.encode()),
                "origin_locators": {
                    key: capture["path"] for key, capture in manifest["captures"].items()
                },
                "education_profile_source_id": profile_source["id"] if is_education else None,
                "education_profile_locator": group["education_profile_locator"],
                "education_profile_sha256": group["education_profile_sha256"],
                **(
                    {
                        "education_profile_correction": {
                            "profile_record": profile["education"][int(match[1])],
                            "profile_source": profile_source,
                            "locator": locator,
                        }
                    }
                    if is_education and correction is not None
                    else {}
                ),
            }
        )
    return result
