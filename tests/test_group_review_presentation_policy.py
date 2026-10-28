"""Fixed documented education is reused without fabricating a human decision."""

import json
from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_resume import task_resume as task_resume
from test_full_latex_flow import latex_flow as latex_flow
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.application_group_review import group_review_snapshot
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def policy_draft():
    from career_evidence_graph.resume_presentation import PRESENTATION_POLICY_VERSION

    source = {
        "source_id": "profile:education:0",
        "source_kind": "education",
        "resume_eligible": True,
        "rewrite_allowed": False,
        "attribution": "Documented education; no capability assessment",
        "text": json.dumps(
            {
                "degree": "MSc Mathematics",
                "institution": "Synthetic University",
                "period": "2020",
                "detail": "Probability",
            }
        ),
    }
    text = "\\section*{Education}\nMSc Mathematics, Synthetic University, 2020. Probability.\n"
    return {
        "id": "a" * 32,
        "draft_sha256": "b" * 64,
        "origin": "generated_latex",
        "group_session": {"id": "c" * 32},
        "presentation_policy": PRESENTATION_POLICY_VERSION,
        "group_context_revision": "d" * 64,
        "source_checkpoint": {"source_revision": "e" * 64},
        "group_preview": {"id": "f" * 32, "source_revision": "e" * 64},
        "review_groups": [
            {
                "id": "1" * 64,
                "content_policy": "fixed_education",
                "disposition": "include",
                "original": text,
                "rewritten": text,
                "sources": [source],
                "attribution": [source["attribution"]],
                "review_fingerprint": "2" * 64,
            }
        ],
    }


def test_documented_education_has_separate_binding_without_a_user_receipt():
    draft = policy_draft()
    before = deepcopy(draft)
    result = group_review_snapshot(draft, {"jd": "synthetic"}, [])
    assert result["receipts"] == []
    assert result["fixed_education"] == [
        {
            "group_id": "1" * 64,
            "review_fingerprint": "2" * 64,
            "source_ids": ["profile:education:0"],
            "basis": "documentary_reuse",
        }
    ]
    assert result["input_revision"] == digest({"jd": "synthetic"})
    assert draft == before
    assert "verified_by" not in result["fixed_education"][0]


@pytest.mark.parametrize("damage", ["rewritten", "source", "eligibility", "policy"])
def test_fixed_education_label_cannot_bypass_source_validation(damage):
    draft = policy_draft()
    group = draft["review_groups"][0]
    if damage == "rewritten":
        group["rewritten"] += "Invented award."
    elif damage == "source":
        group["sources"][0]["source_kind"] = "contribution"
    elif damage == "eligibility":
        group["sources"][0]["resume_eligible"] = False
    else:
        draft["presentation_policy"] = "unknown-policy"
    with pytest.raises(PortalDataError):
        group_review_snapshot(draft, {}, [])


def test_legacy_review_snapshot_keeps_original_receipt_payload():
    draft = policy_draft()
    draft.pop("presentation_policy")
    receipt = {
        "id": "9" * 32,
        "group_id": "1" * 64,
        "draft_id": draft["id"],
        "draft_sha256": draft["draft_sha256"],
        "input_revision": digest({}),
        "source_revision": "e" * 64,
        "preview_id": "f" * 32,
        "verified_by": "user",
        "review_fingerprint": "2" * 64,
    }
    result = group_review_snapshot(draft, {}, [receipt])
    assert result["receipts"] == [receipt]
    assert "fixed_education" not in result
    assert "presentation_policy" not in result


def education_data(full_latex):
    """Add a documented credential to the existing complete-source fixture."""
    from career_evidence_graph.application_resume import career_source_snapshot

    store, _, _, analysis, _, project, output, inputs = full_latex
    (store.catalog.root / "sources/profile.json").write_text(
        json.dumps(
            {
                "name": "Synthetic Person",
                "education": [
                    {
                        "degree": "MSc Mathematics",
                        "institution": "Synthetic University",
                        "period": "2020",
                        "detail": "Probability",
                    }
                ],
            }
        )
    )
    sources = career_source_snapshot(store.catalog)
    data = list(full_latex)
    data[2] = sources
    inputs["sources_revision"] = sources["revision"]
    analysis["source_snapshot_revision"] = sources["revision"]
    text = "\\section*{Education}\nMSc Mathematics, Synthetic University, 2020. Probability.\n"
    main = project / "main.tex"
    main.write_text(main.read_text().replace("\\end{document}", text + "\\end{document}"))
    output["groups"].append(
        {
            "title": "Education",
            "start_line": 14,
            "end_line": 15,
            "source_ids": [sources["profile_source"]["id"] + ":profile.education[0]"],
            "latex": text,
            "disposition": "include",
            "reason": "Documented degree",
        }
    )
    return data


@pytest.fixture
def education_review(full_latex):
    from test_full_latex_generation import generate
    from test_standalone_prism_review import FakePrism

    data = education_data(full_latex)
    store, *_, inputs = data
    generated = generate(data)
    store.group_prism_client = FakePrism()
    draft = store.prepare_group_review(
        generated["id"], generated["draft_sha256"], task_inputs=inputs
    )
    return store, draft, inputs


@pytest.mark.parametrize("change", ["text", "omit", "source"])
def test_group_editor_rejects_fixed_education_changes(education_review, change):
    store, draft, inputs = education_review
    group = draft["review_groups"][-1]
    payload = {
        "group_id": group["id"],
        "title": group["title"],
        "latex": group["rewritten"],
        "source_ids": [s["source_id"] for s in group["sources"]],
        "disposition": "include",
    }
    if change == "text":
        payload["latex"] = payload["latex"].replace("2020", "2021")
    elif change == "omit":
        payload["disposition"] = "omit"
    else:
        payload["source_ids"] = [draft["review_groups"][1]["sources"][0]["source_id"]]
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    with pytest.raises(PortalDataError) as error:
        store.edit_group_review(
            draft["id"], draft["draft_sha256"], task_inputs=inputs, payload=payload
        )
    assert error.value.code == "resume_fixed_education_changed"
    assert before == {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    assert store.group_prism_client.calls == []


@pytest.mark.parametrize("change", ["text", "delete"])
def test_source_editor_cannot_change_or_remove_fixed_education_before_compile(
    education_review, change
):
    from pathlib import Path

    store, draft, inputs = education_review
    group = draft["review_groups"][-1]
    main = Path(draft["group_session"]["project_root"]) / "main.tex"
    text = main.read_text()
    if change == "text":
        text = text.replace("2020", "2021")
    else:
        block = (
            f"% TomorrowStar group {group['id']} begin\n"
            + group["rewritten"]
            + f"\n% TomorrowStar group {group['id']} end\n"
        )
        text = text.replace(block, "")
    main.write_text(text)
    with pytest.raises(PortalDataError) as error:
        store.capture_group_review(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            expected_source_revision=store.group_review_state(draft["id"])["live_source_revision"],
        )
    assert error.value.code == "resume_fixed_education_changed"
    assert store.group_prism_client.calls == []
    assert store.draft(draft["id"])["latex_source"] == draft["latex_source"]


@pytest.mark.parametrize("surface", ["group", "source"])
def test_new_policy_editor_rejects_internal_ai_tool_disclosures(education_review, surface):
    from pathlib import Path

    store, draft, inputs = education_review
    group = draft["review_groups"][1]
    latex = group["rewritten"] + " Codex-assisted implementation."
    if surface == "source":
        main = Path(draft["group_session"]["project_root"]) / "main.tex"
        main.write_text(main.read_text().replace(group["rewritten"], latex))
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    with pytest.raises(PortalDataError) as error:
        if surface == "group":
            store.edit_group_review(
                draft["id"],
                draft["draft_sha256"],
                task_inputs=inputs,
                payload={
                    "group_id": group["id"],
                    "title": group["title"],
                    "latex": latex,
                    "source_ids": [s["source_id"] for s in group["sources"]],
                },
            )
        else:
            store.capture_group_review(
                draft["id"],
                draft["draft_sha256"],
                task_inputs=inputs,
                expected_source_revision=store.group_review_state(draft["id"])[
                    "live_source_revision"
                ],
            )
    assert error.value.code == "resume_tool_attribution_disclosure"
    assert before == {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    assert store.group_prism_client.calls == []


def test_flow_reuses_education_and_waits_only_for_tailored_group(latex_flow):
    from test_group_review_flow import act, generated, prepared

    service, task = generated(latex_flow)
    result = prepared(task)
    result["presentation_policy"] = policy_draft()["presentation_policy"]
    education = policy_draft()["review_groups"][0]
    result["review_groups"][0] = education
    service.callbacks["group_prepare"] = lambda _: result
    task = act(service, task, "begin-group-review")
    result = deepcopy(result)
    result.update(id="captured", draft_sha256="c" * 64)
    result["group_preview"] = {"id": "preview", "source_revision": task["prism"]["source_revision"]}
    service.callbacks["group_capture"] = lambda *args, **kwargs: {
        "draft": result,
        "status": "ready",
    }
    task = act(
        service,
        task,
        "capture-group-review",
        expected_source_revision=task["prism"]["source_revision"],
    )
    before = deepcopy(task)
    task = act(
        service,
        task,
        "review-group",
        draft_id=task["draft_id"],
        draft_sha256=task["draft_sha256"],
        group_id=education["id"],
        review_fingerprint=education["review_fingerprint"],
    )
    assert task == before
    assert task["group_reviews"] == []
    task = act(
        service,
        task,
        "review-group",
        draft_id=task["draft_id"],
        draft_sha256=task["draft_sha256"],
        group_id="two",
        review_fingerprint="2" * 64,
    )
    assert task["factual_review"] == "groups_reviewed"
    assert [row["group_id"] for row in task["group_reviews"]] == ["two"]
    assert task["materials_confirmed"] is False
    assert task["resume_id"] is None


@pytest.mark.parametrize("surface", ["group", "source"])
def test_internal_latex_comments_keep_tool_provenance_without_resume_disclosure(
    education_review, surface
):
    from pathlib import Path

    store, draft, inputs = education_review
    group = draft["review_groups"][1]
    latex = group["rewritten"] + "\n% Codex-assisted implementation; internal evidence only.\n"
    if surface == "group":
        revised = store.edit_group_review(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            payload={
                "group_id": group["id"],
                "title": group["title"],
                "latex": latex,
                "source_ids": [s["source_id"] for s in group["sources"]],
            },
        )
    else:
        main = Path(draft["group_session"]["project_root"]) / "main.tex"
        main.write_text(main.read_text().replace(group["rewritten"], latex))
        revised = store.capture_group_review(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            expected_source_revision=store.group_review_state(draft["id"])["live_source_revision"],
        )["draft"]
    assert "% Codex-assisted implementation; internal evidence only." in revised["latex_source"]
    assert store.draft(revised["id"])["latex_source"] == revised["latex_source"]


def test_tailored_work_can_be_added_while_education_stays_fixed(education_review):
    store, draft, inputs = education_review
    work = draft["review_groups"][1]
    revised = store.edit_group_review(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        payload={
            "title": "Relevant strategy",
            "latex": "Analyzed strategy.\n",
            "source_ids": [work["sources"][0]["source_id"]],
        },
    )
    assert revised["review_groups"][-1]["title"] == "Relevant strategy"
    assert revised["review_groups"][-2]["rewritten"] == draft["review_groups"][-1]["rewritten"]
    assert store.draft(revised["id"])["latex_source"] == revised["latex_source"]


@pytest.mark.parametrize("change", ["title", "policy", "downgrade"])
def test_rehashed_group_metadata_cannot_change_fixed_education_root_binding(
    education_review, change
):
    import hashlib

    store, draft, _ = education_review
    path = store.root / draft["id"] / "draft.json"
    changed = json.loads(path.read_bytes())
    if change == "title":
        changed["review_groups"][-1]["title"] = "A changed documentary identity"
    elif change == "policy":
        changed.pop("presentation_policy")
    else:
        changed["review_groups"][-1]["content_policy"] = "jd_tailored"
    raw = json.dumps(changed).encode()
    path.write_bytes(raw)
    (path.parent / "draft-integrity.json").write_text(
        json.dumps(
            {"schemaVersion": 1, "id": draft["id"], "sha256": hashlib.sha256(raw).hexdigest()}
        )
    )
    with pytest.raises(PortalDataError) as error:
        store.draft(draft["id"])
    assert error.value.code == "resume_draft_invalid"
    assert "provenance" in str(error.value.__cause__) or "Fixed documented education" in str(
        error.value.__cause__
    )


@pytest.mark.parametrize("bucket", ["verification_queue", "omitted_groups", "review_groups"])
def test_unresolved_education_blocks_flow_completion_after_other_groups_reviewed(
    latex_flow, bucket
):
    from test_group_review_flow import act, generated, prepared

    service, task = generated(latex_flow)
    result = prepared(task)
    result["presentation_policy"] = policy_draft()["presentation_policy"]
    education = policy_draft()["review_groups"][0]
    education.update(
        content_policy="education_verification_required",
        disposition={
            "verification_queue": "verify",
            "omitted_groups": "omit",
            "review_groups": "include",
        }[bucket],
    )
    result[bucket].append(education)
    service.callbacks["group_prepare"] = lambda _: result
    task = act(service, task, "begin-group-review")
    result = deepcopy(result)
    result.update(id="captured", draft_sha256="c" * 64)
    result["group_preview"] = {"id": "preview", "source_revision": task["prism"]["source_revision"]}
    service.callbacks["group_capture"] = lambda *args, **kwargs: {
        "draft": result,
        "status": "ready",
    }
    task = act(
        service,
        task,
        "capture-group-review",
        expected_source_revision=task["prism"]["source_revision"],
    )
    for group in result["review_groups"]:
        task = act(
            service,
            task,
            "review-group",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
            group_id=group["id"],
            review_fingerprint=group["review_fingerprint"],
        )
    assert task["factual_review"] == "pending"
    assert task["materials_confirmed"] is False and task["resume_id"] is None
    with pytest.raises(PortalDataError) as error:
        act(
            service,
            task,
            "export-pdf",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
        )
    assert error.value.code == "flow_factual_review_required"


@pytest.mark.parametrize("bucket", ["verification_queue", "omitted_groups", "review_groups"])
def test_snapshot_never_binds_a_version_with_unresolved_education(bucket):
    draft = policy_draft()
    pending = deepcopy(draft["review_groups"][0])
    pending.update(id="3" * 64, content_policy="education_verification_required")
    draft.setdefault(bucket, []).append(pending)
    with pytest.raises(PortalDataError) as error:
        group_review_snapshot(draft, {}, [])
    assert error.value.code == "flow_education_verification_required"


def test_public_store_projection_keeps_presentation_policy_for_review_binding(education_review):
    from career_evidence_graph.resume_presentation import PRESENTATION_POLICY_VERSION

    store, draft, _ = education_review
    assert draft["presentation_policy"] == PRESENTATION_POLICY_VERSION
    assert (
        store.draft(draft["group_session"]["root_draft_id"])["presentation_policy"]
        == PRESENTATION_POLICY_VERSION
    )
    assert draft["review_groups"][-1]["content_policy"] == "fixed_education"
