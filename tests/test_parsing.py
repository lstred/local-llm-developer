"""Tests for the agent output parser."""

from __future__ import annotations

from lld.agents.parsing import (
    extract_score,
    extract_verdict,
    parse_file_blocks,
)


def test_parse_single_file_block():
    text = """
Some preamble.

### FILE: src/foo.py
```python
def add(a: int, b: int) -> int:
    return a + b
```

Trailing notes.
"""
    blocks = parse_file_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].path == "src/foo.py"
    assert "def add" in blocks[0].body
    assert blocks[0].body.endswith("\n")


def test_parse_multiple_file_blocks_with_varied_languages():
    text = """
### FILE: src/a.py
```python
x = 1
```

### FILE: src/b.js
```javascript
const y = 2;
```

### FILE: README.md
```
hello
```
"""
    blocks = parse_file_blocks(text)
    assert [b.path for b in blocks] == ["src/a.py", "src/b.js", "README.md"]


def test_parse_ignores_blocks_without_file_marker():
    text = """
Here is some code:

```python
print("not attached to a FILE: header")
```
"""
    assert parse_file_blocks(text) == []


def test_parse_normalises_crlf():
    text = "### FILE: src/x.py\r\n```python\r\nprint('hi')\r\n```\r\n"
    blocks = parse_file_blocks(text)
    assert len(blocks) == 1
    assert "\r" not in blocks[0].body


def test_extract_score_variants():
    assert extract_score("## Score: 8") == 8
    assert extract_score("Score: 7") == 7
    assert extract_score("**Score:** 9 out of 10") == 9
    assert extract_score("no score here", default=None) is None
    # Score is clamped to 0..10
    assert extract_score("Score: 42") == 10
    assert extract_score("Score: -5") is None  # regex requires positive digit run


def test_extract_verdict():
    assert extract_verdict("## Verdict: APPROVED") == "APPROVED"
    assert extract_verdict("Verdict: blocked") == "BLOCKED"
    assert extract_verdict("nothing here") is None
