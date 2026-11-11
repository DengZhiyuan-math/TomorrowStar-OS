"""Explicit fake model replay retains literal sources and legacy review contracts."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.application_information import read_information_library
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_preparation_fixtures import (
    LITERAL_REPLAY_CACHE_KEY,
    literal_replay_runner,
)
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import ApplicationResumeStore, career_source_snapshot
from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/create_synthetic_flow.py"


@pytest.mark.parametrize("git_parent", [False, True])
def test_full_latex_replay_reuses_literal_sources_and_confirmed_identity(
    tmp_path, monkeypatch, git_parent
):
    root = tmp_path / "full-chain"
    created = subprocess.run(
        [sys.executable, str(SCRIPT), "--preparation", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(root / "codex-fixture"))
    applications = ApplicationStore(root / "applications")
    job = applications.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Synthetic Python Engineer",
            "url": "https://careers.example.test/jobs/full-latex-synthetic",
            "job_description": "Python\nunit tests",
            "application_date": "2026-01-01",
        }
    )
    catalog = CareerCatalog(root / "career")
    sources = career_source_snapshot(catalog)
    library = read_information_library(root / "information-library")
    analysis = analyze_job(job, sources, root / "runtime/analysis")

    def forbidden(*_args):
        raise AssertionError("Draft generation cannot export, open, or compile a PDF")

    store = ApplicationResumeStore(
        applications,
        catalog,
        root / "runtime/material-preparation/resumes",
        exporter=forbidden,
        model_runner=literal_replay_runner(root),
    )
    store._runner_cache_key = LITERAL_REPLAY_CACHE_KEY
    store.model_mode = "synthetic"
    if git_parent:
        store.root.mkdir(parents=True, exist_ok=True)
        (store.root / ".git").mkdir()
    base = root / "latex-base"
    original = (base / "main.tex").read_bytes()
    draft = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        draft_only=True,
        task_inputs={"information_library_revision": library["revision"]},
        latex_base=source_snapshot(base, "main.tex"),
        information_library=library,
    )
    assert draft["origin"] == "generated_latex"
    assert draft["factual_review"] == "pending"
    assert draft["review_status"] == "review_required"
    assert draft["verification_queue"] == draft["omitted_groups"] == []
    assert [row["original"] for row in draft["review_groups"]] == [
        "Synthetic Person\n",
        "\\section*{Synthetic Python endpoint}\n"
        "Implemented a Python health-check endpoint and unit tests.\n",
    ]
    identity = draft["review_groups"][0]["sources"][0]
    assert identity["confirmation_state"] == "confirmed"
    assert identity["source_name"] == "information-library"
    assert draft["review_groups"][1]["sources"][0]["attribution"] == "User"
    payload = json.loads((store.root / draft["id"] / "input.json").read_text())
    assert payload["body_lines"] == [
        {"line_number": 1, "text": "Synthetic Person\n"},
        {"line_number": 2, "text": "\\section*{Synthetic Python endpoint}\n"},
        {
            "line_number": 3,
            "text": "Implemented a Python health-check endpoint and unit tests.\n",
        },
    ]
    assert payload["body_line_count"] == 3
    assert payload["fixed_education_lines"] == []
    assert "Implemented a Python health-check endpoint and unit tests." in draft["latex_source"]
    assert (base / "main.tex").read_bytes() == original
    assert not list((root / "runtime").rglob("*.pdf"))
    assert not (root / "runtime/material-preparation/flow.json").exists()
    raw = json.loads((store.root / draft["id"] / "model-result.json").read_text())
    assert '"new_model_calls": 0' in raw["raw_stdout_jsonl"]
    assert "Literal source replay only" in " ".join(draft["limitations"])
    from career_evidence_graph.application_preparation_fixtures import SyntheticPrismClient

    store.group_prism_client = SyntheticPrismClient(root)
    prepared = store.prepare_group_review(
        draft["id"], draft["draft_sha256"], task_inputs=draft["task_inputs"]
    )
    captured = store.capture_group_review(
        prepared["id"],
        prepared["draft_sha256"],
        task_inputs=draft["task_inputs"],
        expected_source_revision=prepared["source_checkpoint"]["source_revision"],
    )["draft"]
    assert captured["source_checkpoint"]["source_policy"] == "generated-latex-project/v1"
    assert captured["factual_review"] == "pending"
    assert store.draft(captured["id"])["group_preview"] == captured["group_preview"]
