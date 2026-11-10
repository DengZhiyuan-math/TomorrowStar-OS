"""Native material outcomes preserve preparation duties without scheduling recovery."""

import pytest
from test_single_application_worker import single_worker as single_worker
from test_supplemental_material_module import materials
from test_worker_bound_material_delivery import bound_material_page as bound_material_page
from test_worker_bound_material_delivery import field
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page

from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize("required", [False, True])
def test_failed_letter_catalog_preserves_original_requirement_and_selected_destinations(
    bound_material_page, required, monkeypatch
):
    service, fixed, issue = bound_material_page
    builds = []

    def failed_export(*args):
        builds.append(args)
        raise PortalDataError("resume_export_failed", "Synthetic known PDF failure", 409)

    service.store.cover_letter_exporter = failed_export
    question = field(kind="file", required=required, accept=".pdf", draft_path="form.letter")
    state = service.store.load()
    job = state["jobs"][0]
    assert materials((service, job, state["batch_id"])).prepare(
        job, state["batch_id"], {"fields": [question]}
    ) is (not required)
    reference, context = issue([question], prepare=False)
    before = service.store.path.read_bytes()
    saved = service.store.load()["jobs"][0]

    def unexpected_write(*args, **kwargs):
        pytest.fail("Catalog projection must not save, build or retry")

    monkeypatch.setattr(service.store, "save", unexpected_write)
    service.store.cover_letter_exporter = unexpected_write
    delivery = service.store.assistance_delivery(reference, page_context=context)
    letter = next(row for row in delivery["materials"] if row["kind"] == "cover_letter")

    assert letter["status"] == "failed" and letter["reason"] == "resume_export_failed"
    assert letter["requirement"] == ("required" if required else "optional")
    assert letter["selected_fields"] == [[question["id"], "form.letter"]]
    assert letter["fields"] == [
        {
            "field_id": question["id"],
            "draft_path": "form.letter",
            "method": "file",
            "required": required,
            "selected": True,
        }
    ]
    assert "material_ref" not in letter
    assert len(builds) == 1 and service.store.path.read_bytes() == before
    letter["fields"][0]["required"] = not required
    letter["selected_fields"].clear()
    assert service.store.load()["jobs"][0] == saved
    assert fixed["cover_letter"]["status"] == "ready"


@pytest.mark.parametrize("status", ["queued", "running", "failed", "needs_recheck"])
def test_no_material_placeholder_keeps_required_selected_file_and_original_author_outcome(
    bound_material_page, status
):
    service, fixed, issue = bound_material_page
    fixed["cover_letter"] = {"status": status, "error_code": "original_author_outcome"}
    questions = [
        field("letter-text"),
        field("letter-file", kind="file", required=True, accept=".pdf", draft_path="letter.file"),
    ]
    state = service.store.load()
    job = state["jobs"][0]
    if status == "needs_recheck":
        with pytest.raises(PortalDataError):
            materials((service, job, state["batch_id"])).prepare(
                job, state["batch_id"], {"fields": questions}
            )
    else:
        assert not materials((service, job, state["batch_id"])).prepare(
            job, state["batch_id"], {"fields": questions}
        )
    reference, context = issue(questions, prepare=False)
    before = service.store.path.read_bytes()
    original = service.store.load()["jobs"][0]["cover_letter_delivery"]
    letter = next(
        row
        for row in service.store.assistance_delivery(reference, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )

    assert letter["status"] == status and letter["reason"] == "original_author_outcome"
    assert letter["source_ref"] == {"record": "cover_letter_delivery"}
    assert letter["requirement"] == "required"
    assert letter["fields"] == original["fields"]
    assert letter["selected_fields"] == [["letter-file", "letter.file"]]
    assert "material_ref" not in letter and "material_id" not in letter
    if status == "needs_recheck":
        assert set(letter["recovery"]) == {"description"}
        assert "原尝试" in letter["recovery"]["description"]
    else:
        assert "recovery" not in letter
    assert service.store.path.read_bytes() == before


def test_other_known_failure_does_not_invent_a_pdf_retry(bound_material_page):
    service, fixed, issue = bound_material_page
    question = field(required=True, max_length=0)
    state = service.store.load()
    job = state["jobs"][0]
    assert not materials((service, job, state["batch_id"])).prepare(
        job, state["batch_id"], {"fields": [question]}
    )
    reference, context = issue([question], prepare=False)
    before = service.store.path.read_bytes()
    letter = next(
        row
        for row in service.store.assistance_delivery(reference, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )

    assert letter["status"] == "failed" and letter["reason"] == "cover_letter_text_too_long"
    assert letter["requirement"] == "required" and letter["required"] is True
    assert "recovery" not in letter and "material_ref" not in letter
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize(
    "failure,error",
    [
        ("resume_export_failed", PortalDataError("resume_export_failed", "Synthetic", 409)),
        ("prism_not_running", PortalDataError("prism_not_running", "Synthetic", 409)),
        ("letter_export_needs_recheck", TimeoutError("Synthetic dispatched PDF result lost")),
    ],
)
def test_flow_pdf_failure_projects_its_reason_without_a_worker_recovery(
    bound_material_page, required, failure, error, monkeypatch
):
    """The PDF is built once in Flow; a failed or unknown build is Flow's to continue."""
    service, fixed, issue = bound_material_page
    builds = []

    def failed_export(*args):
        builds.append(args)
        raise error

    service.store.cover_letter_exporter = failed_export
    question = field(kind="file", required=required, accept=".pdf")
    state = service.store.load()
    job = state["jobs"][0]
    assert materials((service, job, state["batch_id"])).prepare(
        job, state["batch_id"], {"fields": [question]}
    ) is (not required)
    reference, context = issue([question], prepare=False)
    before = service.store.path.read_bytes()

    def unexpected_dispatch(*args, **kwargs):
        pytest.fail("A catalog read must not save, build or retry")

    monkeypatch.setattr(service, "request", unexpected_dispatch)
    monkeypatch.setattr(service.store, "save", unexpected_dispatch)
    letter = next(
        row
        for row in service.store.assistance_delivery(reference, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )

    assert letter["status"] == "failed" and letter["reason"] == failure
    assert "recovery" not in letter and "material_ref" not in letter
    assert len(builds) == 1 and service.store.path.read_bytes() == before
    assert service.store.load()["jobs"][0].get("materials", []) == []
    assert fixed["cover_letter"]["status"] == "ready"


def test_invalid_page_pdf_limit_fails_the_field_without_a_retry(bound_material_page):
    service, _, issue = bound_material_page
    question = field(kind="file", required=True, accept=".pdf", max_bytes=True)
    state = service.store.load()
    job = state["jobs"][0]
    with pytest.raises(PortalDataError) as caught:
        materials((service, job, state["batch_id"])).prepare(
            job, state["batch_id"], {"fields": [question]}
        )
    assert caught.value.code == "cover_letter_file_limit_invalid"
    reference, context = issue([question], prepare=False)
    original = service.store.load()["jobs"][0]["materials"][0]
    letter = next(
        row
        for row in service.store.assistance_delivery(reference, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )
    assert original["status"] == "failed"
    assert letter["status"] == "failed" and letter["reason"] == "cover_letter_file_limit_invalid"
    assert "recovery" not in letter and "material_ref" not in letter
