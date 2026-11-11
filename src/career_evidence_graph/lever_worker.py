"""Keep the original Lever import path for existing callers and fixtures."""

from .application_worker_browser import INSPECT, ApplicationRunner, main

LeverRunner = ApplicationRunner

__all__ = ["INSPECT", "LeverRunner", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
