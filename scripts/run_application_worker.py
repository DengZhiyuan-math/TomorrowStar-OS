"""Run the independent application worker from this checkout."""

import hashlib
import sys
from pathlib import Path

checkout = Path(__file__).resolve().parents[1]
startup_sources = {
    str(path.relative_to(checkout)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (checkout / "src/career_evidence_graph").rglob("*.py")
}
sys.path.insert(0, str(checkout / "src"))

from career_evidence_graph.application_worker_browser import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(expected_sources=startup_sources))
