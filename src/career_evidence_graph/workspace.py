"""One explicit, private workspace boundary for career-source custody."""

from __future__ import annotations

from pathlib import Path


class PrivateWorkspaceError(ValueError):
    """The selected private workspace is unsafe."""


class PrivateWorkspace:
    """Resolve one existing non-symlink workspace and its semantic namespaces."""

    def __init__(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise PrivateWorkspaceError("career-source-workspace-unsafe")
        self.root = path.resolve(strict=True)

    def child(self, *parts: str) -> Path:
        candidate = self.root.joinpath(*parts)
        if not candidate.is_relative_to(self.root):
            raise PrivateWorkspaceError("career-source-path-unsafe")
        return candidate
