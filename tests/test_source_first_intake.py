"""Source-only intake saves synthetic documentary job records without career reads."""

import json
from types import SimpleNamespace

import pytest
from test_application_intake import applications as applications
from test_application_intake import page, ready

from career_evidence_graph.application_intake import ApplicationIntakeService

TEXT = (
    "Company: Synthetic Labs\nTitle: Systems Engineer\n"
    "Location: Zurich\nRequirements: Python and Linux."
)


def fields(text, directory):
    return {
        "company": "Synthetic Labs",
        "role_title": "Systems Engineer",
        "location": "Zurich",
        "deadline": "",
        "salary": "",
        "employment_type": "",
        "posted_date": "",
        "is_full_jd": True,
    }


def test_pasted_jd_is_saved_without_a_link_or_materials_and_is_idempotent(applications, tmp_path):
    calls = []

    def extractor(text, directory):
        calls.append(text)
        return fields(text, directory)

    service = ApplicationIntakeService(applications, tmp_path / "intake", extractor=extractor)
    try:
        service.ingest(text=TEXT, request_id="a" * 32)
        state = ready(service)
        assert state["job"]["status"] == "saved"
        saved = applications.get_application(state["job"]["application_id"])
        assert saved["company"] == "Synthetic Labs"
        assert saved["url"] == "" and saved["source"] == "pasted-jd"
        assert saved["job_description"] == TEXT
        service.ingest(text=TEXT, request_id="a" * 32)
        assert len(applications.list_applications()) == len(calls) == 1
    finally:
        service.close()


def test_missing_identity_keeps_source_draft_without_inventing_fields(applications, tmp_path):
    service = ApplicationIntakeService(
        applications, tmp_path / "intake", extractor=lambda *_: fields("", None) | {"company": ""}
    )
    try:
        service.ingest(text=TEXT, request_id="b" * 32)
        state = ready(service)
        assert state["job"]["status"] == "needs_input"
        assert state["job"]["missing_fields"] == ["company"]
        assert applications.list_applications() == []
        assert list((tmp_path / "intake" / "runs").glob("*/source.json"))
    finally:
        service.close()


def test_url_uses_complete_structured_page_and_preserves_location(applications, tmp_path):
    def fetcher(url):
        return page(url) | {
            "job_fields": {
                "company": "Synthetic Labs",
                "title": "Systems Engineer",
                "location": "Zurich",
            }
        }

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        fetcher=fetcher,
        extractor=lambda *_: pytest.fail("structured page needs no model"),
    )
    try:
        service.ingest(url="https://jobs.synthetic.example/engineer", request_id="c" * 32)
        result = ready(service)
        assert result["job"]["status"] == "saved"
        assert applications.get_application(result["job"]["application_id"])["location"] == "Zurich"
    finally:
        service.close()


def test_jd_extractor_rejects_ungrounded_facts_and_disables_tools(tmp_path, monkeypatch):
    from career_evidence_graph.application_jd_extract import extract_job_fields

    calls, commands = [], []
    monkeypatch.setattr(
        "career_evidence_graph.application_jd_extract.subprocess.run",
        lambda argv, **_options: commands.append(argv),
    )

    def runner(config, prompt, **options):
        calls.append(options)
        assert config.workspace == tmp_path
        assert config.sandbox == "read-only"
        assert "SOURCE_JSON" in prompt and TEXT in json.loads(prompt.split("SOURCE_JSON:\n")[1])
        options["runner"](["codex", "exec", "synthetic"], cwd=tmp_path)
        return SimpleNamespace(
            structured_result=fields("", None) | {"company": "Invented Inc"},
            model_dump=lambda **_: {"synthetic": True},
        )

    with pytest.raises(Exception, match="原文"):
        extract_job_fields(TEXT, tmp_path, runner=runner)
    assert callable(calls[0]["runner"])
    assert "features.apps=false" in commands[0]
    assert "features.shell_tool=false" in commands[0]
    assert 'web_search="disabled"' in commands[0]


def test_mail_full_jd_is_organized_and_saved_without_source_refetch(applications, tmp_path):
    from test_application_intake import message

    mail = message() | {
        "body_text": TEXT,
        "body_scope": "job_description",
        "body_completeness": "full",
    }
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_args, **_kwargs: {"status": "readable", "emails": [mail], "provenance": {}},
        fetcher=lambda *_: pytest.fail("full JD needs no refetch"),
        extractor=fields,
    )
    try:
        service.refresh()
        state = ready(service)
        assert state["status"] == "complete"
        saved = applications.list_applications()
        assert len(saved) == 1 and saved[0]["job_description"] == TEXT
        service.refresh()
        ready(service)
        assert len(applications.list_applications()) == 1
    finally:
        service.close()


def test_gmail_acquisition_automatically_saves_documentary_job(applications, tmp_path):
    from test_application_intake import message

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_args, **_kwargs: {
            "status": "readable",
            "emails": [message()],
            "provenance": {},
        },
        fetcher=page,
    )
    try:
        service.refresh()
        state = ready(service)
        assert len(applications.list_applications()) == 1
        assert state["recommendations"][0]["selection_status"] == "saved"
    finally:
        service.close()


def test_unknown_application_write_reconciles_locally_without_external_retry(
    applications, tmp_path, monkeypatch
):
    calls = []
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        extractor=lambda text, path: calls.append(text) or fields(text, path),
    )
    real_create = applications.create_application

    def uncertain_create(*args, **kwargs):
        real_create(*args, **kwargs)
        raise OSError("synthetic lost response after write")

    monkeypatch.setattr(applications, "create_application", uncertain_create)
    try:
        service.ingest(text=TEXT, request_id="f" * 32)
        state = ready(service)
        assert state["job"]["status"] == "needs_recheck"
        assert len(applications.list_applications()) == 1
        replay = service.ingest(text=TEXT, request_id="f" * 32)
        assert replay["job"]["status"] == "needs_recheck" and len(calls) == 1
        reconciled = service.reconcile_job("f" * 32)
        assert reconciled["job"]["status"] == "saved"
        assert len(applications.list_applications()) == len(calls) == 1
    finally:
        service.close()


def test_reopening_an_interrupted_extraction_does_not_replay(applications, tmp_path):
    import threading

    entered, release = threading.Event(), threading.Event()

    def extractor(text, directory):
        entered.set()
        assert release.wait(3)
        return fields(text, directory)

    root = tmp_path / "intake"
    service = ApplicationIntakeService(applications, root, extractor=extractor)
    try:
        service.ingest(text=TEXT, request_id="1" * 32)
        assert entered.wait(1)
        service.close()
        release.set()
        service._thread.join(2)
        assert applications.list_applications() == []
        reopened = ApplicationIntakeService(
            applications, root, extractor=lambda *_: pytest.fail("reopen cannot replay")
        )
        try:
            state = reopened.snapshot()
            assert state["status"] == "interrupted"
            assert state["job"]["status"] == "needs_recheck"
            assert (root / "runs" / state["run_id"] / "input.json").is_file()
            recovered = reopened.reconcile_job("1" * 32)
            assert recovered["job"]["status"] == "failed"
            assert recovered["job"]["error_code"] == "intake_interrupted_before_save"
            assert applications.list_applications() == []
            reopened.extractor = fields
            reopened.ingest(text=TEXT, request_id="4" * 32)
            assert ready(reopened)["job"]["status"] == "saved"
            assert len(applications.list_applications()) == 1
        finally:
            reopened.close()
    finally:
        release.set()
        service.close()


def test_changed_source_cannot_claim_new_facts_were_saved_over_prior_record(applications, tmp_path):
    title = ["Systems Engineer"]

    def fetcher(url):
        return page(url) | {
            "body_text": "Requirements: Python and Linux. " + title[0],
            "job_fields": {"company": "Synthetic Labs", "title": title[0]},
        }

    service = ApplicationIntakeService(applications, tmp_path / "intake", fetcher=fetcher)
    try:
        service.ingest(url="https://jobs.synthetic.example/engineer", request_id="2" * 32)
        assert ready(service)["job"]["status"] == "saved"
        title[0] = "Changed Engineer"
        service.ingest(url="https://jobs.synthetic.example/engineer", request_id="3" * 32)
        state = ready(service)
        assert state["job"]["status"] != "saved"
        assert state["job"]["error_code"] == "intake_source_changed"
        assert applications.list_applications()[0]["role_title"] == "Systems Engineer"
    finally:
        service.close()


def test_multi_identity_mail_fetches_each_job_without_spreading_mail_facts(applications, tmp_path):
    from test_application_intake import message

    links = ["https://www.linkedin.com/jobs/view/12345", "https://www.linkedin.com/jobs/view/67890"]
    mail = message(links=links) | {
        "body_text": TEXT,
        "body_scope": "job_description",
        "body_completeness": "full",
    }
    fetched = []

    def fetcher(url):
        fetched.append(url)
        suffix = url.rsplit("/", 1)[-1]
        return page(url) | {
            "body_text": "Complete page requirements for " + suffix,
            "job_fields": {"company": "Company " + suffix, "title": "Role " + suffix},
        }

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_args, **_kwargs: {"status": "readable", "emails": [mail], "provenance": {}},
        fetcher=fetcher,
        extractor=lambda *_: pytest.fail("ambiguous mail must use each page"),
    )
    try:
        service.refresh()
        assert ready(service)["status"] == "complete"
        assert fetched == links
        assert {row["company"] for row in applications.list_applications()} == {
            "Company 12345",
            "Company 67890",
        }
        assert all(row["job_description"] != TEXT for row in applications.list_applications())
    finally:
        service.close()


def test_updated_gmail_jd_keeps_old_note_and_exposes_source_conflict(applications, tmp_path):
    from test_application_intake import message

    current = [TEXT]

    def reader(*_args, **_kwargs):
        mail = message(identifier="mail-" + str(len(current[0]))) | {
            "body_text": current[0],
            "body_scope": "job_description",
            "body_completeness": "full",
        }
        return {"status": "readable", "emails": [mail], "provenance": {}}

    service = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=reader, extractor=fields
    )
    try:
        service.refresh()
        assert ready(service)["status"] == "complete"
        original = applications.list_applications()[0]
        current[0] += "\nSalary: CHF 125000."
        service.refresh()
        state = ready(service)
        assert state["status"] == "partial"
        assert state["error_code"] == "recommendation_source_conflict"
        assert state["recommendations"][0]["selection_status"] == "source_conflict"
        assert state["recommendations"][0]["job_description"] == current[0]
        assert applications.get_application(original["id"])["revision"] == original["revision"]
    finally:
        service.close()


@pytest.mark.parametrize(
    "extra,expected",
    [
        ("", "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/"),
        ("\nRelated role: https://www.linkedin.com/jobs/view/67890", ""),
        (
            "\nCompany: https://www.synthetic.example/",
            "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/",
        ),
    ],
)
def test_explicit_pasted_apply_link_requires_one_job_identity(
    applications, tmp_path, extra, expected
):
    url = "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/"
    text = TEXT + "\nApply at: " + url + extra
    service = ApplicationIntakeService(applications, tmp_path / "intake", extractor=fields)
    try:
        service.ingest(text=text, request_id="5" * 32)
        state = ready(service)
        assert state["job"]["status"] == "saved"
        saved = applications.get_application(state["job"]["application_id"])
        assert saved["url"] == state["job"]["fields"]["url"] == expected
        assert saved["job_description"] == text
    finally:
        service.close()


def test_reconcile_does_not_clear_saved_location_conflict(applications, tmp_path):
    service = ApplicationIntakeService(applications, tmp_path / "intake", extractor=fields)
    try:
        service.ingest(text=TEXT, request_id="6" * 32)
        first = ready(service)
        saved = applications.get_application(first["job"]["application_id"])
        changed = applications.update_application(
            saved["id"], {"location": "Basel"}, saved["revision"]
        )
        service.ingest(text=TEXT, request_id="7" * 32)
        conflict = ready(service)
        assert conflict["job"]["status"] == "needs_recheck"
        reconciled = service.reconcile_job("7" * 32)
        assert reconciled["job"]["status"] == "needs_recheck"
        assert reconciled["job"]["error_code"] == "recommendation_source_conflict"
        assert reconciled["recommendations"][0]["selection_status"] == "source_conflict"
        assert applications.get_application(saved["id"])["revision"] == changed["revision"]
    finally:
        service.close()


def test_retargeted_application_is_not_saved_by_prior_selection_receipt(applications, tmp_path):
    url = "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/"
    other = "https://apply.workable.com/synthetic-employer/j/SYNTHETIC2/apply/"
    text = TEXT + "\nApply at: " + url
    service = ApplicationIntakeService(applications, tmp_path / "intake", extractor=fields)
    try:
        service.ingest(text=text, request_id="b" * 32)
        first = ready(service)
        saved = applications.get_application(first["job"]["application_id"])
        changed = applications.update_application(saved["id"], {"url": other}, saved["revision"])
        service.ingest(text=text, request_id="c" * 32)
        conflict = ready(service)
        assert conflict["job"]["status"] == "needs_recheck"
        assert conflict["recommendations"][0]["selection_status"] == "source_conflict"
        reconciled = service.reconcile_job("c" * 32)
        assert reconciled["job"]["status"] == "needs_recheck"
        assert applications.get_application(saved["id"])["revision"] == changed["revision"]
    finally:
        service.close()
