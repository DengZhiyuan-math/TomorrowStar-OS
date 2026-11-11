"""Fixed native PDFKit inspection for locally built résumé PDFs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .career_portal_data import PortalDataError


class NativePDFInspector:
    def __init__(self, executable: Path):
        self.executable = Path(executable)

    def __call__(self, raw: bytes) -> int:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= 700_000:
            raise PortalDataError("resume_pdf_invalid", "PDF 文件不完整或不能核验。", 409)
        try:
            path = self.executable
            if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
                raise ValueError("native PDF inspector missing")
            result = subprocess.run(
                [str(path)],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd="/",
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
                timeout=10,
            )
            if result.returncode == 2:
                raise PortalDataError("resume_pdf_invalid", "PDF 文件不完整或不能核验。", 409)
            if result.returncode != 0 or len(result.stdout) > 4096:
                raise ValueError("native PDF inspection unavailable")
            value = json.loads(result.stdout)
            if (
                not isinstance(value, dict)
                or set(value) != {"valid", "page_count"}
                or value["valid"] is not True
                or type(value["page_count"]) is not int
                or value["page_count"] < 1
            ):
                raise ValueError("invalid native response")
            return value["page_count"]
        except PortalDataError:
            raise
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            raise PortalDataError(
                "resume_pdf_inspection_unavailable", "本机 PDF 校验组件暂不可用，结果已保留。", 409
            ) from error
