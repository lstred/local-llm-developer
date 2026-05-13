# Self-Review Protocol (appended to every prompt)

Before emitting your final answer, perform an explicit self-review pass.
You may write this pass out loud as a section titled `## Self-Review` if
the role's output schema permits commentary; otherwise perform it
silently. The protocol:

1. **Re-read the task.** Did I address every requirement, or did I drop
   something?
2. **Re-read prior artifacts.** Did I contradict the Plan, the
   Architecture, or earlier code? If so, was the change deliberate and
   justified?
3. **Look for laziness.** Search my own output for: `TODO`, `FIXME`,
   `pass`, `...`, `NotImplementedError`, "placeholder", "your code here".
   If found, fix them. If I genuinely cannot implement something, replace
   the stub with an explicit `## Open Questions` entry.
4. **Look for hallucinations.** For every external library, function, or
   API I referenced, ask: *am I sure this exists with this exact
   signature?* If not certain, switch to a safer alternative (stdlib,
   widely-used package).
5. **Edge cases.** List them. For each, point to the line that handles
   it. If unhandled, fix it.
6. **Tests / verification.** If I produced code, did I (or the test
   agent) cover the happy path AND failure paths?
7. **Output format.** Does the structure match what the role prompt
   demanded?

Only after this pass produces no findings may you emit the final answer.
