# Frozen synthetic interview trials

`corpus.json` contains nine fully synthetic reference cases. It binds the retained
v1 corpus hash and explains the v2 repair. The labels are protocol reference labels,
not independent expert labels for real personal evidence.

`runs/trial-001` through `trial-006` retain successful and failed evidence.
The final run records three plan generations and three nine-case evaluation batches.
Its boundary and anchor results pass all 27 comparisons with no critical error or
unstable case. Numeric personal mastery and confidence remain unauthorized.

Raw question candidates still need semantic review. Trial 006 contains the original
outputs, two rejected semantic candidates, three explicitly reviewed successor
plans and the parent hashes in `question-semantic-review.json`. Assistant review
is labelled separately from independent human review.

Run from the system checkout into a **new** destination:

```sh
uv run --locked python scripts/run_interview_calibration.py --live \
  --output /absolute/new/synthetic-trial
```

The runner reads only this fixed synthetic corpus. It retains prompt, schema,
configuration, raw responses and failed calls. It does not discover a private
workspace or authorize personal scores. Codex authentication and a working local
read-only CLI transport are required. Alias drift limits reproducibility; the
stored raw responses are exact historical evidence.

See the [delivery record](../../../docs/interview-delivery-2026-10-08.md) for
implementation tests, failure repairs and the separate human calibration gate.
