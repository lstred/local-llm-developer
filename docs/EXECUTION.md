# Execution Engine

See `src/lld/orchestrator/engine.py` for the single source of truth.
This document explains *why* the engine is shaped the way it is.

## Single Async Loop

The orchestrator runs in one `asyncio` task per job. There is no
threading and no multiprocessing. This is intentional:

* It removes any chance of two agents racing against the GPU.
* It makes structured logging trivially deterministic.
* The FastAPI server can run alongside it because the engine is
  await-friendly between phases.

## Per-Phase Lifecycle

```python
agent = build_agent(phase.agent, models_config, prompts)
result = await asyncio.wait_for(
    agent.run(memory, model_manager, cycle=cycle),
    timeout=settings.execution.per_phase_timeout_seconds,
)
# Phase-specific gates:
if phase.id == "test":
    report = await VerificationRunner(...).run_all(workspace)
    memory.write_text("TEST_RESULTS.md", report.to_markdown())
if phase.id in {"implement", "test", "refactor"}:
    findings = AntiLazyDetector(...).scan_workspace(workspace)
    if blocking(findings): result.success = False
```

## Repair Loops

Two distinct loops:

1. **Test-repair loop**: `test` failures (or anti-lazy violations)
   send the engine back to `implement`. Capped by
   `quality.max_test_repair_cycles`.
2. **Review loop**: `refactor` always loops back to `review` for a
   re-score, capped by `quality.max_review_cycles - 1` to reserve one
   final review pass after the last refactor.

## Observability

Each transition emits a structured event:

```json
{"event": "phase.end", "job_id": "...", "phase": "implement",
 "agent": "implementation", "cycle": 2, "success": true,
 "score": null, "artifacts": ["src/foo.py", "handoffs/impl_to_test.md"]}
```

Events go to:

* the SQLite `events` table (durable, queryable),
* the in-process `EventBroadcaster` (websocket fan-out for the UI),
* the structured log file (`state/logs/orchestrator.log`),
* registered listeners (e.g. the CLI `run` command attaches a console
  printer).

## Resource Hygiene

`ModelManager.unload_all()` is called on shutdown. Per-call,
`keep_alive=0` ensures Ollama unloads the model immediately. The
`llama.cpp` provider drops its only reference and triggers `gc.collect()`.

## Error Surfaces

| Source                         | What happens                                  |
|-------------------------------|-----------------------------------------------|
| Agent raises                  | phase marked `failed`, job marked `failed`    |
| Phase timeout                 | phase marked `timeout`, job marked `failed`   |
| LLM transport error           | retried (`tenacity`) up to `llm_call_retries` |
| Workspace write error         | phase marked `failed`                         |
| Verification subprocess error | recorded in TEST_RESULTS.md, never fatal      |
| Listener error                | logged; never propagates                      |
