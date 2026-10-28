"""Fixed native-host PDF diagnostic; offline synthetic input, one export attempt."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

SYNTHETIC_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>@page { size: A4; margin: 20mm; } body { font-family: sans-serif; }</style>
</head><body><h1>TomorrowStar synthetic PDF diagnostic</h1>
<p>Offline acceptance fixture. No applicant or employer data.</p>
<p>Native host cold start and PDF export verification.</p></body></html>"""


def load_helper(resources, name):
    """Load a fixed sibling by path; never resolve helpers through caller imports."""
    if name not in {"background_check.py", "verify.py"}:
        raise ValueError("fixed_helper_required")
    spec = importlib.util.spec_from_file_location("native_pdf_" + Path(name).stem, resources / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_root(root):
    parent = Path.home() / "Library/Application Support/TomorrowStar/diagnostics"
    if (
        not root.is_dir()
        or root.is_symlink()
        or root.absolute() != root.resolve()
        or root.parent != parent.resolve()
        or re.fullmatch(r"gui-host-[a-z0-9-]{8,80}", root.name) is None
        or root.stat().st_uid != os.getuid()
        or root.stat().st_mode & 0o777 != 0o700
        or {path.name for path in root.iterdir()} != {"native-tcc.json", "background.log", "tmp"}
    ):
        raise ValueError("private_fresh_diagnostic_directory_required")
    for name in ("native-tcc.json", "background.log", "tmp"):
        path = root / name
        if path.is_symlink() or path.stat().st_uid != os.getuid():
            raise ValueError("private_diagnostic_inputs_required")
    if not (root / "native-tcc.json").is_file() or not (root / "background.log").is_file():
        raise ValueError("native_snapshot_required")
    temporary = root / "tmp"
    if (
        not temporary.is_dir()
        or temporary.stat().st_mode & 0o777 != 0o700
        or any(temporary.iterdir())
    ):
        raise ValueError("fresh_private_temporary_directory_required")


def verify_package(resources, result):
    manifest_path = resources / "build-manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("package_manifest_invalid")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    result["build_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    result["engine_files_match"] = False
    result["native_helpers_match"] = False
    for key, base in (("engine_files", resources / "system"), ("native_helpers", resources)):
        expected = manifest[key]
        if not isinstance(expected, dict) or not expected:
            raise ValueError("package_manifest_invalid")
        if key == "native_helpers" and not {
            "pdf_export_check.py",
            "background_check.py",
            "verify.py",
        }.issubset(expected):
            raise ValueError("package_helper_manifest_incomplete")
        actual = {}
        for name in expected:
            relative = Path(name)
            path = base / relative
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not path.is_file()
                or path.is_symlink()
                or path.resolve() != path
            ):
                raise ValueError("package_file_invalid")
            actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("package_hash_mismatch")
        if key == "engine_files":
            inventory = {str(path.relative_to(base)) for path in base.rglob("*") if path.is_file()}
            if inventory != set(expected):
                raise ValueError("package_inventory_mismatch")
        result[key + "_sha256"] = hashlib.sha256(
            json.dumps(actual, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        result[key + "_match"] = True
    runtime = resources / "python"
    if not Path(sys.prefix).resolve().is_relative_to(runtime) or not Path(
        sys.executable
    ).resolve().is_relative_to(runtime):
        raise ValueError("packaged_runtime_required")


def run(root):
    result = {
        "status": "failed",
        "stage": "root_validation",
        "python_pid": os.getpid(),
        "runtime": sys.executable,
        "chrome_launch_attempted": False,
        "real_ATS": 0,
        "uploads": 0,
        "submits": 0,
        "model_calls": 0,
        "permission_prompts": 0,
        "export_attempts": 0,
    }
    try:
        validate_root(root)
        receipt = root / "pdf-export-result.json"
        descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except (OSError, ValueError):
        print("native_pdf_diagnostic_directory_refused", file=sys.stderr)
        return 1
    with os.fdopen(descriptor, "w") as stream:
        try:
            resources = Path(__file__).resolve().parent
            result["stage"] = "package_identity"
            verify_package(resources, result)
            result["stage"] = "native_identity"
            native = json.loads((root / "native-tcc.json").read_text())
            result.update(
                load_helper(resources, "background_check.py").verify_native_identity(
                    resources, native
                )
            )
            result["stage"] = "registration_preflight"
            load_helper(resources, "verify.py").check_chrome_launch_environment()
            result["stage"] = "pdf_export"
            sys.path.insert(0, str(resources / "system/src"))
            from career_evidence_graph.application_resume import export_pdf

            html = root / "synthetic.html"
            with html.open("x", encoding="utf-8") as source:
                source.write(SYNTHETIC_HTML)
            html.chmod(0o600)
            pdf = root / "synthetic.pdf"
            result.update(chrome_launch_attempted=True, export_attempts=1)
            export_pdf(html, pdf)
            result["stage"] = "pdf_validation"
            if (
                pdf.is_symlink()
                or not pdf.read_bytes().startswith(b"%PDF-")
                or pdf.stat().st_mode & 0o777 != 0o600
            ):
                raise ValueError("synthetic_pdf_invalid")
            result.update(
                status="passed",
                stage="complete",
                pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
            )
        except Exception as error:
            message = str(error)
            result["error_type"] = type(error).__name__
            result["error_code"] = next(
                (
                    code
                    for code in (
                        "macos_chrome_registration_denied",
                        "macos_chrome_registration_unknown",
                    )
                    if message.startswith(code)
                ),
                getattr(error, "code", "native_pdf_" + result["stage"] + "_failed"),
            )
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "stage": result["stage"]}), flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(2)
    raise SystemExit(run(Path(sys.argv[1])))
