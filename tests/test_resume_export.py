"""Export reuses an immutable reviewed draft without calling the model again."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_resume import task_resume as task_resume

from career_evidence_graph import application_resume

PDF_SAMPLE = Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"


@pytest.fixture
def export_draft(task_resume, tmp_path):
    """Use the supported imported LaTeX checkpoint for export regressions."""
    from career_evidence_graph.application_prism import source_snapshot

    store, job, sources, analysis, calls = task_resume
    inputs = {"career_source_revision": sources["revision"], "policy": "v1.0"}
    project = tmp_path / "latex-export-source"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic reviewed LaTeX source")
    binding = source_snapshot(project, "main.tex")
    draft = store.import_latex_for_task(
        job["id"], job["revision"], task_inputs=inputs, prism=binding
    )
    return store, job, draft, inputs, calls


def test_native_renderer_revision_ignores_launch_only_ctime_changes(
    export_draft, tmp_path, monkeypatch
):
    store, _, _, _, _ = export_draft
    executable = tmp_path / "google-chrome"
    executable.write_bytes(b"Synthetic executable; never run.")
    executable.chmod(0o700)
    stat = executable.stat()
    ctime = [stat.st_ctime_ns]
    original_stat = Path.stat

    def observed_stat(path, *args, **kwargs):
        if path == executable:
            return SimpleNamespace(
                st_dev=stat.st_dev,
                st_ino=stat.st_ino,
                st_size=stat.st_size,
                st_mtime_ns=stat.st_mtime_ns,
                st_ctime_ns=ctime[0],
                st_mode=stat.st_mode,
            )
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(application_resume.sys, "platform", "linux")
    monkeypatch.setattr(application_resume.shutil, "which", lambda *_: str(executable))
    monkeypatch.setattr(Path, "stat", observed_stat)
    store.exporter = application_resume.export_pdf
    before = store.export_configuration_revision()
    ctime[0] += 1_000_000_000
    assert store.export_configuration_revision() == before


@pytest.mark.parametrize(
    "change", ["version_link", "framework_binary", "version_info", "executable"]
)
def test_native_renderer_revision_detects_actual_chrome_identity_changes(
    export_draft, tmp_path, monkeypatch, change
):
    store, _, _, _, _ = export_draft
    home = tmp_path / "home"
    contents = home / "Applications/Google Chrome.app/Contents"
    executable = contents / "MacOS/Google Chrome"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"Synthetic executable; never run.")
    executable.chmod(0o700)
    versions = contents / "Frameworks/Google Chrome Framework.framework/Versions"
    for version in ("1.0", "2.0"):
        directory = versions / version
        (directory / "Resources").mkdir(parents=True)
        (directory / "Google Chrome Framework").write_bytes(b"Synthetic framework binary")
        (directory / "Resources/Info.plist").write_text("Synthetic version information")
    (versions / "Current").symlink_to("1.0")
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: (
            False
            if str(path) == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            else original_is_file(path)
        ),
    )
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(application_resume.sys, "platform", "darwin")
    monkeypatch.setattr(application_resume.shutil, "which", lambda *_: None)
    store.exporter = application_resume.export_pdf
    before = store.export_configuration_revision()
    if change == "version_link":
        (versions / "Current").unlink()
        (versions / "Current").symlink_to("2.0")
    elif change == "framework_binary":
        (versions / "1.0/Google Chrome Framework").write_bytes(
            b"Updated synthetic framework binary"
        )
    elif change == "version_info":
        (versions / "1.0/Resources/Info.plist").write_text("Updated synthetic version information")
    else:
        executable.write_bytes(b"Updated synthetic executable; never run.")
    assert store.export_configuration_revision() != before
