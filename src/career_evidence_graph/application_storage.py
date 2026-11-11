"""Private application-record directories, independent of workflow execution."""

from pathlib import Path

PUBLIC_ROOT = Path(__file__).resolve().parents[2]


def private_root(path: Path) -> Path:
    """Open an application directory under the existing containment policy."""
    path = path.expanduser()
    if path.is_symlink():
        raise ValueError("Worker directories cannot be symbolic links.")
    root = path.resolve()
    public = PUBLIC_ROOT.resolve()
    if root.is_relative_to(public) or public.is_relative_to(root):
        raise ValueError("Worker records must remain outside this checkout.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root
