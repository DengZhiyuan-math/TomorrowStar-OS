"""Fixed synthetic Gmail and JD captures for the isolated native preparation journey."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .application_gmail import validate_recommendation_query
from .application_intake import ApplicationIntakeService
from .career_portal_data import PortalDataError

JOB_URL = "https://www.linkedin.com/jobs/view/424242"
_PREVIEW_SHA256 = "024c16287b8b9b105b4dbab31a0bb94fcca0d3ed4b47ecd8cf0b8745ae3b62be"


LITERAL_REPLAY_CACHE_KEY = "synthetic-literal-source-replay/v1"


def literal_replay_runner(root: Path):
    """Explicit fake model boundary for the fixed CLI replay, never real subagents."""
    from .application_worker_fixtures import synthetic_cli_text
    from .codex_cli import run_codex_exec, validate_codex_executable

    root = Path(root)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("synthetic-replay-root")
    marker_path = root / "synthetic-flow.json"
    if marker_path.is_symlink() or not marker_path.is_file():
        raise ValueError("synthetic-replay-contract")
    marker = json.loads(marker_path.read_text())
    executable = root / "codex-fixture"
    expected = hashlib.sha256(synthetic_cli_text().encode()).hexdigest()
    if (
        marker.get("purpose") not in {"preparation-synthetic", "mail-synthetic"}
        or marker.get("schemaVersion") != 1
    ):
        raise ValueError("synthetic-replay-contract")

    def replay(config, prompt, **options):
        # Startup-only fixtures may use a sentinel that must never execute.
        if marker.get("codex_sha256") != expected:
            raise ValueError("synthetic-replay-contract")
        validated = validate_codex_executable(executable)
        if hashlib.sha256(Path(validated).read_bytes()).hexdigest() != expected:
            raise ValueError("synthetic-replay-cli")
        environment = options.pop("environment", None)
        environment = dict(os.environ if environment is None else environment)
        environment["TOMORROWSTAR_CODEX_EXECUTABLE"] = validated
        return run_codex_exec(config, prompt, environment=environment, **options)

    return replay


class SyntheticPrismClient:
    """Replay one fixed PDF inside the explicit fixture; never connect to Prism."""

    def __init__(self, root: Path, *, application: bool = False):
        self.root = Path(root)
        self.projects = (
            self.root
            / "runtime"
            / ("single-job-flow" if application else "material-preparation")
            / "resumes"
        )

    def configuration(self):
        return {
            "kind": "preparation-synthetic-fixed-pdf",
            "synthetic": True,
            "real_compilation": False,
            "fixture_sha256": _PREVIEW_SHA256,
        }

    def _binding(self, binding):
        from .application_prism import refresh_source_snapshot

        project = Path(binding["project_root"])
        if not project.is_relative_to(self.projects) or project == self.projects:
            raise PortalDataError(
                "synthetic_prism_source_invalid", "合成预览仅支持本运行的独立材料项目。", 409
            )
        current = refresh_source_snapshot(binding)
        if any(binding.get(key) != value for key, value in current.items()):
            raise PortalDataError("prism_source_changed", "LaTeX 源已变化，请重新读取。", 409)

    def open(self, binding):
        self._binding(binding)
        raise PortalDataError(
            "synthetic_prism_editor_disabled",
            "合成模式不连接真实 Prism；请使用材料页的分组编辑入口。",
            409,
        )

    def compile(self, binding):
        from .application_prism_review import _read

        self._binding(binding)
        try:
            path = self.root / "synthetic-preview.pdf"
            if path.lstat().st_nlink != 1:
                raise ValueError("aliased synthetic PDF")
            pdf = _read(path, 700_000)
            if hashlib.sha256(pdf).hexdigest() != _PREVIEW_SHA256:
                raise ValueError("changed synthetic PDF")
        except (OSError, ValueError) as error:
            raise PortalDataError(
                "resume_export_failed", "固定合成预览不能核验；不调用真实编译。", 503
            ) from error
        return {
            "source_revision": binding["source_revision"],
            "pdf": pdf,
            "build": {
                "main": binding["main"],
                "exit": 0,
                "pdf_updated": True,
                "synthetic": True,
                "real_compilation": False,
            },
        }


def create_preparation_intake(applications, root: Path) -> ApplicationIntakeService:
    """Use real intake persistence with fixed captures and no external transport."""

    def reader(
        directory,
        *,
        max_results,
        query,
        page_token,
        account_context,
        window_context,
        verify_account,
        expected_mailbox_identity,
        admit_search,
    ):
        try:
            validate_recommendation_query(query)
        except PortalDataError as error:
            raise ValueError("Synthetic reader requires a recommendation query.") from error
        if (
            type(max_results) is not int
            or not 1 <= max_results <= 10
            or page_token is not None
            or expected_mailbox_identity is not None
            or verify_account is not True
            or not isinstance(window_context, str)
            or not window_context
            or not callable(admit_search)
            or not admit_search()
        ):
            raise ValueError("Synthetic reader accepts only an admitted initial read-only window.")
        return {
            "status": "readable",
            "emails": [
                {
                    "message_id": "preparation-synthetic-message",
                    "thread_id": "preparation-synthetic-thread",
                    "received_at": "2026-10-17T00:00:00+00:00",
                    "from": "jobalerts-noreply@linkedin.com",
                    "subject": "Synthetic Python Engineer recommendation",
                    "body_text": "Synthetic recommendation; full JD requires its separate capture.",
                    "body_completeness": "full",
                    "links": [JOB_URL],
                }
            ],
            "provenance": {
                "source": "preparation-synthetic",
                "new_model_calls": 0,
                "mailbox_identity": "a" * 64,
                "account_identity_status": "verified",
                "account_context": account_context,
                "window_context": window_context,
                "query": query,
                "next_page_token": None,
                "has_more": False,
            },
        }

    def fetcher(url):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"linkedin.com", "www.linkedin.com"}
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path.rstrip("/") != "/jobs/view/424242"
        ):
            raise ValueError("Synthetic source is outside the fixed fixture URL.")
        return {
            "capture_id": "preparation-synthetic-page",
            "url": JOB_URL,
            "final_url": JOB_URL,
            "body_text": "Python\nunit tests",
            "acquisition_status": "available",
            "jd_completeness": "full",
            "source_format": "job_posting",
            "redirects": [],
            "job_fields": {"title": "Synthetic Python Engineer", "company": "Synthetic Employer"},
            "synthetic": True,
            "new_model_calls": 0,
        }

    return ApplicationIntakeService(applications, root, reader=reader, fetcher=fetcher)


MAIL_JOBS = (
    ("https://jobs.lever.co/synthetic/11111111-1111-4111-8111-111111111111", "Software Engineer"),
    ("https://jobs.lever.co/synthetic/22222222-2222-4222-8222-222222222222", "Python Engineer"),
)


def create_mail_intake(applications, root: Path, **options) -> ApplicationIntakeService:
    """Two fixed pages and durable simulated mailbox effects; no external adapters."""
    import json

    from ._vendor.job_apply_store import atomic_write_json

    receipt = Path(root) / "synthetic-mailbox.json"

    def load():
        return (
            json.loads(receipt.read_text()) if receipt.exists() else {"messages": {}, "calls": []}
        )

    def reader(
        _directory, *, query, page_token, expected_mailbox_identity, admit_search, **_kwargs
    ):
        validate_recommendation_query(query)
        if (
            page_token not in (None, "mail-synthetic-page-2")
            or expected_mailbox_identity not in (None, "a" * 64)
            or not admit_search()
        ):
            raise ValueError("Outside the fixed synthetic mail window")
        index = 0 if page_token is None else 1
        url, title = MAIL_JOBS[index]
        return {
            "status": "readable",
            "emails": [
                {
                    "message_id": f"mail-synthetic-{index + 1}",
                    "thread_id": f"mail-synthetic-thread-{index + 1}",
                    "received_at": "2026-10-21T00:00:00+00:00",
                    "from": "jobalerts-noreply@linkedin.com",
                    "subject": f"Synthetic {title} recommendation",
                    "body_text": "Synthetic recommendation; read the fixed posting for its JD.",
                    "body_completeness": "full",
                    "links": [f"https://www.linkedin.com/jobs/view/{424242 + index}"],
                }
            ],
            "provenance": {
                "source": "mail-synthetic",
                "new_model_calls": 0,
                "mailbox_identity": "a" * 64,
                "account_identity_status": "verified",
                "next_page_token": "mail-synthetic-page-2" if index == 0 else None,
                "has_more": index == 0,
            },
        }

    def mailbox(_directory, *, message_id, operation, label_name, expected_mailbox_identity):
        if (
            message_id not in {"mail-synthetic-1", "mail-synthetic-2"}
            or operation not in {"inspect", "label", "archive"}
            or expected_mailbox_identity != "a" * 64
        ):
            raise ValueError("Outside the fixed synthetic mailbox")
        state = load()
        row = state["messages"].setdefault(message_id, {"labels": [], "archived": False})
        state["calls"].append([message_id, operation])
        if operation == "label" and label_name not in row["labels"]:
            row["labels"].append(label_name)
        lost = operation == "archive" and message_id == "mail-synthetic-2" and not row["archived"]
        if operation == "archive":
            row["archived"] = True
        atomic_write_json(receipt, state)
        if lost:
            raise TimeoutError("Synthetic archive succeeded; reply lost")
        return {
            "status": "complete",
            "labeled": label_name in row["labels"],
            "archived": row["archived"],
        }

    def fetcher(url):
        fixed = {
            f"https://www.linkedin.com/jobs/view/{424242 + index}": job
            for index, job in enumerate(MAIL_JOBS)
        }
        if url not in fixed:
            raise ValueError("Outside the fixed synthetic postings")
        target, title = fixed[url]
        return {
            "capture_id": "mail-synthetic-" + title.replace(" ", "-"),
            "url": url,
            "final_url": target,
            "body_text": "Python\nunit tests",
            "acquisition_status": "available",
            "jd_completeness": "full",
            "source_format": "job_posting",
            "redirects": [{"url": url, "location": target, "status": 302}],
            "job_fields": {"title": title, "company": "Synthetic Employer"},
            "synthetic": True,
            "new_model_calls": 0,
        }

    def extractor(_text, _directory):
        raise ValueError("Fixed postings supply documentary fields; no model extraction")

    return ApplicationIntakeService(
        applications,
        root,
        reader=reader,
        mailbox=mailbox,
        fetcher=fetcher,
        extractor=extractor,
        **options,
    )
