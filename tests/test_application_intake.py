"""Synthetic Gmail intake saves documentary jobs without application workers."""

import json
import threading
import time

import pytest

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


def message(identifier="mail-one", links=None):
    return {
        "message_id": identifier,
        "thread_id": "thread-one",
        "subject": "Recommended roles",
        "body_text": "A recommendation summary, not a complete job description.",
        "body_completeness": "full",
        "links": links or ["https://www.linkedin.com/comm/jobs/view/12345?trackingId=email"],
    }


def page(url, status="available", completeness="full"):
    return {
        "capture_id": "captured-page",
        "url": url,
        "final_url": url,
        "body_text": "Build services. Requirements: Python and Linux.",
        "acquisition_status": status,
        "jd_completeness": completeness,
        "source_format": "job_posting",
        "redirects": [],
        "job_fields": {"title": "Systems Engineer", "company": "Synthetic Labs"},
    }


def ready(service):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = service.snapshot()
        if state["status"] != "running":
            return state
        time.sleep(0.005)
    pytest.fail("Synthetic intake did not finish")


@pytest.fixture
def applications(tmp_path):
    path = tmp_path / "applications"
    path.mkdir()
    return ApplicationStore(path)


def test_explicit_refresh_reads_fetches_and_automatically_saves_application(applications, tmp_path):
    reads, fetches = [], []

    def reader(directory, *, max_results):
        assert not directory.exists()
        reads.append(max_results)
        directory.mkdir()
        return {"status": "readable", "emails": [message()], "provenance": {"source": "synthetic"}}

    def fetcher(url):
        fetches.append(url)
        return page(url)

    service = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=reader, fetcher=fetcher
    )
    try:
        assert reads == [] and fetches == []
        initial = service.refresh()
        assert initial["status"] == "running"
        state = ready(service)
        assert state["status"] == "complete"
        assert reads == [3]
        assert fetches == ["https://www.linkedin.com/jobs/view/12345"]
        assert len(applications.list_applications()) == 1
        recommendation = state["recommendations"][0]
        assert recommendation["jd_completeness"] == "full"
        selected = service.select(recommendation["id"], recommendation["revision"])
        assert selected["created"] is False
        assert selected["application"]["company"] == "Synthetic Labs"
        assert len(applications.list_applications()) == 1
        runs = list((tmp_path / "intake" / "runs").iterdir())
        assert len(runs) == 1
        assert (runs[0] / "reader-result.json").is_file()
        assert (runs[0] / "source-chain.json").is_file()
        chain = json.loads((runs[0] / "source-chain.json").read_text())
        assert chain["reader_result_revision"] == digest(
            json.loads((runs[0] / "reader-result.json").read_text())
        )
        assert chain["sources"][0]["page_capture_revision"] == digest(
            json.loads((runs[0] / chain["sources"][0]["page_path"]).read_text())
        )
    finally:
        service.close()


def test_repeated_refresh_while_reader_is_running_does_not_start_another_read(
    applications, tmp_path
):
    entered, release = threading.Event(), threading.Event()
    reads = []

    def reader(directory, **kwargs):
        reads.append(directory)
        entered.set()
        assert release.wait(2)
        return {"status": "no_matches", "emails": [], "provenance": {}}

    service = ApplicationIntakeService(applications, tmp_path / "intake", reader=reader)
    try:
        first = service.refresh(max_results=1, max_candidates=2)
        assert entered.wait(1)
        second = service.refresh(max_results=4, max_candidates=5)
        assert second["run_id"] == first["run_id"]
        assert second["max_results"] == 1
        release.set()
        assert ready(service)["status"] == "no_matches"
        assert len(reads) == 1
        assert applications.list_applications() == []
    finally:
        release.set()
        service.close()


@pytest.mark.parametrize(
    "status,completeness",
    [("available", "excerpt"), ("login_required", "unknown"), ("expired", "unknown")],
)
def test_unavailable_full_jd_keeps_mail_context_and_does_not_infer_job_facts(
    applications, tmp_path, status, completeness
):
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *args, **kwargs: {
            "status": "readable",
            "emails": [message()],
            "provenance": {},
        },
        fetcher=lambda url: page(url, status, completeness),
    )
    try:
        service.refresh()
        state = ready(service)
        assert state["status"] == "complete"
        record = state["recommendations"][0]
        assert record["company"] == record["role_title"] == record["job_description"] == ""
        assert record["context"] == "Recommended roles"
        assert record["jd_completeness"] == "unknown"
        assert record["acquisition_status"] == status
        with pytest.raises(PortalDataError) as error:
            service.select(record["id"], record["revision"])
        assert error.value.code == "recommendation_jd_incomplete"
        assert applications.list_applications() == []
    finally:
        service.close()


def test_only_explicit_provider_job_ids_are_fetched_canonically_and_sources_are_preserved(
    applications, tmp_path
):
    fetches = []
    mail_one = message(
        links=[
            "https://www.linkedin.com/comm/jobs/view/12345?trackingId=one",
            "https://ch.indeed.com/rc/clk?jk=0123456789ABCDEF&from=email",
            "https://www.indeed.com/unsubscribe?jk=aaaaaaaaaaaaaaaa",
            "https://www.indeed.com/assessment?jk=bbbbbbbbbbbbbbbb",
            "https://tracking.example.test/?url=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fview%2F99999",
            "https://jobs.lever.co/example/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        ]
    )
    mail_two = message("mail-two", ["https://www.linkedin.com/jobs/view/12345?trackingId=two"])

    def fetcher(url):
        fetches.append(url)
        return page(url) | {"capture_id": f"captured-{len(fetches)}"}

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *args, **kwargs: {
            "status": "readable",
            "emails": [mail_one, mail_two],
            "provenance": {},
        },
        fetcher=fetcher,
    )
    try:
        service.refresh()
        state = ready(service)
        assert state["status"] == "complete"
        assert fetches == [
            "https://www.linkedin.com/jobs/view/12345",
            "https://ch.indeed.com/viewjob?jk=0123456789abcdef",
        ]
        assert len(state["recommendations"]) == 2
        linkedin = next(
            row for row in state["recommendations"] if row["canonical_key"][0] == "linkedin"
        )
        assert {row["message_id"] for row in linkedin["source_messages"]} == {
            "mail-one",
            "mail-two",
        }
        chain = json.loads(
            (tmp_path / "intake" / "runs" / state["run_id"] / "source-chain.json").read_text()
        )
        assert len(chain["sources"]) == 3
        assert len(applications.list_applications()) == 2
    finally:
        service.close()


def test_candidate_limit_does_not_drop_later_mail_provenance_for_an_already_selected_job(
    applications, tmp_path
):
    fetches = []

    def fetcher(url):
        fetches.append(url)
        return page(url)

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *args, **kwargs: {
            "status": "readable",
            "emails": [
                message(
                    links=[
                        "https://www.linkedin.com/jobs/view/12345",
                        "https://www.linkedin.com/jobs/view/67890",
                    ]
                ),
                message("mail-two"),
            ],
            "provenance": {},
        },
        fetcher=fetcher,
    )
    try:
        service.refresh(max_candidates=1)
        state = ready(service)
        assert state["candidate_count"] == 1 and state["skipped_count"] == 1
        assert fetches == ["https://www.linkedin.com/jobs/view/12345"]
        assert len(state["recommendations"][0]["source_messages"]) == 2
    finally:
        service.close()


def test_close_keeps_the_writer_lock_until_the_old_reader_exits_and_restart_does_not_read(
    applications, tmp_path
):
    entered, release = threading.Event(), threading.Event()
    reads, fetches = [], []

    def reader(directory, **kwargs):
        reads.append(directory)
        entered.set()
        assert release.wait(2)
        return {"status": "readable", "emails": [message()], "provenance": {}}

    def fetcher(url):
        fetches.append(url)
        return page(url)

    root = tmp_path / "intake"
    first = ApplicationIntakeService(applications, root, reader=reader, fetcher=fetcher)
    observer = restarted = None
    try:
        first.refresh()
        assert entered.wait(1)
        first.close()
        observer = ApplicationIntakeService(applications, root, reader=reader)
        assert observer.snapshot()["enabled"] is False
        assert observer.snapshot()["status"] == "interrupted"
        with pytest.raises(PortalDataError) as error:
            observer.refresh()
        assert error.value.code == "intake_busy"
        observer.close()
        release.set()
        first.close()
        restarted = ApplicationIntakeService(applications, root, reader=reader)
        assert restarted.snapshot()["enabled"] is True
        assert restarted.snapshot()["status"] == "interrupted"
        assert len(reads) == 1
        assert fetches == []
        assert restarted.snapshot()["recommendations"] == []
        assert applications.list_applications() == []
    finally:
        release.set()
        first.close()
        if observer:
            observer.close()
        if restarted:
            restarted.close()


def test_orphaned_running_state_is_interrupted_without_rereading_or_rewriting_captures(
    applications, tmp_path
):
    root = tmp_path / "intake"
    original = ApplicationIntakeService(applications, root)
    original.close()
    path = root / "intake.json"
    state = json.loads(path.read_text())
    state.update(status="running", run_id="a" * 32, max_results=3, max_candidates=10)
    state["revision"] = digest({key: value for key, value in state.items() if key != "revision"})
    path.write_text(json.dumps(state))

    def forbidden(*args, **kwargs):
        pytest.fail("Restart must not repeat Gmail reads or page acquisition")

    restarted = ApplicationIntakeService(applications, root, reader=forbidden, fetcher=forbidden)
    try:
        recovered = restarted.snapshot()
        assert recovered["status"] == "interrupted"
        assert recovered["error_code"] == "intake_interrupted"
        assert recovered["run_id"] == "a" * 32
        assert not (root / "runs").exists()
    finally:
        restarted.close()


def test_bound_application_root_and_corrupt_state_fail_closed_without_replacing_originals(
    applications, tmp_path
):
    root = tmp_path / "intake"
    service = ApplicationIntakeService(applications, root)
    service.close()
    path = root / "intake.json"
    original = path.read_bytes()
    other_root = tmp_path / "other-applications"
    other_root.mkdir()
    with pytest.raises(PortalDataError) as error:
        ApplicationIntakeService(ApplicationStore(other_root), root)
    assert error.value.code == "intake_invalid"
    assert path.read_bytes() == original
    path.write_bytes(b"{invalid-state")
    with pytest.raises(PortalDataError) as error:
        ApplicationIntakeService(applications, root)
    assert error.value.code == "intake_invalid"
    assert path.read_bytes() == b"{invalid-state"


def test_failed_reader_exposes_only_a_content_free_error_code(applications, tmp_path):
    def reader(*args, **kwargs):
        raise RuntimeError("secret mailbox text and private invitation token")

    service = ApplicationIntakeService(applications, tmp_path / "intake", reader=reader)
    try:
        service.refresh()
        state = ready(service)
        assert state["status"] == "failed" and state["error_code"] == "intake_failed"
        assert "secret" not in json.dumps(state)
        assert applications.list_applications() == []
    finally:
        service.close()


def test_completed_intake_reopens_without_reading_or_changing_original_capture_files(
    applications, tmp_path
):
    root = tmp_path / "intake"
    first = ApplicationIntakeService(
        applications,
        root,
        reader=lambda *args, **kwargs: {
            "status": "readable",
            "emails": [message()],
            "provenance": {},
        },
        fetcher=page,
    )
    first.refresh()
    original = ready(first)
    first.close()
    files = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*.json")}

    def forbidden(*args, **kwargs):
        pytest.fail("Reopen must only inspect persisted captures")

    reopened = ApplicationIntakeService(applications, root, reader=forbidden, fetcher=forbidden)
    try:
        state = reopened.snapshot()
        assert state["status"] == "complete"
        assert state["run_id"] == original["run_id"]
        assert state["recommendations"] == original["recommendations"]
        assert {
            str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*.json")
        } == files
        assert len(applications.list_applications()) == 1
    finally:
        reopened.close()


def test_close_before_reader_admission_rejects_the_queued_read(applications, tmp_path):
    """Writing request.json does not admit external work; close rejects later admission."""
    entered, release = threading.Event(), threading.Event()
    reads = []
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *args, **kwargs: (
            reads.append("read") or {"status": "no_matches", "emails": [], "provenance": {}}
        ),
    )
    artifact = service._artifact

    def paused_artifact(path, payload):
        artifact(path, payload)
        if path.name == "request.json":
            entered.set()
            assert release.wait(2)

    service._artifact = paused_artifact
    try:
        service.refresh()
        assert entered.wait(1)
        service.close()
        assert service.snapshot()["status"] == "interrupted"
        release.set()
        service._thread.join(timeout=1)
        assert not service._thread.is_alive()
        assert reads == []
        assert applications.list_applications() == []
    finally:
        release.set()
        service.close()


@pytest.mark.parametrize("status,run_id", [("interrupted", None), ("running", "b" * 32)])
def test_external_work_is_not_admitted_for_an_interrupted_or_replaced_queued_run(
    applications, tmp_path, status, run_id
):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    reads = []
    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *args, **kwargs: (
            reads.append("read") or {"status": "no_matches", "emails": [], "provenance": {}}
        ),
    )
    artifact, perform = service._artifact, service._perform

    def paused_artifact(path, payload):
        artifact(path, payload)
        if path.name == "request.json":
            entered.set()
            assert release.wait(2)

    def observed_perform(request):
        try:
            return perform(request)
        finally:
            finished.set()

    service._artifact, service._perform = paused_artifact, observed_perform
    try:
        service.refresh()
        assert entered.wait(1)
        with applications.write_lock():
            path = tmp_path / "intake" / "intake.json"
            state = json.loads(path.read_text())
            state["status"] = status
            if run_id:
                state["run_id"] = run_id
            state["revision"] = digest(
                {key: value for key, value in state.items() if key != "revision"}
            )
            path.write_text(json.dumps(state))
        release.set()
        assert finished.wait(1)
        assert reads == []
        assert service.snapshot()["status"] == status
    finally:
        release.set()
        service.close()


def test_regional_indeed_deep_link_uses_its_explicit_job_id_and_original_region(
    applications, tmp_path
):
    fetches = []

    def fetcher(url):
        fetches.append(url)
        return page(url)

    service = ApplicationIntakeService(
        applications,
        tmp_path / "intake",
        reader=lambda *args, **kwargs: {
            "status": "readable",
            "emails": [
                message(
                    links=[
                        "https://de.indeed.com/rc/clk/dl?jk=0123456789abcdef&tracking=synthetic",
                        "https://de.indeed.com/rc/clk/dl/unsubscribe?jk=aaaaaaaaaaaaaaaa",
                        "https://de.indeed.com/assessment?jk=bbbbbbbbbbbbbbbb",
                        "https://-bad.indeed.com/rc/clk/dl?jk=cccccccccccccccc",
                        "https://bad\\de.indeed.com/rc/clk/dl?jk=dddddddddddddddd",
                        "https://de.indeed.com.evil.example/rc/clk/dl?jk=eeeeeeeeeeeeeeee",
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
        assert state["status"] == "complete"
        assert fetches == ["https://de.indeed.com/viewjob?jk=0123456789abcdef"]
        assert len(state["recommendations"]) == 1
    finally:
        service.close()
