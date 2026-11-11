"""Check effective permissions from the pinned installed host without prompting.

Exit 2 means the probe completed but a grant is missing. Never opens a browser,
asks for permissions, accesses normal tasks, or changes a real application.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import time
import uuid
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "main_app_operator", Path(__file__).with_name("main_app.py")
)
if not _spec or not _spec.loader:
    raise RuntimeError("Main App maintenance helpers are unavailable.")
operator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(operator)
inventory = operator.inventory


def save(path, value):
    if not isinstance(value, bytes):
        operator.save(path, value)
        return
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(value)
    if path.read_bytes() != value:
        raise ValueError("Diagnostic receipt copy failed verification.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", required=True, type=Path)
    args = parser.parse_args()
    policy = operator.signing.load_policy()
    app = policy.installed_app
    operator.validate_bundle(app)
    operator.signing.validate_identity(policy)
    operator.signing.verify_app(app, policy)
    root = operator.evidence_root(args.private_root, app)
    original = inventory(app)
    save(root / "app-before.json", original)
    config = Path.home() / "Library/Application Support/TomorrowStar/portal.json"
    config_before = hashlib.sha256(config.read_bytes()).hexdigest() if config.is_file() else None
    save(
        root / "config-before.json", {"present": config_before is not None, "sha256": config_before}
    )
    marker = "gui-host-stable-signing-" + uuid.uuid4().hex[:12]
    diagnostic = Path.home() / "Library/Application Support/TomorrowStar/diagnostics" / marker
    operator.require(not diagnostic.exists(), "Main-host permission diagnostic validation failed.")
    argv = [
        "/usr/bin/open",
        "-W",
        "-n",
        "-g",
        "-a",
        str(app),
        "--args",
        "--permission-check",
        marker,
    ]
    save(
        root / "requested.json",
        {"argv": argv, "diagnostic_root": str(diagnostic), "mode": "permission-only"},
    )
    start = time.monotonic()
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=40)
    save(root / "launch-stdout.bin", result.stdout)
    save(root / "launch-stderr.bin", result.stderr)
    save(
        root / "launch-result.json",
        {"returncode": result.returncode, "elapsed": time.monotonic() - start},
    )
    operator.require(result.returncode == 0, "Main-host permission diagnostic validation failed.")
    for name in ("background-result.json", "native-tcc.json", "background.log"):
        save(root / name, (diagnostic / name).read_bytes())
    receipt = json.loads((root / "background-result.json").read_text())
    native = json.loads((root / "native-tcc.json").read_text())
    operator.require(
        receipt["mode"] == "permission-only" and receipt["browser_prepare_sent"] is False,
        "Main-host permission diagnostic validation failed.",
    )
    operator.require(
        receipt["permission_prompts"] == 0 and receipt["daemon_closed"] is True,
        "Main-host permission diagnostic validation failed.",
    )
    operator.require(
        native["windows"] == 0 and native["active"] is False,
        "Main-host permission diagnostic validation failed.",
    )
    operator.require(
        receipt["native_and_embedded_permissions_match"] is True,
        "Main-host permission diagnostic validation failed.",
    )
    operator.require(
        receipt["bundle_id"] == "dev.tomorrowstar.desktop",
        "Main-host permission diagnostic validation failed.",
    )
    operator.require(
        receipt["python_responsible_pid"] == receipt["native_pid"],
        "Main-host permission diagnostic validation failed.",
    )
    operator.require(
        receipt["daemon_responsible_pid"] == receipt["native_pid"],
        "Main-host permission diagnostic validation failed.",
    )
    operator.require(
        receipt["proxy_responsible_pid"] == receipt["native_pid"],
        "Main-host permission diagnostic validation failed.",
    )
    stopped = []
    for pid in sorted(
        {receipt[key] for key in ("native_pid", "python_pid", "daemon_pid", "proxy_pid")}
    ):
        check = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "pid=,lstart=,command="], capture_output=True
        )
        stopped.append(
            {
                "pid": pid,
                "returncode": check.returncode,
                "stdout": check.stdout.decode(),
                "stderr": check.stderr.decode(),
            }
        )
    save(root / "process-readback.json", stopped)
    operator.require(
        all(row["returncode"] == 1 and (not row["stdout"].strip()) for row in stopped),
        "Main-host permission diagnostic validation failed.",
    )
    after = inventory(app)
    save(root / "app-after.json", after)
    config_after = hashlib.sha256(config.read_bytes()).hexdigest() if config.is_file() else None
    operator.require(
        original == after and config_before == config_after,
        "Main-host permission diagnostic validation failed.",
    )
    signed = subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
        capture_output=True,
        timeout=30,
    )
    save(
        root / "signature.json",
        {
            "returncode": signed.returncode,
            "stdout": signed.stdout.decode(),
            "stderr": signed.stderr.decode(),
        },
    )
    operator.require(signed.returncode == 0, "Main-host permission diagnostic validation failed.")
    summary = {
        "accessibility": receipt["accessibility"],
        "screen_recording": receipt["screen_recording"],
        "current_main_identity_verified": True,
        "responsibility_chain_verified": True,
        "nonprompt_only": True,
        "browser_created": False,
        "all_owned_pids_exited": True,
        "app_bytes_and_modes_unchanged": True,
        "configuration_unchanged": True,
        "signature_verified": True,
        "real_applications_resumed": False,
    }
    save(root / "summary.json", summary)
    for path in (root, *root.rglob("*")):
        operator.require(
            stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600),
            "Main-host permission diagnostic validation failed.",
        )
    print(json.dumps(summary))
    return 0 if summary["accessibility"] and summary["screen_recording"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
