# Orchestrator Design

The orchestrator (`lld.orchestrator.engine.Engine`) is a **state
machine** that walks a list of `PhaseConfig`s defined in
`config/workflow.yaml`. It owns the only thread of control during a job;
agents and providers are passive collaborators.

## Responsibilities

1. **Initialise** the project workspace (canonical layout, write TASK.md).
2. **For each phase**:
   * resolve the agent class via the registry,
   * compute the next `cycle` number,
   * call `agent.run(memory, model_manager, cycle, context)` with a
     wall-clock timeout (`per_phase_timeout_seconds`),
   * apply phase-specific gates (anti-lazy, verification, score),
   * persist the result and emit an event.
3. **Decide** what to do next: `advance`, `retry`, `loop_back`, or
   `block`. The decision matrix lives in `Engine._decide_next` and is
   intentionally explicit and small.
4. **Persist** every transition: `jobs`, `phase_runs`, `events` rows
   are written so an interrupted job can be re-inspected (and, with a
   small follow-up, resumed).

## Decision Matrix

| Phase            | Trigger                                               | Decision                       |
|------------------|--------------------------------------------------------|--------------------------------|
| implement        | anti-lazy violations, cycle < 3                       | `retry` (same phase)           |
| implement        | anti-lazy violations, cycle >= 3                      | `block`                        |
| test             | tests failed *or* anti-lazy violations, cycles left   | `loop_back -> implement`       |
| test             | tests failed, cycles exhausted                        | `block`                        |
| review           | always                                                | `advance` (refactor handles)   |
| refactor         | review cycles left                                    | `loop_back -> review`          |
| refactor         | review cycles exhausted                               | `advance`                      |
| audit            | score < `min_audit_score` or verdict BLOCKED          | `block`                        |
| audit            | otherwise                                              | `advance` (job complete)       |

## Cancellation & Resumption

* `Engine.cancel(job_id)` sets a flag checked between phases. Mid-phase
  cancellation is achieved by the per-phase `asyncio.wait_for` timeout.
* Resumption: state in SQLite is sufficient to know which phase
  completed last. A future `resume(job_id)` command can pick up from
  there - the workspace is the authoritative input for the next phase.

## Why a State Machine, Not a DAG

A DAG implies parallelism. Parallelism implies multi-model residency.
That breaks the VRAM budget. A linear walker with explicit loop-back
arrows expresses everything the workflow needs, in code that fits on
one screen.
