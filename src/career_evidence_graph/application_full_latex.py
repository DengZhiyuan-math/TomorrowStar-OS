"""Evidence-bound complete LaTeX versions, without compilation or review authority."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .application_draft import resume_language_policy, review_findings
from .application_information import (
    CONTACT_FACTS,
    applicable_answers,
    fact_for,
    material_information_context,
)
from .application_prism import archive_sources, validate_archive
from .career_portal_data import PortalDataError
from .codex_cli import CodexCLIError
from .resume_presentation import (
    PRESENTATION_INSTRUCTIONS,
    PRESENTATION_POLICY_VERSION,
    validate_resume_presentation,
)
from .validation.hashing import record_digest as digest
from .validation.models import CodexCLIConfig

ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
# A complete CV includes the base and its body lines as well as factual sources.
# Bound its final UTF-8 argument separately from the smaller analysis request.
MAX_PROMPT_BYTES = 128_000

BUSINESS_FIRST_INSTRUCTIONS = """Sources marked application_trusted are accepted career or
information library facts. Do not reassess their credibility, require an audit or
certificate, or downgrade self-reported proficiency. Missing research skill scores
and editorial/audit status are not application restrictions. Preserve the recorded
facts, personal/team roles, unknown responsibilities and planned/completed status;
do not invent results, responsibilities, scores or exam certificates.
When job_brief is present, reuse its fixed business objective, outputs, atomic requirements
and scoring framework. Do not reinterpret the JD or modify the framework. Otherwise:
First understand the employer's business objective and the
work outputs or decisions this role contributes to, using the actual JD. Then select
and organize evidenced experiences by their contribution to those outputs. Treat
mathematics, quantitative analysis, AI and programming as methods whose relevance
depends on that objective, not as standalone keyword matches. Distinguish direct
domain evidence from transferable research or engineering methods; do not invent
domain experience, financial results or responsibilities to close a gap. Derive the
headline, summary, experience order and space allocation from this reasoning rather
than inheriting the base CV's role positioning. In the experience handoff, the main
Codex orchestrator owns editable global headline, summary and skills groups: list
their indexes in organization_plan.positioning_group_indexes, record the actual author
in positioning_writer_id, and provide their actual
evidence-cited LaTeX in configure's groups. These groups are separate from experience
writers; a summary_focus string alone does not update the CV. Keep fixed identity and
education in separate groups. The pre-section header is protected, including macro-based
identity. Positioning citations require actual-read support notes from experience writers;
the final reviewer must be independent of both experience writers and the positioning author.
Never use positioning to bypass protected text.
Fixed education and unaffected manual
edits retain their existing protections. Review the whole CV for this business
alignment, not just the relevance of individual bullets. If a protected accepted
header or manual summary conflicts with the role positioning, record the conflict
and reject the candidate for revision; do not silently approve inherited framing
or bypass identity and manual-edit protections. When stronger business
evidence is absent from the selected sources, identify the actual missing facts.
When material_packet is present, reuse its fixed facts, source context and locators;
do not repeat retrieval. Request a specific supplemental read only for a genuinely
missing fact. Otherwise use the existing analysis source locators before writing.
Do not silently accept a keyword-led set.
"""


def _application_usable(source):
    """Application libraries are accepted facts; research audit state is separate."""
    if source.get("confirmation_conflicts"):
        return False
    if source.get("application_trusted") is True:
        # Application-only answers must not become employer-facing resume content.
        return source.get("source_kind") != "confirmed_information" or bool(
            source.get("resume_eligible")
        )
    return bool(
        source.get("resume_eligible")
        and source.get("attribution")
        not in {None, "", "Unknown", "Editorial statement; review required"}
    )


def _application_rewrite_allowed(source):
    return bool(
        source.get("rewrite_allowed", True)
        or source.get("application_trusted") is True
        and source.get("source_kind") not in {"identity", "education", "accepted_resume"}
        and not source.get("retained_receipt_revision")
        and _application_usable(source)
    )


def _invalid(message="完整LaTeX生成结果不能核验，请保留本次记录。"):
    return PortalDataError("resume_latex_invalid", message, 409)


def _body(text):
    begin = list(re.finditer(r"\\begin\{document\}(?:\r?\n)?", text))
    end = list(re.finditer(r"\\end\{document\}", text))
    if len(begin) != 1 or len(end) != 1 or begin[0].end() >= end[0].start():
        raise _invalid("底稿须含一个完整document正文，不能将片段当作完整简历。")
    return text[: begin[0].end()], text[begin[0].end() : end[0].start()], text[end[0].start() :]


def _contact_latex(value):
    return (
        value.replace("\\", r"\textbackslash{}")
        .replace("_", r"\_")
        .replace("%", r"\%")
        .replace("&", r"\&")
        .replace("#", r"\#")
    )


def _replace_contact(text, fact, old, new):
    """A name shared with summary text has no unique contact locator."""
    if fact in {"name", "first_name", "last_name"}:
        pattern = re.compile(r"(?<!\w)" + re.escape(old) + r"(?!\w)")
        count = len(pattern.findall(text))
        if count > 1:
            raise _invalid("姓名在页眉中没有唯一可核验位置，请保留人工源核对。")
    else:
        pattern = re.compile(r"(?<![\w.+@/-])" + re.escape(old) + r"(?![\w.@/-])")
    return pattern.subn(lambda _match: _contact_latex(new), text)


def _identity_facts(references):
    result = {}
    for source in references:
        if source.get("source_kind") != "identity":
            continue
        values = json.loads(source["text"])
        for key in CONTACT_FACTS:
            if isinstance(values.get(key), str):
                result[key] = values[key]
        for link in values.get("links", []):
            href = link["href"]
            if href.startswith("mailto:"):
                result["email"] = href[7:]
            elif href.startswith("tel:"):
                result["phone"] = href[4:]
            elif "github.com/" in href:
                result["github_url"] = href
            elif "linkedin.com/" in href:
                result["linkedin_url"] = href
    return result


def _language_sources(application, information_library):
    """Expose applicable language facts without private answer text or scope metadata."""
    from .application_information import information_context

    sources = []
    for fact in information_context(application, information_library)["facts"]:
        name = fact["fact"]
        if fact["status"] != "confirmed" or not name.startswith("language_"):
            continue
        parts = name.split("_")
        if len(parts) != 3 or parts[2] not in {"cefr", "fluent"}:
            continue
        text = json.dumps(
            {"language": parts[1].capitalize(), "proficiency": fact["value"]},
            ensure_ascii=False,
            sort_keys=True,
        )
        binding = {"fact": name, "references": deepcopy(fact["references"])}
        revision = digest({"text": text, "binding": binding})
        sources.append(
            {
                "source_id": "resume-language:" + revision,
                "source_name": "information-library-languages",
                "source_revision": revision,
                "locator": name,
                "source_kind": "language",
                "title": parts[1].capitalize() + " proficiency",
                "text": text,
                "attribution": "User-provided language proficiency",
                "application_trusted": True,
                "resume_eligible": True,
                "rewrite_allowed": True,
                "language_information_binding": binding,
            }
        )
    return sources


def _sources(snapshot, information_library, application, *, original=None, retained_draft=None):
    # This legacy generator still needs exact accepted wording and education
    # templates. Read their archive explicitly, without putting TeX back into
    # the analysis facts or mutating the recorded source snapshot.
    sources_by_id = {source["source_id"]: deepcopy(source) for source in snapshot["items"]}
    for archived in snapshot.get("retained_materials", []):
        if archived.get("source_kind") in {"accepted_resume", "education"} and archived.get(
            "retained_receipt_revision"
        ):
            sources_by_id[archived["source_id"]] = deepcopy(archived)
    sources = list(sources_by_id.values())
    if original is not None:
        prefix, body, _ = _body(original)
        first_section = re.search(r"\\(?:section|cvsection)\*?(?:\[[^\]]*\])?\{", body)
        header_end = prefix.count("\n") + (
            body[: first_section.start()].count("\n") if first_section else 0
        )
        lines = original.splitlines(keepends=True)
        inherited = {
            source["source_id"]: source
            for source in (retained_draft or {}).get("generation_sources", [])
            if source.get("source_kind") == "identity" and source.get("retained_receipt_revision")
        }
        for source in sources:
            start, end = source.get("retained_start_line"), source.get("retained_end_line")
            parent = inherited.get(source["source_id"])
            if parent is not None and all(
                source.get(key) == parent.get(key)
                for key in (
                    "source_name",
                    "locator",
                    "source_revision",
                    "retained_receipt_revision",
                    "retained_source_sha256",
                    "retained_start_line",
                    "retained_end_line",
                    "retained_text_sha256",
                )
            ):
                entry = json.loads(parent["text"])
                if (
                    source.get("source_kind") == "accepted_resume"
                    and entry.get("accepted_latex") == source.get("text")
                    and hashlib.sha256(source["text"].encode()).hexdigest()
                    == source.get("retained_text_sha256")
                ):
                    source.update(
                        source_kind="identity", text=parent["text"], rewrite_allowed=False
                    )
                    continue
            if (
                source.get("source_kind") == "accepted_resume"
                and source.get("retained_receipt_revision")
                and source.get("retained_source_sha256")
                == hashlib.sha256(original.encode()).hexdigest()
                and type(start) is int
                and type(end) is int
                and prefix.count("\n") < start <= end <= header_end
                and (text := "".join(lines[start - 1 : end])) == source.get("text")
                and hashlib.sha256(text.encode()).hexdigest() == source.get("retained_text_sha256")
            ):
                # A human-accepted, exact pre-section slice is fixed document
                # context, not an experience selected for an agent to rewrite.
                source.update(
                    source_kind="identity",
                    text=json.dumps({"accepted_latex": text}, ensure_ascii=False),
                    rewrite_allowed=False,
                )
    for source in sources:
        correction = source.pop("education_profile_correction", None)
        if correction is not None:
            source_id = source["source_id"]
            source.clear()
            source.update(
                source_id=source_id,
                text=json.dumps(correction["profile_record"], ensure_ascii=False),
                source_revision=correction["profile_source"]["revision"],
                source_name=correction["profile_source"]["source_name"],
                locator=correction["locator"],
                source_kind="education",
                title=correction["profile_record"]["degree"],
                attribution="Documented education corrected by user; no capability assessment",
                resume_eligible=True,
                rewrite_allowed=False,
            )
    profile = snapshot.get("profile")
    origin = snapshot.get("profile_source")
    if profile and origin:
        identity = {key: profile[key] for key in ("name", "title", "location", "links")}
        sources.append(
            {
                "source_id": origin["id"] + ":profile.identity",
                "source_name": origin["source_name"],
                "source_revision": origin["revision"],
                "locator": "profile.identity",
                "source_kind": "identity",
                "title": "Profile identity",
                "text": json.dumps(identity, ensure_ascii=False),
                "attribution": "Profile identity; no capability assertion",
                "resume_eligible": True,
                "rewrite_allowed": False,
            }
        )
    if profile and origin:
        for index, entry in enumerate(profile.get("education", [])):
            sources.append(
                {
                    "source_id": origin["id"] + f":profile.education[{index}]",
                    "source_name": origin["source_name"],
                    "source_revision": origin["revision"],
                    "locator": f"profile.education[{index}]",
                    "source_kind": "education",
                    "title": entry["degree"],
                    "text": json.dumps(entry, ensure_ascii=False),
                    "attribution": "Documented education; no capability assessment",
                    "resume_eligible": True,
                    "rewrite_allowed": False,
                }
            )
    if profile and origin:
        for category in ("experience", "research", "master_thesis"):
            for index, entry in enumerate(profile.get(category, [])):
                context_fields = {
                    key: entry[key]
                    for key in ("role", "organization", "period", "name", "location", "supervisor")
                    if entry.get(key)
                }
                if not context_fields:
                    continue
                locator = f"profile.{category}[{index}].context"
                sources.append(
                    {
                        "source_id": origin["id"] + ":" + locator,
                        "source_name": origin["source_name"],
                        "source_revision": origin["revision"],
                        "locator": locator,
                        "source_kind": "career_context",
                        "title": "Career context",
                        "text": json.dumps(context_fields, ensure_ascii=False),
                        "attribution": "Documented career context; no contribution attribution",
                        "resume_eligible": True,
                        "rewrite_allowed": True,
                    }
                )
    records = []
    if information_library.get("status") == "available":
        for fact in CONTACT_FACTS:
            for record in applicable_answers(
                information_library.get("records", []),
                fact,
                material_information_context(application),
            ):
                if (
                    isinstance(record.get("value"), str)
                    and record["value"].strip()
                    and isinstance(record.get("key"), str)
                ):
                    records.append((fact, record))
    # Application contact details belong to the information library. Keep the
    # career profile intact, but do not offer its superseded contact fallback.
    selected_facts = {fact for fact, _record in records}
    for source in sources:
        if source.get("source_kind") != "identity":
            continue
        identity = json.loads(source["text"])
        if "name" in selected_facts or {"first_name", "last_name"} <= selected_facts:
            identity.pop("name", None)

        def contact_fact(href):
            if href.startswith("mailto:"):
                return "email"
            if href.startswith("tel:"):
                return "phone"
            if "github.com/" in href:
                return "github_url"
            if "linkedin.com/" in href:
                return "linkedin_url"
            return None

        identity["links"] = [
            link
            for link in identity.get("links", [])
            if contact_fact(link["href"]) not in selected_facts
        ]
        source["text"] = json.dumps(identity, ensure_ascii=False)
    conflicts = {
        fact
        for fact, _record in records
        if len({record["value"] for candidate, record in records if candidate == fact}) > 1
    }
    if conflicts:
        for source in sources:
            if source.get("source_kind") == "identity":
                source["resume_eligible"] = False
                source["confirmation_conflicts"] = sorted(conflicts)
    for fact, record in records:
        conflicting = fact in conflicts
        sources.append(
            {
                "source_id": "answer:" + record["key"],
                "source_name": "information-library",
                "source_revision": digest(record),
                "locator": "answers." + record["key"],
                "source_kind": "identity",
                "title": record["question"],
                "text": json.dumps({fact: record["value"]}, ensure_ascii=False),
                "attribution": "Confirmed identity; no capability assertion",
                "resume_eligible": not conflicting,
                "rewrite_allowed": False,
                "confirmation_state": "confirmed",
                "scope": deepcopy(record["scope"]),
            }
        )
    for source in sources:
        if source.get("source_kind") == "identity" and source.get("retained_receipt_revision"):
            entry = json.loads(source["text"])
            entry.setdefault("accepted_contact_facts", _identity_facts(sources))
            source["text"] = json.dumps(entry, ensure_ascii=False)
    if snapshot.get("application_library_policy") == "trusted-library/v1":
        for source in sources:
            if source.get("source_kind") != "identity" or not source.get("confirmation_conflicts"):
                source["application_trusted"] = True
        sources.extend(_language_sources(application, information_library))
    return sources


def _prose_latex(text):
    """Ignore ordinary presentation arguments when comparing documentary literals."""
    text = re.sub(r"(?m)(?<!\\)%.*$", "", text)
    text = re.sub(r"\\(?:begin|end)\{[^}]+\}", "", text)
    text = re.sub(r"\\(?:fontsize|rule)\{[^}]*\}\{[^}]*\}", "", text)
    text = re.sub(
        r"\\(?:vspace|hspace|vskip|hskip|color|textcolor|fontfamily|setlength)\*?\{[^}]*\}",
        "",
        text,
    )
    return re.sub(r"\\\\\s*\[[^\]]*\]", "", text)


def _identity_matches(latex, references, *, strict_contacts=False):
    """Identity values cannot supply unrelated work or capability statements."""
    retained_headers = [
        source
        for source in references
        if source.get("source_kind") == "identity" and source.get("retained_receipt_revision")
    ]
    if retained_headers:
        accepted = []
        current = _identity_facts(references)
        for source in sorted(retained_headers, key=lambda row: row["retained_start_line"]):
            entry = json.loads(source["text"])
            text = entry.get("accepted_latex")
            if (
                not isinstance(text, str)
                or hashlib.sha256(text.encode()).hexdigest() != source["retained_text_sha256"]
            ):
                return False
            for key, old in entry.get("accepted_contact_facts", {}).items():
                new = current.get(key)
                if new is not None and new != old:
                    text, _ = _replace_contact(text, key, old, new)
            accepted.append(text)
        if _prose_latex(latex).strip() != _prose_latex("".join(accepted)).strip():
            return False
    values = []

    def strings(value):
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                strings(item)
        elif isinstance(value, list):
            for item in value:
                strings(item)

    for source in references:
        strings(json.loads(source["text"]))
    visible = _prose_latex(latex)
    verified_contacts = False
    if any(
        source.get("confirmation_state") == "confirmed"
        and fact_for(source.get("title", "")) in CONTACT_FACTS
        for source in references
    ):
        visible, observed = _contact_literals(visible)
        _, permitted = _contact_literals("\n".join(values), latex=False)
        if any(observed[kind] - permitted[kind] for kind in observed):
            if strict_contacts:
                raise _invalid("联系人或链接目标含未确认的字面值，请保留生成证据并核对。")
            return False
        verified_contacts = any(observed.values())
        visible = re.sub(r"\b(?:mailto|tel):", "", visible)
    visible = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", visible)
    tokens = set(re.findall(r"\w+", visible.casefold()))
    return bool(tokens or verified_contacts) and tokens <= set(
        re.findall(
            r"\w+",
            (
                " ".join(values)
                + " education academic qualifications background contact name location email phone"
                " github linkedin"
            ).casefold(),
        )
    )


def _contact_literals(text, *, latex=True):
    """Keep complete email/URL targets and phone digits, including href arguments."""
    if latex:
        text = re.sub(r"\\([#$%&_{}])", r"\1", _prose_latex(text))
    contacts = {"email": set(), "url": set(), "phone": set()}
    patterns = {
        "email": r"[^\s{}<>\\():;,\[\]]+@[^\s{}<>\\():;,\[\]]+",
        "url": (
            r"(?<![\w@])(?:https?://[^\s{}<>\\]+|"
            r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:/[^\s{}<>\\]*)?)"
        ),
        "phone": r"(?<!\w)\+?\d[\d \t().-]*\d(?!\w)",
    }
    for kind, pattern in patterns.items():

        def capture(match, kind=kind):
            literal = match[0].rstrip(".,;")
            if kind == "phone":
                literal = re.sub(r"\D", "", literal)
                if len(literal) < 7:
                    return match[0]
            contacts[kind].add(literal)
            return " "

        text = re.sub(pattern, capture, text)
    return text, contacts


def _current_contact_header(rewritten, references):
    """Render complete current contact facts without extending their claim scope."""
    confirmed = [
        source
        for source in references
        if source.get("confirmation_state") == "confirmed"
        and fact_for(source.get("title", "")) in CONTACT_FACTS
    ]
    if (
        not confirmed
        or any(source.get("source_kind") != "identity" for source in references)
        or any(not source.get("resume_eligible") for source in references)
        or not _identity_matches(rewritten, references)
    ):
        return False
    visible = " ".join(re.sub(r"\\([#$%&_{}])", r"\1", _prose_latex(rewritten)).split())
    _, contacts = _contact_literals(rewritten)
    return all(
        isinstance(value, str)
        and (
            re.sub(r"\D", "", value) in contacts["phone"]
            if fact == "phone"
            else " ".join(value.split()) in visible
        )
        for source in confirmed
        for fact, value in json.loads(source["text"]).items()
    )


def _identity_header_exceptions(original, rewritten, references, *, is_header):
    """Keep the generation and retained-editor header exceptions identical."""
    contact = bool(
        is_header and rewritten != original and _current_contact_header(rewritten, references)
    )
    formatting = bool(
        is_header
        and references
        and all(source.get("source_kind") == "identity" for source in references)
        and _identity_matches(original, references)
        and _prose_latex(original).strip() == _prose_latex(rewritten).strip()
    )
    return contact, formatting


def is_fixed_education_group(group):
    """Reuse documented unchanged education, without claiming human PDF acceptance."""
    from .application_group_review import unwrapped_group

    references = group.get("sources", [])
    return bool(
        group.get("content_policy") == "fixed_education"
        and group.get("disposition") == "include"
        and (
            unwrapped_group(group.get("original", ""))
            == unwrapped_group(group.get("rewritten", ""))
            or (
                (corrected := _corrected_education(group.get("original", ""), references))
                is not None
                and unwrapped_group(corrected) == unwrapped_group(group.get("rewritten", ""))
            )
        )
        and references
        and all(
            source.get("source_kind") == "education"
            and _application_usable(source)
            and source.get("rewrite_allowed") is False
            for source in references
        )
        and _education_matches(group["rewritten"], references)
    )


def _corrected_education(latex, references):
    """Apply only unique documentary field substitutions from applied user corrections."""
    previous = []
    corrections = []
    for source in references:
        proof = source.get("education_correction")
        if proof is None:
            previous.append(source)
            continue
        old = proof.get("previous_source", {}) if isinstance(proof, dict) else {}
        events = proof.get("events", []) if isinstance(proof, dict) else []
        revision = events[0].get("before_revision") if events else None
        if (
            not events
            or source.get("source_kind") != "education"
            or old.get("source_id") != source.get("source_id")
        ):
            return None
        before_record = json.loads(old["text"])
        if old.get("retained_receipt_revision"):
            before_record = before_record["profile_record"]
        locator = re.fullmatch(r"profile\.education\[(\d+)\]", source["locator"])
        if (
            locator is None
            or json.loads(events[0]["before_content"])["education"][int(locator[1])]
            != before_record
            or not old.get("retained_receipt_revision")
            and old.get("source_revision") != revision
        ):
            return None
        for event in events:
            expected = {
                key: value
                for key, value in event.items()
                if key not in {"status", "requested", "applied", "before_content"}
            }
            if (
                event.get("status") != "applied"
                or event.get("actor") != "user"
                or not event.get("source")
                or event.get("source_name") != source["source_name"]
                or event.get("before_revision") != revision
                or event.get("requested") != event.get("applied")
                or json.loads(event.get("requested", "null")) != expected
                or hashlib.sha256(event.get("before_content", "").encode()).hexdigest() != revision
            ):
                return None
            revision = event.get("after_revision")
        if revision != source["source_revision"]:
            return None
        previous.append(old)
        corrections.append((old, source))
    if not corrections or not _education_matches(latex, previous):
        return None
    updated = latex
    for old, current in corrections:
        before = json.loads(old["text"])
        if old.get("retained_receipt_revision"):
            before = before["profile_record"]
        after = json.loads(current["text"])
        accepted = _retained_education_text(old)
        fragments = (
            [accepted]
            if accepted is not None and latex.count(accepted) == 1
            else [chunk for chunk in _education_entries(latex) if _education_matches(chunk, [old])]
        )
        if len(fragments) != 1:
            return None
        original = fragments[0]
        replacements = {}
        for key in ("degree", "institution", "period", "detail"):
            if before[key] != after[key]:
                if not before[key] or original.count(before[key]) != 1:
                    return None
                if before[key] in replacements and replacements[before[key]] != after[key]:
                    return None
                replacements[before[key]] = after[key]
        if not replacements:
            return None
        changed = re.sub(
            "|".join(re.escape(value) for value in sorted(replacements, key=len, reverse=True)),
            lambda match, replacements=replacements: replacements[match[0]],
            original,
        )
        if updated.count(original) != 1:
            return None
        updated = updated.replace(original, changed)
    return updated if _education_matches(updated, references) else None


def _education_entries(latex):
    return re.split(r"(?=\\(?:entry|companyheading|resumeSubheading)\{)", latex)


def _retained_education_text(source):
    if not source.get("retained_receipt_revision"):
        return None
    try:
        entry = json.loads(source["text"])
        text = entry["accepted_latex"]
        if (
            source.get("source_kind") != "education"
            or not isinstance(text, str)
            or not text
            or hashlib.sha256(text.encode()).hexdigest() != source["retained_text_sha256"]
            or digest(entry["profile_record"]) != source["education_profile_sha256"]
        ):
            return None
        return text
    except (KeyError, TypeError, ValueError):
        return None


def _education_matches(latex, references):
    """Do not reuse a shortened credential that loses recorded status or qualifications."""
    if any(source.get("retained_receipt_revision") for source in references):
        from .application_group_review import unwrapped_group

        latex = unwrapped_group(latex)
        if not all(source.get("retained_receipt_revision") for source in references):
            remaining = latex
            for source in references:
                if source.get("retained_receipt_revision"):
                    accepted = _retained_education_text(source)
                    if accepted is None or remaining.count(accepted) != 1:
                        return False
                    remaining = remaining.replace(accepted, "", 1)
            return _education_matches(
                remaining,
                [source for source in references if not source.get("retained_receipt_revision")],
            )
        ordered = sorted(references, key=lambda source: source.get("retained_start_line", 0))
        fragments = [_retained_education_text(source) for source in ordered]
        return bool(
            all(fragments)
            and len({source.get("retained_source_sha256") for source in ordered}) == 1
            and len({source.get("retained_receipt_revision") for source in ordered}) == 1
            and all(
                left["retained_end_line"] + 1 == right["retained_start_line"]
                for left, right in zip(ordered, ordered[1:], strict=False)
            )
            and "".join(fragments) == latex
        )

    def words(text):
        visible = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", _prose_latex(text))
        return " ".join(re.findall(r"\w+", visible.casefold()))

    def fields_present(text, source):
        try:
            entry = json.loads(source["text"])
        except (KeyError, TypeError, ValueError):
            return False
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(key), str)
            for key in ("degree", "institution", "period", "detail")
        ):
            return False
        visible = " " + words(text) + " "
        return not any(
            " " + words(value) + " " not in visible
            for value in entry.values()
            if isinstance(value, str) and value.strip()
        )

    if not all(fields_present(latex, source) for source in references):
        return False
    if len(references) > 1:
        # Bind each credential within its own original entry, never to a union
        # of degree/institution/date tokens from different qualifications.
        chunks = _education_entries(latex)
        if len(chunks) <= 1 or any(
            sum(fields_present(chunk, source) for chunk in chunks) != 1 for source in references
        ):
            return False
    return _identity_matches(latex, references)


def _education_lines(body):
    """Recognize ordinary CV education sections so a model cannot relabel their sources."""
    headings = list(re.finditer(r"\\(?:section|cvsection)\*?(?:\[[^\]]*\])?\{([^{}\n]+)\}", body))
    fixed = set()
    for index, heading in enumerate(headings):
        if not re.search(
            r"\beducation(?:al)?\b|\bacademic\s+(?:background|qualifications|credentials)\b",
            heading[1],
            re.I,
        ):
            continue
        start = body[: heading.start()].count("\n") + 1
        end = (
            body[: headings[index + 1].start()].count("\n")
            if index + 1 < len(headings)
            else len(body.splitlines())
        )
        fixed.update(range(start, end + 1))
    return fixed


def _plan(output, original, sources, presentation_policy=None, *, retained_source=None):
    if presentation_policy not in {None, PRESENTATION_POLICY_VERSION}:
        raise _invalid("简历展示规则版本无法核验。")
    if (
        not isinstance(output, dict)
        or set(output) != {"groups", "limitations"}
        or not isinstance(output["groups"], list)
        or not output["groups"]
        or not isinstance(output["limitations"], list)
        or any(not isinstance(x, str) for x in output["limitations"])
    ):
        raise _invalid()
    prefix, body, suffix = _body(original)
    lines = body.splitlines(keepends=True)
    education_lines = _education_lines(body) if presentation_policy else set()
    first_section = re.search(r"\\(?:section|cvsection)\*?(?:\[[^\]]*\])?\{", body)
    header_end = body[: first_section.start()].count("\n") if first_section else 0
    covered = set()
    by_id = {source["source_id"]: source for source in sources}
    education_spans = {}
    for source in sources:
        if source.get("source_kind") == "education" and source.get("retained_receipt_revision"):
            text = _retained_education_text(source)
            if retained_source is not None:
                if (
                    text is None
                    or original.count(text) != 1
                    or retained_source.count(text) != 1
                    or original[: original.index(text)].splitlines(keepends=True)
                    and not original[: original.index(text)].endswith("\n")
                    or not text.endswith("\n")
                ):
                    raise _invalid("已接受教育原文在人工源中不能唯一核验，请保留原学历。")
                start = original[: original.index(text)].count("\n") + 1
                education_spans[source["source_id"]] = (start, start + text.count("\n") - 1)
                continue
            if (
                text is None
                or hashlib.sha256(original.encode()).hexdigest() != source["retained_source_sha256"]
                or "".join(
                    original.splitlines(keepends=True)[
                        source["retained_start_line"] - 1 : source["retained_end_line"]
                    ]
                )
                != text
            ):
                raise _invalid("已接受教育原文与当前完整底稿不符，请保留原证据。")
    groups = []
    for row in output["groups"]:
        if (
            not isinstance(row, dict)
            or set(row)
            != {"title", "start_line", "end_line", "source_ids", "latex", "disposition", "reason"}
            or type(row["start_line"]) is not int
            or type(row["end_line"]) is not int
            or not 1 <= row["start_line"] <= row["end_line"] <= len(lines)
            or not isinstance(row["source_ids"], list)
            or any(not isinstance(x, str) or x not in by_id for x in row["source_ids"])
            or len(set(row["source_ids"])) != len(row["source_ids"])
            or any(not isinstance(row[k], str) or not row[k].strip() for k in ("title", "reason"))
            or not isinstance(row["latex"], str)
            or not isinstance(row["disposition"], str)
            or row["disposition"] not in {"include", "omit", "verify"}
        ):
            raise _invalid()
        span = set(range(row["start_line"], row["end_line"] + 1))
        if span & covered:
            raise _invalid("原稿分组重叠，无法核对每段去向。")
        covered.update(span)
        original_group = "".join(lines[row["start_line"] - 1 : row["end_line"]])
        references = [deepcopy(by_id[x]) for x in row["source_ids"]]
        disposition = row["disposition"]
        reason = row["reason"]
        rewritten = row["latex"]
        fixed_education = False
        if presentation_policy:
            documented = [source for source in sources if source.get("source_kind") == "education"]
            # Recover exact documentary matches even if the model cites work
            # evidence for a fixed education entry or uses a different heading.
            matches = [
                s
                for s in documented
                if (_retained_education_text(s) or "\0") in original_group
                or any(
                    _education_matches(chunk, [s]) for chunk in _education_entries(original_group)
                )
            ]
            retained_matches = [s for s in matches if s.get("retained_receipt_revision")]
            if retained_matches and _education_matches(original_group, retained_matches):
                matches = retained_matches
            if matches and _education_matches(original_group, matches):
                references = deepcopy(matches)
        education_sources = references and all(
            source.get("source_kind") == "education" for source in references
        )
        from .application_group_review import _MARKER

        content_span = {
            line
            for line in span
            if lines[line - 1].strip() and not _MARKER.fullmatch(lines[line - 1])
        }
        education_scope = bool(
            content_span & education_lines
            or any(s.get("source_kind") == "education" for s in references)
        )
        exact_retained_education = bool(
            retained_source is not None
            and education_sources
            and all(source.get("retained_receipt_revision") for source in references)
            and _education_matches(original_group, references)
        )
        if (
            presentation_policy
            and content_span & education_lines
            and not content_span <= education_lines
            and not exact_retained_education
        ):
            raise _invalid("教育经历须单独分组，不能与按JD改写的工作内容混合。")
        if presentation_policy and education_sources:
            retained = [source for source in references if source.get("retained_receipt_revision")]
            retained_span = {
                line - prefix.count("\n")
                for source in retained
                for line in range(
                    education_spans.get(
                        source["source_id"],
                        (source["retained_start_line"], source["retained_end_line"]),
                    )[0],
                    education_spans.get(
                        source["source_id"],
                        (source["retained_start_line"], source["retained_end_line"]),
                    )[1]
                    + 1,
                )
            }
            corrected = _corrected_education(original_group, references)
            candidate = {
                "content_policy": "fixed_education",
                "disposition": "include",
                "original": original_group,
                "rewritten": corrected if corrected is not None else original_group,
                "sources": references,
            }
            fixed_education = bool(
                (
                    not retained
                    or span <= education_lines
                    and span == retained_span
                    or exact_retained_education
                    or corrected is not None
                )
                and is_fixed_education_group(candidate)
            )
            if fixed_education:
                rewritten, disposition = candidate["rewritten"], "include"
                reason = (
                    "Documented fixed education reused unchanged; no repeated factual confirmation"
                )
        if presentation_policy and education_scope and not fixed_education:
            disposition = "verify"
            if "fixed_education_source_unresolved: " not in reason:
                reason = "fixed_education_source_unresolved: " + reason
        # Missing source and unclear ownership are different from relevance omission.
        identity_only = references and all(
            x.get("source_kind") in {"identity", "education"}
            or x.get("source_kind") == "career_context"
            and not x.get("application_trusted")
            for x in references
        )
        # The old header is an exact slice of the archived base, retained for
        # comparison. Its old contact value is not an employer-facing assertion.
        current_contact_header, identity_format_only = _identity_header_exceptions(
            original_group,
            rewritten,
            references,
            is_header=row["end_line"] <= header_end and not education_scope,
        )
        identity_mismatch = identity_only and (
            not _identity_matches(rewritten, references, strict_contacts=True)
            or not current_contact_header
            and not fixed_education
            and not _identity_matches(original_group, references)
        )
        if (
            identity_mismatch
            or not references
            or any(not _application_usable(x) for x in references)
        ):
            disposition = "verify"
            reason = (
                reason
                if reason.startswith("source_or_attribution_unresolved: ")
                else "source_or_attribution_unresolved: " + reason
            )
        evidence = " ".join(
            x.get("text", "") + " " + x.get("title", "") + " " + x.get("boundaries", "")
            for x in references
        )
        prose = _prose_latex(rewritten)
        if current_contact_header or identity_format_only:
            evidence, _ = _contact_literals(evidence)
            prose, _ = _contact_literals(prose)
        literal_checks = review_findings(evidence, prose)["checks"]
        if disposition == "include" and any(
            check["added"] for check in literal_checks if check["category"] in {"numbers", "dates"}
        ):
            disposition = "verify"
            reason = (
                "unsupported_literal: " + reason
                if not reason.startswith("unsupported_literal: ")
                else reason
            )
        if disposition == "include" and (
            not rewritten.strip()
            or any(not _application_rewrite_allowed(x) for x in references)
            and rewritten != original_group
            and not current_contact_header
            and not identity_format_only
            and not fixed_education
        ):
            raise _invalid("改写不得改变已限定为原文保留的来源。")
        groups.append(
            {
                "id": digest(
                    {"start": row["start_line"], "end": row["end_line"], "original": original_group}
                ),
                "title": row["title"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "original": original_group,
                "rewritten": rewritten,
                "sources": references,
                "attribution": [x.get("attribution", "Unknown") for x in references],
                "reason": reason,
                "disposition": disposition,
                "review_status": "review_required",
                "review_findings": review_findings(original_group, rewritten),
                **(
                    {
                        "content_policy": "fixed_education"
                        if fixed_education
                        else (
                            "education_verification_required" if education_scope else "jd_tailored"
                        )
                    }
                    if presentation_policy
                    else {}
                ),
            }
        )
    if covered != set(range(1, len(lines) + 1)):
        raise _invalid("原稿正文未全部对应到采用、未采用或待核对分组。")
    included = [g for g in groups if g["disposition"] == "include"]
    if not included:
        raise PortalDataError(
            "resume_material_insufficient", "没有来源及责任可核验的正文分组。", 409
        )
    latex = _a4_prefix(prefix) + "".join(g["rewritten"] for g in included) + suffix
    if presentation_policy:
        validate_resume_presentation(_prose_latex(latex))
    _body(latex)
    _validate_body("".join(g["rewritten"] for g in included), original)
    return {
        "latex_source": latex,
        "review_groups": included,
        "omitted_groups": [g for g in groups if g["disposition"] == "omit"],
        "verification_queue": [g for g in groups if g["disposition"] == "verify"],
        "limitations": output["limitations"],
    }


def _a4_prefix(prefix):
    """Set the confirmed default on the independent copy, retaining other class options."""
    declarations = list(re.finditer(r"\\documentclass(?:\[([^\]]*)\])?\{([^{}]+)\}", prefix))
    if len(declarations) != 1:
        raise _invalid("底稿文档类不能核验，请先核对完整LaTeX底稿。")
    # Unusual direct page dimensions require an explicit source/layout review.
    if re.search(
        r"\\(?:pdfpagewidth|pdfpageheight|paperwidth|paperheight)\b|\b(?:papersize|paperwidth|paperheight)\s*=",
        prefix,
    ):
        raise _invalid("底稿含独立纸张尺寸设置，须先核对A4布局。")
    match = declarations[0]
    options = [x.strip() for x in (match[1] or "").split(",") if x.strip()]
    paper = re.compile(r"^(?:a[0-9]|b[0-9]|c[0-9]|letter|legal|executive)paper$")
    options = [x for x in options if not paper.fullmatch(x)] + ["a4paper"]
    declaration = "\\documentclass[" + ",".join(options) + "]{" + match[2] + "}"
    prefix = prefix[: match.start()] + declaration + prefix[match.end() :]
    # Geometry's explicit named paper setting can override the class option.
    return re.sub(r"\b(?:a[0-35-9]|b[0-9]|c[0-9]|letter|legal|executive)paper\b", "a4paper", prefix)


def _validate_body(body, original):
    # Model output must not expand the base's executable/read surface.
    forbidden = (
        r"\\(?:input|include|includeonly|subfile|import|includepdf|includegraphics|"
        r"bibliography|addbibresource|lstinputlisting|verbatiminput|openin|openout|"
        r"read|write|immediate|special|directlua|latelua|catcode|csname|def|gdef|edef|"
        r"xdef|let|futurelet|newcommand|renewcommand|newenvironment|renewenvironment|"
        r"usepackage|documentclass)(?![A-Za-z@])"
    )

    def commands(text):
        return set(re.findall(r"\\([A-Za-z@]+)", text))

    if (
        re.search(forbidden, body)
        or not commands(body) <= commands(original)
        or "^^" in body
        or len(body.encode("utf-8")) > 4_000_000
    ):
        raise _invalid("生成内容不能新增外部读取、执行或宏定义。")
    clean = re.sub(r"(?m)(?<!\\)%.*$", "", body)
    if re.search(r"\\(?:begin|end)(?![A-Za-z@])(?!(?:\{))", clean):
        raise _invalid("正文环境须使用可直接核验的规范形式。")

    def environments_in(text):
        return set(re.findall(r"\\(?:begin|end)\{([^}]+)\}", text))

    names = environments_in(clean)
    if not names <= environments_in(original) or any(
        name.casefold().startswith(("filecontents", "luacode", "pycode", "python", "minted"))
        for name in names
    ):
        raise _invalid("正文不能新增环境或包含执行及文件写入环境。")
    clean = re.sub(r"(?m)(?<!\\)%.*$", "", body)
    braces, environments = [], []
    for token in re.finditer(r"\\[{}]|[{}]", clean):
        value = token.group()
        if value == "{":
            braces.append(value)
        elif value == "}":
            if not braces:
                raise _invalid("正文括号不平衡，不能保存为完整简历。")
            braces.pop()
    for token in re.finditer(r"\\(begin|end)\{([^}]+)\}", clean):
        kind, name = token.groups()
        if kind == "begin":
            environments.append(name)
        elif not environments or environments.pop() != name:
            raise _invalid("正文环境不平衡，请核对分组取舍。")
    if braces or environments:
        raise _invalid("正文结构未闭合，请核对分组取舍。")


def _model_payload(payload):
    """Reference exact base lines instead of transmitting duplicate retained text."""
    wire = deepcopy(payload)
    prefix, body, _suffix = _body(payload["base"])
    offset = prefix.count("\n")
    lines = payload["base"].splitlines(keepends=True)
    source_sha256 = hashlib.sha256(payload["base"].encode()).hexdigest()
    for index, source in enumerate(wire["sources"]):
        source.pop("education_correction", None)
        if not source.get("retained_receipt_revision"):
            continue
        start, end = source["retained_start_line"], source["retained_end_line"]
        text = "".join(lines[start - 1 : end])
        if (
            source["retained_source_sha256"] != source_sha256
            or not offset < start <= end <= offset + len(body.splitlines())
            or hashlib.sha256(text.encode()).hexdigest() != source["retained_text_sha256"]
        ):
            if payload.get("update_context", {}).get("pending_merge"):
                accepted = (
                    json.loads(source["text"]).get("accepted_latex")
                    if source["source_kind"] in {"education", "identity"}
                    else source["text"]
                )
                if (
                    not isinstance(accepted, str)
                    or hashlib.sha256(accepted.encode()).hexdigest()
                    != source["retained_text_sha256"]
                ):
                    raise _invalid("已接受来源原文字节不能核验。")
                # This is factual historical context, not a claim that its old
                # receipt locator points into the synthetic pending input.
                continue
            raise _invalid("已接受来源与本次底稿行段不符。")
        if source["source_kind"] == "education":
            source["documentary_profile_record"] = json.loads(source["text"])["profile_record"]
        source.pop("text")
        source["text_from_base_lines"] = {"start_line": start - offset, "end_line": end - offset}
        # Complete provenance remains in input.json and source-snapshot.json.
        # Context sources already occur once under their registered source IDs.
        wire["sources"][index] = {
            key: source[key]
            for key in (
                "source_id",
                "source_kind",
                "application_trusted",
                "title",
                "attribution",
                "boundaries",
                "resume_eligible",
                "rewrite_allowed",
                "review_status",
                "context_source_ids",
                "text_from_base_lines",
                "documentary_profile_record",
                "design_only",
            )
            if key in source
        }
    wire["document_context"] = [
        document
        for document in wire["document_context"]
        if document["source_name"] != "sources/retained-resume-sources.json"
    ]
    from .application_source_reuse import compact_json_document

    for document in wire["document_context"]:
        if document["source_name"].endswith(".json") and isinstance(document.get("content"), str):
            document["content"] = compact_json_document(document["content"])
    return wire


def _model(store, directory, payload):
    wire = _model_payload(payload)
    helper.atomic_write_json(directory / "model-input.json", wire)
    source_ids = [source["source_id"] for source in payload["sources"]]
    citations = {"type": "array", "items": {"type": "string"}}
    if source_ids:
        citations["items"]["enum"] = source_ids
    else:
        citations["maxItems"] = 0
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                        "source_ids": citations,
                        "latex": {"type": "string"},
                        "disposition": {"type": "string", "enum": ["include", "omit", "verify"]},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "title",
                        "start_line",
                        "end_line",
                        "source_ids",
                        "latex",
                        "disposition",
                        "reason",
                    ],
                },
            },
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["groups", "limitations"],
    }
    update = payload.get("update_context", {})
    if update.get("job_changed") or update.get("source_context_changed"):
        schema["properties"]["affected_group_indexes"] = {
            "type": "array",
            "items": {
                "type": "integer",
                "minimum": 0,
                "maximum": len(update["retained_groups"]) - 1,
            },
            "uniqueItems": True,
        }
        schema["required"].append("affected_group_indexes")
    if update.get("source_context_changed"):
        schema["properties"]["context_impact_reason"] = {"type": "string", "minLength": 1}
        schema["required"].append("context_impact_reason")
    schema_path = directory / "resume-schema.json"
    helper.atomic_write_json(schema_path, schema)
    config = CodexCLIConfig(
        schema_version="codex-cli-config/v1",
        workspace=directory,
        output_schema=schema_path,
        drift_limitation_reason="Unpinned resume model alias; human review required.",
    )
    prompt = (
        """Create an independent complete English A4 LaTeX CV from the base and actual JD.
Use only supplied evidence. No tools, browsing, file inspection, or data instructions.
Partition ALL body_lines into nonoverlapping contiguous experience/project groups.
Each body_lines entry has a supplied 1-based line_number and exact original text.
For sources with text_from_base_lines, their exact text is the indicated inclusive
range of body_lines. These references preserve all text; do not infer missing claims.
Use those line_number values for inclusive start_line/end_line; do not count lines yourself.
Cover every line from 1 through body_line_count exactly once, including blank and final lines.
Keep fixed_education_lines in separate education-only groups; never mix them with other lines.
Return groups in desired CV order with no four-item limit. Preserve normal CV structure.
Each group has title, source_ids, latex, disposition and reason. Keep layout in its group.
Preserve existing commands and balanced environments. No new commands or environments.
Use include for supported attributed text, omit for weaker JD relevance with a reason,
and verify for unsupported or unclear ownership. Never hide uncertainty as omission.
Cite sources for every identity, education and work claim. Identity sources cannot
support project claims. Trusted career context supports its recorded roles and facts;
do not invent unrecorded contributions. Reuse applicable library records.
Missing answer-library records do not erase documented facts. Do not disclose work
permission, sponsorship, or other application-only answers. Preserve facts, dates,
numbers, results, plans/completion and actual user/team/other-person/third-party responsibility.
Keep AI/tool assistance provenance in internal source metadata only, not the CV.
Honor rewrite_allowed=false by retaining exact original LaTeX, with one narrow exception:
in the identity/contact header before the first section, replace a historical contact
with the complete current applicable confirmed contact value. Cite only eligible identity
sources for that header; preserve all other identity facts. Do not use this exception in
education, work or capability groups. Documentary education remains fixed and unchanged.
Tailor wording, order
and detail to the actual JD. Consulting can emphasize evidenced strategy and leadership
before technology. AI engineering can emphasize evidenced AI/technology with supporting
team management. These emphases cannot create facts. Preserve the base preamble and
document boundary. Return body fragments only; no new macros, external reads or files.
Source associations and mechanical checks cannot establish semantic or human approval.
All pending_group_indexes must be rechecked using their latest candidate wording,
current facts and actual manual TeX. Preserve later manual changes and do not silently
lose an unresolved candidate. A real remaining fact or responsibility conflict must
remain verify. Only change groups affected by the pending conflict, sources or JD.
When update_context is supplied, review the actual retained TeX and manual wording
against previous/current job context and source changes. Change only content actually
affected by those changes. Preserve other wording, facts, education and layout exactly.
Keep the supplied retained group spans and source associations. Important conflicting
facts or unclear responsibility require verify; never silently retain or invent them.
When job_changed or source_context_changed is true, return affected_group_indexes using
the zero-based indexes
of retained_groups. Select groups whose actual content needs changing for the added,
removed or changed JD requirements, including requirements with no old source mapping.
Unrelated metadata changes may have an empty list. Other proposed rewrites are ignored.
For source_context_changed, use source_context_changes to assess added, changed or removed
context against actual retained TeX. Current document/source values are referenced by name/ID
in document_context/sources; previous delta values are supplied for comparison. Return a
nonempty context_impact_reason even for no impact. It records a model judgment, not new facts
or human acceptance. Keep all existing source IDs; affected groups may additionally cite only
eligible current IDs listed in unmapped_current_source_ids. Raw documents/profile links are
context, not capability evidence. Preserve actual manual omissions; never restore omitted or
deleted text merely because its source changed. Important fact/responsibility conflicts stay verify.
"""
        + BUSINESS_FIRST_INSTRUCTIONS
        + PRESENTATION_INSTRUCTIONS
        + "\n"
        + json.dumps(wire, ensure_ascii=False, separators=(",", ":"))
    )
    prompt_bytes = prompt.encode("utf-8")
    if len(prompt_bytes) > MAX_PROMPT_BYTES:
        helper.atomic_write_json(
            directory / "model-result.json",
            {
                "status": "not_started",
                "error_code": "resume_latex_context_too_large",
                "model_started": False,
                "prompt_bytes": len(prompt_bytes),
                "context_limit_bytes": MAX_PROMPT_BYTES,
                "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            },
        )
        raise PortalDataError(
            "resume_latex_context_too_large",
            "完整LaTeX模型输入超出长度限制，尚未启动模型；请核对取材范围，保留原始资料。",
            409,
        )
    try:
        with store.measurements.stage("model", model_mode=store.model_mode):
            result = store.model_runner(
                config, prompt, timeout_seconds=180, allow_non_repository=True
            )
    except (CodexCLIError, OSError, subprocess.TimeoutExpired) as exc:
        helper.atomic_write_json(
            directory / "model-result.json",
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "raw_stdout_jsonl": getattr(exc, "raw_stdout_jsonl", ""),
                "redacted_stderr": getattr(exc, "redacted_stderr", ""),
            },
        )
        raise PortalDataError(
            "resume_model_unavailable", "完整LaTeX生成未完成，请保留记录后明确重试。", 503
        ) from exc
    helper.atomic_write_json(directory / "model-result.json", result.model_dump(mode="json"))
    return result.structured_result


def retained_contact_plan(draft, original, sources):
    """Change only uniquely mapped contact literals in the retained identity header."""
    from .application_group_review import _MARKER, unwrapped_group

    _, body, _ = _body(original)
    markers = list(_MARKER.finditer(body))
    groups = draft["review_groups"]
    spans = []
    if markers:
        if len(markers) != 2 * len(groups):
            raise _invalid("原完整源的经历边界尚不能唯一核验，请保留源人工修正。")
        for index, _group in enumerate(groups):
            begin, end = markers[index * 2 : index * 2 + 2]
            if begin[1] != end[1] or begin[2] != "begin" or end[2] != "end":
                raise _invalid("原完整源分组标识不符。")
            spans.append((begin.start(), end.end()))
    else:
        cursor = 0
        for group in groups:
            text = group["rewritten"]
            start = body.find(text, cursor)
            if start < 0 or body.count(text) != 1 or body[cursor:start].strip():
                raise _invalid("原完整源的经历边界尚不能唯一核验，请保留源人工修正。")
            spans.append((start, start + len(text)))
            cursor = start + len(text)
        if body[cursor:].strip():
            raise _invalid("原完整源有未定位的正文，请保留源人工修正。")
    current = {source["source_id"]: source for source in sources}
    identity = [source for source in sources if source.get("source_kind") == "identity"]

    old_facts = _identity_facts(
        draft.get("generation_sources", [source for group in groups for source in group["sources"]])
    )
    new_facts = _identity_facts(identity)
    changed = {
        key: (old_facts.get(key), value)
        for key, value in new_facts.items()
        if old_facts.get(key) != value
    }
    first_section = re.search(r"\\(?:section|cvsection)\*?(?:\[[^\]]*\])?\{", body)
    output = []
    applied = {key: 0 for key in changed}
    has_header = False
    for index, group in enumerate(groups):
        start = 0 if index == 0 else spans[index][0]
        finish = len(body) if index == len(groups) - 1 else spans[index + 1][0]
        chunk = body[start:finish]
        if unwrapped_group(chunk) != unwrapped_group(group["rewritten"]):
            raise _invalid("原完整源的正文与已保存分组不符。")
        refs = [
            current[source["source_id"]]
            for source in group["sources"]
            if source["source_id"] in current
        ]
        is_header = (
            (first_section is None or finish <= first_section.start())
            and bool(group["sources"])
            and all(source.get("source_kind") == "identity" for source in group["sources"])
        )
        if is_header:
            has_header = True
            own = {source["source_id"] for source in group["sources"]}
            refs = [
                source
                for source in identity
                if not source.get("retained_receipt_revision") or source["source_id"] in own
            ]
            group_changed = False
            for key, (old, new) in changed.items():
                if not old:
                    raise _invalid("新联系方式在原页眉中没有唯一可核验位置，请编辑完整源。")
                # Literal substitution stays inside this mapped identity header.
                # A value needing LaTeX escaping must already have an exact source
                # representation; unsupported custom macros stop for source editing.
                chunk, replacements = _replace_contact(chunk, key, old, new)
                if not replacements:
                    continue
                applied[key] += 1
                group_changed = True
            # Each fixed slice needs only its displayed current contacts, not
            # confirmed facts rendered by a different header slice.
            if group_changed:
                refs = [
                    source
                    for source in refs
                    if source.get("confirmation_state") != "confirmed"
                    or any(
                        value in chunk
                        or _contact_latex(value) in chunk
                        or fact == "phone"
                        and re.sub(r"\D", "", value) in _contact_literals(chunk)[1]["phone"]
                        for fact, value in _identity_facts([source]).items()
                    )
                ]
            if group_changed and not _current_contact_header(chunk, refs):
                raise _invalid("当前页眉仍有联系方式冲突，请编辑完整源。")
        output.append(
            {
                "title": group["title"],
                "start_line": body[:start].count("\n") + 1,
                "end_line": body[:finish].count("\n"),
                "source_ids": [source["source_id"] for source in refs],
                "latex": chunk,
                "disposition": "include",
                "reason": "Retained full source; confirmed contact header only",
            }
        )
    if has_header and any(count != 1 for count in applied.values()):
        raise _invalid("新联系方式在原页眉中没有唯一可核验位置，请编辑完整源。")
    return {"groups": output, "limitations": []}


def _pending_input(draft, root):
    """Restore only unresolved candidates around the actual adopted editor chunks."""
    from .application_group_review import _MARKER, _marked, unwrapped_group

    if not draft["verification_queue"]:
        return deepcopy(draft), []
    original = draft["latex_source"]
    prefix, _body_text, suffix = _body(original)
    actual = retained_contact_plan(draft, original, draft["generation_sources"])["groups"]
    ordered = [
        (deepcopy(group), row["latex"])
        for group, row in zip(draft["review_groups"], actual, strict=True)
    ]
    root_groups = root["review_groups"] + root["omitted_groups"] + root["verification_queue"]
    anchors = [group["id"] for group in sorted(root_groups, key=lambda group: group["start_line"])]
    queued = draft["verification_queue"]
    present_ids = {group["id"] for group, _chunk in ordered}
    if len(present_ids) != len(ordered) or present_ids & {group["id"] for group in queued}:
        raise _invalid("待核对组与当前人工正文重复，请保留源并核对。")
    marked = bool(_MARKER.search(_body_text))
    for group in sorted(
        queued,
        key=lambda group: anchors.index(group["id"]) if group["id"] in anchors else len(anchors),
    ):
        identifier = group["id"]
        positions = {current["id"]: index for index, (current, _) in enumerate(ordered)}
        if identifier in anchors:
            anchor = anchors.index(identifier)
            following = next((key for key in anchors[anchor + 1 :] if key in positions), None)
            preceding = next((key for key in reversed(anchors[:anchor]) if key in positions), None)
            if following is not None:
                index = positions[following]
            elif preceding is not None:
                index = positions[preceding] + 1
            else:
                raise _invalid("待核对组缺少现有正文锚点，请保留人工顺序并核对。")
        elif group.get("original_locator", {}).get("kind") == "added_from_sources":
            index = len(ordered)
        else:
            raise _invalid("待核对组来源顺序不能核验，请保留人工正文。")
        candidate = deepcopy(group)
        candidate["rewritten"] = _MARKER.sub("", unwrapped_group(group["rewritten"]))
        chunk = _marked([candidate]) if marked else candidate["rewritten"]
        if not chunk.endswith("\n"):
            chunk += "\n"
        ordered.insert(index, (deepcopy(group), chunk))
    if not marked and any(not group["rewritten"].strip() for group in queued):
        # Empty pending candidates have no unique text locator. Mark every virtual
        # chunk so they remain addressable without restoring discarded wording.
        ordered = [(group, _marked([group | {"rewritten": chunk}])) for group, chunk in ordered]
    virtual = deepcopy(draft)
    virtual["review_groups"] = []
    for group, chunk in ordered:
        group["rewritten"] = chunk
        virtual["review_groups"].append(group)
    virtual["latex_source"] = prefix + "".join(chunk for _, chunk in ordered) + suffix
    pending = [
        index
        for index, (group, _) in enumerate(ordered)
        if group["id"] in {g["id"] for g in queued}
    ]
    return virtual, pending


def _omitted_source_mapping(store, parent):
    """Retain omission coverage, never omitted text or obsolete source associations."""
    mapping = deepcopy(parent.get("omitted_source_mapping", {}))
    if "omitted_source_mapping" not in parent and parent.get("pending_merge"):
        # Legacy pending merges did not persist omission coverage. Recover it
        # through their already validated actual parents once, then save it.
        merge = parent["pending_merge"]
        previous = store._draft_document(merge["draft_id"])[0]
        mapping = _omitted_source_mapping(store, previous)
    if not isinstance(mapping, dict) or any(
        not isinstance(identifier, str)
        or not isinstance(references, list)
        or any(
            not isinstance(source, dict)
            or set(source) != {"source_id", "source_name"}
            or any(not isinstance(value, str) or not value for value in source.values())
            for source in references
        )
        for identifier, references in mapping.items()
    ):
        raise _invalid("已省略内容的来源映射不能核验，请保留人工源。")
    for group in parent["omitted_groups"]:
        mapping[group["id"]] = [
            {key: source[key] for key in ("source_id", "source_name")}
            for source in group["sources"]
        ]
    for group in parent["review_groups"] + parent["verification_queue"]:
        mapping.pop(group["id"], None)
    return mapping


def _pending_parent(store, draft_id, draft_sha256, application_id, base, archive):
    parent, observed = store._draft_document(draft_id)
    if (
        observed != draft_sha256
        or not (
            parent["verification_queue"]
            or parent["omitted_groups"]
            or parent.get("pending_merge")
            or "omitted_source_mapping" in parent
            or any(
                source.get("retained_receipt_revision") for source in parent["generation_sources"]
            )
        )
        or parent["application_id"] != application_id
        or parent["source_checkpoint"] != base
        or store._read_version_file(parent["id"], "latex-sources.json", 48_000_000) != archive
    ):
        raise _invalid("待核对人工源的不可变检查点不能核验，请保留历史。")
    if not parent["verification_queue"]:
        return deepcopy(parent) | {"draft_sha256": observed}, []
    root_id = parent.get("group_session", {}).get("root_draft_id", parent["id"])
    root = parent if root_id == parent["id"] else store._draft_document(root_id)[0]
    virtual, indexes = _pending_input(parent, root)
    virtual["draft_sha256"] = observed
    return virtual, indexes


def generate_full_latex(
    store,
    identifier,
    revision,
    *,
    source_snapshot,
    analysis,
    task_inputs,
    latex_base,
    information_library=None,
    retained_draft=None,
    output_provider=None,
    plan_observer=None,
    allow_retained_source_selection=False,
):
    """Generate a separately saved source version; no editor, build, PDF or factual approval."""
    snapshot, analysis, base = deepcopy(source_snapshot), deepcopy(analysis), deepcopy(latex_base)
    configuration = deepcopy(store.configuration())
    application = store._task_current(identifier, snapshot, analysis, configuration)
    if application["revision"] != revision:
        raise PortalDataError("conflict", "岗位记录已变化，请重新读取。", 409)
    if not isinstance(task_inputs, dict) or not task_inputs:
        raise PortalDataError("resume_inputs_stale", "完整LaTeX草稿缺少任务版本。", 409)
    if resume_language_policy(application.get("job_description", ""))["status"] == "needs_input":
        raise PortalDataError(
            "resume_language_needs_input", "岗位要求其他简历语言，请先单独处理。", 409
        )
    base_archive = archive_sources(base)
    original = validate_archive(base_archive, base).decode("utf-8")
    actual_original = original
    if retained_draft is not None and original != retained_draft.get("latex_source"):
        raise _invalid("当前完整底稿与已保存人工源不符，请保留原稿并核对。")
    pending_merge = None
    omitted_mapping = None
    pending_indexes = []
    if retained_draft is not None and (
        retained_draft.get("verification_queue")
        or retained_draft.get("omitted_groups")
        or store._draft_document(retained_draft["id"])[0].get("pending_merge")
        or "omitted_source_mapping" in store._draft_document(retained_draft["id"])[0]
        or any(
            source.get("retained_receipt_revision")
            for source in store._draft_document(retained_draft["id"])[0]["generation_sources"]
        )
    ):
        parent = retained_draft
        retained_draft, pending_indexes = _pending_parent(
            store,
            parent["id"],
            parent["draft_sha256"],
            identifier,
            base | {"archive_sha256": hashlib.sha256(base_archive).hexdigest()},
            base_archive,
        )
        original = retained_draft["latex_source"]
        actual_parent = store._draft_document(parent["id"])[0]
        inherited_mapping = _omitted_source_mapping(store, actual_parent)
        if (
            inherited_mapping
            or actual_parent["omitted_groups"]
            or "omitted_source_mapping" in actual_parent
        ):
            omitted_mapping = inherited_mapping
        pending_merge = {
            "policy": "pending-tex-merge/v2"
            if omitted_mapping is not None
            else "pending-tex-merge/v1",
            "draft_id": parent["id"],
            "draft_sha256": parent["draft_sha256"],
        }
    _, body, _ = _body(original)
    library = deepcopy(information_library or {})
    expected_library = task_inputs.get("information_library_revision")
    if expected_library is not None and library.get("revision") != expected_library:
        raise PortalDataError("resume_inputs_stale", "既有确认记录版本已变化，请更新任务。", 409)
    sources = _sources(
        snapshot, library, application, original=actual_original, retained_draft=retained_draft
    )
    if retained_draft is not None:
        from .application_source_reuse import explicit_profile_correction

        previous_sources = {
            source["source_id"]: source
            for group in retained_draft["review_groups"]
            for source in group["sources"]
        }
        for source in sources:
            old = previous_sources.get(source["source_id"])
            if (
                source.get("source_kind") != "education"
                or old is None
                or old["text"] == source["text"]
                or source.get("retained_receipt_revision")
            ):
                continue
            old_record = json.loads(old["text"])
            if old.get("retained_receipt_revision"):
                old_record = old_record["profile_record"]
            correction = explicit_profile_correction(
                store.catalog,
                snapshot["profile_source"],
                previous_revision=None
                if old.get("retained_receipt_revision")
                else old["source_revision"],
                previous_entry_sha256=digest(old_record)
                if old.get("retained_receipt_revision")
                else None,
                locator=source["locator"],
            )
            if correction is not None:
                old_record = correction["profile"]["education"][
                    int(re.fullmatch(r"profile\.education\[(\d+)\]", source["locator"])[1])
                ]
                if old_record == (
                    json.loads(old["text"])["profile_record"]
                    if old.get("retained_receipt_revision")
                    else json.loads(old["text"])
                ):
                    source["education_correction"] = {
                        "previous_source": old,
                        "events": correction["events"],
                        "draft_id": retained_draft["id"],
                        "draft_sha256": retained_draft["draft_sha256"],
                    }
    version = uuid4().hex
    directory = store.root / version
    directory.mkdir(mode=0o700)
    helper.atomic_write_json(directory / "source-snapshot.json", snapshot)
    education_corrections = {
        source["source_id"]: source["education_correction"]
        for source in sources
        if "education_correction" in source
    }
    if education_corrections:
        helper.atomic_write_json(directory / "education-corrections.json", education_corrections)
    (directory / "base-sources.json").write_bytes(base_archive)
    (directory / "base-sources.json").chmod(0o600)
    binding = {
        "analysis_id": analysis["id"],
        **{
            k: analysis[k]
            for k in (
                "jd_revision",
                "source_snapshot_revision",
                "configuration_revision",
                "policy_version",
            )
        },
    }
    body_lines = body.splitlines(keepends=True)
    payload = {
        "job": {
            k: application.get(k, "")
            for k in ("company", "role_title", "location", "job_description")
        },
        "base": original,
        "body_lines": [
            {"line_number": number, "text": text} for number, text in enumerate(body_lines, 1)
        ],
        "body_line_count": len(body_lines),
        "fixed_education_lines": sorted(_education_lines(body)),
        "sources": sources,
        "analysis": binding,
        "analysis_selected_source_ids": [
            sid
            for sid in analysis["selected_source_ids"]
            if any(source["source_id"] == sid and _application_usable(source) for source in sources)
        ]
        if snapshot.get("application_library_policy") == "trusted-library/v1"
        else analysis["selected_source_ids"],
        "role_understanding": deepcopy(analysis.get("role_understanding")),
        **({"job_brief": deepcopy(analysis["job_brief"])} if analysis.get("job_brief") else {}),
        **(
            {"material_packet": deepcopy(analysis["material_packet"])}
            if analysis.get("material_packet")
            else {}
        ),
        **(
            {"inference_result": deepcopy(analysis["inference_result"])}
            if analysis.get("inference_result")
            else {}
        ),
        "selection_rationale": deepcopy(analysis.get("selection_rationale", [])),
        "requirements": deepcopy(analysis.get("requirements", [])),
        "confirmation_context": [
            source for source in sources if source.get("confirmation_state") == "confirmed"
        ],
        "document_context": [doc for doc in snapshot["documents"] if doc.get("available")],
        "presentation_policy": PRESENTATION_POLICY_VERSION,
    }
    helper.atomic_write_json(directory / "input.json", payload)
    from .application_prism import source_snapshot as latex_snapshot

    project = directory / "project"
    try:
        if directory.resolve(strict=True) != directory or any(
            path.is_symlink() for path in (directory, *directory.parents)
        ):
            raise ValueError("Redirected generation directory")
        project.mkdir(mode=0o700)
        for name, encoded in json.loads(base_archive).items():
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(base64.b64decode(encoded, validate=True))
            path.chmod(0o600)
        preflight = latex_snapshot(
            project, base["main"], source_policy="generated-latex-project/v1"
        )
        if archive_sources(preflight) != base_archive:
            raise ValueError("Generation project differs from the accepted base")
    except (OSError, ValueError, TypeError) as exc:
        helper.atomic_write_json(
            directory / "project-preflight.json",
            {"status": "not_started", "error_type": type(exc).__name__},
        )
        raise PortalDataError(
            "resume_destination_invalid", "生成目录预检失败，模型未启动，请核对专用目录。", 409
        ) from exc
    helper.atomic_write_json(
        directory / "project-preflight.json", {"status": "ready", "binding": preflight}
    )
    provided = False

    def model_output():
        nonlocal provided
        provided = True
        return (output_provider or _model)(store, directory, payload)

    if retained_draft is None:
        output = model_output()
    else:
        output = retained_contact_plan(retained_draft, original, sources)
        current = {source["source_id"]: source for source in sources}

        def facts(value):
            # A document's byte revision is provenance, not a change to every
            # cited fact in that document. All factual and attribution fields,
            # including nested supporting sources, still participate.
            if isinstance(value, dict):
                return {
                    key: facts(item)
                    for key, item in value.items()
                    if key not in {"source_revision", "education_correction"}
                }
            if isinstance(value, list):
                return [facts(item) for item in value]
            return value

        previous = json.loads(
            store._read_version_file(retained_draft["id"], "source-snapshot.json", 32 * 1024 * 1024)
        )
        if not isinstance(previous, dict):
            raise _invalid("原职业来源快照格式不能核验，请保留原稿。")
        if digest(
            {key: value for key, value in previous.items() if key != "revision"}
        ) != previous.get("revision") or previous.get("revision") != retained_draft.get(
            "analysis_binding", {}
        ).get("source_snapshot_revision"):
            raise _invalid("原职业来源快照已变化，请保留原稿并核对历史。")
        old_documents = {doc["source_name"]: doc for doc in previous["documents"]}
        new_documents = {doc["source_name"]: doc for doc in snapshot["documents"]}
        profile_name = (snapshot.get("profile_source") or {}).get("source_name")
        changed_documents = {
            name
            for name in old_documents.keys() | new_documents.keys()
            if name != profile_name
            and {
                key: old_documents.get(name, {}).get(key)
                for key in ("content", "available", "error_code", "kind")
            }
            != {
                key: new_documents.get(name, {}).get(key)
                for key in ("content", "available", "error_code", "kind")
            }
        }
        references = [
            source
            for group in retained_draft["review_groups"] + retained_draft.get("omitted_groups", [])
            for source in group["sources"]
        ]
        references.extend(
            source for references in (omitted_mapping or {}).values() for source in references
        )
        unmapped_documents = changed_documents - {source["source_name"] for source in references}
        old_draft, old_sha256 = store._draft_document(retained_draft["id"])
        if old_sha256 != retained_draft.get("draft_sha256"):
            raise _invalid("原完整源的来源检查点不能核验，请保留原稿。")
        job_changed = old_draft["analysis_binding"]["jd_revision"] != binding["jd_revision"]
        previous_job = old_draft.get("job_context")
        if (
            "job_context" in old_draft
            and (
                not isinstance(previous_job, dict)
                or digest(previous_job) != old_draft["analysis_binding"]["jd_revision"]
            )
            or job_changed
            and previous_job is None
        ):
            raise _invalid("原岗位内容不能核验，请保留已采用TeX并核对JD更新影响。")
        old_sources = {source["source_id"]: source for source in old_draft["generation_sources"]}
        changed_sources = {
            identifier
            for identifier in old_sources.keys() | current.keys()
            if facts(old_sources.get(identifier)) != facts(current.get(identifier))
            and (current.get(identifier) or old_sources.get(identifier)).get("source_kind")
            != "identity"
        }
        unmapped_sources = changed_sources - {source["source_id"] for source in references}

        def unmapped_profile(document):
            raw = json.loads(document["content"])
            wrapped = document["source_name"].endswith("site-content.json")
            remaining = deepcopy(raw.pop("profile")) if wrapped else deepcopy(raw)
            # Compare the raw context the model actually consumed. Only remove
            # mapped fields; nested links and later schema fields remain visible.
            for key in ("name", "title", "location"):
                remaining.pop(key, None)
            for category, fields in (
                ("links", {"label", "href"}),
                ("education", {"degree", "institution", "period", "detail"}),
                ("experience", {"role", "organization", "period", "detail", "points"}),
                ("research", {"name", "points", "location", "period", "supervisor"}),
                ("masterThesis", {"name", "points", "location", "period", "supervisor"}),
            ):
                remaining[category] = [
                    {key: value for key, value in row.items() if key not in fields}
                    for row in remaining.get(category, [])
                ]
            return {"profile": remaining, "document": raw if wrapped else {}}

        previous_profile_name = (previous.get("profile_source") or {}).get("source_name")
        previous_profile_context = (
            unmapped_profile(old_documents[previous_profile_name])
            if previous_profile_name in old_documents
            else None
        )
        current_profile_context = (
            unmapped_profile(new_documents[profile_name]) if profile_name in new_documents else None
        )
        profile_context_changed = previous_profile_context != current_profile_context
        context_changed = bool(unmapped_documents or unmapped_sources or profile_context_changed)
        known_source_ids = {source["source_id"] for source in references}
        context_source_names = unmapped_documents | (
            {profile_name} if profile_context_changed and profile_name else set()
        )
        allowed_new_ids = {
            key
            for key, source in current.items()
            if key not in known_source_ids
            and _application_usable(source)
            and source.get("source_kind") != "identity"
            and (key in unmapped_sources or source["source_name"] in context_source_names)
        }
        affected = list(pending_indexes)
        source_affected = []
        for index, group in enumerate(retained_draft["review_groups"]):
            references = group["sources"]
            if all(source.get("source_kind") == "identity" for source in references):
                continue  # The exact contact-header update above is deterministic.
            if any(source["source_id"] not in current for source in references):
                raise _invalid("原人工源引用的事实已缺失，请保留原稿并核对受影响分组。")
            if any(
                facts(source) != facts(current[source["source_id"]])
                or source["source_name"] in changed_documents
                for source in references
            ):
                source_affected.append(index)
                if index not in affected:
                    affected.append(index)
        if affected or job_changed or context_changed:
            payload["update_context"] = {
                "previous_job": previous_job,
                "current_job": payload["job"],
                "job_changed": job_changed,
                "source_context_changed": context_changed,
                "source_affected_group_indexes": source_affected,
                "pending_group_indexes": pending_indexes,
                "pending_merge": bool(pending_merge),
                "pending_group_reasons": [
                    {
                        "group_index": index,
                        "reason": retained_draft["review_groups"][index]["reason"],
                    }
                    for index in pending_indexes
                ],
                "retained_groups": deepcopy(output["groups"]),
            }
            if context_changed:
                payload["update_context"]["source_context_changes"] = {
                    "documents": [
                        {"source_name": name, "previous": old_documents.get(name)}
                        for name in sorted(unmapped_documents)
                    ],
                    "sources": [
                        {"source_id": key, "previous": old_sources.get(key)}
                        for key in sorted(unmapped_sources)
                    ],
                    "previous_profile_context": previous_profile_context
                    if profile_context_changed
                    else None,
                    "current_profile_source_name": profile_name
                    if profile_context_changed
                    else None,
                }
                payload["update_context"]["unmapped_current_source_ids"] = sorted(allowed_new_ids)
            helper.atomic_write_json(directory / "input.json", payload)
            proposed = model_output()
            if not isinstance(proposed, dict) or not isinstance(proposed.get("groups"), list):
                raise _invalid()
            if context_changed and (
                not isinstance(proposed.get("context_impact_reason"), str)
                or not proposed["context_impact_reason"].strip()
            ):
                raise _invalid("新增资料上下文的影响判断缺少依据，请保留原完整源。")
            if job_changed or context_changed:
                indexes = proposed.get("affected_group_indexes")
                if (
                    not isinstance(indexes, list)
                    or any(
                        type(index) is not int or not 0 <= index < len(output["groups"])
                        for index in indexes
                    )
                    or len(set(indexes)) != len(indexes)
                ):
                    raise _invalid("岗位或资料更新的受影响分组不能核验，请保留原完整源。")
                expected_spans = {(row["start_line"], row["end_line"]) for row in output["groups"]}
                proposed_spans = [
                    (row.get("start_line"), row.get("end_line"))
                    for row in proposed["groups"]
                    if isinstance(row, dict)
                ]
                if (
                    len(proposed_spans) != len(output["groups"])
                    or len(proposed["groups"]) != len(proposed_spans)
                    or any(type(line) is not int for span in proposed_spans for line in span)
                    or set(proposed_spans) != expected_spans
                ):
                    raise _invalid("岗位或资料更新须沿用原完整源的分组边界，请保留人工修改。")
                affected = sorted(set(affected) | set(indexes))
            for index in affected:
                retained = output["groups"][index]
                matches = [
                    row
                    for row in proposed["groups"]
                    if isinstance(row, dict)
                    and (row.get("start_line"), row.get("end_line"))
                    == (retained["start_line"], retained["end_line"])
                ]
                identifiers = matches[0].get("source_ids") if len(matches) == 1 else None
                narrowed = False
                if (
                    allow_retained_source_selection
                    and index in pending_indexes
                    and isinstance(identifiers, list)
                    and identifiers
                    and all(isinstance(sid, str) for sid in identifiers)
                    and set(identifiers) < set(retained["source_ids"])
                    and not any(
                        current[sid].get("source_kind") == "education"
                        for sid in retained["source_ids"]
                    )
                ):
                    accepted = [
                        current[sid]
                        for sid in identifiers
                        if current[sid].get("source_kind") == "accepted_resume"
                        and current[sid].get("retained_receipt_revision")
                        and _application_usable(current[sid])
                    ]
                    auxiliary = {
                        sid for source in accepted for sid in source.get("context_source_ids", [])
                    }
                    removed = set(retained["source_ids"]) - set(identifiers)
                    narrowed = bool(accepted) and (
                        matches[0].get("disposition") == "omit"
                        or all(
                            sid in auxiliary
                            or current[sid].get("source_kind") == "career_context"
                            or current[sid].get("attribution")
                            == "Editorial statement; review required"
                            and re.match(
                                r"profile\.(?:experience|research|master_thesis)\[",
                                current[sid].get("locator", ""),
                            )
                            for sid in removed
                        )
                    )
                if (
                    not isinstance(identifiers, list)
                    or any(not isinstance(identifier, str) for identifier in identifiers)
                    or len(set(identifiers)) != len(identifiers)
                    or not narrowed
                    and not set(retained["source_ids"]) <= set(identifiers)
                    or not set(identifiers) - set(retained["source_ids"]) <= allowed_new_ids
                ):
                    raise _invalid("职业更正须对应原人工源的受影响分组，不能重写其他正文。")
                output["groups"][index] = matches[0]
            output["limitations"] = proposed.get("limitations")
    if output_provider is not None and not provided:
        payload["retained_output"] = deepcopy(output)
        proposed = model_output()
        if proposed.get("groups") != output["groups"]:
            raise _invalid("未受影响的人工正文及省略必须保持原样。")
    plan = _plan(
        output,
        original,
        sources,
        PRESENTATION_POLICY_VERSION,
        retained_source=actual_original if pending_merge else None,
    )
    if plan_observer is not None:
        plan_observer(plan)
    application = store._task_current(identifier, snapshot, analysis, configuration)
    if archive_sources(base) != base_archive:
        raise PortalDataError("prism_source_changed", "生成期间底稿已变化，请保留旧结果。", 409)
    if archive_sources(preflight) != base_archive:
        raise PortalDataError(
            "prism_source_changed", "生成期间目标项目已变化，请保留结果并核验。", 409
        )
    generated = directory / "generated-main.tex"
    with generated.open("xb") as stream:
        stream.write(plan["latex_source"].encode())
    generated.chmod(0o600)
    os.replace(generated, project / base["main"])
    checkpoint = latex_snapshot(project, base["main"], source_policy="generated-latex-project/v1")
    archive = archive_sources(checkpoint)
    (directory / "latex-sources.json").write_bytes(archive)
    (directory / "latex-sources.json").chmod(0o600)
    draft = {
        **plan,
        "id": version,
        "origin": "generated_latex",
        "factual_review": "pending",
        "review_status": "review_required",
        "language": "en",
        "preparation_policy": "preparation-policy/v1.0",
        "application_id": identifier,
        "application_revision": application["revision"],
        "task_inputs": deepcopy(task_inputs),
        "analysis_binding": binding,
        "job_context": payload["job"],
        "generation_policy": configuration,
        "presentation_policy": PRESENTATION_POLICY_VERSION,
        "model_mode": store.model_mode,
        "information_library_revision": library.get("revision"),
        "base_checkpoint": base | {"archive_sha256": hashlib.sha256(base_archive).hexdigest()},
        "source_checkpoint": checkpoint | {"archive_sha256": hashlib.sha256(archive).hexdigest()},
        "generation_sources": sources,
        **({"pending_merge": pending_merge} if pending_merge else {}),
        **({"omitted_source_mapping": omitted_mapping} if omitted_mapping is not None else {}),
        "items": [],
        "context": [
            {k: v for k, v in doc.items() if k != "content"} for doc in snapshot["documents"]
        ],
        "selected_source_ids": list(analysis["selected_source_ids"]),
        "limitations": [
            "完整LaTeX独立版本已保存；内容以TeX核对，PDF编译成功后作为导出产物使用。",
            "来源定位和机械核验不能代替语义及人工审核。",
            *plan["limitations"],
        ],
    }
    helper.atomic_write_json(directory / "draft.json", draft)
    helper.atomic_write_json(
        directory / "draft-integrity.json",
        {
            "schemaVersion": 1,
            "id": version,
            "sha256": hashlib.sha256((directory / "draft.json").read_bytes()).hexdigest(),
        },
    )
    return store.draft(version)


def planned_base_source(store, draft, original=None):
    """Reconstruct a generated draft's plan input from its immutable actual parent."""
    archive = store._read_version_file(draft["id"], "base-sources.json", 48_000_000)
    original = (
        original
        if original is not None
        else validate_archive(archive, draft["base_checkpoint"]).decode("utf-8")
    )
    if "pending_merge" not in draft:
        if "omitted_source_mapping" in draft:
            raise ValueError("Omission coverage requires an immutable parent")
        return original
    merge = draft["pending_merge"]
    if (
        not isinstance(merge, dict)
        or set(merge) != {"policy", "draft_id", "draft_sha256"}
        or merge["policy"] not in {"pending-tex-merge/v1", "pending-tex-merge/v2"}
        or merge["draft_id"] == draft["id"]
    ):
        raise ValueError("Pending merge lineage is invalid")
    parent, _pending = _pending_parent(
        store,
        merge["draft_id"],
        merge["draft_sha256"],
        draft["application_id"],
        draft["base_checkpoint"],
        archive,
    )
    if merge["policy"] == "pending-tex-merge/v2":
        actual_parent = store._draft_document(merge["draft_id"])[0]
        if draft.get("omitted_source_mapping") != _omitted_source_mapping(store, actual_parent):
            raise ValueError("Omitted source coverage differs from its actual parent")
    elif "omitted_source_mapping" in draft:
        raise ValueError("Legacy pending merge cannot declare omission coverage")
    return parent["latex_source"]


def validate_full_latex_draft(store, draft):
    """Validate immutable archives and coverage without reading an edited live project."""
    if draft.get("generation_contract") == "fixed-writing/v1":
        from .application_writing import validate_fixed_draft

        validate_fixed_draft(store, draft)
        return
    if draft["factual_review"] != "pending" or draft["items"] != []:
        raise ValueError("Full LaTeX is pending factual review")
    corrections = {
        source["source_id"]: source["education_correction"]
        for source in draft["generation_sources"]
        if "education_correction" in source
    }
    correction_path = store.root / draft["id"] / "education-corrections.json"
    if corrections or correction_path.exists():
        recorded = json.loads(
            store._read_version_file(draft["id"], "education-corrections.json", 2_000_000)
        )
        snapshot = json.loads(
            store._read_version_file(draft["id"], "source-snapshot.json", 32 * 1024 * 1024)
        )
        if (
            recorded != corrections
            or snapshot["revision"] != draft["analysis_binding"]["source_snapshot_revision"]
            or digest({key: value for key, value in snapshot.items() if key != "revision"})
            != snapshot["revision"]
        ):
            raise ValueError("Education correction evidence changed")
        for source in draft["generation_sources"]:
            if source["source_id"] not in corrections:
                continue
            proof = corrections[source["source_id"]]
            parent, observed = store._draft_document(proof["draft_id"])
            match = re.fullmatch(r"profile\.education\[(\d+)\]", source["locator"])
            if (
                observed != proof["draft_sha256"]
                or parent["application_id"] != draft["application_id"]
                or proof["previous_source"]
                not in [
                    reference for group in parent["review_groups"] for reference in group["sources"]
                ]
                or match is None
                or json.loads(source["text"]) != snapshot["profile"]["education"][int(match[1])]
                or source["source_revision"] != snapshot["profile_source"]["revision"]
                or source["source_id"]
                not in {
                    snapshot["profile_source"]["id"] + ":" + source["locator"],
                    *[
                        item["source_id"]
                        for item in snapshot["items"]
                        if item.get("education_profile_correction", {}).get("locator")
                        == source["locator"]
                    ],
                }
            ):
                raise ValueError("Education correction differs from its immutable sources")
    if "job_context" in draft and (
        not isinstance(draft["job_context"], dict)
        or digest(draft["job_context"]) != draft["analysis_binding"]["jd_revision"]
    ):
        raise ValueError("Saved job context differs from the analyzed JD")
    archives = {}
    for name, key in (
        ("base-sources.json", "base_checkpoint"),
        ("latex-sources.json", "source_checkpoint"),
    ):
        raw = store._read_version_file(draft["id"], name, 48_000_000)
        checkpoint = draft[key]
        if hashlib.sha256(raw).hexdigest() != checkpoint["archive_sha256"]:
            raise ValueError("Full source archive changed")
        archives[key] = validate_archive(raw, checkpoint).decode("utf-8")
    if archives["source_checkpoint"] != draft["latex_source"]:
        raise ValueError("Full LaTeX bytes differ")
    groups = draft["review_groups"] + draft["omitted_groups"] + draft["verification_queue"]
    output = {
        "limitations": [],
        "groups": [
            {
                "title": group["title"],
                "start_line": group["start_line"],
                "end_line": group["end_line"],
                "source_ids": [source["source_id"] for source in group["sources"]],
                "latex": group["rewritten"],
                "disposition": group["disposition"],
                "reason": group["reason"],
            }
            for group in groups
        ],
    }
    plan_input = planned_base_source(store, draft, archives["base_checkpoint"])
    rebuilt = _plan(
        output,
        plan_input,
        draft["generation_sources"],
        draft.get("presentation_policy"),
        retained_source=archives["base_checkpoint"] if "pending_merge" in draft else None,
    )
    for key in ("latex_source", "review_groups", "omitted_groups", "verification_queue"):
        if rebuilt[key] != draft[key]:
            raise ValueError("Full LaTeX review scope changed")
    base, current = draft["base_checkpoint"], draft["source_checkpoint"]
    if base["main"] != current["main"] or set(base["files"]) != set(current["files"]):
        raise ValueError("Independent source files changed")
    if any(
        base["files"][name] != current["files"][name]
        for name in base["files"]
        if name != base["main"]
    ):
        raise ValueError("Ancillary base files changed")
