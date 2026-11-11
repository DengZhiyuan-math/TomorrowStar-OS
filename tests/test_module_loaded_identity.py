"""Loaded role identities include the actual journal and edit implementations."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("role", ["controller", "worker"])
def test_canonical_material_journal_body_changes_the_owning_role_identity(monkeypatch, role):
    from career_evidence_graph import application_bound_materials, loaded_code

    loaded_code.measure_packaged_roles()
    before = loaded_code.loaded_runtime_revision(role)
    assert before is not None

    def changed_journal(*_args, **_kwargs):
        raise AssertionError("Synthetic canonical journal policy changed")

    monkeypatch.setattr(
        application_bound_materials.read_commit_journal, "__code__", changed_journal.__code__
    )
    after = loaded_code.loaded_runtime_revision(role)
    assert after is not None and after != before


@pytest.mark.parametrize(
    ("module", "name", "roles"),
    [
        ("application_bound_materials", "document_token", {"controller", "worker"}),
        ("application_material_edit", "_adopt_material", {"controller"}),
        ("_vendor.job_apply_store", "read_json_object", {"controller", "worker"}),
        ("worker_process_identity", "valid_process_identity", {"controller", "worker"}),
        ("application_experience_latex", "_fixed_inputs_revision", {"controller", "worker"}),
    ],
)
def test_execution_helper_body_is_covered_only_by_its_actual_roles(
    monkeypatch, module, name, roles
):
    from importlib import import_module

    from career_evidence_graph import loaded_code

    implementation = getattr(import_module(f"career_evidence_graph.{module}"), name)
    loaded_code.measure_packaged_roles()
    before = {role: loaded_code.loaded_runtime_revision(role) for role in ("controller", "worker")}
    assert all(before.values())

    def changed_implementation(*_args, **_kwargs):
        raise AssertionError("Synthetic owning helper policy changed")

    monkeypatch.setattr(implementation, "__code__", changed_implementation.__code__)
    for role, original in before.items():
        current = loaded_code.loaded_runtime_revision(role)
        assert current is not None
        assert (current != original) is (role in roles)


@pytest.mark.parametrize(
    ("module", "name"),
    [
        ("application_bound_materials", "read_commit_journal"),
        ("_vendor.job_apply_store", "read_json_object"),
    ],
)
def test_preparation_identity_includes_its_material_journal_policy(monkeypatch, module, name):
    from importlib import import_module

    from career_evidence_graph import loaded_code

    implementation = getattr(import_module(f"career_evidence_graph.{module}"), name)
    before = loaded_code.loaded_preparation_revision()
    assert before is not None

    def changed_preparation_policy(*_args, **_kwargs):
        raise AssertionError("Synthetic preparation journal policy changed")

    monkeypatch.setattr(implementation, "__code__", changed_preparation_policy.__code__)
    after = loaded_code.loaded_preparation_revision()
    assert after is not None and after != before


@pytest.mark.parametrize("worker_first", [False, True])
def test_module_role_preload_does_not_launch_services_or_write_files(tmp_path, worker_first):
    source = Path(__file__).resolve().parents[1] / "src"
    probe = """
import json
import os
import sys

sys.path.insert(0, sys.argv[1])

def deny_external_actions(event, arguments):
    if event in {"socket.connect", "socket.bind", "subprocess.Popen", "os.system",
                 "os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.link", "os.symlink"}:
        raise AssertionError("Role imports must not start external work: " + event)
    if event == "open" and isinstance(arguments[2], int) and arguments[2] & (
        os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    ):
        raise AssertionError("Role imports must not write files")

sys.addaudithook(deny_external_actions)
from career_evidence_graph.loaded_code import measure_packaged_roles
measured = measure_packaged_roles(worker_first=json.loads(sys.argv[2]))
assert all("career_evidence_graph." + name in sys.modules for name in (
    "application_bound_materials", "application_material_edit",
    "worker_process_identity", "_vendor.job_apply_store",
))
print(json.dumps(measured, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(source), json.dumps(worker_first)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    measured = json.loads(completed.stdout)
    assert measured["controller"].startswith("python-loaded-code/v1:controller:")
    assert measured["worker"].startswith("python-loaded-code/v1:worker:")
    assert list(tmp_path.iterdir()) == []
