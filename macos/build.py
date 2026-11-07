"""Build a self-contained, locally signed Apple Silicon App. No downloads."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SIGNING_SPEC = importlib.util.spec_from_file_location(
    "tomorrowstar_code_signing", Path(__file__).with_name("code_signing.py")
)
signing = importlib.util.module_from_spec(_SIGNING_SPEC)
_SIGNING_SPEC.loader.exec_module(signing)
DEPENDENCIES = (
    "pydantic",
    "pydantic_core",
    "annotated_types",
    "typing_extensions",
    "typing_inspection",
    "playwright",
    "pyee",
    "greenlet",
)
MACH_O = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
NATIVE_HELPERS = (
    "server.py",
    "background_check.py",
    "resume_review.py",
    "verify.py",
    "pdf_export_check.py",
)


def copy_cua_driver(resources: Path, driver: Path) -> dict:
    """Bundle the reviewed bytes without changing the helper's signature/hash."""
    sys.path.insert(0, str(ROOT / "src"))
    from career_evidence_graph.cua_driver import _OWNED_DRIVER_SHA256

    if (
        driver.is_symlink()
        or hashlib.sha256(driver.read_bytes()).hexdigest() != _OWNED_DRIVER_SHA256
    ):
        raise ValueError(
            "Choose the reviewed CuaDriver build; unverified helpers cannot be bundled."
        )
    destination = resources / "cua-driver/cua-driver"
    destination.parent.mkdir()
    shutil.copy2(driver, destination)
    shutil.copy2(ROOT / "references/cua-driver-LICENSE.md", destination.parent / "LICENSE.md")
    subprocess.run(["codesign", "--verify", "--strict", str(destination)], check=True)
    return {
        "path": "cua-driver/cua-driver",
        "sha256": _OWNED_DRIVER_SHA256,
        "upstream": "https://github.com/trycua/cua",
        "revision": "c6cb386cf371fed3580ea1c5a238940ce4911641",
        "license": "MIT",
        "local_divergence": (
            "windowless ownership, scope retention, snapshot and exit repairs; trusted native "
            "handoff and bound material delivery; restricted handoff metadata; receiver grant "
            "wait and host admission time from the takeover budget; DOM set_value with read-back "
            "for date, select, checkbox and radio controls in native handoff; custom combobox "
            "option clicks with proven owner and read-back; hidden file inputs exposed for "
            "upload only; combobox expand clicks name the shown value, and refusals before "
            "admission are ledger rows; core refusals after admission name their reason, "
            "and a popup-hidden combobox trigger reads back its DOM expanded state; "
            "core refusal reason codes survive the SDK projection; hit refusals carry a "
            "bounded diagnosis, trusted clicks center an off-band target first, and main-frame "
            "hit tests use the input point; a delivered file may be proven by its name shown "
            "in the form item when the FileList is cleared, with a readback diagnosis otherwise; "
            "that name is found again by stable container or form when the input is unmounted; "
            "an expanded combobox may be clicked again to collapse it; "
            "refusal reasons never take a prose hint's first word; material refusals carry "
            "their code; a handoff click may take any named control except one whose name "
            "sends the application"
        ),
        # MC-10 successor source tree and its divergence from the sealed MC-06 source.
        "source_manifest_sha256": (
            "3e13e5c367ee860299af4ee421cd9aab5713cef1a4517d8e25cb8d4360587e53"
        ),
        "source_divergence_patch_sha256": (
            "5b1a1a01bef5bcf4c83b73b6f2a3809ae3e1c3946a3861ec454117ccf27f9249"
        ),
        "build_profile": "release, signed with the pinned private identity",
        "additional_local_divergence": (
            "bounded cleanup retry; exact opt-in mock keychain for new synthetic macOS profiles; "
            "ownership guard unchanged"
        ),
        "synthetic_keychain_patch_sha256": (
            "c9ac461bfbf6dcc106ebe7d4cba527a0ed06e6fb5260427b9b3c44ad60a0184a"
        ),
    }


def copy_dependencies(site: Path) -> dict[str, str]:
    """Copy only recorded runtime files, without downloaded browser caches."""
    site.mkdir(parents=True)
    versions = {}
    for name in DEPENDENCIES:
        distribution = importlib.metadata.distribution(name)
        versions[name] = distribution.version
        package_root = Path(distribution.locate_file("")).resolve()
        for relative in distribution.files or []:
            if (
                ".." in relative.parts
                or "__pycache__" in relative.parts
                or str(relative).endswith(".pyc")
            ):
                # Console scripts and development headers are outside runtime site-packages.
                continue
            source = Path(distribution.locate_file(relative)).resolve()
            if not source.is_relative_to(package_root):
                raise ValueError("A dependency RECORD points outside site-packages.")
            destination = site / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return versions


def copy_engine_scripts(system: Path) -> None:
    """Keep execution and experience-generation entrypoints in the bundled system."""
    (system / "scripts").mkdir(parents=True)
    for name in (
        "run_application_worker.py",
        "run_codex_handoff.py",
        "run_experience_generation.py",
    ):
        shutil.copy2(ROOT / "scripts" / name, system / "scripts" / name)


def copy_native_helpers(resources: Path) -> dict[str, str]:
    """Copy only the fixed native helper entrypoints and bind their packaged bytes."""
    hashes = {}
    for name in NATIVE_HELPERS:
        destination = resources / name
        shutil.copy2(ROOT / "macos" / name, destination)
        hashes[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    return hashes


_LOADED_CODE_PROBE = r"""
import json, os, sys
from pathlib import Path
resources = Path(sys.argv[1]).resolve(strict=True)
if not Path(sys.prefix).resolve().is_relative_to(resources / "python"):
    raise RuntimeError("Probe must use the packaged Python runtime")
def audit(event, args):
    if event == "open":
        path, mode, flags = args
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise RuntimeError("Loaded identity imports cannot write files")
        if not isinstance(path, (str, bytes)):
            raise RuntimeError("Loaded identity imports cannot read outside the package")
        opened = Path(os.fsdecode(path))
        resolved = opened.resolve()
        # CPython _osx_support reads this public OS-version metadata. This exact
        # canonical read-only file is the sole exception; no private inputs or
        # other /System files are admitted, and the write guard above still runs.
        public_os_version = Path("/System/Library/CoreServices/SystemVersion.plist")
        if (not resolved.is_relative_to(resources)
            and not (opened == public_os_version and resolved == public_os_version)):
            raise RuntimeError("Loaded identity imports cannot read outside the package")
    if event.startswith(("socket.", "subprocess.", "os.spawn", "os.exec", "os.fork")) or event in {
        "os.system", "os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.chmod",
        "os.link", "os.symlink", "os.truncate", "os.chdir", "ctypes.dlopen",
    }:
        raise RuntimeError("Loaded identity import attempted an external action")
sys.addaudithook(audit)
sys.path.insert(0, str(resources / "system/src"))
from career_evidence_graph.loaded_code import measure_packaged_roles
record = measure_packaged_roles(worker_first=sys.argv[2] == "worker-first")
print(json.dumps(record, sort_keys=True))
"""


def engine_file_inventory(system: Path) -> dict:
    return {
        str(path.relative_to(system)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(system.rglob("*"))
        if path.is_file()
    }


def measure_loaded_code(resources: Path, engine_files: dict) -> dict:
    """Bind two independent, action-free packaged import probes to the source inventory."""
    results = []
    with tempfile.TemporaryDirectory(prefix="tomorrowstar-loaded-probe-") as temporary:
        environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": temporary,
            "CODEX_HOME": str(Path(temporary) / "unconfigured-codex"),
            "TMPDIR": temporary,
            "LANG": "en_US.UTF-8",
        }
        for order in ("controller-first", "worker-first"):
            try:
                result = subprocess.run(
                    [
                        str(resources / "python/bin/python3.13"),
                        "-I",
                        "-B",
                        "-c",
                        _LOADED_CODE_PROBE,
                        str(resources),
                        order,
                    ],
                    cwd=temporary,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except subprocess.CalledProcessError as error:
                # Never dump command arguments or arbitrary import stderr. Keep
                # only a fixed audit reason, the known import order and exit code.
                stderr = error.stderr if isinstance(error.stderr, str) else ""
                reasons = (
                    (
                        "Loaded identity imports cannot read outside the package",
                        "outside-package read blocked",
                    ),
                    ("Loaded identity imports cannot write files", "file write blocked"),
                    (
                        "Loaded identity import attempted an external action",
                        "external action blocked",
                    ),
                    ("Probe must use the packaged Python runtime", "packaged Python required"),
                )
                reason = next(
                    (
                        safe
                        for message, safe in reasons
                        if stderr.rstrip().endswith("RuntimeError: " + message)
                    ),
                    "import failed",
                )
                raise ValueError(
                    f"Packaged loaded identity probe failed ({order}; "
                    f"exit {error.returncode}): {reason}"
                ) from None
            except subprocess.TimeoutExpired:
                raise ValueError(
                    f"Packaged loaded identity probe timed out ({order}; 20 seconds)"
                ) from None
            results.append(json.loads(result.stdout))
    if results[0] != results[1] or engine_file_inventory(resources / "system") != engine_files:
        raise ValueError("Packaged loaded identities or engine inputs changed during measurement")
    record = results[0]
    if (
        not isinstance(record, dict)
        or any(
            not isinstance(record.get(role), str)
            or not re.fullmatch("python-loaded-code/v1:" + role + r":[a-f0-9]{64}", record[role])
            for role in ("controller", "worker")
        )
        or not isinstance(record.get("ui_revision"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", record["ui_revision"])
        or not isinstance(record.get("python_runtime"), str)
    ):
        raise ValueError("Packaged loaded identity could not be measured")
    expected_ui = {
        Path(key).name: value
        for key, value in engine_files.items()
        if key.startswith("src/career_evidence_graph/portal_static/") and len(Path(key).parts) == 4
    }

    def canonical(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()

    if not expected_ui or record["ui_revision"] != canonical(expected_ui):
        raise ValueError("Packaged loaded UI does not match the engine inventory")
    return {
        "protocol": "packaged-loaded-code/v1",
        "engine_files_revision": canonical(engine_files),
        **record,
    }


def build(
    output: Path,
    cua_driver: Path,
    *,
    signing_config: Path | None = None,
    signing_identity: str | None = None,
    allow_ad_hoc_synthetic: bool = False,
) -> Path:
    if sys.platform != "darwin" or platform.machine() != "arm64" or sys.version_info[:2] != (3, 13):
        raise ValueError("Use the locked Python 3.13 environment on Apple Silicon macOS.")
    policy = signing.load_policy(signing_config, signing_identity, allow_ad_hoc_synthetic)
    if output.exists() or output.is_symlink():
        raise ValueError("Existing builds are never overwritten.")
    if output.resolve() != output.absolute():
        raise ValueError("The build output cannot use a symlink or path alias.")
    if output.suffix != ".bundle-candidate" or any(
        part == "Applications" or part.lower().endswith(".app") for part in output.resolve().parts
    ):
        raise ValueError("Use a private .bundle-candidate destination outside Applications.")
    signing.validate_identity(policy)
    if not allow_ad_hoc_synthetic:
        signing.verify_app(policy.installed_app, policy)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tomorrowstar-build-", suffix=".noindex") as temporary:
        stage = Path(temporary)
        app = stage / "TomorrowStar.bundle-staging"
        contents = app / "Contents"
        resources = contents / "Resources"
        executable = contents / "MacOS/TomorrowStar"
        executable.parent.mkdir(parents=True)
        resources.mkdir()
        runtime = resources / "python"
        (runtime / "bin").mkdir(parents=True)
        base = Path(sys.base_prefix)
        shutil.copy2(base / "bin/python3.13", runtime / "bin/python3.13")
        shutil.copytree(
            base / "lib",
            runtime / "lib",
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "site-packages"),
        )
        site = runtime / "lib/python3.13/site-packages"
        versions = copy_dependencies(site)
        system = resources / "system"
        shutil.copytree(
            ROOT / "src/career_evidence_graph",
            system / "src/career_evidence_graph",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (system / "docs").mkdir()
        copy_engine_scripts(system)
        shutil.copy2(
            ROOT / "docs/question-scoring-pipeline.md", system / "docs/question-scoring-pipeline.md"
        )
        native_helpers = copy_native_helpers(resources)
        shutil.copy2(ROOT / "references/README.md", resources / "UPSTREAM-REUSE.md")
        licenses = resources / "licenses"
        licenses.mkdir()
        for reference in (ROOT / "references/upstream").iterdir():
            if not reference.is_dir():
                continue
            for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "NOTICE", "NOTICE.md"):
                source = reference / name
                if source.is_file():
                    shutil.copy2(source, licenses / f"{reference.name}-{name}")
        compiler = [
            "xcrun",
            "swiftc",
            "-O",
            "-module-cache-path",
            str(stage / "swift-cache"),
            "-target",
            "arm64-apple-macos13.0",
        ]
        subprocess.run(
            [
                *compiler,
                str(ROOT / "macos/App.swift"),
                "-o",
                str(executable),
                "-framework",
                "AppKit",
                "-framework",
                "WebKit",
            ],
            check=True,
        )
        subprocess.run(
            [
                *compiler,
                str(ROOT / "macos/pdf_inspect.swift"),
                "-o",
                str(resources / "pdf-inspect"),
                "-framework",
                "PDFKit",
            ],
            check=True,
        )
        shutil.copy2(ROOT / "macos/icons/AppIcon.icns", resources / "AppIcon.icns")
        with (contents / "Info.plist").open("wb") as handle:
            plistlib.dump(
                {
                    "CFBundleName": "TomorrowStar",
                    "CFBundleDisplayName": "TomorrowStar",
                    "CFBundleIdentifier": "dev.tomorrowstar.desktop",
                    "CFBundleExecutable": "TomorrowStar",
                    "CFBundlePackageType": "APPL",
                    "CFBundleShortVersionString": "0.1.0",
                    "CFBundleVersion": "1",
                    "CFBundleIconFile": "AppIcon",
                    "LSMinimumSystemVersion": "13.0",
                    "NSHighResolutionCapable": True,
                    "NSPrincipalClass": "NSApplication",
                    "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
                },
                handle,
            )
        # Sign each bundled Mach-O, then seal the outer App. This is a local signature.
        for path in resources.rglob("*"):
            if path.is_file() and not path.is_symlink():
                with path.open("rb") as handle:
                    binary = handle.read(4) in MACH_O
                if binary:
                    signing.sign_code(path, policy)
        bundled_driver = copy_cua_driver(resources, cua_driver)
        manifest = {
            "format": "tomorrowstar-macos-build/v1",
            "architecture": "arm64",
            "python": platform.python_version(),
            "dependencies": versions,
            "signature": "ad-hoc-synthetic"
            if allow_ad_hoc_synthetic
            else "pinned-certificate-local",
            "personal_data_included": False,
            "cua_driver": bundled_driver,
            "native_helpers": native_helpers,
            "native_tools": {
                "pdf-inspect": hashlib.sha256((resources / "pdf-inspect").read_bytes()).hexdigest()
            },
            "public_inputs": {
                str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted((ROOT / "macos").glob("*"))
                if path.is_file()
            },
            "engine_files": engine_file_inventory(system),
        }
        manifest["loaded_code"] = measure_loaded_code(resources, manifest["engine_files"])
        (resources / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        signing.sign_code(app, policy, app=True)
        signing.verify_app(app, policy)
        shutil.copytree(app, output, symlinks=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home()
        / "Library/Application Support/TomorrowStar/builds.noindex/TomorrowStar.bundle-candidate",
    )
    parser.add_argument("--signing-config", type=Path)
    parser.add_argument(
        "--signing-identity", help="Exact certificate SHA-1; must match the pinned configuration"
    )
    parser.add_argument(
        "--allow-ad-hoc-synthetic",
        action="store_true",
        help="Explicit isolated synthetic packaging only; never install",
    )
    parser.add_argument(
        "--cua-driver", type=Path, required=True, help="Reviewed local CuaDriver build"
    )
    args = parser.parse_args()
    try:
        output = build(
            args.output.absolute(),
            args.cua_driver.absolute(),
            signing_config=args.signing_config,
            signing_identity=args.signing_identity,
            allow_ad_hoc_synthetic=args.allow_ad_hoc_synthetic,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"App build failed: {error}", file=sys.stderr)
        return 1
    print(f"Built {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
