"""Small, deliberately limited TeX scanners.

This is not a TeX parser.  It understands the constructs needed to find and
replace generated macro definitions: braces, backslash escapes and line
comments.  Keeping the scanner small makes the replacement logic predictable
and easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


class TexScanError(ValueError):
    """Raised when a TeX construct cannot be scanned safely."""


def is_escaped(text: str, index: int) -> bool:
    """Return True if text[index] is preceded by an odd number of backslashes."""

    count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        count += 1
        cursor -= 1
    return count % 2 == 1


def mask_comments(text: str) -> str:
    """Return a same-length copy with comment text replaced by spaces.

    Newlines are preserved so offsets and line numbers stay valid.  The mask is
    used only for locating commands; all replacement work uses the original
    text.
    """

    chars = list(text)
    cursor = 0
    while cursor < len(text):
        if text[cursor] == "%" and not is_escaped(text, cursor):
            end = text.find("\n", cursor)
            if end == -1:
                end = len(text)
            for position in range(cursor, end):
                chars[position] = " "
            cursor = end
        else:
            cursor += 1
    return "".join(chars)


def find_matching_brace(text: str, open_index: int) -> int:
    """Return the index of the brace matching text[open_index].

    Backslash escapes and TeX line comments are respected.
    """

    if open_index < 0 or open_index >= len(text) or text[open_index] != "{":
        raise TexScanError("expected an opening brace")

    depth = 0
    cursor = open_index
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            # Skip the escaped character.  This also skips \{, \} and \%.
            cursor += 2
            continue
        if char == "%":
            newline = text.find("\n", cursor)
            cursor = len(text) if newline == -1 else newline + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return cursor
            if depth < 0:
                raise TexScanError("unbalanced closing brace")
        cursor += 1

    raise TexScanError("unbalanced opening brace")


@dataclass(frozen=True)
class DefinitionSpan:
    """Location of a macro definition found in a TeX file."""

    name: str
    command: str
    start: int
    end: int
    replaceable: bool
    reason: str | None = None


_DEFINITION_PATTERNS = (
    re.compile(
        r"\\(?P<command>DeclareRobustCommand|newcommand|renewcommand|providecommand"
        r"|newrobustcmd|renewrobustcmd)\*?"
        r"\s*\{?\s*\\(?P<name>[A-Za-z]+)\s*\}?"
    ),
    re.compile(
        r"\\(?P<command>DeclareDocumentCommand|NewDocumentCommand"
        r"|RenewDocumentCommand|ProvideDocumentCommand)"
        r"\s*\{\s*\\(?P<name>[A-Za-z]+)\s*\}"
    ),
    re.compile(r"\\(?P<command>def|gdef|edef|xdef)\s*\\(?P<name>[A-Za-z]+)"),
    re.compile(r"\\(?P<command>let)\s*\\(?P<name>[A-Za-z]+)"),
)

_XPARSE_COMMANDS = frozenset(
    {
        "DeclareDocumentCommand",
        "NewDocumentCommand",
        "RenewDocumentCommand",
        "ProvideDocumentCommand",
    }
)


def _skip_space_and_comments(text: str, cursor: int) -> int:
    while cursor < len(text):
        if text[cursor].isspace():
            cursor += 1
        elif text[cursor] == "%" and not is_escaped(text, cursor):
            newline = text.find("\n", cursor)
            cursor = len(text) if newline == -1 else newline + 1
        else:
            break
    return cursor


def _skip_optional_argument(text: str, cursor: int) -> int:
    """Return the index just after the optional argument starting at cursor."""

    if cursor >= len(text) or text[cursor] != "[":
        raise TexScanError("expected an optional argument")
    depth = 0
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "%":
            newline = text.find("\n", cursor)
            cursor = len(text) if newline == -1 else newline + 1
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    raise TexScanError("unbalanced optional argument")


def _find_body_start(text: str, cursor: int, command: str) -> int:
    cursor = _skip_space_and_comments(text, cursor)

    if command in _XPARSE_COMMANDS:
        if cursor >= len(text) or text[cursor] != "{":
            raise TexScanError("expected an argument specification")
        cursor = find_matching_brace(text, cursor) + 1
        cursor = _skip_space_and_comments(text, cursor)

    while cursor < len(text) and text[cursor] == "[":
        cursor = _skip_optional_argument(text, cursor)
        cursor = _skip_space_and_comments(text, cursor)

    # For \def-like commands the parameter text may contain #1 etc.  The body
    # starts at the first unescaped opening brace.
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "%":
            newline = text.find("\n", cursor)
            cursor = len(text) if newline == -1 else newline + 1
            continue
        if char == "{":
            return cursor
        cursor += 1

    raise TexScanError("macro body not found")


def find_definitions(
    text: str,
    name: str | None = None,
    *,
    exclude: tuple[tuple[int, int], ...] = (),
) -> tuple[DefinitionSpan, ...]:
    """Find macro definitions, optionally restricted to one control-sequence name.

    Definitions inside the half-open ranges in ``exclude`` are ignored.  The
    generated managed blocks use that to avoid mistaking their own contents for
    user-written definitions.
    """

    masked = mask_comments(text)
    spans: list[DefinitionSpan] = []
    seen: set[tuple[int, int, str]] = set()

    for pattern in _DEFINITION_PATTERNS:
        for match in pattern.finditer(masked):
            if is_escaped(masked, match.start()):
                continue

            found_name = match.group("name")
            command = match.group("command")
            if command == "let":
                span = DefinitionSpan(
                    name=found_name,
                    command=command,
                    start=match.start(),
                    end=match.end(),
                    replaceable=False,
                    reason="\\let definitions are not supported for automatic replacement",
                )
            else:
                try:
                    body_start = _find_body_start(text, match.end(), command)
                    end = find_matching_brace(text, body_start) + 1
                    span = DefinitionSpan(
                        name=found_name,
                        command=command,
                        start=match.start(),
                        end=end,
                        replaceable=True,
                    )
                except TexScanError as exc:
                    span = DefinitionSpan(
                        name=found_name,
                        command=command,
                        start=match.start(),
                        end=match.end(),
                        replaceable=False,
                        reason=str(exc),
                    )

            key = (span.start, span.end, span.name)
            if key not in seen:
                seen.add(key)
                spans.append(span)

    # A definition inside another definition's body cannot be replaced on its
    # own without corrupting the outer definition.
    marked: list[DefinitionSpan] = []
    for span in spans:
        nested = any(
            other.start < span.start and span.end <= other.end
            for other in spans
            if other is not span
        )
        if nested and span.replaceable:
            span = DefinitionSpan(
                name=span.name,
                command=span.command,
                start=span.start,
                end=span.end,
                replaceable=False,
                reason="definition is nested inside another macro definition",
            )
        marked.append(span)

    marked.sort(key=lambda item: item.start)
    return tuple(
        span
        for span in marked
        if (name is None or span.name == name)
        and not any(start <= span.start < end for start, end in exclude)
    )
