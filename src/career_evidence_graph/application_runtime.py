"""Runtime assembly: own, connect and start the application owners, then close them."""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
from contextlib import suppress
from contextvars import ContextVar
from functools import partial
from pathlib import Path

from ._vendor.job_apply_store import StoreError
from .application_readiness import ReadinessProbe
from .application_resume import ApplicationResumeStore, career_source_snapshot
from .application_worker import WorkerService
from .application_worker_fixtures import create_fixture_server
from .career_portal_data import ApplicationStore, CareerCatalog, PortalDataError
from .career_portal_graph import CareerGraph
from .loaded_code import (
    load_controller_modules,
    loaded_preparation_revision,
    loaded_runtime_revision,
)
from .validation.hashing import record_digest as digest
from .workspace import open_private_workspace

PUBLIC_ROOT = Path(__file__).resolve().parents[2]
_CLOSE_ERRORS = (OSError, ValueError, KeyError, TypeError, PortalDataError, StoreError)


def _external_directory(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Choose an existing application folder outside the system repository.")
    root = path.resolve(strict=True)
    public = PUBLIC_ROOT.resolve()
    if root == public or root.is_relative_to(public) or public.is_relative_to(root):
        raise ValueError("Personal records must remain outside the system repository.")
    return root


class ApplicationRuntime:
    """The assembled owners an entry uses; it is not a dependency lookup service."""

    applications = evidence = graph = career_library = handoff = review = None
    worker = worker_unavailable = flow = flow_resumes = resumes = None
    intake = intake_unavailable = pipeline = pipeline_unavailable = fixtures = None
    readiness = flow_sources = source_read = identity = flow_view = None
    preparation_only = False

    def stop_writes(self) -> None:
        """Withdraw Worker writes, then stop Pipeline and Flow; pages and owner stay."""
        worker, pipeline, flow = self.worker, self.pipeline, self.flow
        if worker:
            with suppress(*_CLOSE_ERRORS):
                worker.begin_backend_close()
        if pipeline:
            with suppress(*_CLOSE_ERRORS):
                pipeline.close()
        if flow:
            with suppress(*_CLOSE_ERRORS):
                flow.close()
        if worker:
            try:
                worker.close_backend()
            except _CLOSE_ERRORS:
                with suppress(*_CLOSE_ERRORS):
                    worker.store.block_storage()

    def close(self) -> None:
        """Stop writes and release intake and fixtures; repeated calls stay harmless."""
        self.stop_writes()
        if self.intake:
            self.intake.close()
        if self.fixtures:
            self.fixtures.shutdown()
            self.fixtures.server_close()


def _configure_measurements(flow, resumes, preparation_only):
    """Connect Resume measurements to Flow events; observations never gate work."""
    from .application_full_latex import is_fixed_education_group
    from .application_pdf_reuse import _acceptance

    def observe_pdf_ready(task):
        log = resumes.measurements
        episode = log.preparation_started(task["id"], digest(task["inputs"]))
        log.preparation_ready(
            episode,
            task_id=task["id"],
            pdf_sha256=task["resume_sha256"],
            inherited=bool(task.get("pdf_reuse")),
        )

    def observe_material_requests(task, retained_tasks):
        try:
            flow.verify_materials(task)
        except (PortalDataError, OSError, ValueError):
            return
        try:
            resumes.measurements.confirmation_requested(
                task["id"],
                task["resume_sha256"],
                already_accepted=any(
                    row.get("resume_sha256") == task["resume_sha256"] and _acceptance(row)
                    for row in retained_tasks
                ),
            )
        except (OSError, ValueError, TypeError):
            resumes.measurements.incomplete = True

    def group_confirmation_key(group):
        return digest(
            {
                "kind": "reviewed_content",
                "original": group.get("original"),
                "rewritten": group.get("rewritten"),
                "sources": group.get("sources"),
                "responsibility": group.get("responsibility"),
            }
        )

    def observe_group_requests(task, draft):
        try:
            flow.verify_draft(task)
        except (PortalDataError, OSError, ValueError):
            return
        reviewed = {
            (row.get("group_id"), row.get("review_fingerprint"))
            for row in task.get("group_reviews", [])
        }
        for group in draft.get("review_groups", []):
            if (
                not is_fixed_education_group(group)
                and (group["id"], group.get("review_fingerprint")) not in reviewed
            ):
                try:
                    resumes.measurements.confirmation_requested(
                        task["id"], group_confirmation_key(group)
                    )
                except (OSError, ValueError, TypeError):
                    resumes.measurements.incomplete = True

    flow.callbacks.update(
        observe_pdf_ready=observe_pdf_ready,
        observe_preparation_started=lambda task: resumes.measurements.preparation_started(
            task["id"], digest(task["inputs"])
        ),
        observe_confirmation=lambda task: resumes.measurements.confirmation_accepted(
            task["id"], task["resume_sha256"]
        ),
        observe_group_confirmation=lambda task, group: resumes.measurements.confirmation_accepted(
            task["id"], group_confirmation_key(group)
        ),
    )
    if preparation_only:
        flow.callbacks.update(
            observe_material_requests=observe_material_requests,
            observe_group_requests=observe_group_requests,
        )


def open_runtime(
    application_root: Path,
    career_workspace: Path,
    *,
    static_root: Path,
    static_files: dict,
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
    worker_synthetic_browser_root: Path | None = None,
    package_resources: Path | None = None,
    native_host_identity=None,
    native_host_binding: dict | None = None,
    resume_model_mode: str | None = None,
    flow_automatic_latex_base=None,
) -> ApplicationRuntime:
    """Construct and connect every owner before loops start; release them on failure.

    Opening never enables a paused Pipeline; saved intent, pauses and unknown results
    are kept by the owners' own recovery. ``resume_model_mode`` and
    ``flow_automatic_latex_base`` are synthetic-run settings applied before the
    Pipeline starts.
    """
    if resume_model_mode not in (None, "synthetic"):
        raise ValueError("Only synthetic runs select the resume model mode.")
    if flow_automatic_latex_base is not None and (
        not callable(flow_automatic_latex_base) or flow_root is None
    ):
        raise ValueError("A synthetic LaTeX base needs a callable and its flow directory.")
    if information_library_root is not None:
        selected = information_library_root.expanduser().resolve()
        public = PUBLIC_ROOT.resolve()
        if selected.is_relative_to(public) or public.is_relative_to(selected):
            raise ValueError("Applicant information must remain outside the system repository.")
    if preparation_only:
        if flow_root is None or handoff_root is not None:
            raise ValueError("Preparation requires its own flow directory and no handoff runtime.")
        worker_root = None
        worker_live = worker_generic = worker_cua = worker_fixtures = False
        flow_legacy_roots = ()
    if worker_root is not None and handoff_root is not None:
        raise ValueError("Choose the Codex handoff or the experimental worker in separate servers.")
    if worker_codex_assist_config is not None and (
        worker_root is None or worker_synthetic_browser_root is not None
    ):
        raise ValueError("Codex metadata configuration requires its own worker runtime.")
    runtime = ApplicationRuntime()
    runtime.preparation_only = preparation_only
    try:
        _assemble(
            runtime,
            application_root,
            career_workspace,
            static_root=static_root,
            static_files=static_files,
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
            worker_synthetic_browser_root=worker_synthetic_browser_root,
            package_resources=package_resources,
            native_host_identity=native_host_identity,
            native_host_binding=native_host_binding,
            resume_model_mode=resume_model_mode,
            flow_automatic_latex_base=flow_automatic_latex_base,
        )
    except BaseException:
        runtime.close()
        raise
    return runtime


def _assemble(
    runtime,
    application_root,
    career_workspace,
    *,
    static_root,
    static_files,
    worker_root,
    handoff_root,
    flow_root,
    flow_analyzer,
    flow_match_runner,
    flow_resume_factory,
    flow_intake_factory,
    application_processed_label,
    flow_legacy_roots,
    information_library_root,
    career_library_manifest,
    cover_letter_template,
    automatic_resume_author,
    resume_review_root,
    resume_review_config,
    resume_template_config,
    resume_review_pdf_inspector,
    worker_fixtures,
    worker_headless,
    worker_cdp_port,
    worker_live,
    worker_generic,
    worker_cua,
    worker_cua_click_route,
    worker_codex_assist_config,
    worker_synthetic_browser_root,
    package_resources,
    native_host_identity,
    native_host_binding,
    resume_model_mode,
    flow_automatic_latex_base,
):
    preparation_only = runtime.preparation_only
    applications = runtime.applications = ApplicationStore(_external_directory(application_root))
    evidence = runtime.evidence = CareerCatalog(
        open_private_workspace(career_workspace, public_root=PUBLIC_ROOT)
    )
    runtime.graph = CareerGraph(evidence)
    from .application_career_library import CareerLibrary

    career_library = runtime.career_library = CareerLibrary(career_library_manifest)
    if handoff_root is not None:
        from .application_handoff import CodexHandoffService

        runtime.handoff = CodexHandoffService(applications, handoff_root)
    review = None
    if (resume_review_root is None) != (resume_review_config is None):
        raise ValueError("Resume review requires its own root and explicit configuration.")
    if resume_review_root is not None:
        from .application_prism_review import PrismReviewStore

        public = PUBLIC_ROOT.resolve()
        selected = resume_review_root.resolve()
        if selected.is_relative_to(public) or public.is_relative_to(selected):
            raise ValueError("Resume review snapshots must remain outside the system repository.")
        review = runtime.review = PrismReviewStore(
            resume_review_root, resume_review_config, pdf_inspector=resume_review_pdf_inspector
        )
    if worker_live and (worker_fixtures or worker_headless or worker_root is None):
        raise ValueError("Live filling requires its private directory and a visible browser.")
    worker = None
    if worker_root is not None:
        try:
            worker = runtime.worker = WorkerService(
                applications,
                worker_root,
                headless=worker_headless,
                cdp_port=worker_cdp_port,
                live=worker_live,
                generic=worker_generic,
                cua=worker_cua,
                cua_click_route=worker_cua_click_route,
                **(
                    {"codex_assist_config": worker_codex_assist_config}
                    if worker_codex_assist_config is not None
                    else {}
                ),
                **(
                    {"synthetic_browser_root": worker_synthetic_browser_root}
                    if worker_synthetic_browser_root is not None
                    else {}
                ),
                **(
                    {
                        "single_flow_root": flow_root,
                        "single_career_root": evidence.root,
                        "legacy_roots": flow_legacy_roots,
                    }
                    if flow_root is not None
                    else {}
                ),
            )
        except PortalDataError as exc:
            if exc.code != "runtime_applications_mismatch":
                if flow_root is None:
                    raise
                runtime.worker_unavailable = PortalDataError(
                    "flow_worker_unavailable", "自动填写暂不可用；岗位资料仍可查看。", 409
                )
            else:
                runtime.worker_unavailable = exc
        except (OSError, ValueError, KeyError, TypeError, StoreError):
            if flow_root is None:
                raise
            runtime.worker_unavailable = PortalDataError(
                "flow_worker_unavailable", "自动填写暂不可用；岗位资料仍可查看。", 409
            )
    if information_library_root is None and worker is not None:
        information_library_root = worker.store.answers.root
    flow = None
    flow_resumes = None
    source_read = runtime.source_read = ContextVar("preparation_source_read", default=None)
    if information_library_root is None and worker_root is not None:
        information_library_root = worker_root / "answer-library"
    letter_template = cover_letter_template or os.environ.get("TOMORROWSTAR_COVER_LETTER_TEMPLATE")
    if worker is not None and letter_template:
        worker.store.cover_letter_template = Path(letter_template).expanduser().absolute()

    def flow_sources():
        # Reuse one observation only during a read-only status projection.
        # Mutations and worker stages retain their separate freshness checks.
        observation = source_read.get()
        if observation is None:
            return (
                career_source_snapshot(evidence, career_library=career_library)
                if career_library_manifest is not None
                else career_source_snapshot(evidence)
            )
        if "sources" not in observation:
            observation["sources"] = (
                career_source_snapshot(evidence, career_library=career_library)
                if career_library_manifest is not None
                else career_source_snapshot(evidence)
            )
        return observation["sources"]

    runtime.flow_sources = flow_sources

    if flow_root is not None:
        from .application_benchmark import load_benchmark
        from .application_flow import ApplicationFlowService, job_input_revision
        from .application_information import (
            material_information_library,
            read_information_library,
        )
        from .application_match import Analysis, match_configuration_revision
        from .application_resume import resume_configuration_revision

        if flow_analyzer is not None and not callable(flow_analyzer):
            raise ValueError("The job analyzer must be callable.")

        injected_revision = secrets.token_hex(16) if flow_analyzer is not None else "default"

        def current_benchmark(sources: dict, engine_revision: str) -> tuple[dict, str]:
            benchmark = load_benchmark(evidence.root, sources["revision"], engine_revision)
            return benchmark, digest(
                {"status": benchmark["status"], "revision": benchmark.get("revision")}
            )

        def binding_sources(application_id):
            sources = flow_sources()
            if flow is None or "career_library" not in sources:
                return sources
            observation = source_read.get()
            if observation is None:
                base = career_source_snapshot(evidence)
                state = None
            else:
                if "material_base_sources" not in observation:
                    observation["material_base_sources"] = career_source_snapshot(evidence)
                    observation["material_binding_state"] = flow.witness()[0]
                base = observation["material_base_sources"]
                state = observation["material_binding_state"]
            return (
                base
                if flow.reuses_base_sources(application_id, base["revision"], state=state)
                else sources
            )

        def current_flow_inputs(application_id: str) -> dict:
            application = applications.get_application(application_id)
            sources = binding_sources(application_id)
            engine_revision = match_configuration_revision()
            _, benchmark_revision = current_benchmark(sources, engine_revision)
            preparation_identity = {}
            if preparation_only:
                from .application_preparation import preparation_inputs

                preparation_identity = preparation_inputs(evidence.root)
            library = read_information_library(information_library_root)
            preparation_identity["information_library_revision"] = material_information_library(
                application, library
            )["revision"]
            preparation_identity["information_library_root"] = (
                str(information_library_root) if information_library_root is not None else None
            )
            return {
                "application_revision": application["revision"],
                "inputs": {
                    **preparation_identity,
                    "jd_revision": job_input_revision(application),
                    "sources_revision": sources["revision"],
                    "resume_configuration_revision": resume_configuration_revision(flow_resumes),
                    "historical_benchmark_revision": benchmark_revision,
                    "analysis_configuration_revision": digest(
                        {"engine": engine_revision, "adapter": injected_revision}
                    ),
                },
            }

        def current_flow_information():
            library = read_information_library(information_library_root)
            library["career_library"] = career_library.index()
            sources = flow_sources()
            profile, source = sources.get("profile"), sources.get("profile_source")
            if profile is not None and source is not None:
                library["education_profile"] = {
                    "education": profile.get("education", []),
                    "source": source,
                }
            return library

        flow = runtime.flow = ApplicationFlowService(
            applications,
            flow_root,
            input_provider=current_flow_inputs,
            information_provider=current_flow_information,
            information_library_root=information_library_root,
            recheck_source_provider=(
                lambda application_id, candidate_ids=None: (
                    career_library.snapshot_for_analysis(
                        career_source_snapshot(evidence), candidate_ids
                    )
                    if career_library_manifest is not None
                    else career_source_snapshot(evidence)
                )
            ),
            preparation_only=preparation_only,
        )

        from .codex_cli import run_codex_exec

        analysis_module = Analysis(
            flow.root / "analyses",
            runner=flow_match_runner or run_codex_exec,
            source_loader=lambda ids: career_library.snapshot_for_analysis(
                career_source_snapshot(evidence), ids
            ),
            information_provider=lambda: read_information_library(information_library_root),
            analyzer=flow_analyzer,
            adapter_revision=injected_revision,
            refresh_root=flow.root / "match-refreshes",
        )
        flow.configure_analysis(
            analysis_module,
            source_provider=flow_sources,
            benchmark_provider=lambda sources: current_benchmark(
                sources, match_configuration_revision()
            ),
        )
    if worker and flow is None:
        resumes = runtime.resumes = ApplicationResumeStore(
            applications, evidence, worker.store.root / "resumes"
        )
        resumes.career_library = career_library if career_library_manifest is not None else None
        if resume_review_pdf_inspector is not None:
            resumes.pdf_inspector = resume_review_pdf_inspector
        resumes.measurements = worker.store.measurements
    if flow:
        factory = ApplicationResumeStore if flow_resume_factory is None else flow_resume_factory
        if not callable(factory):
            raise ValueError("The resume service factory must be callable.")
        flow_resumes = factory(applications, evidence, flow.root / "resumes")
        if not isinstance(flow_resumes, ApplicationResumeStore):
            raise ValueError("The resume service factory must return an ApplicationResumeStore.")
        runtime.flow_resumes = flow_resumes
        flow_resumes.career_library = (
            career_library if career_library_manifest is not None else None
        )
        if resume_review_pdf_inspector is not None:
            flow_resumes.pdf_inspector = resume_review_pdf_inspector
        if worker:
            flow_resumes.measurements = worker.store.measurements
        flow.configure_materials(
            flow_resumes,
            automatic_author=automatic_resume_author,
            review=review,
            template_config=resume_template_config,
        )
        _configure_measurements(flow, flow_resumes, preparation_only)
        if resume_model_mode is not None:
            flow_resumes.model_mode = resume_model_mode
        if flow_automatic_latex_base is not None:
            flow.callbacks["automatic_latex_base"] = flow_automatic_latex_base
        if worker is not None:
            from .application_single_binding import read_delivered_material_inputs

            worker.store.single_material_source_provider = partial(
                read_delivered_material_inputs, delivery_reader=flow.fixed_writing_inputs
            )
            from .application_single_binding import preflight_target

            flow.configure_worker(
                worker,
                pdf_reader=flow_resumes.pdf,
                target_provider=partial(preflight_target, applications, worker),
            )
        from .application_intake import ApplicationIntakeService

        intake_factory = (
            ApplicationIntakeService if flow_intake_factory is None else flow_intake_factory
        )
        if not callable(intake_factory):
            raise ValueError("The recommendation intake factory must be callable.")
        try:
            options = (
                {"processed_label": application_processed_label}
                if application_processed_label is not None
                else {}
            )
            try:
                runtime.intake = intake_factory(applications, flow.root / "intake", **options)
            except PortalDataError as error:
                if error.code != "gmail_processing_invalid":
                    raise
                # A bad mail setting must not disable documentary reads or capture.
                runtime.intake = intake_factory(applications, flow.root / "intake")
                runtime.intake.mail_processing_error = error.code
        except PortalDataError as error:
            runtime.intake_unavailable = error
        except (OSError, ValueError):
            runtime.intake_unavailable = PortalDataError(
                "intake_unavailable", "推荐读取记录暂不可用，请保留原件并检查状态。", 503
            )
        if preparation_only:
            from .application_material_batch import batch_candidates, select_batch_item

            flow.callbacks["batch_candidates"] = partial(
                batch_candidates, applications, runtime.intake
            )
            flow.callbacks["batch_select"] = partial(
                select_batch_item, applications, runtime.intake
            )
    if worker and worker_fixtures:
        runtime.fixtures = create_fixture_server(
            applications.list_applications(), worker.store.root
        )
        worker.fixture_origin = f"http://127.0.0.1:{runtime.fixtures.server_port}"

    from . import __version__

    load_controller_modules()
    identity = runtime.identity = {
        "session_id": secrets.token_hex(16),
        "engine_revision": loaded_preparation_revision() if preparation_only else None,
        "ui_revision": digest(
            {name: hashlib.sha256(raw).hexdigest() for name, raw in static_files.items()}
        ),
        "version": __version__,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "mode": "preparation" if preparation_only else "application",
    }
    controller_boot = {
        "session_id": identity["session_id"],
        "pid": os.getpid(),
        "mode": identity["mode"],
        "loaded_engine_revision": loaded_runtime_revision("controller"),
        "ui_revision": identity["ui_revision"],
        "python_version": identity["python_version"],
    }
    controller_files = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (PUBLIC_ROOT / "src/career_evidence_graph").rglob("*.py")
        if path.is_file()
    }
    runtime.readiness = ReadinessProbe(
        applications=applications,
        evidence=evidence,
        flow=flow,
        resumes=flow_resumes,
        worker=worker,
        static_root=static_root,
        static_files=static_files,
        controller_boot=controller_boot,
        controller_files=controller_files,
        package_resources=package_resources,
        native_host_identity=native_host_identity,
        native_host_binding=native_host_binding,
        information_library_root=information_library_root,
        legacy_roots=flow_legacy_roots,
        preparation_only=preparation_only,
    )
    if flow:
        from .application_single_binding import validate_write_preflight, write_preflight

        # Single-binding admission owns the preflight and reads Flow through public entries.
        flow.callbacks["write_preflight"] = partial(
            write_preflight,
            flow,
            worker=worker,
            career_root=evidence.root,
            legacy_roots=flow_legacy_roots,
            resumes=flow_resumes,
        )
        flow.callbacks["validate_write_preflight"] = partial(validate_write_preflight, flow)
        if worker:
            worker.validate_write_preflight = flow.callbacks["validate_write_preflight"]
    from .application_flow_view import FlowView

    runtime.flow_view = FlowView(
        runtime,
        analysis_injected=flow_analyzer is not None,
        resume_injected=flow_resume_factory is not None,
    )
    if flow and runtime.intake and worker and not preparation_only:
        from .application_pipeline import ApplicationPipeline

        try:
            # The Pipeline registers its preparation permit before its thread starts.
            runtime.pipeline = ApplicationPipeline(flow, runtime.intake, worker)
        except (PortalDataError, OSError, ValueError, KeyError, TypeError) as error:
            runtime.pipeline_unavailable = (
                error.code if isinstance(error, PortalDataError) else "pipeline_unavailable"
            )
