"""A task is a bounded handoff, never execution or application acceptance."""

import json

import pytest

from career_evidence_graph.application_automation import (
    UPSTREAM_REVISION,
    prepare_application_task,
)
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

LEVER_URL = "https://jobs.lever.co/example/12345678-1234-1234-1234-123456789abc"


@pytest.fixture
def application_store(tmp_path):
    root = tmp_path / "applications"
    root.mkdir()
    store = ApplicationStore(root)
    record = store.create_application(
        {"company": "Example", "role_title": "Research Engineer", "url": LEVER_URL}
    )
    return store, record


@pytest.mark.parametrize(
    ("url", "platform", "canonical"),
    [
        (LEVER_URL + "/apply?source=alert#form", "lever", LEVER_URL),
        (
            LEVER_URL.replace("jobs.lever.co", "jobs.eu.lever.co"),
            "lever",
            LEVER_URL.replace("jobs.lever.co", "jobs.eu.lever.co"),
        ),
        (
            "https://boards.greenhouse.io/example/jobs/123?gh_src=alert",
            "greenhouse",
            "https://boards.greenhouse.io/example/jobs/123",
        ),
        (
            "https://job-boards.greenhouse.io/example/jobs/123/",
            "greenhouse",
            "https://job-boards.greenhouse.io/example/jobs/123",
        ),
    ],
)
def test_task_has_exact_note_revision_and_canonical_target_without_writes(
    application_store, url, platform, canonical
):
    store, record = application_store
    record = store.update_application(record["id"], {"url": url}, record["revision"])
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    task = prepare_application_task(store, record["id"], record["revision"])
    assert task["mode"] == "review_only"
    assert task["executed"] is False
    assert task["platform"] == platform
    assert task["job_url"] == canonical
    assert task["upstream_revision"] == UPSTREAM_REVISION
    assert task["prompt"].startswith("$job-apply:job-apply")
    target = json.loads(task["prompt"].split("\n\n")[2])
    assert target["note_path"] == str(store.root / record["source_name"])
    assert target["note_sha256"] == record["revision"]
    assert target["job_url"] == canonical
    assert {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://boards.greenhouse.io/example/jobs/123",
        "https://jobs.lever.co.attacker.example/example/123",
        "https://attacker.example/?redirect=" + LEVER_URL,
        "https://user:secret@jobs.lever.co/example/123",
        "https://jobs.lever.co:443/example/123",
        "https://jobs.lever.co/example",
        "https://boards.greenhouse.io/example",
        "https://www.linkedin.com/jobs/view/123",
    ],
)
def test_only_supported_direct_https_job_urls_are_admitted(application_store, url):
    store, record = application_store
    record = store.update_application(record["id"], {"url": url}, record["revision"])
    with pytest.raises(PortalDataError):
        prepare_application_task(store, record["id"], record["revision"])


@pytest.mark.parametrize(
    "host",
    [
        "127.1",
        "127.0.1",
        "0177.0.0.1",
        "0x7f.0.0.1",
        "127.0.0.1.",
        "localhost.",
        "LOCALHOST.",
        "app.localhost.",
        "app.local.",
        "app.internal.",
        "127%2e1",
        "127。1",
        "localhost。",
        "app.localhost。",
        "127.0.0.1",
        "10.0.0.1",
        "192.168.1.1",
        "[::ffff:127.0.0.1]",
    ],
)
def test_generic_handoff_rejects_local_host_variants_without_writes(application_store, host):
    store, record = application_store
    record = store.update_application(
        record["id"], {"url": f"https://{host}/jobs/42"}, record["revision"]
    )

    with pytest.raises(PortalDataError) as failure:
        prepare_application_task(store, record["id"], record["revision"], allow_generic=True)

    assert failure.value.code == "invalid_job_url"
    assert store.get_application(record["id"]) == record


@pytest.mark.parametrize("host", ["careers.example.test", "careers.example.test.", "8.8.8.8"])
def test_generic_handoff_keeps_public_targets_and_job_identity(application_store, host):
    store, record = application_store
    url = f"https://{host}/jobs/42?source=selected#form"
    record = store.update_application(record["id"], {"url": url}, record["revision"])

    task = prepare_application_task(store, record["id"], record["revision"], allow_generic=True)

    assert task["platform"] == "generic"
    assert task["job_url"] == url
    assert task["executed"] is False
    assert store.get_application(record["id"]) == record


def test_stale_record_and_existing_application_cannot_enter_handoff(application_store):
    store, record = application_store
    changed = store.update_application(record["id"], {"notes": "Changed"}, record["revision"])
    with pytest.raises(PortalDataError, match="已变更"):
        prepare_application_task(store, record["id"], record["revision"])
    for status in ("applied", "confirmation_received", "waiting", "withdrawn", "rejected"):
        changed = store.update_application(changed["id"], {"status": status}, changed["revision"])
        with pytest.raises(PortalDataError, match="准备投递"):
            prepare_application_task(store, changed["id"], changed["revision"])


def test_expired_saved_deadline_cannot_enter_handoff(application_store):
    store, record = application_store
    record = store.update_application(record["id"], {"deadline": "2000-01-01"}, record["revision"])
    with pytest.raises(PortalDataError) as error:
        prepare_application_task(store, record["id"], record["revision"])
    assert error.value.code == "expired_deadline"
    assert store.get_application(record["id"])["status"] == "drafting"


def test_duplicate_job_in_another_note_blocks_handoff(application_store):
    store, record = application_store
    duplicate = store.create_application(
        {
            "company": "Example",
            "role_title": "Duplicate",
            "url": LEVER_URL + "/apply?source=other",
            "status": "applied",
        }
    )
    with pytest.raises(PortalDataError, match="相同岗位"):
        prepare_application_task(store, record["id"], record["revision"])
    assert store.get_application(duplicate["id"])["status"] == "applied"


def test_prior_same_company_and_role_without_url_requires_review(application_store):
    store, record = application_store
    prior = store.create_application(
        {"company": "EXAMPLE", "role_title": " Research  Engineer ", "status": "applied"}
    )
    with pytest.raises(PortalDataError, match="链接缺失") as error:
        prepare_application_task(store, record["id"], record["revision"])
    assert error.value.code == "duplicate_application"
    assert store.get_application(prior["id"])["status"] == "applied"
    assert store.get_application(record["id"])["status"] == "drafting"


def test_ashby_listing_and_application_links_share_history_identity(application_store):
    store, record = application_store
    url = "https://jobs.ashbyhq.com/example/12345678-1234-1234-1234-123456789abc"
    record = store.update_application(
        record["id"], {"url": url + "/application?utm_source=pilot#form"}, record["revision"]
    )
    prior = store.create_application(
        {"company": "Example", "role_title": "Old label", "url": url, "status": "applied"}
    )
    with pytest.raises(PortalDataError) as error:
        prepare_application_task(store, record["id"], record["revision"], allow_generic=True)
    assert error.value.code == "duplicate_application"
    assert store.get_application(prior["id"])["status"] == "applied"
