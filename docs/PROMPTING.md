# Prompting System

## Layered Prompts

Every system prompt is the concatenation of three Markdown files:

```
+-----------------------------------------+
|  common/anti_lazy_charter.md            |   "rules of the team"
+-----------------------------------------+
|  roles/<role>.md                        |   "what THIS agent must do"
+-----------------------------------------+
|  common/self_review.md                  |   "before you emit, review"
+-----------------------------------------+
```

`PromptLibrary.system_prompt_for(role)` returns the assembled string and
caches it. Files are part of the installed Python package
(`lld.prompts`) and are also accessible during development from the
source tree.

## User-Side Prompts

Each agent builds the *user* prompt at runtime by injecting the
appropriate workspace artifacts. The pattern is consistent:

```
You are running the **<phase>** phase (cycle <N>).

## TASK.md
<contents>

## PLAN.md
<contents>

## handoffs/<previous>.md
<contents>

## Existing source tree (if relevant)
<### FILE: path / fenced contents>

<closing instruction reminding the agent of its output protocol>
```

This guarantees that **every agent re-reads its full inputs every
time** — no reliance on conversation history.

## Why Markdown Prompts?

* They are diff-able, reviewable, version-controlled.
* Non-developers (and the user themself) can tune behaviour without
  touching Python.
* The same files double as the human-readable spec for what each agent
  is *supposed* to do.

## Customising a Role

Edit `src/lld/prompts/roles/<role>.md`. Restart the server / CLI. There
are no plugins or callbacks to register.

## The Anti-Lazy Charter

A short list of universal rules every prompt enforces; see
`src/lld/prompts/common/anti_lazy_charter.md`. Highlights:

* No TODOs, no `pass`-only bodies, no `NotImplementedError`.
* No mocks unless explicitly requested.
* No hallucinated APIs.
* Explicit over clever; reasoning encouraged; brevity is *not* a virtue.
