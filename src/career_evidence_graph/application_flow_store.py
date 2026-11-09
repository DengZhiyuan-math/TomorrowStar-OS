"""Storage of the application flow record: a small index plus one file per task revision.

2026-11-09: the record was one 206 MB ``flow.json`` holding 37 tasks of about 3 MB each.
Every write rewrote all of it and read back every task's history file, so a user's
submit held the shared lock for 9.4 s. Each task revision was already saved as an
immutable history file, ``snapshots/<task id>/<revision>.json``; ``flow.json`` now names
those files instead of repeating them. The record callers see is unchanged
(``schemaVersion`` 1 with the full ``tasks`` list); only its storage differs, and a
record written before this change still loads.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ._vendor import job_apply_store as helper

STORAGE = "task-files/v1"
_ID = re.compile(r"[a-f0-9]{32}")
_REVISION = re.compile(r"[a-f0-9]{64}")


def task_path(root, task_id, revision):
    """The immutable file holding one task revision."""
    if not _ID.fullmatch(str(task_id)) or not _REVISION.fullmatch(str(revision)):
        raise ValueError("invalid task reference")
    return Path(root) / "snapshots" / task_id / f"{revision}.json"


def index_for(state):
    """The index written to flow.json: everything but the task bodies."""
    index = {key: value for key, value in state.items() if key != "tasks"}
    index["storage"] = STORAGE
    index["task_refs"] = [
        {"id": task["id"], "revision": task["revision"]} for task in state["tasks"]
    ]
    return index


def is_index(value):
    return isinstance(value, dict) and value.get("storage") == STORAGE


def assemble(root, index, *, read=None):
    """The full record from an index, or the record itself when it predates the index."""
    if not is_index(index):
        return index
    read = read or (lambda path: helper.read_json_object(path, "application flow task"))
    refs = index.get("task_refs")
    if not isinstance(refs, list):
        raise ValueError("invalid task references")
    tasks = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError("invalid task reference")
        path = task_path(root, ref.get("id"), ref.get("revision"))
        if any(part.is_symlink() for part in (path, path.parent, path.parent.parent)):
            raise ValueError("redirected task file")
        task = read(path)
        if task.get("id") != ref["id"] or task.get("revision") != ref["revision"]:
            raise ValueError("task file differs from its reference")
        tasks.append(task)
    state = {key: value for key, value in index.items() if key not in {"storage", "task_refs"}}
    state["tasks"] = tasks
    return state


def read_flow_state(root):
    """The full flow record for a reader outside the flow service (no validation)."""
    path = Path(root) / "flow.json"
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("unsafe record")
    return assemble(root, json.loads(path.read_bytes().decode("utf-8")))
