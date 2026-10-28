"""Normal match refresh retains completed materials and never replays unknown calls."""

import errno
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from uuid import uuid4

import pytest
from test_application_information import tree_bytes
from test_application_match import model_output, model_runner
from test_career_portal_http import portal as portal
from test_match_recheck_preservation import original_fields
from test_match_recheck_preservation import retained_match as retained_match

from career_evidence_graph import application_match_refresh as refresh_module
from career_evidence_graph.application_explanations import adopted_analysis, job_explanation
from career_evidence_graph.application_information import information_context
from career_evidence_graph.application_match import (
    _analyze_loaded_job,
    match_configuration_revision,
)
from career_evidence_graph.application_match_refresh import (
    _binding,
    reconcile_failed_match_refresh,
    refresh_match,
)
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def setup_callback(retained_match, *, mutation=None):
    _, flow, job, task, sources, library, work = retained_match
    library.update({"status": "available", "records": []})
    reads, calls = [], []

    def source_provider(application_id, selected):
        reads.append((application_id, selected))
        return deepcopy(sources)

    flow.recheck_source_provider = source_provider

    def callback(application, requirements, directory):
        calls.append((application, requirements, directory))
        directory.mkdir()
        report = deepcopy(adopted_analysis(task))
        report.update(
            {
                "id": directory.name,
                "application_id": application["id"],
                "application_revision": application["revision"],
                "jd_revision": digest(
                    {
                        key: application.get(key, "")
                        for key in ("company", "role_title", "location", "job_description")
                    }
                ),
                "configuration_revision": match_configuration_revision(),
                "source_snapshot_revision": sources["revision"],
                "information_context_revision": information_context(application, library)[
                    "revision"
                ],
                "retrieval": {"selected_candidate_ids": ["discovered-candidate"]},
            }
        )
        report["requirements"][1]["judgment"] = "supported"
        report["requirements"][1]["explanation"] = "Normal pipeline read the selected evidence."
        (directory / "analysis.json").write_text(json.dumps(report))
        if mutation:
            mutation(flow, sources, library, application, report, directory)
        return report

    flow.callbacks["refresh_match"] = callback
    return flow, job, task, sources, library, work, reads, calls


def malformed_evaluator(retained_match):
    flow, job, task, sources, library, work, reads, calls = setup_callback(retained_match)

    def callback(application, requirements, directory):
        calls.append((application, requirements, directory))
        directory.mkdir()
        snapshot = deepcopy(sources)
        snapshot["match_requirements"] = requirements
        snapshot["revision"] = digest({k: v for k, v in snapshot.items() if k != "revision"})
        output = model_output(snapshot)
        output["requirements"] = [
            {**output["requirements"][0], **requirement} for requirement in requirements
        ]
        output["selection_rationale"][0]["source_id"] = "garbled-unrelated-source-id"
        return _analyze_loaded_job(
            application, snapshot, directory / "evaluation-1", runner=model_runner(output, [])
        )

    flow.callbacks["refresh_match"] = callback
    return flow, job, task, sources, library, work, reads, calls


def legacy_malformed_refresh(retained_match):
    result = malformed_evaluator(retained_match)
    flow, job, task, *_ = result
    identifier = uuid4().hex
    directory = flow.root / "match-refreshes" / identifier
    directory.mkdir(parents=True)
    binding, original, _ = _binding(flow, task, job)
    intent = {
        **binding,
        "id": identifier,
        "method": "normal_analysis",
        "task_revision": task["revision"],
    }
    (directory / "intent.json").write_text(json.dumps(intent))
    with pytest.raises(PortalDataError) as error:
        flow.callbacks["refresh_match"](
            job,
            [
                {key: row[key] for key in ("text", "importance", "hard_condition")}
                for row in original["requirements"]
            ],
            directory / "analysis",
        )
    assert error.value.code == "match_model_invalid"
    assert not (directory / "failure.json").exists()
    return result, identifier, directory


def test_refresh_preserves_materials_handoff_forms_history_and_other_tasks(retained_match):
    flow, job, task, _, _, work, reads, calls = setup_callback(retained_match)
    before = tree_bytes(flow.root)
    other_tasks = [flow.witness(row["id"])[1] for row in flow.snapshot()["tasks"][1:]]
    identifier = uuid4().hex
    result = refresh_match(flow, task["id"], task["revision"], identifier)
    assert original_fields(result) == original_fields(task)
    assert [flow.witness(row["id"])[1] for row in other_tasks] == other_tasks
    after = tree_bytes(flow.root)
    assert all(after[key] == value for key, value in before.items() if key != "flow.json")
    assert len(calls) == 1 and len(work["exports"]) == 1
    assert reads == [(job["id"], ["discovered-candidate"])]
    receipt = result["match_rechecks"][0]
    assert receipt["method"] == "normal_analysis"
    intent = json.loads((flow.root / "match-refreshes" / identifier / "intent.json").read_text())
    assert intent["configuration_revision"] == receipt["configuration_revision"]
    assert receipt["configuration_revision"] == match_configuration_revision()
    assert receipt["result"]["requirements"][1]["judgment"] == "supported"


def test_replay_does_not_call_model_or_duplicate_history(retained_match):
    flow, _, task, _, _, _, _, calls = setup_callback(retained_match)
    identifier = uuid4().hex
    first = refresh_match(flow, task["id"], task["revision"], identifier)
    before = tree_bytes(flow.root)
    second = refresh_match(flow, task["id"], task["revision"], identifier)
    assert second == first and len(calls) == 1
    assert tree_bytes(flow.root) == before


def test_refresh_uses_current_sources_without_rebinding_uploaded_materials(retained_match):
    flow, job, task, sources, library, _, _, calls = setup_callback(retained_match)
    current_inputs = {
        **task["inputs"],
        "sources_revision": "updated-structured-facts",
        "analysis_configuration_revision": "updated-analysis-engine",
    }
    flow.input_provider = lambda application_id: {
        "application_revision": job["revision"],
        "inputs": current_inputs,
    }
    result = refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert len(calls) == 1
    assert original_fields(result) == original_fields(task)
    explanation = job_explanation(
        job,
        result,
        current_inputs=current_inputs,
        library=library,
        source_provider=lambda application_id, selected: deepcopy(sources),
    )
    assert explanation["fresh"] is True
    assert explanation["materials_fresh"] is False
    assert explanation["match_recheck_stale"] is False
    assert "historical_status" not in explanation["qualification"]
    assert explanation["reasons"][1]["judgment"] == "supported"


def test_verified_refresh_explanation_is_independent_of_old_material_inputs(retained_match):
    flow, job, task, sources, library, _, _, _ = setup_callback(retained_match)
    result = refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    explanation = job_explanation(
        job,
        result,
        current_inputs={**task["inputs"], "sources_revision": "current-facts"},
        library=library,
        source_provider=lambda application_id, selected: deepcopy(sources),
    )
    assert explanation["fresh"] is True
    assert explanation["materials_fresh"] is False
    assert "historical_status" not in explanation["qualification"]


def test_refresh_refuses_changed_jd_before_model_dispatch(retained_match):
    flow, job, task, _, _, _, _, calls = setup_callback(retained_match)
    flow.applications.update_application(
        job["id"], {"job_description": "A different job requirement."}, job["revision"]
    )
    before = tree_bytes(flow.root)
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert calls == []
    assert tree_bytes(flow.root) == before


def reading_budget_failure(
    retained_match, monkeypatch, *, argv_failure=False, terminal_output=False
):
    from test_application_material_packet import many_small_sources
    from test_material_packet_native_response import native_reader

    from career_evidence_graph import application_material_packet as material
    from career_evidence_graph.application_match import match_configuration

    flow, job, task, sources, library, work, reads, calls = setup_callback(retained_match)
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "100")
    snapshot = many_small_sources()
    snapshot["revision"] = digest({k: v for k, v in snapshot.items() if k != "revision"})
    native_calls = []
    read = native_reader(native_calls)
    if argv_failure:

        def read(*args, **kwargs):
            native_calls.append("OS launch attempt")
            configuration = match_configuration()
            raise OSError(
                errno.E2BIG,
                "Argument list too long",
                configuration.get("resolved_executable") or configuration["executable"],
            )

    if terminal_output:

        def read(*args, **kwargs):
            from career_evidence_graph.codex_cli import CodexCLIError

            native_calls.append("completed failed turn")
            message = "Incomplete response returned, reason: max_output_tokens"
            events = [
                {"type": "thread.started", "thread_id": "synthetic-thread"},
                {"type": "turn.started"},
                {"type": "error", "message": message},
                {"type": "turn.failed", "error": {"message": message}},
            ]
            raise CodexCLIError(
                "Codex exec failed with exit code 1: ",
                raw_stdout_jsonl="\n".join(json.dumps(event) for event in events) + "\n",
                redacted_stderr="",
            )

    def fail_reading(application, requirements, directory):
        directory.mkdir()
        progress = {
            "schema_version": "application-analysis-progress/v1",
            "phase": "reading",
            "binding": {
                "application_id": application["id"],
                "job": {
                    key: application.get(key, "")
                    for key in ("company", "role_title", "location", "job_description")
                },
                "configuration": match_configuration(),
            },
            "round_number": 1,
            "reading_origin": str(directory / "material-packet-1"),
            "evaluation": snapshot,
            "stable": requirements,
            "evaluations": [],
        }
        progress["revision"] = digest(progress)
        (directory / "analysis-progress.json").write_text(json.dumps(progress))
        return material.prepare_material_packet(
            application,
            snapshot,
            directory / "material-packet-1",
            runner=read,
            requirements=requirements,
        )

    callback = flow.callbacks["refresh_match"]
    flow.callbacks["refresh_match"] = fail_reading
    identifier = uuid4().hex
    with pytest.raises(PortalDataError) as error:
        refresh_match(flow, task["id"], task["revision"], identifier)
    assert error.value.code == "retrieval_execution_incomplete"
    assert native_calls
    flow.callbacks["refresh_match"] = callback
    return flow, job, task, snapshot, identifier, native_calls


def test_known_reading_budget_failure_can_resume_with_verified_native_reads(
    retained_match, monkeypatch
):
    from test_material_packet_native_response import native_reader

    from career_evidence_graph import application_material_packet as material

    flow, job, task, snapshot, identifier, native_calls = reading_budget_failure(
        retained_match, monkeypatch
    )
    directory = flow.root / "match-refreshes" / identifier
    before = tree_bytes(directory)
    outcome = reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
    assert outcome["error_code"] == "retrieval_execution_incomplete"
    assert outcome["proof"]["method"] == "reconciled_reading_budget"
    assert outcome["completed_calls"] == len(native_calls)
    assert all(tree_bytes(directory)[path] == value for path, value in before.items())
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "60000")
    callback = flow.callbacks["refresh_match"]
    resumed_calls, origins = [], []

    def resume(application, requirements, destination, *, resume_from):
        origins.append(resume_from)
        _, packet = material.prepare_material_packet(
            application,
            snapshot,
            destination.parent / "resumed-reading",
            runner=native_reader(resumed_calls),
            requirements=requirements,
            resume_from=resume_from / "material-packet-1",
        )
        assert packet["status"] == "complete"
        return callback(application, requirements, destination)

    flow.callbacks["refresh_match"] = resume
    next_identifier = uuid4().hex
    result = flow.request(
        "refresh-match",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "request_id": next_identifier,
            "resume_request_id": identifier,
        },
    )
    assert resumed_calls == []
    assert origins == [directory / "analysis"]
    assert original_fields(result) == original_fields(task)
    intent = json.loads(
        (flow.root / "match-refreshes" / next_identifier / "intent.json").read_text()
    )
    assert intent["resume_request_id"] == identifier
    assert intent["resume_failure_revision"] == outcome["revision"]


@pytest.mark.parametrize("tamper", ["pending", "unreceipted", "raw", "budget", "progress"])
def test_reading_budget_reconciliation_cannot_clear_unknown_or_unproved_calls(
    retained_match, monkeypatch, tamper
):
    flow, _, task, _, identifier, _ = reading_budget_failure(retained_match, monkeypatch)
    directory = flow.root / "match-refreshes" / identifier
    packet_path = directory / "analysis/material-packet-1/material-packet.json"
    packet = json.loads(packet_path.read_text())
    if tamper == "raw":
        result_path = next((directory / "analysis/material-packet-1").glob("source-*/result.json"))
        value = json.loads(result_path.read_text())
        value["raw_stdout_jsonl"] = "{}"
        result_path.write_text(json.dumps(value))
    elif tamper == "progress":
        path = directory / "analysis/analysis-progress.json"
        value = json.loads(path.read_text())
        value["phase"] = "evaluation"
        value["revision"] = digest({k: v for k, v in value.items() if k != "revision"})
        path.write_text(json.dumps(value))
    else:
        if tamper == "pending":
            packet["pending_call"] = {"directory": "unknown"}
        elif tamper == "unreceipted":
            next(row for row in packet["source_reads"].values() if row["ranges"])["ranges"] = []
        else:
            packet["context_limits"]["material_context_bytes"] = 60000
        packet["revision"] = digest({k: v for k, v in packet.items() if k != "revision"})
        packet_path.write_text(json.dumps(packet))
    before = tree_bytes(directory)
    with pytest.raises(PortalDataError):
        reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
    assert tree_bytes(directory) == before
    assert not (directory / "failure.json").exists()


def test_proved_oversized_argv_failure_is_undispatched_and_can_resume(retained_match, monkeypatch):
    import os

    real_sysconf = os.sysconf
    monkeypatch.setattr(
        os, "sysconf", lambda name: 1024 if name == "SC_ARG_MAX" else real_sysconf(name)
    )
    flow, _, task, _, identifier, _ = reading_budget_failure(
        retained_match, monkeypatch, argv_failure=True
    )
    origin = flow.root / "match-refreshes" / identifier / "analysis/material-packet-1"
    prompt_path = next(origin.glob("source-*/prompt.json"))
    prompt_bytes = len(json.loads(prompt_path.read_text())["prompt"].encode())
    monkeypatch.setattr(
        os,
        "sysconf",
        lambda name: prompt_bytes + 99 if name == "SC_ARG_MAX" else real_sysconf(name),
    )
    outcome = reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
    assert outcome["proof"]["method"] == "reconciled_reading_argv_capacity"
    assert outcome["completed_calls"] == 0
    assert outcome["proof"]["undispatched_prompt"].endswith("/prompt.json")
    assert outcome["proof"]["prompt_bytes"] < outcome["proof"]["argv_limit"]
    assert outcome["proof"]["minimum_argv_bytes"] > outcome["proof"]["argv_limit"]
    callback = flow.callbacks["refresh_match"]
    flow.callbacks["refresh_match"] = lambda application, requirements, directory, **options: (
        callback(application, requirements, directory)
    )
    result = refresh_match(
        flow, task["id"], task["revision"], uuid4().hex, resume_request_id=identifier
    )
    assert original_fields(result) == original_fields(task)


@pytest.mark.parametrize(
    "tamper", ["short", "output", "missing_result", "other_unknown", "error", "receipted"]
)
def test_argv_capacity_reconciliation_cannot_clear_unproved_or_other_unknown_calls(
    retained_match, monkeypatch, tamper
):
    import os
    import shutil

    real_sysconf = os.sysconf
    monkeypatch.setattr(
        os,
        "sysconf",
        lambda name: (
            (2_000_000 if tamper == "short" else 1024)
            if name == "SC_ARG_MAX"
            else real_sysconf(name)
        ),
    )
    flow, _, task, _, identifier, _ = reading_budget_failure(
        retained_match, monkeypatch, argv_failure=True
    )
    directory = flow.root / "match-refreshes" / identifier
    origin = directory / "analysis/material-packet-1"
    page = next(origin.glob("source-*"))
    if tamper == "output":
        path = page / "result.json"
        value = json.loads(path.read_text())
        value["raw_stdout_jsonl"] = "possibly dispatched"
        path.write_text(json.dumps(value))
    elif tamper == "missing_result":
        (page / "result.json").unlink()
    elif tamper == "other_unknown":
        other = origin / "source-9999-page-0001"
        other.mkdir()
        for name in ("context.json", "prompt.json", "schema.json"):
            shutil.copyfile(page / name, other / name)
    elif tamper == "error":
        path = origin / "material-packet.json"
        value = json.loads(path.read_text())
        value["failure"]["message"] = "A network connection failed."
        value["revision"] = digest({k: v for k, v in value.items() if k != "revision"})
        path.write_text(json.dumps(value))
    elif tamper == "receipted":
        path = origin / "material-packet.json"
        value = json.loads(path.read_text())
        context = json.loads((page / "context.json").read_text())
        row = context.get("source_ranges", [context])[0]
        value["source_reads"][row["source"]["source_id"]]["ranges"].append(row["range"])
        value["revision"] = digest({k: v for k, v in value.items() if k != "revision"})
        path.write_text(json.dumps(value))
    before = tree_bytes(directory)
    with pytest.raises(PortalDataError):
        reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
    assert tree_bytes(directory) == before
    assert not (directory / "failure.json").exists()


def test_unknown_refresh_cannot_be_resumed_by_a_new_request(retained_match):
    flow, _, task, _, _, _, _, calls = setup_callback(retained_match)

    def interrupted(*args):
        calls.append(args)
        raise OSError("unknown model outcome")

    flow.callbacks["refresh_match"] = interrupted
    identifier = uuid4().hex
    with pytest.raises(OSError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    before = tree_bytes(flow.root)
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], uuid4().hex, resume_request_id=identifier)
    assert len(calls) == 1
    assert tree_bytes(flow.root) == before


def test_large_operational_progress_and_packet_input_use_the_operational_budget(tmp_path):
    directory = tmp_path / "refresh"
    directory.mkdir()
    payload = {"saved_facts": "a" * (2 * 1024 * 1024 + 1)}
    for name in ("analysis-progress.json", "input.json"):
        path = directory / name
        path.write_text(json.dumps(payload))
        assert refresh_module._read(path) == payload
    assert len(refresh_module._artifact_hashes(directory)) == 2


def test_operational_reader_rejects_redirects_and_total_artifact_overflow(tmp_path, monkeypatch):
    directory = tmp_path / "refresh"
    directory.mkdir()
    original = directory / "original.json"
    original.write_text('{"value": "saved"}')
    linked = directory / "linked.json"
    linked.symlink_to(original)
    with pytest.raises(PortalDataError):
        refresh_module._read(linked)
    linked.unlink()
    (directory / "second.json").write_bytes(original.read_bytes())
    monkeypatch.setattr(refresh_module, "_MAX_ARTIFACT_BYTES", original.stat().st_size + 1)
    with pytest.raises(PortalDataError):
        refresh_module._artifact_hashes(directory)


def test_terminal_native_output_limit_is_known_failed_and_can_resume(retained_match, monkeypatch):
    flow, _, task, _, identifier, _ = reading_budget_failure(
        retained_match, monkeypatch, terminal_output=True
    )
    outcome = reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
    assert outcome["proof"]["method"] == "reconciled_reading_output_limit"
    assert outcome["proof"]["terminal_failed_calls"] == 1
    assert "undispatched_prompt" not in outcome["proof"]
    callback = flow.callbacks["refresh_match"]
    flow.callbacks["refresh_match"] = lambda application, requirements, directory, **options: (
        callback(application, requirements, directory)
    )
    result = refresh_match(
        flow, task["id"], task["revision"], uuid4().hex, resume_request_id=identifier
    )
    assert original_fields(result) == original_fields(task)


@pytest.mark.parametrize(
    "tamper", ["assistant", "missing_terminal", "message", "stderr", "timeout"]
)
def test_output_limit_reconciliation_refuses_incomplete_or_different_native_failures(
    retained_match, monkeypatch, tamper
):
    flow, _, task, _, identifier, _ = reading_budget_failure(
        retained_match, monkeypatch, terminal_output=True
    )
    directory = flow.root / "match-refreshes" / identifier
    origin = directory / "analysis/material-packet-1"
    path = next(origin.glob("source-*/result.json"))
    value = json.loads(path.read_text())
    events = [json.loads(line) for line in value["raw_stdout_jsonl"].splitlines()]
    if tamper == "assistant":
        events.insert(2, {"type": "item.completed", "item": {"type": "agent_message", "text": "x"}})
    elif tamper == "missing_terminal":
        events.pop()
    elif tamper == "message":
        events[-1]["error"]["message"] = "A different error"
    elif tamper == "stderr":
        value["redacted_stderr"] = "Unrecognized failure"
    else:
        packet_path = origin / "material-packet.json"
        packet = json.loads(packet_path.read_text())
        packet["failure"]["message"] = "Codex CLI timed out"
        packet["revision"] = digest({k: v for k, v in packet.items() if k != "revision"})
        packet_path.write_text(json.dumps(packet))
    value["raw_stdout_jsonl"] = "\n".join(json.dumps(event) for event in events) + "\n"
    path.write_text(json.dumps(value))
    before = tree_bytes(directory)
    with pytest.raises(PortalDataError):
        reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
    assert tree_bytes(directory) == before
    assert not (directory / "failure.json").exists()


@pytest.mark.parametrize("kind", ["sources", "information", "configuration", "job"])
def test_refresh_explanation_becomes_stale_when_its_own_inputs_change(
    retained_match, monkeypatch, kind
):
    flow, job, task, sources, library, _, _, _ = setup_callback(retained_match)
    result = refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    if kind == "sources":
        sources["coverage"]["changed"] = True
        sources["revision"] = digest({k: v for k, v in sources.items() if k != "revision"})
    elif kind == "information":
        library["status"] = "unavailable"
    elif kind == "configuration":
        monkeypatch.setattr(
            "career_evidence_graph.application_match.match_configuration_revision",
            lambda: "changed-engine",
        )
    else:
        job = {**job, "job_description": "Changed job"}
    explanation = job_explanation(
        job,
        result,
        current_inputs=task["inputs"],
        library=library,
        source_provider=lambda application_id, selected: deepcopy(sources),
    )
    assert explanation["fresh"] is False
    assert explanation["match_recheck_stale"] is True


def test_unknown_call_is_not_replayed(retained_match):
    flow, _, task, _, _, _, _, calls = setup_callback(retained_match)

    def interrupted(*args):
        calls.append(args)
        raise OSError("model connection interrupted")

    flow.callbacks["refresh_match"] = interrupted
    identifier = uuid4().hex
    with pytest.raises(OSError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    with pytest.raises(PortalDataError) as error:
        refresh_match(flow, task["id"], task["revision"], identifier)
    assert error.value.code == "match_refresh_unknown"
    assert len(calls) == 1


def test_unknown_call_cannot_be_replayed_with_a_fresh_request_id(retained_match):
    flow, _, task, _, _, _, _, calls = setup_callback(retained_match)

    def interrupted(*args):
        calls.append(args)
        raise OSError("model connection interrupted")

    flow.callbacks["refresh_match"] = interrupted
    with pytest.raises(OSError):
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    before = tree_bytes(flow.root)
    with pytest.raises(PortalDataError) as error:
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert error.value.code == "match_refresh_unknown"
    assert len(calls) == 1 and tree_bytes(flow.root) == before


def test_concurrent_fresh_request_does_not_start_another_model_call(retained_match):
    flow, _, task, _, _, _, _, calls = setup_callback(retained_match)
    callback = flow.callbacks["refresh_match"]
    started, release = Event(), Event()
    invocations = []

    def blocked(*args):
        invocations.append(args)
        started.set()
        assert release.wait(5)
        return callback(*args)

    flow.callbacks["refresh_match"] = blocked
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(refresh_match, flow, task["id"], task["revision"], uuid4().hex)
        try:
            assert started.wait(5)
            with pytest.raises(PortalDataError) as error:
                refresh_match(flow, task["id"], task["revision"], uuid4().hex)
            assert error.value.code == "match_refresh_unknown"
        finally:
            release.set()
        result = pending.result(timeout=5)
    assert len(invocations) == len(calls) == len(result["match_rechecks"]) == 1


def test_saved_report_can_be_reconciled_without_another_model_call(retained_match):
    def interruption(_flow, _sources, _library, _application, _report, _directory):
        raise OSError("interrupted after saving complete analysis")

    flow, _, task, _, _, _, _, calls = setup_callback(retained_match, mutation=interruption)
    identifier = uuid4().hex
    with pytest.raises(OSError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    result = refresh_match(flow, task["id"], task["revision"], identifier)
    assert len(result["match_rechecks"]) == 1 and len(calls) == 1


def test_saved_unadopted_report_must_be_reconciled_before_a_new_request(retained_match):
    def interruption(_flow, _sources, _library, _application, _report, _directory):
        raise OSError("interrupted after saving complete analysis")

    flow, _, task, _, _, _, _, calls = setup_callback(retained_match, mutation=interruption)
    identifier = uuid4().hex
    with pytest.raises(OSError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    with pytest.raises(PortalDataError) as error:
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert error.value.code == "match_refresh_unknown"
    result = refresh_match(flow, task["id"], task["revision"], identifier)
    assert len(result["match_rechecks"]) == len(calls) == 1


def test_completed_refresh_allows_a_new_refresh_and_keeps_both_receipts(retained_match):
    flow, _, task, _, _, _, _, calls = setup_callback(retained_match)
    first = refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    second = refresh_match(flow, task["id"], first["revision"], uuid4().hex)
    assert len(second["match_rechecks"]) == len(calls) == 2
    assert second["match_rechecks"][0] == first["match_rechecks"][0]


def test_wrong_engine_configuration_cannot_be_adopted(retained_match):
    def mutation(_flow, _sources, _library, _application, report, directory):
        report["configuration_revision"] = "stale-engine"
        (directory / "analysis.json").write_text(json.dumps(report))

    flow, _, task, _, _, _, _, calls = setup_callback(retained_match, mutation=mutation)
    before = (flow.root / "flow.json").read_bytes()
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert (flow.root / "flow.json").read_bytes() == before and len(calls) == 1


def test_engine_change_during_call_refuses_adoption(retained_match, monkeypatch):
    def mutation(*_args):
        monkeypatch.setattr(
            refresh_module, "match_configuration_revision", lambda: "changed-engine"
        )

    flow, _, task, _, _, _, _, calls = setup_callback(retained_match, mutation=mutation)
    before = (flow.root / "flow.json").read_bytes()
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert (flow.root / "flow.json").read_bytes() == before and len(calls) == 1


def test_old_engine_completed_report_is_not_reconciled_after_an_upgrade(
    retained_match, monkeypatch
):
    def interruption(*_args):
        raise OSError("interrupted after saving complete analysis")

    flow, _, task, _, _, _, _, calls = setup_callback(retained_match, mutation=interruption)
    identifier = uuid4().hex
    with pytest.raises(OSError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    before = tree_bytes(flow.root)
    monkeypatch.setattr(refresh_module, "match_configuration_revision", lambda: "changed-engine")
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    assert len(calls) == 1 and tree_bytes(flow.root) == before


@pytest.mark.parametrize("kind", ["sources", "facts", "job", "requirements"])
def test_changed_sources_facts_job_or_requirements_refuse_adoption(retained_match, kind):
    def mutation(flow, sources, library, application, report, directory):
        if kind == "sources":
            sources["coverage"]["changed"] = True
            sources["revision"] = digest({k: v for k, v in sources.items() if k != "revision"})
        elif kind == "facts":
            library["status"] = "unavailable"
        elif kind == "job":
            flow.applications.update_application(
                application["id"], {"job_description": "Changed job"}, application["revision"]
            )
        else:
            report["requirements"][0]["text"] = "Changed requirement"
            (directory / "analysis.json").write_text(json.dumps(report))

    flow, _, task, _, _, _, _, calls = setup_callback(retained_match, mutation=mutation)
    before = (flow.root / "flow.json").read_bytes()
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert (flow.root / "flow.json").read_bytes() == before and len(calls) == 1


def test_saved_report_drift_rejects_existing_receipt(retained_match):
    flow, _, task, _, _, _, _, calls = setup_callback(retained_match)
    identifier = uuid4().hex
    refresh_match(flow, task["id"], task["revision"], identifier)
    path = flow.root / "match-refreshes" / identifier / "analysis" / "analysis.json"
    report = json.loads(path.read_text())
    report["requirements"][1]["explanation"] = "Altered after adoption"
    path.write_text(json.dumps(report))
    before = (flow.root / "flow.json").read_bytes()
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    assert (flow.root / "flow.json").read_bytes() == before and len(calls) == 1


def test_existing_gap_is_retained_in_new_match_result(retained_match):
    flow, _, task, _, _, _, _, _ = setup_callback(retained_match)
    with flow.applications.write_lock():
        state = flow._load()
        row = flow._task(state, task["id"])
        old = adopted_analysis(row)
        old["requirements"][1]["judgment"] = "gap"
        old["requirements"][1]["explanation"] = "Confirmed negative answer."
        flow._save(state)
        task.clear()
        task.update(deepcopy(row))
    result = refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert result["match_rechecks"][0]["result"]["requirements"][1]["judgment"] == "gap"


def test_completed_parser_failure_is_recorded_and_does_not_block_a_fresh_request(retained_match):
    flow, _, task, _, _, _, _, calls = malformed_evaluator(retained_match)
    identifier = uuid4().hex
    before = (flow.root / "flow.json").read_bytes()
    with pytest.raises(PortalDataError) as error:
        refresh_match(flow, task["id"], task["revision"], identifier)
    assert error.value.code == "match_model_invalid"
    directory = flow.root / "match-refreshes" / identifier
    outcome = json.loads((directory / "failure.json").read_text())
    assert outcome["status"] == "known_failed" and outcome["completed_calls"] == 1
    assert outcome["proof"]["method"] == "caught_validation_error"
    assert (flow.root / "flow.json").read_bytes() == before
    assert len(calls) == 1
    _, _, _, _, _, _, _, fresh_calls = setup_callback(retained_match)
    result = refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert len(fresh_calls) == len(result["match_rechecks"]) == 1
    assert (directory / "intent.json").exists()


@pytest.mark.parametrize(
    "code", ["match_model_timeout", "match_model_unavailable", "retrieval_model_failed"]
)
def test_transport_failures_stay_unknown_and_cannot_be_cleared(retained_match, code):
    flow, _, task, _, _, _, _, calls = setup_callback(retained_match)

    def callback(*args):
        calls.append(args)
        raise PortalDataError(code, "Synthetic transport failure", 503)

    flow.callbacks["refresh_match"] = callback
    identifier = uuid4().hex
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    directory = flow.root / "match-refreshes" / identifier
    assert not (directory / "failure.json").exists()
    with pytest.raises(PortalDataError):
        reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
    with pytest.raises(PortalDataError) as error:
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert error.value.code == "match_refresh_unknown" and len(calls) == 1


def test_legacy_failure_is_reconciled_without_replay_and_preserves_all_saved_artifacts(
    retained_match, monkeypatch
):
    result, identifier, directory = legacy_malformed_refresh(retained_match)
    flow, _, task, _, _, _, _, calls = result
    before = tree_bytes(flow.root)
    monkeypatch.setattr(refresh_module, "match_configuration_revision", lambda: "upgraded-engine")
    outcome = reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
    assert outcome["proof"]["method"] == "reconciled_selection_contract"
    assert outcome["status"] == "known_failed"
    after = tree_bytes(flow.root)
    assert all(after[path] == data for path, data in before.items())
    assert len(after) == len(before) + 1 and len(calls) == 1
    assert reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier) == outcome
    assert (directory / "analysis/evaluation-1/model-result.json").exists()


@pytest.mark.parametrize(
    "kind", ["exit", "prompt", "schema", "input", "raw_result", "no_mismatch", "missing_result"]
)
def test_legacy_reconciliation_rejects_incomplete_or_unproven_failure(retained_match, kind):
    result, identifier, directory = legacy_malformed_refresh(retained_match)
    flow, _, task, *_ = result
    evaluation = directory / "analysis/evaluation-1"
    if kind == "missing_result":
        (evaluation / "model-result.json").unlink()
    else:
        name = {
            "prompt": "context-input.json",
            "schema": "match-schema.json",
            "input": "input.json",
        }.get(kind, "model-result.json")
        path = evaluation / name
        data = json.loads(path.read_text())
        if kind == "exit":
            data["exit_code"] = 1
        elif kind == "prompt":
            data["prompt"] += "changed"
        elif kind == "schema":
            data["description"] = "changed"
        elif kind == "input":
            data["configuration"] = {"changed": True}
        elif kind == "raw_result":
            data["structured_result"]["limitations"].append("changed")
        else:
            output = data["structured_result"]
            output["selection_rationale"][0]["source_id"] = output["selected_source_ids"][0]
            data["raw_stdout_jsonl"] = json.dumps({"type": "structured_result", "result": output})
        path.write_text(json.dumps(data))
    before = tree_bytes(flow.root)
    with pytest.raises(PortalDataError):
        reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
    assert tree_bytes(flow.root) == before and not (directory / "failure.json").exists()


def test_failed_outcome_cannot_hide_later_original_artifact_changes(retained_match):
    flow, _, task, *_ = malformed_evaluator(retained_match)
    identifier = uuid4().hex
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    path = flow.root / "match-refreshes" / identifier / "analysis/evaluation-1/model-result.json"
    path.write_text(path.read_text() + " ")
    before = tree_bytes(flow.root)
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert tree_bytes(flow.root) == before


def test_parser_error_cannot_clear_an_unproven_nonzero_model_call(retained_match):
    flow, _, task, *_ = malformed_evaluator(retained_match)
    callback = flow.callbacks["refresh_match"]

    def unproven(application, requirements, directory):
        try:
            return callback(application, requirements, directory)
        except PortalDataError:
            path = directory / "evaluation-1/model-result.json"
            result = json.loads(path.read_text())
            result["exit_code"] = 1
            path.write_text(json.dumps(result))
            raise

    flow.callbacks["refresh_match"] = unproven
    identifier = uuid4().hex
    with pytest.raises(PortalDataError):
        refresh_match(flow, task["id"], task["revision"], identifier)
    assert not (flow.root / "match-refreshes" / identifier / "failure.json").exists()
    with pytest.raises(PortalDataError) as error:
        refresh_match(flow, task["id"], task["revision"], uuid4().hex)
    assert error.value.code == "match_refresh_unknown"


def test_reconciliation_cannot_clear_a_callback_still_executing(retained_match):
    flow, _, task, *_ = malformed_evaluator(retained_match)
    callback = flow.callbacks["refresh_match"]
    started, release = Event(), Event()

    def blocked(*args):
        try:
            return callback(*args)
        except PortalDataError:
            started.set()
            assert release.wait(5)
            raise

    flow.callbacks["refresh_match"] = blocked
    identifier = uuid4().hex
    directory = flow.root / "match-refreshes" / identifier
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(refresh_match, flow, task["id"], task["revision"], identifier)
        try:
            assert started.wait(5)
            with pytest.raises(PortalDataError):
                reconcile_failed_match_refresh(flow, task["id"], task["revision"], identifier)
            assert not (directory / "failure.json").exists()
        finally:
            release.set()
        with pytest.raises(PortalDataError) as error:
            pending.result(timeout=5)
        assert error.value.code == "match_model_invalid"
    assert (directory / "failure.json").exists()
