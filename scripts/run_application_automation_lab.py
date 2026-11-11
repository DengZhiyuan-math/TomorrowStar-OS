"""Isolated automated-lane entry point; preflight never starts a browser."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

checkout = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(checkout / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True, help="New isolated lab directory")
    parser.add_argument("--applications", type=Path)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--run-synthetic", action="store_true")
    parser.add_argument("--fixture-origin", default="")
    parser.add_argument("--cua", action="store_true")
    args = parser.parse_args(argv)
    if args.run_synthetic and (
        args.applications is None
        or not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", args.fixture_origin)
    ):
        parser.error("Synthetic execution requires applications and an explicit loopback fixture.")
    if args.cua and not args.run_synthetic:
        parser.error("--cua requires explicit --run-synthetic; preflight stays offline.")
    from career_evidence_graph.application_storage import private_root

    root = private_root(args.runtime)
    if any((root / marker).exists() for marker in ("run.json", "handoff.json", ".worker.lock")):
        parser.error("Use a fresh lab runtime; existing worker and handoff records are preserved.")
    evidence = []
    for source in args.evidence:
        data = source.read_bytes()
        evidence.append({"path": str(source.resolve()), "sha256": hashlib.sha256(data).hexdigest()})
    report = {
        "schemaVersion": 1,
        "mode": "synthetic" if args.run_synthetic else "offline_preflight",
        "runtime": str(root),
        "fixture_origin": args.fixture_origin,
        "native_requested": args.cua,
        "native_verified": False,
        "new_model_calls": 0,
        "real_ats": 0,
        "automatic_final_submits": 0,
        "preserved_evidence": evidence,
        "native_blockers": [
            "Installed default driver was rejected by the background attachment guard.",
            "Reviewed candidate could not confirm LaunchServices PID against the isolated profile.",
            "LaunchServices PID, argv, profile and exit evidence required; guards unchanged.",
            "Legacy tests still need window/source/tool/diagnostic-field alignment.",
        ],
    }
    destination = root / ("preflight-" + uuid4().hex + ".json")
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"report": str(destination), "mode": report["mode"]}), flush=True)
    if not args.run_synthetic:
        return 0
    from career_evidence_graph.application_worker_browser import main as worker_main

    worker_args = [
        "--applications",
        str(args.applications),
        "--runtime",
        str(root),
        "--fixture-origin",
        args.fixture_origin,
    ]
    worker_args += ["--cua"] if args.cua else ["--headless"]
    return worker_main(worker_args)


if __name__ == "__main__":
    raise SystemExit(main())
