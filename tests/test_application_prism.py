"""Local LaTeX review binds source bytes, including existing Git projects."""

import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from career_evidence_graph.career_portal_data import PortalDataError


def test_existing_latex_binding_tracks_source_changes_without_modifying_the_project(tmp_path):
    from career_evidence_graph.application_prism import source_snapshot

    project = tmp_path / "review"
    project.mkdir()
    (project / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Synthetic\end{document}"
    )
    before = {path: path.read_bytes() for path in project.iterdir()}
    first = source_snapshot(project, "main.tex")
    assert first["project_root"] == str(project)
    assert first["main"] == "main.tex"
    assert {path: path.read_bytes() for path in project.iterdir()} == before
    (project / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Changed\end{document}"
    )
    assert source_snapshot(project, "main.tex")["source_revision"] != first["source_revision"]


def test_generated_project_under_git_parent_keeps_explicit_policy_through_archiving(tmp_path):
    from career_evidence_graph.application_prism import (
        archive_sources,
        refresh_source_snapshot,
        source_snapshot,
        validate_archive,
    )

    project = tmp_path / "review"
    project.mkdir()
    raw = b"Synthetic standalone source"
    (project / "main.tex").write_bytes(raw)
    strict = source_snapshot(project, "main.tex")
    generated = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    assert generated["source_revision"] != strict["source_revision"]
    (tmp_path / ".git").mkdir()
    with pytest.raises(PortalDataError):
        source_snapshot(project, "main.tex")
    assert refresh_source_snapshot(generated) == generated
    assert validate_archive(archive_sources(generated), generated) == raw


def test_generated_policy_survives_review_capture_with_git_ancestor(tmp_path):
    from test_standalone_prism_review import FakePrism

    from career_evidence_graph.application_prism import source_snapshot
    from career_evidence_graph.application_prism_review import PrismReviewStore

    (tmp_path / ".git").mkdir()
    project = tmp_path / "generated" / "project"
    project.mkdir(parents=True)
    (project / "main.tex").write_text("Synthetic source")
    binding = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    client = FakePrism()
    store = PrismReviewStore(tmp_path / "receipts", client=client, binding_provider=lambda: binding)
    assert store.binding() == binding
    captured = store.capture(binding["source_revision"])
    assert client.calls == ["compile"]
    assert store.version(captured["latest"]["id"])["binding"] == binding


@pytest.mark.parametrize("location", [".git", "nested/.git", "build/.git", ".prism-local/.git"])
@pytest.mark.parametrize("kind", ["directory", "file", "broken-link"])
def test_generated_project_still_rejects_git_metadata_inside_its_tree(tmp_path, location, kind):
    from career_evidence_graph.application_prism import source_snapshot

    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source")
    metadata = project / location
    metadata.parent.mkdir(parents=True, exist_ok=True)
    if kind == "directory":
        metadata.mkdir()
    elif kind == "file":
        metadata.write_text("gitdir: elsewhere")
    else:
        metadata.symlink_to(tmp_path / "missing-git")
    if location == ".git" and kind == "directory":
        binding = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
        assert set(binding["files"]) == {"main.tex"}
    else:
        with pytest.raises(PortalDataError):
            source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")


def test_generated_archive_policy_cannot_be_dropped_or_changed(tmp_path):
    from career_evidence_graph.application_prism import (
        archive_sources,
        refresh_source_snapshot,
        source_snapshot,
        validate_archive,
    )

    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source")
    binding = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    archive = archive_sources(binding)
    stripped = {key: value for key, value in binding.items() if key != "source_policy"}
    for changed in (stripped, binding | {"source_policy": "unknown"}):
        with pytest.raises(ValueError):
            validate_archive(archive, changed)
    with pytest.raises(PortalDataError):
        refresh_source_snapshot(binding | {"source_policy": "unknown"})


@pytest.mark.parametrize("change", [False, True])
def test_generated_project_keeps_source_guard_during_synthetic_compile(
    tmp_path, monkeypatch, change
):
    from career_evidence_graph.application_prism import PrismClient, source_snapshot

    (tmp_path / ".git").mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source")
    binding = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")

    def on_build():
        if change:
            (project / "main.tex").write_text("Changed during synthetic build")

    with compiling_editor(project, monkeypatch, on_build=on_build):
        if change:
            with pytest.raises(PortalDataError) as error:
                PrismClient().compile(binding)
            assert error.value.code == "resume_export_needs_recheck"
        else:
            result = PrismClient().compile(binding)
            assert result["source_revision"] == binding["source_revision"]


@pytest.mark.parametrize(
    "damage", ["linked-root", "linked-source", "linked-output", "ignored-link"]
)
def test_generated_policy_does_not_admit_redirected_projects(tmp_path, damage):
    from career_evidence_graph.application_prism import source_snapshot

    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source")
    if damage == "linked-root":
        alias = tmp_path / "alias"
        alias.symlink_to(project, target_is_directory=True)
        project = alias
    elif damage == "linked-source":
        (project / "main.tex").unlink()
        (project / "main.tex").symlink_to(tmp_path / "outside.tex")
    else:
        directory = project / ("build" if damage == "linked-output" else ".prism-local")
        directory.mkdir()
        (directory / "linked").symlink_to(tmp_path / "outside")
    with pytest.raises(PortalDataError):
        source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")


def test_generated_policy_connects_to_existing_git_sync_without_changing_it(tmp_path, monkeypatch):
    from career_evidence_graph.application_prism import PrismClient, source_snapshot

    (tmp_path / ".git").mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source")
    binding = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    with compiling_editor(project, monkeypatch, sync={"own": True, "enabled": True}) as calls:
        assert PrismClient().open(binding)
    assert [call[0] for call in calls] == ["GET", "GET"]


@pytest.mark.parametrize(
    "damage", ["git", "linked-root", "linked-source", "linked-output", "outside-main"]
)
def test_source_binding_refuses_git_or_redirects_before_any_service_request(tmp_path, damage):
    from career_evidence_graph.application_prism import source_snapshot

    project = tmp_path / "review"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source")
    main = "main.tex"
    if damage == "git":
        (tmp_path / ".git").mkdir()
    elif damage == "linked-root":
        alias = tmp_path / "alias"
        alias.symlink_to(project, target_is_directory=True)
        project = alias
    elif damage == "linked-source":
        (project / "main.tex").unlink()
        (project / "main.tex").symlink_to(tmp_path / "outside.tex")
    elif damage == "linked-output":
        (project / "build").mkdir()
        (project / "build/main.pdf").symlink_to(tmp_path / "outside.pdf")
    else:
        main = "../outside.tex"
    with pytest.raises(PortalDataError):
        source_snapshot(project, main)


def test_existing_editor_is_identity_checked_without_starting_or_opening_home_projects(
    tmp_path, monkeypatch
):
    from career_evidence_graph.application_prism import PrismClient, project_key, source_snapshot

    project = tmp_path / "review"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source")
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requests.append(self.path)
            payload = (
                {
                    "app": "prism-local",
                    "root": str(project),
                    "project_key": project_key(project),
                    "pid": 42,
                    "token": "synthetic-token",
                }
                if self.path == "/api/ping"
                else {"sync": {"own": False, "enabled": False}}
            )
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        monkeypatch.setenv("TOMORROWSTAR_PRISM_URL", url)
        assert PrismClient().open(source_snapshot(project, "main.tex")) == url + "/"
        assert requests == ["/api/ping", "/api/tree"]
        assert not list(project.glob(".git*"))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@contextmanager
def compiling_editor(
    project,
    monkeypatch,
    *,
    on_build=lambda: None,
    build_result=None,
    disconnect_build=False,
    pdf_bytes=None,
    sync=None,
):
    from career_evidence_graph.application_prism import project_key

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, payload):
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/pdf" if isinstance(payload, bytes) else "application/json",
            )
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            calls.append(("GET", self.path))
            if self.path == "/api/ping":
                self.send(
                    {
                        "app": "prism-local",
                        "root": str(project),
                        "project_key": project_key(project),
                    }
                )
            elif self.path == "/api/tree":
                self.send({"sync": sync or {"own": False, "enabled": False}})
            elif self.path.startswith("/api/file?"):
                self.send({"path": "main.tex", "content": (project / "main.tex").read_text()})
            elif self.path.startswith("/pdf?"):
                self.send(
                    pdf_bytes
                    if pdf_bytes is not None
                    else (
                        Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
                    ).read_bytes()
                )
            else:
                self.send_error(404)

        def do_POST(self):
            assert self.headers["X-Prism-Local"] == "1"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(("POST", self.path, payload))
            assert self.path == "/api/build"
            on_build()
            if disconnect_build:
                self.close_connection = True
                return
            self.send(
                {
                    "busy": False,
                    "exit": 0,
                    "cancelled": False,
                    "timed_out": False,
                    "main": "main.tex",
                    "pdf_mtime": 1234,
                    "pdf_updated": True,
                    "engine": "synthetic",
                    "builder": "synthetic",
                }
                | (build_result or {})
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("TOMORROWSTAR_PRISM_URL", f"http://127.0.0.1:{server.server_port}")
    try:
        yield calls
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_compile_uses_the_bound_source_and_strict_build_without_html_or_model(
    tmp_path, monkeypatch
):
    from career_evidence_graph.application_prism import PrismClient, source_snapshot

    project = tmp_path / "review"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic LaTeX source")
    binding = source_snapshot(project, "main.tex")
    with compiling_editor(project, monkeypatch) as calls:
        result = PrismClient().compile(binding)
    assert result["pdf"].startswith(b"%PDF-")
    assert result["source_revision"] == binding["source_revision"]
    assert [call for call in calls if call[0] == "POST"] == [
        ("POST", "/api/build", {"mode": "strict", "clean": False, "active": "main.tex"})
    ]
    assert not list(project.glob("*.html"))


def test_source_change_during_strict_build_cannot_be_accepted(tmp_path, monkeypatch):
    from career_evidence_graph.application_prism import PrismClient, source_snapshot

    project = tmp_path / "review"
    project.mkdir()
    main = project / "main.tex"
    main.write_text("Reviewed source")
    binding = source_snapshot(project, "main.tex")
    with (
        compiling_editor(project, monkeypatch, on_build=lambda: main.write_text("Changed source")),
        pytest.raises(PortalDataError) as error,
    ):
        PrismClient().compile(binding)
    assert error.value.code == "resume_export_needs_recheck"


def test_edit_then_undo_during_compilation_still_requires_recheck(tmp_path, monkeypatch):
    from career_evidence_graph.application_prism import PrismClient, source_snapshot

    project = tmp_path / "review"
    project.mkdir()
    main = project / "main.tex"
    main.write_text("Reviewed source")
    binding = source_snapshot(project, "main.tex")

    def edit_then_undo():
        main.write_text("Different source read during build")
        main.write_text("Reviewed source")

    with (
        compiling_editor(project, monkeypatch, on_build=edit_then_undo),
        pytest.raises(PortalDataError) as error,
    ):
        PrismClient().compile(binding)
    assert error.value.code == "resume_export_needs_recheck"


@pytest.mark.parametrize(
    "setting", ["custom-command", "shell-escape", "outside-output", "outside-input", "build-input"]
)
def test_binding_refuses_untracked_inputs_or_custom_execution(tmp_path, setting):
    from career_evidence_graph.application_prism import source_snapshot

    project = tmp_path / "review"
    project.mkdir()
    config = {"main": "main.tex", "outdir": "build", "builder": "tectonic"}
    source = r"\documentclass{article}\begin{document}Synthetic\end{document}"
    if setting == "custom-command":
        config["build"] = "arbitrary program"
    elif setting == "shell-escape":
        config["shell_escape"] = True
    elif setting == "outside-output":
        config["outdir"] = "../outside"
    elif setting == "outside-input":
        source = r"\input{../outside.tex}"
    else:
        source = r"\input{build/previous.tex}"
    (project / "prism.json").write_text(json.dumps(config))
    (project / "main.tex").write_text(source)
    with pytest.raises(PortalDataError):
        source_snapshot(project, "main.tex")


@pytest.mark.parametrize(
    "result",
    [
        {"pdf_updated": False},
        {"main": "other.tex"},
        {"cancelled": True},
        {"timed_out": True},
        {"busy": True},
        {"exit": 1},
    ],
)
def test_incomplete_or_unchanged_compilation_never_reads_an_old_pdf(tmp_path, monkeypatch, result):
    from career_evidence_graph.application_prism import PrismClient, source_snapshot

    project = tmp_path / "review"
    project.mkdir()
    (project / "main.tex").write_text("Reviewed source")
    binding = source_snapshot(project, "main.tex")
    with (
        compiling_editor(project, monkeypatch, build_result=result) as calls,
        pytest.raises(PortalDataError) as error,
    ):
        PrismClient().compile(binding)
    assert error.value.code == "resume_export_failed"
    assert not any(call[1].startswith("/pdf?") for call in calls)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8790",
        "http://example.test:8790",
        "http://127.0.0.1:8790/path",
        "http://user:secret@127.0.0.1:8790",
    ],
)
def test_service_configuration_refuses_external_or_credentialed_urls(monkeypatch, url):
    from career_evidence_graph.application_prism import PrismClient

    monkeypatch.setenv("TOMORROWSTAR_PRISM_URL", url)
    with pytest.raises(PortalDataError) as error:
        PrismClient()
    assert error.value.code == "prism_url_invalid"


def test_git_metadata_is_excluded_and_existing_git_diff_is_read_only(tmp_path, monkeypatch):
    import subprocess

    from career_evidence_graph.application_prism import (
        PrismClient,
        archive_sources,
        dependency_snapshot,
        refresh_source_snapshot,
        source_snapshot,
    )

    project = tmp_path / "project"
    project.mkdir()
    main = project / "main.tex"
    main.write_text("Original English source")

    def git(*args):
        return subprocess.run(["git", "-C", str(project), *args], check=True, capture_output=True)

    git("init", "-q")
    git("add", "main.tex")
    git(
        "-c",
        "user.name=Synthetic",
        "-c",
        "user.email=synthetic@example.invalid",
        "commit",
        "-qm",
        "Synthetic baseline",
    )
    main.write_text("Edited English source")
    (project / ".gitattributes").write_text("main.tex filter=unsafe\n")
    git("config", "filter.unsafe.clean", "touch must-not-run; cat")
    before = {
        str(p.relative_to(project)): p.read_bytes() for p in project.rglob("*") if p.is_file()
    }
    binding = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    assert set(binding["files"]) == {"main.tex", ".gitattributes"}
    assert b"Original English" not in archive_sources(binding)
    assert refresh_source_snapshot(binding) == binding
    assert set(dependency_snapshot(project, "main.tex", ["main.tex"])["files"]) == {"main.tex"}
    with compiling_editor(project, monkeypatch, sync={"own": True, "enabled": True}) as calls:
        provenance = PrismClient().edit_provenance(binding)
    assert provenance["kind"] == "prism-git-diff/v1"
    assert provenance["head"] == git("rev-parse", "HEAD").stdout.decode().strip()
    assert provenance["base"] == provenance["head"]
    assert "-Original English source" in provenance["diff"]
    assert "+Edited English source" in provenance["diff"]
    assert not provenance["truncated"]
    assert not any(call[0] == "POST" for call in calls)
    assert {
        str(p.relative_to(project)): p.read_bytes() for p in project.rglob("*") if p.is_file()
    } == before


def test_git_autocommitted_diff_is_not_misreported_as_current_changes(tmp_path, monkeypatch):
    from career_evidence_graph.application_prism import PrismClient, source_snapshot

    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text("English source")
    binding = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    with compiling_editor(project, monkeypatch) as calls:
        provenance = PrismClient().edit_provenance(binding)
    assert provenance == {"kind": "source-diff/v1", "source_revision": binding["source_revision"]}
    assert not any(call[0] == "POST" for call in calls)
