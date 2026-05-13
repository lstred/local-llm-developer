# Example Workflows

Three concrete walkthroughs of running real tasks through the platform.

## 1. CLI Todo Application (Python)

**Task**:

> Build a Python 3.11 command-line todo app called `todo` that stores
> tasks in `~/.todo/tasks.json`. Subcommands: `add`, `list`, `done`,
> `rm`. Use `typer` for the CLI and `rich` for output. Provide
> `pytest` tests covering all subcommands.

**Expected phase trace**:

| # | Phase           | Notable artifacts                                |
|---|-----------------|--------------------------------------------------|
| 1 | plan            | PLAN.md with subcommand contract                 |
| 2 | architect       | ARCHITECTURE.md (one module, JSON store)         |
| 3 | implement       | `src/todo/{cli,store}.py`                        |
| 4 | test            | `tests/test_cli.py` covering add/list/done/rm    |
| 4a| (verification)  | TEST_RESULTS.md — pytest passes                  |
| 5 | review          | REVIEW.md, score >= 8                            |
| 6 | security        | SECURITY.md (low risk, file perms noted)         |
| 7 | refactor        | minor cleanup; loop back to review               |
| 5'| review (cycle 2)| score 9                                          |
| 8 | document        | README.md + docs/USAGE.md                        |
| 9 | audit           | AUDIT.md, verdict APPROVED, score 9              |

**Run it**:

```powershell
local-llm-dev run --task "Build a Python 3.11 ..." --workspace todo-cli
```

## 2. FastAPI REST API for a Bookmarks Service

**Task**:

> Build a FastAPI service `bookmarks` exposing CRUD for bookmark
> records (id, url, title, tags). Persist with SQLite via SQLAlchemy
> async. Provide pytest tests with `httpx.AsyncClient`. Include a
> Dockerfile.

**Notable behaviour**:

* The Architect agent will likely propose a `models / repositories /
  routers` split. The Implementation agent emits all three under
  `src/bookmarks/`.
* The Test agent uses `pytest-asyncio`; the verification runner picks
  up `pytest` automatically.
* The Security agent will flag any unconstrained user input in URL
  parameters; expect a refactor->review cycle.
* The Documentation agent writes README + `docs/API.md` reflecting the
  generated OpenAPI shape.

## 3. Library Upgrade & Refactor

**Task**:

> Take the existing project under `projects/legacy-app/` and migrate it
> from Pydantic v1 to Pydantic v2. Update all models, validators, and
> tests. Do not change behaviour.

**Notable behaviour**:

* If you start the workflow with the workspace pre-populated, the
  Planner reads existing `src/` first and produces a
  *transformation* plan rather than a green-field one.
* The Test agent runs the existing test suite *before* changes (via
  the verification runner during the test phase), which gives Review a
  baseline.
* The Refactor agent is the workhorse here; expect multiple
  refactor->review cycles and a long Implementation phase.

## How to add your own

Drop a Markdown task description into the New Job panel of the
dashboard, or pass `--task @path/to/task.md` on the CLI. The platform
treats the task as opaque — anything coherent in English works.
