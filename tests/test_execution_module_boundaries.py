"""Execution consumes checked targets; pure controls do not depend on browsers."""

import json
import subprocess
import sys
from pathlib import Path

from test_application_automation import application_store as application_store


def test_checked_target_is_readonly_and_prompt_builder_consumes_same_target(application_store):
    from career_evidence_graph.application_automation import (
        prepare_application_task,
        validate_application_target,
    )

    store, app = application_store
    before = {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
    target = validate_application_target(store, app["id"], app["revision"])
    assert target["application_id"] == app["id"]
    assert target["revision"] == app["revision"]
    assert target["platform"] == "lever"
    assert "prompt" not in target
    prompt = prepare_application_task(store, app["id"], app["revision"])["prompt"]
    emitted = json.loads(prompt.split("\n\n")[2])
    assert emitted == {
        "application_id": app["id"],
        "note_path": str(store.root / app["source_name"]),
        "note_sha256": app["revision"],
        "company": app["company"],
        "role_title": app["role_title"],
        "job_url": target["job_url"],
        "ats": target["platform"],
    }
    assert before == {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}


def test_control_write_predicate_has_one_implementation_and_compatible_aliases():
    from career_evidence_graph.application_worker import failed_write, unresolved_write_failure
    from career_evidence_graph.application_worker_browser import (
        _failed_write,
        _unresolved_write_failure,
    )

    assert _failed_write is failed_write
    assert _unresolved_write_failure is unresolved_write_failure
    assert not failed_write(
        {
            "kind": "upload",
            "stage": "requestfailed",
            "http_status": 204,
            "intent": {"action": "upload"},
        }
    )
    assert failed_write({"stage": "requestfailed", "intent": {"action": "fill"}})


def test_material_edit_guard_does_not_load_playwright_or_browser():
    script = """
import sys
from types import SimpleNamespace
from career_evidence_graph.application_material_edit import _edit_target
from career_evidence_graph.career_portal_data import PortalDataError
try:
    _edit_target(SimpleNamespace(preparation_only=True), None, None, 'unused')
except PortalDataError:
    pass
assert 'career_evidence_graph.application_worker_browser' not in sys.modules
assert 'playwright.sync_api' not in sys.modules
"""
    source = Path(__file__).resolve().parents[1] / "src"
    script = f"import sys; sys.path.insert(0, {str(source)!r})\n" + script
    subprocess.run([sys.executable, "-B", "-c", script], check=True)
