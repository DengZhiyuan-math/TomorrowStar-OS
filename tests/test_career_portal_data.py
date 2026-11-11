"""Synthetic coverage for direct, non-destructive local portal integration."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_evidence_graph import career_portal_data
from career_evidence_graph.career_portal_data import (
    ApplicationStore,
    CareerCatalog,
    PortalDataError,
)


@pytest.fixture
def tracker(tmp_path: Path) -> ApplicationStore:
    root = tmp_path / "tracker"
    root.mkdir()
    return ApplicationStore(root)


def legacy_note(tracker: ApplicationStore, *, newline: str = "\n") -> Path:
    path = tracker.root / "original-note.md"
    text = """---
type: job_application
company: "Synthetic Labs"
role_title: "Research Engineer"
status: applied
current_status: "applied"
track: "AI/ML"
application_date: 2026-09-01
needs_action: false
required_next_action: "Wait"
unknown_property: "keep this exactly"
tags:
  - job/application
  - custom/tag
---

# Synthetic Labs - Research Engineer

## Snapshot

- Status: `applied`
- Other: keep

## Next Action

Wait

## Hermes Notes

Unchanged personal note.

## Job Description

Synthetic role description.

## Outcome Email

Historical record remains intact.
"""
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


def test_reads_existing_hermes_format_and_ignores_nonapplication(tracker: ApplicationStore) -> None:
    path = legacy_note(tracker)
    (tracker.root / "readme.md").write_text("---\ntype: help\n---\n# Guide\n")
    items = tracker.list_applications()
    assert len(items) == 1
    row = items[0]
    assert row["company"] == "Synthetic Labs"
    assert row["application_date"] == "2026-09-01"
    assert row["next_action"] == "Wait"
    assert row["notes"] == "Unchanged personal note."
    assert row["job_description"] == "Synthetic role description."
    assert row["needs_action"] is False
    assert row["linked_evidence"] == []
    assert "content" not in row
    assert tracker.get_application(row["id"])["content"] in path.read_text()


def test_changes_preserve_unknown_fields_body_and_original_backup(
    tracker: ApplicationStore,
) -> None:
    path = legacy_note(tracker)
    original = path.read_bytes()
    before = tracker.list_applications()[0]
    after = tracker.update_application(
        before["id"],
        {"status": "interview_scheduled", "next_action": "Prepare\nBring examples."},
        before["revision"],
    )
    assert after["status"] == "interview_scheduled"
    assert after["needs_action"] is True
    assert after["next_action"] == "Prepare\nBring examples."
    assert after["revision"] != before["revision"]
    assert after["id"] == before["id"]
    text = path.read_text()
    assert path.read_bytes() == original
    assert after["status"] == "interview_scheduled"
    assert after["next_action"] == "Prepare\nBring examples."
    assert (
        'unknown_property: "keep this exactly"\ntags:\n  - job/application\n  - custom/tag\n'
        in text
    )
    assert (
        "## Job Description\n\nSynthetic role description.\n\n"
        "## Outcome Email\n\nHistorical record remains intact.\n" in text
    )
    backups = list((tracker.root / ".tomorrowstar-history").rglob("*.md"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


def test_stale_revision_rejects_edit_without_overwriting_external_changes(
    tracker: ApplicationStore,
) -> None:
    path = legacy_note(tracker)
    old = tracker.list_applications()[0]
    latest = path.read_bytes() + b"\nExternal change.\n"
    path.write_bytes(latest)
    with pytest.raises(PortalDataError) as failure:
        tracker.update_application(old["id"], {"status": "rejected"}, old["revision"])
    assert failure.value.status == 409
    assert path.read_bytes() == latest
    assert not (tracker.root / ".tomorrowstar-history").exists()


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("has_snapshot", [True, False])
@pytest.mark.parametrize("snapshot_status", [True, False])
def test_status_edit_preserves_history_and_quoted_statuses(
    tracker, newline, has_snapshot, snapshot_status
):
    path = legacy_note(tracker, newline=newline)
    original = path.read_bytes()
    if not has_snapshot:
        original = original.replace(b"## Snapshot", b"## Earlier Snapshot")
    if not snapshot_status:
        original = original.replace(b"- Status: `applied`", b"- Status not recorded")
    archived = "## Custom Archive\n\n- Status: `waiting`\n\n".replace("\n", newline).encode()
    original = original.replace(b"## Next Action", archived + b"## Next Action", 1)
    history = (
        ("## History\n\n- Status: `drafting`\n\n## Email Quote\n\n- Status: `rejected`\n")
        .replace("\n", newline)
        .encode()
    )
    original += history
    path.write_bytes(original)
    before = tracker.list_applications()[0]

    after = tracker.update_application(before["id"], {"status": "rejected"}, before["revision"])

    expected = original.replace(b"status: applied", b'status: "rejected"', 1).replace(
        b'current_status: "applied"', b'current_status: "rejected"', 1
    )
    if has_snapshot and snapshot_status:
        expected = expected.replace(b"- Status: `applied`", b"- Status: `rejected`", 1)
    assert after["status"] == "rejected"
    assert path.read_bytes() == original
    assert after["content"].encode() in original
    assert after["status"] == "rejected"
    backups = list((tracker.root / ".tomorrowstar-history").rglob("*.md"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


def test_routing_decisions_round_trip_preserving_legacy_bytes_and_status(tracker):
    path = legacy_note(tracker)
    original = path.read_bytes()
    before = tracker.list_applications()[0]
    assert before["application_strategy"] == ""
    changes = {
        "application_strategy": "manual",
        "jd_match": "strong",
        "evidence_match": "direct",
        "personal_priority": "high",
        "target_company": "target",
        "compensation_priority": "exceptional",
        "strategy_notes": "Synthetic JD and salary source.\nReview personal contribution.",
    }
    after = tracker.update_application(before["id"], changes, before["revision"])
    assert all(after[key] == value for key, value in changes.items())
    assert after["status"] == before["status"]
    assert after["job_description"] == before["job_description"]
    assert after["notes"] == before["notes"]
    assert "Historical record remains intact." in path.read_text()
    assert list((tracker.root / ".tomorrowstar-history").rglob("*.md"))[0].read_bytes() == original


@pytest.mark.parametrize("field", career_portal_data.APPLICATION_DECISIONS)
def test_unknown_routing_decisions_are_rejected(tracker, field):
    with pytest.raises(PortalDataError) as error:
        tracker.create_application(
            {"company": "Synthetic", "role_title": "AI Engineer", field: "other"}
        )
    assert error.value.code == "invalid-decision"
    assert tracker.list_applications() == []


def test_creates_compatible_unique_notes_and_persists_explicit_links(
    tracker: ApplicationStore,
) -> None:
    payload = {
        "company": '示例 "Labs"',
        "role_title": "Engineer",
        "job_description": "A role.\nDetails.",
        "linked_evidence": ["a" * 24],
        "url": "https://example.test/job",
        "status": "applied",
    }
    first = tracker.create_application(payload)
    second = tracker.create_application(payload)
    assert first["id"] != second["id"]
    assert first["company"] == payload["company"]
    assert first["linked_evidence"] == ["a" * 24]
    assert first["needs_action"] is False
    assert first["job_description"] == payload["job_description"]
    reloaded = ApplicationStore(tracker.root).get_application(first["id"])
    assert reloaded == first
    assert len(list(tracker.root.glob("*.json"))) == 2
    assert not list(tracker.root.glob("*.md"))


def test_creation_request_survives_restart_and_does_not_overwrite_later_edits(tracker):
    payload = {"company": "Synthetic", "role_title": "Engineer"}
    first = tracker.create_application(payload, request_id="a" * 32)
    changed = tracker.update_application(first["id"], {"notes": "Later edit."}, first["revision"])
    raw = (tracker.root / changed["source_name"]).read_bytes()

    retried = ApplicationStore(tracker.root).create_application(payload, request_id="a" * 32)

    assert retried == changed
    assert (tracker.root / changed["source_name"]).read_bytes() == raw
    assert len(tracker.list_applications()) == 1
    separate = tracker.create_application(payload, request_id="b" * 32)
    assert separate["id"] != first["id"]


@pytest.mark.parametrize("request_id", ["", "../escape", "A" * 32, "a" * 33])
def test_invalid_creation_request_cannot_write_a_note(tracker, request_id):
    with pytest.raises(PortalDataError, match="保存请求标识无效"):
        tracker.create_application(
            {"company": "Synthetic", "role_title": "Engineer"}, request_id=request_id
        )
    assert list(tracker.root.glob("*.md")) == []
    assert list(tracker.root.glob("*.json")) == []


def test_creation_request_cannot_be_reused_for_changed_content(tracker):
    first = tracker.create_application(
        {"company": "Synthetic", "role_title": "Engineer"}, request_id="a" * 32
    )
    with pytest.raises(PortalDataError) as rejected:
        tracker.create_application(
            {"company": "Other", "role_title": "Engineer"}, request_id="a" * 32
        )
    assert rejected.value.code == "save-request-conflict"
    assert rejected.value.status == 409
    assert tracker.get_application(first["id"]) == first
    assert len(tracker.list_applications()) == 1


def test_note_heading_cannot_replace_the_job_description(tracker):
    description = "Build ML systems. French C1 required."
    notes = "Private preparation.\n\n## Job Description\n\nSynthetic private note."
    record = tracker.create_application(
        {
            "company": "Synthetic",
            "role_title": "AI Engineer",
            "job_description": description,
            "notes": notes,
        }
    )

    reloaded = ApplicationStore(tracker.root).get_application(record["id"])

    assert reloaded["job_description"] == description
    assert reloaded["notes"] == notes


@pytest.mark.parametrize("field", ["next_action", "notes", "job_description", "strategy_notes"])
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_free_text_headings_stay_in_their_field_across_edits(tracker, field, operation, newline):
    from career_evidence_graph.job_screening import screen_applications

    value = (
        "Synthetic field content.\n\n"
        "## Job Description\n\n<!-- career-portal:job-description:v1 -->\nPrivate preparation.\n\n"
        "## Next Action\n\nNested action.\n\n"
        "## Hermes Notes\n\nNested note.\n\n"
        "## Application Strategy\n\nNested strategy.\n\n"
        "## Snapshot\n\n- Status: `waiting`\n\n"
        "## History\n\nFrench C1 required.\n    Keep this indentation."
    ).replace("\n", newline)
    expected = {
        "next_action": "Review the role.",
        "notes": "Keep personal notes.",
        "job_description": "Build ML systems. French C1 required.",
        "strategy_notes": "Keep the strategy.",
    }
    record = tracker.create_application(
        {
            "company": "Synthetic",
            "role_title": "AI Engineer",
            "url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789abc",
            **expected,
            **({field: value} if operation == "create" else {}),
        }
    )
    path = tracker.root / record["source_name"]
    history = "\n## History\n\nReal application history.\n\n## Outcome Email\n\nKeep this email.\n"
    payload = json.loads(path.read_bytes())
    payload["record"]["content"] = history.replace("\n", newline)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    original = path.read_bytes()
    record = tracker.get_application(record["id"])
    if operation == "update":
        record = tracker.update_application(record["id"], {field: value}, record["revision"])
    expected[field] = value
    reloaded = ApplicationStore(tracker.root).get_application(record["id"])
    assert {key: reloaded[key] for key in expected} == expected
    screening = screen_applications([reloaded], language_levels={"French": "A1"})[0]["screening"]
    assert screening["language_mismatch"] and screening["category"] == "excluded"

    other = "notes" if field != "notes" else "next_action"
    expected[other] = "Changed another field."
    updated = tracker.update_application(
        reloaded["id"], {other: expected[other], "status": "rejected"}, reloaded["revision"]
    )
    assert {key: updated[key] for key in expected} == expected
    assert "- Status: `waiting`" in updated[field]
    expected[field] = "Replaced only this field."
    updated = tracker.update_application(
        updated["id"], {field: expected[field]}, updated["revision"]
    )
    reloaded = ApplicationStore(tracker.root).get_application(updated["id"])
    assert {key: reloaded[key] for key in expected} == expected
    assert "Synthetic field content." not in reloaded[field]
    assert reloaded["content"] == history.replace("\n", newline)
    assert original in [
        item.read_bytes() for item in (tracker.root / ".tomorrowstar-history").rglob("*.json")
    ]


def test_link_edits_preserve_application_identity(tracker: ApplicationStore) -> None:
    record = tracker.create_application({"company": "Synthetic", "role_title": "Engineer"})
    updated = tracker.update_application(
        record["id"], {"linked_evidence": ["b" * 24]}, record["revision"]
    )
    assert updated["id"] == record["id"]
    assert updated["linked_evidence"] == ["b" * 24]
    assert updated["status"] == "drafting"


@pytest.mark.parametrize(
    "changes",
    [
        {"company": ""},
        {"role_title": ""},
        {"status": "invented"},
        {"url": "javascript:alert(1)"},
        {"unknown": "field"},
        {"company": "line\nbreak"},
        {"needs_action": "yes"},
        {"linked_evidence": ["../../secret"]},
        {"linked_evidence": ["a" * 24, "a" * 24]},
        {"application_date": "tomorrow"},
    ],
)
def test_rejects_invalid_changes_without_writing(tracker: ApplicationStore, changes: dict) -> None:
    path = legacy_note(tracker)
    raw = path.read_bytes()
    record = tracker.list_applications()[0]
    with pytest.raises(PortalDataError):
        tracker.update_application(record["id"], changes, record["revision"])
    assert path.read_bytes() == raw
    assert not (tracker.root / ".tomorrowstar-history").exists()


def test_duplicates_and_complex_yaml_fail_closed(tracker: ApplicationStore) -> None:
    path = legacy_note(tracker)
    path.write_text(
        path.read_text().replace("status: applied", "status: applied\nstatus: rejected")
    )
    with pytest.raises(PortalDataError, match="重复属性"):
        tracker.list_applications()
    path = legacy_note(tracker)
    path.write_text(
        path.read_text().replace('company: "Synthetic Labs"', "company: |\n  Synthetic Labs")
    )
    record = tracker.list_applications()[0]
    before = path.read_bytes()
    with pytest.raises(PortalDataError, match="多行格式"):
        tracker.update_application(record["id"], {"company": "Change"}, record["revision"])
    assert path.read_bytes() == before


def test_symlink_note_and_backup_escape_are_refused(
    tracker: ApplicationStore, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("DO NOT READ")
    (tracker.root / "escape.md").symlink_to(outside)
    assert tracker.list_applications() == []
    path = legacy_note(tracker)
    record = tracker.list_applications()[0]
    (tracker.root / ".tomorrowstar-history").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PortalDataError, match="符号链接"):
        tracker.update_application(record["id"], {"status": "rejected"}, record["revision"])
    assert path.read_text().count("status: applied") == 1
    assert outside.read_text() == "DO NOT READ"


def test_identifier_never_accepts_file_paths(tracker: ApplicationStore) -> None:
    legacy_note(tracker)
    with pytest.raises(PortalDataError) as failure:
        tracker.get_application("../original-note.md")
    assert failure.value.status == 404


def test_non_body_edit_preserves_crlf_and_all_body_bytes(tracker: ApplicationStore) -> None:
    path = legacy_note(tracker, newline="\r\n")
    original_body = path.read_bytes().split(b"---\r\n", 2)[-1]
    record = tracker.list_applications()[0]
    updated = tracker.update_application(record["id"], {"location": "Remote"}, record["revision"])
    assert path.read_bytes().split(b"---\r\n", 2)[-1] == original_body
    assert updated["location"] == "Remote"
    assert updated["content"].encode() == original_body


def test_catalog_reads_documents_without_promoting_them_or_exposing_raw(tmp_path: Path) -> None:
    career = tmp_path / "career"
    report = career / "reports" / "projects" / "synthetic.md"
    report.parent.mkdir(parents=True)
    report.write_text("# Synthetic research\n\nSource-derived report, pending review.\n")
    raw = career / ".career-evidence" / "raw" / "private.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("Sensitive source capture")
    (career / "reports" / "raw-link.md").symlink_to(raw)
    (career / "reports" / "linked-dir").symlink_to(raw.parent, target_is_directory=True)
    hidden = career / "reports" / ".hidden.md"
    hidden.write_text("Hidden content")
    catalog = CareerCatalog(career)
    items = catalog.list_evidence()
    assert len(items) == 1
    assert items[0]["title"] == "synthetic"
    assert items[0]["kind"] == "report"
    assert items[0]["status"] == "documentary"
    assert "content" not in items[0]
    assert "revision" not in items[0]
    assert items[0]["available"] is True
    assert catalog.get_evidence(items[0]["id"])["content"] == report.read_text()
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence("../../.career-evidence/raw/private.md")
    assert failure.value.status == 404


def test_links_support_obsidian_native_yaml_lists(tracker: ApplicationStore) -> None:
    path = legacy_note(tracker)
    path.write_text(
        path.read_text().replace(
            "tags:\n",
            'career_evidence_links:\n  - "' + "a" * 24 + '"\n  - ' + "b" * 24 + "\ntags:\n",
        )
    )
    record = tracker.list_applications()[0]
    assert record["linked_evidence"] == ["a" * 24, "b" * 24]
    updated = tracker.update_application(
        record["id"], {"linked_evidence": ["c" * 24]}, record["revision"]
    )
    assert updated["linked_evidence"] == ["c" * 24]
    assert updated["linked_evidence"] == ["c" * 24]
    assert "a" * 24 in path.read_text()
    assert "tags:\n  - job/application\n  - custom/tag\n" in path.read_text()


def test_job_description_keeps_nested_headings_and_preserves_other_tracker_sections(
    tracker: ApplicationStore,
) -> None:
    path = legacy_note(tracker)
    path.write_text(
        path.read_text().replace(
            "Synthetic role description.",
            "Synthetic role description.\n\n## Responsibilities\n\nBuild tools.\n\n"
            "## Qualifications\n\nPython.",
        )
    )
    record = tracker.list_applications()[0]
    assert "## Responsibilities\n\nBuild tools." in record["job_description"]
    assert record["job_description"].endswith("Python.")
    description = "New JD.\n\n## Requirements\n\nTesting."
    updated = tracker.update_application(
        record["id"], {"job_description": description}, record["revision"]
    )
    assert updated["job_description"] == description
    assert "Build tools." not in updated["job_description"]
    assert "Build tools." in path.read_text()
    assert "## Outcome Email\n\nHistorical record remains intact." in path.read_text()
    assert "Unchanged personal note." in path.read_text()


@pytest.mark.parametrize(
    "heading",
    ["History", "Next Action", "Application Strategy", "Job Description", "Outcome Email"],
)
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_jd_tracker_named_headings_survive_roundtrip_and_language_screening(
    tracker, heading, operation, newline
):
    from career_evidence_graph.job_screening import screen_applications

    description = f"Build ML systems.\n\n## {heading}\n\nFrench C1 required.".replace("\n", newline)
    record = tracker.create_application(
        {
            "company": "Synthetic",
            "role_title": "AI Engineer",
            "url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789abc",
            "notes": "Keep personal notes.",
            "next_action": "Review the JD.",
            "strategy_notes": "Keep the strategy.",
            "job_description": description if operation == "create" else "Previous JD.",
        }
    )
    if operation == "update":
        record = tracker.update_application(
            record["id"], {"job_description": description}, record["revision"]
        )
    assert record["job_description"] == description
    updated = tracker.update_application(
        record["id"], {"strategy_notes": "New strategy."}, record["revision"]
    )
    reloaded = ApplicationStore(tracker.root).get_application(updated["id"])
    assert reloaded["job_description"] == description
    assert reloaded["notes"] == "Keep personal notes."
    assert reloaded["next_action"] == "Review the JD."
    assert reloaded["strategy_notes"] == "New strategy."
    screening = screen_applications([reloaded], language_levels={"French": "A1"})[0]["screening"]
    assert screening["language_mismatch"] and screening["category"] == "excluded"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("spacer", ["", "  \t\n"])
@pytest.mark.parametrize(
    "description",
    ["", "Build ML systems.\n\n## History\n\nFrench C1 required."],
    ids=["empty", "with-heading"],
)
def test_marked_jd_edit_preserves_adjacent_real_history(tracker, newline, spacer, description):
    record = tracker.create_application(
        {
            "company": "Synthetic",
            "role_title": "AI Engineer",
            "job_description": description,
            "strategy_notes": "Keep this strategy.",
        }
    )
    path = tracker.root / record["source_name"]
    history = "## History\n\n- 2026-10-16: User confirmed the application draft.\n\n"
    payload = json.loads(path.read_bytes())
    payload["record"]["content"] = history.replace("\n", newline)
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = path.read_bytes()

    before = tracker.get_application(record["id"])

    assert before["job_description"] == description
    updated = tracker.update_application(
        before["id"], {"job_description": "New complete JD."}, before["revision"]
    )
    assert updated["job_description"] == "New complete JD."
    assert updated["content"] == history.replace("\n", newline)
    assert updated["strategy_notes"] == "Keep this strategy."
    assert original in [
        item.read_bytes() for item in (tracker.root / ".tomorrowstar-history").rglob("*.json")
    ]


def test_legacy_jd_history_heading_keeps_requirements_and_replaces_the_whole_jd(tracker):
    path = legacy_note(tracker)
    description = "Build ML systems.\n\n## History\n\nFrench C1 required."
    path.write_text(path.read_text().replace("Synthetic role description.", description))
    original = path.read_bytes()

    record = tracker.list_applications()[0]

    assert record["job_description"] == description
    assert path.read_bytes() == original
    updated = tracker.update_application(
        record["id"], {"job_description": "New complete JD."}, record["revision"]
    )
    assert updated["job_description"] == "New complete JD."
    assert "French C1" not in updated["job_description"]
    assert path.read_bytes() == original
    assert "## Outcome Email\n\nHistorical record remains intact." in path.read_text()


@pytest.mark.parametrize("replacement", ["missing", "symlink"])
def test_missing_or_replaced_tracker_root_is_unavailable(
    tracker: ApplicationStore,
    tmp_path: Path,
    replacement: str,
) -> None:
    tracker.root.rename(tmp_path / "old-tracker")
    if replacement == "symlink":
        tracker.root.symlink_to(tmp_path / "old-tracker", target_is_directory=True)
    for operation in (
        tracker.list_applications,
        lambda: tracker.create_application({"company": "Synthetic", "role_title": "Engineer"}),
    ):
        with pytest.raises(PortalDataError) as failure:
            operation()
        assert failure.value.status == 503
    assert not list((tmp_path / "old-tracker").glob("*.md"))
    assert not list((tmp_path / "old-tracker").glob("*.json"))


@pytest.mark.parametrize("replacement", ["missing", "symlink"])
def test_missing_or_replaced_career_root_is_unavailable(tmp_path: Path, replacement: str) -> None:
    root = tmp_path / "career"
    root.mkdir()
    catalog = CareerCatalog(root)
    root.rename(tmp_path / "old-career")
    if replacement == "symlink":
        root.symlink_to(tmp_path / "old-career", target_is_directory=True)
    with pytest.raises(PortalDataError) as failure:
        catalog.list_evidence()
    assert failure.value.status == 503


def test_cloud_placeholder_list_never_reads_content_and_detail_is_actionable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "career"
    folder = root / "reports"
    folder.mkdir(parents=True)
    note = folder / "cloud-document.md"
    note.write_text("Not locally available")
    original_stat = Path.stat

    def metadata(path: Path, **kwargs):
        result = original_stat(path, **kwargs)
        if path == note:
            return SimpleNamespace(
                st_flags=1073741824, st_mode=result.st_mode, st_size=result.st_size
            )
        return result

    monkeypatch.setattr(Path, "stat", metadata)
    monkeypatch.setattr(career_portal_data.stat, "SF_DATALESS", 1073741824, raising=False)

    def unexpected_read(*args, **kwargs):
        raise AssertionError("Placeholder must never trigger download or subprocess read")

    monkeypatch.setattr(career_portal_data.subprocess, "run", unexpected_read)
    catalog = CareerCatalog(root)
    items = catalog.list_evidence()
    assert len(items) == 1
    assert items[0]["title"] == "cloud document"
    assert items[0]["available"] is False
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence(items[0]["id"])
    assert failure.value.status == 503
    assert "Finder" in failure.value.message


def test_document_read_timeout_does_not_remove_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "career"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "slow.md").write_text("# Slow file\n")

    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 3
        raise career_portal_data.subprocess.TimeoutExpired("synthetic", 3)

    monkeypatch.setattr(career_portal_data.subprocess, "run", timeout)
    catalog = CareerCatalog(root)
    items = catalog.list_evidence()
    assert len(items) == 1
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence(items[0]["id"])
    assert failure.value.status == 503
    assert len(catalog.list_evidence()) == 1


def test_document_size_is_bounded_without_launching_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "career"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "large.md").write_bytes(b"x" * 2_000_001)

    def unexpected_read(*args, **kwargs):
        raise AssertionError("Oversize files must not be read")

    monkeypatch.setattr(career_portal_data.subprocess, "run", unexpected_read)
    catalog = CareerCatalog(root)
    item = catalog.list_evidence()[0]
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence(item["id"])
    assert failure.value.status == 413


def test_application_sort_puts_unknown_and_invalid_dates_last_without_rewriting(
    tracker: ApplicationStore,
) -> None:
    dates = ["unknown", "2026-09-01", "", "2026-09-18", "2026-99-99"]
    originals = {}
    for index, value in enumerate(dates):
        path = tracker.root / f"{index}.md"
        raw = (
            '---\ntype: job_application\ncompany: "Synthetic"\nrole_title: "Engineer"\n'
            f'application_date: "{value}"\n---\n'
        ).encode()
        path.write_bytes(raw)
        originals[path] = raw
    items = tracker.list_applications()
    assert [item["application_date"] for item in items[:2]] == ["2026-09-18", "2026-09-01"]
    assert {item["application_date"] for item in items[2:]} == {"unknown", "", "2026-99-99"}
    assert all(path.read_bytes() == raw for path, raw in originals.items())
