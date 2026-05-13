# Anti-Lazy Enforcement

LLMs frequently produce stubs (`pass`, `TODO`, `NotImplementedError`,
mocked dependencies, "implementation left as an exercise") when they
get tired or uncertain. This platform treats such output as a *bug*
and refuses to advance the workflow until it is fixed.

## Two-Pronged Approach

1. **Prompt-level prohibition** — every system prompt embeds
   `prompts/common/anti_lazy_charter.md` which forbids these patterns
   in plain language and gives examples.
2. **Mechanical detection** — `lld.verification.anti_lazy.AntiLazyDetector`
   scans every file produced by the implementation, test, and refactor
   phases.

## Patterns Detected

| Pattern                                     | Severity |
|---------------------------------------------|----------|
| `# TODO`, `// TODO`, `<!-- TODO -->`, FIXME, XXX | error |
| Strings like `"placeholder"`, `"not implemented yet"` | error |
| `raise NotImplementedError(...)` (Python)   | error    |
| `throw new Error("not implemented")` (JS)   | error    |
| Function/method body that is *only* `pass` or `...` | error |
| Test body with no assertions and no calls   | error    |
| `unittest.mock` / `jest.mock` in `src/`     | warning  |

`@abstractmethod`-decorated methods are exempt from the empty-body rule.

## What Happens On A Hit

`AntiLazyDetector.scan_workspace(workspace)` returns a list of
`Finding`s. The orchestrator:

* writes them to the phase's `extra` payload (visible in the UI),
* attaches them to the next agent's input (so it knows what to fix),
* returns `success=False` for the phase, triggering retry / loop-back.

## Configuration

Toggle individual rules in `config/settings.yaml`:

```yaml
verification:
  anti_lazy:
    block_todos: true
    block_placeholders: true
    block_empty_bodies: true
    block_notimplemented: true
    block_mocks_in_src: true
```

Set a rule to `false` only when you genuinely want stubs (e.g. while
exploring an architecture). Re-enable before letting the auditor see
the result, or it will (correctly) BLOCK the job.
