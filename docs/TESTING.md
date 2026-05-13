# Testing Pipeline

Tests are a first-class phase, not an afterthought. The platform
considers a job *not done* if its tests do not pass.

## What runs, and when

The orchestrator runs the **Test agent** to produce / refine `tests/`,
then it runs the **VerificationRunner** to actually execute them. The
results are written to `TEST_RESULTS.md` in the workspace and folded
into the orchestrator's decision matrix.

## Tools (auto-detected)

| Project type | Commands run                                         |
|--------------|------------------------------------------------------|
| Python       | `pytest -x --tb=short -q`, `ruff check .`, `mypy .`  |
| Node / TS    | `npm test --silent`                                  |

A tool that is not on `PATH` is **skipped, not failed**. The skipped
result still appears in `TEST_RESULTS.md` with the reason. All commands
are configurable in `config/settings.yaml` under `verification:`.

## Repair Loop

If the test phase reports any hard failure (or the anti-lazy detector
flags blocking issues in `src/` or `tests/`), the orchestrator loops
back to `implement`. The Implementation agent is given the most recent
`TEST_RESULTS.md` as input so it can fix the failures rather than rebuild
from scratch.

The loop is bounded by `quality.max_test_repair_cycles` (default 4).
Beyond that, the job is BLOCKED with the failures captured.

## Anti-Lazy Test Rules

The Test agent is forbidden from emitting:

* empty test bodies (`def test_x(): pass`),
* trivial bodies with no assertions (`def test_x(): x = 1`),
* tests that import code but never call it.

Violations are surfaced by `AntiLazyDetector` and trigger the same
repair flow as a hard test failure.

## Static Analysis

`ruff` (lint) and `mypy` (type-check) failures are reported but do not
*block* the test phase by default — they are surfaced to the Review
agent which decides severity. To enforce a strict bar, edit the workflow
to add a custom `lint` phase, or change the `python_lint_command` to
something that exits non-zero on violations.

## Sandboxing

Subprocesses run with `cwd=workspace`, no environment modifications, and
a per-command timeout of `min(per_phase_timeout, 1200)` seconds.
Timeouts kill the process group.
