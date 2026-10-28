"""Loaded identities describe actual code, independently of mutable source files."""

from career_evidence_graph import application_worker_browser, owned_browser_cdp
from career_evidence_graph.loaded_code import load_worker_modules

# The worker records its identity after preloading the whole role (MC-20).
load_worker_modules()


def test_worker_revision_changes_when_actual_loaded_function_changes(monkeypatch):
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    original = loaded_runtime_revision("worker")
    assert original is not None and original.startswith("python-loaded-code/v1:worker:")
    method = application_worker_browser.ApplicationRunner.permitted
    monkeypatch.setattr(
        method,
        "__code__",
        method.__code__.replace(co_consts=(*method.__code__.co_consts, "Synthetic loaded change")),
    )
    assert loaded_runtime_revision("worker") != original


def test_loaded_defaults_and_constants_change_identity(monkeypatch):
    from career_evidence_graph import application_worker
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    original = loaded_runtime_revision("worker")
    method = application_worker_browser.ApplicationRunner.permitted
    monkeypatch.setattr(method, "__defaults__", ("Synthetic loaded default",))
    changed_defaults = loaded_runtime_revision("worker")
    assert changed_defaults != original
    monkeypatch.setattr(application_worker, "HELPER_SHA256", "Synthetic loaded constant")
    assert loaded_runtime_revision("worker") != changed_defaults


def test_set_order_is_irrelevant_but_membership_changes_identity(monkeypatch):
    from career_evidence_graph import application_worker
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    for container in (set, frozenset):
        monkeypatch.setattr(application_worker, "COUNTRIES", container(("CHE", "USA", "GBR")))
        original = loaded_runtime_revision("worker")
        monkeypatch.setattr(application_worker, "COUNTRIES", container(("GBR", "USA", "CHE")))
        assert loaded_runtime_revision("worker") == original
        monkeypatch.setattr(application_worker, "COUNTRIES", container(("CHE", "USA", "DEU")))
        assert loaded_runtime_revision("worker") != original


def test_disk_edits_do_not_relabel_loaded_code(tmp_path, monkeypatch):
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    disk = tmp_path / "application_worker_browser.py"
    disk.write_text("# Synthetic source before replacement\n")
    monkeypatch.setattr(application_worker_browser, "__file__", str(disk))
    original = loaded_runtime_revision("worker")
    disk.write_text("# Different source bytes which have never been loaded\n")
    assert loaded_runtime_revision("worker") == original


def test_local_code_filename_and_line_locations_do_not_change_identity(monkeypatch):
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    original = loaded_runtime_revision("worker")
    method = application_worker_browser.ApplicationRunner.permitted
    monkeypatch.setattr(
        method,
        "__code__",
        method.__code__.replace(
            co_filename="/synthetic/other-checkout/private.py",
            co_firstlineno=4000,
            co_linetable=b"",
        ),
    )
    assert loaded_runtime_revision("worker") == original


def test_missing_worker_module_stays_unknown_without_importing(monkeypatch):
    import sys

    from career_evidence_graph import loaded_code

    assert loaded_code.loaded_runtime_revision("worker") is not None
    monkeypatch.delitem(sys.modules, "career_evidence_graph.workable_uploads")

    def no_import(*_args, **_kwargs):
        raise AssertionError("An identity read must not load an executor")

    monkeypatch.setattr(loaded_code, "import_module", no_import)
    assert loaded_code.loaded_runtime_revision("worker") is None
    assert "career_evidence_graph.workable_uploads" not in sys.modules


def test_missing_owned_cdp_code_keeps_worker_identity_unknown(monkeypatch):
    import sys

    from career_evidence_graph import loaded_code

    assert loaded_code.loaded_runtime_revision("worker") is not None
    monkeypatch.delitem(sys.modules, "career_evidence_graph.owned_browser_cdp", raising=False)

    def no_import(*_args, **_kwargs):
        raise AssertionError("An identity read must not load a browser helper")

    monkeypatch.setattr(loaded_code, "import_module", no_import)
    assert loaded_code.loaded_runtime_revision("worker") is None
    assert "career_evidence_graph.owned_browser_cdp" not in sys.modules


def test_owned_cdp_operation_code_is_part_of_worker_identity(monkeypatch):
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    original = loaded_runtime_revision("worker")
    assert original is not None
    operation = owned_browser_cdp._operation
    monkeypatch.setattr(
        operation,
        "__code__",
        operation.__code__.replace(
            co_consts=(*operation.__code__.co_consts, "Synthetic CDP operation change")
        ),
    )
    assert loaded_runtime_revision("worker") != original


def test_owned_cdp_pending_connection_state_does_not_change_worker_identity():
    import asyncio
    from types import SimpleNamespace

    from career_evidence_graph.loaded_code import loaded_runtime_revision

    original = loaded_runtime_revision("worker")
    assert original is not None
    handlers = []
    connection = SimpleNamespace(on=lambda event, handler: handlers.append((event, handler)))
    page = SimpleNamespace(_impl_obj=SimpleNamespace(_connection=connection))
    keeper = owned_browser_cdp._state(page)
    assert owned_browser_cdp._state(page) is keeper
    assert [event for event, _handler in handlers] == ["close"]
    loop = asyncio.new_event_loop()
    response = loop.create_future()

    async def pending_response():
        return await response

    task = loop.create_task(pending_response())
    try:
        loop.run_until_complete(asyncio.sleep(0))
        keeper.pending.add(task)
        keeper.background.add(task)
        resource = object()
        keeper.resources[id(resource)] = resource
        assert not task.done()
        assert loaded_runtime_revision("worker") == original
        keeper.close()
        assert keeper.closed and not keeper.resources
        assert loaded_runtime_revision("worker") == original
    finally:
        task.cancel()
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        loop.close()


def test_owned_cdp_ambient_deadline_does_not_change_worker_identity():
    from career_evidence_graph.loaded_code import loaded_runtime_revision

    original = loaded_runtime_revision("worker")
    assert original is not None
    deadline = owned_browser_cdp._ACTIVE_DEADLINE
    before = deadline.get()
    first = deadline.set(123.0)
    try:
        assert loaded_runtime_revision("worker") == original
        second = deadline.set(456.0)
        try:
            assert loaded_runtime_revision("worker") == original
        finally:
            deadline.reset(second)
        assert deadline.get() == 123.0
        assert loaded_runtime_revision("worker") == original
    finally:
        deadline.reset(first)
    assert deadline.get() == before
    assert loaded_runtime_revision("worker") == original


def test_actual_normalizer_code_is_part_of_loaded_identity(monkeypatch):
    from career_evidence_graph import loaded_code

    original = loaded_code.loaded_runtime_revision("worker")
    method = loaded_code._normalize
    monkeypatch.setattr(
        method,
        "__code__",
        method.__code__.replace(
            co_consts=(*method.__code__.co_consts, "Synthetic normalizer change")
        ),
    )
    assert loaded_code.loaded_runtime_revision("worker") != original


def test_controller_startup_is_explicit_and_roles_are_not_file_digests():
    import re

    from career_evidence_graph import loaded_code
    from career_evidence_graph.career_portal import _loaded_preparation_revision

    loaded_code.load_controller_modules()
    controller = loaded_code.loaded_runtime_revision("controller")
    worker = loaded_code.loaded_runtime_revision("worker")
    assert re.fullmatch(r"python-loaded-code/v1:controller:[a-f0-9]{64}", controller)
    assert re.fullmatch(r"python-loaded-code/v1:worker:[a-f0-9]{64}", worker)
    assert controller != worker
    assert re.fullmatch(r"[a-f0-9]{64}", _loaded_preparation_revision())


def test_runtime_role_revisions_are_stable_across_hash_seeds():
    import os
    import subprocess
    import sys
    from pathlib import Path

    code = (
        "from career_evidence_graph import application_single_binding, application_worker_browser; "
        "from career_evidence_graph.loaded_code import "
        "load_controller_modules, loaded_runtime_revision; "
        "load_controller_modules(); "
        "print(loaded_runtime_revision('controller')); "
        "print(loaded_runtime_revision('worker'))"
    )
    source = str(Path(application_worker_browser.__file__).parents[1])
    results = [
        subprocess.check_output(
            [sys.executable, "-s", "-B", "-c", code],
            env={**os.environ, "PYTHONPATH": source, "PYTHONHASHSEED": str(seed)},
            text=True,
            timeout=10,
        )
        for seed in (1, 2, 3)
    ]
    assert len(set(results)) == 1
    assert "None" not in results[0]


def test_measurement_session_id_is_not_a_code_revision(monkeypatch):
    from career_evidence_graph import loaded_code, worker_measurement

    original = loaded_code.loaded_runtime_revision("worker")
    monkeypatch.setattr(worker_measurement, "_CLOCK", "Synthetic new measurement session")
    assert loaded_code.loaded_runtime_revision("worker") == original


def test_actual_callable_default_replacement_changes_loaded_controller_identity(monkeypatch):
    from career_evidence_graph import application_match, loaded_code

    loaded_code.load_controller_modules()
    original = loaded_code.loaded_runtime_revision("controller")
    function = application_match.analyze_job
    monkeypatch.setattr(
        function,
        "__kwdefaults__",
        {
            **function.__kwdefaults__,
            "runner": lambda *_args, **_kwargs: None,
        },
    )
    assert loaded_code.loaded_runtime_revision("controller") != original


def test_actual_form_selector_change_is_part_of_worker_identity(monkeypatch):
    from dataclasses import replace

    from career_evidence_graph import ats_forms, loaded_code

    original = loaded_code.loaded_runtime_revision("worker")
    monkeypatch.setitem(
        ats_forms.FORMS, "lever", replace(ats_forms.FORMS["lever"], selector="form.synthetic-other")
    )
    assert loaded_code.loaded_runtime_revision("worker") != original


def test_opaque_callable_default_fails_closed(monkeypatch):
    from career_evidence_graph import application_match, loaded_code

    loaded_code.load_controller_modules()
    assert loaded_code.loaded_runtime_revision("controller") is not None
    monkeypatch.setattr(application_match.analyze_job, "__kwdefaults__", {"runner": object()})
    assert loaded_code.loaded_runtime_revision("controller") is None


def test_callable_closure_state_is_included(monkeypatch):
    from career_evidence_graph import application_match, loaded_code

    loaded_code.load_controller_modules()

    def runner(value):
        def execute(*_args, **_kwargs):
            return value

        return execute

    monkeypatch.setattr(
        application_match.analyze_job, "__kwdefaults__", {"runner": runner("first")}
    )
    first = loaded_code.loaded_runtime_revision("controller")
    monkeypatch.setattr(
        application_match.analyze_job, "__kwdefaults__", {"runner": runner("second")}
    )
    assert first is not None and loaded_code.loaded_runtime_revision("controller") != first


def test_actual_imported_execution_alias_cannot_change_without_identity_change(monkeypatch):
    from career_evidence_graph import application_worker_browser, loaded_code

    original = loaded_code.loaded_runtime_revision("worker")
    assert original is not None
    monkeypatch.setattr(
        application_worker_browser, "require_execution", lambda *_args, **_kwargs: None
    )
    assert loaded_code.loaded_runtime_revision("worker") != original


def test_actual_model_validation_policy_change_is_visible(monkeypatch):
    import pytest
    from pydantic import ValidationError

    from career_evidence_graph import application_match, loaded_code

    loaded_code.load_controller_modules()
    model = application_match._Requirement
    original = loaded_code.loaded_runtime_revision("controller")
    values = {
        "text": "Synthetic requirement",
        "importance": "required",
        "judgment": "unknown",
        "hard_condition": "true",
        "explanation": "Synthetic",
        "source_ids": [],
        "citations": [],
        "claim_scope": "unknown",
    }
    with pytest.raises(ValidationError):
        model.model_validate(values)
    try:
        model.model_config["strict"] = False
        model.model_rebuild(force=True)
        assert model.model_validate(values).hard_condition is True
        assert loaded_code.loaded_runtime_revision("controller") != original
    finally:
        model.model_config["strict"] = True
        model.model_rebuild(force=True)


def test_actual_compiled_validator_is_not_replaced_by_declared_schema_identity(monkeypatch):
    from pydantic_core import SchemaValidator, core_schema

    from career_evidence_graph import application_match, loaded_code

    loaded_code.load_controller_modules()
    model = application_match._Requirement
    original = loaded_code.loaded_runtime_revision("controller")
    declared = model.__pydantic_core_schema__

    def substitute_confirmed_boolean(value, _info):
        return {**value, "hard_condition": True}

    changed = core_schema.with_info_before_validator_function(
        substitute_confirmed_boolean, declared
    )
    monkeypatch.setattr(model, "__pydantic_validator__", SchemaValidator(changed))
    values = {
        "text": "Synthetic requirement",
        "importance": "required",
        "judgment": "unknown",
        "hard_condition": "not a boolean",
        "explanation": "Synthetic",
        "source_ids": [],
        "citations": [],
        "claim_scope": "unknown",
    }
    assert model.model_validate(values).hard_condition is True
    assert model.model_config["strict"] is True and model.__pydantic_core_schema__ is declared
    assert original is not None and loaded_code.loaded_runtime_revision("controller") != original


def test_opaque_field_metadata_stays_unknown(monkeypatch):
    from career_evidence_graph import application_match, loaded_code

    loaded_code.load_controller_modules()
    field = application_match._Requirement.model_fields["text"]
    monkeypatch.setattr(field, "metadata", [object()])
    assert loaded_code.loaded_runtime_revision("controller") is None


def test_draft_validation_scope_is_runtime_state_not_a_code_revision():
    from career_evidence_graph import application_resume, loaded_code

    loaded_code.load_controller_modules()
    original = loaded_code.loaded_runtime_revision("controller")
    assert original is not None
    token = application_resume._DRAFT_VALIDATION.set(
        {"validated": {("synthetic", "draft"): object()}, "visiting": set()}
    )
    try:
        assert loaded_code.loaded_runtime_revision("controller") == original
    finally:
        application_resume._DRAFT_VALIDATION.reset(token)
    assert loaded_code.loaded_runtime_revision("controller") == original


def test_active_match_refresh_operations_do_not_change_loaded_code_identity():
    from career_evidence_graph import application_match_refresh, loaded_code

    loaded_code.load_controller_modules()
    before = loaded_code.loaded_runtime_revision("controller")
    assert before is not None
    operation = ("synthetic-runtime-scope", "synthetic-request")
    application_match_refresh._ACTIVE_CALLBACKS.add(operation)
    try:
        assert loaded_code.loaded_runtime_revision("controller") == before
    finally:
        application_match_refresh._ACTIVE_CALLBACKS.discard(operation)
