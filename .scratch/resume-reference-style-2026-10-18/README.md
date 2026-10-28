# Resume reference style adaptation

Changed only `render_resume` in `src/career_evidence_graph/application_resume.py`. The patch uses the verified reference design parameters supplied by the parent: A4, 14 mm margins, Times New Roman/Times/serif, body 11/14.4 pt, name 24/28 pt, and blue 12/15 pt section headings with a 0.4 pt underline. Entry titles and dates share a baseline row. Pages flow naturally; no forced page count or filler was added. The print toolbar remains hidden.

The synthetic text comparison preserves visible text and order, escaping, responsibility attribution and scope boundaries. The AST outside the renderer is identical. Contacts retain their existing safe text separator; no link functionality was added.

Verification: 175 existing affected offline tests passed, 2 browser tests excluded by default. Ruff lint/format and whitespace checks passed. The tests use synthetic exporter doubles or copies of an existing public fixture. No real PDF, browser, model call, external request, private-file edit or installation change occurred in this subtask.

`change.patch` is the exact delta against `application_resume.before.py`. `verification.json` binds the checkout source hash and test results. Parent owns actual reference comparison, private draft review and PDF visual acceptance. This source edit does not describe the installed application version.
