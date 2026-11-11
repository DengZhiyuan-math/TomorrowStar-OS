# Synthetic PDF transport fixture

Generated on 2026-10-17 with the existing `render_resume` A4 template and actual
system Chrome through `export_pdf`. Contains only Synthetic Candidate and `.test`
contacts. SHA-256: `024c16287b8b9b105b4dbab31a0bb94fcca0d3ed4b47ecd8cf0b8745ae3b62be`.

Tests copy this complete file to exercise export receipts, integrity and workflow
failures without launching a renderer. Copying it does not validate the current
draft text or renderer quality. Actual text, A4 page and pixel QA is recorded in
`.scratch/pdf-export-2026-10-17/` with a separate multi-page synthetic document.

## Tectonic compressed-object fixture

`tectonic-compressed.pdf` is a four-page synthetic document generated from the
adjacent `.tex` on 2026-10-18 with the existing local Tectonic runtime, using only
cached TeX resources. It includes PDF object streams, where page and catalog
objects are compressed. The PDFKit regression checks four pages and rejects an
incomplete file. No real résumé material appears in this fixture.
