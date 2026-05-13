# Agent Framework

Every agent inherits from `lld.agents.base.Agent` and implements
`run(memory, model_manager, cycle, context) -> AgentResult`. The base
class supplies a `system_prompt()` helper that concatenates:

1. `prompts/common/anti_lazy_charter.md` — universal rules.
2. `prompts/roles/<role>.md` — the role's specification.
3. `prompts/common/self_review.md` — the mandatory self-review pass.

## The Nine Roles

| Role           | Class                  | Inputs                                          | Outputs                                       |
|----------------|------------------------|-------------------------------------------------|-----------------------------------------------|
| planner        | `PlannerAgent`         | TASK.md                                         | PLAN.md, handoffs/plan_to_architect.md        |
| architect      | `ArchitectAgent`       | TASK, PLAN, plan handoff                        | ARCHITECTURE.md, handoffs/architect_to_impl.md |
| implementation | `ImplementationAgent`  | TASK, PLAN, ARCHITECTURE, prior `src/`          | `src/**`, IMPLEMENTATION_LOG.md, handoff      |
| test           | `TestAgent`            | ARCHITECTURE, `src/**`, prior TEST_RESULTS.md   | `tests/**`, TEST_RESULTS.md (by orchestrator) |
| review         | `ReviewAgent`          | `src/**`, `tests/**`, ARCHITECTURE, TEST_RESULTS| REVIEW.md, handoffs/review_to_refactor.md     |
| security       | `SecurityAgent`        | `src/**`, ARCHITECTURE                          | SECURITY.md, handoffs/security_to_refactor.md |
| refactor       | `RefactorAgent`        | REVIEW, SECURITY, both handoffs, `src/**`       | `src/**`, IMPLEMENTATION_LOG addendum         |
| documentation  | `DocumentationAgent`   | ARCHITECTURE, `src/**`, README                  | README.md, `docs/**`                          |
| final_auditor  | `FinalAuditorAgent`    | everything above                                | AUDIT.md (verdict + score)                    |

## Output Protocols

* **Markdown agents** (planner, architect, review, security, audit)
  emit a single Markdown document; the orchestrator writes it to a
  fixed canonical filename.
* **File-writing agents** (implementation, test, refactor,
  documentation) emit one or more `### FILE: <path>` blocks containing
  full file contents. The parser (`lld.agents.parsing.parse_file_blocks`)
  extracts them. Paths are sandboxed to per-agent `allowed_roots`.
* **Scored agents** (review, security, audit) include a `## Score: <n>`
  line; `extract_score` parses it. The Final Auditor additionally
  includes `## Verdict: APPROVED|BLOCKED`.

## Why "stateless across calls"?

Every agent reads its full input set from the workspace each time it
runs. There is no in-memory hand-over between phases. This makes:

* phases independently auditable;
* the system trivially resumable;
* "loop back" a no-op for the agent (it sees the most recent state).

## Adding a New Agent

1. Create `src/lld/prompts/roles/<role>.md` with a precise spec.
2. Create a subclass of `Agent` (or `FileWritingAgent`) under
   `src/lld/agents/`.
3. Register it in `src/lld/agents/registry.py`.
4. Add it as a phase in `config/workflow.yaml`.
