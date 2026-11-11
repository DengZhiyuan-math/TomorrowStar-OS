"""Create fresh external inputs for an explicitly synthetic native App journey."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHECKOUT / "src"))

SYNTHETIC_JD = "Python\nunit tests"
JOB_URL = "https://jobs.lever.co/synthetic/11111111-1111-4111-8111-111111111111"
CONTRIBUTION = (
    "# Contribution candidate: Synthetic Python endpoint\n\n"
    "## Scope\nImplemented a Python health-check endpoint and unit tests.\n\n"
    "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
    "| Synthetic implementation and tests | User |\n\n"
    "## Boundaries\nSynthetic fixture only; no production deployment or GPU training claim.\n"
)


def _write(path: Path, text: str, mode=0o600):
    with path.open("x", encoding="utf-8") as output:
        output.write(text)
    path.chmod(mode)


def _json(path: Path, value: dict):
    _write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def create_fixture(
    root: Path, *, preparation: bool = False, browser: str | None = None, mail: bool = False
) -> dict:
    """Create once, never replace or populate an existing directory."""
    from career_evidence_graph.career_portal_data import ApplicationStore

    if (
        browser
        not in {
            None,
            "dom",
            "manual",
            "unknown",
            "integration",
            "integration-upload",
            "ashby-bootstrap",
        }
        or sum((preparation, bool(browser), mail)) > 1
    ):
        raise ValueError("Choose one fixed synthetic mode.")
    root = Path(root).expanduser()
    if not root.is_absolute():
        raise ValueError("Choose an absolute new external fixture directory.")
    if any(part.is_symlink() for part in (root, *root.parents)):
        raise ValueError("Fixture paths cannot contain symbolic links.")
    root = root.resolve()
    if root.is_relative_to(CHECKOUT) or CHECKOUT.is_relative_to(root):
        raise ValueError("Synthetic inputs must remain outside the system checkout.")
    if root.exists():
        raise ValueError("Fixture destination already exists; choose a new directory.")
    if not root.parent.is_dir():
        raise ValueError("The fixture parent directory must already exist.")
    if (preparation or mail) and any((parent / ".git").exists() for parent in root.parents):
        raise ValueError("Preparation LaTeX base must remain outside Git workspaces.")
    root.mkdir(mode=0o700)
    directories = [
        "applications",
        "career",
        "home",
        "tmp",
        "runtime",
        "career/sources",
        "career/contributions",
    ]
    directories += ["information-library", "latex-base"]
    if not preparation:
        directories += ["runtime/single-job-flow", "runtime/single-job-worker"]
    for name in directories:
        (root / name).mkdir(mode=0o700)
    career = root / "career"
    subprocess.run(
        ["git", "init", "--quiet", "--template=", str(career)],
        check=True,
        capture_output=True,
        env={
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": str(root / "home"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
    )
    _write(career / ".gitignore", ".career-evidence/raw/\n")
    _json(career / "sources/profile.json", {"name": "Synthetic Person"})
    _write(career / "contributions/python.md", CONTRIBUTION)
    # Every synthetic resume journey now starts from a real LaTeX template.
    from career_evidence_graph._vendor.job_apply_store import answer_key

    key = answer_key("Full name", {})
    _json(
        root / "information-library/answers.json",
        {
            "schemaVersion": 1,
            "answers": {
                key: {
                    "key": key,
                    "question": "Full name",
                    "value": "Synthetic Person",
                    "scope": {},
                    "state": "confirmed",
                }
            },
            "metadata": {},
        },
    )
    _write(
        root / "latex-base/main.tex",
        "\\documentclass[a4paper]{article}\n"
        "% Synthetic fixture only; no real applicant or capability assessment.\n"
        "\\begin{document}\n"
        "Synthetic Person\n"
        "\\section*{Synthetic Python endpoint}\n"
        "Implemented a Python health-check endpoint and unit tests.\n"
        "\\end{document}\n",
    )
    # Fixed technical preview input only; never claim it compiles the LaTeX above.
    preview = root / "synthetic-preview.pdf"
    with preview.open("xb") as output:
        output.write((CHECKOUT / "tests/fixtures/pdf-export/current-template.pdf").read_bytes())
    preview.chmod(0o600)
    if not preparation:
        from career_evidence_graph.application_worker_fixtures import browser_fixture_job_url

        ApplicationStore(root / "applications").create_application(
            {
                "company": "Synthetic Employer",
                "role_title": "Software Engineer",
                "url": (browser_fixture_job_url(browser) if browser else JOB_URL),
                "job_description": SYNTHETIC_JD if browser or mail else "",
                "application_date": "2026-01-01",
                "notes": "Synthetic native fixture only. No real application or submission.",
            },
            request_id=hashlib.sha256(b"single-job-synthetic/seed").hexdigest()[:32],
        )
        if mail:
            ApplicationStore(root / "applications").create_application(
                {
                    "company": "Synthetic Employer",
                    "role_title": "Python Engineer",
                    "url": "https://jobs.lever.co/synthetic/22222222-2222-4222-8222-222222222222",
                    "application_date": "2026-01-01",
                    "job_description": SYNTHETIC_JD,
                    "notes": "Synthetic mail queue fixture only.",
                },
                request_id=hashlib.sha256(b"mail-synthetic/second").hexdigest()[:32],
            )
    executable = root / "codex-fixture"
    from career_evidence_graph.application_worker_fixtures import synthetic_cli_text

    _write(executable, synthetic_cli_text(), 0o700)
    _json(
        root / "portal.json",
        {
            "applications": str(root / "applications"),
            "career_workspace": str(career),
            **({"preparation_root": str(root / "latex-base")} if mail else {}),
        },
    )
    marker = {
        "schemaVersion": 1,
        "purpose": "browser-synthetic"
        if browser
        else (
            "mail-synthetic"
            if mail
            else "preparation-synthetic"
            if preparation
            else "single-job-synthetic"
        ),
        "codex_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    _json(root / "synthetic-flow.json", marker)
    if browser:
        _json(root / "browser-fixture.json", {"schemaVersion": 1, "scenario": browser})
    return {
        "root": str(root),
        "synthetic": True,
        "new_model_calls": 0,
        "suggested_jd": SYNTHETIC_JD,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--preparation", action="store_true", help="Seed inputs for the preparation-only workflow"
    )
    modes.add_argument(
        "--mail", action="store_true", help="Seed the fixed mail and sequential queue journey"
    )
    modes.add_argument(
        "--browser",
        choices=(
            "dom",
            "manual",
            "unknown",
            "integration",
            "integration-upload",
            "ashby-bootstrap",
        ),
        help="Seed one fixed isolated browser-acceptance scenario",
    )
    parser.add_argument("root", type=Path, help="New absolute directory outside the checkout")
    args = parser.parse_args()
    try:
        result = create_fixture(
            args.root, preparation=args.preparation, browser=args.browser, mail=args.mail
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Synthetic fixture was not created: {error}\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
