"""Local LaTeX source bindings and read-only provenance; never launch or sync."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
from difflib import unified_diff
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest

_ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def project_key(root: Path) -> str:
    """Match the local server's public project identity protocol."""
    label = (
        "".join(char if char.isalnum() or char in "-_" else "_" for char in root.name) or "project"
    )
    return label + "-" + hashlib.sha1(os.path.normcase(str(root)).encode()).hexdigest()[:10]


def _local_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or not parsed.port
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise PortalDataError("prism_url_invalid", "Prism 地址必须是本机 HTTP 服务。", 409)
    return value.rstrip("/") + "/"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise PortalDataError("prism_redirect", "Prism 服务地址已变化，请核验本机实例。", 409)


class PrismClient:
    """Reuse an existing editor; never launch Home, Git sync, agents or providers."""

    def __init__(self):
        self.url = _local_url(os.environ.get("TOMORROWSTAR_PRISM_URL", "http://127.0.0.1:8790"))
        self.http = build_opener(ProxyHandler({}), _NoRedirect())

    def configuration(self) -> dict:
        return {
            "kind": "prism-local-latex",
            "engine_sha256": _ENGINE_SHA256,
            "mode": "strict",
            "clean": False,
        }

    def _request(self, url, route, payload=None, *, pdf=False):
        address = _local_url(url) + route.lstrip("/")
        request = Request(
            address,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"X-Prism-Local": "1", "Content-Type": "application/json"},
        )
        try:
            with self.http.open(request, timeout=45 if route == "api/build" else 3) as response:
                limit = 700_000 if pdf else 2_000_000
                raw = response.read(limit + 1)
                if (
                    len(raw) > limit
                    or pdf
                    and response.headers.get_content_type() != "application/pdf"
                ):
                    raise ValueError("unexpected response")
                value = raw if pdf else json.loads(raw)
                if not pdf and not isinstance(value, dict):
                    raise ValueError("invalid service response")
                return value
        except (OSError, ValueError) as error:
            raise PortalDataError(
                "prism_unavailable", "Prism 服务暂不能核验，请保留当前源与结果。", 503
            ) from error

    def open(self, binding: dict) -> str:
        root = Path(binding["project_root"])
        refresh_source_snapshot(binding)
        key = project_key(root)
        url = self.url
        ping = self._request(url, "api/ping")
        record = None
        if ping.get("app") == "prism-home":
            state_root = Path(
                os.environ.get("PRISM_STATE_DIR")
                or str(
                    Path(os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state"))
                    / "prism-local"
                )
            )
            path = state_root / "instances" / (key + ".json")
            try:
                if (
                    any(part.is_symlink() for part in (path, *path.parents))
                    or path.stat().st_size > 16_384
                ):
                    raise ValueError("unsafe instance")
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("root") != str(root) or record.get("app") != "prism-local":
                    raise ValueError("wrong instance")
                url = _local_url(record["url"])
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise PortalDataError(
                    "prism_not_running", "请先启动独立的本地 Prism 项目，再连接审阅。", 409
                ) from error
            ping = self._request(url, "api/ping")
        if (
            ping.get("app") != "prism-local"
            or ping.get("root") != str(root)
            or ping.get("project_key") != key
            or record
            and (record.get("token") != ping.get("token") or record.get("pid") != ping.get("pid"))
        ):
            raise PortalDataError(
                "prism_identity_changed", "Prism 当前项目身份不符，请核验原服务。", 409
            )
        tree = self._request(url, "api/tree")
        sync = tree.get("sync", {})
        git_supported = binding.get("source_policy") in {
            "generated-latex-project/v1",
            "prism-dependencies/v1",
        }
        if (
            type(sync.get("own")) is not bool
            or type(sync.get("enabled")) is not bool
            or not git_supported
            and (sync["own"] or sync["enabled"])
        ):
            raise PortalDataError(
                "prism_sync_active", "此审阅入口要求独立且未启用 Git 同步的项目。", 409
            )
        return _local_url(url)

    def edit_provenance(self, binding: dict) -> dict:
        """Read HEAD-to-working-source diff, never the editor's fallback last commit.

        The archived edit baseline remains authoritative when autosync has already
        committed a change. Git is optional and its metadata is never a source input.
        """
        current = refresh_source_snapshot(binding)
        if current != binding:
            raise PortalDataError("prism_source_changed", "编辑源已变化，请保留当前稿。", 409)
        self.open(binding)
        result = {"kind": "source-diff/v1", "source_revision": binding["source_revision"]}
        root = Path(binding["project_root"])
        if not (root / ".git").is_dir():
            return result
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith("GIT_")
        }
        command = [
            "git",
            "--no-optional-locks",
            "-C",
            str(root),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
        ]

        def read(*args):
            value = subprocess.run(
                [*command, *args],
                capture_output=True,
                timeout=5,
                env=environment,
                check=True,
            )
            return value.stdout.decode("utf-8")

        try:
            head = read("rev-parse", "--verify", "HEAD").strip()
            if re.fullmatch(r"[a-f0-9]{40,64}", head) is None:
                return result
            # Even `git diff --no-ext-diff` can run clean filters. Read the
            # committed blob directly and compute text differences ourselves.
            base_source = read("cat-file", "blob", head + ":" + binding["main"])
            diff = "".join(
                unified_diff(
                    base_source.splitlines(True),
                    (root / binding["main"]).read_text(encoding="utf-8").splitlines(True),
                    fromfile="HEAD/" + binding["main"],
                    tofile=binding["main"],
                )
            )
            if read("rev-parse", "--verify", "HEAD").strip() != head:
                return result
        except (OSError, UnicodeError, subprocess.SubprocessError):
            return result
        if refresh_source_snapshot(binding) != binding:
            raise PortalDataError("prism_source_changed", "编辑源已变化，请保留当前稿。", 409)
        return result | {
            "kind": "prism-git-diff/v1",
            "base": head,
            "head": head,
            "diff_basis": "HEAD-to-working-tree",
            "diff": diff[:64_000],
            "truncated": len(diff) > 64_000,
        }

    def compile(self, binding: dict) -> dict:
        """Compile precisely the reviewed source; an uncertain request is never retried."""
        root = Path(binding["project_root"])
        before = refresh_source_snapshot(binding)
        versions = _source_versions(root, before["files"])
        if before["source_revision"] != binding["source_revision"]:
            raise PortalDataError("prism_source_changed", "LaTeX 源已变化，请重新审阅。", 409)
        url = self.open(binding)
        query = urlencode({"path": binding["main"]})
        source = self._request(url, "api/file?" + query)
        if source.get("path") != binding["main"] or source.get("content") != (
            root / binding["main"]
        ).read_text(encoding="utf-8"):
            raise PortalDataError("prism_source_changed", "Prism 源与本地审阅源不一致。", 409)
        try:
            result = self._request(
                url, "api/build", {"mode": "strict", "clean": False, "active": binding["main"]}
            )
            if (
                result.get("busy") is not False
                or type(result.get("exit")) is not int
                or result["exit"] != 0
                or result.get("cancelled") is not False
                or result.get("timed_out") is not False
                or result.get("main") != binding["main"]
                or result.get("pdf_updated") is not True
                or not isinstance(result.get("pdf_mtime"), (int, float))
            ):
                raise PortalDataError(
                    "resume_export_failed", "Prism 严格编译未完成，请核验诊断后明确重试。", 503
                )
            pdf = self._request(url, "pdf?" + urlencode({"main": binding["main"]}), pdf=True)
            after = refresh_source_snapshot(binding)
            remote = self._request(url, "api/file?" + query)
            if (
                after != before
                or remote.get("content") != source["content"]
                or _source_versions(root, before["files"]) != versions
            ):
                raise PortalDataError(
                    "resume_export_needs_recheck",
                    "编译期间 LaTeX 源已变化，请保留结果并核验。",
                    409,
                )
            return {
                "pdf": pdf,
                "source_revision": before["source_revision"],
                "build": {
                    key: result.get(key)
                    for key in ("main", "exit", "engine", "builder", "pdf_updated")
                },
            }
        except PortalDataError as error:
            if error.code in {"resume_export_failed", "resume_export_needs_recheck"}:
                raise
            raise PortalDataError(
                "resume_export_needs_recheck", "Prism 编译结果尚未核验，请保留当前尝试。", 409
            ) from error

    def read_compiled(self, binding: dict) -> dict:
        """Read one proven existing result; never request or repeat a build."""
        root = Path(binding["project_root"])
        url = self.open(binding)
        identity = self._request(url, "api/ping")
        query = urlencode({"main": binding["main"]})
        route = "api/build/result?" + query
        try:
            result = self._request(url, route)
        except PortalDataError as error:
            raise PortalDataError(
                "prism_result_unavailable",
                "当前 Prism 未提供可核验的自动编译结果，请保留源与已有 PDF。",
                409,
            ) from error
        if result.get("schema_version") != "prism-build-result/v1":
            raise PortalDataError(
                "prism_result_unavailable", "Prism 自动编译结果接口尚不支持源与 PDF 对应核验。", 409
            )
        if result.get("status") == "failed":
            raise PortalDataError("resume_export_failed", "Prism 编译失败，请保留源与旧终稿。", 409)
        try:
            if (
                result.get("status") != "complete"
                or not isinstance(result.get("id"), str)
                or not re.fullmatch(r"[a-f0-9]{32}", result["id"])
                or result.get("main") != binding["main"]
                or type(result.get("exit")) is not int
                or result["exit"] != 0
                or result.get("cancelled") is not False
                or result.get("timed_out") is not False
                or result.get("pdf_updated") is not True
                or not isinstance(result.get("files"), dict)
                or not isinstance(result.get("pdf_sha256"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", result["pdf_sha256"])
                or not isinstance(result.get("diagnostics"), list)
                or any(
                    not isinstance(row, dict) or row.get("severity") == "error"
                    for row in result["diagnostics"]
                )
            ):
                raise ValueError("incomplete build result")
            actual = dependency_snapshot(root, binding["main"], result["files"])
            if (
                actual["files"] != result["files"]
                or actual["files"][binding["main"]] != binding["files"][binding["main"]]
            ):
                raise ValueError("result inputs changed")
            identities = _source_versions(root, actual["files"])
            pdf = self._request(url, "pdf?" + query, pdf=True)
            repeated = self._request(url, route)
            current_url = self.open(actual)
            current_identity = self._request(url, "api/ping")
            if (
                hashlib.sha256(pdf).hexdigest() != result["pdf_sha256"]
                or repeated != result
                or refresh_source_snapshot(actual) != actual
                or _source_versions(root, actual["files"]) != identities
                or current_url != url
                or any(
                    current_identity.get(key) != identity.get(key)
                    for key in ("app", "root", "project_key", "token", "pid")
                )
            ):
                raise ValueError("result changed during readback")
            return {
                "pdf": pdf,
                "binding": actual,
                "build": result | {"source_revision": actual["source_revision"]},
            }
        except (OSError, ValueError, TypeError, KeyError, PortalDataError) as error:
            raise PortalDataError(
                "resume_export_needs_recheck",
                "自动编译结果与当前源尚不能对应，请保留源与旧终稿。",
                409,
            ) from error

    def apply_proofread(self, binding: dict, expected_source: str, patched_source: str) -> dict:
        """Apply a local text patch through Prism's hash-conditional editor lock."""
        if (
            not isinstance(expected_source, str)
            or not isinstance(patched_source, str)
            or not 1 <= len(patched_source.encode("utf-8")) <= 4_000_000
            or hashlib.sha256(expected_source.encode("utf-8")).hexdigest()
            != binding.get("files", {}).get(binding.get("main"))
            or refresh_source_snapshot(binding) != binding
        ):
            raise PortalDataError("prism_source_changed", "人工源已变化，请保留当前文字。", 409)
        url = self.open(binding)
        identity = self._request(url, "api/ping")
        try:
            result = self._request(
                url,
                "api/file/conditional",
                {
                    "path": binding["main"],
                    "content": patched_source,
                    "expected_sha256": binding["files"][binding["main"]],
                },
            )
        except PortalDataError as error:
            from urllib.error import HTTPError

            if isinstance(error.__cause__, HTTPError) and error.__cause__.code in {404, 405}:
                raise PortalDataError(
                    "prism_edit_unavailable", "当前 Prism 不支持安全局部写入，已保留人工原文。", 409
                ) from error
            if isinstance(error.__cause__, HTTPError) and error.__cause__.code == 409:
                raise PortalDataError(
                    "prism_source_changed", "人工源已变化，未覆盖当前文字。", 409
                ) from error
            raise PortalDataError(
                "prism_edit_needs_recheck", "局部校对写入结果尚不明确，请读取当前源核对。", 409
            ) from error
        expected = dict(binding["files"])
        expected[binding["main"]] = hashlib.sha256(patched_source.encode("utf-8")).hexdigest()
        current = refresh_source_snapshot(binding)
        current_url = self.open(current)
        current_identity = self._request(url, "api/ping")
        if (
            result.get("ok") is not True
            or result.get("sha256") != expected[binding["main"]]
            or current["files"] != expected
            or current_url != url
            or any(
                current_identity.get(key) != identity.get(key)
                for key in ("app", "root", "project_key", "token", "pid")
            )
        ):
            raise PortalDataError(
                "prism_edit_needs_recheck", "局部校对后源版本已变化，请保留全部版本核对。", 409
            )
        return current


def _source_versions(root: Path, names) -> dict:
    versions = {}
    for name in names:
        info = (root / name).stat()
        versions[name] = (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
    return versions


def _dependency_names(main, files):
    if not isinstance(main, str) or Path(main).suffix != ".tex" or isinstance(files, (str, bytes)):
        raise ValueError("invalid dependency document")
    names = list(files)
    if not 1 <= len(names) <= 512 or len(set(names)) != len(names) or main not in names:
        raise ValueError("invalid dependency set")
    for name in names:
        if (
            not isinstance(name, str)
            or not name
            or "\\" in name
            or Path(name).is_absolute()
            or any(part in {"..", ".git", "build", ".prism-local"} for part in Path(name).parts)
            or Path(name).as_posix() != name
            or name == "prism.json"
            or Path(name).suffix in {".pdf", ".aux", ".log", ".out", ".fls", ".fdb_latexmk"}
        ):
            raise ValueError("unsafe dependency name")
    return sorted(names)


def dependency_snapshot(project_root: Path, main: str, files) -> dict:
    """Hash only explicitly recorded local compiler inputs, without scanning a tree."""
    try:
        root = Path(project_root)
        if (
            not root.is_absolute()
            or not root.is_dir()
            or root.resolve(strict=True) != root
            or any(path.is_symlink() for path in (root, *root.parents))
            or os.path.lexists(root / ".git")
            and ((root / ".git").is_symlink() or not (root / ".git").is_dir())
        ):
            raise ValueError("unsafe dependency project")
        names = _dependency_names(main, files)
        hashes, total = {}, 0
        for name in names:
            path = root / name
            if (
                any(part.is_symlink() for part in (path, *path.parents))
                or not path.is_file()
                or path.stat().st_size > 4_000_000
            ):
                raise ValueError("unsafe dependency file")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_size > 4_000_000:
                    raise ValueError("unsafe dependency file")
                raw = stream.read(4_000_001)
                after = os.fstat(stream.fileno())
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if (
                len(raw) > 4_000_000
                or any(getattr(before, key) != getattr(after, key) for key in fields)
                or _source_versions(root, [name])[name]
                != tuple(getattr(after, key) for key in fields)
            ):
                raise ValueError("dependency changed during read")
            total += len(raw)
            if total > 32_000_000:
                raise ValueError("dependency bytes exceed limit")
            hashes[name] = hashlib.sha256(raw).hexdigest()
        if not (root / main).read_text(encoding="utf-8").strip():
            raise ValueError("empty main")
        policy = "prism-dependencies/v1"
        return {
            "project_root": str(root),
            "main": main,
            "files": hashes,
            "source_policy": policy,
            "source_revision": digest({"main": main, "files": hashes, "source_policy": policy}),
        }
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        raise PortalDataError(
            "prism_source_invalid", "实际编译依赖不能核验，请保留当前源与已有 PDF。", 409
        ) from error


def source_snapshot(project_root: Path, main: str, *, source_policy=None) -> dict:
    """Hash the dedicated source tree without touching it or following redirects."""
    try:
        root = Path(project_root)
        if source_policy not in {None, "generated-latex-project/v1"}:
            raise ValueError("unsupported source policy")
        if (
            not root.is_absolute()
            or not root.is_dir()
            or root.resolve(strict=True) != root
            or any(path.is_symlink() for path in (root, *root.parents))
            or not isinstance(main, str)
            or Path(main).is_absolute()
            or ".." in Path(main).parts
            or Path(main).suffix != ".tex"
        ):
            raise ValueError("unsafe source")
        git_roots = () if source_policy else (root, *root.parents)
        if any(os.path.lexists(path / ".git") for path in git_roots):
            raise PortalDataError(
                "prism_project_git",
                "当前接入仅支持独立无 Git 的简历项目，请选择专用本地目录。",
                409,
            )
        output = root / "build"
        if (
            output.is_symlink()
            or output.exists()
            and (not output.is_dir() or any(path.is_symlink() for path in output.rglob("*")))
        ):
            raise ValueError("redirected compilation output")
        config_path = root / "prism.json"
        if config_path.exists():
            if config_path.is_symlink() or config_path.stat().st_size > 16_384:
                raise ValueError("unsafe project configuration")
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if (
                not isinstance(config, dict)
                or set(config) - {"main", "outdir", "builder", "engine", "shell_escape"}
                or config.get("main", main) != main
                or config.get("outdir", "build") != "build"
                or config.get("builder", "auto") not in {"auto", "tectonic", "latexmk"}
                or config.get("engine", "pdflatex")
                not in {"pdflatex", "xelatex", "lualatex", "tectonic"}
                or config.get("shell_escape", False) is not False
            ):
                raise ValueError("unsupported project configuration")
        text = (root / main).read_text(encoding="utf-8")
        if len(Path(main).parts) != 1 or re.search(
            r"\\(?:input|include|includeonly|subfile|import|includepdf|includegraphics|bibliography|addbibresource|lstinputlisting|verbatiminput|openin|read)\b",
            text,
        ):
            raise ValueError("only standalone LaTeX sources are currently supported")
        files, total = {}, 0
        generated = {".aux", ".log", ".out", ".toc", ".fls", ".fdb_latexmk", ".synctex.gz"}
        for directory, children, names in os.walk(root, followlinks=False):
            if ".git" in children or ".git" in names:
                metadata = Path(directory) / ".git"
                if (
                    not source_policy
                    or Path(directory) != root
                    or metadata.is_symlink()
                    or not metadata.is_dir()
                ):
                    raise PortalDataError(
                        "prism_project_git", "简历项目不能包含重定向或嵌套 Git 元数据。", 409
                    )
                children.remove(".git")
            if any((Path(directory) / name).is_symlink() for name in children):
                raise ValueError("linked source directory")
            ignored = {"build", ".prism-local"}
            children[:] = sorted(name for name in children if source_policy or name not in ignored)
            ignored_directory = bool(set(Path(directory).relative_to(root).parts) & ignored)
            for name in sorted(names):
                path = Path(directory) / name
                if source_policy and path.is_symlink():
                    raise ValueError("linked project file")
                if ignored_directory:
                    continue
                relative = path.relative_to(root).as_posix()
                if (
                    path.suffix in generated
                    or name.endswith(".synctex.gz")
                    or relative == str(Path(main).with_suffix(".pdf"))
                ):
                    continue
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 4_000_000:
                    raise ValueError("unsafe source file")
                raw = path.read_bytes()
                total += len(raw)
                files[relative] = hashlib.sha256(raw).hexdigest()
                if len(files) > 512 or total > 32_000_000:
                    raise ValueError("source tree too large")
        if main not in files or not (root / main).read_text(encoding="utf-8").strip():
            raise ValueError("main source missing")
        policy = {"source_policy": source_policy} if source_policy else {}
        return {
            "project_root": str(root),
            "main": main,
            "files": files,
            "source_revision": digest({"main": main, "files": files, **policy}),
            **policy,
        }
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        raise PortalDataError(
            "prism_source_invalid", "LaTeX 项目或主文件不能核验，请选择真实专用目录。", 409
        ) from error


def refresh_source_snapshot(binding: dict) -> dict:
    """Re-read a bound project without dropping its explicit source policy."""
    if binding.get("source_policy") == "prism-dependencies/v1":
        return dependency_snapshot(Path(binding["project_root"]), binding["main"], binding["files"])
    return source_snapshot(
        Path(binding["project_root"]),
        binding["main"],
        source_policy=binding.get("source_policy"),
    )


def archive_sources(binding: dict) -> bytes:
    root = Path(binding["project_root"])
    current = refresh_source_snapshot(binding)
    if current["source_revision"] != binding["source_revision"]:
        raise PortalDataError("prism_source_changed", "LaTeX 源已变化，请重新审阅。", 409)
    archive = {
        name: base64.b64encode((root / name).read_bytes()).decode() for name in current["files"]
    }
    raw = json.dumps(archive, sort_keys=True, ensure_ascii=False).encode()
    validate_archive(raw, binding)
    return raw


def validate_archive(raw: bytes, binding: dict) -> bytes:
    policy = binding.get("source_policy")
    if policy not in {None, "generated-latex-project/v1", "prism-dependencies/v1"}:
        raise ValueError("unsupported source policy")
    if policy == "prism-dependencies/v1":
        _dependency_names(binding["main"], binding["files"])
    archive = json.loads(raw)
    if not isinstance(archive, dict) or set(archive) != set(binding["files"]):
        raise ValueError("source archive mismatch")
    for name, encoded in archive.items():
        decoded = base64.b64decode(encoded, validate=True)
        if hashlib.sha256(decoded).hexdigest() != binding["files"][name]:
            raise ValueError("source archive changed")
    revision = {"main": binding["main"], "files": binding["files"]}
    if policy:
        revision["source_policy"] = policy
    if digest(revision) != binding["source_revision"]:
        raise ValueError("source revision changed")
    return base64.b64decode(archive[binding["main"]], validate=True)
