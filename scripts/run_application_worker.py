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

from career_evidence_graph.application_worker_browser import (  # noqa: E402
    main,
    timestamp_log_lines,
)

if __name__ == "__main__":
    # Each worker.log line starts with its ISO 8601 UTC time (milliseconds).
    timestamp_log_lines()
    raise SystemExit(main(expected_sources=startup_sources))
