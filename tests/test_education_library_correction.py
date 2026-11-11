"""An explicit library correction updates current education without losing manual work."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_flow_tex_impact_updates import refresh_tex, save_manual_wording
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate
from test_retained_education_boundaries import _two_credential_base

from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def education_base(full_latex):
    store, _, _, _, _, project, output, _ = full_latex
    source = store.catalog.get_evidence(
        career_source_snapshot(store.catalog)["profile_source"]["id"]
    )
    profile = json.loads(source["content"])
    profile["education"] = [
        {
            "degree": "MSc Mathematics",
            "institution": "Synthetic University",
            "period": "2020",
            "detail": "Probability",
        }
    ]
    store.catalog.update_evidence(
        source["id"],
        source["revision"],
        json.dumps(profile),
        actor="user",
        source="Recorded degree",
    )
    text = "\\section*{Education}\nMSc Mathematics, Synthetic University, 2020. Probability.\n"
    main = project / "main.tex"
    main.write_text(main.read_text().replace("\\end{document}", text + "\\end{document}"))
    output["groups"].append(
        {
            "title": "Education",
            "start_line": 14,
            "end_line": 15,
            "source_ids": [source["id"] + ":profile.education[0]"],
            "latex": text,
            "disposition": "include",
            "reason": "Documented degree",
        }
    )


@pytest.fixture
def education_portal(education_base, complete_portal):
    return complete_portal


@pytest.mark.parametrize(
    "field,before,after",
    [
        ("period", "2020", "2021"),
        ("degree", "MSc Mathematics", "MSc Mathematics (in progress)"),
        ("institution", "Synthetic University", "Correct University"),
        ("detail", "Probability", "Probability; expected completion, not awarded"),
    ],
)
def test_explicit_degree_correction_updates_only_education_without_confirmation(
    education_portal, field, before, after
):
    server, store, original, _ = education_portal
    flow = server.application_flow_service
    manual = save_manual_wording(flow, store, original)
    old = store.draft(manual["draft_id"])
    receipt = store.read_export(original["resume_id"])
    source = store.catalog.get_evidence(
        career_source_snapshot(store.catalog)["profile_source"]["id"]
    )
    profile = json.loads(source["content"])
    profile["education"][0][field] = after
    corrected = store.catalog.update_evidence(
        source["id"],
        source["revision"],
        json.dumps(profile),
        actor="user",
        source="Explicit correction: degree awarded in 2021",
    )

    def model(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        groups = deepcopy(payload["update_context"]["retained_groups"])
        for group in groups:
            if group["title"] == "Education":
                group["latex"] = "\\section*{Education}\nPhD awarded in 2030.\n"
            if group["title"] == "Project 6":
                group["latex"] = group["latex"].replace(
                    "Built 6 Python services; analyzed strategy.",
                    "Analyzed strategy; built 6 Python services.",
                )
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": []},
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    job = store.applications.get_application(original["application_id"])
    task = refresh_tex(flow, manual, job)
    assert task["status"] == "draft_ready", task["stages"]
    current = store.draft(task["draft_id"])
    assert not current["verification_queue"]
    assert current["latex_source"] == old["latex_source"].replace(before, after)
    assert store.draft(manual["draft_id"]) == old
    assert store.read_export(original["resume_id"]) == receipt
    assert corrected["history"][-1]["source"] == "Explicit correction: degree awarded in 2021"
    edited = flow.begin_automatic_edit(task["id"], task["revision"])
    text = store.draft(edited["draft_id"])["latex_source"].replace(
        "Analyzed strategy; built 5 Python services.",
        "Built 5 Python services; analyzed strategy.",
    )
    edited = flow.save_automatic_source(
        edited["id"], edited["revision"], edited["prism"]["source_revision"], text
    )
    assert not store.draft(edited["draft_id"])["verification_queue"]
    flow.start(edited["id"], edited["revision"], "export")
    exported = wait_for(
        flow, edited["id"], lambda row: row["status"] in {"materials_ready", "failed"}
    )
    assert exported["status"] == "materials_ready", exported["stages"]
    assert store.read_export(exported["resume_id"])["latex_source"] == text


@pytest.mark.parametrize("change", ["unrecorded", "damaged_applied", "unchanged"])
def test_unverified_correction_or_model_proposal_does_not_change_fixed_education(
    education_portal, change
):
    server, store, original, _ = education_portal
    flow = server.application_flow_service
    old = store.draft(original["draft_id"])
    source = store.catalog.get_evidence(
        career_source_snapshot(store.catalog)["profile_source"]["id"]
    )
    profile = json.loads(source["content"])
    if change != "unchanged":
        profile["education"][0]["period"] = "2021"
        if change == "unrecorded":
            (store.catalog.root / source["source_name"]).write_text(json.dumps(profile))
        else:
            corrected = store.catalog.update_evidence(
                source["id"],
                source["revision"],
                json.dumps(profile),
                actor="user",
                source="Date correction",
            )
            backup = store.catalog.root / corrected["history"][-1]["backup"]
            (backup.parent / "applied.json").write_text("{}")
    else:
        document = store.catalog.root / "contributions/project-1.md"
        document.write_text(document.read_text().replace("1 Python", "11 Python"))

    def model(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        groups = deepcopy(payload["update_context"]["retained_groups"])
        for group in groups:
            if group["title"] == "Education":
                group["latex"] = group["latex"].replace("2020", "2021")
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": []},
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    job = store.applications.get_application(original["application_id"])
    task = refresh_tex(flow, original, job)
    assert task["status"] == "draft_ready", task["stages"]
    current = store.draft(task["draft_id"])
    if change == "unchanged":
        assert (
            "MSc Mathematics, Synthetic University, 2020. Probability." in current["latex_source"]
        )
        assert not current["verification_queue"]
    else:
        assert [group["title"] for group in current["verification_queue"]] == ["Education"]
        compiles = len(store.prism_client.calls)
        with pytest.raises(PortalDataError):
            flow.start(task["id"], task["revision"], "export")
        assert len(store.prism_client.calls) == compiles
    assert store.draft(original["draft_id"]) == old


@pytest.mark.parametrize("manual_first", [False, True])
def test_accepted_two_credentials_update_only_the_corrected_entry(full_latex, manual_first):
    data, _ = _two_credential_base(full_latex)
    store, job, _, analysis, _, _, _, inputs = data
    original = generate(data)
    if manual_first:
        editable = store.prepare_group_review(
            original["id"], original["draft_sha256"], task_inputs=inputs
        )
        text = editable["latex_source"].replace(
            "Built a Python service with the engineering team.",
            "With the engineering team, built a Python service.",
        )
        original = store.save_automatic_source(
            editable["id"],
            editable["draft_sha256"],
            task_inputs=inputs,
            latex_source=text,
        )
    captures = {path: path.read_bytes() for path in (store.catalog.root / ".retained").iterdir()}
    manifest = store.catalog.root / "sources/retained-resume-sources.json"
    manifest_bytes = manifest.read_bytes()
    source = store.catalog.get_evidence(data[2]["profile_source"]["id"])
    profile = json.loads(source["content"])
    profile["education"][0]["period"] = "2017--2020"
    store.catalog.update_evidence(
        source["id"],
        source["revision"],
        json.dumps(profile),
        actor="user",
        source="Explicit first credential date correction",
    )
    current = career_source_snapshot(store.catalog)

    def model(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        return SimpleNamespace(
            structured_result={
                "groups": payload["update_context"]["retained_groups"],
                "limitations": [],
                "affected_group_indexes": [],
                "context_impact_reason": "Only documented credential A changed; work unchanged.",
            },
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    revised = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=current,
        analysis=analysis | {"source_snapshot_revision": current["revision"]},
        draft_only=True,
        task_inputs=inputs | {"sources_revision": current["revision"]},
        latex_base=original["source_checkpoint"],
        retained_draft=original,
    )
    assert not revised["verification_queue"]
    assert revised["latex_source"] == original["latex_source"].replace("2017--2021", "2017--2020")
    assert (
        "\\entry{Beta University}{2021--2022}{MSc Statistics}{Applied statistics}\n"
        in revised["latex_source"]
    )
    assert store.draft(revised["id"])["latex_source"] == revised["latex_source"]
    assert store.draft(original["id"])["latex_source"] == original["latex_source"]
    assert manifest.read_bytes() == manifest_bytes
    assert {path: path.read_bytes() for path in captures} == captures
    source = store.catalog.get_evidence(current["profile_source"]["id"])
    profile = json.loads(source["content"])
    profile["education"][0]["period"] = "2017--2019"
    store.catalog.update_evidence(
        source["id"],
        source["revision"],
        json.dumps(profile),
        actor="user",
        source="Second explicit first credential date correction",
    )
    current = career_source_snapshot(store.catalog)
    second = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=current,
        analysis=analysis | {"source_snapshot_revision": current["revision"]},
        draft_only=True,
        task_inputs=inputs | {"sources_revision": current["revision"]},
        latex_base=revised["source_checkpoint"],
        retained_draft=revised,
    )
    assert not second["verification_queue"]
    assert second["latex_source"] == revised["latex_source"].replace("2017--2020", "2017--2019")
    assert store.draft(revised["id"])["latex_source"] == revised["latex_source"]
    assert manifest.read_bytes() == manifest_bytes
    assert {path: path.read_bytes() for path in captures} == captures


@pytest.mark.parametrize("corruption", ["missing", "cleared", "wrong_parent", "wrong_event"])
def test_corrected_education_rejects_changed_proof_even_after_outer_rehash(
    education_portal, corruption
):
    server, store, original, _ = education_portal
    flow = server.application_flow_service
    source = store.catalog.get_evidence(
        career_source_snapshot(store.catalog)["profile_source"]["id"]
    )
    profile = json.loads(source["content"])
    profile["education"][0]["period"] = "2021"
    store.catalog.update_evidence(
        source["id"],
        source["revision"],
        json.dumps(profile),
        actor="user",
        source="Date correction",
    )

    def model(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        return SimpleNamespace(
            structured_result={
                "groups": payload["update_context"]["retained_groups"],
                "limitations": [],
            },
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    job = store.applications.get_application(original["application_id"])
    task = refresh_tex(flow, original, job)
    assert task["status"] == "draft_ready", task["stages"]
    path = store.root / task["draft_id"] / "draft.json"
    draft = json.loads(path.read_text())
    sources = draft["generation_sources"] + [
        source for group in draft["review_groups"] for source in group["sources"]
    ]
    for source in sources:
        if "education_correction" not in source:
            continue
        if corruption == "missing":
            source.pop("education_correction")
        elif corruption == "cleared":
            source["education_correction"] = {}
        elif corruption == "wrong_parent":
            source["education_correction"]["draft_id"] = "f" * 32
        else:
            source["education_correction"]["events"][0]["actor"] = "model"
    encoded = json.dumps(draft).encode()
    path.write_bytes(encoded)
    integrity = path.with_name("draft-integrity.json")
    document = json.loads(integrity.read_text())
    document["sha256"] = hashlib.sha256(encoded).hexdigest()
    integrity.write_text(json.dumps(document))
    with pytest.raises(PortalDataError) as error:
        store.draft(task["draft_id"])
    assert error.value.code == "resume_draft_invalid"


def test_two_explicit_corrections_keep_intervening_manual_work_without_unrelated_generation(
    education_portal,
):
    server, store, original, _ = education_portal
    flow = server.application_flow_service
    task = save_manual_wording(flow, store, original)
    historical = store.draft(task["draft_id"])

    def retained_model(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        return SimpleNamespace(
            structured_result={
                "groups": payload["update_context"]["retained_groups"],
                "limitations": [],
            },
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = retained_model
    job = store.applications.get_application(original["application_id"])
    for period in ("2021", "2022"):
        record = store.catalog.get_evidence(
            career_source_snapshot(store.catalog)["profile_source"]["id"]
        )
        profile = json.loads(record["content"])
        profile["education"][0]["period"] = period
        store.catalog.update_evidence(
            record["id"],
            record["revision"],
            json.dumps(profile),
            actor="user",
            source="Explicit date correction " + period,
        )
        task = refresh_tex(flow, task, job)
        assert task["status"] == "draft_ready", task["stages"]
        current = store.draft(task["draft_id"])
        assert not current["verification_queue"]
        assert "Synthetic University, " + period in current["latex_source"]
        assert "Built 6 Python services; analyzed strategy." in current["latex_source"]
        if period == "2021":
            task = flow.begin_automatic_edit(task["id"], task["revision"])
            text = store.draft(task["draft_id"])["latex_source"].replace(
                "Analyzed strategy; built 5 Python services.",
                "Built 5 Python services; analyzed strategy.",
            )
            task = flow.save_automatic_source(
                task["id"], task["revision"], task["prism"]["source_revision"], text
            )
        assert (
            "Built 5 Python services; analyzed strategy."
            in store.draft(task["draft_id"])["latex_source"]
        )
    adopted = store.draft(task["draft_id"])
    record = store.catalog.get_evidence(
        career_source_snapshot(store.catalog)["profile_source"]["id"]
    )
    profile = json.loads(record["content"])
    profile["title"] = "Updated unprinted title"
    store.catalog.update_evidence(
        record["id"],
        record["revision"],
        json.dumps(profile),
        actor="user",
        source="Explicit unprinted headline correction",
    )
    store.model_runner = lambda *_args, **_kwargs: pytest.fail(
        "Unchanged TeX needs no material model"
    )
    task = refresh_tex(flow, task, job)
    assert task["status"] == "draft_ready", task["stages"]
    assert store.draft(task["draft_id"])["latex_source"] == adopted["latex_source"]
    assert store.draft(historical["id"]) == historical
