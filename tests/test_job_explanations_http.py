"""Real loopback routes use synthetic inputs and the existing information library."""

import json
from pathlib import Path

import pytest
from test_application_flow import wait_for
from test_application_information import answer, tree_bytes, write_library
from test_career_portal_http import portal as portal
from test_job_explanation_browser import explanation_portal
from test_preparation_entry import post, snapshot

from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore


@pytest.fixture(autouse=True)
def isolated_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_information_change_rechecks_qualification_without_rewriting_match(portal, tmp_path):
    applications = ApplicationStore(portal.applications)
    job = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Python and German B2 required.",
        }
    )
    key, fact = answer("German level", "C1")
    library = tmp_path / "information"
    write_library(library, answers={key: fact}, profile={"phone": "+000 synthetic"})
    before = tree_bytes(library)
    hard = {
        "text": "German B2 required",
        "importance": "required",
        "judgment": "unknown",
        "hard_condition": True,
        "explanation": "Language is not evidenced by the career source.",
        "source_ids": [],
        "citations": [],
        "claim_scope": "unknown",
    }
    with explanation_portal(
        portal, tmp_path, extra_requirements={"Synthetic": [hard]}, information_library_root=library
    ) as (active, work):
        _, task = post(
            active, "create", {"application_id": job["id"], "application_revision": job["revision"]}
        )
        assert (
            post(
                active,
                "start",
                {"task_id": task["id"], "task_revision": task["revision"], "stage": "analysis"},
            )[0]
            == 200
        )
        task = wait_for(
            active.server.application_flow_service,
            task["id"],
            lambda row: row["status"] == "analysis_ready",
        )
        original = snapshot(active)["active_explanation"]
        original_calls = list(work["calls"])
        assert (
            original["score"]["lower"] == 50 and original["qualification"]["status"] == "supported"
        )
        assert original["policy_version"] == "preparation-policy/v1.0"
        assert tree_bytes(library) == before
        assert "+000 synthetic" not in json.dumps(snapshot(active))
        assert active.server.worker_service is None
        fact["value"] = "A2"
        (library / "answers.json").write_text(
            json.dumps({"schemaVersion": 1, "answers": {key: fact}, "metadata": {}})
        )
        current = snapshot(active)["active_explanation"]
        assert current["fresh"] is True and current["qualification"]["status"] == "conflict"
        assert current["input_binding"] == original["input_binding"]
        assert current["score"] == original["score"] and current["reasons"] == original["reasons"]
        assert (
            post(
                active,
                "start",
                {"task_id": task["id"], "task_revision": task["revision"], "stage": "resume"},
            )[1]["error"]
            == "flow_qualification_required"
        )
        assert work["calls"] == original_calls and work["exports"] == []


def test_reorder_requires_auth_current_revision_and_server_owned_fields(portal, tmp_path):
    applications = ApplicationStore(portal.applications)
    jobs = [
        applications.create_application(
            {"company": name, "role_title": "Engineer", "job_description": "Build Python services."}
        )
        for name in ("One", "Two")
    ]
    with explanation_portal(portal, tmp_path) as (active, work):
        state = snapshot(active)
        payload = {
            "application_id": jobs[1]["id"],
            "direction": "up",
            "order_revision": state["order_revision"],
        }
        assert (
            active.request("POST", "/api/flow/reorder", body=json.dumps(payload).encode())[0] == 403
        )
        assert post(active, "reorder", payload | {"score": 100})[0] == 400
        assert post(active, "reorder", payload | {"order_revision": "old"})[0] == 409
        assert post(active, "reorder", payload | {"direction": "sideways"})[0] == 400
        assert post(active, "reorder", payload)[0] == 200
        current = snapshot(active)
        assert current["explanations"][0]["application_id"] == jobs[1]["id"]
        assert current["tasks"] == [] and work["calls"] == [] and work["exports"] == []


def test_information_library_must_remain_outside_the_system_repository(portal, tmp_path):
    root = tmp_path / "flow"
    with pytest.raises(ValueError, match="outside"):
        create_server(
            portal.applications,
            portal.career,
            flow_root=root,
            preparation_only=True,
            information_library_root=Path(__file__).resolve().parents[1] / "personal-information",
        )
    assert not root.exists()
