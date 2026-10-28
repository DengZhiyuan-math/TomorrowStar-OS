"""Native service opt-in never changes or launches the legacy default."""

from io import StringIO

import pytest

from career_evidence_graph import cua_driver as module
from career_evidence_graph.career_portal_data import PortalDataError


def test_native_service_requires_reviewed_candidate_before_launch(tmp_path, monkeypatch):
    binary = tmp_path / "driver"
    binary.write_bytes(b"unreviewed")
    monkeypatch.setattr(module, "_NATIVE_HANDOFF_DRIVER_SHA256", None)
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *a, **k: pytest.fail("unreviewed launch")
    )
    with (
        pytest.raises(PortalDataError) as error,
        module.managed_cua_client(
            binary,
            str(tmp_path / "driver.sock"),
            {},
            StringIO(),
            {},
            embedded=True,
            trusted_session=True,
        ),
    ):
        pytest.fail("unreviewed native service")
    assert error.value.code == "cua_native_candidate_unverified"
    assert not (tmp_path / "driver.json").exists()
