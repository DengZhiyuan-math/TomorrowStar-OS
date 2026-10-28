"""Application reads reuse only the records verified during that one call."""

import json
from pathlib import Path

import pytest

from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.fixture
def applications(tmp_path):
    store = ApplicationStore(tmp_path)
    records = [
        store.create_application(
            {"company": f"Synthetic {number}", "role_title": "Engineer"},
            request_id=f"{number:032x}",
        )
        for number in range(4)
    ]
    return store, records


@pytest.mark.parametrize("operation", ["list", "get", "missing"])
def test_each_json_is_read_and_validated_once_per_lookup(applications, monkeypatch, operation):
    store, records = applications
    reads, validations = [], []
    read_bytes, validate = Path.read_bytes, store._json

    def counted_read(path):
        if path.parent == store.root and path.suffix == ".json":
            reads.append(path.name)
        return read_bytes(path)

    def counted_validation(path, raw):
        validations.append(path.name)
        return validate(path, raw)

    monkeypatch.setattr(Path, "read_bytes", counted_read)
    monkeypatch.setattr(store, "_json", counted_validation)
    if operation == "list":
        assert len(store.list_applications()) == len(records)
    elif operation == "get":
        assert store.get_application(records[-1]["id"]) == records[-1]
    else:
        with pytest.raises(PortalDataError) as failure:
            store.get_application("f" * 24)
        assert failure.value.code == "application-not-found"
    expected = sorted(record["source_name"] for record in records)
    assert sorted(reads) == expected
    assert sorted(validations) == expected


@pytest.mark.parametrize("operation", ["list", "get", "missing"])
def test_unrelated_invalid_json_still_stops_every_lookup(applications, operation):
    store, records = applications
    (store.root / records[-1]["source_name"]).write_text("{broken", encoding="utf-8")
    with pytest.raises(PortalDataError) as failure:
        if operation == "list":
            store.list_applications()
        else:
            store.get_application(records[0]["id"] if operation == "get" else "f" * 24)
    assert failure.value.code == "invalid-application-json"


def test_read_projection_is_not_retained_between_calls(applications):
    store, records = applications
    record = records[0]
    assert store.get_application(record["id"]) == record
    path = store.root / record["source_name"]
    payload = json.loads(path.read_bytes())
    payload["record"]["notes"] = "External edit"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert store.get_application(record["id"])["notes"] == "External edit"
    assert store.list_applications()[0].get("content") is None
    assert "content" in store.get_application(record["id"])


def test_json_lookup_does_not_parse_unrelated_markdown(applications):
    store, records = applications
    (store.root / "help.md").write_text("---\ntype: help\n---\n# Guide\n", encoding="utf-8")
    assert store.get_application(records[0]["id"]) == records[0]
    assert len(store.list_applications()) == len(records)


def test_invalid_identifier_stops_before_scanning(applications, monkeypatch):
    store, _ = applications

    def unexpected_scan():
        pytest.fail("An invalid identifier must not scan application records")

    monkeypatch.setattr(store, "_records", unexpected_scan)
    with pytest.raises(PortalDataError) as failure:
        store.get_application("invalid")
    assert failure.value.code == "application-not-found"


def test_adopted_legacy_drift_is_rechecked_for_each_read(tmp_path):
    store = ApplicationStore(tmp_path)
    source = tmp_path / "legacy.md"
    source.write_text(
        "---\ntype: job_application\ncompany: Synthetic\nrole_title: Engineer\n---\n"
        "# Original\n\n## Job Description\n\nSynthetic JD.\n",
        encoding="utf-8",
    )
    original = store.list_applications()[0]
    adopted = store.import_application(original["id"], expected_revision=original["revision"])
    assert store.get_application(adopted["id"])["legacy_source_changed"] is False
    source.write_text(source.read_text(encoding="utf-8") + "\nExternal edit.\n", encoding="utf-8")
    assert store.get_application(adopted["id"])["legacy_source_changed"] is True
    assert store.list_applications()[0]["legacy_source_changed"] is True


def test_write_still_rereads_after_archiving(applications, monkeypatch):
    store, records = applications
    before = records[0]
    primary = store.root / before["source_name"]
    archive = store._archive
    external = None

    def external_edit(identifier, path, raw):
        nonlocal external
        archive(identifier, path, raw)
        payload = json.loads(path.read_bytes())
        payload["record"]["notes"] = "Concurrent external edit"
        external = json.dumps(payload).encode("utf-8")
        path.write_bytes(external)

    monkeypatch.setattr(store, "_archive", external_edit)
    with pytest.raises(PortalDataError) as failure:
        store.update_application(before["id"], {"notes": "Requested edit"}, before["revision"])
    assert failure.value.code == "revision-conflict"
    assert primary.read_bytes() == external
