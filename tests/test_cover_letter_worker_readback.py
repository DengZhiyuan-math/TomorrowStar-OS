"""The Worker never builds or rechecks a letter PDF; Flow's letter_export owns it.

Before step 3 the Worker compiled one PDF per upload field and had its own
recheck/retry operations. Their unknown-build invariants now live in Flow
(`test_application_cover_letter_flow`); ``OriginalBuild`` stays for v1 fixtures.
"""

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest
from test_application_worker import service as service
from test_cover_letter_delivery import field
from test_cover_letter_delivery import modern as modern
from test_supplemental_material_module import materials
from test_supplemental_material_module import prepared as prepared

from career_evidence_graph.career_portal_data import PortalDataError


class OriginalBuild:
    """One compile completes remotely but loses its response to the caller."""

    def __init__(self):
        self.compiles = 0
        self.reads = 0
        self.binding = None
        self.raw = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
        self.change = lambda result: None

    def compile(self, binding):
        self.compiles += 1
        self.binding = deepcopy(binding)
        raise TimeoutError("Synthetic completed build response lost")

    def read_compiled(self, binding):
        self.reads += 1
        assert binding == self.binding
        result = {
            "binding": deepcopy(binding),
            "pdf": self.raw,
            "build": {
                "source_revision": binding["source_revision"],
                "pdf_sha256": hashlib.sha256(self.raw).hexdigest(),
                "status": "complete",
                "exit": 0,
            },
        }
        self.change(result)
        return result


@pytest.mark.parametrize("operation", ["recheck-cover-letter-file", "retry-cover-letter-file"])
def test_worker_has_no_fill_time_letter_build_operations(modern, operation):
    prepared, _ = modern
    worker, job, batch = prepared
    assert materials(prepared).prepare(job, batch, {"fields": [field(kind="file", accept=".pdf")]})
    material = worker.store.load()["jobs"][0]["materials"][0]
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        worker.request(
            operation,
            {
                "application_id": job["application_id"],
                "material_id": material["id"],
                "expected_material_revision": "a" * 64,
                "request_id": "e" * 32,
            },
        )
    assert worker.store.path.read_bytes() == before
    # The one PDF came from Flow's letter-pdfs, not a per-field Worker build.
    assert "letter-pdfs" in material["file_path"]
