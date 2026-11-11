"""Preparation restart identity describes the loaded service without private roots."""

import json
import re
import shutil

import pytest
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_preparation_entry import snapshot

from career_evidence_graph import (
    application_draft,
    application_experience_latex,
    application_full_latex,
    application_group_review,
    application_job_source,
    application_preparation,
    career_portal,
)
from career_evidence_graph.application_flow import ApplicationFlowService


@pytest.mark.parametrize(
    ("module", "name"),
    [
        (application_full_latex, "generate_full_latex"),
        (application_group_review, "group_review_snapshot"),
        (application_experience_latex, "read_completed"),
    ],
)
@pytest.mark.parametrize("change", ["code", "defaults", "constant"])
def test_full_chain_loaded_identity_includes_code_defaults_and_constants(
    portal, tmp_path, monkeypatch, module, name, change
):
    options = {"flow_root": tmp_path / "preparation", "preparation_only": True}
    function = getattr(module, name)
    with _running_portal(portal.applications, portal.career, **options) as active:
        identity = snapshot(active)["runtime"]
        if change == "code":
            monkeypatch.setattr(
                function,
                "__code__",
                function.__code__.replace(
                    co_consts=(*function.__code__.co_consts, "Synthetic loaded revision")
                ),
            )
        elif change == "defaults":
            monkeypatch.setattr(function, "__defaults__", ("Synthetic loaded default",))
        else:
            monkeypatch.setattr(module, "ENGINE_SHA256", "Synthetic loaded constant")
        assert snapshot(active)["runtime"] == identity
    with _running_portal(portal.applications, portal.career, **options) as reopened:
        assert snapshot(reopened)["runtime"]["engine_revision"] != identity["engine_revision"]
        assert snapshot(reopened)["tasks"] == []


def test_preparation_runtime_identity_is_stable_until_a_new_service_starts(portal, tmp_path):
    options = {"flow_root": tmp_path / "preparation", "preparation_only": True}
    with _running_portal(portal.applications, portal.career, **options) as active:
        identity = snapshot(active)["runtime"]
        assert identity == snapshot(active)["runtime"]
        assert identity["mode"] == "preparation"
        for key in ("session_id", "engine_revision", "ui_revision"):
            assert re.fullmatch(r"[a-f0-9]{32,64}", identity[key])
        assert identity["version"] and identity["python_version"].startswith("3.")
        assert str(tmp_path) not in json.dumps(identity)
        assert active.server.worker_service is None
    with _running_portal(portal.applications, portal.career, **options) as reopened:
        next_identity = snapshot(reopened)["runtime"]
        assert next_identity["session_id"] != identity["session_id"]
        for key in ("engine_revision", "ui_revision", "version", "python_version", "mode"):
            assert next_identity[key] == identity[key]
        assert snapshot(reopened)["tasks"] == []
        assert reopened.server.worker_service is None


@pytest.mark.parametrize("target", ["method", "source_property"])
def test_runtime_revision_tracks_loaded_code_and_keeps_existing_service_identity(
    portal, tmp_path, monkeypatch, target
):
    options = {"flow_root": tmp_path / "preparation", "preparation_only": True}
    owner, key = (
        (ApplicationFlowService, "snapshot")
        if target == "method"
        else (application_job_source._Page, "text")
    )
    original = getattr(owner, key)
    if isinstance(original, property):
        original = original.fget
    with _running_portal(portal.applications, portal.career, **options) as active:
        identity = snapshot(active)["runtime"]

        def changed_snapshot(self, *args, **kwargs):
            return original(self, *args, **kwargs)

        monkeypatch.setattr(
            owner, key, changed_snapshot if target == "method" else property(changed_snapshot)
        )
        assert snapshot(active)["runtime"] == identity
    with _running_portal(portal.applications, portal.career, **options) as reopened:
        assert snapshot(reopened)["runtime"]["engine_revision"] != identity["engine_revision"]
        assert snapshot(reopened)["tasks"] == []


def test_runtime_revision_includes_loaded_function_defaults(portal, tmp_path, monkeypatch):
    options = {"flow_root": tmp_path / "preparation", "preparation_only": True}
    method = ApplicationFlowService.snapshot
    code = method.__code__
    with _running_portal(portal.applications, portal.career, **options) as active:
        identity = snapshot(active)["runtime"]
        monkeypatch.setattr(method, "__defaults__", ("synthetic-default",))
        assert method.__code__ is code
        assert snapshot(active)["runtime"] == identity
    with _running_portal(portal.applications, portal.career, **options) as reopened:
        assert snapshot(reopened)["runtime"]["engine_revision"] != identity["engine_revision"]
        assert snapshot(reopened)["tasks"] == []


def test_preparation_serves_startup_ui_bytes_until_restart(portal, tmp_path, monkeypatch):
    static = tmp_path / "synthetic-static"
    shutil.copytree(career_portal._STATIC, static)
    monkeypatch.setattr(career_portal, "_STATIC", static)
    options = {"flow_root": tmp_path / "preparation", "preparation_only": True}
    with _running_portal(portal.applications, portal.career, **options) as active:
        identity = snapshot(active)["runtime"]
        original = active.request("GET", "/static/application_flow.js")[2]
        (static / "application_flow.js").write_bytes(original + b"\n// Synthetic later UI\n")
        assert active.request("GET", "/static/application_flow.js")[2] == original
        assert snapshot(active)["runtime"] == identity
    with _running_portal(portal.applications, portal.career, **options) as reopened:
        next_identity = snapshot(reopened)["runtime"]
        assert next_identity["ui_revision"] != identity["ui_revision"]
        assert next_identity["engine_revision"] == identity["engine_revision"]
        assert reopened.request("GET", "/static/application_flow.js")[2] != original


@pytest.mark.parametrize(
    ("module", "key", "value"),
    [
        (application_preparation, "PREPARATION_POLICY_VERSION", "synthetic/v2"),
        (application_draft, "_LANGUAGES", {"synthetic": "synthetic-language"}),
        (application_draft, "_DATES", re.compile(r"synthetic-date", re.IGNORECASE)),
        (application_job_source, "MAX_RESPONSE_BYTES", 2_000_001),
    ],
)
def test_runtime_revision_includes_loaded_policy_constants(
    portal, tmp_path, monkeypatch, module, key, value
):
    options = {"flow_root": tmp_path / "preparation", "preparation_only": True}
    with _running_portal(portal.applications, portal.career, **options) as active:
        identity = snapshot(active)["runtime"]
        monkeypatch.setattr(module, key, value)
        assert snapshot(active)["runtime"] == identity
    with _running_portal(portal.applications, portal.career, **options) as reopened:
        assert snapshot(reopened)["runtime"]["engine_revision"] != identity["engine_revision"]
