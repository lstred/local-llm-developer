# UI

A deliberately small HTML/CSS/JS dashboard served by FastAPI at `/`.
No build step, no framework, no bundler.

## Layout

```
+--------------------------------------------------+
|  local-llm-developer    [provider · model badge] |
+----------------------+---------------------------+
|  New Job             |  Jobs                     |
|  [task textarea]     |  - id status              |
|  [workspace name]    |  - id status              |
|  [Start]             |  ...                      |
+----------------------+---------------------------+
|  Job Detail (selected job)                       |
|  Summary | Phases table | Artifacts list | View |
+--------------------------------------------------+
|  Live Events (websocket stream)                  |
+--------------------------------------------------+
```

## Pages / Endpoints

| Route                          | Purpose                                  |
|--------------------------------|------------------------------------------|
| `GET /`                        | Single-page dashboard                    |
| `GET /api/health`              | Provider connectivity + current model    |
| `GET /api/config`              | Resolved model / workflow / anti-lazy    |
| `GET /api/jobs`                | List recent jobs                         |
| `POST /api/jobs`               | Create + start a new job                 |
| `GET /api/jobs/{id}`           | Job + phases + events                    |
| `GET /api/jobs/{id}/artifact?path=...` | Read a file from the workspace   |
| `POST /api/jobs/{id}/cancel`   | Request cancellation                     |
| `WS /ws/events`                | Live stream of orchestrator events       |

## Live Events

Every orchestrator event (`phase.start`, `phase.end`, `phase.decision`,
`job.end`, ...) is fanned out to the websocket. The UI updates the
phases table and refreshes the job summary in response. Events are
also persisted to the SQLite `events` table so a late-joining client
can rebuild history via `GET /api/jobs/{id}`.

## Why So Plain?

Because the value is in the *artifacts*, not the chrome. The UI's job
is to make it easy to:

* see which agent is running and on which model,
* see which phase is in retry / loop-back territory,
* read every artifact the agents produced, and
* watch the structured event log.

Editing artifacts is intentionally not offered by the UI — that is the
user's editor's job. Open the workspace folder in VS Code; the platform
will pick up your edits the next time the workflow re-reads them.
