"""Helpers for parsing agent output.

Two parser flavours:

* :func:`parse_file_blocks`  - extracts ``### FILE: <path>`` + fenced code
  blocks emitted by Implementation / Test / Refactor / Documentation.
* :func:`extract_score`      - finds a single integer 0-10 score in
  Review / Security / Audit output (``## Score: 7`` style line).

Both are intentionally tolerant of small format drift while still being
strict enough to fail loudly on truly malformed output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Match `### FILE: path` then a fenced block (```lang ... ```).
# We allow optional language tag and require closing fence.
_FILE_BLOCK_RX = re.compile(
    r"^[ \t]*#{2,4}[ \t]*FILE:[ \t]*(?P<path>[^\n\r`]+?)[ \t]*\n+"
    r"```[a-zA-Z0-9_+\-]*[ \t]*\n(?P<body>.*?)\n```",
    re.DOTALL | re.MULTILINE,
)

# Score line: "## Score: 7" or "Score: 7" or "**Score:** 7"
_SCORE_RX = re.compile(
    r"(?:^|\n)\s*(?:#{1,4}\s*|\*\*)?Score(?:\*\*)?\s*[:\-]\s*(?:\*\*)?\s*(\d{1,2})\b",
    re.IGNORECASE,
)

_VERDICT_RX = re.compile(
    r"(?:^|\n)\s*(?:#{1,4}\s*)?Verdict\s*[:\-]\s*(APPROVED|BLOCKED)\b",
    re.IGNORECASE,
)


@dataclass
class FileBlock:
    path: str
    body: str
    language: str = ""


def parse_file_blocks(text: str) -> list[FileBlock]:
    """Extract every ``### FILE: ...`` + fenced code block from ``text``."""
    out: list[FileBlock] = []
    for m in _FILE_BLOCK_RX.finditer(text):
        path = m.group("path").strip().strip("`'\"")
        body = m.group("body")
        # Normalise CRLF -> LF; ensure trailing newline.
        body = body.replace("\r\n", "\n").replace("\r", "\n")
        if not body.endswith("\n"):
            body += "\n"
        if not path:
            continue
        out.append(FileBlock(path=path, body=body))
    return out


def extract_score(text: str, default: int | None = None) -> int | None:
    m = _SCORE_RX.search(text)
    if not m:
        return default
    try:
        n = int(m.group(1))
    except ValueError:
        return default
    return max(0, min(10, n))


def extract_verdict(text: str) -> str | None:
    m = _VERDICT_RX.search(text)
    return m.group(1).upper() if m else None


__all__ = ["FileBlock", "parse_file_blocks", "extract_score", "extract_verdict"]
