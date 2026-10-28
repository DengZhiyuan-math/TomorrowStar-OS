"""Independent synthetic probe: a restored contact header stays editable."""

import json
from copy import deepcopy
from types import SimpleNamespace

from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import career_source_snapshot


def test_restored_contact_header_remains_manually_editable(full_latex):
    store, job, _sources, analysis, _calls, project, output, inputs = full_latex
    path = store.catalog.root / "sources/profile.json"
    profile = json.loads(path.read_text())
    profile["links"] = [{"label": "Email", "href": "mailto:old@example.invalid"}]
    path.write_text(json.dumps(profile))
    sources = career_source_snapshot(store.catalog)
    analysis["source_snapshot_revision"] = sources["revision"]
    inputs["sources_revision"] = sources["revision"]
    full_latex = (store, job, sources, analysis, _calls, project, output, inputs)
    header = "Synthetic Person old@example.invalid\n"
    (project / "main.tex").write_text(
        (project / "main.tex").read_text().replace("Synthetic Person\n", header)
    )
    output["groups"][0].update(
        latex=header, disposition="verify", reason="Important header contact conflict"
    )
    pending = generate(full_latex)
    assert "old@example.invalid" not in pending["latex_source"]
    editable = store.prepare_group_review(
        pending["id"], pending["draft_sha256"], task_inputs=inputs
    )
    manual = store.save_automatic_source(
        editable["id"],
        editable["draft_sha256"],
        task_inputs=inputs,
        latex_source=editable["latex_source"].replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        ),
    )
    library = {
        "status": "available",
        "revision": "a" * 64,
        "records": [
            {
                "key": "email",
                "question": "Email",
                "value": "new@example.invalid",
                "state": "confirmed",
                "scope": {"application_id": job["id"]},
            }
        ],
    }
    next_inputs = inputs | {"information_library_revision": library["revision"]}

    def model(config, prompt, **_kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        groups = deepcopy(payload["update_context"]["retained_groups"])
        for group in groups:
            group.update(
                disposition="include", reason="Confirmed new contact, original facts retained"
            )
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": []},
            model_dump=lambda **_: {"synthetic": True},
        )

    store.model_runner = model
    restored = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        draft_only=True,
        task_inputs=next_inputs,
        latex_base=source_snapshot(
            store.root / manual["id"] / "project",
            "main.tex",
            source_policy="generated-latex-project/v1",
        ),
        retained_draft=manual,
        information_library=library,
    )
    assert not restored["verification_queue"]
    assert "new@example.invalid" in restored["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in restored["latex_source"]
    next_editable = store.prepare_group_review(
        restored["id"], restored["draft_sha256"], task_inputs=next_inputs
    )
    saved = store.save_automatic_source(
        next_editable["id"],
        next_editable["draft_sha256"],
        task_inputs=next_inputs,
        latex_source=next_editable["latex_source"].replace(
            "Built 6 Python services; analyzed strategy.",
            "Built 6 Python services and analyzed strategy.",
        ),
    )
    assert "new@example.invalid" in saved["latex_source"]
