from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def charter_path() -> Path:
    return Path(__file__).parents[1] / "validation" / "charter" / "v1.json"
