"""Test-side guards for MC-10 real Codex runs (no production hook).

``OutboundTap`` wraps the Adapter instance's existing ``_send``/``_request`` seams: every
frame written to the app-server is checked before it is written and recorded as
evidence; a private or over-limit frame is refused before it leaves the process.
``InboundTap`` records frames the reader receives. Every row carries a monotonic ``t``.
``assert_isolated_codex_home`` checks a Codex home by entry names only; it never reads
file contents. ``prepare_case_dir`` and the C0 marker keep zero-cost failures from
consuming a case and keep later cases behind a passed C0.
"""

import hashlib
import json
import re
import subprocess
import threading
import time
from pathlib import Path

from career_evidence_graph.application_codex_assist import CodexAdapter

ALLOWED_JOB = "jobs.lever.co/synthetic-1"
_USER_PATH = re.compile(r"/Users/[^\s\"'\\]*")
_URL_HOST = re.compile(r"\b[a-z][a-z0-9+.-]*://([^/\s\"'\\?#:]+)((?:/[^/\s\"'\\?#]*)?)", re.I)
_TLDS = "com|net|org|io|co|ch|ai|de|uk|us|eu|fr|edu|gov|dev|info|biz|cn|jp"
_BARE_HOST = re.compile(
    rf"(?<![\w./@-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:{_TLDS}))((?:/[^/\s\"'\\?#]*)?)"
    r"(?![\w-])",
    re.I,
)
_EMAIL_HOST = re.compile(r"@((?:[a-z0-9-]+\.)+[a-z]{2,})\b", re.I)
_RESERVED = (".invalid", ".test", ".example", ".localhost")
_LOOPBACK = {"127.0.0.1", "localhost", "[::1]", "::1"}
# Context the user's own Codex home would add to every model turn.
_USER_CONTEXT = ("AGENTS.md", "skills", "memories", "rules", ".agents")
# Codex installs its bundled system skills into $CODEX_HOME/skills/.system at startup.
_BUNDLED_SKILLS = {".system"}
_INBOUND_FULL = ("turn/", "item/", "thread/", "mcpServer", "error", "serverRequest/")


def assert_isolated_codex_home(home):
    """Return the resolved home once it is a separate, context-free Codex HOME."""
    home = Path(home)
    assert home.is_absolute(), "Codex home must be an absolute path"
    assert home.resolve() != Path.home().resolve(), "Codex home must not be the user home"
    assert home.is_dir() and not home.is_symlink(), "Codex home must be an existing directory"
    for folder in (home, home / ".codex"):
        assert folder.resolve() != (Path.home() / ".codex").resolve(), "user ~/.codex"
        for name in _USER_CONTEXT:
            entry = folder / name
            if name == "skills" and entry.is_dir() and not entry.is_symlink():
                extra = sorted({child.name for child in entry.iterdir()} - _BUNDLED_SKILLS)
                assert not extra, f"isolated Codex home contains skills {extra}"
                continue
            assert not entry.exists() and not entry.is_symlink(), (
                f"isolated Codex home contains {name}"
            )
    return home.resolve()


def codex_home_names(home):
    """Entry names only (never contents) of the isolated home, for case evidence."""
    home = Path(home)
    names = {"home": sorted(child.name for child in home.iterdir())}
    for relative in (".codex", ".codex/skills"):
        folder = home / relative
        if folder.is_dir() and not folder.is_symlink():
            names[relative] = sorted(child.name for child in folder.iterdir())
    return names


def _turn_started(case):
    path = case / "outbound.jsonl"
    if not path.is_file():
        return False
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return any((row.get("frame") or {}).get("method") == "turn/start" for row in rows)


def prepare_case_dir(root, name, executable, home):
    """Check the CLI before claiming a case directory; reuse one only if no turn was sent."""
    from career_evidence_graph.application_codex_assist import PROTOCOL_VERSION

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    version = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"},
        check=False,
    ).stdout.strip()
    assert version == "codex-cli " + PROTOCOL_VERSION, f"Codex version {version!r} is not pinned"
    case, prior = root / name, []
    if case.exists():
        assert not _turn_started(case), f"{name} already sent turn/start: refusing a rerun"
        index = 1
        while (root / f"{name}.prior-{index}").exists():
            index += 1
        case.rename(root / f"{name}.prior-{index}")
        prior.append(f"{name}.prior-{index}")
    case.mkdir()
    digest = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    return case, {"version": version, "sha256": digest, "prior": prior}


def mark_passed(case):
    (Path(case) / "PASSED").write_text(json.dumps({"at": time.time()}) + "\n")


def c0_passed(root):
    return (Path(root) / "C0" / "PASSED").is_file()


def frame_violations(text, *, temp_root, private_roots):
    """Name every user path, private root or real host found in one serialized frame."""
    temp = str(Path(temp_root)) if temp_root is not None else None
    found = [
        "user_path:" + path
        for path in _USER_PATH.findall(text)
        if temp is None or not (path == temp or path.startswith(temp.rstrip("/") + "/"))
    ]
    found += ["private_root:" + str(root) for root in private_roots if str(root) in text]
    hosts = set()
    for pattern in (_URL_HOST, _BARE_HOST):
        for host, path in pattern.findall(text):
            hosts.add((host.lower(), path))
    hosts.update((host.lower(), "") for host in _EMAIL_HOST.findall(text))
    domains = set()
    for host, path in hosts:
        if host in _LOOPBACK or host.endswith(_RESERVED) or "." not in host:
            continue
        if host == "jobs.lever.co":
            if host + path != ALLOWED_JOB:
                domains.add(host + path)
        else:
            domains.add(host)
    return found + ["domain:" + host for host in sorted(domains)]


class OutboundTap:
    """Record and guard every frame one Adapter writes to its app-server."""

    def __init__(self, adapter, evidence, *, temp_root, private_roots, limits=None, turn_tokens=()):
        self.evidence, self.temp_root = Path(evidence), temp_root
        self.private_roots = [Path(root).resolve() for root in private_roots]
        self.limits = dict(limits or {})
        # Extra substrings refused only in model-facing turn/start frames (checkout, user name).
        self.turn_tokens = [str(token) for token in turn_tokens if str(token)]
        self.counts, self.blocked, self.violations, self.responses = {}, [], [], []
        self.failures = []
        self._lock = threading.Lock()
        send, request = adapter._send, adapter._request

        def tapped_send(run, message, **options):
            self.check(message)
            return send(run, message, **options)

        def tapped_request(run, method, params, **options):
            started = time.monotonic()
            try:
                result = request(run, method, params, **options)
            except BaseException as error:
                self.failures.append(
                    {
                        "t": time.monotonic(),
                        "method": method,
                        "error": repr(error),
                        "latency": time.monotonic() - started,
                    }
                )
                raise
            self.responses.append(
                {
                    "t": time.monotonic(),
                    "method": method,
                    "latency": time.monotonic() - started,
                    "result": json.loads(json.dumps(result)),
                }
            )
            return result

        adapter._send, adapter._request = tapped_send, tapped_request

    def check(self, message):
        text = json.dumps(message, ensure_ascii=False, allow_nan=False)
        method = message.get("method")
        reasons = frame_violations(text, temp_root=self.temp_root, private_roots=self.private_roots)
        if method == "turn/start":
            reasons += ["turn_token:" + token for token in self.turn_tokens if token in text]
        with self._lock:
            if method in self.limits and self.counts.get(method, 0) >= self.limits[method]:
                reasons = [*reasons, "limit:" + method]
            row = {"t": time.monotonic(), "method": method, "id": message.get("id")}
            if reasons:
                self.blocked.append(row | {"reasons": reasons})
                self.violations += [r for r in reasons if not r.startswith("limit:")]
                self._write(row | {"blocked": True, "reasons": reasons})
                # OSError is the Adapter's own transport-failure path: the run closes as unknown.
                raise OSError("MC-10 outbound guard refused frame: " + ", ".join(reasons))
            if method is not None:
                self.counts[method] = self.counts.get(method, 0) + 1
            self._write(row | {"frame": message})

    def _write(self, row):
        with self.evidence.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


class InboundTap:
    """Record every frame the Adapter's reader thread receives from its app-server."""

    def __init__(self, adapter, evidence):
        self.evidence, self.messages = Path(evidence), []
        self._lock = threading.Lock()

        def tapped_read(run):
            put = run.events.put_nowait

            def recorded(message):
                self.record(message)
                put(message)

            run.events.put_nowait = recorded
            return CodexAdapter._read(run)

        adapter._read = tapped_read

    def record(self, message):
        method = message.get("method")
        now = time.monotonic()
        if method is None:
            result = message.get("result")
            row = {"t": now, "id": message.get("id"), "error": message.get("error")}
            row["result_keys"] = sorted(result) if isinstance(result, dict) else None
        elif method.startswith(_INBOUND_FULL):
            row = {"t": now, **message}
        else:  # e.g. account or rate-limit notifications: name only
            row = {"t": now, "method": method, "id": message.get("id")}
        with self._lock:
            self.messages.append(json.loads(json.dumps(row)))
            with self.evidence.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
