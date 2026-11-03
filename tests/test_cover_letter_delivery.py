"""One adopted body crosses text/file entrances without repeating its author."""

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest
from test_application_worker import service as service
from test_supplemental_material_module import materials
from test_supplemental_material_module import prepared as prepared
from test_supplemental_materials import source_data
from test_tectonic_compiler import native_pdf_inspector as native_pdf_inspector

from career_evidence_graph.application_materials import (
    application_binding,
    cover_letter_requirements,
    material_kind,
)
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest

TEMPLATE = (
    "\\documentclass{article}\n\\begin{document}\nDear Hiring Team,\n\n"
    "% BEGIN LETTER BODY\n% END LETTER BODY\n\nSincerely,\\\\\nSynthetic Applicant\n"
    "\\end{document}\n"
)


def field(identifier="letter", *, kind="textarea", required=False, **changes):
    return {
        "id": identifier,
        "type": kind,
        "question": "Cover letter",
        "required": required,
        "value": "",
        "valid": True,
        "filename": "",
        "file_sha256": None,
        "resume": False,
        **changes,
    }


@pytest.fixture
def modern(prepared, tmp_path, monkeypatch):
    from career_evidence_graph import application_materials

    service, job, batch = prepared
    application = service.store.applications.get_application(job["application_id"])
    content = {
        "schema_version": "cover-letter-content/v1",
        "application_id": application["id"],
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
    result = {
        "id": "body",
        "attempt_id": "author",
        "kind": "cover_letter",
        "status": "ready",
        "actor": "system",
        "content": content,
        "content_revision": content["revision"],
        "source_binding": {
            "application": application_binding(application),
            "sources": source_data()["items"],
        },
    }
    fixed = {
        "application": application,
        "sources": source_data(),
        "cover_letter": {"status": "ready", "result": result},
    }
    service.store.material_inputs = lambda unused: deepcopy(fixed)
    job["workflow"] = "single"
    state = service.store.load()
    state["jobs"][0]["workflow"] = "single"
    service.store.save(state)
    template = tmp_path / "private-template.tex"
    template.write_text(TEMPLATE)
    service.store.cover_letter_template = template
    monkeypatch.setattr(
        application_materials, "run_codex_exec", lambda *args, **kw: pytest.fail("repeat author")
    )
    return prepared, fixed


@pytest.mark.parametrize(
    "label", ["Cover letter", "Motivation letter", "Lettre de motivation", "Anschreiben", "求职信"]
)
def test_letter_identity_does_not_depend_on_file_or_text(label):
    assert material_kind(field(question=label)) == "cover_letter"
    assert material_kind(field(kind="file", question=label)) == "cover_letter"
    assert material_kind(field(question="Why this company?")) == "motivation_text"


def test_requirement_projection_preserves_unverified_and_explicit_jd():
    app = {"id": "job", "job_description": "Build services."}
    assert cover_letter_requirements(app, {"fields": []})["requirement"] == "unverified"
    assert (
        cover_letter_requirements(app, {"fields": [], "requirements_verified": True})["requirement"]
        == "none"
    )
    app["job_description"] += " Please submit a cover letter."
    requirement = cover_letter_requirements(app, {"fields": []})
    assert requirement["requirement"] == "required"
    assert requirement["jd_requirements"][0]["origin"] == "jd"


def test_required_file_and_optional_text_do_not_require_duplicate_delivery():
    requirement = cover_letter_requirements(
        {"id": "job", "job_description": "Build services."},
        {"fields": [field(), field("file", kind="file", required=True)]},
    )
    assert requirement["selected_fields"] == [["file", ""]]


def test_text_preferred_over_optional_file_without_pdf_or_author(modern):
    prepared, fixed = modern
    service, job, batch = prepared
    service.store.cover_letter_exporter = lambda *a, **kw: pytest.fail("unneeded PDF")
    assert materials(prepared).prepare(
        job, batch, {"fields": [field(), field("file", kind="file")]}
    )
    saved = service.store.load()["jobs"][0]
    assert len(saved["materials"]) == 1
    letter = saved["materials"][0]
    assert letter["content_revision"] == fixed["cover_letter"]["result"]["content_revision"]
    assert letter["text"].startswith("Dear Hiring Team,\n\nBuilt Python")
    assert letter["text"].endswith("Sincerely,\nSynthetic Applicant")
    assert "file_path" not in letter
    assert service.store.resolve(field(), saved)[0] == letter["text"]


@pytest.mark.parametrize("kind", ["textarea", "file"])
def test_role_slot_uses_fixed_job_for_both_delivery_methods(modern, kind):
    from career_evidence_graph.application_cover_letter import ROLE_TITLE_SLOT

    prepared, fixed = modern
    service, job, batch = prepared
    path = service.store.cover_letter_template
    template = path.read_text().replace(
        "Dear Hiring Team,\n\n",
        "% BEGIN LETTER OPENING\nDear Hiring Team,\n\nI am writing to apply for "
        + ROLE_TITLE_SLOT
        + ".\n% END LETTER OPENING\n\n",
    )
    path.write_text(template)
    builds = []

    def export(directory, content, bound_template):
        builds.append(bound_template)
        assert ROLE_TITLE_SLOT not in bound_template
        directory.mkdir(parents=True)
        pdf = directory / "letter.pdf"
        pdf.write_bytes(b"synthetic PDF fixture")
        return {
            "file_path": str(pdf),
            "filename": "cover-letter.pdf",
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        }

    service.store.cover_letter_exporter = export
    assert materials(prepared).prepare(job, batch, {"fields": [field(kind=kind)]})
    saved = service.store.load()["jobs"][0]["materials"][0]
    role = fixed["application"]["role_title"]
    assert "I am writing to apply for " + role + "." in saved["text"]
    assert ROLE_TITLE_SLOT not in saved["text"]
    assert len(builds) == (1 if kind == "file" else 0)


def test_file_only_builds_once_and_reuses_adopted_body(modern):
    prepared, _ = modern
    service, job, batch = prepared
    builds = []

    def export(directory, content, template):
        builds.append(content["revision"])
        directory.mkdir(parents=True)
        pdf = directory / "letter.pdf"
        pdf.write_bytes(b"synthetic PDF fixture")
        return {
            "file_path": str(pdf),
            "filename": "cover-letter.pdf",
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        }

    service.store.cover_letter_exporter = export
    observed = {"fields": [field(kind="file")]}
    assert materials(prepared).prepare(job, batch, observed)
    assert materials(prepared).prepare(job, batch, observed)
    assert len(builds) == 1
    saved = service.store.load()["jobs"][0]["materials"][0]
    assert Path(saved["file_path"]).is_file()


def test_modern_source_verification_consumes_the_same_complete_packet_projection(modern):
    prepared, fixed = modern
    service, job, batch = prepared
    source = deepcopy(source_data()["items"][0])
    source["record_context"] = {"fact_id": "complete-fact", "experience_id": "experience"}
    packet = {"status": "complete", "sources": {source["source_id"]: source}}
    packet["revision"] = digest(packet)
    fixed["material_packet"] = packet
    fixed["cover_letter"]["result"]["source_binding"]["sources"] = [source]
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    assert service.store.resolve(field(), job) is not None
    packet["sources"][source["source_id"]]["text"] = "Unversioned change"
    with pytest.raises(PortalDataError) as error:
        service.store.resolve(field(), job)
    assert error.value.code == "retrieval_execution_incomplete"


def test_external_letter_tex_change_preserves_source_and_pdf_and_stops_reuse(modern):
    prepared, _ = modern
    service, job, batch = prepared

    def exporter(directory, content, template):
        directory.mkdir(parents=True)
        pdf, tex = directory / "letter.pdf", directory / "main.tex"
        pdf.write_bytes(b"synthetic PDF")
        tex.write_text("Synthetic exact compiled source")
        return {
            "file_path": str(pdf),
            "filename": "cover-letter.pdf",
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "tex_path": str(tex),
            "tex_sha256": hashlib.sha256(tex.read_bytes()).hexdigest(),
        }

    service.store.cover_letter_exporter = exporter
    observed = {"fields": [field(kind="file")]}
    assert materials(prepared).prepare(job, batch, observed)
    material = job["materials"][0]
    tex, pdf = Path(material["tex_path"]), Path(material["file_path"])
    tex.write_text("Human changed the LaTeX body")
    assert service.store.verify_material(material, job) == material
    with pytest.raises(PortalDataError) as source_error:
        service.store.verify_material_source(material)
    assert source_error.value.code == "cover_letter_tex_changed"
    with pytest.raises(PortalDataError) as error:
        service.store.field_material(observed["fields"][0], job)
    assert error.value.code == "cover_letter_tex_changed"
    assert tex.read_text() == "Human changed the LaTeX body"
    assert pdf.read_bytes() == b"synthetic PDF"


def test_both_explicit_required_entrances_keep_same_body_revision(modern):
    prepared, _ = modern
    service, job, batch = prepared

    def export(directory, content, template):
        directory.mkdir(parents=True)
        path = directory / "letter.pdf"
        path.write_bytes(b"synthetic")
        return {
            "file_path": str(path),
            "filename": "cover-letter.pdf",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    service.store.cover_letter_exporter = export
    assert materials(prepared).prepare(
        job,
        batch,
        {
            "fields": [
                field(required=True),
                field("file", kind="file", required=True),
            ]
        },
    )
    rows = service.store.load()["jobs"][0]["materials"]
    assert len(rows) == 2 and len({row["content_revision"] for row in rows}) == 1


@pytest.mark.parametrize("status", ["queued", "running", "failed"])
def test_optional_pending_or_known_failed_body_does_not_block_resume(modern, status):
    prepared, fixed = modern
    service, job, batch = prepared
    fixed["cover_letter"] = {"status": status, "error_code": "known_failure"}
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    assert service.store.load()["jobs"][0]["cover_letter_delivery"]["status"] == status
    assert not job.get("materials")


def test_unknown_body_stops_even_optional_or_no_entrance(modern):
    prepared, fixed = modern
    service, job, batch = prepared
    fixed["cover_letter"] = {"status": "needs_recheck"}
    with pytest.raises(PortalDataError, match="求职信"):
        materials(prepared).prepare(job, batch, {"fields": []})
    assert service.store.load()["jobs"][0]["cover_letter_delivery"]["status"] == "needs_recheck"


def test_required_pending_body_waits_but_manual_page_text_satisfies_it(modern):
    prepared, fixed = modern
    service, job, batch = prepared
    fixed["cover_letter"] = {"status": "failed"}
    assert not materials(prepared).prepare(job, batch, {"fields": [field(required=True)]})
    manual = field(required=True, value="User's own letter")
    assert materials(prepared).prepare(job, batch, {"fields": [manual]})
    saved = service.store.load()["jobs"][0]
    assert saved["manual_fields"]["letter"]["value"] == "User's own letter"
    assert saved["cover_letter_delivery"]["status"] == "ready"


def test_nonempty_page_letter_and_file_are_retained_without_template(modern):
    prepared, _ = modern
    service, job, batch = prepared
    service.store.cover_letter_template = None
    assert materials(prepared).prepare(
        job,
        batch,
        {
            "fields": [
                field(required=True, value="Human letter"),
                field("file", kind="file", required=True, filename="human.pdf", file_sha256="hash"),
            ]
        },
    )
    saved = service.store.load()["jobs"][0]
    assert saved["manual_fields"]["letter"]["value"] == "Human letter"
    assert saved["materials"][0]["status"] == "manual"


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"max_length": 10}, "cover_letter_text_too_long"),
        ({"kind": "file", "accept": ".docx"}, "cover_letter_format_unsupported"),
    ],
)
def test_known_unsupported_optional_delivery_preserves_body(modern, changes, reason):
    prepared, fixed = modern
    service, job, batch = prepared
    revision = fixed["cover_letter"]["result"]["content_revision"]
    assert materials(prepared).prepare(job, batch, {"fields": [field(**changes)]})
    saved = service.store.load()["jobs"][0]
    assert saved["cover_letter_delivery"]["reason"] == reason
    assert fixed["cover_letter"]["result"]["content_revision"] == revision


def test_required_jd_letter_can_appear_in_later_form_step(modern):
    prepared, fixed = modern
    _, job, batch = prepared
    fixed["application"]["job_description"] += " Please submit a cover letter."
    assert materials(prepared).prepare(job, batch, {"fields": [], "navigation": {"next": "step2"}})
    assert not materials(prepared).prepare(job, batch, {"fields": []})


def test_new_page_field_reuses_body_without_old_field_receipt(modern):
    prepared, _ = modern
    service, job, batch = prepared
    assert materials(prepared).prepare(job, batch, {"fields": [field("first-page")]})
    assert materials(prepared).prepare(job, batch, {"fields": [field("second-page")]})
    rows = service.store.load()["jobs"][0]["materials"]
    assert len(rows) == 2 and rows[0]["id"] != rows[1]["id"]
    assert rows[0]["content_revision"] == rows[1]["content_revision"]
    assert all("readback" not in row for row in rows)


def revised_body(fixed):
    result = fixed["cover_letter"]["result"]
    content = result["content"]
    content["paragraphs"][0].update(
        text="Human technical explanation.", origin="human", protected=True
    )
    content["revision"] = digest(
        {key: value for key, value in content.items() if key != "revision"}
    )
    result["content_revision"] = content["revision"]


def test_updated_canonical_body_rebinds_blank_field_and_preserves_history(modern):
    prepared, fixed = modern
    service, job, batch = prepared
    observed = {"fields": [field()]}
    assert materials(prepared).prepare(job, batch, observed)
    old = deepcopy(job["materials"][0])
    revised_body(fixed)
    assert materials(prepared).prepare(job, batch, observed)
    saved = service.store.load()["jobs"][0]
    assert saved["material_history"] == [old]
    assert saved["materials"][0]["id"] != old["id"]
    assert "Human technical explanation." in saved["materials"][0]["text"]


def test_updated_canonical_body_never_overwrites_existing_page_text(modern):
    prepared, fixed = modern
    service, job, batch = prepared
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    old = deepcopy(job["materials"][0])
    revised_body(fixed)
    with pytest.raises(PortalDataError) as error:
        materials(prepared).prepare(job, batch, {"fields": [field(value=old["text"])]})
    assert error.value.code == "cover_letter_page_version_changed"
    assert service.store.load()["jobs"][0]["materials"][0] == old
    assert service.store.verify_material(old, job) == old
    with pytest.raises(PortalDataError) as send_error:
        service.store.field_material(field(), job)
    assert send_error.value.code == "material_changed"


def test_legacy_letter_text_retains_kind_and_history_without_migration(modern):
    prepared, _ = modern
    service, job, batch = prepared
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    state = service.store.load()
    legacy = state["jobs"][0]["materials"][0]
    legacy["kind"] = "motivation_text"
    for key in ("letter_content", "content_revision", "letter_attempt_id"):
        legacy.pop(key)
    service.store.save(state)
    job["materials"] = deepcopy(state["jobs"][0]["materials"])
    assert service.store.resolve(field(), job)[0] == legacy["text"]
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    assert service.store.load()["jobs"][0]["materials"][0] == legacy


@pytest.mark.parametrize(
    "status,code",
    [
        ("conflict", "material_fact_conflict"),
        ("needs_recheck", "material_consistency_needs_recheck"),
    ],
)
def test_material_pair_conflict_or_unknown_stops_execution_but_preserves_history(
    modern, status, code
):
    prepared, fixed = modern
    service, job, batch = prepared
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    old = deepcopy(job["materials"][0])
    fixed["material_consistency"] = {"status": status}
    assert service.store.verify_material(old, job) == old
    with pytest.raises(PortalDataError) as error:
        materials(prepared).prepare(job, batch, {"fields": []})
    assert error.value.code == code
    with pytest.raises(PortalDataError):
        service.store.resolve(field(), job)


def test_pending_pair_defers_optional_letter_only_and_cannot_send_existing_row(modern):
    prepared, fixed = modern
    service, job, batch = prepared
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    fixed["material_consistency"] = {"status": "running"}
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    assert service.store.resolve(field(), job) is None
    assert job["cover_letter_delivery"]["reason"] == "material_consistency_pending"
    assert not materials(prepared).prepare(job, batch, {"fields": [field(required=True)]})
    fixed["material_consistency"]["status"] = "passed"
    assert materials(prepared).prepare(job, batch, {"fields": [field(required=True)]})
    assert service.store.resolve(field(), job) is not None


def test_old_pair_pass_cannot_authorize_new_human_content(modern):
    prepared, fixed = modern
    _, job, batch = prepared
    fixed["material_consistency"] = {
        "status": "passed",
        "letter_content_revision": fixed["cover_letter"]["result"]["content_revision"],
    }
    revised_body(fixed)
    with pytest.raises(PortalDataError) as error:
        materials(prepared).prepare(job, batch, {"fields": [field()]})
    assert error.value.code == "material_consistency_needs_recheck"


@pytest.mark.parametrize("failure_code", ["resume_export_failed", "prism_not_running"])
def test_explicit_file_retry_rebuilds_only_known_failed_file(modern, failure_code):
    prepared, fixed = modern
    service, job, batch = prepared
    builds = []

    def exporter(directory, content, template):
        builds.append(directory.name)
        if len(builds) == 1:
            raise PortalDataError(failure_code, "Synthetic known compile failure", 409)
        directory.mkdir(parents=True)
        path = directory / "letter.pdf"
        path.write_bytes(b"synthetic PDF")
        return {
            "file_path": str(path),
            "filename": "cover-letter.pdf",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    service.store.cover_letter_exporter = exporter
    observed = {"fields": [field(kind="file")]}
    assert materials(prepared).prepare(job, batch, observed)
    assert materials(prepared).prepare(job, batch, observed)
    assert len(builds) == 1
    state = service.store.load()
    state["control"] = "paused"
    failed = deepcopy(state["jobs"][0]["materials"][0])
    service.store.save(state)
    service.store.check_single = lambda *args, **kwargs: True
    payload = {
        "application_id": job["application_id"],
        "material_id": failed["id"],
        "expected_material_revision": digest(failed),
        "request_id": "b" * 32,
    }
    service.request("retry-cover-letter-file", payload)
    service.request("retry-cover-letter-file", payload)
    state = service.store.load()
    assert state["jobs"][0]["materials"] == []
    assert state["jobs"][0]["material_history"] == [failed]
    state["control"] = "running"
    service.store.save(state)
    job = state["jobs"][0]
    assert materials((service, job, batch)).prepare(job, batch, observed)
    assert len(builds) == 2 and builds[0] != builds[1]
    assert (
        job["materials"][0]["content_revision"]
        == fixed["cover_letter"]["result"]["content_revision"]
    )


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("failure_code", ["prism_not_running", "prism_unavailable"])
def test_prebuild_capability_failure_is_known_and_does_not_repeat_build(
    modern, required, failure_code
):
    prepared, fixed = modern
    service, job, batch = prepared
    calls = []

    def unavailable(*args):
        calls.append(args)
        raise PortalDataError(failure_code, "Synthetic prebuild capability unavailable", 409)

    service.store.cover_letter_exporter = unavailable
    observed = {"fields": [field(kind="file", required=required)]}
    assert materials(prepared).prepare(job, batch, observed) is (not required)
    current = service.store.load()["jobs"][0]
    failed = current["materials"][0]
    assert failed["status"] == "failed" and failed["error_code"] == failure_code
    assert fixed["cover_letter"]["status"] == "ready"
    assert materials((service, current, batch)).prepare(current, batch, observed) is (not required)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,error_code",
    [
        ("needs_recheck", "letter_export_needs_recheck"),
        ("failed", "letter_pdf_pages_unverified"),
    ],
)
def test_file_retry_cannot_clear_unknown_results(modern, status, error_code):
    prepared, fixed = modern
    service, job, _ = prepared
    state = service.store.load()
    state["control"] = "paused"
    material = {
        "id": "file-attempt",
        "kind": "cover_letter",
        "status": status,
        "error_code": error_code,
        "letter_content": deepcopy(fixed["cover_letter"]["result"]["content"]),
    }
    state["jobs"][0]["materials"] = [material]
    service.store.save(state)
    service.store.check_single = lambda *args, **kwargs: True
    with pytest.raises(PortalDataError) as error:
        service.request(
            "retry-cover-letter-file",
            {
                "application_id": job["application_id"],
                "material_id": material["id"],
                "expected_material_revision": digest(material),
                "request_id": "b" * 32,
            },
        )
    assert error.value.code == "material_retry_changed"
    assert service.store.load()["jobs"][0]["materials"] == [material]


@pytest.mark.parametrize("incomplete", [False, True])
def test_file_recheck_adopts_only_complete_local_build_without_repeating_it(
    modern, monkeypatch, incomplete
):
    from test_cover_letter_content import Compiler

    from career_evidence_graph import application_cover_letter as letter

    prepared, fixed = modern
    service, job, batch = prepared
    compiler = Compiler(unknown=incomplete)
    reads = []

    # Both compile and the newly connected readback seam remain explicitly offline.
    def unavailable(binding):
        reads.append(binding)
        raise PortalDataError("letter_export_needs_recheck", "Synthetic incomplete build", 409)

    compiler.read_compiled = unavailable
    service.store.cover_letter_client = compiler
    atomic_write = letter.helper.atomic_write_json

    def lose_publication(path, value):
        if path.name == "export.json":
            raise OSError("Synthetic lost local publication")
        return atomic_write(path, value)

    monkeypatch.setattr(letter.helper, "atomic_write_json", lose_publication)
    service.store.cover_letter_exporter = lambda directory, content, template: (
        letter.export_cover_letter_pdf(
            directory, content, template, client=compiler, pdf_inspector=lambda raw: 1
        )
    )
    with pytest.raises(PortalDataError):
        materials(prepared).prepare(job, batch, {"fields": [field(kind="file")]})
    assert compiler.calls == 1
    state = service.store.load()
    state["control"] = "paused"
    state["jobs"][0]["status"] = "needs_recheck"
    unknown = deepcopy(state["jobs"][0]["materials"][0])
    assert unknown["status"] == "needs_recheck"
    service.store.save(state)
    service.store.check_single = lambda *args, **kwargs: True
    service.store.cover_letter_pdf_inspector = lambda raw: 1
    service.store.cover_letter_exporter = lambda *args: pytest.fail("repeated build")
    payload = {
        "application_id": job["application_id"],
        "material_id": unknown["id"],
        "expected_material_revision": digest(unknown),
        "request_id": "c" * 32,
    }
    directory = service.store.root / "materials" / unknown["id"]
    before_files = {
        str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in directory.rglob("*")
        if path.is_file()
    }
    if incomplete:
        with pytest.raises(PortalDataError) as error:
            service.request("recheck-cover-letter-file", payload)
        assert error.value.code == "letter_export_needs_recheck"
        assert service.store.load()["jobs"][0]["materials"] == [unknown]
    else:
        service.request("recheck-cover-letter-file", payload)
        service.request("recheck-cover-letter-file", payload)
        recovered = service.store.load()["jobs"][0]
        material = recovered["materials"][0]
        assert material["status"] == "ready" and material["id"] == unknown["id"]
        assert material["content_revision"] == fixed["cover_letter"]["result"]["content_revision"]
        assert recovered["material_file_rechecks"][0]["previous_material"] == unknown
        assert len(recovered["material_file_rechecks"]) == 1
        assert before_files == {
            str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in directory.rglob("*")
            if path.is_file()
        }
    assert len(reads) == int(incomplete)
    assert compiler.calls == 1


@pytest.mark.worker_browser
def test_optional_cover_file_is_generated_and_uploaded_when_sources_are_available(
    tmp_path, monkeypatch
):
    from test_generic_worker import FIELDS, native_form
    from test_supplemental_materials import application, selection
    from worker_preview_support import advance_until

    from career_evidence_graph import application_materials, application_resume

    calls = []

    def runner(*args, **kwargs):
        calls.append(1)
        return selection(*args, **kwargs)

    monkeypatch.setattr(application_materials, "run_codex_exec", runner)
    raw = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
    monkeypatch.setattr(application_resume, "export_pdf", lambda html, pdf: pdf.write_bytes(raw))
    html = (
        "<form>" + FIELDS + '<label>Cover letter<input id="cover" type="file"></label>'
        '<button type="submit">Submit</button></form>'
    )
    with native_form(tmp_path, monkeypatch, html) as (service, engine, job, posts):
        service.store.material_sources = source_data
        app = service.store.applications.get_application(job["application_id"])
        updated = service.store.applications.update_application(
            job["application_id"],
            {"job_description": application()["job_description"]},
            app["revision"],
        )
        state = service.store.load()
        state["jobs"][0]["revision"] = updated["revision"]
        service.store.save(state)
        current = advance_until(service, engine, lambda row: row["status"] == "ready_for_review")
        assert current["status"] == "ready_for_review", current
        assert current["materials"][0]["kind"] == "cover_letter"
        assert (
            engine.pages[job["application_id"]].locator("#cover").evaluate("e=>e.files[0].name")
            == "cover-letter.pdf"
        )
        assert len(calls) == 2 and posts == []


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize(
    "accept",
    [
        "image/*",
        "text/*",
        ".pdfx",
        "application/pdfx",
        ".docx",
        "image/*, text/*",
        "application/pdfx, .pdfx",
    ],
)
def test_pdf_accept_rejects_complete_unsupported_items_before_build(modern, required, accept):
    prepared, fixed = modern
    service, job, batch = prepared
    revised_body(fixed)
    body = deepcopy(fixed["cover_letter"])
    service.store.cover_letter_exporter = lambda *a, **kw: pytest.fail("unsupported PDF built")
    observed = {"fields": [field(kind="file", required=required, accept=accept)]}
    assert materials(prepared).prepare(job, batch, observed) is (not required)
    saved = service.store.load()["jobs"][0]
    material = saved["materials"][0]
    assert material["status"] == "failed"
    assert material["error_code"] == "cover_letter_format_unsupported"
    assert saved["cover_letter_delivery"]["reason"] == "cover_letter_format_unsupported"
    assert material["letter_content"] == body["result"]["content"]
    assert fixed["cover_letter"] == body
    assert not list((service.store.root / "materials").glob("*/project"))


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize(
    "accept",
    [
        ".pdf",
        "application/pdf",
        " .PDF ",
        " APPLICATION/PDF ",
        "image/*, .pdf",
        ".docx, application/pdf",
        "",
        "*",
        "*/*",
    ],
)
def test_pdf_accept_supported_items_and_existing_unrestricted_fields(modern, required, accept):
    prepared, _ = modern
    service, job, batch = prepared
    builds = []

    def export(directory, content, template):
        builds.append(content["revision"])
        directory.mkdir(parents=True)
        pdf = directory / "letter.pdf"
        pdf.write_bytes(b"synthetic PDF fixture")
        return {
            "file_path": str(pdf),
            "filename": "cover-letter.pdf",
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        }

    service.store.cover_letter_exporter = export
    assert materials(prepared).prepare(
        job, batch, {"fields": [field(kind="file", required=required, accept=accept)]}
    )
    assert len(builds) == 1
    assert service.store.load()["jobs"][0]["materials"][0]["status"] == "ready"


def test_optional_unsupported_file_does_not_clear_unknown_delivery(modern):
    prepared, fixed = modern
    service, job, batch = prepared
    service.store.cover_letter_exporter = lambda *a, **kw: pytest.fail("unknown file repeated")
    assert materials(prepared).prepare(job, batch, {"fields": [field()]})
    state = service.store.load()
    state["jobs"][0]["materials"][0].update(
        status="needs_recheck", error_code="letter_export_needs_recheck"
    )
    service.store.save(state)
    job.update(deepcopy(state["jobs"][0]))
    with pytest.raises(PortalDataError) as caught:
        materials(prepared).prepare(job, batch, {"fields": [field(kind="file", accept="image/*")]})
    assert caught.value.code == "cover_letter_needs_recheck"
    assert service.store.load()["jobs"][0]["materials"] == state["jobs"][0]["materials"]


def stable_letter_observation(worker, job, batch, question, monkeypatch):
    """Capture a real stable field snapshot before checking its upload contract."""
    from types import SimpleNamespace

    from career_evidence_graph import application_form_runner as form_runner

    page = object()
    run = "current-letter-form"
    state = worker.store.load()
    state["current_job_id"] = job["application_id"]
    state["runtime"] = {
        "id": run,
        "applications_root": state["applications_root"],
        "pid": 1,
        "started_at": 0.0,
        "observed_at": 0.0,
        "source": {"sha256": "a" * 64, "files": {"synthetic.py": "b" * 64}},
    }
    worker.store.save(state)
    now = [0.0]
    monkeypatch.setattr(form_runner, "time", SimpleNamespace(time=lambda: now[0]))
    observed = {
        "fields": [deepcopy(question)],
        "stage": "documents",
        "document_token": "same-document",
        "parser": {"status": "complete"},
        "validation_errors": [],
    }
    runner = SimpleNamespace(
        store=worker.store,
        run_id=run,
        page_ids={page: "current-letter-page"},
        pages={job["application_id"]: page},
        persist=worker.store.save,
        observe=lambda p, j: deepcopy(observed),
    )
    for value in (0.0, 0.25, 0.5):
        now[0] = value
        form_runner.capture(runner, page, job, batch, deepcopy(observed))
    assert job["form_state"]["parser"]["status"] == "stable"
    assert not job["form_state"].get("intervention_pending")
    assert form_runner.check_snapshot(runner, page, job, observed)["fields"] == [question]
    return runner, page, observed


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("accept", ["image/*", "text/*", ".pdfx", "application/pdfx"])
def test_ready_pdf_reuse_obeys_current_stable_accept_without_losing_body(
    modern, monkeypatch, required, accept
):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from test_cover_letter_content import Compiler

    from career_evidence_graph import application_form_runner as form_runner
    from career_evidence_graph import application_prism
    from career_evidence_graph import application_worker_browser as browser

    ready, fixed = modern
    worker, job, batch = ready
    revised_body(fixed)
    body = deepcopy(fixed["cover_letter"])
    compiler = Compiler()
    worker.store.cover_letter_client = compiler
    monkeypatch.setattr(
        application_prism, "PrismClient", lambda *a, **kw: pytest.fail("No real Prism")
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_resume_versions.TectonicCompiler",
        lambda *a, **kw: pytest.fail("No real Prism"),
    )
    assert materials(ready).prepare(
        job, batch, {"fields": [field(kind="file", required=required, accept=".pdf")]}
    )
    original = deepcopy(job["materials"][0])
    raw = Path(original["file_path"]).read_bytes()
    changed = field(kind="file", required=required, accept=accept)
    runner, page, observed = stable_letter_observation(worker, job, batch, changed, monkeypatch)
    assert materials(ready).prepare(job, batch, observed) is (not required)
    current = worker.store.load()["jobs"][0]
    assert current["cover_letter_delivery"]["status"] == "failed"
    assert current["cover_letter_delivery"]["reason"] == "cover_letter_format_unsupported"
    assert current["materials"] == [original]
    assert fixed["cover_letter"] == body and Path(original["file_path"]).read_bytes() == raw
    if required:
        with pytest.raises(PortalDataError) as rejected:
            worker.store.field_material(changed, current)
        assert rejected.value.code == "cover_letter_format_unsupported"
    else:
        assert worker.store.field_material(changed, current) is None
    captured = []
    monkeypatch.setattr(
        browser.hosted_ats,
        "control",
        lambda *a: SimpleNamespace(set_input_files=lambda value: captured.append(value)),
    )

    @contextmanager
    def dispatch(row, batch_id, intent, observed=None):
        form_runner.check_snapshot(runner, page, row, observed)
        yield

    runner.drafts = {}
    runner.workable = set()
    runner.verified_intents = lambda row: []
    runner.authorize = lambda *a: True
    runner.dispatch_current = dispatch
    if required:
        with pytest.raises(PortalDataError) as rejected:
            browser.ApplicationRunner.upload_supplement(runner, page, current, batch, observed)
        assert rejected.value.code == "cover_letter_format_unsupported"
    else:
        browser.ApplicationRunner.upload_supplement(runner, page, current, batch, observed)
    assert captured == [] and compiler.calls == 1


@pytest.mark.parametrize("required", [False, True])
def test_ready_pdf_reuse_obeys_current_file_size_without_rebuilding(modern, required):
    from test_cover_letter_content import Compiler

    ready, fixed = modern
    worker, job, batch = ready
    revised_body(fixed)
    body = deepcopy(fixed["cover_letter"])
    compiler = Compiler()
    worker.store.cover_letter_client = compiler
    question = field(kind="file", required=required, accept=".pdf")
    assert materials(ready).prepare(job, batch, {"fields": [question]})
    original = deepcopy(job["materials"][0])
    question["max_bytes"] = Path(original["file_path"]).stat().st_size - 1
    assert materials(ready).prepare(job, batch, {"fields": [question]}) is (not required)
    current = worker.store.load()["jobs"][0]
    assert current["cover_letter_delivery"]["reason"] == "letter_file_too_large"
    assert current["materials"] == [original] and fixed["cover_letter"] == body
    if required:
        with pytest.raises(PortalDataError) as rejected:
            worker.store.field_material(question, current)
        assert rejected.value.code == "letter_file_too_large"
    else:
        assert worker.store.field_material(question, current) is None
    assert compiler.calls == 1


@pytest.mark.parametrize("accept", [" .PDF ", "image/*, APPLICATION/PDF", ""])
def test_retained_pdf_becomes_deliverable_again_without_another_build(modern, accept):
    from test_cover_letter_content import Compiler

    ready, fixed = modern
    worker, job, batch = ready
    revised_body(fixed)
    body = deepcopy(fixed["cover_letter"])
    compiler = Compiler()
    worker.store.cover_letter_client = compiler
    question = field(kind="file", required=True, accept=".pdf")
    assert materials(ready).prepare(job, batch, {"fields": [question]})
    original = deepcopy(job["materials"][0])
    assert not materials(ready).prepare(job, batch, {"fields": [question | {"accept": "image/*"}]})
    allowed = question | {
        "accept": accept,
        "max_bytes": Path(original["file_path"]).stat().st_size,
    }
    assert materials(ready).prepare(job, batch, {"fields": [allowed]})
    current = worker.store.load()["jobs"][0]
    assert current["cover_letter_delivery"]["status"] == "ready"
    assert worker.store.field_material(allowed, current) == original
    assert current["materials"] == [original] and fixed["cover_letter"] == body
    assert compiler.calls == 1


def test_actual_retained_non_pdf_attachment_is_preserved_without_pdf_rules(modern):
    ready, fixed = modern
    worker, job, batch = ready
    worker.store.cover_letter_exporter = lambda *a, **kw: pytest.fail("retained image rebuilt")
    question = field(
        kind="file",
        required=True,
        accept="image/*",
        filename="human-letter.png",
        file_sha256="human-file-hash",
        max_bytes=1,
    )
    body = deepcopy(fixed["cover_letter"])
    assert materials(ready).prepare(job, batch, {"fields": [question]})
    current = worker.store.load()["jobs"][0]
    assert current["materials"][0]["status"] == "manual"
    assert current["materials"][0]["filename"] == "human-letter.png"
    assert current["materials"][0]["file_sha256"] == "human-file-hash"
    assert current["cover_letter_delivery"]["status"] == "ready"
    assert worker.store.field_material(question, current) is None
    assert fixed["cover_letter"] == body


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("limit", [True, False, "64000", 64_000.5, -1])
def test_unverified_page_size_limits_do_not_become_optional_delivery_success(
    modern, retained, limit
):
    from test_cover_letter_content import Compiler

    ready, fixed = modern
    worker, job, batch = ready
    compiler = Compiler()
    worker.store.cover_letter_client = compiler
    question = field(kind="file", accept=".pdf")
    if retained:
        assert materials(ready).prepare(job, batch, {"fields": [question]})
    original = deepcopy(job.get("materials", []))
    body = deepcopy(fixed["cover_letter"])
    with pytest.raises(PortalDataError) as rejected:
        materials(ready).prepare(job, batch, {"fields": [question | {"max_bytes": limit}]})
    assert rejected.value.code == "cover_letter_file_limit_invalid"
    assert fixed["cover_letter"] == body and compiler.calls == int(retained)
    current = worker.store.load()["jobs"][0]
    if retained:
        assert current["materials"] == original
    else:
        assert current["materials"][0]["status"] == "failed"
        assert current["materials"][0]["file_build_started"] is False


def invalid_pdf(raw):
    raise PortalDataError("resume_pdf_invalid", "Synthetic regex-only rejection", 409)


def lost_build(directory, content, template):
    raise TimeoutError("Synthetic lost build")


@pytest.fixture
def unchecked_letter_build(modern, request):
    """2026-11-03: a built PDF 1.5 letter was left needs_recheck / resume_pdf_invalid."""
    from career_evidence_graph.application_resume_versions import tectonic_executable

    prepared, _ = modern
    service, job, batch = prepared
    native = None
    if request.param == "tectonic":
        if tectonic_executable() is None:
            pytest.skip("tectonic not installed")
        native = request.getfixturevalue("native_pdf_inspector")
    else:
        from test_cover_letter_content import Compiler

        service.store.cover_letter_client = Compiler()
    service.store.cover_letter_pdf_inspector = invalid_pdf
    observed = {"fields": [field(kind="file", accept=".pdf")]}
    assert materials(prepared).prepare(job, batch, observed)
    state = service.store.load()
    # The record as written before resume_pdf_invalid became a known failure.
    state["jobs"][0]["materials"][0]["status"] = "needs_recheck"
    state["jobs"][0]["cover_letter_delivery"]["reason"] = "resume_export_failed"
    service.store.save(state)
    job.update(deepcopy(state["jobs"][0]))
    del service.store.cover_letter_pdf_inspector
    service.store.cover_letter_exporter = lambda *a, **kw: pytest.fail("rebuilt letter")
    directory = service.store.root / "materials" / state["jobs"][0]["materials"][0]["id"]
    assert (directory / "letter.pdf").is_file() and not (directory / "export.json").exists()
    return prepared, observed, directory, native or (lambda raw: 1)


@pytest.mark.parametrize("unchecked_letter_build", ["tectonic", "fake"], indirect=True)
def test_retained_letter_build_is_rechecked_with_the_current_inspector(unchecked_letter_build):
    prepared, observed, directory, inspector = unchecked_letter_build
    service, job, batch = prepared
    service.store.pdf_inspector = inspector
    assert materials(prepared).prepare(job, batch, observed)
    saved = service.store.load()["jobs"][0]
    material = saved["materials"][0]
    assert material["status"] == "ready" and "error_code" not in material
    assert material["page_count"] == 1
    assert (directory / "export.json").is_file()
    assert saved["cover_letter_delivery"]["status"] == "ready"
    assert not saved["cover_letter_delivery"].get("reason")


@pytest.mark.parametrize("unchecked_letter_build", ["fake"], indirect=True)
def test_retained_letter_still_invalid_fails_with_its_current_reason(unchecked_letter_build):
    prepared, observed, directory, _ = unchecked_letter_build
    service, job, batch = prepared
    service.store.pdf_inspector = invalid_pdf
    assert materials(prepared).prepare(job, batch, observed)
    saved = service.store.load()["jobs"][0]
    material = saved["materials"][0]
    assert (material["status"], material["error_code"]) == ("failed", "resume_pdf_invalid")
    assert saved["cover_letter_delivery"]["status"] == "failed"
    assert saved["cover_letter_delivery"]["reason"] == "resume_pdf_invalid"
    assert not (directory / "export.json").exists()


def test_unbuilt_unknown_letter_file_still_needs_recheck(modern):
    prepared, _ = modern
    service, job, batch = prepared
    service.store.cover_letter_exporter = lost_build
    observed = {"fields": [field(kind="file", accept=".pdf")]}
    with pytest.raises(PortalDataError):
        materials(prepared).prepare(job, batch, observed)
    state = service.store.load()
    assert state["jobs"][0]["materials"][0]["status"] == "needs_recheck"
    job.update(deepcopy(state["jobs"][0]))
    with pytest.raises(PortalDataError) as caught:
        materials(prepared).prepare(job, batch, observed)
    assert caught.value.code == "cover_letter_needs_recheck"
    assert service.store.load()["jobs"][0]["materials"] == state["jobs"][0]["materials"]
