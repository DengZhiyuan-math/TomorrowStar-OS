"""Independent CLI saves merge current settings before releasing their write lock."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from career_evidence_graph import career_portal

CHILD = r"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from career_evidence_graph import career_portal as portal
barrier, tag = Path(sys.argv[2]), sys.argv[3]
real_create, real_read = portal.create_server, portal._read_local_configuration
created = False

def wait_for(path):
    deadline = time.monotonic() + 15
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Synthetic parent synchronization timed out')
        time.sleep(0.005)

def create_server(*args, **kwargs):
    global created
    server = real_create(*args, **kwargs)
    (barrier / ('port-' + tag)).write_text(str(server.server_port))
    created = True
    def serve_forever():
        (barrier / ('served-' + tag)).write_text('ready')
        if tag == 'one':
            wait_for(barrier / 'finish-one')
        raise KeyboardInterrupt
    server.serve_forever = serve_forever
    return server

def read_configuration():
    old = real_read()
    if created:
        (barrier / ('read-' + tag)).write_text(str(os.getpid()))
        if tag == 'one':
            wait_for(barrier / 'release-one')
    return old

portal.create_server, portal._read_local_configuration = create_server, read_configuration
sys.exit(portal.main(json.loads(sys.argv[4])))
"""


def wait_for(path, *, timeout=10):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() > deadline:
            raise AssertionError(f"Synthetic CLI did not reach {path.name}")
        time.sleep(0.005)


@pytest.mark.parametrize("explicit_roots", [False, True])
def test_independent_cli_saves_preserve_both_selected_settings(tmp_path, explicit_roots):
    apps, career = tmp_path / "applications", tmp_path / "career"
    apps.mkdir()
    career.mkdir()
    subprocess.run(["/usr/bin/git", "init", "--quiet", str(career)], check=True)
    (career / ".gitignore").write_text(".career-evidence/raw/\n")
    home = tmp_path / "home"
    config = home / "Library/Application Support/TomorrowStar/portal.json"
    config.parent.mkdir(parents=True)
    old = {
        "applications": str(apps),
        "career_workspace": str(career),
        "cover_letter_template": str(tmp_path / "old-letter.tex"),
        "career_library_manifest": str(tmp_path / "old-library.json"),
        "application_processed_label": "synthetic-preserve-mail",
        "preparation_root": str(tmp_path / "materials"),
        "extension": {"preserve": ["synthetic", 42]},
    }
    selected = {
        "cover_letter_template": str(tmp_path / "new-letter.tex"),
        "career_library_manifest": str(tmp_path / "new-library.json"),
    }
    for value in [*selected.values(), old["cover_letter_template"], old["career_library_manifest"]]:
        Path(value).write_text("{}" if value.endswith(".json") else "Synthetic template\n")
    config.write_text(json.dumps(old))
    barrier = tmp_path / "barrier"
    barrier.mkdir()
    environment = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    children = []

    def start(tag, field, value):
        arguments = ["--" + field.replace("_", "-"), value, "--port", "0", "--save-config"]
        if explicit_roots:
            arguments += ["--applications", str(apps), "--career-workspace", str(career)]
        child = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-c",
                CHILD,
                str(Path(career_portal.__file__).parents[1]),
                str(barrier),
                tag,
                json.dumps(arguments),
            ],
            cwd=tmp_path,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(child)
        return child

    try:
        first = start("one", "cover_letter_template", selected["cover_letter_template"])
        wait_for(barrier / "read-one")
        second = start("two", "career_library_manifest", selected["career_library_manifest"])
        wait_for(barrier / "port-two")
        # Before serialization this fixes read/read/write/write. With the lock,
        # the second writer waits here without entering its save-time read.
        deadline = time.monotonic() + 1
        while not (barrier / "read-two").exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        (barrier / "release-one").touch()
        wait_for(barrier / "served-one")
        stdout, stderr = second.communicate(timeout=10)
        assert second.returncode == 0, stdout + stderr
        # A bound, serving first CLI must not retain the configuration lock.
        assert first.poll() is None
        (barrier / "finish-one").touch()
        stdout, stderr = first.communicate(timeout=10)
        assert first.returncode == 0, stdout + stderr
        ports = [(barrier / f"port-{tag}").read_text() for tag in ("one", "two")]
        pids = [(barrier / f"read-{tag}").read_text() for tag in ("one", "two")]
        assert len(set(ports)) == len(set(pids)) == 2
        assert json.loads(config.read_text()) == old | selected
    finally:
        (barrier / "release-one").touch()
        (barrier / "finish-one").touch()
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
