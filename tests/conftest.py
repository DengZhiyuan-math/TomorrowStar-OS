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
