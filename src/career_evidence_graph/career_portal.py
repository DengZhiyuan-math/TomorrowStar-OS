"""Local web workspace for existing application notes and career evidence."""

from __future__ import annotations

import argparse
import base64
import csv
import fcntl
import io
import json
import os
import re
import secrets
import stat
import sys
import webbrowser
from contextlib import contextmanager, nullcontext, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pydantic import TypeAdapter

from ._vendor.job_apply_store import atomic_write_json
from .application_automation import prepare_application_task
from .application_resume import (
    career_source_snapshot,
)
from .application_runtime import open_runtime
from .audit import ProjectInterviewPlan, inspect_project_interview_plan
from .audit.models import ArtifactFact
from .career_portal_data import (
    STATUS_LABELS,
    TRACKS,
    PortalDataError,
)
from .job_screening import screen_applications
from .loaded_code import (
    loaded_preparation_revision,
)
from .public_site import load_public_site
from .validation.hashing import record_digest as digest

_STATIC = Path(__file__).with_name("portal_static")
_PUBLIC_ROOT = Path(__file__).resolve().parents[2]
_MAX_BODY = 1_048_576
_CONFIG = Path.home() / "Library/Application Support/TomorrowStar/portal.json"


def _loaded_preparation_revision() -> str:
    """Fingerprint loaded preparation code without consulting mutable disk sources."""
    return loaded_preparation_revision()


def _csv_cell(value: object) -> str:
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


_PIPELINE_START = "请使用自动流程开始、暂停或收录邮件。"
_PIPELINE_CURRENT = "请使用当前岗位操作。"
# Route -> (named Pipeline control, accepted body keys, refusal message, status).
_PIPELINE_ROUTES = {
    "start": ("start", ({"request_id"},), _PIPELINE_START, 400),
    "capture": ("capture_mail", ({"request_id"},), _PIPELINE_START, 400),
    "pause": ("pause", (set(),), _PIPELINE_START, 400),
    "continue": ("continue_current", ({"request_id"},), _PIPELINE_CURRENT, 409),
    "skip": ("skip_current", ({"request_id"},), _PIPELINE_CURRENT, 409),
    "return": ("return_to", ({"request_id", "application_id"},), _PIPELINE_CURRENT, 409),
    "observe-result": ("observe_result", ({"request_id"},), _PIPELINE_CURRENT, 409),
    "cancel-current": (
        "cancel_current",
        ({"request_id"}, {"request_id", "task_id", "task_revision"}),
        "请使用当前岗位取消操作。",
        409,
    ),
}


def pipeline_control(pipeline, action: str, payload: dict):
    """Map one Pipeline route to its named control; a malformed body has no effect."""
    if action == "admit":
        return pipeline.admit(payload)
    method, shapes, message, status = _PIPELINE_ROUTES.get(action, (None, (), _PIPELINE_START, 400))
    if set(payload) not in shapes:
        raise PortalDataError("pipeline_request_invalid", message, status)
    return getattr(pipeline, method)(**payload)


def create_server(
    application_root: Path,
    career_workspace: Path,
    *,
    port: int = 0,
    worker_root: Path | None = None,
    handoff_root: Path | None = None,
    flow_root: Path | None = None,
    flow_analyzer=None,
    flow_match_runner=None,
    flow_resume_factory=None,
    flow_intake_factory=None,
    application_processed_label=None,
    flow_legacy_roots=(),
    information_library_root: Path | None = None,
    career_library_manifest: Path | None = None,
    cover_letter_template: Path | None = None,
    automatic_resume_author: bool = True,
    preparation_only: bool = False,
    resume_review_root: Path | None = None,
    resume_review_config: Path | None = None,
    resume_template_config: Path | None = None,
    resume_review_pdf_inspector=None,
    worker_fixtures: bool = False,
    worker_headless: bool = False,
    worker_cdp_port: int = 0,
    worker_live: bool = False,
    worker_generic: bool = False,
    worker_cua: bool = False,
    worker_cua_click_route: str = "trusted",
    worker_codex_assist_config: dict | None = None,
    worker_native_assistance_policy: dict | None = None,
    takeover_unavailable_reason: str | None = None,
    worker_synthetic_browser_root: Path | None = None,
    package_resources: Path | None = None,
    native_host_identity=None,
    native_host_binding: dict | None = None,
    write_admission_policy: str = "strict",
    resume_model_mode: str | None = None,
    flow_automatic_latex_base=None,
) -> ThreadingHTTPServer:
    """Bind only loopback; all input roots are selected explicitly by the operator."""
    if not 0 <= port <= 65535:
        raise ValueError("Choose a port between 0 and 65535.")
    if write_admission_policy not in {"strict", "development"}:
        raise ValueError("Choose the trusted write admission policy.")
    installed_resources = Path(__file__).absolute().parents[3]
    installed_layout = (
        installed_resources.name == "Resources" and installed_resources.parent.name == "Contents"
    )
    if installed_layout and package_resources is None:
        package_resources = installed_resources
    preparation_static = {
        path.name: path.read_bytes() for path in _STATIC.iterdir() if path.is_file()
    }
    runtime = open_runtime(
        application_root,
        career_workspace,
        static_root=_STATIC,
        static_files=preparation_static,
        worker_root=worker_root,
        handoff_root=handoff_root,
        flow_root=flow_root,
        flow_analyzer=flow_analyzer,
        flow_match_runner=flow_match_runner,
        flow_resume_factory=flow_resume_factory,
        flow_intake_factory=flow_intake_factory,
        application_processed_label=application_processed_label,
        flow_legacy_roots=flow_legacy_roots,
        information_library_root=information_library_root,
        career_library_manifest=career_library_manifest,
        cover_letter_template=cover_letter_template,
        automatic_resume_author=automatic_resume_author,
        preparation_only=preparation_only,
        resume_review_root=resume_review_root,
        resume_review_config=resume_review_config,
        resume_template_config=resume_template_config,
        resume_review_pdf_inspector=resume_review_pdf_inspector,
        worker_fixtures=worker_fixtures,
        worker_headless=worker_headless,
        worker_cdp_port=worker_cdp_port,
        worker_live=worker_live,
        worker_generic=worker_generic,
        worker_cua=worker_cua,
        worker_cua_click_route=worker_cua_click_route,
        worker_codex_assist_config=worker_codex_assist_config,
        worker_native_assistance_policy=worker_native_assistance_policy,
        takeover_unavailable_reason=takeover_unavailable_reason,
        worker_synthetic_browser_root=worker_synthetic_browser_root,
        package_resources=package_resources,
        native_host_identity=native_host_identity,
        native_host_binding=native_host_binding,
        resume_model_mode=resume_model_mode,
        flow_automatic_latex_base=flow_automatic_latex_base,
    )
    applications, evidence, graph = runtime.applications, runtime.evidence, runtime.graph
    career_library, handoff, review = runtime.career_library, runtime.handoff, runtime.review
    worker, worker_unavailable = runtime.worker, runtime.worker_unavailable
    flow, flow_resumes, resumes = runtime.flow, runtime.flow_resumes, runtime.resumes
    intake, intake_unavailable = runtime.intake, runtime.intake_unavailable
    pipeline, pipeline_unavailable = runtime.pipeline, runtime.pipeline_unavailable
    readiness, flow_sources = runtime.readiness, runtime.flow_sources
    token = secrets.token_urlsafe(32)

    def worker_reference(_state: dict, task: dict) -> dict:
        # Retain the HTTP/material adapter signature during interface migration.
        return flow.callbacks["worker_reference"](task)

    def screened_applications() -> list[dict]:
        return screen_applications(
            applications.list_applications(),
            language_levels=worker.store.language_levels if worker else None,
            allow_generic=worker.generic if worker else False,
        )

    class Handler(BaseHTTPRequestHandler):
        server_version = "TomorrowStar"

        def log_message(self, format: str, *args: object) -> None:
            # Request paths and query text can contain personal information.
            pass

        def _send(
            self,
            status: int,
            body: bytes,
            mime: str,
            *,
            allow_same_origin_frame: bool = False,
            **headers: str,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "SAMEORIGIN" if allow_same_origin_frame else "DENY")
            frame_ancestors = "'self'" if allow_same_origin_frame else "'none'"
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                f"base-uri 'none'; frame-ancestors {frame_ancestors}; form-action 'self'",
            )
            for key, value in headers.items():
                self.send_header(key.replace("_", "-"), value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, value: object, status: int = 200) -> None:
            self._send(
                status,
                json.dumps(value, ensure_ascii=False, allow_nan=False).encode(),
                "application/json; charset=utf-8",
            )

        def _error(self, code: str, message: str, status: int) -> None:
            self._json({"error": code, "message": message}, status)

        def _admit(self, *, write: bool = False) -> bool:
            port = self.server.server_port
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if len(self.headers.get_all("Host", [])) != 1 or host not in hosts:
                self._error("invalid_host", "请从本机地址打开工作台。", 403)
                return False
            if self.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin"):
                self._error("invalid_origin", "无法接受来自其他网站的请求。", 403)
                return False
            if origin is not None and origin != f"http://{host}":
                self._error("invalid_origin", "无法接受来自其他网站的请求。", 403)
                return False
            if write and (
                origin != f"http://{host}"
                or not self.headers.get("X-CSRF-Token", "").isascii()
                or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), token)
            ):
                self._error("invalid_csrf", "请刷新工作台后重新保存。", 403)
                return False
            return True

        def _body(self, maximum: int = _MAX_BODY) -> dict:
            if self.headers.get("Transfer-Encoding"):
                raise PortalDataError("invalid_body", "不支持此请求格式。", 400)
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1:
                raise PortalDataError("invalid_body", "请求长度不明确。", 400)
            try:
                size = int(lengths[0])
            except ValueError as exc:
                raise PortalDataError("invalid_body", "请求长度无效。", 400) from exc
            if size < 1 or size > maximum:
                raise PortalDataError("body_too_large", "内容过长，请缩短职位描述或备注。", 413)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise PortalDataError("invalid_content_type", "请使用工作台表单保存。", 415)
            self.connection.settimeout(10)
            try:
                data = json.loads(self.rfile.read(size))
            except (ValueError, UnicodeError, OSError) as exc:
                raise PortalDataError("invalid_body", "无法读取表单内容，请重试。", 400) from exc
            if not isinstance(data, dict):
                raise PortalDataError("invalid_body", "表单内容必须是对象。", 400)
            return data

        def _path(self) -> str:
            return unquote(urlsplit(self.path).path)

        def _record_id(self, prefix: str) -> str:
            identifier = self._path()[len(prefix) :]
            if (
                not identifier
                or "/" in identifier
                or "\\" in identifier
                or identifier.startswith(".")
            ):
                raise PortalDataError("not_found", "找不到此记录。", 404)
            return identifier

        def do_GET(self) -> None:
            if not self._admit():
                return
            try:
                path = self._path()
                static = {
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/static/application_flow.js": (
                        "application_flow.js",
                        "text/javascript; charset=utf-8",
                    ),
                    "/static/resume_review.js": (
                        "resume_review.js",
                        "text/javascript; charset=utf-8",
                    ),
                    "/static/resume_review.css": ("resume_review.css", "text/css; charset=utf-8"),
                    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
                    "/static/graph.js": ("graph.js", "text/javascript; charset=utf-8"),
                    "/static/graph.css": ("graph.css", "text/css; charset=utf-8"),
                    "/static/worker.js": ("worker.js", "text/javascript; charset=utf-8"),
                    "/static/worker.css": ("worker.css", "text/css; charset=utf-8"),
                    "/static/handoff.js": ("handoff.js", "text/javascript; charset=utf-8"),
                    "/static/handoff.css": ("handoff.css", "text/css; charset=utf-8"),
                }
                if path in static:
                    filename, mime = static[path]
                    raw = (
                        preparation_static[filename]
                        if preparation_static is not None
                        else (_STATIC / filename).read_bytes()
                    )
                    self._send(200, raw, mime)
                elif path == "/api/health":
                    self._json({"ok": True, "local_only": True})
                elif path == "/api/handoff/state":
                    self._json(handoff.snapshot() if handoff else {"enabled": False})
                elif path == "/api/pipeline/state":
                    self._json(
                        pipeline.snapshot()
                        if pipeline
                        else {
                            "protocol": "application-pipeline/v1",
                            "enabled": False,
                            "control": "paused",
                            "status": "unavailable",
                            "error": pipeline_unavailable,
                            "notification": None,
                        }
                    )
                elif path in {"/api/recommendations/state", "/api/intake/state"}:
                    self._json(
                        intake.snapshot()
                        if intake
                        else {
                            "enabled": False,
                            **(
                                {
                                    "error": intake_unavailable.code,
                                    "message": str(intake_unavailable),
                                }
                                if intake_unavailable
                                else {}
                            ),
                        }
                    )
                elif path == "/api/resume-review/state":
                    self._json(
                        {"enabled": True, **review.state()} if review else {"enabled": False}
                    )
                elif path.startswith("/api/resume-review/versions/") and review:
                    parts = path.removeprefix("/api/resume-review/versions/").split("/")
                    if len(parts) != 2 or parts[1] not in {"source", "pdf"}:
                        raise PortalDataError("not_found", "找不到此审阅版本。", 404)
                    identifier, kind = parts
                    raw = review.pdf(identifier) if kind == "pdf" else review.source(identifier)
                    self._send(
                        200,
                        raw,
                        "application/pdf" if kind == "pdf" else "text/plain; charset=utf-8",
                        allow_same_origin_frame=kind == "pdf",
                    )
                elif path == "/api/flow/readiness":
                    self._json(readiness())
                elif path.startswith("/api/flow/readiness/"):
                    self._json(readiness(self._record_id("/api/flow/readiness/")))
                elif path == "/api/flow/state":
                    self._json(runtime.flow_view.state())
                elif (
                    path.startswith("/api/flow/group-previews/")
                    and flow_resumes
                    and preparation_only
                ):
                    parts = path.removeprefix("/api/flow/group-previews/").split("/")
                    if len(parts) != 3 or parts[2] != "pdf":
                        raise PortalDataError("flow_draft_not_found", "找不到此预览。", 404)
                    flow.read_draft(parts[0])
                    self._send(
                        200,
                        flow_resumes.group_preview_pdf(parts[0], parts[1]),
                        "application/pdf",
                        allow_same_origin_frame=True,
                    )
                elif path.startswith("/api/flow/worker-materials/") and flow:
                    from .application_material_edit import read_material_pdf

                    parts = path.removeprefix("/api/flow/worker-materials/").split("/")
                    if (
                        len(parts) != 3
                        or parts[2] != "pdf"
                        or any(re.fullmatch("[a-f0-9]{32}", item) is None for item in parts[:2])
                    ):
                        raise PortalDataError("material_not_found", "找不到此附稿。", 404)
                    raw = read_material_pdf(flow, worker, worker_reference, parts[0], parts[1])
                    self._send(200, raw, "application/pdf", allow_same_origin_frame=True)
                elif path.startswith("/api/flow/drafts/") and flow_resumes:
                    self._json(flow.read_draft(path.removeprefix("/api/flow/drafts/")))
                elif path.startswith("/api/flow/exports/") and flow_resumes and preparation_only:
                    saved = flow.read_export(path.removeprefix("/api/flow/exports/"))
                    self._json({key: value for key, value in saved.items() if key != "file_base64"})
                elif (
                    path.startswith("/api/flow/resumes/") and path.endswith("/pdf") and flow_resumes
                ):
                    identifier = path.removeprefix("/api/flow/resumes/").removesuffix("/pdf")
                    raw = (
                        base64.b64decode(flow.read_export(identifier)["file_base64"], validate=True)
                        if preparation_only
                        else flow_resumes.pdf(identifier)
                    )
                    self._send(
                        200,
                        raw,
                        "application/pdf",
                        allow_same_origin_frame=True,
                    )
                elif path.startswith("/api/flow/") and flow:
                    self._json(runtime.flow_view.state(self._record_id("/api/flow/")))
                elif path == "/api/worker/state":
                    try:
                        self._json(
                            worker.snapshot()
                            if worker and flow is None
                            else {
                                "enabled": False,
                                **(
                                    {
                                        "error": worker_unavailable.code,
                                        "message": str(worker_unavailable),
                                    }
                                    if worker_unavailable
                                    else {}
                                ),
                            }
                        )
                    except (OSError, ValueError, KeyError) as exc:
                        if worker:
                            worker.store.block_storage()
                        raise PortalDataError(
                            "worker_checkpoint_unavailable",
                            "运行记录无法核验。自动操作已停止；请保留原文件并核验。",
                            409,
                        ) from exc
                elif path.startswith("/api/resumes/") and path.endswith("/pdf") and resumes:
                    identifier = path.removeprefix("/api/resumes/").removesuffix("/pdf")
                    self._send(200, resumes.pdf(identifier), "application/pdf")
                elif path == "/api/graph":
                    self._json(graph.snapshot())
                elif path == "/api/public-site":
                    try:
                        self._json(
                            load_public_site(
                                evidence.root / "reports/public-site/site-content.json"
                            )
                        )
                    except (OSError, ValueError) as exc:
                        raise PortalDataError(
                            "public-site-unavailable", "公开展示内容尚未配置或需要修正。", 404
                        ) from exc
                elif path == "/api/interview/protocol":
                    self._json(
                        {
                            "content": (
                                _PUBLIC_ROOT / "docs/question-scoring-pipeline.md"
                            ).read_text(encoding="utf-8")
                        }
                    )
                elif path == "/api/state":
                    self._json(
                        {
                            "applications": screened_applications(),
                            "evidence": evidence.list_evidence(),
                            "statuses": [
                                {"value": value, "label": label}
                                for value, label in STATUS_LABELS.items()
                            ],
                            "tracks": list(TRACKS),
                            "connections": {"applications": True, "career": True},
                            "csrf_token": token,
                            "worker_warning": {
                                "code": worker_unavailable.code,
                                "message": str(worker_unavailable),
                            }
                            if worker_unavailable
                            else None,
                        }
                    )
                elif path.startswith("/api/applications/"):
                    self._json(
                        {
                            "application": applications.get_application(
                                self._record_id("/api/applications/")
                            )
                        }
                    )
                elif path == "/api/career-library":
                    self._json(career_library.index())
                elif path.startswith("/api/career-library/"):
                    identifier = self._record_id("/api/career-library/")
                    self._json(
                        career_library.snapshot_for_analysis(
                            career_source_snapshot(evidence), [identifier]
                        )
                    )
                elif path.startswith("/api/evidence/"):
                    self._json(evidence.get_evidence(self._record_id("/api/evidence/")))
                elif path == "/api/export.csv":
                    output = io.StringIO(newline="")
                    writer = csv.writer(output)
                    fields = (
                        "company",
                        "role_title",
                        "status",
                        "track",
                        "application_date",
                        "deadline",
                        "next_action",
                        "url",
                        "notes",
                    )
                    writer.writerow(fields)
                    for app in applications.list_applications():
                        writer.writerow([_csv_cell(app.get(field)) for field in fields])
                    self._send(
                        200,
                        ("\ufeff" + output.getvalue()).encode(),
                        "text/csv; charset=utf-8",
                        Content_Disposition='attachment; filename="tomorrowstar-applications.csv"',
                    )
                else:
                    self._error("not_found", "找不到此页面。", 404)
            except PortalDataError as exc:
                self._error(exc.code, str(exc), exc.status)
            except (OSError, ValueError):
                self._error("read_failed", "暂时无法读取本地记录，请检查连接后重试。", 500)

        def _write(self, *, patch: bool) -> None:
            if not self._admit(write=True):
                return
            try:
                path = self._path()
                if (not patch and path != "/api/applications") or (
                    patch and not path.startswith("/api/applications/")
                ):
                    self._error("not_found", "找不到此记录。", 404)
                    return
                data = self._body()
                links = data.get("linked_evidence", [])
                if not isinstance(links, list) or any(not isinstance(item, str) for item in links):
                    raise PortalDataError("invalid_evidence", "请选择有效的经历证据。")
                known = {item["id"] for item in evidence.list_evidence()}
                if set(links) - known:
                    raise PortalDataError("invalid_evidence", "关联证据已变更，请刷新后重新选择。")
                if patch:
                    revision = data.pop("revision", None)
                    if not isinstance(revision, str) or not revision:
                        raise PortalDataError("revision_required", "请重新打开记录后保存。", 409)
                    app = applications.update_application(
                        self._record_id("/api/applications/"), data, revision
                    )
                else:
                    request_ids = self.headers.get_all("Idempotency-Key", [])
                    if len(request_ids) > 1:
                        raise PortalDataError("invalid-save-request", "保存请求标识重复。")
                    if request_ids:
                        app = applications.create_application(data, request_id=request_ids[0])
                    else:
                        app = applications.create_application(data)
            except PortalDataError as exc:
                self._error(exc.code, str(exc), exc.status)
                return
            except (OSError, ValueError):
                self._error("save_failed", "保存失败，原记录已保留。请刷新后重试。", 500)
                return
            response = {"application": app}
            try:
                app["screening"] = next(
                    row["screening"] for row in screened_applications() if row["id"] == app["id"]
                )
            except Exception:
                # The write committed. Optional derived state cannot invalidate its receipt.
                response["screening_warning"] = {
                    "code": "screening_unavailable",
                    "message": "记录已保存，但筛选结果暂不可用。请刷新工作台；无需重复保存。",
                }
            self._json(response, 200 if patch else 201)

        def do_POST(self) -> None:
            if self._path().startswith("/api/resume-review/"):
                if not self._admit(write=True):
                    return
                try:
                    if review is None:
                        raise PortalDataError(
                            "resume_review_disabled", "尚未配置独立简历审阅。", 409
                        )
                    action = self._record_id("/api/resume-review/")
                    payload = self._body()
                    if action == "capture" and set(payload) == {"source_revision"}:
                        result = review.capture(payload["source_revision"])
                    elif action == "editor" and not payload:
                        result = {"editor_url": review.editor()}
                    elif action == "reconcile" and not payload:
                        result = review.reconcile()
                    else:
                        raise PortalDataError("invalid_body", "请刷新审阅页后重试。", 400)
                    self._json({"enabled": True, **result})
                except PortalDataError as exc:
                    self._error(exc.code, str(exc), exc.status)
                except (OSError, ValueError, KeyError, TypeError):
                    self._error(
                        "resume_review_unavailable", "审阅材料尚未核验，原版本已保留。", 409
                    )
                return
            if self._path().startswith("/api/pipeline/"):
                if not self._admit(write=True):
                    return
                try:
                    if pipeline is None:
                        raise PortalDataError(
                            "pipeline_unavailable", "自动申请流程暂不可用，请保留当前任务。", 409
                        )
                    action = self._record_id("/api/pipeline/")
                    payload = self._body()
                    self._json(pipeline_control(pipeline, action, payload))
                except PortalDataError as error:
                    self._error(error.code, str(error), error.status)
                except (OSError, ValueError, KeyError, TypeError):
                    self._error(
                        "pipeline_result_unknown", "自动流程结果尚未核验，原任务已保留。", 500
                    )
                return
            if self._path().startswith("/api/intake/"):
                if not self._admit(write=True):
                    return
                try:
                    if intake is None:
                        raise intake_unavailable or PortalDataError(
                            "intake_disabled", "请先配置岗位工作区。", 409
                        )
                    action = self._record_id("/api/intake/")
                    payload = self._body()
                    if action == "ingest" and {"request_id"} < payload.keys() <= {
                        "request_id",
                        "text",
                        "url",
                    }:
                        self._json(intake.ingest(**payload))
                    elif action == "reconcile" and set(payload) == {"request_id"}:
                        self._json(intake.reconcile_job(payload["request_id"]))
                    else:
                        raise PortalDataError(
                            "invalid_intake_request", "请只提供完整 JD 或岗位链接。"
                        )
                except PortalDataError as error:
                    self._error(error.code, str(error), error.status)
                except (OSError, ValueError, KeyError, TypeError):
                    self._error(
                        "intake_save_failed", "岗位整理结果尚未核验，请先读取持久记录。", 500
                    )
                return
            if self._path().startswith("/api/recommendations/"):
                if not self._admit(write=True):
                    return
                try:
                    if intake is None:
                        raise intake_unavailable or PortalDataError(
                            "intake_disabled", "请先配置单岗位工作区。", 409
                        )
                    action = self._record_id("/api/recommendations/")
                    payload = self._body()
                    with (
                        pipeline.manual_entry(f"recommendations:{action}", payload)
                        if pipeline is not None and not preparation_only
                        else nullcontext()
                    ):
                        if action == "refresh" and payload.keys() <= {
                            "max_results",
                            "max_candidates",
                            "capture_only",
                            "after",
                            "before",
                        }:
                            self._json(intake.refresh(**payload))
                        elif action == "continue" and {"revision"} <= payload.keys() <= {
                            "revision",
                            "after",
                            "before",
                        }:
                            self._json(intake.continue_read(**payload))
                        elif action == "acquire" and {"id", "revision"} <= payload.keys() <= {
                            "id",
                            "revision",
                            "retry",
                        }:
                            self._json(
                                intake.acquire(
                                    payload["id"],
                                    payload["revision"],
                                    retry=payload.get("retry", False),
                                )
                            )
                        elif action == "reconcile-source" and set(payload) == {"id"}:
                            self._json(intake.reconcile_source(payload["id"]))
                        elif action == "select" and set(payload) == {"id", "revision"}:
                            self._json(intake.select(payload["id"], payload["revision"]))
                        else:
                            raise PortalDataError("invalid_intake_request", "推荐请求字段无效。")
                except PortalDataError as error:
                    self._error(error.code, str(error), error.status)
                except (OSError, ValueError, KeyError, TypeError):
                    self._error(
                        "intake_save_failed", "推荐操作结果尚未核验，请读取持久记录后再操作。", 500
                    )
                return
            if self._path().startswith("/api/flow/"):
                if not self._admit(write=True):
                    return
                try:
                    if flow is None:
                        raise PortalDataError("flow_disabled", "请先配置单岗位任务目录。", 409)
                    action = self._record_id("/api/flow/")
                    payload = self._body()
                    if action == "cancel" and pipeline is not None and not preparation_only:
                        if set(payload) != {"task_id", "task_revision"}:
                            raise PortalDataError("flow_request_invalid", "任务取消参数无效。")
                        cancelled = pipeline.cancel_current(
                            payload["task_id"],
                            payload["task_revision"],
                            request_id="flow-cancel-" + digest(payload),
                        )
                        self._json(
                            flow.task_snapshot(payload["task_id"])
                            | {"cancellation": cancelled["current_cancellation"]}
                        )
                        return
                    if pipeline is not None and not preparation_only:
                        routed = pipeline.flow_control(action, payload)
                        if routed is not None:
                            self._json(routed)
                            return
                    with (
                        pipeline.manual_entry(f"flow:{action}", payload)
                        if pipeline is not None and not preparation_only
                        else nullcontext()
                    ):
                        if action == "edit-material":
                            from .application_material_edit import edit_material

                            self._json(edit_material(flow, worker, worker_reference, payload))
                        elif action == "capture-material-tex":
                            from .application_material_edit import capture_material_tex

                            self._json(
                                capture_material_tex(flow, worker, worker_reference, payload)
                            )
                        elif action == "reconcile-material-edit":
                            from .application_material_edit import reconcile_material_edit

                            self._json(
                                reconcile_material_edit(flow, worker, worker_reference, payload)
                            )
                        else:
                            self._json(flow.request(action, payload))
                except PortalDataError as exc:
                    self._error(exc.code, str(exc), exc.status)
                except (OSError, ValueError, KeyError, TypeError):
                    self._error(
                        "flow_save_failed", "任务状态尚未核验，请读取持久记录后再操作。", 500
                    )
                return
            if self._path().startswith("/api/handoff/"):
                if not self._admit(write=True):
                    return
                try:
                    if handoff is None:
                        raise PortalDataError(
                            "handoff_disabled", "请先配置独立 Codex 交接目录。", 409
                        )
                    action = self._record_id("/api/handoff/")
                    if action not in {
                        "prepare",
                        "claim",
                        "readback",
                        "review",
                        "submitted",
                        "receipt",
                        "resolve",
                        "release",
                        "retry-sync",
                        "answer",
                    }:
                        raise PortalDataError("not_found", "找不到此交接操作。", 404)
                    self._json(handoff.request(action, self._body()))
                except PortalDataError as exc:
                    self._error(exc.code, str(exc), exc.status)
                except (OSError, ValueError, KeyError, TypeError):
                    self._error(
                        "handoff_save_failed",
                        "交接结果尚未核验。请保留当前输入，刷新持久记录后核对；不要重复上传或提交。",
                        500,
                    )
                return
            if self._path().startswith("/api/worker/"):
                if not self._admit(write=True):
                    return
                try:
                    if flow is not None:
                        raise PortalDataError(
                            "flow_scoped_worker_required", "请通过当前单岗位任务控制填写。", 409
                        )
                    if worker is None:
                        if worker_unavailable:
                            raise worker_unavailable
                        raise PortalDataError("worker_disabled", "请先配置独立 worker。", 409)
                    self._json(
                        worker.request(
                            self._record_id("/api/worker/"), self._body(maximum=20_000_000)
                        )
                    )
                except PortalDataError as exc:
                    self._error(exc.code, str(exc), exc.status)
                except (OSError, ValueError, KeyError, TypeError):
                    if worker is not None:
                        worker.store.block_storage()
                    self._error("worker_save_failed", "操作未保存，请保留输入后重试。", 500)
                return
            if self._path() == "/api/automation/prepare":
                if not self._admit(write=True):
                    return
                try:
                    payload = self._body()
                    if set(payload) != {"application_id", "revision"} or any(
                        not isinstance(payload[key], str) or not payload[key]
                        for key in ("application_id", "revision")
                    ):
                        raise PortalDataError("invalid_task", "请重新打开投递记录后准备填表。")
                    task = prepare_application_task(
                        applications, payload["application_id"], payload["revision"]
                    )
                    screening = next(
                        app["screening"]
                        for app in screened_applications()
                        if app["id"] == payload["application_id"]
                    )
                    if screening["application_route"] not in {"batch", "manual"}:
                        raise PortalDataError(
                            "application_route_required",
                            "请先在岗位详情核对评价并保存投递分流。",
                            409,
                        )
                    task["application_route"] = screening["application_route"]
                    task["prompt"] += (
                        "\n投递分流：" + screening["route_label"] + "。"
                        "人工精准岗位须先复核关键 JD、相关贡献证据和定制简历，再辅助填写。\n"
                    )
                    self._json(task)
                except PortalDataError as exc:
                    self._error(exc.code, str(exc), exc.status)
                except (OSError, ValueError):
                    self._error("prepare_failed", "无法准备任务，请检查原记录后重试。", 500)
                return
            if self._path() != "/api/interview/inspect-plan":
                self._write(patch=False)
                return
            if not self._admit(write=True):
                return
            try:
                payload = self._body()
                if set(payload) != {"plan", "facts_by_contribution", "experience_id"}:
                    raise ValueError("unexpected interview inspection fields")
                experience_id = payload["experience_id"]
                if not isinstance(experience_id, str) or not experience_id.strip():
                    raise ValueError("expected Experience identity")
                plan = ProjectInterviewPlan.model_validate(payload["plan"])
                facts = TypeAdapter(dict[str, tuple[ArtifactFact, ...]]).validate_python(
                    payload["facts_by_contribution"]
                )
                self._json(
                    inspect_project_interview_plan(
                        plan, experience_id=experience_id, facts_by_contribution=facts
                    )
                )
            except PortalDataError as exc:
                self._error(exc.code, str(exc), exc.status)
            except ValueError:
                self._error(
                    "invalid_interview_plan",
                    "计划检查未通过。请核对经历标识、三层结构、评价判据和来源引用。",
                    400,
                )

        def do_PATCH(self) -> None:
            if self._path().startswith("/api/evidence/"):
                if not self._admit(write=True):
                    return
                try:
                    payload = self._body()
                    if (
                        not {"revision", "content"}
                        <= payload.keys()
                        <= {
                            "revision",
                            "content",
                            "source",
                        }
                    ):
                        raise PortalDataError("invalid_fact_correction", "职业事实更正字段无效。")
                    self._json(
                        evidence.update_evidence(
                            self._record_id("/api/evidence/"),
                            payload["revision"],
                            payload["content"],
                            source=payload.get("source", "explicit-career-correction"),
                        )
                    )
                except PortalDataError as error:
                    self._error(error.code, str(error), error.status)
                except (OSError, ValueError):
                    self._error(
                        "career_save_failed", "职业资料更正结果尚未核验，请先读取保存记录。", 500
                    )
                return
            self._write(patch=True)

        def send_error(
            self, code: int, message: str | None = None, explain: str | None = None
        ) -> None:
            self._error("invalid_request", "不支持此请求。", code)

    class Server(ThreadingHTTPServer):
        # The document and static resources can arrive before request dispatch.
        request_queue_size = 32

        def shutdown(self) -> None:
            # Stop writes before the backend stops serving, retaining pages and owner.
            runtime.stop_writes()
            super().shutdown()

        def server_close(self) -> None:
            runtime.close()
            super().server_close()

    try:
        server = Server(("127.0.0.1", port), Handler)
    except BaseException:
        runtime.close()
        raise
    server.daemon_threads = True
    server.handoff_service = handoff
    server.worker_service = worker
    server.worker_fixtures = runtime.fixtures
    server.resume_review_store = review
    server.application_flow_service = flow
    server.application_readiness = readiness
    server.application_resume_store = flow_resumes
    server.application_intake_service = intake
    server.career_library = career_library
    server.analysis_context = lambda application_id, candidate_ids=None: (
        applications.get_application(application_id),
        career_library.snapshot_for_analysis(career_source_snapshot(evidence), candidate_ids)
        if career_library_manifest is not None
        else flow_sources(),
    )
    server.application_pipeline_service = pipeline
    return server


def _read_local_configuration() -> dict:
    if _CONFIG.is_symlink():
        raise ValueError("Local configuration cannot be a symbolic link.")
    config = json.loads(_CONFIG.read_text())
    if not isinstance(config, dict) or any(
        not isinstance(config.get(key), str) or not config[key]
        for key in ("applications", "career_workspace")
    ):
        raise ValueError("Invalid local configuration.")
    return config


@contextmanager
def _configuration_write_lock():
    if any(path.is_symlink() for path in (_CONFIG, *_CONFIG.parents)):
        raise ValueError("Local configuration cannot use symbolic links.")
    _CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        _CONFIG.with_name(f".{_CONFIG.name}.lock"),
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Local configuration lock must be a regular file.")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TomorrowStar local career workspace")
    parser.add_argument("--applications", type=Path, help="Existing Obsidian application folder")
    parser.add_argument("--career-workspace", type=Path, help="Private career-data Git workspace")
    parser.add_argument("--career-library-manifest", type=Path)
    parser.add_argument(
        "--cover-letter-template", type=Path, help="Private fixed LaTeX letter template"
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the workspace in your browser")
    parser.add_argument("--worker-root", type=Path, help="Experimental automatic worker directory")
    parser.add_argument(
        "--handoff-root", type=Path, help="Private single-job Codex handoff directory"
    )
    parser.add_argument(
        "--worker-live", action="store_true", help="Supervised live ATS filling; manual Submit"
    )
    parser.add_argument(
        "--worker-generic",
        action="store_true",
        help="Opt into supervised generic HTTPS form inspection and filling",
    )
    parser.add_argument(
        "--worker-fixtures",
        action="store_true",
        help="Use isolated synthetic Lever / Greenhouse pages",
    )
    parser.add_argument(
        "--worker-headless", action="store_true", help="Headless synthetic test mode"
    )
    parser.add_argument(
        "--worker-cdp-port", type=int, default=0, help="Optional local QA attachment port"
    )
    parser.add_argument(
        "--worker-cua", action="store_true", help="Use an isolated CuaDriver browser"
    )
    parser.add_argument(
        "--worker-cua-click-route", choices=("trusted", "dom_event"), default="trusted"
    )
    parser.add_argument(
        "--save-config", action="store_true", help="Remember paths outside the repo"
    )
    args = parser.parse_args(argv)
    selected_configuration = {
        key: value
        for key in (
            "applications",
            "career_workspace",
            "career_library_manifest",
            "cover_letter_template",
        )
        if (value := getattr(args, key)) is not None
    }
    if args.worker_root is not None and args.handoff_root is not None:
        parser.error("Choose --handoff-root or --worker-root; use separate servers.")
    if args.worker_root is None and (
        args.worker_fixtures
        or args.worker_headless
        or args.worker_cdp_port
        or args.worker_live
        or args.worker_generic
        or args.worker_cua
        or args.worker_cua_click_route != "trusted"
    ):
        parser.error("Worker options require --worker-root.")
    try:
        if args.applications is None and args.career_workspace is None:
            config = _read_local_configuration()
            args.applications = Path(config["applications"])
            args.career_workspace = Path(config["career_workspace"])
            if args.career_library_manifest is None and config.get("career_library_manifest"):
                args.career_library_manifest = Path(config["career_library_manifest"])
            if args.cover_letter_template is None and config.get("cover_letter_template"):
                args.cover_letter_template = Path(config["cover_letter_template"])
        if args.applications is None or args.career_workspace is None:
            parser.error("Supply both --applications and --career-workspace on first launch.")
        worker_options = (
            {
                "worker_root": args.worker_root,
                "worker_fixtures": args.worker_fixtures,
                "worker_headless": args.worker_headless,
                "worker_cdp_port": args.worker_cdp_port,
                "worker_live": args.worker_live,
                "worker_generic": args.worker_generic,
                "worker_cua": args.worker_cua,
                "worker_cua_click_route": args.worker_cua_click_route,
            }
            if args.worker_root is not None
            else {}
        )
        with create_server(
            args.applications.expanduser(),
            args.career_workspace.expanduser(),
            port=args.port,
            **(
                {"career_library_manifest": args.career_library_manifest}
                if args.career_library_manifest is not None
                else {}
            ),
            write_admission_policy="development",
            **(
                {"cover_letter_template": args.cover_letter_template}
                if args.cover_letter_template is not None
                else {}
            ),
            **worker_options,
            **({"handoff_root": args.handoff_root} if args.handoff_root is not None else {}),
        ) as server:
            if args.save_config:
                with _configuration_write_lock():
                    config = _read_local_configuration() if os.path.lexists(_CONFIG) else {}
                    for key, value in selected_configuration.items():
                        path = value.expanduser()
                        config[key] = str(
                            path.resolve()
                            if key in {"applications", "career_workspace"}
                            else path.absolute()
                        )
                    atomic_write_json(_CONFIG, config)
            url = f"http://127.0.0.1:{server.server_port}/"
            print(f"TomorrowStar is ready: {url}", flush=True)
            if args.open:
                webbrowser.open(url)
            with suppress(KeyboardInterrupt):
                server.serve_forever()
        return 0
    except (OSError, ValueError, KeyError, PortalDataError):
        print(
            "Unable to start. Check the two private folders and that the port is available.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
