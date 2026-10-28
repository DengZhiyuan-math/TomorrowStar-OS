"""Native PDF validation accepts standard compressed-object PDFs."""

import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture(scope="module")
def native_pdf_inspector(tmp_path_factory):
    if sys.platform != "darwin":
        pytest.skip("PDFKit is a macOS native API")
    tmp_path = tmp_path_factory.mktemp("native-pdf-inspector")
    from career_evidence_graph.application_pdf import NativePDFInspector

    executable = tmp_path / "pdf-inspect"
    subprocess.run(
        [
            "xcrun",
            "swiftc",
            "-module-cache-path",
            str(tmp_path / "swift-cache"),
            str(Path(__file__).parents[1] / "macos/pdf_inspect.swift"),
            "-o",
            str(executable),
            "-framework",
            "PDFKit",
        ],
        check=True,
        capture_output=True,
    )
    return NativePDFInspector(executable)


def test_pdfkit_accepts_compressed_four_page_pdf_and_rejects_truncation(native_pdf_inspector):
    raw = (Path(__file__).parent / "fixtures/pdf-export/tectonic-compressed.pdf").read_bytes()
    assert b"/ObjStm" in raw
    assert native_pdf_inspector(raw) == 4
    with pytest.raises(PortalDataError) as error:
        native_pdf_inspector(raw[:100])
    assert error.value.code == "resume_pdf_invalid"
