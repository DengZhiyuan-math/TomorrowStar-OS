"""Local human source versions and read-only adoption of Prism build results."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from ._vendor import job_apply_store as helper
from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest

CONTRACT = "local-material/v1"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _invalid(message="本地材料版本不能核验，请保留当前源与历史终稿。"):
    return PortalDataError("resume_local_version_invalid", message, 409)


def _unavailable(source, notice):
    return {
        "status": "unavailable",
        "before_sha256": _sha(source.encode()),
        "after_sha256": _sha(source.encode()),
        "patches": [],
        "notices": [notice],
        "latex_source": source,
    }


def _client(store):
    from .application_prism import PrismClient

    return store.prism_client if store.prism_client is not None else PrismClient()


class TectonicCompiler:
    """Compile automatic materials directly (decided 2026-10-31); Prism stays the editor.

    The project is copied to a temporary directory, so compiling never writes into it.
    """

    def read_compiled(self, binding):
        from .application_prism import dependency_snapshot

        actual = dependency_snapshot(
            Path(binding["project_root"]), binding["main"], [binding["main"]]
        )
        executable = shutil.which("tectonic")
        if executable is None:
            raise PortalDataError(
                "resume_compiler_unavailable", "未找到 tectonic，暂不能编译 PDF。", 409
            )
        with tempfile.TemporaryDirectory() as work:
            main = Path(work) / actual["main"]
            main.write_bytes((Path(actual["project_root"]) / actual["main"]).read_bytes())
            try:
                run = subprocess.run(
                    [executable, "--untrusted", "--keep-logs", main.name],
                    cwd=work,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            except subprocess.TimeoutExpired as error:
                raise PortalDataError(
                    "resume_export_failed", "PDF 编译超时，源与旧终稿保留。", 409
                ) from error
            log = run.stderr + run.stdout
            pdf = main.with_suffix(".pdf")
            if run.returncode != 0 or not pdf.is_file():
                raise PortalDataError("resume_export_failed", "PDF 编译失败，源与旧终稿保留。", 409)
            raw = pdf.read_bytes()
        # A glyph missing from the font silently drops text from the PDF.
        missing = sorted(set(re.findall(r"could not represent character \"(.)\"", log)))
        diagnostics = [
            {"severity": "error", "message": f"missing glyph {char!r}"} for char in missing
        ]
        result = {
            "schema_version": "prism-build-result/v1",
            "status": "complete",
            "id": uuid4().hex,
            "main": actual["main"],
            "builder": "tectonic",
            "exit": run.returncode,
            "pdf_updated": True,
            "cancelled": False,
            "timed_out": False,
            "diagnostics": diagnostics,
            "files": actual["files"],
            "pdf_sha256": _sha(raw),
        }
        return {
            "pdf": raw,
            "binding": actual,
            "build": result | {"source_revision": actual["source_revision"]},
        }


def _edit_provenance(store, binding):
    reader = getattr(_client(store), "edit_provenance", None)
    fallback = {"kind": "source-diff/v1", "source_revision": binding["source_revision"]}
    if reader is None:
        return fallback
    try:
        value = reader(binding)
        if (
            not isinstance(value, dict)
            or value.get("source_revision") != binding["source_revision"]
        ):
            return fallback
        return deepcopy(value)
    except (OSError, PortalDataError):
        return fallback


def _successful_build(build, binding, raw):
    return (
        isinstance(build, dict)
        and build.get("schema_version") == "prism-build-result/v1"
        and build.get("status") == "complete"
        and isinstance(build.get("id"), str)
        and re.fullmatch(r"[a-f0-9]{32}", build["id"]) is not None
        and build.get("main") == binding["main"]
        and type(build.get("exit")) is int
        and build["exit"] == 0
        and build.get("pdf_updated") is True
        and build.get("cancelled") is False
        and build.get("timed_out") is False
        and isinstance(build.get("diagnostics"), list)
        and all(
            isinstance(item, dict) and item.get("severity") != "error"
            for item in build["diagnostics"]
        )
        and build.get("files") == binding["files"]
        and build.get("pdf_sha256") == _sha(raw)
    )


def _binding(checkpoint):
    from .application_prism import dependency_snapshot

    # A pending human version captures the edited text, not a claim that the
    # complete project has compiled. Final PDF archives use the result's full
    # recorder dependency set instead (see capture).
    return dependency_snapshot(
        Path(checkpoint["project_root"]), checkpoint["main"], [checkpoint["main"]]
    )


def session(store, identifier):
    try:
        value = json.loads(store._read_version_file(identifier, "edit-session.json", 12_000_000))
        parent, sha = store._draft_document(value["parent_draft_id"])
        if (
            value["id"] != identifier
            or value["contract"] != CONTRACT
            or value["parent_draft_sha256"] != sha
            or value["task_inputs"] != parent["task_inputs"]
            or value["source_checkpoint"]["project_root"]
            != parent["source_checkpoint"]["project_root"]
            or value["source_checkpoint"]["main"] != parent["source_checkpoint"]["main"]
            or value["status"]
            not in {
                "editing",
                "finishing",
                "complete",
                "proofreading_unavailable",
                "source_changed",
            }
        ):
            raise ValueError("edit session binding")
        if value.get("result_draft_id") is not None and (
            not isinstance(value["result_draft_id"], str)
            or not re.fullmatch(r"[a-f0-9]{32}", value["result_draft_id"])
        ):
            raise ValueError("edit result identifier")
        for captured in (
            value.get("captured_binding"),
            (value.get("finish_outcome") or {}).get("binding"),
        ):
            if captured is not None and any(
                captured[key] != parent["source_checkpoint"][key]
                for key in ("project_root", "main")
            ):
                raise ValueError("captured edit source binding")
        if value.get("draft_id"):
            result, result_sha = store._draft_document(value["draft_id"])
            manual = result.get("manual_source") or {}
            if (
                value.get("draft_sha256") != result_sha
                or result["application_id"] != parent["application_id"]
                or result["task_inputs"] != value["task_inputs"]
                or manual.get("parent_draft_id") != value["parent_draft_id"]
                or manual.get("parent_draft_sha256") != value["parent_draft_sha256"]
            ):
                raise ValueError("edit session result lineage")
        return value
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise _invalid() from error


def begin(store, draft_id, draft_sha256, *, task_inputs):
    from .application_prism import archive_sources

    with store.applications.write_lock():
        parent, actual_sha = store._draft_document(draft_id)
        if actual_sha != draft_sha256 or parent["task_inputs"] != task_inputs:
            raise _invalid("人工编辑必须接回指定的原材料版本。")
        if parent.get("origin") not in {"generated_latex", "existing_latex"}:
            raise _invalid()
        binding = _binding(parent["source_checkpoint"])
        archive = archive_sources(binding)
        url = _client(store).open(binding)
        identifier = uuid4().hex
        directory = store.root / identifier
        directory.mkdir(mode=0o700)
        (directory / "opened-sources.json").write_bytes(archive)
        value = {
            "id": identifier,
            "contract": CONTRACT,
            "status": "editing",
            "parent_draft_id": draft_id,
            "parent_draft_sha256": actual_sha,
            "task_inputs": deepcopy(task_inputs),
            "editor_url": url,
            "opened_edit_provenance": _edit_provenance(store, binding),
            "project_root": binding["project_root"],
            "main": binding["main"],
            "source_checkpoint": binding | {"archive_sha256": _sha(archive)},
        }
        helper.atomic_write_json(directory / "edit-session.json", value)
        return deepcopy(value)


def _content_parent(store, parent, parent_sha):
    """Keep the last rebuildable content link across an unmerged human version."""
    if (parent.get("resume_content") or {}).get("schema_version") == "resume-template-content/v1":
        return parent, parent_sha
    reference = parent.get("parent_content_ref")
    if reference:
        saved, saved_sha = store._draft_document(reference["draft_id"])
        content = saved.get("resume_content") or {}
        if (
            saved_sha != reference["draft_sha256"]
            or content.get("revision") != reference["content_revision"]
            or content.get("template_revision") != reference["template_revision"]
        ):
            raise _invalid("人工源保留的内容版本链接不能核验。")
        return saved, saved_sha
    return parent, parent_sha


def _omitted_ids(value):
    if (
        not isinstance(value, list)
        or any(not isinstance(identifier, str) or not identifier for identifier in value)
        or len(value) != len(set(value))
    ):
        raise ValueError("retained experience omissions are invalid")
    return set(value)


def _manual_omissions(parent, parent_content, content):
    present = {row["id"] for row in content["experiences"]}
    previous = {row["id"] for row in parent_content["experiences"]}
    return sorted(
        (_omitted_ids(parent.get("retained_omitted_experience_ids", [])) | previous) - present
    )


def _save_draft(
    store,
    parent,
    parent_sha,
    binding,
    archive,
    before,
    record,
    *,
    identifier=None,
    edit_provenance=None,
):
    from .application_prism import validate_archive

    identifier = identifier or uuid4().hex
    directory = store.root / identifier
    if directory.is_symlink():
        raise _invalid()
    if (directory / "draft-integrity.json").exists():
        saved = store.draft(identifier)
        if (
            saved["manual_source"]["parent_draft_sha256"] != parent_sha
            or saved["source_checkpoint"] != binding | {"archive_sha256": _sha(archive)}
            or saved["proofreading"] != record
        ):
            raise _invalid("已保存人工版本与返回结果不符。")
        return saved
    directory.mkdir(mode=0o700, exist_ok=True)
    source = validate_archive(archive, binding).decode("utf-8")
    draft = deepcopy(parent)
    # A previous AI review is provenance, never approval of new human wording.
    for key in (
        "generation_contract",
        "content_mapping",
        "content_template",
        "content_reconciliation",
        "parent_content_ref",
        "resume_content",
        "retained_content",
        "content_revision",
        "render_manifest",
        "template_revision",
        "renderer_revision",
        "item_ranges",
        "final_review",
        "writing_plan",
        "block_mapping",
        "group_session",
        "group_parent_id",
        "group_preview",
        "group_context_revision",
        "verified_unchanged_group_ids",
    ):
        draft.pop(key, None)
    draft.update(
        id=identifier,
        origin="generated_latex",
        material_version_contract=CONTRACT,
        review_status="review_required",
        language="en",
        factual_review="human_edited",
        source_checkpoint=binding | {"archive_sha256": _sha(archive)},
        latex_source=source,
        review_groups=[],
        omitted_groups=[],
        retained_omissions=deepcopy(
            parent.get("retained_omissions", []) + parent.get("omitted_groups", [])
        ),
        verification_queue=[],
        manual_source={
            "actor": "user",
            "scope": "prism_return",
            "parent_draft_id": parent["id"],
            "parent_draft_sha256": parent_sha,
            "source_sha256": _sha(before.encode()),
            **(
                {"edit_provenance": deepcopy(edit_provenance)}
                if edit_provenance is not None
                else {}
            ),
        },
        proofreading=deepcopy(record),
    )
    content_parent, content_parent_sha = _content_parent(store, parent, parent_sha)
    parent_content = content_parent.get("resume_content") or {}
    if parent_content.get("schema_version") == "resume-template-content/v1":
        from .application_content_reconcile import reconcile_content
        from .application_resume_render import render_resume

        template = _content_template(store, content_parent)
        reconciliation = reconcile_content(
            parent_content,
            template,
            source,
            "prism:" + digest(draft["manual_source"]),
            render_manifest=_content_manifest(content_parent, template),
        )
        draft["content_reconciliation"] = reconciliation
        draft["parent_content_ref"] = {
            "draft_id": content_parent["id"],
            "draft_sha256": content_parent_sha,
            "content_revision": parent_content["revision"],
            "template_revision": parent_content["template_revision"],
        }
        if reconciliation["status"] in {"mapped", "unchanged"}:
            content = reconciliation["content"]
            rendered = render_resume(content, template=template)
            ranges = {key: list(value) for key, value in rendered.ranges.items()}
            draft.update(
                resume_content=deepcopy(content),
                content_revision=content["revision"],
                template_revision=rendered.template_revision,
                renderer_revision=rendered.renderer_revision,
                item_ranges=ranges,
                render_manifest={
                    "schema_version": "resume-render-manifest/v1",
                    "content_revision": rendered.content_revision,
                    "template_revision": rendered.template_revision,
                    "renderer_revision": rendered.renderer_revision,
                    "tex_sha256": _sha(rendered.tex.encode()),
                    "item_ranges": ranges,
                },
            )
            from .application_writing import _retained_structure_scopes

            draft["retained_protected_scopes"] = _retained_structure_scopes(store, draft, content)
            draft["retained_omitted_experience_ids"] = _manual_omissions(
                parent, parent_content, content
            )
            (directory / "content.json").write_text(
                json.dumps(content, ensure_ascii=False), encoding="utf-8"
            )
            helper.atomic_write_json(directory / "render-manifest.json", draft["render_manifest"])
            if content_parent.get("origin") == "existing_latex":
                from .application_prism import archive_sources, source_snapshot

                # Publish the actual verified mapping template, never the rendered
                # imported document or a fabricated generation checkpoint.
                template_root = directory / "template"
                if template_root.is_symlink() or (template_root / "main.tex").is_symlink():
                    raise _invalid()
                template_root.mkdir(mode=0o700, exist_ok=True)
                (template_root / "main.tex").write_text(template, encoding="utf-8")
                base = source_snapshot(
                    template_root, "main.tex", source_policy="generated-latex-project/v1"
                )
                base_archive = archive_sources(base)
                draft["base_checkpoint"] = base | {"archive_sha256": _sha(base_archive)}
            else:
                draft["base_checkpoint"] = deepcopy(content_parent["base_checkpoint"])
                base_archive = store._read_version_file(
                    content_parent["id"], "base-sources.json", 48_000_000
                )
            (directory / "base-sources.json").write_bytes(base_archive)
    draft.setdefault("generation_sources", [])
    draft.setdefault("information_library_revision", None)
    draft.setdefault("base_checkpoint", parent["source_checkpoint"])
    if parent.get("final_review"):
        draft["upstream_final_review"] = deepcopy(parent["final_review"])
    (directory / "human-source.tex").write_text(before, encoding="utf-8")
    (directory / "latex-sources.json").write_bytes(archive)
    helper.atomic_write_json(directory / "draft.json", draft)
    helper.atomic_write_json(
        directory / "draft-integrity.json",
        {
            "schemaVersion": 1,
            "id": identifier,
            "sha256": _sha((directory / "draft.json").read_bytes()),
        },
    )
    return store.draft(identifier)


def _needs_recheck():
    return PortalDataError("prism_edit_needs_recheck", "返回校对尚未核验，不会自动重试。", 409)


def _finish_proofread(store, directory, before, *, resumed):
    """Recover a saved response through the same text-only proofreading guards."""
    from types import SimpleNamespace

    from .application_proofread import proofread, validate_record

    result_path = directory / "proofread-result.json"
    response_path = directory / "proofread-response.json"
    if result_path.exists():
        record = json.loads(
            store._read_version_file(directory.name, "proofread-result.json", 4_000_000)
        )
        validate_record(before, record)
        return record
    if response_path.exists():
        response = json.loads(
            store._read_version_file(directory.name, "proofread-response.json", 4_000_000)
        )
        payload = {key: value for key, value in response.items() if key != "revision"}
        if response.get("revision") != digest(payload) or response.get("source_sha256") != _sha(
            before.encode()
        ):
            raise _invalid("文字校对响应与捕获原文不符。")
        replayed = []

        def runner(config, prompt, **kwargs):
            if response["prompt_sha256"] != _sha(prompt.encode()) or response[
                "schema_sha256"
            ] != _sha(Path(config.output_schema).read_bytes()):
                replayed.append(False)
                raise ValueError("proofread_response_binding")
            replayed.append(True)
            return SimpleNamespace(structured_result=response["structured_result"])

        record = proofread(
            SimpleNamespace(model_runner=runner),
            directory / ("proofread-recovery-" + uuid4().hex),
            before,
        )
        if replayed != [True]:
            raise _invalid("文字校对响应的请求绑定不能核验。")
        helper.atomic_write_json(result_path, record)
        return record
    if resumed:
        raise _needs_recheck()

    def runner(config, prompt, **kwargs):
        result = store.model_runner(config, prompt, **kwargs)
        response = {
            "source_sha256": _sha(before.encode()),
            "prompt_sha256": _sha(prompt.encode()),
            "schema_sha256": _sha(Path(config.output_schema).read_bytes()),
            "structured_result": result.structured_result,
        }
        helper.atomic_write_json(response_path, response | {"revision": digest(response)})
        return result

    return proofread(SimpleNamespace(model_runner=runner), directory, before)


def _proofread_scope(store, parent, parent_sha, before, record):
    """Fixed template prose is documentary data, outside automatic text patches."""
    if not record["patches"]:
        return record
    content_parent, _ = _content_parent(store, parent, parent_sha)
    content = content_parent.get("resume_content") or {}
    if content.get("schema_version") != "resume-template-content/v1":
        return record
    from .application_content_reconcile import reconcile_content
    from .application_resume_render import render_resume

    template = _content_template(store, content_parent)
    reconciled = reconcile_content(
        content,
        template,
        before,
        "prism:proofread-scope",
        render_manifest=_content_manifest(content_parent, template),
    )
    if reconciled["status"] in {"mapped", "unchanged"}:
        current = reconciled["content"]
        rendered = render_resume(current, template=template)
        items = (
            current["summary"]
            + current["skills"]
            + [item for experience in current["experiences"] for item in experience["items"]]
        )
        if current.get("headline"):
            items.append(current["headline"])
        ranges = [rendered.ranges[item["id"]] for item in items]
        if all(
            any(start <= patch["start"] < patch["end"] <= end for start, end in ranges)
            for patch in record["patches"]
        ):
            return record
    return _unavailable(before, "文字校对补丁超出可核验的可变内容；固定模板和人工源均已保留。")


def _finish_outcome(
    store, directory, value, parent, parent_sha, before, binding, archive, record, status
):
    result = _save_draft(
        store,
        parent,
        parent_sha,
        binding,
        archive,
        before,
        record,
        identifier=value.get("result_draft_id"),
        edit_provenance=value.get("captured_edit_provenance"),
    )
    value.update(
        status=status,
        draft_id=result["id"],
        draft_sha256=result["draft_sha256"],
        notices=record["notices"],
        patches=record["patches"],
        captured_source_revision=binding["source_revision"],
    )
    helper.atomic_write_json(directory / "edit-session.json", value)
    return result | {"prism_edit": deepcopy(value)}


def finish(store, identifier):
    from .application_prism import archive_sources, refresh_source_snapshot, validate_archive

    with store.applications.write_lock():
        value = session(store, identifier)
        if value.get("draft_id"):
            return store.draft(value["draft_id"]) | {"prism_edit": value}
        resumed = value["status"] == "finishing"
        if value["status"] not in {"editing", "finishing"}:
            raise _needs_recheck()
        parent, parent_sha = store._draft_document(value["parent_draft_id"])
        directory = store.root / identifier
        if resumed:
            if "captured_binding" not in value:
                raise _needs_recheck()
            binding = value["captured_binding"]
            archive = store._read_version_file(identifier, "human-sources.json", 48_000_000)
            before = store._read_version_file(identifier, "human-source.tex", 4_000_000).decode()
            if (
                _sha(archive) != value["captured_archive_sha256"]
                or validate_archive(archive, binding).decode() != before
            ):
                raise _invalid("人工返回捕获归档不能核验。")
        else:
            binding = _binding(value["source_checkpoint"])
            archive = archive_sources(binding)
            before = validate_archive(archive, binding).decode("utf-8")
            (directory / "human-sources.json").write_bytes(archive)
            (directory / "human-source.tex").write_text(before, encoding="utf-8")
            value.update(
                status="finishing",
                captured_source_revision=binding["source_revision"],
                captured_binding=deepcopy(binding),
                captured_archive_sha256=_sha(archive),
                result_draft_id=uuid4().hex,
                captured_edit_provenance=_edit_provenance(store, binding),
            )
            helper.atomic_write_json(directory / "edit-session.json", value)
        if value.get("finish_outcome"):
            outcome = value["finish_outcome"]
            saved_archive = store._read_version_file(
                identifier, "finished-sources.json", 48_000_000
            )
            saved_binding = outcome["binding"]
            from .application_proofread import validate_record

            if (
                _sha(saved_archive) != outcome["archive_sha256"]
                or validate_archive(saved_archive, saved_binding).decode()
                != validate_record(before, outcome["record"])
                or outcome["status"]
                not in {"complete", "proofreading_unavailable", "source_changed"}
            ):
                raise _invalid("已保存人工版本的采用结果不能核验。")
            return _finish_outcome(
                store,
                directory,
                value,
                parent,
                parent_sha,
                before,
                saved_binding,
                saved_archive,
                outcome["record"],
                outcome["status"],
            )
    multiple_documents = any(
        name != binding["main"] and Path(name).suffix == ".tex" for name in binding["files"]
    ) or re.search(r"\\(?:input|include|subfile|import)\b", before)
    record = (
        _unavailable(before, "当前文字校对只支持独立主文档；多文件正文已保留，未宣称完成校对。")
        if multiple_documents
        else _finish_proofread(store, directory, before, resumed=resumed)
    )
    record = _proofread_scope(store, parent, parent_sha, before, record)
    with store.applications.write_lock():
        if session(store, identifier) != value:
            raise _invalid("编辑接续已变化，人工源与校对结果均已保留。")
        captured_binding, captured_archive = deepcopy(binding), archive
        status = "complete" if record["status"] == "complete" else "proofreading_unavailable"
        intent_path = directory / "proofread-write-intent.json"
        receipt_path = directory / "proofread-write-receipt.json"
        try:
            current_binding = _binding(binding)
            current_archive = archive_sources(current_binding)
            current_source = validate_archive(current_archive, current_binding).decode()
            unchanged = refresh_source_snapshot(binding) == binding
        except PortalDataError:
            current_source, unchanged = None, False
        after = record["latex_source"]
        if intent_path.exists():
            intent = json.loads(
                store._read_version_file(identifier, "proofread-write-intent.json", 128_000)
            )
            if intent != {
                "before_revision": binding["source_revision"],
                "after_sha256": _sha(after.encode()),
            }:
                raise _invalid("局部补丁写入意图不能核验。")
            if receipt_path.exists():
                receipt = json.loads(
                    store._read_version_file(identifier, "proofread-write-receipt.json", 128_000)
                )
                written_archive = store._read_version_file(
                    identifier, "proofread-written-sources.json", 48_000_000
                )
                written_binding = receipt["binding"]
                if (
                    any(
                        written_binding[key] != captured_binding[key]
                        for key in ("project_root", "main")
                    )
                    or _sha(written_archive) != receipt["archive_sha256"]
                    or validate_archive(written_archive, written_binding).decode() != after
                ):
                    raise _invalid("已写入局部补丁的归档不能核验。")
                binding, archive = written_binding, written_archive
                if current_source != after:
                    status = "source_changed"
                    record = deepcopy(record)
                    record["notices"].append("补丁写入后已有新人工修改；已保留校对版本和当前源。")
            elif current_source == after:
                binding, archive = current_binding, current_archive
                (directory / "proofread-written-sources.json").write_bytes(archive)
                helper.atomic_write_json(
                    receipt_path, {"binding": binding, "archive_sha256": _sha(archive)}
                )
            elif unchanged:
                raise _needs_recheck()
            else:
                status = "source_changed"
                record = _unavailable(before, "局部补丁未安全接回，人工源和原校对结果已保留。")
        elif not unchanged:
            status = "source_changed"
            record = _unavailable(before, "校对期间源有新修改，已保留当前源，未应用补丁。")
        elif after != before:
            writer = getattr(_client(store), "apply_proofread", None)
            try:
                if writer is None:
                    raise PortalDataError(
                        "prism_conditional_save_unavailable", "Prism 暂无安全补丁接口。", 409
                    )
                helper.atomic_write_json(
                    intent_path,
                    {
                        "before_revision": binding["source_revision"],
                        "after_sha256": _sha(after.encode()),
                    },
                )
                writer(binding, before, after)
                binding = _binding(binding)
                archive = archive_sources(binding)
                if validate_archive(archive, binding).decode() != after:
                    raise _invalid("补丁保存后又有人工修改，未采用迟到结果。")
                (directory / "proofread-written-sources.json").write_bytes(archive)
                helper.atomic_write_json(
                    receipt_path, {"binding": binding, "archive_sha256": _sha(archive)}
                )
            except PortalDataError:
                status = "source_changed"
                binding, archive = captured_binding, captured_archive
                record = _unavailable(before, "局部补丁未安全接回，人工源和原校对结果已保留。")
        (directory / "finished-sources.json").write_bytes(archive)
        value["finish_outcome"] = {
            "binding": deepcopy(binding),
            "archive_sha256": _sha(archive),
            "record": deepcopy(record),
            "status": status,
        }
        helper.atomic_write_json(directory / "edit-session.json", value)
        return _finish_outcome(
            store,
            directory,
            value,
            parent,
            parent_sha,
            before,
            binding,
            archive,
            record,
            status,
        )


def validate(store, draft):
    from .application_prism import validate_archive
    from .application_proofread import validate_record

    parent_id = draft["manual_source"]["parent_draft_id"]
    parent, parent_sha = store._draft_document(parent_id)
    checkpoint = draft["source_checkpoint"]
    archive = store._read_version_file(draft["id"], "latex-sources.json", 48_000_000)
    before = store._read_version_file(draft["id"], "human-source.tex", 4_000_000).decode()
    source = validate_archive(archive, checkpoint).decode()
    if (
        draft["material_version_contract"] != CONTRACT
        or draft["manual_source"]["parent_draft_sha256"] != parent_sha
        or draft["manual_source"]["source_sha256"] != _sha(before.encode())
        or draft["application_id"] != parent["application_id"]
        or draft["task_inputs"] != parent["task_inputs"]
        or checkpoint["project_root"] != parent["source_checkpoint"]["project_root"]
        or checkpoint["main"] != parent["source_checkpoint"]["main"]
        or checkpoint.get("source_policy") != "prism-dependencies/v1"
        or _sha(archive) != checkpoint["archive_sha256"]
        or source != draft["latex_source"]
        or validate_record(before, draft["proofreading"]) != source
        or _proofread_scope(store, parent, parent_sha, before, draft["proofreading"])
        != draft["proofreading"]
        or draft.get("retained_omissions", [])
        != parent.get("retained_omissions", []) + parent.get("omitted_groups", [])
    ):
        raise ValueError("local draft lineage mismatch")
    content_parent, content_parent_sha = _content_parent(store, parent, parent_sha)
    parent_content = content_parent.get("resume_content") or {}
    if parent_content.get("schema_version") == "resume-template-content/v1":
        from .application_content_reconcile import reconcile_content

        template = _content_template(store, content_parent)
        expected = reconcile_content(
            parent_content,
            template,
            source,
            "prism:" + digest(draft["manual_source"]),
            render_manifest=_content_manifest(content_parent, template),
        )
        expected_ref = {
            "draft_id": content_parent["id"],
            "draft_sha256": content_parent_sha,
            "content_revision": parent_content["revision"],
            "template_revision": parent_content["template_revision"],
        }
        if (
            draft.get("content_reconciliation") != expected
            or draft.get("parent_content_ref") != expected_ref
        ):
            raise ValueError("human content reconciliation differs")
        if expected["status"] in {"mapped", "unchanged"}:
            from .application_writing import _retained_structure_scopes

            if content_parent.get("origin") == "existing_latex":
                base_revision = {
                    "main": "main.tex",
                    "files": {"main.tex": _sha(template.encode())},
                    "source_policy": "generated-latex-project/v1",
                }
                base_archive = store._read_version_file(
                    draft["id"], "base-sources.json", 48_000_000
                )
                expected_base = {
                    **base_revision,
                    "project_root": str(store.root / draft["id"] / "template"),
                    "source_revision": digest(base_revision),
                    "archive_sha256": _sha(base_archive),
                }
            else:
                expected_base = content_parent["base_checkpoint"]
            if draft.get("base_checkpoint") != expected_base:
                raise ValueError("human content template provenance differs")
            scope_basis = {
                **draft,
                "retained_protected_scopes": parent.get("retained_protected_scopes", []),
            }
            expected_scopes = _retained_structure_scopes(store, scope_basis, expected["content"])
            if draft.get("retained_protected_scopes", []) != expected_scopes:
                raise ValueError("human list structure protection differs from parent and edit")
            if draft.get("retained_omitted_experience_ids", []) != _manual_omissions(
                parent, parent_content, expected["content"]
            ):
                raise ValueError("human experience omissions differ from parent and edit")
            if _content_template(store, draft) != template:
                raise ValueError("human content template differs from parent")
            rendered, manifest = _rendered_content(draft, template=template)
            saved = json.loads(store._read_version_file(draft["id"], "content.json", 2_000_000))
            saved_manifest = json.loads(
                store._read_version_file(draft["id"], "render-manifest.json", 2_000_000)
            )
            if (
                draft.get("resume_content") != expected["content"]
                or saved != expected["content"]
                or draft.get("content_revision") != rendered.content_revision
                or draft.get("render_manifest") != manifest
                or saved_manifest != manifest
            ):
                raise ValueError("human content version differs")
        elif any(key in draft for key in ("resume_content", "content_revision", "render_manifest")):
            raise ValueError("unmerged human source claims rebuildable content")
        elif draft.get("retained_protected_scopes", []) != parent.get(
            "retained_protected_scopes", []
        ):
            raise ValueError("unmerged human source changed inherited list protection")
        elif draft.get("retained_omitted_experience_ids", []) != parent.get(
            "retained_omitted_experience_ids", []
        ):
            raise ValueError("unmerged human source changed inherited experience omissions")
    elif any(
        key in draft for key in ("resume_content", "content_reconciliation", "parent_content_ref")
    ):
        raise ValueError("manual content has no corresponding parent")


def capture(store, draft_id, draft_sha256, *, task_inputs, export_id):
    from .application_prism import archive_sources, refresh_source_snapshot, validate_archive

    draft, actual_sha = store._draft_document(draft_id)
    if actual_sha != draft_sha256 or draft["task_inputs"] != task_inputs:
        raise _invalid()
    if not isinstance(export_id, str) or not re.fullmatch(r"[a-f0-9]{32}", export_id):
        raise _invalid()
    directory = store.root / export_id
    if directory.exists():
        saved = read_export(store, export_id)
        if (
            saved["draft_id"] != draft_id
            or saved["draft_sha256"] != draft_sha256
            or saved["task_inputs"] != task_inputs
        ):
            raise _invalid("同一结果读取编号不能对应另一材料版本。")
        return saved
    client = store.prism_client if store.prism_client is not None else TectonicCompiler()
    reader = getattr(client, "read_compiled", None)
    if reader is None:
        raise PortalDataError(
            "prism_result_unavailable", "Prism 暂无可核验的自动编译结果接口。", 409
        )
    compiled = reader(_binding(draft["source_checkpoint"]))
    binding, build, raw = compiled["binding"], compiled["build"], compiled["pdf"]
    defects = [
        row.get("message", "")
        for row in (build.get("diagnostics") if isinstance(build.get("diagnostics"), list) else [])
        if isinstance(row, dict) and row.get("severity") == "error"
    ]
    if defects:
        # A known refusal of this source, not an unknown build result.
        raise PortalDataError(
            "resume_pdf_source_defect",
            "PDF 会缺失内容（" + "；".join(defects) + "），旧终稿保留。",
            409,
        )
    archive = archive_sources(binding)
    source = validate_archive(archive, binding)
    if (
        binding.get("source_policy") != "prism-dependencies/v1"
        or binding["project_root"] != draft["source_checkpoint"]["project_root"]
        or binding["main"] != draft["source_checkpoint"]["main"]
        or source.decode() != draft["latex_source"]
        or not _successful_build(build, binding, raw)
        or refresh_source_snapshot(binding) != binding
    ):
        raise PortalDataError(
            "resume_export_needs_recheck", "自动结果与当前源不对应，旧终稿保留。", 409
        )
    store._validate_export_pdf(raw, store.pdf_inspector)
    directory.mkdir(mode=0o700)
    intent = {
        "schemaVersion": 1,
        "status": "pending",
        "id": export_id,
        "material_version_contract": CONTRACT,
        "draft_id": draft_id,
        "draft_sha256": draft_sha256,
        "task_inputs": deepcopy(task_inputs),
        "application_id": draft["application_id"],
        "application_revision": draft["application_revision"],
        "analysis_binding": deepcopy(draft["analysis_binding"]),
        "resume_configuration_revision": digest(draft["generation_policy"]),
        "export_configuration": {"kind": "prism-automatic-result", "contract": CONTRACT},
        "prism": binding,
        "latex_sha256": _sha(source),
        "latex_archive_sha256": _sha(archive),
        "automatic_materials": True,
    }
    if draft.get("content_reconciliation"):
        intent.update(
            content_reconciliation_revision=digest(draft["content_reconciliation"]),
            parent_content_ref=deepcopy(draft["parent_content_ref"]),
            content_revision=draft.get("content_revision"),
            template_revision=draft.get("template_revision"),
            renderer_revision=draft.get("renderer_revision"),
        )
    intent["export_configuration_revision"] = digest(intent["export_configuration"])
    helper.atomic_write_json(directory / "export-intent.json", intent)
    (directory / "resume.tex").write_bytes(source)
    (directory / "resume.pdf").write_bytes(raw)
    (directory / "latex-sources.json").write_bytes(archive)
    helper.atomic_write_json(directory / "prism-build.json", build)
    if refresh_source_snapshot(binding) != binding:
        raise PortalDataError(
            "resume_export_needs_recheck", "结果保存期间源变化，旧终稿保留。", 409
        )
    helper.atomic_write_json(
        directory / "export.json",
        intent
        | {
            "status": "complete",
            "pdf_sha256": _sha(raw),
            "prism_build_sha256": _sha((directory / "prism-build.json").read_bytes()),
        },
    )
    return read_export(store, export_id)


def read_export(store, identifier):
    from .application_prism import validate_archive

    try:
        intent = json.loads(store._read_version_file(identifier, "export-intent.json", 128_000))
        manifest_raw = store._read_version_file(identifier, "export.json", 128_000)
        manifest = json.loads(manifest_raw)
        draft, sha = store._draft_document(intent["draft_id"])
        if draft.get("content_reconciliation") and (
            intent.get("content_reconciliation_revision") != digest(draft["content_reconciliation"])
            or intent.get("parent_content_ref") != draft["parent_content_ref"]
            or intent.get("content_revision") != draft.get("content_revision")
            or intent.get("template_revision") != draft.get("template_revision")
            or intent.get("renderer_revision") != draft.get("renderer_revision")
        ):
            raise ValueError("local PDF content binding differs")
        raw = store._read_version_file(identifier, "resume.pdf", 700_000)
        source = store._read_version_file(identifier, "resume.tex", 4_000_000)
        archive = store._read_version_file(identifier, "latex-sources.json", 48_000_000)
        build_raw = store._read_version_file(identifier, "prism-build.json", 128_000)
        build = json.loads(build_raw)
        if (
            intent["material_version_contract"] != CONTRACT
            or intent["id"] != identifier
            or intent["status"] != "pending"
            or manifest
            != intent
            | {
                "status": "complete",
                "pdf_sha256": _sha(raw),
                "prism_build_sha256": _sha(build_raw),
            }
            or sha != intent["draft_sha256"]
            or draft["task_inputs"] != intent["task_inputs"]
            or draft["application_id"] != intent["application_id"]
            or draft["application_revision"] != intent["application_revision"]
            or draft["analysis_binding"] != intent["analysis_binding"]
            or digest(draft["generation_policy"]) != intent["resume_configuration_revision"]
            or intent["automatic_materials"] is not True
            or digest(intent["export_configuration"]) != intent["export_configuration_revision"]
            or _sha(archive) != intent["latex_archive_sha256"]
            or validate_archive(archive, intent["prism"]) != source
            or source.decode() != draft["latex_source"]
            or _sha(source) != intent["latex_sha256"]
            or not _successful_build(build, intent["prism"], raw)
            or not 1 <= len(raw) <= 700_000
            or not raw.startswith(b"%PDF-")
        ):
            raise ValueError("local PDF receipt mismatch")
        return {
            "kind": "pdf",
            "id": identifier,
            "application_id": draft["application_id"],
            "revision": draft["application_revision"],
            "draft_id": draft["id"],
            "draft_sha256": sha,
            "task_inputs": intent["task_inputs"],
            "pdf_sha256": _sha(raw),
            "export_manifest_sha256": _sha(manifest_raw),
            "resume_configuration_revision": intent["resume_configuration_revision"],
            "export_configuration_revision": intent["export_configuration_revision"],
            "filename": f"job-resume-{identifier[:8]}.pdf",
            "file_base64": base64.b64encode(raw).decode(),
            "preview_url": f"/api/resumes/{identifier}/pdf",
            "items": draft["items"],
            "limitations": draft["limitations"],
            "context_count": len(draft["context"]),
            "model_mode": draft["model_mode"],
            **store._source_review(draft),
            "prism_source_revision": intent["prism"]["source_revision"],
            "material_version_contract": CONTRACT,
            "automatic_materials": True,
        }
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, PortalDataError) as error:
        raise PortalDataError(
            "resume_export_needs_recheck", "材料归档或 PDF 完整性不能核验。", 409
        ) from error


CONTENT_CONTRACT = "content-writing/v1"


def _content_template(store, state):
    """Read fixed TeX only inside the program from its immutable source archive."""
    from .application_prism import validate_archive

    content = state.get("resume_content") or state.get("writing_plan") or {}
    if content.get("schema_version") not in {
        "resume-template-plan/v1",
        "resume-template-content/v1",
    }:
        return None
    if state.get("origin") == "existing_latex":
        store._validate_imported_latex(state)
        return state["content_template"]
    base = state.get("base_checkpoint") or state["request"]["latex_base"]
    archive = store._read_version_file(state["id"], "base-sources.json", 48_000_000)
    if _sha(archive) != state.get("base_sha256", base.get("archive_sha256")):
        raise _invalid("固定模板归档已变化。")
    template = validate_archive(archive, base).decode("utf-8")
    if digest(template) != content["template_revision"]:
        raise _invalid("固定模板版本与内容计划不符。")
    return template


def _content_manifest(state, template):
    """Adapt only the independently verified imported manifest to reconciliation."""
    if state.get("origin") == "existing_latex":
        return _rendered_content(state, template=template)[1]
    return state.get("render_manifest")


def _rendered_content(plan, *, template=None):
    from .application_resume_render import render_resume, symbols_for

    content = plan["resume_content"]
    rendered = render_resume(
        content,
        plan["template_revision"],
        template=template,
        symbols=symbols_for(plan["renderer_revision"]),
    )
    ranges = {key: list(value) for key, value in rendered.ranges.items()}
    if (
        plan["latex_source"] != rendered.tex
        or plan["renderer_revision"] != rendered.renderer_revision
        or plan["item_ranges"] != ranges
    ):
        raise _invalid("内容版本与固定模板渲染结果不符。")
    manifest = {
        "schema_version": "resume-render-manifest/v1",
        "content_revision": rendered.content_revision,
        "template_revision": rendered.template_revision,
        "renderer_revision": rendered.renderer_revision,
        "tex_sha256": _sha(rendered.tex.encode()),
        "item_ranges": ranges,
    }
    return rendered, manifest


def _validate_content_scope(content, writing_plan, retained=None, *, protected_scopes=None):
    from .application_resume_content import validate_content, validate_plan

    raw_plan = {key: value for key, value in writing_plan.items() if key != "revision"}
    if "revision" in writing_plan and writing_plan["revision"] != digest(raw_plan):
        raise ValueError("Content writing plan revision differs")
    planned = validate_plan(raw_plan).model_dump(mode="json")
    content = validate_content(content).model_dump(mode="json")
    fixed = (
        ("application_id", "template_revision")
        if "template_revision" in planned
        else ("application_id", "profile", "education")
    )
    if any(content.get(key) != planned[key] for key in fixed):
        raise ValueError("Fixed template or identity binding differs from delivered plan")
    if [row["id"] for row in content["experiences"]] != [
        row["experience_id"] for row in planned["assignments"]
    ]:
        raise ValueError("Content experience set or order differs")
    sections = {key: content[key] for key in ("summary", "skills")}
    if content["schema_version"] == "resume-template-content/v1":
        sections["headline"] = [content["headline"]] if content.get("headline") else []
    allowed = {}
    for row, assignment in zip(content["experiences"], planned["assignments"], strict=True):
        if row["candidate_id"] != assignment["candidate_id"] or any(
            row[key] != assignment["experience"][key]
            for key in ("title", "role", "organization", "start", "end", "location")
        ):
            raise ValueError("Content experience metadata differs from assignment")
        sections[row["id"]] = row["items"]
        allowed[row["id"]] = (
            set(assignment["allowed_fact_refs"]),
            set(assignment["allowed_inference_refs"]),
        )
    global_scope = (
        set().union(*(facts for facts, _ in allowed.values())),
        set().union(*(inferences for _, inferences in allowed.values())),
    )
    allowed.update(summary=global_scope, skills=global_scope)
    if "headline" in sections:
        allowed["headline"] = global_scope
    protected = {}
    if protected_scopes and retained is None:
        raise ValueError("Protected list scopes require retained content")
    if retained is not None:
        saved = validate_content(retained).model_dump(mode="json")
        if saved["application_id"] != content["application_id"] or (
            "template_revision" in content
            and saved.get("template_revision") != content["template_revision"]
        ):
            raise ValueError("Retained content belongs to another application or template")
        saved_sections = {key: saved[key] for key in ("summary", "skills")}
        if saved["schema_version"] == "resume-template-content/v1":
            saved_sections["headline"] = [saved["headline"]] if saved.get("headline") else []
        saved_sections.update({row["id"]: row["items"] for row in saved["experiences"]})
        if not isinstance(protected_scopes or [], list) or any(
            scope not in saved_sections for scope in (protected_scopes or [])
        ):
            raise ValueError("Protected list scope is outside retained content")
        for scope in protected_scopes or []:
            if sections.get(scope) != saved_sections[scope]:
                raise ValueError("Protected human item list or ordering differs")
        for section, items in saved_sections.items():
            for index, item in enumerate(items):
                if item["origin"] == "human":
                    protected[section, index] = item
    for section, items in sections.items():
        facts, inferences = allowed[section]
        for index, item in enumerate(items):
            if item["origin"] == "human":
                if protected.get((section, index)) != item:
                    raise ValueError("Protected human content or position differs")
            elif (
                not set(item["fact_refs"]) <= facts or not set(item["inference_refs"]) <= inferences
            ):
                raise ValueError("Content references are outside assigned experience")
    for (section, index), item in protected.items():
        if (
            section not in sections
            or index >= len(sections[section])
            or sections[section][index] != item
        ):
            raise ValueError("Protected human content was removed or replaced")


def persist_content_generation(store, state, plan):
    """Adopt reviewed content into the existing immutable material version store."""
    from .application_prism import archive_sources, source_snapshot, validate_archive

    rendered, manifest = _rendered_content(plan, template=_content_template(store, state))
    _validate_content_scope(
        plan["resume_content"],
        state["writing_plan"],
        state["payload"].get("retained_content"),
        protected_scopes=state["payload"].get("retained_protected_scopes", []),
    )
    review = state.get("review") or {}
    content = deepcopy(plan["resume_content"])
    omitted_ids = _omitted_ids(state["payload"].get("retained_omitted_experience_ids", []))
    if omitted_ids & {row["id"] for row in content["experiences"]}:
        raise _invalid("写作版本不能恢复已保留的人工经历省略。")
    if (
        state.get("generation_contract") != CONTENT_CONTRACT
        or content["application_id"] != state["application_id"]
        or not review.get("passed")
        or review.get("content_revision") != rendered.content_revision
        or review.get("candidate_sha256") != manifest["tex_sha256"]
        or store._read_version_file(state["id"], "candidate-main.tex", 4_000_000).decode()
        != rendered.tex
    ):
        raise _invalid("采用须绑定终审通过的唯一内容和渲染版本。")
    directory = store.root / state["id"]
    if (directory / "draft.json").exists():
        previous = store.draft(state["id"])
        if (
            previous.get("resume_content") != content
            or previous.get("final_review") != review
            or previous.get("render_manifest") != manifest
        ):
            raise _invalid("已采用内容版本不能被后续候选覆盖。")
        return previous
    base = state["request"]["latex_base"]
    archive = store._read_version_file(state["id"], "base-sources.json", 48_000_000)
    project = directory / "project"
    before = source_snapshot(project, base["main"], source_policy="generated-latex-project/v1")
    if _sha(archive) != state["base_sha256"]:
        raise _invalid("采用前底稿归档已变化。")
    validate_archive(archive, base)
    expected = json.loads(archive)
    expected[base["main"]] = base64.b64encode(rendered.tex.encode()).decode()
    current = archive_sources(before)
    if current != archive and json.loads(current) != expected:
        raise _invalid("采用前源文件有人工修改，已保留当前文件。")
    if current == archive:
        temporary = directory / "reviewed-main.tex"
        temporary.write_text(rendered.tex, encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(project / base["main"])
    checkpoint = source_snapshot(project, base["main"], source_policy="generated-latex-project/v1")
    generated = archive_sources(checkpoint)
    (directory / "latex-sources.json").write_bytes(generated)
    (directory / "latex-sources.json").chmod(0o600)
    helper.atomic_write_json(directory / "content.json", content)
    helper.atomic_write_json(directory / "render-manifest.json", manifest)
    payload = state["payload"]
    draft = {
        **deepcopy(plan),
        "id": state["id"],
        "origin": "generated_latex",
        "generation_contract": CONTENT_CONTRACT,
        "content_revision": content["revision"],
        "render_manifest": manifest,
        "writing_plan": deepcopy(state["writing_plan"]),
        "retained_content": deepcopy(payload.get("retained_content")),
        "retained_protected_scopes": deepcopy(payload.get("retained_protected_scopes", [])),
        "retained_omitted_experience_ids": sorted(omitted_ids),
        "final_review": deepcopy(review),
        "retained_omissions": deepcopy(payload.get("retained_omissions", [])),
        "factual_review": "pending",
        "review_status": "review_required",
        "language": "en",
        "preparation_policy": "preparation-policy/v1.0",
        "application_id": state["application_id"],
        "application_revision": state["application_revision"],
        "task_inputs": deepcopy(state["request"]["task_inputs"]),
        "analysis_binding": deepcopy(payload["analysis"]),
        "job_context": deepcopy(payload["job"]),
        "generation_policy": deepcopy(state["configuration"]),
        "model_mode": store.model_mode,
        "information_library_revision": (state["request"].get("information_library") or {}).get(
            "revision"
        ),
        "base_checkpoint": {**base, "archive_sha256": state["base_sha256"]},
        "source_checkpoint": {**checkpoint, "archive_sha256": _sha(generated)},
        "generation_sources": deepcopy(payload["sources"]),
        "selected_source_ids": list(payload["analysis_selected_source_ids"]),
        "items": [],
        "context": [],
    }
    helper.atomic_write_json(directory / "draft.json", draft)
    helper.atomic_write_json(
        directory / "draft-integrity.json",
        {
            "schemaVersion": 1,
            "id": state["id"],
            "sha256": _sha((directory / "draft.json").read_bytes()),
        },
    )
    return store.draft(state["id"])


def validate_content_generation(store, draft):
    """Rebuild only archived JSON; current libraries and edited projects are irrelevant."""
    from .application_prism import validate_archive

    rendered, manifest = _rendered_content(draft, template=_content_template(store, draft))
    _validate_content_scope(
        draft["resume_content"],
        draft["writing_plan"],
        draft.get("retained_content"),
        protected_scopes=draft.get("retained_protected_scopes", []),
    )
    content = json.loads(store._read_version_file(draft["id"], "content.json", 2_000_000))
    saved_manifest = json.loads(
        store._read_version_file(draft["id"], "render-manifest.json", 2_000_000)
    )
    if _omitted_ids(draft.get("retained_omitted_experience_ids", [])) & {
        row["id"] for row in content["experiences"]
    }:
        raise ValueError("generated content restored retained human omission")
    review = draft["final_review"]
    if (
        draft.get("generation_contract") != CONTENT_CONTRACT
        or content != draft["resume_content"]
        or content["application_id"] != draft["application_id"]
        or content["revision"] != draft["content_revision"]
        or saved_manifest != manifest
        or draft["render_manifest"] != manifest
        or not review.get("passed")
        or review.get("content_revision") != rendered.content_revision
        or review.get("candidate_sha256") != manifest["tex_sha256"]
        or draft["factual_review"] != "pending"
        or any(
            draft[key]
            for key in (
                "review_groups",
                "omitted_groups",
                "verification_queue",
                "items",
                "context",
                "block_mapping",
            )
        )
    ):
        raise ValueError("Content material binding differs")
    for name, key in (
        ("base-sources.json", "base_checkpoint"),
        ("latex-sources.json", "source_checkpoint"),
    ):
        raw = store._read_version_file(draft["id"], name, 48_000_000)
        if _sha(raw) != draft[key]["archive_sha256"]:
            raise ValueError("Content source archive differs")
        source = validate_archive(raw, draft[key]).decode()
        if key == "source_checkpoint" and source != rendered.tex:
            raise ValueError("Content build differs from renderer")
