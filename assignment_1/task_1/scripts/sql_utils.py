from __future__ import annotations

import re
from pathlib import Path

VERSIONED_COMMENT_RE = re.compile(r"/\*!\d+\s*(.*?)\*/", re.DOTALL)
BLOCK_COMMENT_RE = re.compile(r"/\*(?!\!)(.*?)\*/", re.DOTALL)
INSERT_RE = re.compile(
    r"^insert\s+into\s+`?(?P<table>[a-zA-Z0-9_]+)`?",
    re.IGNORECASE,
)


def is_sql_token_char(char: str) -> bool:
    return char.isalnum() or char in {"_", "`", "$"}


def unwrap_versioned_comment(match: re.Match[str]) -> str:
    content = match.group(1).strip()
    if not content:
        return ""

    start, end = match.span()
    previous_char = match.string[start - 1] if start > 0 else ""
    next_char = match.string[end] if end < len(match.string) else ""

    prefix = " " if previous_char and is_sql_token_char(previous_char) and is_sql_token_char(content[0]) else ""
    suffix = " " if next_char and is_sql_token_char(content[-1]) and is_sql_token_char(next_char) else ""
    return f"{prefix}{content}{suffix}"


def normalize_mysql_script(script: str) -> str:
    normalized = VERSIONED_COMMENT_RE.sub(unwrap_versioned_comment, script)
    normalized = BLOCK_COMMENT_RE.sub("", normalized)
    return normalized


def split_sql_statements(script: str) -> list[str]:
    normalized = normalize_mysql_script(script)
    statements: list[str] = []
    buffer: list[str] = []
    i = 0
    size = len(normalized)
    in_single = False
    in_double = False
    in_backtick = False

    while i < size:
        char = normalized[i]
        next_char = normalized[i + 1] if i + 1 < size else ""

        if in_single:
            buffer.append(char)
            if char == "\\" and i + 1 < size:
                i += 1
                buffer.append(normalized[i])
            elif char == "'":
                if next_char == "'":
                    i += 1
                    buffer.append(normalized[i])
                else:
                    in_single = False
            i += 1
            continue

        if in_double:
            buffer.append(char)
            if char == "\\" and i + 1 < size:
                i += 1
                buffer.append(normalized[i])
            elif char == '"':
                in_double = False
            i += 1
            continue

        if in_backtick:
            buffer.append(char)
            if char == "`":
                in_backtick = False
            i += 1
            continue

        if char == "-" and next_char == "-" and (i + 2 >= size or normalized[i + 2].isspace()):
            i += 2
            while i < size and normalized[i] != "\n":
                i += 1
            continue

        if char == "#":
            while i < size and normalized[i] != "\n":
                i += 1
            continue

        if char == "'":
            in_single = True
            buffer.append(char)
            i += 1
            continue

        if char == '"':
            in_double = True
            buffer.append(char)
            i += 1
            continue

        if char == "`":
            in_backtick = True
            buffer.append(char)
            i += 1
            continue

        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            i += 1
            continue

        buffer.append(char)
        i += 1

    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)

    return statements


def count_insert_rows(statement: str) -> int:
    match = re.search(r"\bvalues\b", statement, re.IGNORECASE)
    if not match:
        return 0
    return count_value_tuples(statement[match.end() :])


def count_value_tuples(values_fragment: str) -> int:
    count = 0
    depth = 0
    i = 0
    size = len(values_fragment)
    in_single = False
    in_double = False

    while i < size:
        char = values_fragment[i]
        next_char = values_fragment[i + 1] if i + 1 < size else ""

        if in_single:
            if char == "\\" and i + 1 < size:
                i += 2
                continue
            if char == "'":
                if next_char == "'":
                    i += 2
                    continue
                in_single = False
            i += 1
            continue

        if in_double:
            if char == "\\" and i + 1 < size:
                i += 2
                continue
            if char == '"':
                in_double = False
            i += 1
            continue

        if char == "'":
            in_single = True
            i += 1
            continue

        if char == '"':
            in_double = True
            i += 1
            continue

        if char == "(":
            if depth == 0:
                count += 1
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)

        i += 1

    return count


def expected_row_counts_from_sql(sql_file: Path) -> dict[str, int]:
    script = sql_file.read_text(encoding="utf-8", errors="ignore")
    counts: dict[str, int] = {}

    for statement in split_sql_statements(script):
        match = INSERT_RE.match(statement.strip())
        if not match:
            continue

        table = match.group("table")
        counts[table] = counts.get(table, 0) + count_insert_rows(statement)

    return counts
