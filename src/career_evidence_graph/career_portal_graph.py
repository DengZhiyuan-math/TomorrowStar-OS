"""Read-only documentary relationships, deliberately separate from Skill assessment."""

from __future__ import annotations

import hashlib
import posixpath
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import PurePosixPath
from threading import Lock
from urllib.parse import unquote, urlsplit

from .career_portal_data import CareerCatalog, PortalDataError
from .career_portal_data import _read_document as read_document

# Display vocabulary, not an ontology or a claim that the user knows these technologies.
# Matching is confined to explicitly titled technology sections and retains the source line.
_TECHNOLOGIES = (
    "Python",
    "JavaScript",
    "TypeScript",
    "C++",
    "C#",
    "Java",
    "Rust",
    "Go",
    "SQL",
    "PostgreSQL",
    "SQLite",
    "MySQL",
    "Redis",
    "FastAPI",
    "Django",
    "Flask",
    "React",
    "Next.js",
    "Vue",
    "Node.js",
    "Docker",
    "Kubernetes",
    "Terraform",
    "AWS",
    "GCP",
    "PyTorch",
    "TensorFlow",
    "JAX",
    "NumPy",
    "pandas",
    "scikit-learn",
    "MLX",
    "SGLang",
    "vLLM",
    "Transformers",
    "Git",
    "GitHub Actions",
    "Linux",
    "Bash",
    "pytest",
    "Playwright",
    "REST",
    "GraphQL",
    "MCP",
    "WebSocket",
    "LaTeX",
    "Uvicorn",
    "Jinja2",
)
_TECH_PATTERNS = [
    (
        name,
        re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])", 0 if name in {"Go", "REST"} else re.I),
    )
    for name in _TECHNOLOGIES
]
_TECH_HEADING = re.compile(
    r"^(technology(?: and .+)?|technical stack|tech stack|技术栈|技术与架构)$", re.I
)
_EXCLUDED = re.compile(r"^(?:(?:excluded|rejected)\b|明确排除|不纳入|已排除)", re.I)
_EXCLUDED_DOCUMENT = re.compile(
    r"(?im)^(?:#{1,6}\s+)?Boundary:\s*excluded from career skill evidence"
)


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _id(kind: str, value: str) -> str:
    identity = _key(value) if kind == "skill" else value
    return kind + "-" + hashlib.sha256(identity.encode()).hexdigest()[:20]


def _plain(value: str) -> str:
    return re.sub(r"[*`]", "", value).strip()


def _title(document: dict) -> str:
    match = re.search(r"(?m)^#\s+(.+)$", document.get("content", ""))
    return _plain(match[1]) if match else document["title"]


def _is_index(document: dict) -> bool:
    return bool(
        re.search(
            r"(?:^|[-_ ])(?:readme|index|catalog|catalogue)(?:$|[-_ ])",
            PurePosixPath(document["source_name"]).stem,
            re.I,
        )
    )


def _references(document: dict, by_path: dict, warnings: list[str]) -> list[tuple[str, int, str]]:
    """Resolve only visible catalog documents; never read a path found in source text."""
    references = []
    for number, line in enumerate(document.get("content", "").splitlines(), 1):
        targets = re.findall(r"\[[^\]]*\]\(([^)]+)\)", line)
        targets += re.findall(r"`((?:sources|reports|contributions|skill-graph)/[^`]+)`", line)
        targets += [value.split("|", 1)[0] for value in re.findall(r"\[\[([^\]]+)\]\]", line)]
        for target in targets:
            target = unquote(target.strip().strip("<>"))
            try:
                parsed = urlsplit(target)
            except ValueError:
                warnings.append(f"{document['source_name']}:{number} 引用格式无效，已跳过。")
                continue
            if parsed.scheme or parsed.netloc or target.startswith(("/", "\\")):
                continue
            target = parsed.path
            if not target or "\\" in target:
                continue
            candidates = {
                posixpath.normpath(target),
                posixpath.normpath(str(PurePosixPath(document["source_name"]).parent / target)),
            }
            candidates |= {value + ".md" for value in candidates if not PurePosixPath(value).suffix}
            matches = candidates & by_path.keys()
            if not matches and "/" not in target and not target.startswith("."):
                matches = {path for path in by_path if PurePosixPath(path).stem == target}
            if len(matches) == 1:
                destination = next(iter(matches))
                if destination != document["source_name"]:
                    references.append((destination, number, line.strip()))
    return references


def build_graph(documents: list[dict], warnings: list[str] | None = None) -> dict:
    """Project explicit references, candidate rows and technology mentions; never scores."""
    documents = [
        {
            **item,
            "content": item.get("content")
            if item.get("available") is not False and isinstance(item.get("content"), str)
            else "",
        }
        for item in documents
    ]
    documents = sorted(documents, key=lambda item: item["source_name"])
    by_path = {item["source_name"]: item for item in documents}
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    warnings = list(warnings or [])
    unavailable = sum(item.get("available") is False for item in documents)
    if unavailable:
        warning = f"{unavailable} 份文档正文暂不可用，图中仅显示其目录信息；下载后刷新可补充关系。"
        if warning not in warnings:
            warnings.append(warning)
    projects: dict[str, str] = {}
    references = {item["source_name"]: _references(item, by_path, warnings) for item in documents}
    report_paths = {
        doc["source_name"]
        for doc in documents
        if doc["kind"] == "report"
        and doc["content"]
        and not _is_index(doc)
        and not _EXCLUDED_DOCUMENT.search(doc["content"])
    }
    project_paths = {
        path for path in report_paths if PurePosixPath(path).parts[:2] == ("reports", "projects")
    } or report_paths
    project_documents = {
        path: {path}
        | {
            target
            for target, _, _ in references[path]
            if target not in project_paths
            and by_path[target]["kind"] in {"report", "source"}
            and not _is_index(by_path[target])
        }
        for path in project_paths
    }

    def add_node(kind: str, identity: str, label: str, doc: dict, status="documentary") -> str:
        identifier = _id(kind, identity)
        entry = nodes.setdefault(
            identifier,
            {
                "id": identifier,
                "label": label,
                "type": kind,
                "status": status,
                "summary": "候选技能，尚未形成能力评分。"
                if status == "candidate"
                else "来自原始材料的文档关联。",
                "evidence_ids": [],
            },
        )
        if doc["id"] not in entry["evidence_ids"]:
            entry["evidence_ids"].append(doc["id"])
        if status == "candidate":
            entry["status"] = "candidate"
            entry["summary"] = "候选技能，尚未形成能力评分。"
        return identifier

    def connect(source: str, target: str, kind: str, label: str, doc: dict, line: int, basis: str):
        if source == target:
            return
        identifier = _id("edge", f"{source}|{target}|{kind}")
        entry = edges.setdefault(
            identifier,
            {
                "id": identifier,
                "source": source,
                "target": target,
                "type": kind,
                "label": label,
                "basis": "",
                "evidence_ids": [],
            },
        )
        citation = f"{doc['source_name']}:{line} · {basis[:800]}"
        if citation not in entry["basis"].splitlines():
            entry["basis"] = "\n".join(filter(None, (entry["basis"], citation)))
        if doc["id"] not in entry["evidence_ids"]:
            entry["evidence_ids"].append(doc["id"])
        if label not in entry["label"].split(" / "):
            entry["label"] += " / " + label

    for doc in documents:
        document_id = add_node("document", doc["source_name"], _title(doc), doc)
        if doc.get("available") is False or "content" not in doc:
            nodes[document_id]["summary"] = "正文暂不可用；未推断其中的技能或关系。"
        if doc["source_name"] in project_paths:
            project = add_node("project", doc["source_name"], _title(doc), doc)
            projects[doc["source_name"]] = project
            connect(project, document_id, "documents", "项目报告", doc, 1, _title(doc))

    for doc in documents:
        for target, line, snippet in references[doc["source_name"]]:
            connect(
                _id("document", doc["source_name"]),
                _id("document", target),
                "references",
                "文档引用",
                doc,
                line,
                snippet,
            )
            if doc["source_name"] in projects and target in projects:
                connect(
                    projects[doc["source_name"]],
                    projects[target],
                    "references",
                    "报告引用",
                    doc,
                    line,
                    snippet,
                )
            if doc["source_name"] in projects and target in project_documents[doc["source_name"]]:
                connect(
                    projects[doc["source_name"]],
                    _id("document", target),
                    "references",
                    "项目参考",
                    doc,
                    line,
                    snippet,
                )

    def context_project(doc: dict, context: str, source_paths: list[str], line: int) -> str:
        matches = set()
        for source_path in source_paths:
            for report in projects:
                if source_path in project_documents[report] or any(
                    ref[0] in project_documents[report] for ref in references.get(source_path, [])
                ):
                    matches.add(projects[report])
        if len(matches) == 1:
            project = next(iter(matches))
            if doc["id"] not in nodes[project]["evidence_ids"]:
                nodes[project]["evidence_ids"].append(doc["id"])
        else:
            project = add_node("project", f"{doc['source_name']}#{context}", context, doc)
        connect(
            project,
            _id("document", doc["source_name"]),
            "documents",
            "候选技能来源",
            doc,
            line,
            context,
        )
        for source_path in source_paths:
            connect(
                project,
                _id("document", source_path),
                "references",
                "项目来源",
                doc,
                line,
                source_path,
            )
        return project

    excluded_rows = 0
    for doc in documents:
        content = doc.get("content", "")
        if _EXCLUDED_DOCUMENT.search(content):
            continue
        report_projects = {
            projects[path]
            for path, aliases in project_documents.items()
            if doc["source_name"] in aliases
        }
        report_project = next(iter(report_projects)) if len(report_projects) == 1 else None
        section = ""
        source_paths: list[str] = []
        table = False
        context = _title(doc)
        for number, line in enumerate(content.splitlines(), 1):
            heading = re.match(r"^##\s+(.+)$", line)
            if heading:
                section = _plain(heading[1])
                context = section
                table = False
                source_paths = []
                continue
            if re.match(r"^(?:Experience|Subproject) source:", line, re.I):
                source_paths = [
                    target for target, n, _ in references[doc["source_name"]] if n == number
                ]
            cells = [
                _plain(cell.replace(r"\|", "|"))
                for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))
            ]
            if cells and cells[0].casefold() == "candidate skill":
                table = len(cells) >= 3
                continue
            if table and line.strip().startswith("|") and len(cells) >= 3:
                if re.fullmatch(r"[:\-\s]+", cells[0]):
                    continue
                if not cells[0] or len(cells[0]) > 160:
                    continue
                if _EXCLUDED.match(cells[2]):
                    excluded_rows += 1
                    continue
                project = context_project(doc, context, source_paths, number)
                skill = add_node("skill", cells[0], cells[0], doc, "candidate")
                connect(project, skill, "mentions", "候选技能 · 待审核", doc, number, line.strip())
            elif table and line.strip():
                table = False
            if doc["kind"] == "report" and report_project and _TECH_HEADING.fullmatch(section):
                for technology, pattern in _TECH_PATTERNS:
                    if pattern.search(line):
                        skill = add_node("skill", technology, technology, doc)
                        connect(
                            report_project,
                            skill,
                            "mentions",
                            "技术提及 · 未审核",
                            doc,
                            number,
                            line.strip(),
                        )
            if section.casefold() == "candidate skill links" and doc["kind"] == "contribution":
                bullet = re.match(r"^[-*]\s+(.+)$", line)
                if bullet and len(bullet[1]) <= 160:
                    skill = add_node(
                        "skill", _plain(bullet[1]), _plain(bullet[1]), doc, "candidate"
                    )
                    connect(
                        _id("document", doc["source_name"]),
                        skill,
                        "mentions",
                        "贡献的候选技能",
                        doc,
                        number,
                        line.strip(),
                    )
    if excluded_rows:
        warnings.append(f"{excluded_rows} 条明确排除的候选未作为技能关系展示；原文仍可查看。")
    for entry in nodes.values():
        entry["evidence_ids"].sort()
    for entry in edges.values():
        entry["evidence_ids"].sort()
    return {
        "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
        "edges": sorted(edges.values(), key=lambda item: item["id"]),
        "warnings": warnings,
        "authority": "documentary",
    }


class CareerGraph:
    """Lazy, bounded document projection; the ordinary catalog remains metadata-only."""

    def __init__(self, catalog: CareerCatalog):
        self.catalog = catalog
        self._lock = Lock()
        self._cache: dict[str, tuple[tuple[int, int], dict]] = {}

    def snapshot(self) -> dict:
        with self._lock:
            paths = self.catalog._paths()
            documents = []
            pending = {}
            unavailable = 0
            with ThreadPoolExecutor(max_workers=8) as pool:
                for path, kind in paths[:300]:
                    meta = self.catalog._record(path, kind, detail=False)
                    signature = (path.stat().st_mtime_ns, path.stat().st_size)
                    cached = self._cache.get(meta["id"])
                    if not meta["available"]:
                        documents.append(meta)
                        unavailable += 1
                    elif cached and cached[0] == signature:
                        documents.append(cached[1])
                    else:
                        pending[pool.submit(read_document, path)] = (meta, signature)
                try:
                    for future in as_completed(pending, timeout=5):
                        meta, signature = pending.pop(future)
                        try:
                            meta["content"] = future.result()
                            self._cache[meta["id"]] = (signature, meta)
                        except (PortalDataError, OSError):
                            meta["available"] = False
                            unavailable += 1
                        documents.append(meta)
                except TimeoutError:
                    for future, (meta, _) in pending.items():
                        future.cancel()
                        meta["available"] = False
                        documents.append(meta)
                        unavailable += 1
            active_ids = {item["id"] for item in documents}
            self._cache = {key: value for key, value in self._cache.items() if key in active_ids}
            warnings = []
            if unavailable:
                warnings.append(
                    f"{unavailable} 份文档正文暂不可用，图中仅显示其目录信息；"
                    "下载后刷新可补充关系。"
                )
            if len(paths) > 300:
                warnings.append("本次只读取前 300 份文档，请缩小文档目录后再查看完整图谱。")
            return build_graph(documents, warnings)
