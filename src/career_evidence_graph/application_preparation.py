"""Local preparation readiness; inspecting dependencies never executes them."""

import os
from pathlib import Path

from .validation.hashing import record_digest as digest

PREPARATION_POLICY_VERSION = "preparation-policy/v1.0"


def preparation_inputs(career_root):
    """Bind local account/config metadata without reading or exposing credentials.

    Remote Gmail identity remains unverified until an explicit connector read.
    Completed content retains its producer context; credential metadata is not
    a change to its factual inputs.
    """
    # MC-21: the App's model calls sign in inside its dedicated Codex home.
    dedicated = os.environ.get("TOMORROWSTAR_CODEX_HOME")
    home = (
        Path(dedicated) / ".codex"
        if dedicated
        else Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    )
    metadata = {}
    for name in ("auth.json", "config.toml"):
        try:
            stat = (home / name).stat()
            metadata[name] = [
                stat.st_dev,
                stat.st_ino,
                stat.st_size,
                stat.st_mtime_ns,
                stat.st_ctime_ns,
            ]
        except OSError:
            metadata[name] = None
    return {
        "account_context_revision": digest(
            {
                "home": str(home.absolute()),
                "metadata": metadata,
                "credentials": {
                    key: os.environ.get(key) for key in ("CODEX_API_KEY", "OPENAI_API_KEY")
                },
            }
        ),
        "career_workspace_revision": digest(str(career_root)),
        "preparation_policy_revision": PREPARATION_POLICY_VERSION,
    }


def preparation_checks(*, sources, configuration, intake, resumes, task, fresh, materials_valid):
    cli = configuration["executable_status"] == "available"
    mail = intake.snapshot() if intake else None
    gmail = {
        "status": "unverified" if cli and mail and mail["enabled"] else "unavailable",
        "message": "邮箱连接与账号尚未核验；仅在明确更新推荐时读取。"
        if cli and mail and mail["enabled"]
        else "推荐读取暂不可用；请检查 Codex 连接，仍可选择已有完整 JD。",
    }
    if mail and mail.get("status") in {"failed", "unavailable", "needs_recheck"}:
        gmail = {"status": "unavailable", "message": mail.get("message") or gmail["message"]}
    has_sources = bool(sources["items"])
    source_status = (
        "unavailable"
        if not has_sources
        else "needs_input"
        if sources["profile"] is None or sources["coverage"]["unavailable_documents"]
        else "available"
    )
    source_messages = []
    if not has_sources:
        source_messages.append("尚无可用于材料准备的经历条目，请核对已选资料范围和责任归属。")
    if sources["profile"] is None:
        issue = sources.get("profile_issue") or {}
        source_messages.append(
            {
                "resume_profile_invalid": "结构化个人资料格式无效，请检查姓名及字段格式。",
                "resume_profile_unavailable": "结构化个人资料暂不可读，请在原工作区检查后重试。",
            }.get(issue.get("code"), "未找到结构化个人资料，请检查已选资料范围或补充个人资料。")
        )
    elif source_status != "available":
        source_messages.append("个人资料已读取。")
    if sources["coverage"]["unavailable_documents"]:
        errors = {
            document.get("error_code")
            for document in sources.get("documents", [])
            if document["id"] in sources["coverage"]["unavailable_documents"]
        }
        if "document-too-large" in errors:
            source_messages.append("部分文档超过读取大小限制，未读取其内容。请在原工作区查看。")
        if "invalid-document" in errors:
            source_messages.append("部分文档不是有效的 UTF-8 文本，请在原工作区检查格式。")
        if not errors or errors - {"document-too-large", "invalid-document"}:
            source_messages.append("部分文档暂不可读，请在原工作区确认已下载且可读取后重试。")
    source_message = " ".join(source_messages) or "职业资料已读取；内容归属仍以来源审核为准。"
    pdf_configured = resumes.prism_client is not None
    return {
        "gmail": gmail,
        "model": {
            "status": "unverified" if cli else "unavailable",
            "message": "已发现 Codex；登录、额度与实际模型调用尚未核验。"
            if cli
            else "未找到 Codex；请配置可用的 Codex 后再分析或生成新材料。",
        },
        "sources": {
            "status": source_status,
            "message": source_message,
        },
        "pdf": {
            "status": "available" if pdf_configured else "unverified",
            "message": "LaTeX 编译服务已配置；以具体导出结果为准。"
            if pdf_configured
            else "简历仅通过 LaTeX 编译导出 PDF；编译服务尚未执行核验。",
        },
        "policy": {
            "status": "available",
            "message": (
                f"已确认 {PREPARATION_POLICY_VERSION}；事实适用范围仍须核验，真实申请保持暂停。"
            ),
        },
        "draft": {
            "status": "stale"
            if not fresh
            else "invalid"
            if not materials_valid
            else "available"
            if task and (task.get("resume_id") or task.get("draft_id"))
            else "not_created",
            "message": "输入已变化；旧材料保留，请更新任务后再使用。"
            if not fresh
            else "当前材料无法核验；保留旧版本记录，请明确重新生成简历。"
            if not materials_valid
            else "已有岗位材料，可打开并复核具体 PDF。"
            if task and task.get("resume_id")
            else "已有可审阅草稿；请核对原文、改写及事实提示，尚未导出 PDF。"
            if task and task.get("draft_id")
            else "尚无当前岗位简历；可选择已有完整 JD 并保存准备任务。",
        },
    }
