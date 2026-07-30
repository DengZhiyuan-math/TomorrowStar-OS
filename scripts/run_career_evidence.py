"""Explicitly run the checkout's CLI without changing global interpreter startup."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Select this checkout's ``src`` package only for this invoked process."""
    source_root = Path(__file__).resolve().parents[1] / "src"
    if not (source_root / "career_evidence_graph" / "__init__.py").is_file():
        raise RuntimeError("career_evidence_graph source package is missing")
    sys.path.insert(0, str(source_root))
    from career_evidence_graph.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
