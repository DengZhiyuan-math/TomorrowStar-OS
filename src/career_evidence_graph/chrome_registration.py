"""Read-only macOS service access check before browser registration."""

import hashlib
import sys
from pathlib import Path

ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def check_chrome_launch_environment() -> None:
    """Check registration-service access without starting Chrome or requesting TCC."""
    if sys.platform != "darwin":
        return
    import ctypes

    try:
        system = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        lookup = system.bootstrap_look_up
        lookup.argtypes = [ctypes.c_uint, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint)]
        lookup.restype = ctypes.c_int
        release = system.mach_port_deallocate
        release.argtypes = [ctypes.c_uint, ctypes.c_uint]
        release.restype = ctypes.c_int
        bootstrap = ctypes.c_uint.in_dll(system, "bootstrap_port").value
        task = ctypes.c_uint.in_dll(system, "mach_task_self_").value
        service = b"com.apple.coreservices.launchservicesd"
        port = ctypes.c_uint()
        code = lookup(bootstrap, service, ctypes.byref(port))
        if code == 1100:  # BOOTSTRAP_NOT_PRIVILEGED in servers/bootstrap.h
            raise RuntimeError(
                "macos_chrome_registration_denied: current execution context denies "
                f"{service.decode()}; Chrome was not started. "
                "Run this synthetic verification from an authorized native host."
            )
        if code != 0 or not port.value:
            raise RuntimeError(
                f"macos_chrome_registration_unknown: {service.decode()} lookup returned {code}"
            )
        if release(task, port.value) != 0:
            raise RuntimeError(
                f"macos_chrome_registration_unknown: {service.decode()} port release failed"
            )
    except (OSError, AttributeError, ValueError) as error:
        raise RuntimeError("macos_chrome_registration_unknown: native API unavailable") from error
