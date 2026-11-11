"""Incremental reads of synthetic documentary career material."""

import os
from pathlib import Path

import pytest

from career_evidence_graph import career_portal_data
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    original_run = career_portal_data.subprocess.run
    calls = []

    def counted_read(*args, **kwargs):
        calls.append(args[0][-1])
        return original_run(*args, **kwargs)

    monkeypatch.setattr(career_portal_data.subprocess, "run", counted_read)
    return calls


def test_unchanged_document_reuses_successful_bounded_read(
    tmp_path: Path, reads: list[str]
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    (folder / "note.md").write_text("# Original\nSynthetic content.\n")
    catalog = CareerCatalog(tmp_path)
    identifier = catalog.list_evidence()[0]["id"]
    first = catalog.get_evidence(identifier)
    second = catalog.get_evidence(identifier)

    assert first == second
    assert first["content"] == "# Original\nSynthetic content.\n"
    assert len(reads) == 1


def test_source_revision_changes_only_re_read_changed_documents(
    tmp_path: Path, reads: list[str]
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    note = folder / "note.md"
    note.write_text("# Original\n")
    (folder / "other.md").write_text("# Other\n")
    catalog = CareerCatalog(tmp_path)
    before = career_source_snapshot(catalog)
    assert len(reads) == 2
    assert career_source_snapshot(catalog) == before
    assert len(reads) == 2
    metadata = note.stat()
    note.write_text("# Modified\n")  # Same byte count; preserve the old mtime deliberately.
    os.utime(note, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    after = career_source_snapshot(catalog)
    assert len(reads) == 3
    assert before["revision"] != after["revision"]
    assert career_source_snapshot(catalog) == after
    assert len(reads) == 3


def test_atomic_replacement_is_read_even_with_matching_size_and_mtime(
    tmp_path: Path, reads: list[str]
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    note = folder / "note.md"
    note.write_text("# Original\n")
    catalog = CareerCatalog(tmp_path)
    identifier = catalog.list_evidence()[0]["id"]
    original = catalog.get_evidence(identifier)
    metadata = note.stat()
    replacement = tmp_path / "replacement.md"
    replacement.write_text("# Modified\n")
    os.utime(replacement, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    replacement.replace(note)
    latest = catalog.get_evidence(identifier)
    assert latest["content"] == "# Modified\n"
    assert latest["revision"] != original["revision"]
    assert len(reads) == 2


def test_catalog_rescans_additions_renames_and_deletions(tmp_path: Path, reads: list[str]) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    original = folder / "original.md"
    original.write_text("# Original\n")
    catalog = CareerCatalog(tmp_path)
    first = career_source_snapshot(catalog)
    second_path = folder / "second.md"
    second_path.write_text("# Second\n")
    added = career_source_snapshot(catalog)
    assert len(reads) == 2
    assert first["revision"] != added["revision"]
    renamed_path = folder / "renamed.md"
    second_path.rename(renamed_path)
    renamed = career_source_snapshot(catalog)
    assert len(reads) == 3
    assert renamed["revision"] != added["revision"]
    renamed_path.unlink()
    assert career_source_snapshot(catalog) == first
    assert len(reads) == 3


@pytest.mark.parametrize("replacement", ["file", "parent", "root"])
def test_cached_documents_are_unavailable_after_symlink_replacement(
    tmp_path: Path, reads: list[str], replacement: str
) -> None:
    root = tmp_path / "career"
    folder = root / "reports"
    folder.mkdir(parents=True)
    note = folder / "note.md"
    note.write_text("# Original\n")
    catalog = CareerCatalog(root)
    identifier = catalog.list_evidence()[0]["id"]
    catalog.get_evidence(identifier)
    path = {"file": note, "parent": folder, "root": root}[replacement]
    moved = tmp_path / "moved"
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=replacement != "file")
    with pytest.raises(PortalDataError):
        catalog.get_evidence(identifier)
    assert len(reads) == 1


def test_cached_document_cloud_transition_remains_actionable(
    tmp_path: Path, reads: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    (folder / "note.md").write_text("# Original\n")
    catalog = CareerCatalog(tmp_path)
    identifier = catalog.list_evidence()[0]["id"]
    catalog.get_evidence(identifier)
    monkeypatch.setattr(career_portal_data, "_is_cloud_placeholder", lambda path: True)
    assert catalog.list_evidence()[0]["available"] is False
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence(identifier)
    assert failure.value.status == 503
    assert "Finder" in failure.value.message
    assert len(reads) == 1
    monkeypatch.setattr(career_portal_data, "_is_cloud_placeholder", lambda path: False)
    assert catalog.get_evidence(identifier)["content"] == "# Original\n"
    assert len(reads) == 2


def test_failed_changed_document_read_is_retried_on_next_refresh(
    tmp_path: Path, reads: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    note = folder / "note.md"
    note.write_text("# Original\n")
    catalog = CareerCatalog(tmp_path)
    identifier = catalog.list_evidence()[0]["id"]
    catalog.get_evidence(identifier)
    note.write_text("# Updated\n")
    counted_read = career_portal_data.subprocess.run
    attempts = 0

    def timeout_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise career_portal_data.subprocess.TimeoutExpired("synthetic", 3)
        return counted_read(*args, **kwargs)

    monkeypatch.setattr(career_portal_data.subprocess, "run", timeout_once)
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence(identifier)
    assert failure.value.status == 503
    assert catalog.get_evidence(identifier)["content"] == "# Updated\n"
    assert catalog.get_evidence(identifier)["content"] == "# Updated\n"
    assert attempts == 2
    assert len(reads) == 2


def test_document_changed_during_read_is_not_cached(
    tmp_path: Path, reads: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    note = folder / "note.md"
    note.write_text("# Original\n")
    catalog = CareerCatalog(tmp_path)
    identifier = catalog.list_evidence()[0]["id"]
    counted_read = career_portal_data.subprocess.run

    def changed_during_read(*args, **kwargs):
        result = counted_read(*args, **kwargs)
        note.write_text("# Updated\n")
        return result

    monkeypatch.setattr(career_portal_data.subprocess, "run", changed_during_read)
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence(identifier)
    assert failure.value.status == 503
    monkeypatch.setattr(career_portal_data.subprocess, "run", counted_read)
    assert catalog.get_evidence(identifier)["content"] == "# Updated\n"
    assert len(reads) == 2


@pytest.mark.parametrize("relative_parent", ["reports/nested", "reports", "", ".."])
def test_transient_parent_swap_during_read_cannot_cache_outside_content(
    tmp_path: Path,
    reads: list[str],
    monkeypatch: pytest.MonkeyPatch,
    relative_parent: str,
) -> None:
    root = tmp_path / "container" / "career"
    note = root / "reports" / "nested" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Original\n")
    parent = root.parent if relative_parent == ".." else root / relative_parent
    outside = tmp_path / "outside"
    outside_note = outside / note.relative_to(parent)
    outside_note.parent.mkdir(parents=True, exist_ok=True)
    outside_note.write_text("# Outside\n")
    catalog = CareerCatalog(root)
    identifier = catalog.list_evidence()[0]["id"]
    counted_read = career_portal_data.subprocess.run
    moved = tmp_path / "moved"

    def swap_during_read(*args, **kwargs):
        parent.rename(moved)
        parent.symlink_to(outside, target_is_directory=True)
        try:
            return counted_read(*args, **kwargs)
        finally:
            parent.unlink()
            moved.rename(parent)

    monkeypatch.setattr(career_portal_data.subprocess, "run", swap_during_read)
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence(identifier)
    assert failure.value.status == 503
    monkeypatch.setattr(career_portal_data.subprocess, "run", counted_read)
    assert catalog.get_evidence(identifier)["content"] == "# Original\n"
    assert len(reads) == 2


def test_unrelated_sibling_creation_above_workspace_does_not_fail_read(
    tmp_path: Path, reads: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "career"
    folder = root / "reports"
    folder.mkdir(parents=True)
    (folder / "note.md").write_text("# Original\n")
    catalog = CareerCatalog(root)
    identifier = catalog.list_evidence()[0]["id"]
    counted_read = career_portal_data.subprocess.run

    def sibling_creation(*args, **kwargs):
        (tmp_path / "unrelated.txt").write_text("Independent activity.")
        return counted_read(*args, **kwargs)

    monkeypatch.setattr(career_portal_data.subprocess, "run", sibling_creation)
    assert catalog.get_evidence(identifier)["content"] == "# Original\n"
    assert len(reads) == 1


def test_parent_swap_before_reader_checks_uses_outer_document_identity(
    tmp_path: Path, reads: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "career"
    folder = root / "reports"
    folder.mkdir(parents=True)
    (folder / "note.md").write_text("# Original\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.md").write_text("# Outside\n")
    moved = tmp_path / "moved"
    catalog = CareerCatalog(root)
    identifier = catalog.list_evidence()[0]["id"]
    original_read = career_portal_data._read_document

    def swap_before_reader(*args, **kwargs):
        folder.rename(moved)
        folder.symlink_to(outside, target_is_directory=True)
        try:
            return original_read(*args, **kwargs)
        finally:
            folder.unlink()
            moved.rename(folder)

    monkeypatch.setattr(career_portal_data, "_read_document", swap_before_reader)
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence(identifier)
    assert failure.value.status == 503
    monkeypatch.setattr(career_portal_data, "_read_document", original_read)
    assert catalog.get_evidence(identifier)["content"] == "# Original\n"
    assert len(reads) == 2


@pytest.mark.parametrize(
    "content, status", [(b"x" * 2_000_001, 413), (b"\xff", 400)], ids=["oversize", "utf8"]
)
def test_cached_read_keeps_size_and_utf8_guards_after_changes(
    tmp_path: Path, reads: list[str], content: bytes, status: int
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    note = folder / "note.md"
    note.write_text("# Original\n")
    catalog = CareerCatalog(tmp_path)
    identifier = catalog.list_evidence()[0]["id"]
    catalog.get_evidence(identifier)
    note.write_bytes(content)
    with pytest.raises(PortalDataError) as failure:
        catalog.get_evidence(identifier)
    assert failure.value.status == status
    note.write_text("# Fixed\n")
    assert catalog.get_evidence(identifier)["content"] == "# Fixed\n"
    assert len(reads) == (2 if status == 413 else 3)


def test_cache_memory_budget_evicts_least_recently_used_successful_document(
    tmp_path: Path, reads: list[str]
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    content = "x" * 2_000_000
    for index in range(17):
        (folder / f"{index:02}.md").write_text(content)
    catalog = CareerCatalog(tmp_path)
    identifiers = [row["id"] for row in catalog.list_evidence()]
    for identifier in identifiers[:16]:
        assert len(catalog.get_evidence(identifier)["content"]) == 2_000_000
    catalog.get_evidence(identifiers[0])  # Keep this one recent before reaching the budget.
    catalog.get_evidence(identifiers[16])
    assert len(reads) == 17
    catalog.get_evidence(identifiers[0])
    assert len(reads) == 17
    catalog.get_evidence(identifiers[1])
    assert len(reads) == 18


def test_empty_documents_are_bounded_by_entry_count(
    tmp_path: Path, reads: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    for index in range(3):
        (folder / f"{index}.md").write_text("")
    monkeypatch.setattr(CareerCatalog, "_DOCUMENT_CACHE_MAX_ITEMS", 2)
    catalog = CareerCatalog(tmp_path)
    identifiers = [row["id"] for row in catalog.list_evidence()]
    for identifier in identifiers:
        assert catalog.get_evidence(identifier)["content"] == ""
    assert len(reads) == 3
    catalog.get_evidence(identifiers[0])
    assert len(reads) == 4


def test_content_budget_counts_python_string_storage(
    tmp_path: Path, reads: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    (folder / "unicode.md").write_text("😀" * 4)
    # UTF-8 source occupies 16 bytes, but its Python string occupies more than 32 bytes.
    monkeypatch.setattr(CareerCatalog, "_DOCUMENT_CACHE_MAX_BYTES", 32)
    catalog = CareerCatalog(tmp_path)
    identifier = catalog.list_evidence()[0]["id"]
    assert catalog.get_evidence(identifier)["content"] == "😀" * 4
    assert catalog.get_evidence(identifier)["content"] == "😀" * 4
    assert len(reads) == 2
