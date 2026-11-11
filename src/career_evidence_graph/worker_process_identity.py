"""Read a macOS process birth generation without taking control of the process."""

import os
import sys


def valid_process_identity(value):
    """Validate a saved kernel generation without claiming that it is alive."""
    return bool(
        isinstance(value, dict)
        and set(value) == {"pid", "uid", "started_seconds", "started_microseconds", "executable"}
        and type(value["pid"]) is int
        and value["pid"] > 0
        and type(value["uid"]) is int
        and value["uid"] >= 0
        and type(value["started_seconds"]) is int
        and value["started_seconds"] > 0
        and type(value["started_microseconds"]) is int
        and 0 <= value["started_microseconds"] < 1_000_000
        and isinstance(value["executable"], str)
        and os.path.isabs(value["executable"])
        and "\x00" not in value["executable"]
    )


def process_identity(pid: int) -> dict | None:
    """Return kernel PID, UID, birth time and executable, or retain unknown."""
    observed = _process_information(pid)
    return observed[0] if observed is not None else None


def process_parent_identity(pid: int) -> dict | None:
    """Read the direct kernel parent while the child's identity stays unchanged."""
    before = _process_information(pid)
    if before is None or type(before[1]) is not int or before[1] <= 0 or before[1] == pid:
        return None
    parent = _process_information(before[1])
    after = _process_information(pid)
    if before != after or parent is None:
        return None
    return parent[0]


def _process_information(pid: int):
    """Share one kernel read between existing identity and direct-parent checks."""
    if sys.platform != "darwin" or type(pid) is not int or pid <= 0:
        return None
    import ctypes

    # Darwin sys/proc_info.h: proc_bsdinfo, PROC_PIDTBSDINFO (3).
    class ProcessInfo(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint32)
            for name in (
                "pbi_flags",
                "pbi_status",
                "pbi_xstatus",
                "pbi_pid",
                "pbi_ppid",
                "pbi_uid",
                "pbi_gid",
                "pbi_ruid",
                "pbi_rgid",
                "pbi_svuid",
                "pbi_svgid",
                "rfu_1",
            )
        ] + [
            ("command", ctypes.c_char * 16),
            ("name", ctypes.c_char * 32),
            ("suffix", ctypes.c_uint32 * 6),
            ("started_seconds", ctypes.c_uint64),
            ("started_microseconds", ctypes.c_uint64),
        ]

    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        library.proc_pidinfo.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        library.proc_pidinfo.restype = ctypes.c_int
        library.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        library.proc_pidpath.restype = ctypes.c_int
        information = ProcessInfo()
        size = ctypes.sizeof(information)
        if library.proc_pidinfo(pid, 3, 0, ctypes.byref(information), size) != size:
            return None
        executable = ctypes.create_string_buffer(4096)
        if (
            information.pbi_pid != pid
            or information.pbi_uid != os.getuid()
            or not information.started_seconds
            or library.proc_pidpath(pid, executable, len(executable)) <= 0
        ):
            return None
        return {
            "pid": pid,
            "uid": information.pbi_uid,
            "started_seconds": information.started_seconds,
            "started_microseconds": information.started_microseconds,
            "executable": os.fsdecode(executable.value),
        }, int(information.pbi_ppid)
    except (OSError, ValueError, AttributeError):
        return None
