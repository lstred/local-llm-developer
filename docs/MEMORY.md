# Memory & Artifacts

## Workspace Layout

Every job operates inside a *project workspace*:

```
<workspace>/
  TASK.md                  # the user's task statement (input)
  PLAN.md                  # planner output
  ARCHITECTURE.md          # architect output
  IMPLEMENTATION_LOG.md    # appended by impl/test/refactor agents
  REVIEW.md                # review output (with score)
  SECURITY.md              # security output (with score)
  TEST_RESULTS.md          # written by orchestrator after the test phase
  AUDIT.md                 # final auditor verdict + score
  README.md                # user-facing docs
  src/                     # production code (impl + refactor)
  tests/                   # tests (test agent)
  docs/                    # supplementary docs (doc agent)
  artifacts/               # archived prior versions of every overwritten file
  handoffs/                # explicit phase->phase pointers
    plan_to_architect.md
    architect_to_impl.md
    impl_to_test.md
    test_to_review.md
    review_to_refactor.md
    security_to_refactor.md
    refactor_to_review.md
    doc_to_audit.md
    _log.jsonl             # append-only audit trail of every artifact write
```

## Atomic, Versioned Writes

`ProjectMemory.write_text` performs:

1. Snapshot the prior version (if any) under
   `artifacts/<path>/<timestamp>.md`.
2. Write the new content to a temp file in the same directory.
3. `os.replace()` it onto the target — atomic on every supported OS.

This means:

* No agent can ever observe a half-written artifact.
* Every overwrite is recoverable.
* `git log` is *augmented*, not replaced — Git captures whole-workspace
  diffs per phase, while `artifacts/` captures per-file history.

## Sandboxing

All writes resolve through `ProjectMemory._safe`, which `Path.resolve()`s
the target and verifies it stays inside the workspace root. Path
traversal attempts (e.g. `../../../etc/passwd`) raise `ValueError`.

`FileWritingAgent.allowed_roots` further restricts each agent to
specific subtrees (e.g. the documentation agent may write only to
`README.md` and `docs/`). File blocks targeting other paths are
*rejected*, not silently dropped — the orchestrator records them under
`extra.rejected_paths`.

## Why Filesystem-First?

* The workspace is a self-contained, portable record of the entire run.
* Users can open it in their editor and inspect/intervene at any time.
* Agents can be reliably re-run by re-reading the workspace - no
  hidden in-memory state to reconstruct.
