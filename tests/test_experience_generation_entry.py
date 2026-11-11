"""The production entry prepares an external-agent handoff, including wrapped runtimes."""

import json
import shutil
import subprocess
import sys
from functools import partial
from pathlib import Path

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.codex_cli import run_codex_exec


@pytest.mark.parametrize("wrapped", [False, True])
def test_default_and_configured_runtime_never_call_whole_library_model(
    full_latex, monkeypatch, wrapped
):
    store, job, snapshot, analysis, _, project, _, inputs = full_latex
    store.model_runner = partial(run_codex_exec, environment={}) if wrapped else run_codex_exec
    calls = []

    def prepare(*args, **kwargs):
        calls.append(kwargs)
        return {"kind": "experience_handoff"}

    monkeypatch.setattr(generation, "prepare_generation", prepare)
    result = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=snapshot,
        analysis=analysis,
        task_inputs=inputs,
        latex_base={"project_root": str(project)},
        draft_only=True,
    )
    assert result == {"kind": "experience_handoff"}
    assert len(calls) == 1
    assert calls[0]["source_snapshot"] == snapshot


def test_bundled_cli_reads_handoff_without_public_git_checkout(full_latex, tmp_path):
    store, job, snapshot, analysis, _, project, _, inputs = full_latex
    store.model_runner = run_codex_exec
    subprocess.run(["git", "init", "--quiet", "--template=", str(store.catalog.root)], check=True)
    state = generation.prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=snapshot,
        analysis=analysis,
        task_inputs=inputs,
        latex_base=source_snapshot(project, "main.tex"),
    )
    checkout = Path(__file__).resolve().parents[1]
    system = tmp_path / "installed/Contents/Resources/system"
    shutil.copytree(checkout / "src", system / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (system / "scripts").mkdir()
    launcher = system / "scripts/run_experience_generation.py"
    shutil.copy2(checkout / "scripts/run_experience_generation.py", launcher)
    assert not any((parent / ".git").exists() for parent in (system, *system.parents))
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(launcher),
            "--applications",
            str(store.applications.root),
            "--career-workspace",
            str(store.catalog.root),
            "--resume-root",
            str(store.root),
            "status",
            "--generation-id",
            state["id"],
        ],
        cwd=system,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == state
