"""PEP 517 backend shim for filesystems that hide editable ``.pth`` files.

CPython 3.13.14 skips files carrying the macOS hidden flag. In this workspace,
editable ``.pth`` files acquire that flag during repeated uv synchronization.
The installed project hook therefore inserts this checkout's ``src`` path
before a previously installed package copy is imported.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from flit_core.buildapi import (
    build_sdist,
    get_requires_for_build_sdist,
    get_requires_for_build_wheel,
    prepare_metadata_for_build_wheel,
)
from flit_core.buildapi import build_wheel as _flit_build_wheel

__all__ = [
    "build_editable",
    "build_sdist",
    "build_wheel",
    "get_requires_for_build_editable",
    "get_requires_for_build_sdist",
    "get_requires_for_build_wheel",
    "prepare_metadata_for_build_editable",
    "prepare_metadata_for_build_wheel",
]


def _source_sitecustomize() -> bytes:
    source_root = Path(__file__).resolve().parent / "src"
    return (
        '"""Prioritize this repository checkout for locked project commands."""\n'
        "import sys\n"
        f"_SOURCE_ROOT = {str(source_root)!r}\n"
        "if _SOURCE_ROOT not in sys.path:\n"
        "    sys.path.insert(0, _SOURCE_ROOT)\n"
    ).encode()


def _append_source_import_hook(wheel_path: Path) -> None:
    """Install a site hook and record it in the wheel's integrity manifest."""
    with zipfile.ZipFile(wheel_path, "a") as wheel:
        record_name = next(name for name in wheel.namelist() if name.endswith(".dist-info/RECORD"))
        rows = list(csv.reader(io.TextIOWrapper(wheel.open(record_name), encoding="utf-8")))
        hook_name = "sitecustomize.py"
        wheel.writestr(hook_name, _source_sitecustomize())
        rows.append([hook_name, "", ""])
        serialized = io.StringIO(newline="")
        csv.writer(serialized, lineterminator="\n").writerows(rows)
        wheel.writestr(record_name, serialized.getvalue().encode("utf-8"))


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, object] | None = None,
    metadata_directory: str | None = None,
) -> str:
    """Build the wheel and make its startup import source-first deterministically."""
    wheel_name = _flit_build_wheel(wheel_directory, config_settings, metadata_directory)
    _append_source_import_hook(Path(wheel_directory) / wheel_name)
    return wheel_name


def build_editable(
    wheel_directory: str,
    config_settings: dict[str, object] | None = None,
    metadata_directory: str | None = None,
) -> str:
    """Build a complete wheel for PEP 660 installation."""
    return build_wheel(wheel_directory, config_settings, metadata_directory)


def get_requires_for_build_editable(
    config_settings: dict[str, object] | None = None,
) -> list[str]:
    """Use the normal wheel build requirements."""
    return get_requires_for_build_wheel(config_settings)


def prepare_metadata_for_build_editable(
    metadata_directory: str,
    config_settings: dict[str, object] | None = None,
) -> str:
    """Use the normal wheel metadata contract."""
    return prepare_metadata_for_build_wheel(metadata_directory, config_settings)
