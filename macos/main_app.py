"""Maintain the single installed App and its pinned signing requirement.

Never launches the App, grants permissions, or operates an application task.
Evidence roots must be fresh private directories outside this checkout and Applications.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import plistlib
import shutil
import stat
import subprocess
import uuid
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "main_app_code_signing", Path(__file__).with_name("code_signing.py")
)
assert _spec and _spec.loader
signing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(signing)


def save(path: Path, value: object) -> None:
    with path.open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")


def inventory(root: Path) -> list[dict]:
    rows = []
    for path in (root, *sorted(root.rglob("*"))):
        before = path.lstat()
        row = {"path": str(path.relative_to(root)), "mode": stat.S_IMODE(before.st_mode)}
        if path.is_symlink():
            row["link"] = os.readlink(path)
        elif path.is_dir():
            row["directory"] = True
        elif stat.S_ISREG(before.st_mode):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            after = path.lstat()
            require(
                (before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_ino, after.st_size, after.st_mtime_ns),
                "App changed during inventory.",
            )
            row.update(sha256=digest.hexdigest(), size=before.st_size)
        else:
            raise ValueError("Unsupported App filesystem entry.")
        rows.append(row)
    return rows


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120, check=True
    )


def matching_processes(app: Path) -> list[dict]:
    processes = {}
    for line in run(["/bin/ps", "-axo", "pid=,ppid=,command="]).stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) == 3:
            processes[int(fields[0])] = (int(fields[1]), fields[2])
    ancestors = set()
    pid = os.getpid()
    while pid and pid not in ancestors:
        ancestors.add(pid)
        pid = processes.get(pid, (0, ""))[0]
    procpath = ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath
    procpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    procpath.restype = ctypes.c_int
    rows = []
    for pid, (ppid, command) in processes.items():
        buffer = ctypes.create_string_buffer(4096)
        executable = os.fsdecode(buffer.value) if procpath(pid, buffer, len(buffer)) > 0 else None
        if (executable and executable.startswith(str(app) + "/")) or (
            pid not in ancestors and str(app) + "/" in command
        ):
            rows.append({"pid": pid, "ppid": ppid, "command": command, "executable": executable})
    return rows


def validate_bundle(app: Path) -> None:
    require(
        app.is_absolute() and app.resolve() == app and app.is_dir(),
        "App must be a real directory without symlink ancestors.",
    )
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    require(
        info.get("CFBundleIdentifier") == signing.BUNDLE_ID
        and info.get("CFBundleExecutable") == "TomorrowStar",
        "Unexpected App bundle identity.",
    )


def idle(app: Path, root: Path, name: str) -> None:
    processes = matching_processes(app)
    save(root / name, processes)
    require(
        not processes,
        "Main App processes are active; leave them untouched and retry after they exit.",
    )


def evidence_root(path: Path, app: Path) -> Path:
    require(
        path.is_absolute() and not path.exists() and path.resolve() == path,
        "Use a fresh absolute private evidence directory without symlink ancestors.",
    )
    for forbidden in (Path(__file__).resolve().parent.parent, app.parent):
        require(
            not path.is_relative_to(forbidden),
            "Evidence must be outside the checkout and Applications.",
        )
    path.mkdir(mode=0o700, parents=True)
    return path


def copy_bundle(source: Path, target: Path) -> None:
    run(["/usr/bin/ditto", "--rsrc", "--extattr", "--acl", str(source), str(target)])


def maintain(command: str, policy, root: Path, candidate: Path | None = None) -> dict:
    app = policy.installed_app
    require(
        app == Path.home() / "Applications/TomorrowStar.app",
        "Only the fixed installed App can be maintained.",
    )
    require(
        policy.identity_sha1 != "-", "Main App maintenance requires the pinned stable identity."
    )
    validate_bundle(app)
    signing.validate_identity(policy)
    original = inventory(app)
    save(root / "original-inventory.json", original)
    if command == "migrate-signature":
        run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
        details = run(["/usr/bin/codesign", "-dv", "--verbose=4", str(app)])
        save(root / "original-signature.json", {"stdout": details.stdout, "stderr": details.stderr})
        require(
            "Signature=adhoc" in details.stdout + details.stderr,
            "Migration accepts only the existing ad-hoc App; "
            "a signed identity change is forbidden.",
        )
    else:
        signing.verify_app(app, policy)
    if command == "check":
        return {
            "main_requirement_verified": True,
            "configured_identity_available": True,
            "app_changed": False,
            "real_applications_resumed": False,
        }
    require(command in {"migrate-signature", "update"}, "Unknown maintenance command.")
    if command == "update":
        require(
            candidate is not None and candidate.suffix == ".bundle-candidate",
            "Update requires a private .bundle-candidate.",
        )
        require(
            not candidate.is_relative_to(app.parent)
            and not candidate.is_relative_to(Path(__file__).resolve().parent.parent),
            "Candidate must be outside the checkout and Applications.",
        )
        validate_bundle(candidate)
        signing.verify_app(candidate, policy)
        new = inventory(candidate)
        save(root / "candidate-inventory.json", new)
    idle(app, root, "processes-before.json")
    config = Path.home() / "Library/Application Support/TomorrowStar/portal.json"
    config_before = config.read_bytes() if config.is_file() else None
    save(
        root / "configuration-before.json",
        {
            "present": config_before is not None,
            "sha256": hashlib.sha256(config_before).hexdigest()
            if config_before is not None
            else None,
        },
    )
    rollback = root / "rollback-main.bundle-backup"
    copy_bundle(app, rollback)
    require(inventory(rollback) == original == inventory(app), "Rollback copy or original changed.")
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(rollback)])
    if command == "migrate-signature":
        prepared = root / "signed-main.bundle-staging"
        copy_bundle(app, prepared)
        require(inventory(prepared) == original, "Private signing stage differs from original.")
        signing.sign_code(prepared, policy, app=True)
        signing.verify_app(prepared, policy)
        new = inventory(prepared)
        save(root / "signed-stage-inventory.json", new)
    else:
        prepared = candidate
    token = uuid.uuid4().hex
    stage = app.parent / f".TomorrowStar-stage-{token}.bundle-staging"
    holding = app.parent / f".TomorrowStar-replaced-{token}.bundle-backup"
    require(not stage.exists() and not holding.exists(), "Staging paths already exist.")
    copy_bundle(prepared, stage)
    require(inventory(stage) == new, "Staged candidate differs.")
    signing.verify_app(stage, policy)
    idle(app, root, "processes-immediately-before-mutation.json")
    require(inventory(app) == original, "Main App changed before maintenance.")
    save(root / "mutation-requested.json", {"command": command, "backup": str(rollback)})
    os.rename(app, holding)
    try:
        os.rename(stage, app)
    except BaseException:
        os.rename(holding, app)
        raise
    signing.verify_app(app, policy)
    require(inventory(app) == new, "Installed App differs from signed stage.")
    require(inventory(holding) == original, "Preserved original differs.")
    moved = root / "replaced-main-original.bundle-backup"
    shutil.move(str(holding), str(moved))
    require(inventory(moved) == original, "Archived original differs.")
    require(
        config_before == (config.read_bytes() if config.is_file() else None),
        "App configuration changed during maintenance.",
    )
    save(root / "installed-inventory.json", inventory(app))
    save(root / "processes-after.json", matching_processes(app))
    return {
        "main_requirement_verified": True,
        "stable_identity_used": True,
        "original_rollback_verified": True,
        "configuration_unchanged": True,
        "main_app_updated": command == "update",
        "signature_migrated": command == "migrate-signature",
        "native_gui_launched": False,
        "permissions_changed": False,
        "real_applications_resumed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "migrate-signature", "update"))
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    require(
        (args.command == "update") == (args.candidate is not None),
        "Only update accepts --candidate.",
    )
    policy = signing.load_policy()
    root = evidence_root(args.private_root, policy.installed_app)
    try:
        result = maintain(args.command, policy, root, args.candidate)
    except Exception as error:
        save(
            root / "failure.json",
            {
                "type": type(error).__name__,
                "error": str(error),
                "stdout": getattr(error, "stdout", None),
                "stderr": getattr(error, "stderr", None),
            },
        )
        raise
    save(root / "result.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
