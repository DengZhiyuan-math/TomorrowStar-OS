"""Package-to-loaded mappings bind an actual build probe, not file/code hash equality."""

from test_career_portal_http import portal as portal


def test_frozen_loaded_identity_maps_only_to_its_unchanged_build_record():
    from career_evidence_graph.application_readiness import map_loaded_package

    package = {
        "status": "verified",
        "manifest_revision": "disk-manifest-sha256:synthetic",
        "loaded_mapping": "unknown",
        "signature": "not_checked",
        "loaded_code": {
            "controller": "python-loaded-code/v1:controller:" + "a" * 64,
            "worker": "python-loaded-code/v1:worker:" + "b" * 64,
            "ui_revision": "c" * 64,
        },
    }
    controller = {
        "loaded_engine_revision": package["loaded_code"]["controller"],
        "ui_revision": "c" * 64,
    }
    shown = map_loaded_package(package, package, controller)
    assert shown["loaded_mapping"] == "verified"
    assert shown["signature"] == "not_checked"
    assert controller["loaded_engine_revision"] == package["loaded_code"]["controller"]


def synthetic_record(engine_files):
    from career_evidence_graph.application_worker import digest

    prefix = "src/career_evidence_graph/portal_static/"
    ui = {
        key.removeprefix(prefix): value
        for key, value in engine_files.items()
        if key.startswith(prefix)
    }
    return {
        "protocol": "packaged-loaded-code/v1",
        "engine_files_revision": digest(engine_files),
        "controller": "python-loaded-code/v1:controller:" + "a" * 64,
        "worker": "python-loaded-code/v1:worker:" + "b" * 64,
        "ui_revision": digest(ui),
        "python_runtime": "Synthetic Python runtime",
    }


def package_fixture(tmp_path):
    import hashlib
    import json

    resources = tmp_path / "Resources"
    path = resources / "system/src/career_evidence_graph/portal_static/app.js"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"// Synthetic fixed UI\n")
    files = {
        str(path.relative_to(resources / "system")): hashlib.sha256(path.read_bytes()).hexdigest()
    }
    manifest = {
        "format": "tomorrowstar-macos-build/v1",
        "engine_files": files,
        "loaded_code": synthetic_record(files),
    }
    (resources / "build-manifest.json").write_text(json.dumps(manifest))
    return resources, manifest, path


def test_measured_record_is_bound_to_inventory_and_current_disk(tmp_path):
    import json

    from career_evidence_graph.application_readiness import inspect_disk_package, map_loaded_package

    resources, manifest, path = package_fixture(tmp_path)
    original = inspect_disk_package(resources)
    assert original["matches_manifest"] is True
    controller = {
        "loaded_engine_revision": manifest["loaded_code"]["controller"],
        "ui_revision": manifest["loaded_code"]["ui_revision"],
    }
    assert map_loaded_package(original, original, controller)["loaded_mapping"] == "verified"
    path.write_bytes(b"// Disk drift, not loaded into the running controller\n")
    shown = map_loaded_package(original, inspect_disk_package(resources), controller)
    assert shown["loaded_mapping"] == "mismatch" and shown["status"] == "mismatch"
    assert controller["loaded_engine_revision"] == manifest["loaded_code"]["controller"]
    manifest["loaded_code"]["engine_files_revision"] = "0" * 64
    (resources / "build-manifest.json").write_text(json.dumps(manifest))
    assert inspect_disk_package(resources)["status"] == "unavailable"


def test_old_manifest_and_missing_or_wrong_loaded_identity_do_not_invent_mapping(tmp_path):
    import json

    from career_evidence_graph.application_readiness import inspect_disk_package, map_loaded_package

    resources, manifest, _ = package_fixture(tmp_path)
    current = inspect_disk_package(resources)
    wrong = {
        "loaded_engine_revision": "python-loaded-code/v1:controller:" + "d" * 64,
        "ui_revision": manifest["loaded_code"]["ui_revision"],
    }
    assert map_loaded_package(current, current, wrong)["loaded_mapping"] == "mismatch"
    unknown = {**wrong, "loaded_engine_revision": None}
    assert map_loaded_package(current, current, unknown)["loaded_mapping"] == "unknown"
    del manifest["loaded_code"]
    (resources / "build-manifest.json").write_text(json.dumps(manifest))
    old = inspect_disk_package(resources)
    assert old["matches_manifest"] is True
    assert map_loaded_package(old, old, wrong)["loaded_mapping"] == "unknown"


def builder_module():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "synthetic_loaded_mapping_build", Path(__file__).parents[1] / "macos/build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builder_requires_two_isolated_identical_import_probes(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    module = builder_module()
    resources, manifest, _ = package_fixture(tmp_path)
    expected = manifest["loaded_code"]
    measured = {
        key: expected[key] for key in ("controller", "worker", "ui_revision", "python_runtime")
    }
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps(measured))

    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.measure_loaded_code(resources, manifest["engine_files"])
    assert result == expected
    assert [args[-1] for args, _ in calls] == ["controller-first", "worker-first"]
    assert len(calls) == 2 and calls[0][1]["cwd"] == calls[1][1]["cwd"]
    for args, options in calls:
        assert args[0] == str(resources / "python/bin/python3.13") and args[1:4] == [
            "-I",
            "-B",
            "-c",
        ]
        assert options["env"]["HOME"] == options["cwd"] and options["check"] is True
        assert options["env"]["CODEX_HOME"].startswith(options["cwd"])
    measured["controller"] = None
    import pytest

    with pytest.raises(ValueError, match="could not be measured"):
        module.measure_loaded_code(resources, manifest["engine_files"])


def test_builder_rejects_import_order_instability(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import pytest

    module = builder_module()
    resources, manifest, _ = package_fixture(tmp_path)
    measured = {
        key: manifest["loaded_code"][key]
        for key in ("controller", "worker", "ui_revision", "python_runtime")
    }

    def run(command, **_kwargs):
        return SimpleNamespace(stdout=json.dumps({**measured, "python_runtime": command[-1]}))

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(ValueError, match="changed during measurement"):
        module.measure_loaded_code(resources, manifest["engine_files"])


def test_loaded_probe_is_stable_across_relocation_and_import_order(tmp_path):
    import json
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    from career_evidence_graph import loaded_code

    source = Path(loaded_code.__file__).parent
    results = []
    for name, order in (("first", "False"), ("relocated", "True")):
        destination = tmp_path / name / source.name
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        before = {
            str(path.relative_to(destination)): path.read_bytes()
            for path in destination.rglob("*")
            if path.is_file()
        }
        command = (
            "import sys,json;sys.path.insert(0,sys.argv[1]);"
            "from career_evidence_graph.loaded_code import measure_packaged_roles;"
            "print(json.dumps(measure_packaged_roles(worker_first=" + order + "),sort_keys=True))"
        )
        result = subprocess.check_output(
            [sys.executable, "-I", "-B", "-c", command, str(destination.parent)],
            cwd=tmp_path,
            env={**os.environ, "HOME": str(tmp_path), "CODEX_HOME": str(tmp_path / "unconfigured")},
            timeout=20,
            text=True,
        )
        results.append(json.loads(result))
        assert {
            str(path.relative_to(destination)): path.read_bytes()
            for path in destination.rglob("*")
            if path.is_file()
        } == before
    assert results[0] == results[1]
    assert results[0]["controller"].startswith("python-loaded-code/v1:controller:")
    assert results[0]["worker"].startswith("python-loaded-code/v1:worker:")


def test_native_entry_imports_match_build_probe_without_starting_services(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    from career_evidence_graph import loaded_code

    checkout = Path(loaded_code.__file__).resolve().parents[2]
    code = """
import json, runpy, sys
from pathlib import Path
checkout = Path(sys.argv[1])
sys.path.insert(0, str(checkout / 'src'))
mode = sys.argv[2]
if mode == 'native':
    runpy.run_path(str(checkout / 'macos/server.py'), run_name='native_import_only')
elif mode == 'worker':
    from career_evidence_graph import application_worker_browser
from career_evidence_graph import loaded_code
loaded_code.load_controller_modules()
controller = loaded_code.loaded_runtime_revision('controller')
preparation = loaded_code.loaded_preparation_revision()
measured = loaded_code.measure_packaged_roles(worker_first=mode == 'worker-first')
assert controller == measured['controller']
from career_evidence_graph import application_worker, resume_presentation
application_worker.reserve_execution = lambda *_args, **_kwargs: None
changed_alias = loaded_code.loaded_runtime_revision('controller')
assert changed_alias is not None and changed_alias != controller
resume_presentation.PRESENTATION_INSTRUCTIONS += ' Changed policy.'
changed_policy = loaded_code.loaded_runtime_revision('controller')
assert changed_policy is not None and changed_policy != changed_alias
print(json.dumps({'measured': measured, 'preparation': preparation}, sort_keys=True))
"""
    results = [
        json.loads(
            subprocess.check_output(
                [sys.executable, "-I", "-B", "-c", code, str(checkout), mode],
                cwd=tmp_path,
                env={**os.environ, "HOME": str(tmp_path)},
                timeout=20,
                text=True,
            )
        )
        for mode in ("controller-first", "worker-first", "native", "worker")
    ]
    assert all(result == results[0] for result in results[1:])
    assert all(results[0]["measured"][role] is not None for role in ("controller", "worker"))


def test_startup_frozen_actual_identity_is_not_relabelled_by_new_disk_record(portal, tmp_path):
    import hashlib
    import json
    import shutil

    from career_evidence_graph import career_portal
    from career_evidence_graph.application_worker import digest
    from career_evidence_graph.loaded_code import measure_packaged_roles

    resources = tmp_path / "Resources"
    static = resources / "system/src/career_evidence_graph/portal_static"
    shutil.copytree(career_portal._STATIC, static)
    engine_files = {
        str(path.relative_to(resources / "system")): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in static.iterdir()
        if path.is_file()
    }
    record = {
        "protocol": "packaged-loaded-code/v1",
        "engine_files_revision": digest(engine_files),
        **measure_packaged_roles(),
    }
    manifest = {
        "format": "tomorrowstar-macos-build/v1",
        "engine_files": engine_files,
        "loaded_code": record,
    }
    path = resources / "build-manifest.json"
    path.write_text(json.dumps(manifest))
    # The fixture helper keeps its old options; package evidence is supplied by
    # the same pure projection which create_server exposes, not a business snapshot.
    from career_evidence_graph.career_portal import create_server

    with create_server(
        portal.applications, portal.career, flow_root=tmp_path / "flow", package_resources=resources
    ) as server:
        initial = server.application_readiness()
        assert initial["package"]["loaded_mapping"] == "verified"
        assert initial["package"]["signature"] == "not_checked"
        assert initial["decision"]["can_fill"] is False
        manifest["loaded_code"]["controller"] = "python-loaded-code/v1:controller:" + "d" * 64
        path.write_text(json.dumps(manifest))
        changed = server.application_readiness()
        assert changed["package"]["loaded_mapping"] == "mismatch"
        assert (
            changed["controller"]["loaded_engine_revision"]
            == initial["controller"]["loaded_engine_revision"]
        )
        assert changed["status"] == "blocked"


def test_build_probe_rejects_import_write_and_process_side_effects(tmp_path):
    import os
    import subprocess
    import sys

    module = builder_module()
    resources = tmp_path / "Resources"
    package = resources / "system/src/career_evidence_graph"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    touched = resources / "unexpected-write"
    # This adapter supplies only a synthetic runtime location for testing the real
    # probe's audit boundary. Actual builds still require their packaged Python.
    adapter = "import sys,subprocess;sys.prefix=sys.argv[1]+'/python';exec(sys.argv[3])"
    for body in (
        "open(" + repr(str(touched)) + ",'w').write('must not be written')",
        "subprocess.run([sys.executable,'-c','pass'])",
    ):
        (package / "loaded_code.py").write_text(
            "import sys,subprocess\n" + body + "\ndef measure_packaged_roles(**kwargs): return {}\n"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                adapter,
                str(resources),
                "controller-first",
                module._LOADED_CODE_PROBE,
            ],
            cwd=tmp_path,
            env={**os.environ, "HOME": str(tmp_path), "CODEX_HOME": str(tmp_path / "unconfigured")},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0 and "Loaded identity" in result.stderr
        assert not touched.exists()
    assert not list(package.rglob("*.pyc"))


def test_unchanged_legacy_manifest_stays_unknown_without_backfilling_loaded_record():
    from career_evidence_graph.application_readiness import map_loaded_package

    original = {
        "status": "verified",
        "manifest_revision": "disk-manifest-sha256:legacy",
        "loaded_code": None,
        "loaded_mapping": "unknown",
    }
    result = map_loaded_package(
        original, original, {"loaded_engine_revision": "synthetic-controller"}
    )
    assert result["loaded_mapping"] == "unknown" and result["status"] == "verified"
    assert result["mapping_reason"] == "build_loaded_record_missing"
    assert original["loaded_code"] is None and result["loaded_code"] is None


def test_legacy_manifest_drift_is_blocked_before_missing_record_fallback():
    from test_application_readiness import projection_fixture

    from career_evidence_graph.application_readiness import map_loaded_package, project_readiness

    original = {
        "status": "verified",
        "manifest_revision": "disk-manifest-sha256:legacy",
        "loaded_code": None,
        "loaded_mapping": "unknown",
    }
    for current in (
        {**original, "manifest_revision": "disk-manifest-sha256:replacement"},
        {**original, "status": "mismatch"},
        {**original, "status": "unavailable", "manifest_revision": None},
    ):
        result = map_loaded_package(
            original, current, {"loaded_engine_revision": "synthetic-controller"}
        )
        assert result["loaded_mapping"] == "mismatch" and result["status"] == "mismatch"
        assert result["mapping_reason"] == "disk_package_changed_since_startup"
        args = projection_fixture()
        args["package"] = result
        assert project_readiness(**args)["status"] == "blocked"
        assert original["loaded_code"] is None


def guarded_synthetic_import(tmp_path, body):
    """Test the real hook with a fake runtime prefix, without a packaged build."""
    import os
    import subprocess
    import sys

    module = builder_module()
    resources = tmp_path / "guarded-resources"
    package = resources / "system/src/career_evidence_graph"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "loaded_code.py").write_text(
        "import sys,os\n"
        + body
        + "\ndef measure_packaged_roles(**kwargs): return {'imported':True}\n"
    )
    adapter = "import sys;sys.prefix=sys.argv[1]+'/python';exec(sys.argv[3])"
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            adapter,
            str(resources),
            "controller-first",
            module._LOADED_CODE_PROBE,
        ],
        cwd=tmp_path,
        env={"PATH": os.defpath, "HOME": str(tmp_path), "CODEX_HOME": str(tmp_path / "empty")},
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_probe_allows_only_exact_public_system_version_metadata_read(tmp_path):
    import json
    from pathlib import Path

    import pytest

    public = Path("/System/Library/CoreServices/SystemVersion.plist")
    if not public.is_file():
        pytest.skip("macOS public OS metadata fixture")
    result = guarded_synthetic_import(
        tmp_path, "with open(" + repr(str(public)) + ", 'rb') as stream: assert stream.read(1)"
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"imported": True}


def test_public_metadata_exception_keeps_private_read_write_and_external_action_guards(tmp_path):
    cases = {
        "public-write": "open('/System/Library/CoreServices/SystemVersion.plist','r+')",
        "private-read": "open(" + repr(str(tmp_path / "private-input.txt")) + ").read()",
        "other-system-read": "open('/System/Library/CoreServices/SystemVersionCompat.plist','rb')",
        "socket": "sys.audit('socket.__new__',None,2,1,0)",
        "subprocess": "sys.audit('subprocess.Popen','fixed',[],None,None)",
        "ctypes": "sys.audit('ctypes.dlopen',None)",
    }
    (tmp_path / "private-input.txt").write_text("PRIVATE SYNTHETIC INPUT MUST NOT BE READ")
    alias = tmp_path / "public-os-version-alias"
    alias.symlink_to("/System/Library/CoreServices/SystemVersion.plist")
    cases["public-alias-read"] = "open(" + repr(str(alias)) + ", 'rb')"
    for name, body in cases.items():
        directory = tmp_path / name
        directory.mkdir()
        result = guarded_synthetic_import(directory, body)
        assert result.returncode != 0 and "Loaded identity" in result.stderr
        assert "PRIVATE SYNTHETIC INPUT" not in result.stderr + result.stdout


def test_probe_failure_explains_safe_reason_without_dumping_command_or_stderr(
    tmp_path, monkeypatch
):
    import subprocess

    import pytest

    module = builder_module()
    resources, manifest, _ = package_fixture(tmp_path)

    def denied(command, **kwargs):
        raise subprocess.CalledProcessError(
            1,
            ["PRIVATE_COMMAND_ARGUMENT"],
            stderr=(
                "PRIVATE INPUT BODY\n"
                "RuntimeError: Loaded identity imports cannot read outside the package\n"
            ),
        )

    monkeypatch.setattr(module.subprocess, "run", denied)
    with pytest.raises(ValueError, match="outside-package read blocked") as error:
        module.measure_loaded_code(resources, manifest["engine_files"])
    assert "controller-first" in str(error.value)
    assert "PRIVATE" not in str(error.value)


def test_native_main_passes_exact_bundle_resources_and_legacy_stays_unknown(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    from career_evidence_graph.application_readiness import inspect_disk_package, map_loaded_package

    monkeypatch.setattr(sys, "path", sys.path.copy())
    spec = importlib.util.spec_from_file_location(
        "native_main_package_wiring", Path(__file__).parents[1] / "macos/server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resources, manifest, _ = package_fixture(tmp_path)
    import json

    del manifest["loaded_code"]
    (resources / "build-manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(module, "root", resources)
    monkeypatch.setattr(module, "find_codex_executable", lambda configured: None)
    monkeypatch.setattr(module, "NativePDFInspector", lambda path: None)
    monkeypatch.setattr(
        module,
        "NativeHostBridge",
        lambda *args: SimpleNamespace(snapshot=lambda: {"state": "unknown"}, binding=None),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "server.py",
            "--applications",
            str(tmp_path / "applications"),
            "--career-workspace",
            str(tmp_path / "career"),
            "--flow-root",
            str(tmp_path / "flow"),
        ],
    )
    calls = []
    fake = SimpleNamespace(server_port=4321, application_flow_service=object(), worker_service=None)

    def create(*args, **kwargs):
        assert kwargs.get("package_resources") == resources
        package = inspect_disk_package(kwargs["package_resources"])
        assert package["matches_manifest"] is True and package["loaded_code"] is None
        shown = map_loaded_package(package, package, {"loaded_engine_revision": None})
        assert shown["loaded_mapping"] == "unknown"
        calls.append(kwargs)
        return fake

    monkeypatch.setattr(module, "create_server", create)
    served = []
    monkeypatch.setattr(
        module, "serve_with_parent_pipe", lambda server, *a, **k: served.append(server)
    )

    assert module.main() == 0
    assert len(calls) == 1 and served == [fake]


def test_unknown_probe_failure_and_timeout_do_not_echo_private_diagnostics(tmp_path, monkeypatch):
    import subprocess

    import pytest

    module = builder_module()
    resources, manifest, _ = package_fixture(tmp_path)
    for failure, reason in (
        (
            subprocess.CalledProcessError(9, ["PRIVATE ARG"], stderr="PRIVATE INPUT"),
            "import failed",
        ),
        (subprocess.TimeoutExpired(["PRIVATE ARG"], 20, stderr="PRIVATE INPUT"), "timed out"),
    ):

        def failed(*args, failure=failure, **kwargs):
            raise failure

        monkeypatch.setattr(module.subprocess, "run", failed)
        with pytest.raises(ValueError, match=reason) as error:
            module.measure_loaded_code(resources, manifest["engine_files"])
        assert "PRIVATE" not in str(error.value)


def test_store_import_needs_no_ctypes_action_but_rename_still_hits_the_guard(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    source = tmp_path / "synthetic-source"
    source.write_bytes(b"fixed synthetic storage input")
    destination = tmp_path / "destination"
    program = """
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
def audit(event,args):
    if event == 'ctypes.dlopen': raise RuntimeError('synthetic ctypes guard')
sys.addaudithook(audit)
from career_evidence_graph.validation.store import _rename_noreplace
try:
    _rename_noreplace(Path(sys.argv[2]),Path(sys.argv[3]))
except RuntimeError as error:
    assert str(error) == 'synthetic ctypes guard'
else: raise AssertionError('The actual rename must still require ctypes')
print(json.dumps({'import_without_ctypes':True,'actual_rename_guarded':True}))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            program,
            str(Path(__file__).parents[1] / "src"),
            str(source),
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "import_without_ctypes": True,
        "actual_rename_guarded": True,
    }
    assert source.read_bytes() == b"fixed synthetic storage input" and not destination.exists()
