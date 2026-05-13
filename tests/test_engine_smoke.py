"""End-to-end engine test using a stub provider (no real LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lld.app import build_app_context
from lld.models import GenerationRequest, GenerationResult, ModelManager, ModelProvider
from lld.orchestrator import Engine, JobSpec
from lld.persistence import StateStore
from lld.prompts import PromptLibrary
from lld.config import AppConfig


class StubProvider(ModelProvider):
    """Returns canned per-role outputs so the engine can run end-to-end."""

    name = "stub"

    RESPONSES = {
        "planner": (
            "# Plan\n\n"
            "## 1. Restatement of the Task\nAdd two integers.\n\n"
            "## 2. Goals & Non-Goals\n- Goal: implement add(a, b).\n\n"
            "## 3. Assumptions\n- Inputs are ints.\n\n"
            "## 4. Open Questions\n- None [NON-BLOCKING]\n\n"
            "## 5. Milestones\n1. add function\n   - DoD: returns a+b\n"
            "## 6. Recommended Tech Surface\nPython 3.10+\n\n"
            "## 7. Success Criteria\nadd(2,3)==5\n"
        ),
        "architect": (
            "# Architecture\n\n## 1. Overview\nSingle module.\n"
            "## 4. Public Contracts\n`add(a:int,b:int)->int`\n"
        ),
        "implementation": (
            "### FILE: src/calc.py\n"
            "```python\n"
            "from __future__ import annotations\n"
            "def add(a: int, b: int) -> int:\n"
            "    if not isinstance(a, int) or not isinstance(b, int):\n"
            "        raise TypeError('ints required')\n"
            "    return a + b\n"
            "```\n"
        ),
        "test": (
            "### FILE: tests/test_calc.py\n"
            "```python\n"
            "import pytest\n"
            "from src.calc import add\n"
            "def test_add_happy():\n    assert add(2, 3) == 5\n"
            "def test_add_rejects_strings():\n"
            "    with pytest.raises(TypeError):\n        add('a', 1)\n"
            "```\n"
        ),
        "review": "# Review\n## Summary\nLooks good.\n## Score: 9\n",
        "security": "# Security\n## Summary\nNo issues.\n## Score: 10\n",
        "refactor": (
            "### FILE: src/calc.py\n"
            "```python\n"
            "from __future__ import annotations\n"
            "def add(a: int, b: int) -> int:\n"
            "    if not isinstance(a, int) or not isinstance(b, int):\n"
            "        raise TypeError('ints required')\n"
            "    return a + b\n"
            "```\n"
        ),
        "documentation": (
            "### FILE: README.md\n```\n# Calc\nAdd two ints with `add(a, b)`.\n```\n"
        ),
        "final_auditor": (
            "# Final Audit\n## Verdict: APPROVED\n## Score: 9\n"
            "## Quality Dimensions\n- Correctness: 9\n"
        ),
    }

    async def generate(self, req: GenerationRequest) -> GenerationResult:
        # Pick the response by inspecting the system prompt for the role header.
        role = "implementation"
        for r in self.RESPONSES:
            if f"# Role: {r.replace('_', ' ').title()}" in req.system or \
               f"role: {r}" in req.system.lower():
                role = r
                break
        # Better: identify by the `role` field encoded in our prompts via filename.
        for r in self.RESPONSES:
            if f"# Role: {r.title().replace('_', ' ')}" in req.system:
                role = r
                break
        # Direct match using known headings.
        mapping = {
            "Planner": "planner", "Architect": "architect",
            "Implementation": "implementation", "Test": "test",
            "Review": "review", "Security": "security",
            "Refactor": "refactor", "Documentation": "documentation",
            "Final Auditor": "final_auditor",
        }
        for header, r in mapping.items():
            if f"# Role: {header}" in req.system:
                role = r
                break
        return GenerationResult(text=self.RESPONSES[role], model=req.model)

    async def unload(self, model: str) -> None:
        return None

    async def list_loaded(self) -> list[str]:
        return []


@pytest.mark.asyncio
async def test_engine_runs_full_pipeline_with_stub(tmp_path: Path, monkeypatch):
    # Use stub provider so we don't need Ollama running.
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    cfg = AppConfig.load("config")
    # Redirect storage paths into tmp_path to keep tests hermetic.
    cfg.settings.storage.state_dir = tmp_path / "state"
    cfg.settings.storage.database_url = (
        f"sqlite+aiosqlite:///{(tmp_path / 'state' / 'orch.db').as_posix()}"
    )
    cfg.settings.storage.projects_root = tmp_path / "projects"
    cfg.settings.logging.log_file = tmp_path / "state" / "logs" / "x.log"
    cfg.settings.git.enabled = False  # don't pollute with git inits
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)

    store = StateStore(cfg.settings.storage.database_url)
    await store.init()
    manager = ModelManager(StubProvider())
    engine = Engine(cfg, manager, store, PromptLibrary())

    workspace = tmp_path / "projects" / "calc"
    workspace.mkdir(parents=True)
    spec = JobSpec(
        job_id=engine.make_job_id(),
        workspace=workspace,
        task="Implement add(a:int, b:int) -> int.",
    )

    outcome = await engine.run_job(spec)

    assert outcome.status in {"completed", "blocked"}
    assert (workspace / "PLAN.md").read_text().startswith("# Plan")
    assert (workspace / "ARCHITECTURE.md").read_text().startswith("# Architecture")
    assert (workspace / "src" / "calc.py").exists()
    assert (workspace / "tests" / "test_calc.py").exists()
    # Audit verdict captured.
    audit = (workspace / "AUDIT.md").read_text()
    assert "Verdict" in audit

    await manager.close()
    await store.close()
