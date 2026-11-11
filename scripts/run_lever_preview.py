"""Start a disposable ATS preview using the real local backend."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import webbrowser
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from career_evidence_graph.application_worker import WorkerStore
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic Lever / Greenhouse usable preview")
    parser.add_argument("--platform", choices=("lever", "greenhouse", "mixed"), default="lever")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--cdp-port", type=int, default=0)
    parser.add_argument(
        "--output", type=Path, help="Explicit new synthetic directory outside checkout"
    )
    args = parser.parse_args()
    root = args.output or Path(tempfile.mkdtemp(prefix="tomorrowstar-application-preview-"))
    root.mkdir(exist_ok=True)
    apps, career, runtime = (root / name for name in ("applications", "career", "worker"))
    for path in (apps, career, runtime):
        path.mkdir(mode=0o700)
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    (career / ".gitignore").write_text(".career-evidence/raw/\n")
    store = ApplicationStore(apps)
    for index, (company, country) in enumerate(
        (
            ("Preview Alps", "CHE"),
            ("Preview Lake", "CHE"),
            ("Preview Bay", "USA"),
            ("Preview Berlin", "DEU"),
        ),
        1,
    ):
        platform = args.platform
        if platform == "mixed":
            platform = "lever" if index % 2 else "greenhouse"
        url = (
            f"https://jobs.lever.co/preview-{index}/00000000-0000-0000-0000-{index:012d}"
            if platform == "lever"
            else f"https://job-boards.greenhouse.io/preview-{index}/jobs/{1000 + index}"
        )
        store.create_application(
            {
                "company": company,
                "role_title": "Synthetic Engineer",
                "status": "drafting",
                "location": country,
                "url": url,
                "application_strategy": "batch",
            }
        )
    # Minimal valid PDFs. These contain synthetic text only.
    for index in range(1, 5):
        text = f"BT /F1 18 Tf 30 100 Td (Synthetic resume {index} - no personal information) Tj ET"
        objects = [
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 180] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
        ]
        raw = b"%PDF-1.4\n"
        offsets = []
        for number, body in enumerate(objects, 1):
            offsets.append(len(raw))
            raw += f"{number} 0 obj\n{body}\nendobj\n".encode()
        position = len(raw)
        raw += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(
            f"{offset:010d} 00000 n \n".encode() for offset in offsets
        )
        raw += f"trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n{position}\n%%EOF\n".encode()
        (root / f"synthetic-resume-{index}.pdf").write_bytes(raw)
    answers = WorkerStore(store, runtime)
    with store.write_lock():
        for question, value, scope in (
            ("Full name", "Preview Applicant", {}),
            ("First name", "Preview", {}),
            ("Last name", "Applicant", {}),
            ("Email address", "preview@example.invalid", {}),
            ("Will you now or in the future require visa sponsorship?", "No", {"country": "USA"}),
            ("Are you currently authorized to work in this country?", "Yes", {"country": "USA"}),
        ):
            answers.answers.put_answer(
                {
                    "question": question,
                    "value": value,
                    "scope": scope,
                    "state": "confirmed",
                    "source": "synthetic_fixture",
                }
            )
    server = create_server(
        apps,
        career,
        port=args.port,
        worker_root=runtime,
        worker_fixtures=True,
        worker_headless=args.headless,
        worker_cdp_port=args.cdp_port,
    )
    url = f"http://127.0.0.1:{server.server_port}/#applications"
    print(f"{args.platform.title()} preview: {url}", flush=True)
    print(f"Synthetic PDFs and runtime: {root}", flush=True)
    if args.open:
        webbrowser.open(url)
    with server, suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
