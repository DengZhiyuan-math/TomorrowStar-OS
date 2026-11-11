"""Capture-first intake keeps jobs durable before mailbox changes and JD reads."""

import pytest
from test_application_intake import applications as applications
from test_application_intake import message, ready

from career_evidence_graph.application_intake import ApplicationIntakeService


def test_capture_only_pages_without_fetching_or_extracting_jds(applications, tmp_path):
    calls = []

    def reader(directory, **options):
        calls.append(options.get("page_token"))
        return {
            "status": "readable",
            "emails": [message("mail-one" if len(calls) == 1 else "mail-two")],
            "provenance": {"next_page_token": "second-page" if len(calls) == 1 else ""},
        }

    def forbidden(*args, **kwargs):
        raise AssertionError("Capture must not fetch or analyze a JD")

    service = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=reader, fetcher=forbidden, extractor=forbidden
    )
    try:
        service.refresh(capture_only=True)
        state = ready(service)
        assert calls == [None, "second-page"]
        assert state["status"] == "complete"
        assert state["progress"]["pages"] == 2
        assert len(state["recommendations"]) == 1
        assert len(state["recommendations"][0]["source_messages"]) == 2
        assert state["progress"]["pending_candidates"] == 1
        assert state["recommendations"][0]["acquisition_checkpoint"] == "not_started"
        assert applications.list_applications() == []
    finally:
        service.close()


def test_mailbox_changes_follow_durable_capture_and_unknown_archive_is_reconciled(
    applications, tmp_path
):
    calls, external = [], {"labeled": False, "archived": False}

    def mailbox(directory, *, message_id, label_name, operation, **kwargs):
        assert message_id == "mail-one" and label_name == "Configured Jobs"
        captured = service.snapshot()["recommendations"]
        assert len(captured) == 1 and captured[0]["source_messages"]
        calls.append(operation)
        if operation == "label":
            external["labeled"] = True
        if operation == "archive":
            external["archived"] = True
            raise TimeoutError("Archive succeeded, response lost")
        return {"status": "complete", **external}

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_a, **_k: {"status": "readable", "emails": [message()], "provenance": {}},
        mailbox=mailbox,
        processed_label="Configured Jobs",
    )
    try:
        service.refresh(capture_only=True)
        first = ready(service)
        assert first["progress"]["mail_captured"] == 1
        assert first["progress"]["mail_labeled"] == 1
        assert first["progress"]["mail_needs_recheck"] == 1
        service.continue_read()
        result = ready(service)
        assert result["progress"]["mail_archived"] == 1
        assert result["progress"]["mail_needs_recheck"] == 0
        assert calls == ["inspect", "label", "inspect", "archive", "inspect"]
        assert len(result["recommendations"]) == 1
    finally:
        service.close()


def test_capture_save_failure_never_changes_mail_and_reuses_retained_read(
    applications, tmp_path, monkeypatch
):
    from career_evidence_graph._vendor import job_apply_store as helper

    calls, reads, failed = [], [], [False]
    original = helper.atomic_write_json

    def write(path, payload):
        if path.name == "recommendations.json" and not failed[0]:
            failed[0] = True
            raise OSError("Synthetic capture write failure")
        return original(path, payload)

    def reader(*_args, **_kwargs):
        reads.append(True)
        return {"status": "readable", "emails": [message()], "provenance": {}}

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=reader,
        processed_label="Configured Jobs",
        mailbox=lambda *_a, **_k: (
            calls.append(True) or {"status": "complete", "labeled": True, "archived": True}
        ),
    )
    try:
        monkeypatch.setattr(helper, "atomic_write_json", write)
        service.refresh(capture_only=True)
        assert ready(service)["status"] == "failed"
        assert calls == []
        service.continue_read()
        result = ready(service)
        assert result["status"] == "complete"
        assert len(result["recommendations"]) == 1
        assert len(reads) == 1
        assert len(calls) == 1
    finally:
        service.close()


def test_checkpoint_save_failure_stops_all_later_mailbox_operations(
    applications, tmp_path, monkeypatch
):
    from career_evidence_graph._vendor import job_apply_store as helper

    original, calls, failed = helper.atomic_write_json, [], [False]

    def write(path, payload):
        if (
            path.name == "intake.json"
            and not failed[0]
            and any(
                row.get("label_status") == "needs_recheck"
                for row in payload.get("mail_processing", {}).values()
            )
        ):
            failed[0] = True
            raise OSError("Synthetic durable checkpoint failure")
        return original(path, payload)

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        processed_label="Configured Jobs",
        reader=lambda *_a, **_k: {
            "status": "readable",
            "emails": [message(), message("mail-two")],
            "provenance": {},
        },
        mailbox=lambda *_a, **options: (
            calls.append((options["message_id"], options["operation"]))
            or {"status": "complete", "labeled": False, "archived": False}
        ),
    )
    try:
        monkeypatch.setattr(helper, "atomic_write_json", write)
        service.refresh(capture_only=True)
        result = ready(service)
        assert result["status"] == "failed"
        assert calls == [("mail-one", "inspect")]
    finally:
        service.close()


def test_incomplete_message_is_saved_without_label_or_archive(applications, tmp_path):
    calls = []
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        processed_label="Configured Jobs",
        reader=lambda *_a, **_k: {
            "status": "readable",
            "emails": [message() | {"body_completeness": "excerpt"}],
            "provenance": {},
        },
        mailbox=lambda *_a, **_k: calls.append(True),
    )
    try:
        service.refresh(capture_only=True)
        result = ready(service)
        assert result["status"] == "partial"
        assert len(result["recommendations"]) == 1
        assert result["progress"]["incomplete_messages"] == 1
        assert result["progress"]["mail_captured"] == 0
        assert calls == []
    finally:
        service.close()


def test_capture_retains_interrupted_next_page_and_existing_unprocessed_jobs(
    applications, tmp_path
):
    calls = []

    def reader(directory, **options):
        calls.append(options.get("page_token"))
        if len(calls) == 2:
            raise TimeoutError("Synthetic next-page interruption")
        return {
            "status": "readable",
            "emails": [message("mail-new", ["https://www.linkedin.com/jobs/view/22222"])],
            "provenance": {"next_page_token": "next" if len(calls) == 1 else ""},
        }

    service = ApplicationIntakeService(applications, tmp_path / "intake", reader=reader)
    try:
        service.store.import_messages(
            [message()],
            [{"message_id": "mail-one", "url": "https://www.linkedin.com/jobs/view/12345"}],
        )
        service.refresh(capture_only=True)
        failed = ready(service)
        assert failed["status"] == "failed" and failed["progress"]["has_more"]
        assert len(failed["recommendations"]) == 2
        assert failed["progress"]["pending_candidates"] == 2
        service.continue_read()
        result = ready(service)
        assert result["status"] == "complete"
        assert calls == [None, "next", "next"]
        assert len(result["recommendations"]) == 2
        assert result["progress"]["pending_candidates"] == 2
    finally:
        service.close()


@pytest.mark.parametrize("first_unknown", [False, True])
def test_same_message_id_in_another_mailbox_has_separate_history_and_progress(
    applications, tmp_path, first_unknown
):
    active, calls = ["a" * 64], []
    external = {
        "a" * 64: {"labeled": False, "archived": False},
        "b" * 64: {"labeled": False, "archived": False},
    }

    def reader(*_args, **_kwargs):
        return {
            "status": "readable",
            "emails": [message()],
            "provenance": {
                "mailbox_identity": active[0],
                "account_identity_status": "verified",
            },
        }

    def mailbox(_directory, *, message_id, operation, expected_mailbox_identity, **_kwargs):
        assert expected_mailbox_identity == active[0]
        assert message_id == "mail-one"
        calls.append((expected_mailbox_identity, operation))
        if first_unknown and expected_mailbox_identity == "a" * 64:
            return {"status": "needs_recheck"}
        actual = external[expected_mailbox_identity]
        if operation == "label":
            actual["labeled"] = True
        if operation == "archive":
            actual["archived"] = True
        return {"status": "complete", **actual}

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=reader,
        mailbox=mailbox,
        processed_label="Configured Jobs",
    )
    try:
        service.refresh(capture_only=True)
        first = ready(service)
        assert first["progress"]["mail_needs_recheck"] == int(first_unknown)
        first_calls = list(calls)
        active[0] = "b" * 64
        service.refresh(capture_only=True)
        second = ready(service)
        assert second["status"] == "complete"
        assert second["progress"]["mail_captured"] == 1
        assert second["progress"]["mail_archived"] == 1
        assert second["progress"]["mail_needs_recheck"] == 0
        assert calls == first_calls + [
            ("b" * 64, operation)
            for operation in (
                "inspect",
                "label",
                "inspect",
                "archive",
                "inspect",
            )
        ]
        sources = second["recommendations"][0]["source_messages"]
        assert {row["mailbox_identity"] for row in sources} == {"a" * 64, "b" * 64}
        assert len({row["capture_id"] for row in sources}) == 2
        active[0] = "a" * 64
        service.refresh(capture_only=True)
        restored = ready(service)
        assert restored["progress"]["mail_captured"] == 1
        assert restored["progress"]["mail_archived"] == int(not first_unknown)
        assert restored["progress"]["mail_needs_recheck"] == int(first_unknown)
    finally:
        service.close()


def test_summary_capture_preserves_complete_jd_documentary_fields(applications, tmp_path):
    description = "Synthetic complete JD. Build and maintain service operations."
    facts = {"deadline": "2026-12-31", "employmentType": "FULL_TIME"}
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_a, **_k: {
            "status": "readable",
            "emails": [message("new-summary")],
            "provenance": {},
        },
    )
    try:
        service.store.import_messages(
            [message("full-jd") | {"body_scope": "job_description", "body_text": description}],
            [
                {
                    "message_id": "full-jd",
                    "url": "https://www.linkedin.com/jobs/view/12345",
                    "company": "Synthetic Labs",
                    "role_title": "Systems Engineer",
                    "job_description": description,
                    "jd_completeness": "full",
                    "documentary_fields": facts,
                }
            ],
        )
        service.refresh(capture_only=True)
        result = ready(service)
        row = result["recommendations"][0]
        assert row["jd_completeness"] == "full"
        assert row["job_description"] == description
        assert row["documentary_fields"] == facts
        assert {source["message_id"] for source in row["source_messages"]} == {
            "full-jd",
            "new-summary",
        }
    finally:
        service.close()
