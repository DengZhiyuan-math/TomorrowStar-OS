"""P06 reads proven automatic build results without starting a compiler."""

import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from career_evidence_graph.application_prism import (
    PrismClient,
    archive_sources,
    dependency_snapshot,
    project_key,
    refresh_source_snapshot,
    source_snapshot,
    validate_archive,
)
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def result_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source\\input{section}\n")
    (project / "section.tex").write_text("Synthetic included section.\n")
    (project / "unrelated.txt").write_text("Not an input.\n")
    return project


@contextmanager
def result_editor(
    project,
    monkeypatch,
    *,
    mutation=None,
    missing=False,
    overrides=None,
    conditional=False,
    before_write=None,
    disconnect_write=False,
):
    pdf = b"%PDF-1.7\nsynthetic result\n%%EOF"
    snapshot = dependency_snapshot(project, "main.tex", ["main.tex", "section.tex"])
    result = {
        "schema_version": "prism-build-result/v1",
        "status": "complete",
        "id": "a" * 32,
        "main": "main.tex",
        "files": snapshot["files"],
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "exit": 0,
        "cancelled": False,
        "timed_out": False,
        "pdf_updated": True,
        "engine": "synthetic",
        "builder": "synthetic",
        "diagnostics": [],
    } | (overrides or {})
    calls = []
    identity = {
        "app": "prism-local",
        "root": str(project),
        "project_key": project_key(project),
        "token": "synthetic-token",
        "pid": 1234,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            calls.append(("POST", self.path))
            if self.path != "/api/file/conditional" or not conditional:
                self.send_error(404)
                return
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if before_write:
                before_write(project)
            path = project / payload["path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != payload["expected_sha256"]:
                self.send_error(409)
                return
            path.write_text(payload["content"])
            if disconnect_write:
                self.close_connection = True
                return
            raw = json.dumps(
                {"ok": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            calls.append(("GET", self.path))
            if self.path == "/api/ping":
                value = identity
            elif self.path == "/api/tree":
                value = {"sync": {"own": False, "enabled": False}}
            elif self.path == "/api/build/result?main=main.tex":
                if missing:
                    self.send_error(404)
                    return
                value = deepcopy(result)
            elif self.path == "/pdf?main=main.tex":
                value = pdf
                if mutation:
                    mutation(project, result, identity)
            else:
                self.send_error(404)
                return
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/pdf" if isinstance(value, bytes) else "application/json",
            )
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("TOMORROWSTAR_PRISM_URL", f"http://127.0.0.1:{server.server_port}")
    try:
        yield calls, result
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_dependency_snapshot_ignores_unrelated_files_and_archives_only_actual_inputs(
    result_project,
):
    project = result_project
    first = dependency_snapshot(project, "main.tex", ["main.tex", "section.tex"])
    archived = archive_sources(first)
    assert validate_archive(archived, first) == (project / "main.tex").read_bytes()
    (project / "unrelated.txt").write_text("Different unrelated content.")
    (project / "prism.json").write_text('{"engine":"xelatex"}')
    assert refresh_source_snapshot(first) == first
    assert archive_sources(first) == archived
    (project / "section.tex").write_text("Actual dependency changed.")
    assert refresh_source_snapshot(first)["source_revision"] != first["source_revision"]


@pytest.mark.parametrize(
    "name",
    [
        "../outside.tex",
        "/outside.tex",
        "./main.tex",
        "build/old.tex",
        ".git/config",
        "prism.json",
        "missing.tex",
        "result.pdf",
    ],
)
def test_dependency_snapshot_rejects_unsafe_or_unavailable_inputs(result_project, name):
    with pytest.raises(PortalDataError, match="实际编译依赖"):
        dependency_snapshot(result_project, "main.tex", ["main.tex", name])


def test_dependency_snapshot_rejects_symlink_without_following(result_project, tmp_path):
    (tmp_path / "external.tex").write_text("External")
    (result_project / "linked.tex").symlink_to(tmp_path / "external.tex")
    with pytest.raises(PortalDataError):
        dependency_snapshot(result_project, "main.tex", ["main.tex", "linked.tex"])


def test_read_compiled_uses_actual_inputs_and_performs_only_get(result_project, monkeypatch):
    project = result_project
    initial = dependency_snapshot(project, "main.tex", ["main.tex"])
    with result_editor(project, monkeypatch) as (calls, receipt):
        result = PrismClient().read_compiled(initial)
    assert result["binding"]["files"] == receipt["files"]
    assert result["build"]["source_revision"] == result["binding"]["source_revision"]
    assert hashlib.sha256(result["pdf"]).hexdigest() == receipt["pdf_sha256"]
    assert all(method == "GET" for method, _ in calls)
    assert not list(project.glob("build"))


def test_old_snapshot_semantics_remain_unchanged(tmp_path):
    (tmp_path / "main.tex").write_text("Synthetic standalone source")
    (tmp_path / "unrelated.txt").write_text("one")
    before = source_snapshot(tmp_path, "main.tex")
    (tmp_path / "unrelated.txt").write_text("two")
    assert source_snapshot(tmp_path, "main.tex")["source_revision"] != before["source_revision"]


@pytest.mark.parametrize("overrides,missing", [({}, True), ({"schema_version": "old"}, False)])
def test_missing_result_capability_never_falls_back_to_build(
    result_project, monkeypatch, overrides, missing
):
    binding = dependency_snapshot(result_project, "main.tex", ["main.tex"])
    with (
        result_editor(result_project, monkeypatch, missing=missing, overrides=overrides) as (
            calls,
            _,
        ),
        pytest.raises(PortalDataError) as error,
    ):
        PrismClient().read_compiled(binding)
    assert error.value.code == "prism_result_unavailable"
    assert all(method == "GET" for method, _ in calls)
    assert not any(path.startswith("/pdf?") for _, path in calls)


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"status": "failed"}, "resume_export_failed"),
        ({"status": "building"}, "resume_export_needs_recheck"),
        ({"status": "unknown"}, "resume_export_needs_recheck"),
        ({"exit": True}, "resume_export_needs_recheck"),
        ({"cancelled": True}, "resume_export_needs_recheck"),
        ({"timed_out": True}, "resume_export_needs_recheck"),
        ({"main": "other.tex"}, "resume_export_needs_recheck"),
        ({"files": {"main.tex": "0" * 64}}, "resume_export_needs_recheck"),
        ({"pdf_sha256": "0" * 64}, "resume_export_needs_recheck"),
        (
            {"diagnostics": [{"severity": "error", "message": "tool failed"}]},
            "resume_export_needs_recheck",
        ),
        ({"diagnostics": None}, "resume_export_needs_recheck"),
    ],
)
def test_unproven_result_is_not_adopted(result_project, monkeypatch, overrides, code):
    binding = dependency_snapshot(result_project, "main.tex", ["main.tex"])
    with (
        result_editor(result_project, monkeypatch, overrides=overrides) as (calls, _),
        pytest.raises(PortalDataError) as error,
    ):
        PrismClient().read_compiled(binding)
    assert error.value.code == code
    assert all(method == "GET" for method, _ in calls)


@pytest.mark.parametrize("damage", ["dependency", "undo", "receipt", "identity"])
def test_change_during_readback_preserves_existing_files(result_project, monkeypatch, damage):
    project = result_project
    binding = dependency_snapshot(project, "main.tex", ["main.tex"])

    def mutate(root, receipt, identity):
        if damage in {"dependency", "undo"}:
            path = root / "section.tex"
            original = path.read_bytes()
            path.write_text("Changed during readback")
            if damage == "undo":
                path.write_bytes(original)
        elif damage == "receipt":
            receipt["id"] = "b" * 32
        else:
            identity["token"] = "replacement-instance"

    with (
        result_editor(project, monkeypatch, mutation=mutate) as (calls, _),
        pytest.raises(PortalDataError) as error,
    ):
        PrismClient().read_compiled(binding)
    assert error.value.code == "resume_export_needs_recheck"
    assert all(method == "GET" for method, _ in calls)


def test_unrelated_edit_during_readback_does_not_revoke_result(result_project, monkeypatch):
    binding = dependency_snapshot(result_project, "main.tex", ["main.tex"])
    with result_editor(
        result_project,
        monkeypatch,
        mutation=lambda root, *_: (root / "unrelated.txt").write_text("Changed"),
    ):
        assert PrismClient().read_compiled(binding)["pdf"].startswith(b"%PDF-")


def test_proofread_patch_uses_hash_conditional_endpoint_without_build(result_project, monkeypatch):
    project = result_project
    binding = dependency_snapshot(project, "main.tex", ["main.tex", "section.tex"])
    original = (project / "main.tex").read_text()
    patched = original.replace("Synthetic source", "Synthetic corrected source")
    with result_editor(project, monkeypatch, conditional=True) as (calls, _):
        result = PrismClient().apply_proofread(binding, original, patched)
    assert (project / "main.tex").read_text() == patched
    assert refresh_source_snapshot(result) == result
    assert [path for method, path in calls if method == "POST"] == ["/api/file/conditional"]
    assert result["files"]["section.tex"] == binding["files"]["section.tex"]


def test_old_prism_does_not_receive_unguarded_proofread_write(result_project, monkeypatch):
    binding = dependency_snapshot(result_project, "main.tex", ["main.tex"])
    original = (result_project / "main.tex").read_text()
    with (
        result_editor(result_project, monkeypatch) as (calls, _),
        pytest.raises(PortalDataError) as error,
    ):
        PrismClient().apply_proofread(binding, original, original + "Corrected")
    assert error.value.code == "prism_edit_unavailable"
    assert (result_project / "main.tex").read_text() == original
    assert [path for method, path in calls if method == "POST"] == ["/api/file/conditional"]


def test_simultaneous_editor_save_wins_over_proofread_patch(result_project, monkeypatch):
    binding = dependency_snapshot(result_project, "main.tex", ["main.tex"])
    original = (result_project / "main.tex").read_text()
    with (
        result_editor(
            result_project,
            monkeypatch,
            conditional=True,
            before_write=lambda root: (root / "main.tex").write_text("New manual text"),
        ),
        pytest.raises(PortalDataError) as error,
    ):
        PrismClient().apply_proofread(binding, original, original + "Corrected")
    assert error.value.code == "prism_source_changed"
    assert (result_project / "main.tex").read_text() == "New manual text"


def test_unknown_conditional_write_is_never_repeated(result_project, monkeypatch):
    binding = dependency_snapshot(result_project, "main.tex", ["main.tex"])
    original = (result_project / "main.tex").read_text()
    with (
        result_editor(result_project, monkeypatch, conditional=True, disconnect_write=True) as (
            calls,
            _,
        ),
        pytest.raises(PortalDataError) as error,
    ):
        PrismClient().apply_proofread(binding, original, original + "Corrected")
    assert error.value.code == "prism_edit_needs_recheck"
    assert (result_project / "main.tex").read_text() == original + "Corrected"
    assert [path for method, path in calls if method == "POST"] == ["/api/file/conditional"]


def test_conditional_write_retains_generated_source_policy_with_configuration(
    result_project, monkeypatch
):
    (result_project / "main.tex").write_text("English before")
    (result_project / "prism.json").write_text('{"main":"main.tex","shell_escape":false}')
    binding = source_snapshot(
        result_project, "main.tex", source_policy="generated-latex-project/v1"
    )
    before_config = (result_project / "prism.json").read_bytes()
    with result_editor(result_project, monkeypatch, conditional=True):
        result = PrismClient().apply_proofread(binding, "English before", "English after")
    assert result["source_policy"] == binding["source_policy"]
    assert result == refresh_source_snapshot(binding)
    assert (result_project / "prism.json").read_bytes() == before_config
