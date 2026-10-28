"""Native preparation fixtures use explicit, isolated, entirely synthetic inputs."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from career_evidence_graph.application_gmail import RECOMMENDATION_QUERY
from career_evidence_graph.application_information import read_information_library
from career_evidence_graph.career_portal_data import ApplicationStore

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/create_synthetic_flow.py"


def create(root):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--preparation", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_preparation_fixture_starts_with_empty_applications_and_no_work(tmp_path):
    root = tmp_path / "preparation"
    result = create(root)
    assert result.returncode == 0, result.stderr
    assert json.loads((root / "synthetic-flow.json").read_text()) == {
        "schemaVersion": 1,
        "purpose": "preparation-synthetic",
        "codex_sha256": hashlib.sha256((root / "codex-fixture").read_bytes()).hexdigest(),
    }
    assert json.loads((root / "portal.json").read_text()) == {
        "applications": str(root / "applications"),
        "career_workspace": str(root / "career"),
    }
    assert ApplicationStore(root / "applications").list_applications() == []
    for name in ("runtime", "home", "tmp"):
        assert (root / name).is_dir()
        assert list((root / name).iterdir()) == []
    assert (root / "career/contributions/python.md").is_file()
    assert read_information_library(root / "information-library")["status"] == "available"
    assert (root / "codex-fixture").read_text().startswith("#!/bin/sh\nexec ")
    injected = tmp_path / "injected"
    injected.mkdir()
    sentinel = tmp_path / "unexpected-sitecustomize"
    (injected / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n"
    )
    version = subprocess.run(
        [str(root / "codex-fixture"), "--version"],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ | {"PYTHONPATH": str(injected)},
    )
    assert version.returncode == 0, version.stderr
    assert "isolated=1 bytecode_writes=0" in version.stdout
    assert not sentinel.exists()


def test_explicit_intake_reads_and_saves_fixed_jd_without_flow_or_real_io(tmp_path, monkeypatch):
    import socket
    import urllib.request

    from career_evidence_graph.application_preparation_fixtures import create_preparation_intake

    root = tmp_path / "intake-fixture"
    assert create(root).returncode == 0

    def forbidden(*args, **kwargs):
        raise AssertionError("Synthetic intake must not call real mail, model, or network adapters")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    applications = ApplicationStore(root / "applications")
    service = create_preparation_intake(applications, root / "runtime/material-preparation/intake")
    try:
        initial = service.snapshot()
        assert initial["status"] == "idle"
        assert initial["recommendations"] == []
        assert not (service.root / "runs").exists()
        service.refresh()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = service.snapshot()
            if state["status"] != "running":
                break
            time.sleep(0.005)
        assert state["status"] == "complete", state
        assert state["progress"]["account_verified"] is True
        assert state["progress"]["source_complete"] == 1
        row = state["recommendations"][0]
        assert row["url"] == "https://www.linkedin.com/jobs/view/424242"
        assert row["company"] == "Synthetic Employer"
        assert row["role_title"] == "Synthetic Python Engineer"
        assert row["job_description"] == "Python\nunit tests"
        assert row["jd_completeness"] == "full"
        assert len(applications.list_applications()) == 1
        assert row["selection_status"] == "saved"
        run = next((service.root / "runs").iterdir())
        capture = json.loads((run / "reader-result.json").read_text())
        assert capture["provenance"]["source"] == "preparation-synthetic"
        assert capture["provenance"]["new_model_calls"] == 0
        assert not (root / "runtime/single-job-worker").exists()
        assert not (root / "runtime/material-preparation/flow.json").exists()
    finally:
        service.close()


def test_preparation_seeds_standalone_full_latex_and_confirmed_synthetic_identity(tmp_path):
    from career_evidence_graph.application_prism import source_snapshot

    root = tmp_path / "full-latex"
    assert create(root).returncode == 0
    base = root / "latex-base"
    checkpoint = source_snapshot(base, "main.tex")
    assert checkpoint["project_root"] == str(base)
    text = (base / "main.tex").read_text()
    assert text.startswith("\\documentclass[a4paper]{article}\n")
    assert "Synthetic Person\n" in text
    assert "Implemented a Python health-check endpoint and unit tests.\n" in text
    assert text.endswith("\\end{document}\n")
    assert not any((parent / ".git").exists() for parent in (base, *base.parents))
    library = read_information_library(root / "information-library")
    assert library["records"] == [
        {
            "key": library["records"][0]["key"],
            "question": "Full name",
            "value": "Synthetic Person",
            "scope": {},
            "state": "confirmed",
        }
    ]
    assert not list((root / "runtime").rglob("*.pdf"))
    assert not (root / "runtime/material-preparation/flow.json").exists()


@pytest.mark.parametrize("worktree", [False, True])
def test_preparation_rejects_git_ancestor_before_creating_fixture(tmp_path, worktree):
    parent = tmp_path / "external-repository"
    parent.mkdir()
    git = parent / ".git"
    if worktree:
        git.write_text("gitdir: elsewhere\n")
    else:
        git.mkdir()
    root = parent / "fixture"
    result = create(root)
    assert result.returncode == 1
    assert "outside Git workspaces" in result.stderr
    assert not root.exists()


def test_preparation_copies_fixed_pdf_as_synthetic_input_without_creating_task_output(tmp_path):
    root = tmp_path / "fixed-pdf"
    assert create(root).returncode == 0
    preview = root / "synthetic-preview.pdf"
    assert (
        preview.read_bytes()
        == (SCRIPT.parents[1] / "tests/fixtures/pdf-export/current-template.pdf").read_bytes()
    )
    assert preview.stat().st_mode & 0o777 == 0o600
    assert not list((root / "runtime").rglob("*.pdf"))


def test_preparation_generator_preserves_existing_roots_and_rejects_path_escape(tmp_path):
    root = tmp_path / "existing"
    root.mkdir()
    retained = root / "preserved.txt"
    retained.write_bytes(b"Preserve earlier progress.\n")
    result = create(root)
    assert result.returncode == 1 and "already exists" in result.stderr
    assert list(root.iterdir()) == [retained]
    assert retained.read_bytes() == b"Preserve earlier progress.\n"
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    result = create(alias / "escaped")
    assert result.returncode == 1 and "symbolic links" in result.stderr
    assert not (root / "escaped").exists()
    result = create(SCRIPT.parents[1] / "forbidden-preparation-fixture")
    assert result.returncode == 1 and "outside the system checkout" in result.stderr


def test_fixed_source_normalization_keeps_only_the_fixture_identity(tmp_path):
    from career_evidence_graph.application_preparation_fixtures import create_preparation_intake

    applications_root = tmp_path / "applications"
    applications_root.mkdir()
    service = create_preparation_intake(ApplicationStore(applications_root), tmp_path / "intake")
    try:
        capture = service.fetcher("https://linkedin.com/jobs/view/424242/?trackingId=synthetic")
        assert capture["url"] == "https://www.linkedin.com/jobs/view/424242"
        assert capture["final_url"] == "https://www.linkedin.com/jobs/view/424242"
        assert capture["body_text"] == "Python\nunit tests"
        assert capture["new_model_calls"] == 0
    finally:
        service.close()


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/999999",
        "https://other.linkedin.com/jobs/view/424242",
        "http://www.linkedin.com/jobs/view/424242",
        "https://user@www.linkedin.com/jobs/view/424242",
        "https://www.linkedin.com:444/jobs/view/424242",
        "https://example.test/jobs/view/424242",
    ],
)
def test_fixture_fetcher_rejects_every_other_source_without_fallback(tmp_path, url):
    from career_evidence_graph.application_preparation_fixtures import create_preparation_intake

    applications_root = tmp_path / "applications"
    applications_root.mkdir()
    service = create_preparation_intake(ApplicationStore(applications_root), tmp_path / "intake")
    try:
        with pytest.raises(ValueError, match="Synthetic source"):
            service.fetcher(url)
    finally:
        service.close()


@pytest.mark.parametrize(
    "change",
    [
        {"page_token": "other-page"},
        {"expected_mailbox_identity": "a" * 64},
        {"verify_account": False},
        {"admit_search": lambda: False},
        {"query": "in:anywhere"},
        {"max_results": 0},
    ],
)
def test_fixture_reader_accepts_only_initial_read_only_recommendation_window(tmp_path, change):
    from career_evidence_graph.application_preparation_fixtures import create_preparation_intake

    applications_root = tmp_path / "applications"
    applications_root.mkdir()
    service = create_preparation_intake(ApplicationStore(applications_root), tmp_path / "intake")
    try:
        scope = {
            "max_results": 3,
            "query": RECOMMENDATION_QUERY,
            "page_token": None,
            "account_context": "b" * 64,
            "window_context": "Synthetic fixture window",
            "verify_account": True,
            "expected_mailbox_identity": None,
            "admit_search": lambda: True,
        }
        with pytest.raises(ValueError, match="Synthetic reader"):
            service.reader(tmp_path / "reader", **(scope | change))
        assert not (tmp_path / "reader").exists()
        assert service.snapshot()["status"] == "idle"
    finally:
        service.close()
