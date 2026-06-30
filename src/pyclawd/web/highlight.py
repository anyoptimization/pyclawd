"""Server-side syntax highlighting for diff lines (Pygments, full-file context).

Highlighting a diff line-by-line in the browser would mangle multi-line
constructs — docstrings, triple-quoted strings — because each line loses the
lexer state of the lines around it. Instead we tokenise the *whole* file on the
server with Pygments and hand the frontend one ready-made HTML fragment per
source line, so a docstring spanning ten lines is coloured correctly on every
one of them.

Pygments ships transitively with rich (a core pyclawd dependency), so this adds
no install cost. It still degrades gracefully: any failure — no lexer for the
file type, Pygments unavailable — returns ``None`` and callers fall back to
plain text.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

#: CSS class prefix for emitted token spans (matched by the dashboard stylesheet).
CLASS_PREFIX = "pl-"


@lru_cache(maxsize=256)
def _lexer_for(path: str) -> Any | None:
    """Return a Pygments lexer for *path* by filename, or ``None`` if unknown."""
    try:
        from pygments.lexers import get_lexer_for_filename
        from pygments.lexers.special import TextLexer
        from pygments.util import ClassNotFound
    except ImportError:
        return None
    try:
        lexer = get_lexer_for_filename(path, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return None
    # Plain-text files resolve to TextLexer, which emits no token spans — skip it
    # so callers fall back to plain text instead of shipping redundant markup.
    return None if isinstance(lexer, TextLexer) else lexer


def highlight_lines(path: str, source: list[str]) -> list[str] | None:
    """Return one HTML fragment per line of *source*, or ``None`` if not highlightable.

    The result is aligned 1:1 with *source* (same length). Each fragment is safe
    to inject as-is: Pygments HTML-escapes the text and never emits a span that
    crosses a line boundary, so per-line injection is sound.

    Args:
        path: Repo-relative path; its extension selects the lexer.
        source: The file's lines, without trailing newlines.

    Returns:
        A list of HTML strings (one per input line), or ``None`` when no lexer
        matches the file type or Pygments is unavailable.
    """
    lexer = _lexer_for(path)
    if lexer is None or not source:
        return None
    try:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
    except ImportError:
        return None
    fmt = HtmlFormatter(nowrap=True, classprefix=CLASS_PREFIX)
    rendered = highlight("\n".join(source), lexer, fmt).split("\n")
    # Pygments may emit a trailing empty element; align strictly to the input.
    if len(rendered) < len(source):
        rendered += [""] * (len(source) - len(rendered))
    return rendered[: len(source)]
