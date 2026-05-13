# Implementation Roadmap

The platform is shipped as a working scaffold. This roadmap describes
the sequence in which the remaining capabilities should land.

## Milestone M1 — Foundation (this release)

* [x] Configuration system (Pydantic + YAML)
* [x] Model providers (Ollama default, llama.cpp optional)
* [x] ModelManager with single-resident invariant
* [x] ProjectMemory with sandboxing + atomic writes + per-file archive
* [x] Prompt library (charter + 9 roles + self-review)
* [x] Nine agent classes + registry + parser
* [x] Anti-lazy detector
* [x] Verification runners (pytest / ruff / mypy / npm test)
* [x] Sequential orchestrator with repair + review loops
* [x] SQLite state persistence
* [x] Optional Git per-phase commits
* [x] FastAPI server + websocket events
* [x] Vanilla HTML/JS dashboard
* [x] Typer CLI
* [x] Smoke test suite with stub provider

## Milestone M2 — Hardening

* [ ] `resume <job_id>` CLI command (state already supports it)
* [ ] Streaming token output to the UI (not just events)
* [ ] Per-job structured logs surfaced in the dashboard
* [ ] More aggressive anti-lazy AST checks for JS/TS via tree-sitter
* [ ] Configurable per-phase max-token budgets
* [ ] Workflow validation (`local-llm-dev validate-workflow`)

## Milestone M3 — Quality of Life

* [ ] Pre-built workflow presets (cli-app, http-api, library, refactor-only)
* [ ] One-click "open workspace in editor" from the UI
* [ ] Diff viewer for `artifacts/` history
* [ ] Per-agent prompt overrides from the UI
* [ ] Token + wall-clock cost report per phase

## Milestone M4 — Multi-Project / Multi-User

* [ ] Auth (single shared password, then per-user tokens)
* [ ] Job queue across projects (still single-resident GPU)
* [ ] Optional remote model providers (OpenAI-compatible endpoint)

## Out of Scope (forever)

* Parallel agent execution (breaks the VRAM budget)
* In-VRAM model swapping for "speed" (defeats the point)
* Hidden agent autonomy (the orchestrator is the only decision-maker)
