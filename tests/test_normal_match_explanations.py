"""Normal match refreshes use current selected captures and shared confirmed facts."""

from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_information import answer, library_with
from test_job_explanations import job_and_task, requirement

from career_evidence_graph.application_explanations import job_explanation
from career_evidence_graph.application_flow import analysis_input_binding, job_input_revision
from career_evidence_graph.application_information import (
    information_context,
    information_source_snapshot,
)
from career_evidence_graph.application_match import match_configuration_revision
from career_evidence_graph.application_match_recheck import current_match_recheck
from career_evidence_graph.application_worker import digest


def case():
    app, task = job_and_task(
        [requirement("Professional English communication", judgment="unknown", hard=True)]
    )
    lib = library_with(answer("English fluency", "professional"))
    lib["career_library"] = {"status": "available", "revision": "catalog-current"}
    base = {"schemaVersion": 1, "documents": [], "items": []}
    base["revision"] = digest(base)
    source = information_source_snapshot(app, lib, base)["items"][0]
    old = task["artifacts"][0]["result"]
    report = {
        **deepcopy(old),
        "id": "normal-report",
        "jd_revision": job_input_revision(app),
        "configuration_revision": match_configuration_revision(),
        "retrieval": {"selected_candidate_ids": []},
        "source_snapshot_revision": base["revision"],
        "information_context_revision": information_context(app, lib)["revision"],
    }
    report["requirements"][0].update(
        judgment="supported",
        sources=[source],
        information_support={
            "fact": "confirmed_information",
            "status": "supported",
            "references": source["confirmed_information"]["references"],
            "explanation": "Confirmed professional English.",
        },
    )
    receipt = {
        "id": "normal-refresh",
        "method": "normal_analysis",
        "base_analysis_id": task["analysis_id"],
        "base_analysis_revision": digest(old),
        "job_binding": task["job_binding"],
        "library_revision": "catalog-current",
        "source_snapshot_revision": base["revision"],
        "information_context_revision": report["information_context_revision"],
        "reviewed_at": "2026-10-23",
        "result": report,
    }
    task["match_rechecks"] = [receipt]
    return app, task, lib, base


def explain(app, task, lib, base):
    return job_explanation(
        app,
        task,
        current_inputs=task["inputs"],
        library=lib,
        source_provider=lambda application_id, selected: deepcopy(base),
    )


def test_current_normal_receipt_uses_generic_fact_qualification_without_jd_special_case(
    monkeypatch,
):
    app, task, lib, base = case()
    before = deepcopy((app, task, lib, base))

    def reject_legacy(*args, **kwargs):
        raise AssertionError("Normal matching must not invoke exact-JD factual projections")

    monkeypatch.setattr(
        "career_evidence_graph.application_information.condition_from_library", reject_legacy
    )
    result = explain(app, task, lib, base)
    assert result["score"]["lower"] == 100
    assert result["qualification"]["status"] == "supported"
    assert result["factual_rechecks"][0]["fact"] == "confirmed_information"
    assert not result["match_recheck_stale"]
    assert (app, task, lib, base) == before


@pytest.mark.parametrize("drift", ["facts", "capture", "scope", "withdrawn"])
def test_normal_receipt_becomes_stale_when_evidence_or_applicable_answers_change(drift):
    app, task, lib, base = case()
    if drift == "facts":
        lib["records"][0]["value"] = "no"
    elif drift == "withdrawn":
        lib["records"][0].update(value=None, state="missing")
    elif drift == "scope":
        lib["records"][0]["scope"] = {"company": "Other"}
    else:
        base["items"] = [{"changed": True}]
        base.pop("revision")
        base["revision"] = digest(base)
    assert (
        current_match_recheck(task, lib, application=app, source_provider=lambda *_: base) is None
    )
    result = explain(app, task, lib, base)
    assert result["match_recheck_stale"]
    assert result["score"]["lower"] == 0
    assert result["qualification"]["status"] == "needs_input"


def test_explicit_negative_resolution_is_not_overridden_by_new_positive_documentary_match():
    app, task, lib, base = case()
    task["hard_condition_resolutions"] = [
        {
            "analysis_id": task["analysis_id"],
            "requirement_index": 0,
            "confirmed": True,
            "verified_by": "user",
            "eligible": False,
            "source": "Explicit correction",
            "analysis_input_revision": digest(analysis_input_binding(task["inputs"])),
        }
    ]
    result = explain(app, task, lib, base)
    assert result["qualification"]["status"] == "conflict"
    assert result["qualification"]["conditions"][0]["resolution"]["eligible"] is False


def test_invalid_fact_source_cannot_prove_generic_qualification():
    app, task, lib, base = case()
    task["match_rechecks"][0]["result"]["requirements"][0]["sources"][0]["text"] = "tampered"
    result = explain(app, task, lib, base)
    assert result["score"]["lower"] == 0
    assert result["qualification"]["status"] == "needs_input"


def test_newly_adopted_normal_analysis_also_checks_capture_freshness():
    app, task, lib, base = case()
    report = task.pop("match_rechecks")[0]["result"]
    report["id"] = task["analysis_id"]
    task["artifacts"][0]["result"] = report
    assert explain(app, task, lib, base)["qualification"]["status"] == "supported"
    base["changed"] = True
    base.pop("revision")
    base["revision"] = digest(base)
    result = explain(app, task, lib, base)
    assert result["score"]["lower"] == 0
    assert result["match_recheck_stale"]
    assert result["qualification"]["status"] == "needs_input"


@pytest.mark.parametrize("withdrawn", [False, True])
def test_preparation_stage_gate_uses_current_normal_receipt_instead_of_old_analysis(
    application, tmp_path, withdrawn
):
    from threading import Event

    from career_evidence_graph.application_flow import ApplicationFlowService, job_input_revision
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, app = application
    _, template, lib, base = case()
    called = Event()

    def resume(task):
        called.set()
        raise PortalDataError("synthetic_stop", "Stop after verifying the stage gate.")

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={"resume": resume},
        information_provider=lambda: lib,
        recheck_source_provider=lambda *_: deepcopy(base),
    )
    try:
        task = service.create(app["id"], app["revision"])
        original = deepcopy(template["artifacts"][0]["result"])
        report = deepcopy(template["match_rechecks"][0]["result"])
        source = information_source_snapshot(app, lib, base)["items"][0]
        report["jd_revision"] = job_input_revision(app)
        report["information_context_revision"] = information_context(app, lib)["revision"]
        report["requirements"][0].update(
            sources=[source],
            information_support={
                "fact": "confirmed_information",
                "status": "supported",
                "references": source["confirmed_information"]["references"],
                "explanation": "Applicable confirmed professional English.",
            },
        )
        with applications.write_lock():
            state = service._load()
            saved = service._task(state, task["id"])
            saved.update(
                status="analysis_ready",
                analysis_id=original["id"],
                artifacts=[{"stage": "analysis", "adopted": True, "result": original}],
            )
            saved["stages"]["analysis"] = {"status": "complete"}
            receipt = deepcopy(template["match_rechecks"][0])
            receipt.update(
                base_analysis_id=original["id"],
                base_analysis_revision=digest(original),
                job_binding=job_input_revision(app),
                result=report,
                information_context_revision=report["information_context_revision"],
            )
            saved["match_rechecks"] = [receipt]
            service._save(state)
            task = deepcopy(saved)
        assert original["requirements"][0]["judgment"] == "unknown"
        if withdrawn:
            lib["records"][0].update(state="missing", value=None)
            with pytest.raises(PortalDataError) as error:
                service.start(task["id"], task["revision"], "resume")
            assert error.value.code == "flow_qualification_required"
            assert not called.is_set()
        else:
            service.start(task["id"], task["revision"], "resume")
            assert called.wait(2), "The current generic review should pass the qualification gate"
    finally:
        service.close()


def test_withdrawn_fact_invalidates_prior_positive_resolution_without_jd_lookup(monkeypatch):
    from test_english_information_reuse import ENGLISH, example_case

    from career_evidence_graph.application_explanations import qualification_for
    from career_evidence_graph.application_information import condition_information_binding

    app, task = example_case(ENGLISH)
    original = library_with(answer("English fluency", "yes"))
    task["hard_condition_resolutions"] = [
        {
            "analysis_id": task["analysis_id"],
            "requirement_index": 0,
            "confirmed": True,
            "eligible": True,
            "verified_by": "user",
            "source": "Explicit language answer",
            "input_revision": digest(task["inputs"]),
            "qualification_basis": condition_information_binding(ENGLISH, app, original),
        }
    ]
    withdrawn = library_with(answer("English fluency", None, state="missing"))

    def forbidden(*args, **kwargs):
        raise AssertionError("Generic reuse must not parse a JD sentence")

    monkeypatch.setattr(
        "career_evidence_graph.application_information.condition_from_library", forbidden
    )
    from career_evidence_graph.application_explanations import adopted_analysis

    analysis = deepcopy(adopted_analysis(task))
    analysis["normal_facts_path"] = True
    before = deepcopy(task)
    result = qualification_for(task, app, withdrawn, analysis=analysis)
    assert result["status"] == "needs_input"
    assert result["conditions"][0]["resolution"] is None
    assert task == before


def test_trusted_career_requirement_needs_no_second_credibility_confirmation():
    from career_evidence_graph.application_explanations import qualification_for

    app, task, _, _ = case()
    report = deepcopy(task["match_rechecks"][0]["result"])
    report["application_library_policy"] = "trusted-library/v1"
    report["requirements"][0].pop("information_support")
    report["requirements"][0].update(
        explanation="Recorded professional English is accepted.",
        sources=[{"source_id": "career:language", "text": "English C2 (self-reported)."}],
    )
    result = qualification_for(task, app, analysis=report)
    assert result["status"] == "supported"
    assert result["conditions"][0]["explanation"] == "Recorded professional English is accepted."


def test_trusted_library_keeps_an_actual_unmet_certificate_requirement():
    from career_evidence_graph.application_explanations import qualification_for

    app, task, _, _ = case()
    report = deepcopy(task["match_rechecks"][0]["result"])
    report["application_library_policy"] = "trusted-library/v1"
    report["requirements"][0].pop("information_support")
    report["requirements"][0].update(
        text="Provide a valid language examination certificate",
        judgment="gap",
        explanation="The user reports no examination certificate.",
    )
    result = qualification_for(task, app, analysis=report)
    assert result["status"] == "conflict"
