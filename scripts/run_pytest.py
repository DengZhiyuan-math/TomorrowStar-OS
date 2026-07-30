"""Explicitly run pytest against this checkout's source package."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Select this checkout's ``src`` package only for this pytest process."""
    source_root = Path(__file__).resolve().parents[1] / "src"
    if not (source_root / "career_evidence_graph" / "__init__.py").is_file():
        raise RuntimeError("career_evidence_graph source package is missing")
    sys.path.insert(0, str(source_root))
    import pytest

    return pytest.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
