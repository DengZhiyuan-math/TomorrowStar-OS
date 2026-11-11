"""Synthetic continuation journeys retain ranges, candidates and source checkpoints."""

import pytest
from test_application_intake import applications as applications
from test_application_intake import message, page, ready

from career_evidence_graph.application_gmail import RECOMMENDATION_QUERY
from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture(autouse=True)
def synthetic_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_calendar_range_uses_exact_utc_epoch_boundaries(applications, tmp_path):
    calls = []

    def reader(directory, **scope):
        calls.append(scope)
        return {"status": "no_matches", "emails": [], "provenance": {}}

    service = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=reader, fetcher=page
    )
    try:
        service.refresh(after="2026-10-01", before="2026-10-08")
        state = ready(service)
        assert state["status"] == "no_matches"
        assert calls[0]["query"] == RECOMMENDATION_QUERY.replace(
            "newer_than:7d", "after:1790812800 before:1791417600"
        )
        assert state["progress"]["window"] == "2026-10-01 — 2026-10-08 (UTC)"
    finally:
        service.close()


def test_two_pages_keep_cross_page_sources_without_repeating_completed_jobs(applications, tmp_path):
    reads, fetches = [], []

    def reader(directory, **scope):
        directory.mkdir()
        reads.append(scope)
        second = bool(scope.get("page_token"))
        return {
            "status": "readable",
            "emails": [message("mail-one")]
            if not second
            else [
                message("mail-one"),
                message("mail-two", ["https://www.linkedin.com/jobs/view/67890"]),
            ],
            "provenance": {"next_page_token": None if second else "synthetic-page-two"},
        }

    def fetcher(url):
        fetches.append(url)
        return page(url) | {"capture_id": str(len(fetches))}

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=reader,
        fetcher=fetcher,
    )
    try:
        service.refresh(max_results=3)
        first = ready(service)
        assert first["status"] == "partial" and first["progress"]["has_more"] is True
        service.continue_read(revision=first["revision"])
        second = ready(service)
        assert second["status"] == "complete"
        assert second["progress"]["pages"] == 2
        assert second["message_count"] == 2
        assert reads[1]["page_token"] == "synthetic-page-two"
        assert reads[1]["query"] == reads[0]["query"]
        assert len(fetches) == 2
        assert len(second["recommendations"]) == 2
        assert len(applications.list_applications()) == 2
    finally:
        service.close()


def test_candidate_limit_retains_all_jobs_and_continues_without_rereading_mail(
    applications, tmp_path
):
    reads, fetches = [], []

    def reader(directory, **scope):
        reads.append(scope)
        return {
            "status": "readable",
            "emails": [
                message(
                    links=[
                        f"https://www.linkedin.com/jobs/view/{identifier}"
                        for identifier in (111, 222, 333)
                    ]
                )
            ],
            "provenance": {},
        }

    def fetcher(url):
        fetches.append(url)
        return page(url) | {"capture_id": str(len(fetches))}

    service = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=reader, fetcher=fetcher
    )
    try:
        service.refresh(max_candidates=1)
        state = ready(service)
        assert state["status"] == "partial" and state["progress"]["pending_candidates"] == 2
        assert len(state["recommendations"]) == 3
        service.continue_read()
        state = ready(service)
        assert state["progress"]["pending_candidates"] == 1
        service.continue_read()
        state = ready(service)
        assert state["status"] == "complete"
        assert state["progress"]["source_complete"] == 3
        assert len(reads) == 1 and len(fetches) == 3
    finally:
        service.close()


def test_disconnection_keeps_the_same_next_page_and_previous_completed_jobs(applications, tmp_path):
    reads = []

    def reader(directory, **scope):
        reads.append(scope)
        if len(reads) == 2:
            return {"status": "unavailable", "emails": [], "provenance": {}}
        return {
            "status": "readable",
            "emails": [message(str(len(reads)))],
            "provenance": {"next_page_token": "next-two" if len(reads) == 1 else ""},
        }

    fetches = []
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=reader,
        fetcher=lambda url: fetches.append(url) or page(url),
    )
    try:
        service.refresh()
        ready(service)
        service.continue_read()
        failed = ready(service)
        assert failed["status"] == "unavailable" and failed["message_count"] == 1
        assert failed["progress"]["has_more"] is True
        assert len(failed["recommendations"]) == 1
        service.continue_read()
        result = ready(service)
        assert result["status"] == "complete" and len(reads) == 3
        assert reads[1]["page_token"] == reads[2]["page_token"] == "next-two"
        assert len(fetches) == 1
    finally:
        service.close()


@pytest.mark.parametrize("changed", ["account", "query", "window"])
def test_cursor_scope_changes_fail_before_any_further_read(
    applications, tmp_path, changed, monkeypatch
):
    reads = []

    def reader(directory, **scope):
        reads.append(scope)
        return {
            "status": "readable",
            "emails": [message()],
            "provenance": {"next_page_token": "private-cursor"},
        }

    service = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=reader, fetcher=page
    )
    try:
        service.refresh(query=RECOMMENDATION_QUERY, window_context="window-one")
        before = ready(service)
        options = {}
        if changed == "account":
            monkeypatch.setenv("CODEX_HOME", str(tmp_path / "other-account"))
        elif changed == "query":
            options["query"] = RECOMMENDATION_QUERY.replace("7d", "8d")
        else:
            options["window_context"] = "window-two"
        with pytest.raises(PortalDataError) as error:
            service.continue_read(**options)
        assert error.value.code == "intake_scope_changed"
        assert len(reads) == 1 and service.snapshot()["revision"] == before["revision"]
        assert "private-cursor" not in str(service.snapshot())
    finally:
        service.close()


def test_truncated_mail_remains_explicitly_incomplete_without_a_fake_cursor(applications, tmp_path):
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_a, **_k: {
            "status": "readable",
            "emails": [message() | {"body_completeness": "excerpt"}],
            "provenance": {},
        },
        fetcher=page,
    )
    try:
        service.refresh()
        state = ready(service)
        assert state["status"] == "partial"
        assert state["progress"]["incomplete_messages"] == 1
        assert state["progress"]["can_continue"] is False
    finally:
        service.close()


def test_existing_candidate_can_be_acquired_without_any_gmail_read(applications, tmp_path):
    reads, fetches = [], []
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_a, **_k: reads.append(True) or pytest.fail("No Gmail read permitted"),
        fetcher=lambda url: fetches.append(url) or page(url),
    )
    try:
        record = service.store.import_messages(
            [message()],
            [
                {
                    "message_id": "mail-one",
                    "url": "https://www.linkedin.com/jobs/view/12345",
                }
            ],
        )["recommendations"][0]
        service.acquire(record["id"], record["revision"])
        state = ready(service)
        row = state["recommendations"][0]
        assert row["jd_completeness"] == "full" and row["captured_at"]
        assert reads == [] and len(fetches) == 1
        service.acquire(row["id"], row["revision"])
        assert ready(service)["recommendations"][0]["jd_completeness"] == "full"
        assert len(fetches) == 1
    finally:
        service.close()


def test_redirect_merging_pending_candidates_does_not_strand_the_intake(applications, tmp_path):
    target = "https://www.indeed.com/viewjob?jk=0123456789abcdef"
    calls = []

    def fetcher(url):
        calls.append(url)
        return page(url) | {
            "final_url": target,
            "redirects": [
                {"url": url, "location": target, "status": 302},
            ],
        }

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_a, **_k: {
            "status": "readable",
            "emails": [
                message(
                    links=[
                        "https://www.linkedin.com/jobs/view/10001",
                        target,
                    ]
                )
            ],
            "provenance": {},
        },
        fetcher=fetcher,
    )
    try:
        service.refresh()
        state = ready(service)
        assert state["status"] == "complete" and state["progress"]["pending_candidates"] == 0
        assert len(state["recommendations"]) == 1 and len(calls) == 1
    finally:
        service.close()


def test_unread_range_survives_later_empty_pages(applications, tmp_path):
    reads = []

    def reader(directory, **scope):
        reads.append(scope)
        return {
            "status": "no_matches",
            "emails": [],
            "provenance": {
                "next_page_token": "two" if len(reads) == 1 else "",
                "unread_message_ids": ["not-returned"] if len(reads) == 1 else [],
            },
        }

    service = ApplicationIntakeService(applications, tmp_path / "intake", reader=reader)
    try:
        service.refresh()
        assert ready(service)["progress"]["unread_messages"] == 1
        service.continue_read()
        state = ready(service)
        assert state["status"] == "partial" and state["progress"]["unread_messages"] == 1
    finally:
        service.close()


def test_changed_connector_identity_invalidates_the_cursor_and_retains_prior_jobs(
    applications, tmp_path
):
    calls = []

    def reader(directory, **scope):
        calls.append(scope)
        if len(calls) == 2:
            assert scope["verify_account"] is True
            assert scope["expected_mailbox_identity"] == "a" * 64
            return {
                "status": "unavailable",
                "emails": [],
                "reason": "gmail_account_changed",
                "provenance": {},
            }
        return {
            "status": "readable",
            "emails": [message()],
            "provenance": {
                "next_page_token": "private-next",
                "mailbox_identity": "a" * 64,
                "account_identity_status": "verified",
            },
        }

    service = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=reader, fetcher=page
    )
    try:
        service.refresh()
        ready(service)
        service.continue_read()
        changed = ready(service)
        assert (
            changed["status"] == "unavailable" and changed["error_code"] == "gmail_account_changed"
        )
        assert changed["progress"]["can_continue"] is False
        assert changed["progress"]["has_more"] is False
        assert len(changed["recommendations"]) == 1
        with pytest.raises(PortalDataError) as error:
            service.continue_read()
        assert error.value.code == "intake_scope_changed" and len(calls) == 2
    finally:
        service.close()


def test_one_failed_job_does_not_discard_or_refetch_other_completed_jobs(applications, tmp_path):
    calls = []

    def fetcher(url):
        calls.append(url)
        if url.endswith("111") and len(calls) == 1:
            raise OSError("private failure details")
        return page(url)

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_a, **_k: {
            "status": "readable",
            "emails": [
                message(
                    links=[
                        "https://www.linkedin.com/jobs/view/111",
                        "https://www.linkedin.com/jobs/view/222",
                    ]
                )
            ],
            "provenance": {},
        },
        fetcher=fetcher,
    )
    try:
        service.refresh()
        state = ready(service)
        failed = next(
            r for r in state["recommendations"] if r["acquisition_checkpoint"] == "failed"
        )
        assert state["progress"]["source_complete"] == 1
        assert "private failure" not in str(state)
        service.acquire(failed["id"], failed["revision"], retry=True)
        result = ready(service)
        assert result["progress"]["source_complete"] == 2
        assert calls == [
            "https://www.linkedin.com/jobs/view/111",
            "https://www.linkedin.com/jobs/view/222",
            "https://www.linkedin.com/jobs/view/111",
        ]
    finally:
        service.close()


def test_unknown_job_save_only_reconciles_retained_capture_without_refetch(
    applications,
    tmp_path,
    monkeypatch,
):
    from career_evidence_graph._vendor import job_apply_store as helper

    calls, fail = [], [True]
    original_write = helper.atomic_write_json

    def write(path, payload):
        if (
            path.name == "recommendations.json"
            and fail[0]
            and any(r.get("jd_completeness") == "full" for r in payload.get("recommendations", []))
        ):
            fail[0] = False
            raise OSError("synthetic result save interrupted")
        return original_write(path, payload)

    monkeypatch.setattr(helper, "atomic_write_json", write)
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *_a, **_k: {"status": "readable", "emails": [message()], "provenance": {}},
        fetcher=lambda url: calls.append(url) or page(url),
    )
    try:
        service.refresh()
        state = ready(service)
        assert state["status"] == "failed"
        row = state["recommendations"][0]
        assert row["acquisition_checkpoint"] == "needs_recheck"
        with pytest.raises(PortalDataError) as error:
            service.acquire(row["id"], row["revision"], retry=True)
        assert error.value.code == "intake_source_needs_recheck"
        result = service.reconcile_source(row["id"])
        assert result["recommendations"][0]["acquisition_checkpoint"] == "complete"
        service.continue_read()
        assert ready(service)["status"] == "complete" and len(calls) == 1
    finally:
        service.close()
