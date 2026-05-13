# Local LLM Developer

> A local-first AI software-engineering orchestration platform for a single
> RTX 3070 laptop (8 GB VRAM). It coordinates a *team* of specialised AI
> agents that work **sequentially** to maximise software quality while
> minimising GPU memory usage.

This is **not** a speed-focused system. It is a *meticulous senior
engineering team that never rushes*. Waiting 20+ minutes for a high-quality
result is acceptable, even expected.

---

## Philosophy

The platform exists to produce the **highest-quality** AI-generated software
possible on consumer hardware. Every architectural decision optimises for:

- correctness over speed
- completeness over responsiveness
- robustness over cleverness
- verification over assumption
- explicit reasoning over hidden shortcuts

Agents are explicitly forbidden from generating placeholders, fake tests,
unimplemented branches, or "TODO" cop-outs. The orchestrator detects and
rejects such outputs (see [docs/ANTI_LAZY.md](docs/ANTI_LAZY.md)).

---

## The Agent Team

Agents run **one at a time**. Only one model is resident in VRAM at any
moment. Between phases the previous model is unloaded.

| # | Agent              | Default model            | Role                                         |
|---|--------------------|--------------------------|----------------------------------------------|
| 1 | Planner            | `qwen3:8b`               | Decomposes the task into milestones          |
| 2 | Architect          | `qwen3:8b`               | Designs system architecture & contracts      |
| 3 | Implementation     | `qwen2.5-coder:7b`       | Writes production code                       |
| 4 | Test               | `qwen2.5-coder:7b`       | Writes & runs tests                          |
| 5 | Review             | `deepseek-r1:8b`         | Senior-engineer code review                  |
| 6 | Security           | `deepseek-r1:8b`         | OWASP / threat-modelling pass                |
| 7 | Refactor           | `qwen2.5-coder:7b`       | Applies review + security findings           |
| 8 | Documentation      | `phi4-mini`              | Generates user / API docs                    |
| 9 | Final Auditor      | `deepseek-r1:8b`         | Blocking quality gate before "done"          |

All assignments are configurable in [`config/models.yaml`](config/models.yaml).

---

## Quick Start

```bash
# 1. Install Ollama  (https://ollama.com) and pull the default models
ollama pull qwen3:8b
ollama pull qwen2.5-coder:7b
ollama pull deepseek-r1:8b
ollama pull phi4-mini

# 2. Install the platform
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e .

# 3. Run the orchestrator API + UI
local-llm-dev serve              # http://127.0.0.1:8765

# 4. Or run a job from the CLI
local-llm-dev run --task "Build a CLI todo app with SQLite persistence" \
                  --workspace ./projects/todo-app
```

The UI shows: current agent, phase progress, live logs, generated artifacts,
review findings, confidence scores, and retry history.

---

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - system architecture
- [docs/ORCHESTRATOR.md](docs/ORCHESTRATOR.md) - orchestrator design
- [docs/AGENTS.md](docs/AGENTS.md) - agent framework
- [docs/PROMPTING.md](docs/PROMPTING.md) - prompting system
- [docs/MEMORY.md](docs/MEMORY.md) - memory & artifacts
- [docs/EXECUTION.md](docs/EXECUTION.md) - execution engine
- [docs/REVIEW_LOOPS.md](docs/REVIEW_LOOPS.md) - review & critique
- [docs/TESTING.md](docs/TESTING.md) - testing pipeline
- [docs/UI.md](docs/UI.md) - UI design
- [docs/ANTI_LAZY.md](docs/ANTI_LAZY.md) - anti-lazy detector rules
- [docs/ROADMAP.md](docs/ROADMAP.md) - implementation roadmap
- [docs/WORKFLOWS.md](docs/WORKFLOWS.md) - example workflows

---

## License

MIT - see [LICENSE](LICENSE).
