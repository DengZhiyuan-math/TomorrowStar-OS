"""Startup failure and private configuration tests without real config writes."""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

import career_evidence_graph.career_portal as portal_module


class StartupServer(AbstractContextManager):
    server_port = 8765

    def __init__(self) -> None:
        self.closed = False
        self.served = False

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def serve_forever(self) -> None:
        self.served = True
        raise KeyboardInterrupt


@pytest.mark.parametrize(
    "content",
    [None, "{", "[]", "null", "{}", '{"applications": 123, "career_workspace": "synthetic"}'],
)
def test_missing_or_invalid_config_fails_safely_before_server_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    content: str | None,
) -> None:
    config = tmp_path / "synthetic-config.json"
    if content is not None:
        config.write_text(content, encoding="utf-8")
    monkeypatch.setattr(portal_module, "_CONFIG", config)

    def unexpected_server(*_: object, **__: object) -> None:
        pytest.fail("Invalid configuration must fail before binding the local server")

    monkeypatch.setattr(portal_module, "create_server", unexpected_server)
    assert portal_module.main([]) == 2
    captured = capsys.readouterr()
    assert "Unable to start" in captured.err
    assert "Traceback" not in captured.err
    assert str(config) not in captured.err


@pytest.mark.parametrize("argument", ["--applications", "--career-workspace"])
def test_only_one_private_path_is_a_clear_usage_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argument: str,
) -> None:
    monkeypatch.setattr(portal_module, "_CONFIG", tmp_path / "missing.json")
    with pytest.raises(SystemExit) as rejected:
        portal_module.main([argument, str(tmp_path / "synthetic-private-path")])
    assert rejected.value.code == 2
    assert "Supply both" in capsys.readouterr().err


@pytest.mark.parametrize("port", [-1, 65536])
def test_out_of_range_port_is_rejected_before_binding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], port: int
) -> None:
    with pytest.raises(ValueError, match="port"):
        portal_module.create_server(tmp_path, tmp_path, port=port)
    assert (
        portal_module.main(
            [
                "--applications",
                str(tmp_path),
                "--career-workspace",
                str(tmp_path),
                "--port",
                str(port),
            ]
        )
        == 2
    )
    assert "Traceback" not in capsys.readouterr().err


@pytest.mark.parametrize("use_library", [False, True])
def test_save_and_load_config_use_selected_external_path_and_close_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, use_library: bool
) -> None:
    config = tmp_path / "local-settings" / "portal.json"
    applications = tmp_path / "synthetic-applications"
    career = tmp_path / "synthetic-career"
    applications.mkdir()
    career.mkdir()
    monkeypatch.setattr(portal_module, "_CONFIG", config)
    created: list[StartupServer] = []
    selected: list[tuple[Path, Path]] = []
    manifest = tmp_path / "synthetic-career-library.json" if use_library else None

    def start(
        applications: Path,
        career_workspace: Path,
        *,
        port: int,
        write_admission_policy: str,
        career_library_manifest: Path | None = None,
    ) -> StartupServer:
        assert write_admission_policy == "development"
        assert career_library_manifest == manifest
        selected.append((applications, career_workspace))
        server = StartupServer()
        created.append(server)
        return server

    monkeypatch.setattr(portal_module, "create_server", start)
    assert (
        portal_module.main(
            [
                "--applications",
                str(applications),
                "--career-workspace",
                str(career),
                "--save-config",
                *(["--career-library-manifest", str(manifest)] if manifest is not None else []),
            ]
        )
        == 0
    )
    assert json.loads(config.read_text()) == {
        "applications": str(applications.resolve()),
        "career_workspace": str(career.resolve()),
        **({"career_library_manifest": str(manifest)} if manifest is not None else {}),
    }
    assert config.stat().st_mode & 0o777 == 0o600
    assert not config.is_relative_to(portal_module._PUBLIC_ROOT)
    assert created[0].closed and created[0].served
    assert portal_module.main([]) == 0
    assert selected == [(applications, career), (applications.resolve(), career.resolve())]
    assert created[1].closed and created[1].served


def test_config_save_failure_closes_created_server_without_overwriting_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "existing-synthetic-file"
    target.write_bytes(b"preserve this synthetic file")
    config = tmp_path / "portal.json"
    config.symlink_to(target)
    monkeypatch.setattr(portal_module, "_CONFIG", config)
    server = StartupServer()
    monkeypatch.setattr(portal_module, "create_server", lambda *args, **kwargs: server)
    assert (
        portal_module.main(
            ["--applications", str(tmp_path), "--career-workspace", str(tmp_path), "--save-config"]
        )
        == 2
    )
    assert server.closed
    assert not server.served
    assert target.read_bytes() == b"preserve this synthetic file"


def test_private_letter_template_path_round_trips_through_existing_config(tmp_path, monkeypatch):
    config = tmp_path / "portal.json"
    template = tmp_path / "private" / "letter.tex"
    monkeypatch.setattr(portal_module, "_CONFIG", config)
    selected = []

    def start(*args, **options):
        selected.append(options.get("cover_letter_template"))
        return StartupServer()

    monkeypatch.setattr(portal_module, "create_server", start)
    assert (
        portal_module.main(
            [
                "--applications",
                str(tmp_path),
                "--career-workspace",
                str(tmp_path),
                "--cover-letter-template",
                str(template),
                "--save-config",
            ]
        )
        == 0
    )
    assert json.loads(config.read_text())["cover_letter_template"] == str(template)
    assert portal_module.main([]) == 0
    assert selected == [template, template]


@pytest.mark.parametrize(
    "changed_field", ["cover_letter_template", "career_library_manifest", None]
)
def test_save_preserves_other_config_fields(tmp_path, monkeypatch, changed_field):
    config = tmp_path / "portal.json"
    saved = {
        "applications": str(tmp_path / "old-applications"),
        "career_workspace": str(tmp_path / "old-career"),
        "preparation_root": str(tmp_path / "materials"),
        "application_processed_label": "synthetic-processed",
        "archive_processed_mail": True,
        "cover_letter_template": str(tmp_path / "original-letter.tex"),
        "career_library_manifest": str(tmp_path / "original-manifest.json"),
        "extension": {"nested": ["synthetic", 42]},
    }
    config.write_text(json.dumps(saved))
    monkeypatch.setattr(portal_module, "_CONFIG", config)
    monkeypatch.setattr(portal_module, "create_server", lambda *args, **kwargs: StartupServer())
    arguments = [
        "--applications",
        str(tmp_path / "new-applications"),
        "--career-workspace",
        str(tmp_path / "new-career"),
        "--save-config",
    ]
    if changed_field:
        arguments.extend(["--" + changed_field.replace("_", "-"), str(tmp_path / "replacement")])
        saved[changed_field] = str(tmp_path / "replacement")
    saved.update(
        applications=str(tmp_path / "new-applications"),
        career_workspace=str(tmp_path / "new-career"),
    )
    assert portal_module.main(arguments) == 0
    assert json.loads(config.read_text()) == saved
    assert portal_module.main([]) == 0


@pytest.mark.parametrize(
    "content", ["{", "[]", "null", "{}", '{"applications": 123, "career_workspace": "synthetic"}']
)
def test_save_does_not_overwrite_invalid_existing_config(tmp_path, monkeypatch, content):
    config = tmp_path / "portal.json"
    config.write_text(content)
    monkeypatch.setattr(portal_module, "_CONFIG", config)
    monkeypatch.setattr(portal_module, "create_server", lambda *args, **kwargs: StartupServer())
    assert (
        portal_module.main(
            [
                "--applications",
                str(tmp_path),
                "--career-workspace",
                str(tmp_path),
                "--save-config",
            ]
        )
        == 2
    )
    assert config.read_text() == content


def test_atomic_config_replacement_failure_preserves_original_and_cleans_temporary(
    tmp_path,
    monkeypatch,
):
    from career_evidence_graph._vendor import job_apply_store

    config = tmp_path / "portal.json"
    original = json.dumps(
        {
            "applications": str(tmp_path),
            "career_workspace": str(tmp_path),
            "preparation_root": "synthetic-materials",
            "application_processed_label": "processed",
            "extension": {"keep": True},
        }
    ).encode()
    config.write_bytes(original)
    monkeypatch.setattr(portal_module, "_CONFIG", config)
    server = StartupServer()
    monkeypatch.setattr(portal_module, "create_server", lambda *args, **kwargs: server)
    attempted = []

    def fail_replace(source, destination):
        assert destination == config
        attempted.append(Path(source))
        raise OSError("Synthetic replace failure")

    monkeypatch.setattr(job_apply_store.os, "replace", fail_replace)
    assert (
        portal_module.main(
            [
                "--applications",
                str(tmp_path),
                "--career-workspace",
                str(tmp_path),
                "--cover-letter-template",
                str(tmp_path / "new-letter.tex"),
                "--save-config",
            ]
        )
        == 2
    )
    assert attempted
    assert config.read_bytes() == original
    lock = tmp_path / ".portal.json.lock"
    assert set(tmp_path.iterdir()) == {config, lock}
    with lock.open("rb") as stream:
        portal_module.fcntl.flock(
            stream.fileno(), portal_module.fcntl.LOCK_EX | portal_module.fcntl.LOCK_NB
        )
    assert server.closed and not server.served


@pytest.mark.parametrize("redirect", ["symlink", "dangling_symlink", "directory", "fifo"])
def test_config_save_refuses_redirected_or_nonregular_lock(tmp_path, monkeypatch, redirect):
    import os

    config = tmp_path / "portal.json"
    original = json.dumps({"applications": str(tmp_path), "career_workspace": str(tmp_path)})
    config.write_text(original)
    lock = tmp_path / ".portal.json.lock"
    target = tmp_path / "preserve-synthetic-document.txt"
    target.write_bytes(b"preserve synthetic document")
    if redirect in {"symlink", "dangling_symlink"}:
        if redirect == "dangling_symlink":
            target.unlink()
        lock.symlink_to(target)
    elif redirect == "directory":
        lock.mkdir()
    else:
        os.mkfifo(lock)
    server = StartupServer()
    monkeypatch.setattr(portal_module, "_CONFIG", config)
    monkeypatch.setattr(portal_module, "create_server", lambda *args, **kwargs: server)
    assert (
        portal_module.main(
            ["--applications", str(tmp_path), "--career-workspace", str(tmp_path), "--save-config"]
        )
        == 2
    )
    assert config.read_text() == original
    assert server.closed and not server.served
    if redirect == "dangling_symlink":
        assert not target.exists()
    else:
        assert target.read_bytes() == b"preserve synthetic document"
