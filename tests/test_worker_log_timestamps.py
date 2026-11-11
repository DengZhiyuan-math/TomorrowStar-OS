"""Each worker.log line carries its UTC time; the message after it is unchanged."""

import io
import re
import subprocess
import sys
from pathlib import Path

from career_evidence_graph.application_worker_browser import TimestampedLines

STAMP = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z "


def test_every_line_is_prefixed_once_even_when_print_writes_in_pieces():
    raw = io.StringIO()
    stream = TimestampedLines(raw)
    print('assistance_binding_changed: {"run": true}', file=stream, flush=True)
    stream.write("first half ")
    stream.write("second half\nnext line\n")
    lines = raw.getvalue().splitlines()
    assert len(lines) == 3
    assert all(re.match(STAMP, line) for line in lines)
    assert [re.sub(STAMP, "", line, count=1) for line in lines] == [
        'assistance_binding_changed: {"run": true}',
        "first half second half",
        "next line",
    ]


def test_the_worker_launcher_writes_timestamped_lines(tmp_path):
    """The launcher's own process output (its argument errors here) is stamped too."""
    launcher = Path(__file__).parents[1] / "scripts/run_application_worker.py"
    result = subprocess.run(
        [sys.executable, "-B", str(launcher)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 2
    lines = result.stderr.splitlines()
    assert lines and all(re.match(STAMP, line) for line in lines)
    assert any("--applications" in line for line in lines)
