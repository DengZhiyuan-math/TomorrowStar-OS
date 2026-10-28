"""JSON application records keep the existing application API and legacy evidence."""

import json
from pathlib import Path

import pytest

from career_evidence_graph import career_portal_data
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


def store(tmp_path: Path) -> ApplicationStore:
    root = tmp_path / "applications"
    root.mkdir()
    return ApplicationStore(root)


def test_new_application_uses_json_without_markdown_parsing(tmp_path, monkeypatch):
    tracker = store(tmp_path)

    def forbid_parse(*args):
        raise AssertionError("Normal JSON records must not pass through Markdown")

    monkeypatch.setattr(career_portal_data, "_parse_note", forbid_parse)
    before = tracker.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Full JD\n## History\nKeep it",
        },
        request_id="a" * 32,
    )
    assert before["source_name"].endswith(".json")
    assert list(tracker.root.glob("*.md")) == []
    after = tracker.update_application(before["id"], {"notes": "Human edit"}, before["revision"])
    reopened = ApplicationStore(tracker.root)
    assert reopened.get_application(after["id"]) == after
    assert (
        reopened.create_application(
            {
                "company": "Synthetic",
                "role_title": "Engineer",
                "job_description": "Full JD\n## History\nKeep it",
            },
            request_id="a" * 32,
        )
        == after
    )
    assert reopened.list_applications()[0]["job_description"] == "Full JD\n## History\nKeep it"


def legacy(tracker):
    path = tracker.root / "original.md"
    path.write_bytes(
        b"---\r\ntype: job_application\r\ncompany: Synthetic\r\nrole_title: Engineer\r\n"
        b"unknown: preserve\r\ntags:\r\n  - private\r\n---\r\n# Old record\r\n\r\n"
        b"## Job Description\r\n\r\nFull JD\r\n\r\n## Outcome Email\r\n\r\nKeep history.\r\n"
    )
    return path


def test_legacy_adoption_retains_id_and_exact_original_with_daily_json_reads(tmp_path, monkeypatch):
    tracker = store(tmp_path)
    path = legacy(tracker)
    raw = path.read_bytes()
    before = tracker.list_applications()[0]
    adopted = tracker.import_application(before["id"], expected_revision=before["revision"])
    assert adopted["id"] == before["id"]
    assert adopted["legacy_source_name"] == path.name
    assert adopted["legacy_source_changed"] is False
    assert path.read_bytes() == raw
    assert list((tracker.root / ".tomorrowstar-history").rglob("*.md"))[0].read_bytes() == raw
    monkeypatch.setattr(
        career_portal_data,
        "_parse_note",
        lambda *args: pytest.fail("adopted record reparsed Markdown"),
    )
    assert tracker.get_application(before["id"]) == adopted
    assert len(tracker.list_applications()) == 1
    assert (
        tracker.import_application(before["id"], expected_revision=adopted["revision"]) == adopted
    )


def test_changed_legacy_source_is_explicit_and_cannot_overwrite_newer_json(tmp_path):
    tracker = store(tmp_path)
    path = legacy(tracker)
    before = tracker.list_applications()[0]
    tracker.import_application(before["id"], expected_revision=before["revision"])
    path.write_bytes(path.read_bytes().replace(b"Full JD", b"New full JD"))
    stale = tracker.get_application(before["id"])
    assert stale["legacy_source_changed"] is True
    assert stale["job_description"] == "Full JD"
    refreshed = tracker.import_application(stale["id"], expected_revision=stale["revision"])
    assert refreshed["job_description"] == "New full JD"
    edited = tracker.update_application(
        refreshed["id"], {"notes": "Human JSON change"}, refreshed["revision"]
    )
    path.write_bytes(path.read_bytes().replace(b"New full JD", b"Third JD"))
    primary = tracker.root / edited["source_name"]
    raw = primary.read_bytes()
    with pytest.raises(PortalDataError) as error:
        tracker.import_application(edited["id"], expected_revision=edited["revision"])
    assert error.value.code == "source-import-conflict"
    assert primary.read_bytes() == raw
    assert tracker.get_application(edited["id"])["notes"] == "Human JSON change"


def test_adoption_retry_after_archive_interrupt_does_not_duplicate_record(tmp_path, monkeypatch):
    tracker = store(tmp_path)
    path = legacy(tracker)
    before = tracker.list_applications()[0]
    original_write = career_portal_data._write_file

    def interrupt_primary(destination, raw, *, replace):
        if destination.suffix == ".json" and destination.parent == tracker.root:
            raise KeyboardInterrupt
        original_write(destination, raw, replace=replace)

    monkeypatch.setattr(career_portal_data, "_write_file", interrupt_primary)
    with pytest.raises(KeyboardInterrupt):
        tracker.import_application(before["id"], expected_revision=before["revision"])
    assert path.is_file()
    monkeypatch.setattr(career_portal_data, "_write_file", original_write)
    adopted = tracker.import_application(before["id"], expected_revision=before["revision"])
    assert adopted["id"] == before["id"]
    assert len(ApplicationStore(tracker.root).list_applications()) == 1
    assert len(list((tracker.root / ".tomorrowstar-history").rglob("*.md"))) == 1


@pytest.mark.parametrize(
    "damage",
    [
        "invalid-json",
        "unknown-version",
        "wrong-id",
        "invalid-source",
        "duplicate-key",
        "invalid-import-parent",
    ],
)
def test_malformed_json_fails_closed_without_losing_legacy(tmp_path, damage):
    tracker = store(tmp_path)
    path = legacy(tracker)
    before = tracker.list_applications()[0]
    adopted = tracker.import_application(before["id"], expected_revision=before["revision"])
    primary = tracker.root / adopted["source_name"]
    payload = json.loads(primary.read_bytes())
    if damage == "invalid-json":
        primary.write_text("{broken")
    elif damage == "unknown-version":
        payload["schema_version"] = "application-record/v2"
        primary.write_text(json.dumps(payload))
    elif damage == "wrong-id":
        payload["id"] = "f" * 24
        primary.write_text(json.dumps(payload))
    elif damage == "invalid-source":
        payload["legacy_source"] = {"name": "../outside.md"}
        primary.write_text(json.dumps(payload))
    elif damage == "invalid-import-parent":
        payload["import_parent_revision"] = "invalid-receipt"
        primary.write_text(json.dumps(payload))
    else:
        primary.write_text(
            primary.read_text().replace('"record": {', f'"id": "{adopted["id"]}", "record": {{')
        )
    saved = primary.read_bytes()
    with pytest.raises(PortalDataError) as error:
        tracker.get_application(before["id"])
    assert error.value.code == "invalid-application-json"
    assert primary.read_bytes() == saved
    assert path.is_file()


def test_import_retry_after_published_result_keeps_same_id_and_primary(tmp_path, monkeypatch):
    tracker = store(tmp_path)
    legacy(tracker)
    before = tracker.list_applications()[0]
    original_write = career_portal_data._write_file

    def interrupt_after_publish(destination, raw, *, replace):
        original_write(destination, raw, replace=replace)
        if destination.suffix == ".json" and destination.parent == tracker.root:
            raise KeyboardInterrupt

    monkeypatch.setattr(career_portal_data, "_write_file", interrupt_after_publish)
    with pytest.raises(KeyboardInterrupt):
        tracker.import_application(before["id"], expected_revision=before["revision"])
    monkeypatch.setattr(career_portal_data, "_write_file", original_write)
    current = tracker.get_application(before["id"])
    retried = tracker.import_application(before["id"], expected_revision=before["revision"])
    assert retried == current
    assert len(tracker.list_applications()) == 1


@pytest.mark.parametrize("replacement", ["symlink", "directory"])
def test_unavailable_json_primary_cannot_reactivate_older_markdown(tmp_path, replacement):
    tracker = store(tmp_path)
    legacy(tracker)
    before = tracker.list_applications()[0]
    adopted = tracker.import_application(before["id"], expected_revision=before["revision"])
    edited = tracker.update_application(
        adopted["id"], {"notes": "Preserve later human JSON notes"}, adopted["revision"]
    )
    primary = tracker.root / edited["source_name"]
    preserved = tmp_path / "preserved-primary.json"
    primary.rename(preserved)
    if replacement == "symlink":
        primary.symlink_to(preserved)
    else:
        primary.mkdir()
    for operation in (tracker.list_applications, lambda: tracker.get_application(edited["id"])):
        with pytest.raises(PortalDataError) as error:
            operation()
        assert error.value.code == "invalid-application-json"
    assert (
        json.loads(preserved.read_bytes())["record"]["notes"] == "Preserve later human JSON notes"
    )


def test_refresh_import_retry_adopts_published_result_without_losing_later_edits(
    tmp_path, monkeypatch
):
    tracker = store(tmp_path)
    path = legacy(tracker)
    before = tracker.list_applications()[0]
    adopted = tracker.import_application(before["id"], expected_revision=before["revision"])
    path.write_bytes(path.read_bytes().replace(b"Full JD", b"Updated full JD"))
    original_write = career_portal_data._write_file

    def interrupt_after_publish(destination, raw, *, replace):
        original_write(destination, raw, replace=replace)
        if destination.suffix == ".json" and destination.parent == tracker.root:
            raise KeyboardInterrupt

    monkeypatch.setattr(career_portal_data, "_write_file", interrupt_after_publish)
    with pytest.raises(KeyboardInterrupt):
        tracker.import_application(adopted["id"], expected_revision=adopted["revision"])
    monkeypatch.setattr(career_portal_data, "_write_file", original_write)
    current = tracker.get_application(adopted["id"])
    saved = (tracker.root / current["source_name"]).read_bytes()
    reopened = ApplicationStore(tracker.root)
    retried = reopened.import_application(adopted["id"], expected_revision=adopted["revision"])
    assert retried == current
    assert retried["job_description"] == "Updated full JD"
    assert (tracker.root / current["source_name"]).read_bytes() == saved
    edited = reopened.update_application(
        current["id"], {"notes": "Later human change"}, current["revision"]
    )
    with pytest.raises(PortalDataError) as error:
        reopened.import_application(adopted["id"], expected_revision=adopted["revision"])
    assert error.value.code == "revision-conflict"
    assert reopened.get_application(edited["id"])["notes"] == "Later human change"


def test_import_preview_shows_mapping_and_unmapped_fields_without_writes(tmp_path):
    tracker = store(tmp_path)
    legacy(tracker)
    before = tracker.list_applications()[0]
    original = {
        str(p.relative_to(tracker.root)): p.read_bytes()
        for p in tracker.root.rglob("*")
        if p.is_file()
    }
    preview = tracker.preview_application_import(before["id"], expected_revision=before["revision"])
    assert preview["status"] == "ready"
    assert preview["unmapped_properties"] == ["tags", "type", "unknown"]
    assert preview["record"]["job_description"] == before["job_description"]
    assert preview["id"] == before["id"]
    assert preview["original_bytes_preserved"]
    assert {
        str(p.relative_to(tracker.root)): p.read_bytes()
        for p in tracker.root.rglob("*")
        if p.is_file()
    } == original
    with pytest.raises(PortalDataError):
        tracker.preview_application_import(before["id"], expected_revision="0" * 64)
