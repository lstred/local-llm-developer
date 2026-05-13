# Review Loops

Quality is enforced by two cooperating mechanisms:

1. **Mechanical gates** — fast, deterministic, run by the orchestrator.
2. **LLM critique** — the Review, Security, and Final Auditor agents.

## Mechanical Gates (no LLM)

* **Anti-lazy detector** (`lld.verification.anti_lazy.AntiLazyDetector`)
  — scans `src/` and `tests/` for placeholder patterns, empty bodies,
  `NotImplementedError`, mocks in production, etc. Errors block phase
  progression; warnings are logged.
* **Verification runners** (`lld.verification.runners`) — pytest, ruff,
  mypy (Python projects); npm test (Node). A non-zero exit code from a
  hard test runner blocks progression.

These gates run *before* the LLM review agents, so the Review agent
never wastes cycles re-discovering things the detector already caught.

## LLM Critique Layer

* **Review** — full code review with severity-tagged findings and a
  0-10 score. Drives the refactor->review repair loop.
* **Security** — OWASP-oriented audit with its own score and severity
  vocabulary (critical/high/medium/low/informational).
* **Final Auditor** — last gate. Produces a verdict
  (`APPROVED`/`BLOCKED`) and a 0-10 score. The orchestrator BLOCKS the
  job if the score is below `min_audit_score` *or* the verdict is
  `BLOCKED`.

## The Review->Refactor->Review Cycle

```
+----------+     score >= min     +-----------+
| review   |--------------------->| security  |
+----------+                      +-----------+
     |                                  |
     | (always)                         | (always)
     v                                  v
+----------+   re-review under cap +----------+
| refactor |--------------------->| review   |
+----------+                      +----------+
                                       |
                       cycles exhausted v
                                  +-----------+
                                  | document  |
                                  +-----------+
```

Cap: `quality.max_review_cycles`. The final review pass after the last
allowed refactor produces the score the auditor consumes.

## Recursive Critique

The "self-review" appendix on every system prompt forces each agent to
critique its *own* output before emitting. This is not a separate
review pass — it is folded into the agent's single generate() call,
which keeps VRAM cost flat.

## Confidence Scoring

* Numeric scores (0-10) come from review/security/audit agents.
* Verdict comes from the auditor.
* The UI surfaces both per-phase. The CLI's `show <job_id>` command
  prints the same data.

## Why Bound the Loops?

To guarantee progress. Without caps, a stubborn refactor->review cycle
could spin forever. With caps, the worst case is `BLOCKED` with a
detailed `AUDIT.md` explaining what to do next — which is precisely the
behaviour the user asked for.
