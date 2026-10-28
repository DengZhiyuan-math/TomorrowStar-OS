"""Explicit, source-bound import plans for the existing experience store.

The caller supplies structured facts and exact source mappings. This module does
not parse presentation syntax, infer career facts, write files or call models.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field

from .application_resume_content import Contract, ExperienceFacts, Text
from .career_experiences import _json_bytes, material_identity
from .career_portal_data import PortalDataError


class ImportPart(Contract):
    id: Text
    source_pointer: Text
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: Text
    disposition: Literal["fact", "presentation", "duplicate", "unresolved"]
    fact_ids: list[Text] = Field(default_factory=list)
    source_ref: Text | None = None
    reason: Text
    duplicate_of: Text | None = None


class ExperienceImportRequest(Contract):
    schema_version: Literal["experience-import/v1"]
    expected_revision: Text
    content: ExperienceFacts
    parts: list[ImportPart]


def pending_materials(experience):
    """Return active raw material whose current text or context is not covered."""
    snapshots = (experience.get("migration") or {}).get("source_snapshots", {})
    return [
        material
        for index, material in enumerate(experience["materials"])
        if material["role"] not in {"history", "generated"}
        and snapshots.get(f"/materials/{index}/text")
        != {
            "text_sha256": hashlib.sha256(material["text"].encode("utf-8")).hexdigest(),
            "context_sha256": hashlib.sha256(_json_bytes(material)).hexdigest(),
        }
    ]


def _import_sources(previous):
    result = (
        {}
        if "content" in previous
        else {
            "/body": (
                previous["body"],
                {key: previous.get(key) for key in ("candidate_id", "title", "metadata")},
            )
        }
    )
    pending_ids = {material["id"] for material in pending_materials(previous)}
    for index, material in enumerate(previous.get("materials", [])):
        if material["role"] not in {"generated", "history"} and (
            "content" not in previous or material["id"] in pending_ids
        ):
            result[f"/materials/{index}/text"] = (material["text"], material)
    return result


def _duplicate_context(pointer, context, quote):
    if pointer == "/body":
        context = {
            key: value
            for key, value in (context.get("metadata") or {}).items()
            if key
            not in {
                "import_status",
                "source_revision",
                "manual_fields",
                "unavailable_sources",
                "aliases",
                "links",
                "related_ids",
            }
        }
    return {**context, "text": quote}


def prepare_experience_import(previous: dict, request: dict) -> dict:
    """Preview exact mappings; publication belongs to CareerLibrary's CAS save."""
    incoming = ExperienceImportRequest.model_validate(request)
    if "content" not in previous and not isinstance(previous.get("body"), str):
        raise ValueError("An existing experience is required for import.")
    if incoming.expected_revision != previous["revision"]:
        raise PortalDataError("revision-conflict", "经历已更新，请刷新后重试。", 409)
    if incoming.content.candidate_id != previous["candidate_id"]:
        raise ValueError("Import candidate identity does not match the existing experience.")
    content = incoming.content.model_dump(mode="json")
    content["revision"] = hashlib.sha256(
        _json_bytes({key: value for key, value in content.items() if key != "revision"})
    ).hexdigest()
    inherited_facts = {}
    if "content" in previous:
        baseline = ExperienceFacts.model_validate(previous["content"]).model_dump(mode="json")
        if any(
            content[key] != value
            for key, value in baseline.items()
            if key not in {"revision", "facts", "sources"}
        ):
            raise ValueError("Incremental import must preserve saved experience fields.")
        new_sources = {source["id"]: source for source in content["sources"]}
        new_facts = {fact["id"]: fact for fact in content["facts"]}
        if any(new_sources.get(source["id"]) != source for source in baseline["sources"]):
            raise ValueError("Incremental import must preserve saved sources.")
        for fact in baseline["facts"]:
            updated = new_facts.get(fact["id"], {})
            if any(
                updated.get(key) != value for key, value in fact.items() if key != "source_refs"
            ) or not set(fact["source_refs"]) <= set(updated.get("source_refs", [])):
                raise ValueError("Incremental import must preserve saved facts and references.")
            inherited_facts[fact["id"]] = fact
    sources = _import_sources(previous)
    ranges = {pointer: [] for pointer in sources}
    unresolved = []
    facts = {fact.id: fact for fact in incoming.content.facts}
    source_ids = {source.id for source in incoming.content.sources}
    identifiers = [part.id for part in incoming.parts]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Import part IDs must be unique.")
    by_id = {part.id: part for part in incoming.parts}
    for part in incoming.parts:
        if len(part.fact_ids) != len(set(part.fact_ids)) or not set(part.fact_ids) <= facts.keys():
            raise ValueError("Import mapping contains duplicate or unknown fact IDs.")
        if part.disposition in {"fact", "duplicate"}:
            if not part.fact_ids or part.source_ref not in source_ids:
                raise ValueError("A fact mapping needs its delivered fact and source IDs.")
            if any(part.source_ref not in facts[fid].source_refs for fid in part.fact_ids):
                raise ValueError("Import mapping source is not referenced by the mapped fact.")
        if part.disposition == "duplicate":
            original = by_id.get(part.duplicate_of)
            if (
                original is None
                or original.disposition != "fact"
                or original.source_pointer not in sources
                or part.source_pointer not in sources
                or " ".join(original.quote.split()) != " ".join(part.quote.split())
                or set(original.fact_ids) != set(part.fact_ids)
            ):
                raise ValueError("A duplicate must match its explicit original fact mapping.")
            original_context = _duplicate_context(
                original.source_pointer, sources[original.source_pointer][1], original.quote
            )
            duplicate_context = _duplicate_context(
                part.source_pointer, sources[part.source_pointer][1], part.quote
            )
            if material_identity(original_context) != material_identity(duplicate_context):
                raise ValueError("A duplicate must retain the original responsibility context.")
        elif part.duplicate_of is not None:
            raise ValueError("Only duplicates can name an original mapping.")
        if part.disposition == "presentation" and (part.fact_ids or part.source_ref):
            raise ValueError("Presentation-only mappings cannot claim fact coverage.")
        if part.source_pointer not in sources:
            raise ValueError("Import source pointer is not in the previous record.")
        text = sources[part.source_pointer][0]
        if not 0 <= part.start < part.end <= len(text) or text[part.start : part.end] != part.quote:
            raise ValueError("Import source quote or range does not match the previous record.")
        ranges[part.source_pointer].append((part.start, part.end))
        if part.disposition == "unresolved":
            unresolved.append(part.model_dump(mode="json"))
    for pointer, spans in ranges.items():
        text = sources[pointer][0]
        cursor = 0
        for start, end in sorted(spans) + [(len(text), len(text))]:
            if start < cursor:
                raise ValueError("Import source ranges overlap.")
            if text[cursor:start].strip():
                unresolved.append(
                    {
                        "source_pointer": pointer,
                        "start": cursor,
                        "end": start,
                        "quote": text[cursor:start],
                        "reason": "unmapped_source_text",
                    }
                )
            cursor = end
    mapped = set(inherited_facts) | {
        identifier
        for part in incoming.parts
        if part.disposition == "fact"
        for identifier in part.fact_ids
    }
    unresolved.extend(
        {"fact_id": identifier, "reason": "unmapped_fact"}
        for identifier in facts
        if identifier not in mapped
    )
    bound_pairs = {
        (identifier, ref)
        for identifier, fact in inherited_facts.items()
        for ref in fact["source_refs"]
    } | {
        (identifier, part.source_ref)
        for part in incoming.parts
        if part.disposition in {"fact", "duplicate"}
        for identifier in part.fact_ids
    }
    unresolved.extend(
        {"fact_id": identifier, "source_ref": ref, "reason": "unmapped_fact_source"}
        for identifier, fact in facts.items()
        if identifier in mapped
        for ref in fact.source_refs
        if (identifier, ref) not in bound_pairs
    )
    return {
        "schema_version": "experience-import-plan/v1",
        "candidate_id": previous["candidate_id"],
        "expected_revision": previous["revision"],
        "ready": not unresolved,
        "content": content,
        "migration": {
            "schema_version": "experience-import-coverage/v1",
            "from_revision": previous["revision"],
            "parts": [part.model_dump(mode="json") for part in incoming.parts],
            "source_snapshots": {
                **(previous.get("migration") or {}).get("source_snapshots", {}),
                **{
                    pointer: {
                        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "context_sha256": hashlib.sha256(_json_bytes(context)).hexdigest(),
                    }
                    for pointer, (text, context) in sources.items()
                },
            },
            "coverage_complete": not unresolved,
        },
        "unresolved": unresolved,
    }
