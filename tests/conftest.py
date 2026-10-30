from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def charter_path() -> Path:
    return Path(__file__).parents[1] / "validation" / "charter" / "v1.json"


@pytest.fixture(autouse=True)
def _restore_dedicated_codex_home():
    # The in-process backend publishes its dedicated Codex home (MC-21); keep it per test.
    saved = os.environ.get("TOMORROWSTAR_CODEX_HOME")
    yield
    if saved is None:
        os.environ.pop("TOMORROWSTAR_CODEX_HOME", None)
    else:
        os.environ["TOMORROWSTAR_CODEX_HOME"] = saved


@pytest.fixture
def reading_limits(monkeypatch):
    """Exercise the excerpt reader under the limits that made whole-library reading too big."""
    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "128000")
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "60000")


@pytest.fixture
def planner_path(monkeypatch, reading_limits):
    """Exercise directory selection, which runs when the whole library does not fit."""
    from career_evidence_graph import application_matching_pipeline

    monkeypatch.setattr(application_matching_pipeline, "_whole_library_plan", lambda *_: None)
