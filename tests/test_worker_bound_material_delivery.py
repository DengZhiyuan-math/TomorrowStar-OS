"""Fixed native material references resolve without authoring or page writes."""

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
from test_cover_letter_delivery import TEMPLATE, flow_inputs
from test_cover_letter_delivery import field as letter_field
from test_single_application_worker import single_worker as single_worker
from test_supplemental_material_module import materials
from test_supplemental_materials import source_data
from test_worker_assistance_delivery import page_context
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_native_assistance import native_service

from career_evidence_graph.application_materials import application_binding
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def field(identifier="letter", **changes):
    return letter_field(identifier, control_ids=["worker-" + identifier], **changes)


def material_target(question):
    return {
        "frame": "main",
        "worker_field": question["control_ids"][0],
        "draft_path": question.get("draft_path", ""),
        "id": "dom-" + question["id"],
        "name": question["id"],
        "tag": "input" if question["type"] == "file" else "textarea",
        "type": question["type"],
        "label": question["question"],
        "required": bool(question.get("required")),
        "disabled": False,
        "readonly": False,
        "accept": question.get("accept", ""),
        "multiple": False,
        "max_length": question.get("max_length"),
        "file_count": 0,
        "value_empty": not bool(question.get("value")),
    }


@pytest.fixture
def bound_material_page(retained_assistance_page, monkeypatch, tmp_path):
    from career_evidence_graph import application_materials

    service, identifier = retained_assistance_page
    service = native_service(service, monkeypatch)
    application = service.store.applications.get_application(identifier)
    content = {
        "schema_version": "cover-letter-content/v1",
        "application_id": identifier,
        "job_revision": digest(application_binding(application)),
        "inputs_revision": "fixed",
        "language": "en",
        "paragraphs": [
            {
                "id": "p1",
                "kind": "fact",
                "text": "Built Python services for a team of analysts.",
                "source_ids": ["project:Scope"],
                "source_quotes": ["Built Python services for a team of analysts."],
                "origin": "ai",
                "protected": False,
            }
        ],
    }
    content["revision"] = digest(content)
    fixed = {
        "application": application,
        "sources": source_data(),
        "cover_letter": {
            "status": "ready",
            "result": {
                "id": "body",
                "attempt_id": "original-author",
                "kind": "cover_letter",
                "status": "ready",
                "actor": "system",
                "content": content,
                "content_revision": content["revision"],
                "source_binding": {
                    "application": application_binding(application),
                    "sources": source_data()["items"],
                },
            },
        },
    }
    template = tmp_path / "letter-template.tex"
    template.write_text(TEMPLATE)
    service.store.cover_letter_template = template
    # Flow delivers the adopted body with the one PDF it built (letter_export).
    service.store.single_material_source_provider = flow_inputs(service.store, fixed, tmp_path)
    monkeypatch.setattr(
        application_materials, "run_codex_exec", lambda *a, **kw: pytest.fail("repeat author")
    )

    def issue(questions, *, prepare=True):
        state = service.store.load()
        job = state["jobs"][0]
        if prepare:
            assert materials((service, job, state["batch_id"])).prepare(
                job, state["batch_id"], {"fields": questions}
            )
        state = service.store.load()
        state["jobs"][0]["form_state"]["snapshot"] = {"fields": deepcopy(questions)}
        service.store.save(state)
        service.request(
            "request-assistance",
            {
                "application_id": identifier,
                "binding": service.assistance_context(identifier)["binding"],
                "request_id": "fixed-material-request",
            },
        )
        ref = service.assistance_context(identifier)["assistance_ref"]
        service.request(
            "claim-assistance",
            {"application_id": identifier, "assistance_ref": ref, "request_id": "fixed-claim"},
        )
        context = page_context(service, ref)
        context["data"]["fields"] = [
            {
                **{key: q[key] for key in ("type", "value", "required", "valid") if key in q},
                "id": "dom-" + q["id"],
                "material_target": material_target(q),
            }
            for q in questions
        ]
        return ref, context

    return service, fixed, issue


def test_ready_text_reference_resolves_exact_body_without_writes(bound_material_page):
    service, fixed, issue = bound_material_page
    question = field(draft_path="questions.letter")
    ref, context = issue([question])
    before = service.store.path.read_bytes()
    catalog = service.store.assistance_delivery(ref, page_context=context)["materials"]
    entry = next(row for row in catalog if row["kind"] == "cover_letter")
    assert re.fullmatch(r"[a-f0-9]{64}", entry["material_ref"])
    resolved = service.store.resolve_bound_material(
        ref, entry["material_ref"], question=question, page_context=context
    )
    material = service.store.load()["jobs"][0]["materials"][0]
    assert resolved["kind"] == "text"
    assert resolved["text"] == material["text"]
    assert resolved["sha256"] == material["text_sha256"]
    assert resolved["material_id"] == material["id"]
    assert (
        resolved["material"]["content_revision"]
        == fixed["cover_letter"]["result"]["content_revision"]
    )
    assert resolved["question"] == question
    assert "file_path" not in json.dumps(catalog)
    assert "file_path" not in json.dumps(resolved)
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("status", ["queued", "running", "failed"])
def test_unprepared_letter_is_explicit_and_has_no_delivery_reference(bound_material_page, status):
    service, fixed, issue = bound_material_page
    fixed["cover_letter"] = {
        "status": status,
        "error_code": "synthetic_author_failed" if status == "failed" else None,
    }
    ref, context = issue([field()])
    before = service.store.path.read_bytes()
    entries = service.store.assistance_delivery(ref, page_context=context)["materials"]
    letter = next(row for row in entries if row["kind"] == "cover_letter")
    assert letter["status"] == status
    assert "material_ref" not in letter
    assert letter["reason"] == (
        "synthetic_author_failed" if status == "failed" else "cover_letter_pending"
    )
    assert service.store.path.read_bytes() == before


def test_pending_consistency_never_publishes_a_ready_field_token(bound_material_page):
    service, fixed, issue = bound_material_page
    state = service.store.load()
    job = state["jobs"][0]
    assert materials((service, job, state["batch_id"])).prepare(
        job, state["batch_id"], {"fields": [field()]}
    )
    fixed["material_consistency"] = {"status": "running"}
    ref, context = issue([field()])
    rows = service.store.assistance_delivery(ref, page_context=context)["materials"]
    letter = next(row for row in rows if row["kind"] == "cover_letter")
    assert letter["status"] == "running"
    assert letter["reason"] == "material_consistency_pending"
    assert "material_ref" not in letter


def test_retained_human_text_is_not_a_system_delivery(bound_material_page):
    service, fixed, issue = bound_material_page
    fixed["cover_letter"] = {"status": "queued"}
    question = field(value="My own motivation, retained on this page.")
    ref, context = issue([question])
    before = service.store.path.read_bytes()
    rows = service.store.assistance_delivery(ref, page_context=context)["materials"]
    letter = next(row for row in rows if row["kind"] == "cover_letter")
    assert letter["status"] == "manual"
    assert letter["reason"] == "retained_page"
    assert "material_ref" not in letter
    assert service.store.load()["jobs"][0]["manual_fields"]["letter"]["value"] == question["value"]
    assert service.store.path.read_bytes() == before


def file_export(directory, content, template):
    directory.mkdir(parents=True)
    pdf = directory / "letter.pdf"
    tex = directory / "letter.tex"
    pdf.write_bytes(b"%PDF-1.4 fixed synthetic letter")
    tex.write_text(template)
    return {
        "file_path": str(pdf),
        "filename": "cover-letter.pdf",
        "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "tex_path": str(tex),
        "tex_sha256": hashlib.sha256(tex.read_bytes()).hexdigest(),
    }


def test_ready_file_uses_original_pdf_source_and_body_without_rebuilding(bound_material_page):
    service, fixed, issue = bound_material_page
    service.store.cover_letter_exporter = file_export
    question = field(kind="file", accept=".pdf", max_bytes=1000, required=True)
    ref, context = issue([question])
    service.store.cover_letter_exporter = lambda *a, **kw: pytest.fail("repeat PDF")
    before = {p: p.read_bytes() for p in service.store.root.rglob("*") if p.is_file()}
    rows = service.store.assistance_delivery(ref, page_context=context)["materials"]
    entry = next(row for row in rows if row["kind"] == "cover_letter")
    resolved = service.store.resolve_bound_material(
        ref, entry["material_ref"], question=question, page_context=context
    )
    material = service.store.load()["jobs"][0]["materials"][0]
    assert resolved["kind"] == "file"
    assert resolved["bytes"] == Path(material["file_path"]).read_bytes()
    assert resolved["sha256"] == hashlib.sha256(resolved["bytes"]).hexdigest()
    assert resolved["filename"] == "cover-letter.pdf"
    assert (
        resolved["material"]["content_revision"]
        == fixed["cover_letter"]["result"]["content_revision"]
    )
    assert resolved["material"]["tex_sha256"] == material["tex_sha256"]
    assert "file_path" not in resolved and "file_path" not in resolved["material"]
    assert {p: p.read_bytes() for p in service.store.root.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    "change", ["field", "draft_path", "meaning", "type", "limit", "human", "duplicate"]
)
def test_current_destination_must_match_fixed_text(bound_material_page, change):
    service, _, issue = bound_material_page
    question = field(draft_path="questions.letter")
    ref, context = issue([question])
    token = next(
        row["material_ref"]
        for row in service.store.assistance_delivery(ref, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )
    if change == "field":
        question["id"] = "new-letter"
    elif change == "draft_path":
        question["draft_path"] = "questions.other"
    elif change == "meaning":
        question["question"] = "Why this company?"
    elif change == "type":
        question["type"] = "file"
    elif change == "limit":
        question["max_length"] = 0
        context["data"]["fields"][0]["material_target"]["max_length"] = 0
    elif change == "human":
        question["value"] = "A human edit must remain."
        context["data"]["fields"][0]["value"] = question["value"]
        context["data"]["fields"][0]["material_target"]["value_empty"] = False
    else:
        context["data"]["fields"].append(deepcopy(context["data"]["fields"][0]))
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        service.store.resolve_bound_material(ref, token, question=question, page_context=context)
    if change == "limit":
        assert error.value.code == "cover_letter_text_too_long"
    elif change == "human":
        assert error.value.code == "material_human_content"
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["bytes", "source", "missing", "symlink"])
def test_fixed_file_rejects_changed_actual_artifacts(bound_material_page, change):
    service, _, issue = bound_material_page
    service.store.cover_letter_exporter = file_export
    question = field(kind="file", accept=".pdf", required=True)
    ref, context = issue([question])
    entry = next(
        row
        for row in service.store.assistance_delivery(ref, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )
    material = service.store.load()["jobs"][0]["materials"][0]
    path = Path(material["tex_path"] if change == "source" else material["file_path"])
    if change == "missing":
        path.unlink()
    elif change == "symlink":
        replacement = path.with_suffix(".retained")
        path.rename(replacement)
        path.symlink_to(replacement)
    else:
        path.write_bytes(b"changed external bytes")
    with pytest.raises(PortalDataError):
        service.store.resolve_bound_material(
            ref, entry["material_ref"], question=question, page_context=context
        )


@pytest.mark.parametrize(
    "token",
    [
        "/private/arbitrary.pdf",
        "0" * 64,
        {"material_ref": "0" * 64, "file_path": "/private/arbitrary.pdf"},
    ],
)
def test_only_the_opaque_fixed_reference_is_accepted(bound_material_page, token):
    service, _, issue = bound_material_page
    question = field()
    ref, context = issue([question])
    with pytest.raises(PortalDataError, match="固定材料引用"):
        service.store.resolve_bound_material(ref, token, question=question, page_context=context)


@pytest.mark.parametrize("change", ["generation", "job", "record"])
def test_old_reference_never_resolves_changed_scope(bound_material_page, change):
    service, _, issue = bound_material_page
    question = field()
    ref, context = issue([question])
    token = next(
        row["material_ref"]
        for row in service.store.assistance_delivery(ref, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )
    if change == "generation":
        ref["generation"] += 1
    elif change == "job":
        ref["binding"]["application_id"] = "f" * 32
    else:
        state = service.store.load()
        state["jobs"][0]["materials"][0]["text"] += " changed"
        service.store.save(state)
    with pytest.raises(PortalDataError):
        service.store.resolve_bound_material(ref, token, question=question, page_context=context)


@pytest.mark.parametrize(
    "change",
    ["marker", "draft_path", "type", "disabled", "readonly", "multiple", "file_count", "accept"],
)
def test_native_target_must_identify_one_current_file_control(bound_material_page, change):
    service, _, issue = bound_material_page
    service.store.cover_letter_exporter = file_export
    question = field(kind="file", accept=".pdf")
    ref, context = issue([question])
    token = next(
        row["material_ref"]
        for row in service.store.assistance_delivery(ref, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )
    target = context["data"]["fields"][0]["material_target"]
    if change == "marker":
        target["worker_field"] = "another-control"
    elif change == "draft_path":
        target["draft_path"] = "other.destination"
    elif change == "type":
        target["type"] = "text"
    elif change == "accept":
        target["accept"] = ".docx"
    elif change == "file_count":
        target["file_count"] = 1
    else:
        target[change] = True
    with pytest.raises(PortalDataError):
        service.store.resolve_bound_material(ref, token, question=question, page_context=context)


def test_resume_reference_reads_only_current_bound_file(bound_material_page):
    service, _, issue = bound_material_page
    question = field("resume", kind="file", question="Resume", resume=True, accept=".pdf")
    ref, context = issue([question], prepare=False)
    entry = next(
        row
        for row in service.store.assistance_delivery(ref, page_context=context)["materials"]
        if row["kind"] == "resume"
    )
    result = service.store.resolve_bound_material(
        ref, entry["material_ref"], question=question, page_context=context
    )
    job = service.store.load()["jobs"][0]
    assert result["bytes"] == Path(job["file_path"]).read_bytes()
    assert result["sha256"] == job["file_sha256"]
    assert result["material_id"] == "resume"


@pytest.mark.parametrize("change", ["bytes", "path", "destination", "accept", "limit"])
def test_resume_rejects_wrong_bytes_path_or_destination(bound_material_page, change, tmp_path):
    service, _, issue = bound_material_page
    question = field("resume", kind="file", question="Resume", resume=True, accept=".pdf")
    ref, context = issue([question], prepare=False)
    entry = next(
        row
        for row in service.store.assistance_delivery(ref, page_context=context)["materials"]
        if row["kind"] == "resume"
    )
    state = service.store.load()
    job = state["jobs"][0]
    if change == "bytes":
        Path(job["file_path"]).write_bytes(b"changed PDF")
    elif change == "path":
        another = tmp_path / "unbound.pdf"
        another.write_bytes(Path(job["file_path"]).read_bytes())
        job["file_path"] = str(another)
        service.store.save(state)
    elif change == "destination":
        question["resume"] = False
        question["question"] = "Cover letter"
    elif change == "accept":
        question["accept"] = ".docx"
        context["data"]["fields"][0]["material_target"]["accept"] = ".docx"
    else:
        question["max_bytes"] = 1
    with pytest.raises(PortalDataError):
        service.store.resolve_bound_material(
            ref, entry["material_ref"], question=question, page_context=context
        )


def test_changed_fixed_source_is_refused_without_catalog_or_author_fallback(bound_material_page):
    service, fixed, issue = bound_material_page
    question = field()
    ref, context = issue([question])
    entry = next(
        row
        for row in service.store.assistance_delivery(ref, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )
    fixed["sources"]["items"][0]["text"] = "Changed outside the adopted source archive."
    with pytest.raises(PortalDataError) as error:
        service.store.resolve_bound_material(
            ref, entry["material_ref"], question=question, page_context=context
        )
    assert error.value.code == "material_reference_invalid"
    invalid = next(
        row
        for row in service.store.assistance_delivery(ref, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )
    assert invalid["reason"] == "material_input_changed"


def test_no_letter_entrance_does_not_gate_ordinary_assistance(bound_material_page):
    service, fixed, issue = bound_material_page
    fixed["cover_letter"] = {"status": "queued"}
    ref, context = issue([])
    delivery = service.store.assistance_delivery(ref, page_context=context)
    letter = next(row for row in delivery["materials"] if row["kind"] == "cover_letter")
    assert letter["status"] == "unavailable"
    assert letter["reason"] == "no_delivery_field"
    assert "material_ref" not in letter
    assert service.store.load()["control"] == "running"


def test_known_pdf_failure_is_preserved_without_a_ready_token(bound_material_page):
    service, _, issue = bound_material_page

    def failed_export(*args, **kwargs):
        raise PortalDataError("prism_unavailable", "Synthetic known failure.", 409)

    service.store.cover_letter_exporter = failed_export
    ref, context = issue([field(kind="file")])
    rows = service.store.assistance_delivery(ref, page_context=context)["materials"]
    letter = next(row for row in rows if row["kind"] == "cover_letter")
    # Flow's PDF stage failed: the field has no material and no Worker retry.
    assert letter["status"] == "failed"
    assert letter["reason"] == "prism_unavailable"
    assert "material_id" not in letter and "recovery" not in letter
    assert "material_ref" not in letter


@pytest.mark.parametrize("kind", ["resume", "cover_letter"])
def test_catalog_does_not_publish_tokens_for_changed_actual_file_bytes(bound_material_page, kind):
    service, _, issue = bound_material_page
    service.store.cover_letter_exporter = file_export
    ref, _ = issue([field(kind="file")])
    job = service.store.load()["jobs"][0]
    source = job if kind == "resume" else job["materials"][0]
    Path(source["file_path"]).write_bytes(b"changed actual PDF bytes")
    rows = service.store.assistance_delivery(ref)["materials"]
    invalid = next(row for row in rows if row["kind"] == kind)
    assert invalid["status"] == "needs_recheck"
    assert invalid["reason"] == "material_changed"
    assert "material_ref" not in invalid
