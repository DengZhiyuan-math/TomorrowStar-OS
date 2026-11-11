"""Internal PDF reuse uses exact accepted bytes and fails closed."""

import hashlib
from types import SimpleNamespace

import pytest

from career_evidence_graph.application_pdf_reuse import read_reuse, try_reuse, verify_reuse
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def test_empty_history_does_not_invoke_model(tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("No semantic call without eligible history")

    assert try_reuse(SimpleNamespace(root=tmp_path), {}, {}, {}, [], runner=forbidden) is None


@pytest.fixture
def accepted(tmp_path, monkeypatch):
    raw = b"%PDF-1.4 synthetic accepted training resume"
    old_id = "a" * 32
    directory = tmp_path / old_id
    directory.mkdir()
    (directory / "resume.pdf").write_bytes(raw)

    def pdf(identifier):
        return (tmp_path / identifier / "resume.pdf").read_bytes()

    store = SimpleNamespace(root=tmp_path, pdf=pdf, configuration=lambda: {"model": "fake"})
    inputs = {"sources_revision": "source-v1"}
    source = {
        "id": "source-task",
        "application_revision": "revision-old",
        "application_id": "old-app",
        "origin": "generated_latex",
        "factual_review": "groups_reviewed",
        "draft_id": "b" * 32,
        "draft_sha256": "d" * 64,
        "prism": {"source_revision": "c" * 64},
        "job_description": "Optimize post training language models using experiments.",
        "inputs": inputs,
        "materials_confirmed": True,
        "status": "materials_ready",
        "resume_id": old_id,
        "resume_sha256": hashlib.sha256(raw).hexdigest(),
        "material_reviews": [
            {
                "id": "f" * 32,
                "at": 1.0,
                "actor": "user",
                "scope": "current_pdf_materials",
                "draft_id": "b" * 32,
                "draft_sha256": "d" * 64,
                "source_revision": "c" * 64,
                "group_review_revision": "g" * 64,
                "preview_id": "e" * 32,
                "resume_id": old_id,
                "pdf_sha256": hashlib.sha256(raw).hexdigest(),
                "input_revision": digest(inputs),
                "reviewed": ["complete_pdf_content", "pdf_layout", "full_source_consistency"],
            }
        ],
    }
    source["artifacts"] = [
        {
            "adopted": True,
            "stage": "export",
            "result": {
                "id": old_id,
                "pdf_sha256": source["resume_sha256"],
                "draft_id": "b" * 32,
                "draft_sha256": "d" * 64,
                "group_review": {
                    "revision": "g" * 64,
                    "source_revision": "c" * 64,
                    "preview_id": "e" * 32,
                },
            },
        }
    ]
    exported = source["artifacts"][0]["result"]
    groups = exported["group_review"]
    groups.update(
        draft_id=source["draft_id"],
        draft_sha256=source["draft_sha256"],
        input_revision=digest(inputs),
    )
    groups["revision"] = digest({k: v for k, v in groups.items() if k != "revision"})
    source["material_reviews"][0]["group_review_revision"] = groups["revision"]
    exported.update(
        application_id=source["application_id"],
        revision=source["application_revision"],
        task_inputs=inputs,
        prism_source_revision=source["prism"]["source_revision"],
        export_manifest_sha256="a" * 64,
    )
    import json

    manifest = dict(
        status="complete",
        id=old_id,
        application_id=source["application_id"],
        application_revision=source["application_revision"],
        task_inputs=inputs,
        draft_id=source["draft_id"],
        draft_sha256=source["draft_sha256"],
        pdf_sha256=source["resume_sha256"],
        group_review=groups,
        prism=source["prism"],
    )
    manifest_raw = json.dumps(manifest).encode()
    (directory / "export.json").write_bytes(manifest_raw)
    exported["export_manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
    target = {
        "id": "target-task",
        "application_id": "new-app",
        "inputs": inputs,
        "job_description": "Research post training language model optimization.",
        "input_epoch": 0,
        "analysis_id": "analysis",
    }
    monkeypatch.setattr(
        "career_evidence_graph.application_pdf_reuse.subprocess.run",
        lambda *a, **kw: SimpleNamespace(
            stdout="Reviewed model training and evaluation experience.", returncode=0
        ),
    )
    outputs = iter(
        [
            {
                "profiles": [
                    {
                        "id": "source-task",
                        "content": "post training optimization",
                        "core_work_confirmed": True,
                        "locators": ["Optimize post training"],
                    }
                ],
                "task_ids": ["source-task"],
            },
            {
                "approved": True,
                "source_task_id": "source-task",
                "reason": "Existing reviewed PDF sufficiently covers this JD and current facts.",
            },
        ]
    )
    calls = []

    def runner(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(structured_result=next(outputs))

    return store, source, target, runner, calls, raw


def test_accepted_pdf_is_copied_without_rewriting_origin(accepted):
    store, source, target, runner, calls, raw = accepted
    before = digest(source)
    result = try_reuse(
        store,
        target,
        {"revision": "source-v1", "items": []},
        {"id": "analysis"},
        [source],
        runner=runner,
    )
    assert result["kind"] == "accepted_pdf_reuse"
    assert result["application_id"] == "new-app"
    assert result["id"] != source["resume_id"]
    assert read_reuse(store, result) == raw
    assert digest(source) == before
    verify_reuse(store, target, result, [source])
    target["input_epoch"] = 1
    with pytest.raises(PortalDataError):
        verify_reuse(store, target, result, [source])


@pytest.mark.parametrize(
    "change",
    [
        {"materials_confirmed": False},
        {"status": "needs_recheck"},
        {"material_reviews": []},
        {"revoked": True},
        {"facts_invalid": True},
        {"job_description": "AI engineer"},
        {"pdf_reuse": {"old": "receipt"}},
    ],
)
def test_unaccepted_or_incomplete_history_is_not_considered(accepted, change):
    store, source, target, runner, calls, raw = accepted
    source.update(change)
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is None
    )
    assert calls == []


def test_revoked_origin_invalidates_already_adopted_pdf(accepted):
    store, source, target, runner, calls, raw = accepted
    result = try_reuse(
        store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
    )
    source["revoked"] = True
    with pytest.raises(PortalDataError):
        verify_reuse(store, target, result, [source])


def test_cache_failure_safely_misses_and_unknown_target_remains_blocked(accepted):
    store, source, target, runner, calls, raw = accepted

    def unavailable(*args, **kwargs):
        from career_evidence_graph.codex_cli import CodexCLIError

        raise CodexCLIError("configured Codex CLI executable is unavailable")

    assert (
        try_reuse(
            store,
            target,
            {"revision": "source-v1"},
            {"id": "analysis"},
            [source],
            runner=unavailable,
        )
        is None
    )
    target["status"] = "needs_recheck"
    with pytest.raises(PortalDataError):
        try_reuse(
            store,
            target,
            {"revision": "source-v1"},
            {"id": "analysis"},
            [source],
            runner=unavailable,
        )


def test_pdf_suitability_rejection_returns_to_generation(accepted):
    store, source, target, runner, calls, raw = accepted

    def reject(*args, **kwargs):
        output = runner(*args, **kwargs)
        if "approved" in output.structured_result:
            output.structured_result = {
                "approved": False,
                "source_task_id": "",
                "reason": "Language mismatch",
            }
        return output

    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=reject
        )
        is None
    )
    assert len(calls) == 2


def test_modified_pdf_and_explicit_regeneration_are_not_reused(accepted):
    store, source, target, runner, calls, raw = accepted
    target["force_regenerate"] = True
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is None
    )
    assert calls == []
    del target["force_regenerate"]
    (store.root / source["resume_id"] / "resume.pdf").write_bytes(b"%PDF-1.4 changed")
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is None
    )
    assert len(calls) == 1


def test_oversize_history_is_a_miss_without_silent_truncation(accepted):
    from copy import deepcopy

    store, source, target, runner, calls, raw = accepted
    history = [deepcopy(source) | {"id": f"source-{i}"} for i in range(25)]
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, history, runner=runner
        )
        is None
    )
    assert calls == []


def test_incomplete_core_work_profile_is_not_retrieved(accepted):
    store, source, target, runner, calls, raw = accepted
    source["job_description"] = (
        "AI engineer. Great company benefits and flexible hours for all employees."
    )

    def generic(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            structured_result={
                "profiles": [
                    {
                        "id": source["id"],
                        "content": "Unknown core duties",
                        "core_work_confirmed": False,
                        "locators": ["AI engineer."],
                    }
                ],
                "task_ids": [source["id"]],
            }
        )

    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=generic
        )
        is None
    )
    assert len(calls) == 1


def test_unreviewed_snapshot_facts_are_never_sent_as_reviewed(accepted):
    store, source, target, runner, calls, raw = accepted
    prompts = []

    def capture(config, prompt, **kwargs):
        prompts.append(prompt)
        return runner(config, prompt, **kwargs)

    snapshot = {
        "revision": "source-v1",
        "items": [{"text": "UNREVIEWED NEW EXPERIENCE", "resume_eligible": True}],
    }
    result = try_reuse(store, target, snapshot, {"id": "analysis"}, [source], runner=capture)
    assert result is not None
    assert "UNREVIEWED NEW EXPERIENCE" not in " ".join(prompts)


def test_generated_review_must_bind_original_draft_and_export(accepted):
    store, source, target, runner, calls, raw = accepted
    source["material_reviews"][0]["draft_id"] = "another-draft"
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is None
    )
    assert calls == []


def test_native_cli_version_and_exec_share_one_deadline(accepted, monkeypatch):
    import json
    from functools import partial

    from career_evidence_graph.codex_cli import run_codex_exec

    store, source, target, runner, calls, raw = accepted
    clock = [0.0]
    timeouts = []
    monkeypatch.setattr(
        "career_evidence_graph.application_pdf_reuse.time.monotonic", lambda: clock[0]
    )

    def process(argv, **kwargs):
        timeouts.append(kwargs["timeout"])
        if "--version" in argv:
            clock[0] += 5
            return SimpleNamespace(returncode=0, stdout="codex synthetic", stderr="")
        clock[0] += 8
        output = {
            "profiles": [
                {
                    "id": "source-task",
                    "content": "training",
                    "core_work_confirmed": True,
                    "locators": ["Optimize post training"],
                }
            ]
        }
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"type": "structured_result", "result": output}),
            stderr="",
        )

    native = partial(run_codex_exec, runner=process, environment={"PATH": "/synthetic"})
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=native
        )
        is None
    )
    assert timeouts == [12, 7]


def test_current_documentary_contact_and_education_can_reject_stale_pdf(accepted):
    store, source, target, runner, calls, raw = accepted
    captured = []
    snapshot = {
        "revision": "source-v1",
        "items": [],
        "profile_source": {"id": "profile", "revision": "current"},
        "documents": [{"id": "profile", "revision": "current", "available": True}],
        "profile": {
            "name": "Current Name",
            "links": [{"label": "Email", "url": "mailto:new@example.test"}],
            "education": [{"institution": "Confirmed University", "status": "in progress"}],
            "experience": [{"text": "UNREVIEWED EXPERIENCE"}],
        },
    }

    def check(config, prompt, **kwargs):
        output = runner(config, prompt, **kwargs)
        if "approved" in output.structured_result:
            captured.append(prompt)
            output.structured_result = {
                "approved": False,
                "source_task_id": "",
                "reason": "Stale contact or education",
            }
        return output

    assert try_reuse(store, target, snapshot, {"id": "analysis"}, [source], runner=check) is None
    assert "new@example.test" in captured[0]
    assert "in progress" in captured[0]
    assert "UNREVIEWED EXPERIENCE" not in captured[0]


def test_missing_current_source_revision_cannot_match_none(accepted):
    store, source, target, runner, calls, raw = accepted
    target["inputs"] = {}
    source["inputs"] = {}
    source["material_reviews"][0]["input_revision"] = digest({})
    assert try_reuse(store, target, {}, {"id": "analysis"}, [source], runner=runner) is None
    assert calls == []


def test_changed_information_library_is_a_conservative_miss(accepted):
    store, source, target, runner, calls, raw = accepted
    target["inputs"] = dict(target["inputs"], information_library_revision="new")
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is None
    )
    assert len(calls) == 1


def test_past_accepted_source_can_have_worker_reference(accepted):
    store, source, target, runner, calls, raw = accepted
    source.update(status="ready_for_review", worker_ref={"id": "past-worker"})
    before = digest(source)
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is not None
    )
    assert digest(source) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("application_id", "unrelated-app"),
        ("task_inputs", {"sources_revision": "wrong"}),
        ("prism_source_revision", "0" * 64),
        ("export_manifest_sha256", ""),
    ],
)
def test_generated_acceptance_rejects_unrelated_export(accepted, field, value):
    store, source, target, runner, calls, raw = accepted
    source["artifacts"][0]["result"][field] = value
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is None
    )
    assert calls == []


@pytest.mark.parametrize("field,value", [("id", ""), ("at", float("nan")), ("preview_id", "")])
def test_generated_acceptance_requires_real_review_identity(accepted, field, value):
    store, source, target, runner, calls, raw = accepted
    source["material_reviews"][0][field] = value
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is None
    )
    assert calls == []


def test_original_manifest_changes_invalidate_adopted_pdf(accepted):
    store, source, target, runner, calls, raw = accepted
    result = try_reuse(
        store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
    )
    (store.root / source["resume_id"] / "export.json").write_text("{}")
    with pytest.raises(PortalDataError):
        verify_reuse(store, target, result, [source])


def test_copied_material_has_private_permissions(accepted):
    import stat

    store, source, target, runner, calls, raw = accepted
    result = try_reuse(
        store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
    )
    folder = store.root / result["id"]
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE((folder / "resume.pdf").stat().st_mode) == 0o600


def test_cold_retrieval_and_pdf_check_need_only_two_model_round_trips(accepted):
    store, source, target, _runner, calls, raw = accepted
    outputs = iter(
        [
            {
                "profiles": [
                    {
                        "id": source["id"],
                        "content": "post training optimization",
                        "core_work_confirmed": True,
                        "locators": ["Optimize post training"],
                    }
                ],
                "task_ids": [source["id"]],
            },
            {
                "approved": True,
                "source_task_id": "source-task",
                "reason": "Reviewed unchanged PDF covers the target work.",
            },
        ]
    )

    def bounded_runner(*args, **kwargs):
        calls.append(kwargs)
        assert len(calls) <= 2, "Reuse must not require a separate profile-model round trip"
        return SimpleNamespace(structured_result=next(outputs))

    result = try_reuse(
        store,
        target,
        {"revision": "source-v1"},
        {"id": "analysis"},
        [source],
        runner=bounded_runner,
    )
    assert result is not None
    assert read_reuse(store, result) == raw
    assert len(calls) == 2


def test_alternative_pdf_is_checked_in_same_model_round(accepted):
    import json
    from copy import deepcopy

    store, source, target, _runner, calls, raw = accepted
    alternative = deepcopy(source)
    alternative.update(id="alternative-task", resume_id="9" * 32)
    alternative_raw = b"%PDF-1.4 alternative accepted training resume"
    alternative["resume_sha256"] = hashlib.sha256(alternative_raw).hexdigest()
    alternative["material_reviews"][0].update(
        resume_id=alternative["resume_id"], pdf_sha256=alternative["resume_sha256"]
    )
    export = alternative["artifacts"][0]["result"]
    export.update(id=alternative["resume_id"], pdf_sha256=alternative["resume_sha256"])
    original_manifest = json.loads((store.root / source["resume_id"] / "export.json").read_text())
    original_manifest.update(id=alternative["resume_id"], pdf_sha256=alternative["resume_sha256"])
    folder = store.root / alternative["resume_id"]
    folder.mkdir()
    (folder / "resume.pdf").write_bytes(alternative_raw)
    manifest_raw = json.dumps(original_manifest).encode()
    (folder / "export.json").write_bytes(manifest_raw)
    export["export_manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
    outputs = iter(
        [
            {
                "profiles": [
                    {
                        "id": row["id"],
                        "content": "training optimization",
                        "core_work_confirmed": True,
                        "locators": ["Optimize post training"],
                    }
                    for row in [source, alternative]
                ],
                "task_ids": [source["id"], alternative["id"]],
            },
            {
                "approved": True,
                "source_task_id": alternative["id"],
                "reason": "Second candidate fits; first candidate language does not.",
            },
        ]
    )

    def runner(config, prompt, **kwargs):
        calls.append(prompt)
        assert len(calls) <= 2
        return SimpleNamespace(structured_result=next(outputs))

    result = try_reuse(
        store,
        target,
        {"revision": "source-v1"},
        {"id": "analysis"},
        [source, alternative],
        runner=runner,
    )
    assert result is not None
    assert read_reuse(store, result) == alternative_raw
    assert len(calls) == 2
    assert source["id"] in calls[1] and alternative["id"] in calls[1]


def test_unchanged_jd_query_reuses_retrieval_but_rechecks_exact_pdf(accepted):
    import json

    store, source, target, _runner, calls, raw = accepted

    def runner(config, prompt, **kwargs):
        calls.append(json.loads(config.output_schema.read_text())["title"])
        result = (
            {
                "profiles": [
                    {
                        "id": source["id"],
                        "content": "training",
                        "core_work_confirmed": True,
                        "locators": ["Optimize post training"],
                    }
                ],
                "task_ids": [source["id"]],
            }
            if calls[-1] == "_Retrieval"
            else {
                "approved": True,
                "source_task_id": source["id"],
                "reason": "Suitable unchanged PDF",
            }
        )
        return SimpleNamespace(structured_result=result)

    first = try_reuse(
        store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
    )
    assert first is not None and read_reuse(store, first) == raw
    second_target = dict(target, id="another-task")
    second = try_reuse(
        store, second_target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
    )
    assert second is not None and read_reuse(store, second) == raw
    assert calls == ["_Retrieval", "_Suitability", "_Suitability"]
    source["revoked"] = True
    assert (
        try_reuse(
            store,
            second_target,
            {"revision": "source-v1"},
            {"id": "analysis"},
            [source],
            runner=runner,
        )
        is None
    )
    assert len(calls) == 3


@pytest.mark.parametrize("chosen", ["unselected-task", "", "source-task-with-wrong-binding"])
def test_model_cannot_adopt_a_pdf_outside_verified_batch(accepted, chosen):
    store, source, target, runner, calls, raw = accepted

    def forged(config, prompt, **kwargs):
        result = runner(config, prompt, **kwargs)
        if "approved" in result.structured_result:
            result.structured_result["source_task_id"] = chosen
        return result

    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=forged
        )
        is None
    )
    assert len(calls) == 2


@pytest.mark.parametrize("cached", [[], None, "invalid root"])
def test_malformed_query_cache_safely_returns_to_generation(accepted, cached):
    import json

    store, source, target, runner, calls, raw = accepted
    assert try_reuse(
        store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
    )
    query = next((store.root / ".pdf-reuse-index").glob("query-*.json"))
    query.write_text(json.dumps(cached))
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is None
    )


def test_adopted_choice_must_bind_the_same_source_as_original_acceptance(accepted):
    import json

    store, source, target, runner, calls, raw = accepted
    result = try_reuse(
        store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
    )
    result["reuse_binding"]["suitability"]["source_task_id"] = "different-source"
    (store.root / result["id"] / "reuse.json").write_text(json.dumps(result))
    with pytest.raises(PortalDataError):
        verify_reuse(store, target, result, [source])


def test_ineligible_source_association_cannot_hide_same_pdf_current_association(accepted):
    import json
    from copy import deepcopy

    store, source, target, _runner, calls, raw = accepted
    old_source = deepcopy(source)
    old_source.update(id="old-source-task", resume_id="7" * 32)
    old_source["inputs"]["sources_revision"] = "source-v0"
    exported = old_source["artifacts"][0]["result"]
    groups = exported["group_review"]
    groups["input_revision"] = digest(old_source["inputs"])
    groups["revision"] = digest({key: value for key, value in groups.items() if key != "revision"})
    exported.update(id=old_source["resume_id"], task_inputs=old_source["inputs"])
    old_source["material_reviews"][0].update(
        resume_id=old_source["resume_id"],
        input_revision=digest(old_source["inputs"]),
        group_review_revision=groups["revision"],
    )
    manifest = json.loads((store.root / source["resume_id"] / "export.json").read_text())
    manifest.update(
        id=old_source["resume_id"], task_inputs=old_source["inputs"], group_review=groups
    )
    directory = store.root / old_source["resume_id"]
    directory.mkdir()
    (directory / "resume.pdf").write_bytes(raw)
    manifest_raw = json.dumps(manifest).encode()
    (directory / "export.json").write_bytes(manifest_raw)
    exported["export_manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()

    def runner(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())["title"]
        calls.append(schema)
        if schema == "_Retrieval":
            output = {
                "profiles": [
                    {
                        "id": row["id"],
                        "content": "post training optimization",
                        "core_work_confirmed": True,
                        "locators": ["Optimize post training"],
                    }
                    for row in [old_source, source]
                ],
                "task_ids": [old_source["id"], source["id"]],
            }
        else:
            supplied = json.loads(prompt.split("\n", 1)[1])["candidates"]
            assert [candidate["source_task_id"] for candidate in supplied] == [source["id"]]
            output = {
                "approved": True,
                "source_task_id": source["id"],
                "reason": "The current source association permits unchanged reuse.",
            }
        return SimpleNamespace(structured_result=output)

    result = try_reuse(
        store,
        target,
        {"revision": "source-v1", "items": []},
        {"id": "analysis"},
        [old_source, source],
        runner=runner,
    )
    assert result is not None
    assert read_reuse(store, result) == raw
    assert result["reuse_binding"]["source_task_id"] == source["id"]
    verify_reuse(store, target, result, [old_source, source])
    assert calls == ["_Retrieval", "_Suitability"]


def test_content_version_never_enters_legacy_pdf_business_reuse(accepted):
    store, source, target, runner, calls, raw = accepted
    source["artifacts"].append(
        {
            "adopted": True,
            "stage": "resume",
            "result": {
                "id": source["draft_id"],
                "draft_sha256": source["draft_sha256"],
                "generation_contract": "content-writing/v1",
                "content_reconciliation": {"status": "unmerged"},
            },
        }
    )
    assert (
        try_reuse(
            store, target, {"revision": "source-v1"}, {"id": "analysis"}, [source], runner=runner
        )
        is None
    )
    assert calls == []
