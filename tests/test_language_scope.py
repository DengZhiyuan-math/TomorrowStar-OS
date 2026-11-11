"""Language facts keep their confirmed scope through real application entrypoints."""

import base64

import pytest

from career_evidence_graph.application_information import condition_from_library
from career_evidence_graph.application_worker import WorkerService
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.fixture
def language_job(tmp_path, monkeypatch):
    applications = tmp_path / "applications"
    applications.mkdir()
    service = WorkerService(ApplicationStore(applications), tmp_path / "worker", live=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    app = service.store.applications.create_application(
        {
            "company": "Synthetic scope",
            "role_title": "Engineer",
            "status": "drafting",
            "application_strategy": "batch",
            "job_description": "German B2 required.",
            "url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001",
        }
    )
    return service, app


def prepare_language_job(service, app):
    return service.request(
        "prepare",
        {
            "jobs": [
                {
                    "application_id": app["id"],
                    "revision": app["revision"],
                    "country": "CHE",
                    "filename": "resume.pdf",
                    "file_base64": base64.b64encode(b"%PDF-1.4 synthetic").decode(),
                }
            ]
        },
    )


@pytest.mark.parametrize("scope_kind", ["application_id", "company", "country"])
def test_job_language_exception_reaches_prepare_and_field_reuse(language_job, scope_kind):
    service, app = language_job
    context = {"application_id": app["id"], "company": app["company"], "country": "CHE"}
    for scope, value in [({}, "A1"), ({scope_kind: context[scope_kind]}, "B2")]:
        service.store.answers.put_answer(
            {
                "question": "German proficiency CEFR",
                "value": value,
                "scope": scope,
                "state": "confirmed",
            }
        )
    library = {"status": "available", "records": service.store.library()}
    assert (
        condition_from_library("German B2 required", app | {"country": "CHE"}, library)["status"]
        == "supported"
    )

    prepared = prepare_language_job(service, app)

    assert prepared["jobs"][0]["status"] == "queued"
    current = service.store.load()["jobs"][0]
    assert service.store.resolve({"question": "German proficiency CEFR"}, current)[0] == "B2"
    ApplicationRunner(service.store, None).check_inputs(current)


def test_incomparable_language_scopes_wait_before_prepare(language_job):
    service, app = language_job
    for scope, value in [({"company": app["company"]}, "B2"), ({"country": "CHE"}, "C1")]:
        service.store.answers.put_answer(
            {"question": "German level", "value": value, "scope": scope, "state": "confirmed"}
        )
    library = {"status": "available", "records": service.store.library()}
    assert (
        condition_from_library("German B2 required", app | {"country": "CHE"}, library)["status"]
        == "needs_input"
    )
    with pytest.raises(PortalDataError) as error:
        prepare_language_job(service, app)
    assert error.value.code == "language_information_required"
    assert service.store.load()["jobs"] == []
    assert not list(service.store.root.rglob("*.pdf"))


def test_lower_job_exception_does_not_inherit_a_higher_global_level(language_job):
    service, app = language_job
    for scope, value in [({}, "C1"), ({"application_id": app["id"]}, "A1")]:
        service.store.answers.put_answer(
            {"question": "German level", "value": value, "scope": scope, "state": "confirmed"}
        )
    library = {"status": "available", "records": service.store.library()}
    assert condition_from_library("German B2 required", app, library)["status"] == "conflict"
    with pytest.raises(PortalDataError) as error:
        prepare_language_job(service, app)
    assert error.value.code == "job_requirement_mismatch"
    assert service.store.load()["jobs"] == []
    assert not list(service.store.root.rglob("*.pdf"))

    other = service.store.applications.create_application(
        {
            "company": "Synthetic other",
            "role_title": "Engineer",
            "application_strategy": "batch",
            "job_description": "German B2 required.",
            "url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000002",
        }
    )
    assert condition_from_library("German B2 required", other, library)["status"] == "supported"
    assert prepare_language_job(service, other)["jobs"][0]["status"] == "queued"
    current = service.store.load()["jobs"][0]
    assert service.store.resolve({"question": "German level"}, current)[0] == "C1"
    ApplicationRunner(service.store, None).check_inputs(current)


def test_new_language_conflict_stops_action_check_without_touching_page_or_pdf(language_job):
    service, app = language_job
    service.store.answers.put_answer(
        {"question": "German level", "value": "B2", "scope": {}, "state": "confirmed"}
    )
    prepare_language_job(service, app)
    current = service.store.load()["jobs"][0]
    before = service.store.path.read_bytes()
    pdfs = {path: path.read_bytes() for path in service.store.root.rglob("*.pdf")}
    service.store.answers.put_answer(
        {
            "question": "German proficiency CEFR",
            "value": "C1",
            "scope": {},
            "state": "confirmed",
        }
    )
    with pytest.raises(PortalDataError) as error:
        ApplicationRunner(service.store, None).check_inputs(current)
    assert error.value.code == "language_information_required"
    assert service.store.resolve({"question": "German level"}, current) is None
    assert service.store.path.read_bytes() == before
    assert {path: path.read_bytes() for path in service.store.root.rglob("*.pdf")} == pdfs
