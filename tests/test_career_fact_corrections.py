"""Explicit career corrections retain the original documentary source."""

import pytest

from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError


def test_career_correction_updates_same_source_and_retains_revision_history(tmp_path):
    (tmp_path / "sources").mkdir()
    path = tmp_path / "sources" / "career.md"
    original = b"# Career\r\n\r\nEmployer: Old Company\r\n"
    path.write_bytes(original)
    catalog = CareerCatalog(tmp_path)
    before = catalog.get_evidence(catalog.list_evidence()[0]["id"])
    updated = catalog.update_evidence(
        before["id"],
        before["revision"],
        "# Career\n\nEmployer: Correct Company\n",
        actor="user",
        source="explicit correction in current application",
    )
    assert updated["id"] == before["id"]
    assert updated["source_name"] == "sources/career.md"
    assert "Correct Company" in catalog.get_evidence(before["id"])["content"]
    assert len(updated["history"]) == 1
    event = updated["history"][0]
    assert event["before_revision"] == before["revision"]
    assert event["after_revision"] == updated["revision"]
    assert event["actor"] == "user"
    assert event["source"] == "explicit correction in current application"
    assert (tmp_path / event["backup"]).read_bytes() == original
    with pytest.raises(PortalDataError) as error:
        catalog.update_evidence(before["id"], before["revision"], "stale edit")
    assert error.value.code == "revision-conflict"
    assert len(catalog.get_evidence(before["id"])["history"]) == 1
    assert [row["source_name"] for row in catalog.list_evidence()] == ["sources/career.md"]


@pytest.mark.parametrize(
    "relative,content",
    [
        ("contributions/current.json", '{"fact":"original"}'),
        ("sources/registry.json", '{"schema_version":"captured-source/v1"}'),
        ("sources/sealed.md", "---\nschema_version: sealed-career/v1\n---\n# Captured source\n"),
        ("sources/profile.json", '{"schemaVersion":"sealed-career/v1","name":"Original"}'),
    ],
)
def test_correction_preserves_immutable_research_objects(tmp_path, relative, content):
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(content)
    catalog = CareerCatalog(tmp_path)
    before = catalog.get_evidence(catalog.list_evidence()[0]["id"])
    with pytest.raises(PortalDataError) as error:
        catalog.update_evidence(before["id"], before["revision"], "replacement")
    assert error.value.code == "career-read-only"
    assert path.read_text() == content
    assert not (tmp_path / ".tomorrowstar-career-history").exists()


def test_correction_atomic_failure_keeps_source_and_backup(tmp_path, monkeypatch):
    from career_evidence_graph import career_portal_data

    (tmp_path / "sources").mkdir()
    path = tmp_path / "sources/career.md"
    original = b"# Career\nOriginal fact\n"
    path.write_bytes(original)
    catalog = CareerCatalog(tmp_path)
    before = catalog.get_evidence(catalog.list_evidence()[0]["id"])
    sources_before = career_source_snapshot(catalog)
    real = career_portal_data.os.replace

    def fail_current(source, destination):
        if destination == path:
            raise OSError("synthetic atomic replace failure")
        return real(source, destination)

    monkeypatch.setattr(career_portal_data.os, "replace", fail_current)
    with pytest.raises(OSError):
        catalog.update_evidence(before["id"], before["revision"], "Corrected fact")
    assert path.read_bytes() == original
    retained = list((tmp_path / ".tomorrowstar-career-history").glob("*/*/before.md"))
    assert len(retained) == 1
    assert retained[0].read_bytes() == original
    assert not list((tmp_path / ".tomorrowstar-career-history").glob("*/*/applied.json"))
    assert career_source_snapshot(catalog)["revision"] == sources_before["revision"]
    assert catalog.get_evidence(before["id"])["history"][0]["status"] == "needs_recheck"


def test_profile_correction_is_used_without_research_resealing(tmp_path):
    (tmp_path / "sources").mkdir()
    path = tmp_path / "sources/profile.json"
    path.write_text('{"name":"Original Person"}')
    catalog = CareerCatalog(tmp_path)
    before = catalog.get_evidence(catalog.list_evidence()[0]["id"])
    updated = catalog.update_evidence(before["id"], before["revision"], '{"name":"Correct Person"}')
    assert career_source_snapshot(catalog)["profile"]["name"] == "Correct Person"
    assert (tmp_path / updated["history"][0]["backup"]).read_text() == '{"name":"Original Person"}'


@pytest.mark.parametrize("content", ['{"name":', "[]", "\ud800"])
def test_invalid_profile_correction_does_not_change_source(tmp_path, content):
    (tmp_path / "sources").mkdir()
    path = tmp_path / "sources/profile.json"
    original = '{"name":"Original Person"}'
    path.write_text(original)
    catalog = CareerCatalog(tmp_path)
    before = catalog.get_evidence(catalog.list_evidence()[0]["id"])
    with pytest.raises(PortalDataError) as error:
        catalog.update_evidence(before["id"], before["revision"], content)
    assert error.value.code == "invalid-document"
    assert path.read_text() == original
    assert not (tmp_path / ".tomorrowstar-career-history").exists()
