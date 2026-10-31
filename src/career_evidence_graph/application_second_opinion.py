"""Opus scores the same matching prompt beside the primary model (decided 2026-10-31).

A four-job comparison found sol and Opus each stable within a few points; their gap
shows how differently two models read the same facts. Opus only scores: the primary
model's judgments, citations and inferences still drive qualification and writing.
"""

from __future__ import annotations

import json
import os
import pwd
import subprocess
import tempfile
from pathlib import Path

from ._vendor import job_apply_store as helper
from .codex_cli import strict_output_schema

CLAUDE_MODEL = "claude-opus-5-5"
# Within this many points the two scores are averaged; above it the job needs review.
REVIEW_GAP = 10
_EXECUTABLES = ("/opt/homebrew/bin/claude", "/usr/local/bin/claude")


def _claude_environment(config_dir: Path) -> dict:
    # A Finder-started App has only HOME, PATH and TMPDIR; the CLI then cannot find its
    # keychain login and reports "Not logged in" (installed MC-11, 2026-10-31).
    user = pwd.getpwuid(os.getuid()).pw_name
    return {
        **os.environ,
        "USER": os.environ.get("USER") or user,
        "LOGNAME": os.environ.get("LOGNAME") or user,
        "CLAUDE_CONFIG_DIR": str(config_dir),
    }


class ClaudeScorer:
    """Run the Claude CLI once; return a result record and never raise."""

    def __init__(self, config_dir: Path, executable: str | None = None):
        self.config_dir = Path(config_dir).expanduser()
        self.executable = executable or next(
            (
                path
                for path in (*_EXECUTABLES, str(Path.home() / ".local/bin/claude"))
                if os.access(path, os.X_OK)
            ),
            None,
        )

    def __call__(self, prompt: str, schema: dict, directory: Path) -> dict:
        record = {"model": CLAUDE_MODEL, "status": "failed"}
        if self.executable is None:
            record["error_code"] = "claude_unavailable"
        else:
            try:
                with tempfile.TemporaryDirectory() as work:
                    process = subprocess.run(
                        [
                            self.executable,
                            "-p",
                            "--model",
                            CLAUDE_MODEL,
                            "--effort",
                            "medium",
                            "--output-format",
                            "json",
                            "--json-schema",
                            json.dumps(strict_output_schema(schema)),
                            "--tools",
                            "",
                            "--no-session-persistence",
                        ],
                        input=prompt,
                        capture_output=True,
                        text=True,
                        cwd=work,
                        timeout=300,
                        env=_claude_environment(self.config_dir),
                    )
                value = json.loads(process.stdout or "{}")
                output = value.get("structured_output")
                if value.get("is_error") or not isinstance(output, dict):
                    message = str(value.get("result") or process.stderr)[:300]
                    record["error_code"] = (
                        "claude_not_signed_in"
                        if "log" in message.casefold() or "authenticate" in message.casefold()
                        else "claude_failed"
                    )
                    record["message"] = message
                else:
                    record.update(status="complete", output=output)
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                record.update(error_code="claude_failed", message=repr(error)[:300])
        helper.atomic_write_json(Path(directory) / "second-opinion-result.json", record)
        return record


def summarize(record: dict, requirements: list[dict]) -> dict:
    """Keep only what scoring and review need, aligned to the primary requirements."""
    rows = (record.get("output") or {}).get("requirements")
    if (
        record.get("status") != "complete"
        or not isinstance(rows, list)
        or len(rows) != len(requirements)
    ):
        return {
            "model": CLAUDE_MODEL,
            "status": "failed",
            "error_code": record.get("error_code") or "claude_output_invalid",
        }
    return {
        "model": CLAUDE_MODEL,
        "status": "complete",
        "requirements": [
            {
                "judgment": row.get("judgment"),
                "fit_score": row.get("fit_score"),
                "explanation": str(row.get("explanation") or "")[:1000],
            }
            for row in rows
        ],
    }
