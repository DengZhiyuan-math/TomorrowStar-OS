"""Fixed native entry for an existing local LaTeX review; no job workflow."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path


def _config_object(pairs):
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("duplicate configuration fields")
    return value


def read_config(path: Path) -> dict:
    if (
        not path.is_absolute()
        or ".." in path.parts
        or any(part.is_symlink() for part in (path, *path.parents))
    ):
        raise ValueError("unsafe configuration")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= 16_384:
            raise ValueError("invalid configuration file")
        raw = source.read(16_385)
    if len(raw) > 16_384:
        raise ValueError("configuration exceeds limit")
    value = json.loads(raw, object_pairs_hook=_config_object)
    if (
        not isinstance(value, dict)
        or set(value) != {"project_root", "main"}
        or any(not isinstance(item, str) or not item.strip() for item in value.values())
    ):
        raise ValueError("invalid configuration fields")
    return value


def main(argv=None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and (len(arguments) != 2 or arguments[0] != "--config"):
        result = {
            "status": "error",
            "code": "resume_review_request_invalid",
            "message": "请从 App 的固定简历审阅入口打开。",
        }
    else:
        path = (
            Path(arguments[1])
            if arguments
            else Path.home() / "Library/Application Support/TomorrowStar/resume-review.json"
        )
        try:
            config = read_config(path)
        except FileNotFoundError:
            result = {
                "status": "error",
                "code": "resume_review_not_configured",
                "message": "请先配置专用 LaTeX 简历审阅项目。",
            }
        except (OSError, ValueError, TypeError, UnicodeError):
            result = {
                "status": "error",
                "code": "resume_review_config_invalid",
                "message": "简历审阅配置不能核验，请检查专用项目设置。",
            }
        else:
            resources = Path(__file__).resolve().parent
            system = resources.parent if resources.name == "macos" else resources / "system"
            try:
                source_root = system / "src"
                if not (source_root / "career_evidence_graph/application_prism.py").is_file():
                    raise ValueError("review engine is unavailable")
                sys.path.insert(0, str(source_root))
                from career_evidence_graph.application_prism import PrismClient, source_snapshot

                binding = source_snapshot(Path(config["project_root"]), config["main"])
                url = PrismClient().open(binding)
                result = {"status": "ready", "url": url, "title": "LaTeX 简历编辑与预览"}
            except Exception:
                result = {
                    "status": "error",
                    "code": "resume_review_unavailable",
                    "message": "简历审阅项目暂不能连接。请保留原稿，检查本地 Prism 服务。",
                }
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
