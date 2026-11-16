"""Closing the App while a step runs does not record the step as failed."""

import threading

from career_evidence_graph.application_pipeline import ApplicationPipeline


def test_a_step_ended_by_closing_the_app_is_not_recorded_as_a_failure():
    pipeline = ApplicationPipeline.__new__(ApplicationPipeline)
    pipeline._closed = threading.Event()
    pipeline._runtime_error = None

    def tick():
        pipeline._closed.set()
        raise OSError("the matching process ended with the App")

    def load():
        raise AssertionError("a closing App must not rewrite the saved step")

    pipeline._tick = tick
    pipeline._load = load
    pipeline._run(0)
    assert pipeline._runtime_error is None


def test_an_unexpected_error_names_its_type_and_place_in_the_stop():
    pipeline = ApplicationPipeline.__new__(ApplicationPipeline)
    pipeline._closed = threading.Event()
    pipeline._runtime_error = None
    pipeline._guard = threading.RLock()
    saved = {"status": "matching", "control": "running"}
    stops = []

    def tick():
        raise KeyError("score")

    pipeline._tick = tick
    pipeline._load = lambda: saved
    pipeline._pause_owned_worker = lambda state: None
    pipeline._stop = lambda state, status, message: stops.append(dict(state, status=status))
    pipeline._run(0)
    assert pipeline._runtime_error == "pipeline_checkpoint_unavailable"
    error = stops[0]["last_stop_error"]
    assert error["code"] == "KeyError"
    assert error["location"].startswith("test_pipeline_close_during_step.py:")
