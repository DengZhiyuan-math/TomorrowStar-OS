"""PEP 517 backend shim for filesystems that hide editable ``.pth`` files.

CPython 3.13.14 skips files carrying the macOS hidden flag. In this workspace,
editable ``.pth`` files acquire that flag during repeated uv synchronization.
Building the normal Flit wheel for the editable hook keeps imports repeatable
without weakening Python's path-file safety behavior.
"""

from flit_core.buildapi import (
    build_sdist,
    build_wheel,
    get_requires_for_build_sdist,
    get_requires_for_build_wheel,
    prepare_metadata_for_build_wheel,
)

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
