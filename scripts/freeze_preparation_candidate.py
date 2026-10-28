"""Create or read-only verify a public preparation-source handoff candidate.

This copies reviewed source and synthetic verification inputs. It does not build,
install, execute, or validate an App, or create a standalone full-test checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tomllib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "tomorrowstar-preparation-candidate/v1"
POLICY = "preparation-policy/v1.0"
SCOPE = {
    "kind": "public-source-and-synthetic-verification-handoff",
    "standalone_full_test_checkout": False,
    "app_built_or_installed": False,
    "real_applications_authorized": False,
}
CONFIG = ("pyproject.toml", "uv.lock", ".python-version", "_career_evidence_build.py")
PUBLIC_DOCS = (
    "README.md",
    "ARCHITECTURE.md",
    "CONTEXT.md",
    "CONVENTIONS.md",
    "AGENTS.md",
    "docs/macos-app.md",
    "docs/validation-runs.md",
    "docs/data-boundaries.md",
    "docs/question-scoring-pipeline.md",
)
PROVENANCE = (
    "references/README.md",
    "references/cua-driver-LICENSE.md",
    "references/cua-driver-synthetic-keychain.patch",
)
LICENSES = {"LICENSE", "LICENSE.md", "LICENSE.txt", "NOTICE", "NOTICE.md"}
EXCLUDED = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".scratch",
    ".git",
    ".venv",
    "build",
    "output",
    "runtime",
    "private",
}


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def _safe_path(path: Path) -> Path:
    if ".." in path.parts:
        raise ValueError("Parent traversal is not allowed in source or candidate paths.")
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"Symlinks are not allowed: {path.name}")
    return path


def _read(path: Path) -> bytes:
    _safe_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Expected a regular file: {path.name}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        content = handle.read()
        after = os.fstat(handle.fileno())

    def identity(item):
        return (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )

    if (
        identity(before) != identity(opened)
        or identity(opened) != identity(after)
        or identity(after) != identity(path.stat())
    ):
        raise ValueError(f"Source changed while reading: {path.name}")
    return content


def _walk(root: Path):
    _safe_path(root)
    if not root.is_dir():
        raise ValueError(f"Expected a directory: {root.name}")
    for path in sorted(root.iterdir()):
        _safe_path(path)
        if path.name in EXCLUDED or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_dir():
            yield from _walk(path)
        elif path.is_file():
            yield path
        else:
            raise ValueError(f"Unsafe source entry: {path.name}")


def _category(relative: str) -> str | None:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
        return None
    if any(part in EXCLUDED for part in path.parts) or path.suffix in {".pyc", ".pyo"}:
        return None
    if relative in CONFIG:
        return "configuration"
    if relative in PUBLIC_DOCS:
        return "public_documentation"
    if relative in PROVENANCE:
        return "provenance"
    if len(path.parts) >= 3 and path.parts[:2] == ("src", "career_evidence_graph"):
        return "runtime_source"
    if len(path.parts) == 2 and path.parts[0] == "scripts" and path.suffix == ".py":
        return "launcher_source"
    if (
        len(path.parts) == 2 and path.parts[0] == "macos" and path.suffix in {".py", ".swift"}
    ) or relative == "macos/icons/AppIcon.icns":
        return "native_shell_source"
    if (len(path.parts) == 2 and path.parts[0] == "tests" and path.suffix == ".py") or (
        len(path.parts) >= 3 and path.parts[:2] == ("tests", "fixtures")
    ):
        return "synthetic_verification"
    if (
        len(path.parts) == 4
        and path.parts[:2] == ("references", "upstream")
        and path.name in LICENSES
    ):
        return "provenance"
    return None


def _source_files(root: Path) -> list[Path]:
    _safe_path(root)
    if not root.is_dir():
        raise ValueError("Source root must be an existing directory.")
    paths = [root / name for name in CONFIG]
    paths.append(root / "src/career_evidence_graph/__init__.py")
    for path in paths:
        _read(path)
    paths.extend(_walk(root / "src/career_evidence_graph"))
    for directory in ("scripts", "macos", "tests"):
        base = root / directory
        if base.exists() or base.is_symlink():
            _safe_path(base)
            for path in sorted(base.iterdir()):
                if _category(path.relative_to(root).as_posix()):
                    _safe_path(path)
                    paths.append(path)
    fixtures = root / "tests/fixtures"
    if fixtures.exists() or fixtures.is_symlink():
        paths.extend(_walk(fixtures))
    for relative in (*PUBLIC_DOCS, *PROVENANCE, "macos/icons/AppIcon.icns"):
        path = root / relative
        if path.exists() or path.is_symlink():
            paths.append(path)
    upstream = root / "references/upstream"
    if upstream.exists() or upstream.is_symlink():
        _safe_path(upstream)
        for reference in sorted(upstream.iterdir()):
            _safe_path(reference)
            if reference.is_dir():
                for name in sorted(LICENSES):
                    path = reference / name
                    if path.exists() or path.is_symlink():
                        paths.append(path)
    return sorted(set(paths))


def _inventory(root: Path) -> list[dict]:
    result = []
    for path in _source_files(root):
        relative = path.relative_to(root).as_posix()
        category = _category(relative)
        if category is None:
            raise ValueError(f"Source is outside the public allowlist: {relative}")
        content = _read(path)
        result.append(
            {
                "path": relative,
                "category": category,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return result


def _configuration(root: Path) -> dict:
    project = tomllib.loads(_read(root / "pyproject.toml").decode())
    return {
        "python_version": _read(root / ".python-version").decode().strip(),
        "requires_python": project.get("project", {}).get("requires-python"),
        "dependencies": project.get("project", {}).get("dependencies", []),
        "development_dependencies": project.get("dependency-groups", {}).get("dev", []),
        "lock_sha256": hashlib.sha256(_read(root / "uv.lock")).hexdigest(),
    }


def _manifest(root: Path) -> dict:
    value = {
        "format": FORMAT,
        "policy_version": POLICY,
        "scope": SCOPE,
        "configuration": _configuration(root),
        "files": _inventory(root),
    }
    value["candidate_id"] = "preparation-candidate-" + hashlib.sha256(_json(value)).hexdigest()
    return value


def create(source_root: Path, output: Path) -> dict:
    """Copy one stable allowlisted source snapshot into a new destination."""
    source_root, output = _safe_path(source_root), _safe_path(output)
    if output.exists():
        raise ValueError("Choose a new candidate destination; existing paths are preserved.")
    if not output.parent.is_dir():
        raise ValueError("Candidate parent directory must already exist.")
    for name in ("src", "scripts", "macos", "tests", "references", "docs"):
        if output.is_relative_to(source_root / name):
            raise ValueError("Candidate destination must be outside source input directories.")
    manifest = _manifest(source_root)
    output.mkdir()
    try:
        for item in manifest["files"]:
            content = _read(source_root / item["path"])
            if (
                len(content) != item["size"]
                or hashlib.sha256(content).hexdigest() != item["sha256"]
            ):
                raise ValueError("Source changed while copying the candidate.")
            destination = output / "payload" / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        if _manifest(source_root) != manifest:
            raise ValueError("Source changed while copying the candidate.")
        (output / "manifest.json").write_bytes(_json(manifest))
        return verify(output, source_root)
    except BaseException:
        shutil.rmtree(output)
        raise


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Manifest contains duplicate keys.")
        result[key] = value
    return result


def verify(candidate: Path, source_root: Path | None = None) -> dict:
    """Check sealed bytes and optional checkout equality, without writing or executing."""
    candidate = _safe_path(candidate)
    manifest = json.loads(_read(candidate / "manifest.json"), object_pairs_hook=_object)
    if not isinstance(manifest, dict) or set(manifest) != {
        "format",
        "policy_version",
        "scope",
        "configuration",
        "files",
        "candidate_id",
    }:
        raise ValueError("Malformed candidate manifest.")
    if (
        manifest["format"] != FORMAT
        or manifest["policy_version"] != POLICY
        or manifest["scope"] != SCOPE
    ):
        raise ValueError("Candidate policy or scope does not match.")
    files = manifest["files"]
    if not isinstance(files, list) or not files:
        raise ValueError("Candidate inventory is missing.")
    expected = {"manifest.json"}
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "category", "size", "sha256"}:
            raise ValueError("Malformed candidate inventory entry.")
        path = item["path"]
        if (
            not isinstance(path, str)
            or not _category(path)
            or _category(path) != item["category"]
            or type(item["size"]) is not int
            or item["size"] < 0
            or not isinstance(item["sha256"], str)
            or not re.fullmatch("[0-9a-f]{64}", item["sha256"])
        ):
            raise ValueError("Unsafe candidate inventory entry.")
        relative = "payload/" + path
        if relative in expected:
            raise ValueError("Duplicate candidate inventory entry.")
        expected.add(relative)
    ancestors = {
        parent.as_posix()
        for relative in expected
        for parent in PurePosixPath(relative).parents
        if parent != PurePosixPath(".")
    }
    actual = set()
    for path in candidate.rglob("*"):
        _safe_path(path)
        relative = path.relative_to(candidate).as_posix()
        if path.is_dir():
            if relative not in ancestors:
                raise ValueError("Candidate contains an extra directory.")
        elif path.is_file():
            actual.add(relative)
        else:
            raise ValueError("Candidate contains an unsafe entry.")
    if actual != expected or _json(_manifest(candidate / "payload")) != _json(manifest):
        raise ValueError("Candidate bytes, inventory, configuration, or ID changed.")
    if source_root is not None and _json(_manifest(_safe_path(source_root))) != _json(manifest):
        raise ValueError("Current source differs from the frozen candidate.")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--output", type=Path, required=True)
    create_parser.add_argument("--source-root", type=Path, default=ROOT)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--candidate", type=Path, required=True)
    verify_parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    try:
        manifest = (
            create(args.source_root, args.output)
            if args.operation == "create"
            else verify(args.candidate, args.source_root)
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Candidate {args.operation} failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "candidate_id": manifest["candidate_id"],
                "files": len(manifest["files"]),
                "policy_version": manifest["policy_version"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
