"""Literal source records, shared model projections and quote-span anchoring.

Readers, comparison and writing consume this same Interface. There is no model
execution, library read, scoring or workflow transition in this module.
"""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy

from .application_input_limits import context_limits
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest


def structured_fact(source):
    context = source.get("record_context", {})
    return isinstance(context, dict) and all(
        context.get(key) for key in ("fact_id", "experience_id", "content_revision", "source_refs")
    )


def source_records(snapshot):
    if "material_packet_sources" in snapshot:
        packet = snapshot.get("material_packet", {})
        if (
            packet.get("status") != "complete"
            or packet.get("revision")
            != digest({key: value for key, value in packet.items() if key != "revision"})
            or snapshot["material_packet_sources"] != packet.get("sources")
        ):
            raise PortalDataError("retrieval_execution_incomplete", "固定资料包不能完整核验。", 409)
        order = [
            item["source_id"]
            for item in snapshot["items"]
            if item["source_id"] in packet["sources"]
        ]
        order.extend(sorted(packet["sources"].keys() - set(order)))
        return {source_id: deepcopy(packet["sources"][source_id]) for source_id in order}
    documents = {document["id"]: document for document in snapshot["documents"]}
    sources = {
        item["source_id"]: deepcopy(item)
        | {
            "available": bool(documents.get(item["evidence_id"], {}).get("available"))
            and documents[item["evidence_id"]].get("revision") == item["source_revision"],
            "match_eligible": item["resume_eligible"]
            or (
                item.get("source_kind") == "confirmed_information"
                and bool(item.get("confirmed_information"))
            ),
            **(
                {
                    "documentary_only": True,
                    "resume_eligible": False,
                }
                if item.get("source_kind") == "education"
                else {}
            ),
            "design_only": bool(
                item.get("design_only")
                or re.match(r"(?:Defined|Designed|Proposed|Specified)\b", item["text"])
            ),
        }
        for item in snapshot["items"]
    }
    profile_source = snapshot.get("profile_source")
    profile = snapshot.get("profile")
    if profile_source and profile:
        document = documents.get(profile_source["id"], {})
        if document.get("available") and document.get("revision") == profile_source["revision"]:
            aliases = {
                "side_projects": "sideProjects",
                "open_source": "openSourceContributions",
                "master_thesis": "masterThesis",
            }
            prefix = (
                "$.profile" if profile_source["source_name"].endswith("site-content.json") else "$"
            )
            records = [("location", profile.get("location")), ("title", profile.get("title"))]
            records.extend(
                (f"{category}[{index}]", entry)
                for category in (
                    "education",
                    "experience",
                    "research",
                    "master_thesis",
                    "side_projects",
                    "open_source",
                )
                for index, entry in enumerate(profile.get(category, []))
            )
            for path, entry in records:
                if not entry:
                    continue
                locator = "profile." + path
                source_id = f"{profile_source['id']}:{locator}"
                context = (
                    {
                        key: entry[key]
                        for key in (
                            "role",
                            "organization",
                            "period",
                            "name",
                            "title",
                            "location",
                            "status",
                        )
                        if entry.get(key)
                    }
                    if isinstance(entry, dict)
                    else {}
                )
                planned = bool(
                    re.search(
                        r"\b(?:incoming|planned)(?!\s+end)\b",
                        " ".join(str(context.get(key, "")) for key in ("role", "period", "status")),
                        re.I,
                    )
                )
                category = path.split("[", 1)[0]
                document_path = aliases.get(category, category) + path[len(category) :]
                document_locator = prefix + "." + document_path
                if isinstance(entry, str):
                    fields = [(document_locator, entry)]
                elif category == "education":
                    fields = [
                        (document_locator + "." + key, entry.get(key, ""))
                        for key in ("degree", "institution", "period", "detail")
                    ]
                elif category in {"side_projects", "open_source"}:
                    fields = [(document_locator + ".description", entry["description"])]
                else:
                    fields = [(document_locator + ".detail", entry.get("detail", ""))]
                    fields.extend(
                        (document_locator + f".points[{index}]", point)
                        for index, point in enumerate(entry.get("points", []))
                    )
                text, segments = "", []
                for field, value in fields:
                    if not value:
                        continue
                    if text:
                        text += "\n"
                    segments.append(
                        {
                            "start": len(text),
                            "end": len(text) + len(value),
                            "document_locator": field,
                            "text": value,
                        }
                    )
                    text += value
                if not text:
                    continue
                specific = {
                    "source_id": source_id,
                    "evidence_id": profile_source["id"],
                    "source_name": profile_source["source_name"],
                    "source_revision": profile_source["revision"],
                    "locator": locator,
                    "document_locator": segments[0]["document_locator"],
                    "text": text,
                    "quote_segments": segments,
                    "available": True,
                    "record_context": context,
                    "planned_only": planned,
                    "attribution": "Editorial statement; review required",
                    "review_status": "documentary",
                    "match_eligible": not planned,
                    "resume_eligible": False,
                    "rewrite_allowed": False,
                    "design_only": False,
                    "documentary_only": True,
                }
                if source_id in sources:
                    # Keep the catalog's selection and responsibility boundaries;
                    # the same record now includes its role/date/status context.
                    source = sources[source_id]
                    source.update(
                        {
                            key: specific[key]
                            for key in (
                                "text",
                                "document_locator",
                                "record_context",
                                "planned_only",
                                "documentary_only",
                                "quote_segments",
                            )
                        }
                    )
                    source["match_eligible"] = source["match_eligible"] and not planned
                else:
                    sources[source_id] = specific
    if snapshot.get("application_library_policy") == "trusted-library/v1":
        for source in sources.values():
            source["application_trusted"] = True
            source["match_eligible"] = source["available"]
    return sources


_TRUSTED_RECEIPT_ONLY = {
    "source_name",
    "locator",
    "document_locator",
    "review_status",
    "match_eligible",
    "rewrite_allowed",
    "design_only",
    "documentary_only",
    "application_trusted",
}


def model_source(source):
    """Send evidence and responsibility boundaries; keep internal hashes in the receipt."""
    keys = {
        "source_id",
        "source_name",
        "text",
        "locator",
        "document_locator",
        "record_context",
        "attribution",
        "boundaries",
        "review_status",
        "match_eligible",
        "resume_eligible",
        "rewrite_allowed",
        "design_only",
        "documentary_only",
        "planned_only",
        "source_kind",
        "application_trusted",
        "original_text_chars",
        "context_range",
    }
    if source.get("application_trusted") is True:
        # The program admitted this trusted-library source and keeps these flags and
        # file locators for its own checks; the model reads evidence and boundaries.
        # resume_eligible stays: only native citations list resume sources in the schema.
        keys -= _TRUSTED_RECEIPT_ONLY
        if source.get("source_kind") == "confirmed_information":
            # Every confirmed fact shares this boundary, which the prompt already states.
            keys -= {"attribution", "boundaries"}
    result = {key: value for key, value in source.items() if key in keys}
    if source.get("application_trusted") is True:
        result = {
            key: value
            for key, value in result.items()
            if not (
                key == "planned_only" and value is not True or key == "boundaries" and not value
            )
        }
    if source.get("confirmed_information"):
        result["confirmed_information"] = {"fact": source["confirmed_information"]["fact"]}
    return result


def model_sources(sources):
    """Share canonical JSON metadata without changing native facts or replay hashes."""
    rows, experiences, scopes = [], {}, {}
    experience_keys, scope_keys, referenced, trusted_experiences = {}, {}, {}, set()
    fact_keys = {"fact_id", "source_refs", "responsibility", "status", "scope"}
    for source in sources:
        row = deepcopy(model_source(source))
        context = row.get("record_context", {})
        if not (
            isinstance(context, dict)
            and isinstance(context.get("sources"), list)
            and all(
                context.get(key)
                for key in ("fact_id", "experience_id", "content_revision", "source_refs")
            )
        ):
            rows.append(row)
            continue
        metadata = {
            key: value
            for key, value in context.items()
            if key not in fact_keys | {"content_revision", "experience_revision"}
        }
        identity = digest(metadata)
        if identity not in experience_keys:
            name = "experience-" + str(len(experiences) + 1)
            experience_keys[identity] = name
            experiences[name] = metadata
            referenced[name] = set()
        name = experience_keys[identity]
        referenced[name].update(context["source_refs"])
        trusted = source.get("application_trusted") is True
        if trusted:
            trusted_experiences.add(name)
        compact = {
            key: context[key]
            for key in fact_keys - ({"fact_id", "source_refs"} if trusted else set())
            if key in context and key != "scope"
        }
        compact["experience_context_ref"] = name
        if "scope" in context:
            scope = context["scope"]
            if scope not in scope_keys:
                scope_name = "scope-" + str(len(scopes) + 1)
                scope_keys[scope] = scope_name
                scopes[scope_name] = scope
            compact["scope_ref"] = scope_keys[scope]
        row["record_context"] = compact
        for key in ("source_name", "locator", "document_locator"):
            row.pop(key, None)
        if row.get("attribution") == "Responsibility: " + context.get("responsibility", ""):
            row.pop("attribution")
        if row.get("boundaries") == (
            "Status: " + context.get("status", "") + "; scope: " + context.get("scope", "")
        ):
            row.pop("boundaries")
        rows.append(row)
    for name, context in experiences.items():
        if name in trusted_experiences:
            # Source locators are provenance the program reattaches after the answer.
            context.pop("sources")
            if context.get("experience_id") == context.get("candidate_id"):
                context.pop("experience_id")
            continue
        context["sources"] = [
            definition
            for definition in context["sources"]
            if definition.get("id") in referenced[name]
        ]
    return {"sources": rows} | (
        {"experience_contexts": experiences, "scope_contexts": scopes} if experiences else {}
    )


_DEFAULT_NOTES = {"Recorded experience fact.", "Experience background; not the user's activity."}


def matching_view(sources):
    """Group facts under their Experience: one header, its facts, background and notes."""
    projected = model_sources(sources)
    if "experience_contexts" not in projected:
        return projected
    experiences = {
        name: {
            key: value
            for key, value in context.items()
            if key in {"title", "role", "organization", "location", "start", "end"}
            and value is not None
        }
        | {"facts": [], "context": [], "notes": []}
        for name, context in projected["experience_contexts"].items()
    }
    others = []
    for row in projected["sources"]:
        context = row.pop("record_context", {})
        name = context.get("experience_context_ref")
        if name not in experiences:
            others.append(row | ({"record_context": context} if context else {}))
            continue
        experience = experiences[name]
        entry = {key: value for key, value in row.items() if key != "text"}
        if context.get("responsibility") != "third_party":
            entry["responsibility"] = context.get("responsibility")
        entry |= {"status": context.get("status"), "text": row["text"]}
        note = projected["scope_contexts"].get(context.get("scope_ref"))
        if note and note not in _DEFAULT_NOTES:
            if note not in experience["notes"]:
                experience["notes"].append(note)
            entry["note"] = experience["notes"].index(note) + 1
        bucket = "context" if context.get("responsibility") == "third_party" else "facts"
        experience[bucket].append(entry)
    return {
        "experiences": [
            {key: value for key, value in experience.items() if value != []}
            for experience in experiences.values()
        ],
        "sources": others,
    }


_PRESENTATION_WRAPPER = re.compile(
    r"(?<!\\)\\(?:textbf|textit|emph|textrm|texttt|textnormal)\{([^\\{}$%\n]+)\}"
)


def _presentation_source(source):
    text = source["text"]
    return (
        source.get("source_kind") == "accepted_resume"
        and bool(source.get("retained_receipt_revision"))
        and bool(source.get("retained_source_sha256"))
        and source.get("retained_text_sha256") == hashlib.sha256(text.encode()).hexdigest()
        and len(text) <= context_limits()["match_context_bytes"]
    )


def _presentation_quote_span(source, quote):
    """Map allowlisted, plain TeX presentation wrappers to original character offsets."""
    text = source["text"]
    if not _presentation_source(source):
        return None
    # Existing prose helpers also remove comments, layout and other commands. This
    # citation mapping deliberately removes only these single plain-text wrappers.
    visible, starts, ends = [], [], []
    offset = 0
    for match in _PRESENTATION_WRAPPER.finditer(text):
        visible.extend(text[offset : match.start()])
        starts.extend(range(offset, match.start()))
        ends.extend(range(offset + 1, match.start() + 1))
        content = match.group(1)
        visible.extend(content)
        starts.extend(range(match.start(1), match.end(1)))
        ends.extend(range(match.start(1) + 1, match.end(1) + 1))
        starts[-len(content)] = match.start()
        ends[-1] = match.end()
        offset = match.end()
    if not offset:
        return None
    visible.extend(text[offset:])
    starts.extend(range(offset, len(text)))
    ends.extend(range(offset + 1, len(text) + 1))
    normalized = "".join(visible)
    start = normalized.find(quote)
    if start < 0 or normalized.find(quote, start + 1) >= 0:
        return None
    return starts[start], ends[start + len(quote) - 1]


def quoted_source(source, quote):
    """Anchor a literal quote to one visible source field and its sentence context."""
    start = source["text"].find(quote)
    end = start + len(quote)
    proposed_quote = None
    if start < 0 and quote.strip():
        span = _presentation_quote_span(source, quote)
        if span is not None:
            start, end = span
            proposed_quote, quote = quote, source["text"][start:end]
    if not quote.strip() or start < 0:
        raise PortalDataError("match_source_invalid", "引用片段不在该来源已读取的原文内。", 409)
    result = deepcopy(source) | {"quote": quote, "quote_start": start, "quote_end": end}
    if proposed_quote is not None:
        result.update(
            proposed_quote=proposed_quote, quote_match_policy="latex-presentation-literal/v1"
        )
    text, offset = source["text"], 0
    if "quote_segments" in source:
        segment = next(
            (
                part
                for part in source["quote_segments"]
                if part["start"] <= start and end <= part["end"]
            ),
            None,
        )
        if segment is None:
            raise PortalDataError(
                "match_source_invalid", "请分别引用具体字段，不能跨字段拼接引文。", 409
            )
        text, offset = segment["text"], segment["start"]
        result["document_locator"] = segment["document_locator"]
        result["field_quote_start"] = start - offset
        result["field_quote_end"] = end - offset
        if "source_start" in segment:
            result["quote_start"] = segment["source_start"] + start - offset
            result["quote_end"] = segment["source_start"] + end - offset
            result["field_quote_start"] += segment.get("field_start", 0)
            result["field_quote_end"] += segment.get("field_start", 0)
    sentences = list(re.finditer(r".+?(?:(?<=[.!?。！？])(?=\s)|\n|$)", text, re.S))
    context = " ".join(
        part.group()
        for part in sentences
        if part.start() < end - offset and start - offset < part.end()
    )
    result["quote_context"] = context or text
    reviewed_context = (
        _PRESENTATION_WRAPPER.sub(r"\1", result["quote_context"])
        if _presentation_source(source)
        else result["quote_context"]
    )
    result["planned_only"] = bool(
        source.get("planned_only")
        or re.search(
            r"\b(?:plan(?:ned|s|ning)?\s+to|will\b|"
            r"not\s+(?:yet\b|implemented|completed|built|developed|trained|deployed|published))\b"
            r"|计划|尚未实施|拟开发",
            reviewed_context,
            re.I,
        )
    )
    return result
