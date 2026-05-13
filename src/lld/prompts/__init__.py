"""Prompt assembly.

Each role has a primary prompt under ``prompts/roles/<role>.md``. Two
universal fragments are concatenated to every system prompt:

* ``prompts/common/anti_lazy_charter.md`` - rules every agent must obey.
* ``prompts/common/self_review.md``       - the mandatory self-review pass.

The :class:`PromptLibrary` caches file contents (they are part of the
installed package) and produces the final system prompt for an agent.
The user-message prompt is constructed by the agent itself.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path


class PromptLibrary:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    # -- Loading ---------------------------------------------------------- #

    def _read(self, relpath: str) -> str:
        if relpath in self._cache:
            return self._cache[relpath]
        # Try installed-package resources first; fall back to source layout.
        try:
            data = (resources.files("lld.prompts")
                    .joinpath(relpath).read_text(encoding="utf-8"))
        except (FileNotFoundError, ModuleNotFoundError, AttributeError):
            here = Path(__file__).parent
            data = (here / relpath).read_text(encoding="utf-8")
        self._cache[relpath] = data
        return data

    # -- Public ----------------------------------------------------------- #

    def system_prompt_for(self, role: str) -> str:
        role_body = self._read(f"roles/{role}.md")
        charter = self._read("common/anti_lazy_charter.md")
        review = self._read("common/self_review.md")
        return (
            f"{charter}\n\n---\n\n{role_body}\n\n---\n\n{review}\n"
        )

    def role_body(self, role: str) -> str:
        return self._read(f"roles/{role}.md")


__all__ = ["PromptLibrary"]
