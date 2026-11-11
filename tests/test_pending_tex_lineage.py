"""Independent synthetic measurement of immutable lineage read fan-out."""

from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_pending_tex_merge import pending_manual as pending_manual
from test_pending_tex_merge import regenerate


def test_pending_lineage_read_cost(pending_manual):
    data, _pending, manual = pending_manual
    store, job, sources, analysis, _calls, _project, _output, inputs = data
    result, _ = regenerate(data, manual)
    observed = []
    original_read = store._read_version_file
    count = [0]

    def read(*args, **kwargs):
        count[0] += 1
        return original_read(*args, **kwargs)

    store._read_version_file = read
    for index in range(4):
        count[0] = 0
        store.draft(result["id"])
        observed.append(count[0])
        print("lineage_read_cost", index, count[0], flush=True)
        if index == 3:
            break
        editable = store.prepare_group_review(
            result["id"], result["draft_sha256"], task_inputs=inputs
        )
        edited = store.save_automatic_source(
            editable["id"],
            editable["draft_sha256"],
            task_inputs=inputs,
            latex_source=editable["latex_source"],
        )
        current_job = store.applications.get_application(job["id"])
        current_job = store.applications.update_application(
            current_job["id"],
            {"role_title": f"Engineer condition {index}."},
            current_job["revision"],
        )
        next_data = list(data)
        next_data[1] = current_job
        result, _ = regenerate(next_data, edited, job_change=True)
    assert observed[-1] < observed[0] * 8, observed
