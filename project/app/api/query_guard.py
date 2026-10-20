"""Shared read-only SQL guard for the Query Lab.

Both the Pydantic schema (``QueryRequest``) and the router use this module so
validation is identical at the HTTP boundary and at execution time.

Rules enforced:

* After stripping leading whitespace, ``--`` line comments, ``/* */`` block
  comments and opening parentheses, the first keyword must be ``SELECT``,
  ``WITH`` or ``EXPLAIN`` (case-insensitive, any whitespace after).
* Exactly one statement: at most one ``;`` outside string literals and
  comments, and only as the trailing terminator (whitespace/comments may
  follow). A ``;`` inside ``'...'`` / ``"..."`` / ```...``` is data, not a
  terminator.
* No write/DDL keywords outside strings/comments (word-boundary match):
  INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE,
  COMMIT, ROLLBACK, REPLACE, MERGE, CALL, VACUUM, ATTACH, DETACH, COPY.
  ``SELECT ... INTO new_table`` (Postgres table creation) is also rejected,
  as are ``FOR UPDATE`` / ``FOR SHARE`` row locks.
* Comments (``--`` and ``/* */``) and string literals are allowed anywhere;
  they are masked before keyword/semicolon detection so they can neither
  smuggle a second statement nor cause a false rejection.
"""

from __future__ import annotations

import re

WRITE_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "truncate",
    "grant",
    "revoke",
    "commit",
    "rollback",
    "replace",
    "merge",
    "call",
    "vacuum",
    "attach",
    "detach",
    "copy",
)

_WRITE_RE = re.compile(r"\b(" + "|".join(WRITE_KEYWORDS) + r")\b", re.IGNORECASE)
_INTO_RE = re.compile(r"\binto\b", re.IGNORECASE)
_FOR_LOCK_RE = re.compile(r"\bfor\s+(update|share|no\s+key\s+update)\b", re.IGNORECASE)
_FIRST_KEYWORD_RE = re.compile(r"(select|with|explain)\b", re.IGNORECASE)


def _scan(sql: str) -> tuple[str, list[int]]:
    """Mask strings/comments with spaces; return (masked, semicolon_positions).

    Single pass so a ``--`` inside ``'...'`` is data, and a quote inside a
    comment does not open a string. Handles ``'...'`` (with ``''`` and
    backslash escapes), ``"..."`` and ```...``` identifiers, ``--`` to end of
    line, and ``/* ... */`` blocks (unclosed block runs to end of input).
    """
    masked = list(sql)
    semicolons: list[int] = []
    i = 0
    n = len(sql)
    in_single = in_double = in_backtick = False
    in_line_comment = in_block_comment = False

    def mask(pos: int) -> None:
        if masked[pos] not in ("\n",):
            masked[pos] = " "

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if in_line_comment:
            mask(i)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            mask(i)
            if ch == "*" and nxt == "/":
                mask(i + 1)
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue
        if in_single:
            mask(i)
            if ch == "\\" and i + 1 < n:
                mask(i + 1)
                i += 2
                continue
            if ch == "'":
                if nxt == "'":  # escaped '' inside literal
                    mask(i + 1)
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if in_double:
            mask(i)
            if ch == "\\" and i + 1 < n:
                mask(i + 1)
                i += 2
                continue
            if ch == '"':
                if nxt == '"':
                    mask(i + 1)
                    i += 2
                    continue
                in_double = False
            i += 1
            continue
        if in_backtick:
            mask(i)
            if ch == "`":
                in_backtick = False
            i += 1
            continue

        # code context
        if ch == "-" and nxt == "-":
            # ``--`` starts a comment only when not part of a longer operator?
            # In SQL ``--`` always starts a comment, even in ``a--b``.
            mask(i)
            mask(i + 1)
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            mask(i)
            mask(i + 1)
            in_block_comment = True
            i += 2
            continue
        if ch == "'":
            mask(i)
            in_single = True
            i += 1
            continue
        if ch == '"':
            mask(i)
            in_double = True
            i += 1
            continue
        if ch == "`":
            mask(i)
            in_backtick = True
            i += 1
            continue
        if ch == ";":
            semicolons.append(i)
        i += 1

    return "".join(masked), semicolons


def _strip_leading(masked: str) -> str:
    """Remove leading whitespace, comments (already masked to spaces) and '('."""
    stripped = masked.lstrip()
    while stripped.startswith("("):
        stripped = stripped[1:].lstrip()
    return stripped


def validate_readonly(sql: str) -> str:
    """Validate a read-only statement; return the original SQL or raise ValueError."""
    if sql is None or not str(sql).strip():
        raise ValueError("SQL statement is empty")
    original = str(sql)
    masked, semicolons = _scan(original)

    # --- single statement: at most one ';' outside strings/comments, trailing only
    if semicolons:
        if len(semicolons) > 1:
            raise ValueError("only one statement per query; semicolon-separated batches are refused")
        only = semicolons[0]
        trailing = masked[only + 1 :]
        if trailing.strip():
            raise ValueError("only one statement per query; content after ';' is refused")

    # --- first keyword must be SELECT / WITH / EXPLAIN
    leading = _strip_leading(masked)
    match = _FIRST_KEYWORD_RE.match(leading)
    if not match:
        raise ValueError("only SELECT / WITH / EXPLAIN statements are allowed")

    # --- no write/DDL keywords outside strings/comments
    write = _WRITE_RE.search(masked)
    if write:
        raise ValueError(f"statement contains a forbidden keyword '{write.group(1).upper()}'")
    # SELECT ... INTO new_table creates a table in Postgres.
    if _INTO_RE.search(masked):
        # ``INSERT INTO`` is already rejected; any remaining INTO in a SELECT
        # can only be the table-creating variant.
        raise ValueError("SELECT ... INTO is not allowed in the read-only console")
    if _FOR_LOCK_RE.search(masked):
        raise ValueError("locking reads (FOR UPDATE / FOR SHARE) are not allowed")

    return original


def clean_for_execution(sql: str) -> str:
    """Remove the single trailing ``;`` terminator (if any) for subquery wrapping.

    Keeps trailing ``-- reference: ...`` comments intact; the caller must still
    wrap with a newline before the closing paren so a trailing line comment
    cannot swallow the wrapper suffix.
    """
    text = str(sql).strip()
    _, semicolons = _scan(text)
    if not semicolons:
        return text
    pos = semicolons[0]
    return (text[:pos] + text[pos + 1 :]).strip()


def is_explain(statement: str) -> bool:
    """True when the (already validated) statement is an EXPLAIN plan request."""
    masked, _ = _scan(statement)
    return _strip_leading(masked).lower().startswith("explain")


__all__ = [
    "WRITE_KEYWORDS",
    "validate_readonly",
    "clean_for_execution",
    "is_explain",
]
