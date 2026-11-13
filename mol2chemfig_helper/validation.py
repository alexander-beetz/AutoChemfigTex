"""Validation of values that end up in a TeX file or a subprocess call."""

from __future__ import annotations

import re


class ValidationError(ValueError):
    """Raised when user input is unsafe or would produce invalid LaTeX."""


_NAME_RE = re.compile(r"^[A-Za-z]{1,64}$")

# Control sequences that would collide with TeX/LaTeX internals or common
# packages.  This is deliberately conservative; descriptive names such as
# Azid, ParaAlkin or Product are unaffected.
_RESERVED_NAMES = frozenset(
    {
        "Alph",
        "DeclareRobustCommand",
        "Roman",
        "addtocounter",
        "alph",
        "arabic",
        "begin",
        "caption",
        "catcode",
        "cite",
        "csname",
        "def",
        "documentclass",
        "edef",
        "else",
        "emph",
        "end",
        "endcsname",
        "expandafter",
        "fi",
        "fnsymbol",
        "gdef",
        "if",
        "include",
        "input",
        "label",
        "let",
        "makeatletter",
        "makeatother",
        "newcommand",
        "newcounter",
        "newenvironment",
        "noexpand",
        "or",
        "pageref",
        "par",
        "protect",
        "providecommand",
        "ref",
        "relax",
        "renewcommand",
        "renewenvironment",
        "roman",
        "setcounter",
        "text",
        "textbf",
        "textit",
        "the",
        "usepackage",
        "value",
        "xdef",
    }
)


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def normalize_name(raw: str) -> str:
    """Normalize and validate a LaTeX control-sequence name.

    ``Azid`` and ``\\Azid`` both become ``Azid``.  Only ASCII letters are
    accepted because LaTeX control words cannot contain digits or punctuation
    without makeatletter tricks.
    """

    if not isinstance(raw, str):
        raise ValidationError("structure name must be text")

    name = raw.strip()
    if name.startswith("\\"):
        name = name[1:]

    if not name:
        raise ValidationError("structure name must not be empty")

    if not _NAME_RE.fullmatch(name):
        raise ValidationError(
            "structure name must contain only ASCII letters (A-Z, a-z), "
            "for example Azid or ParaAlkin"
        )

    if name in _RESERVED_NAMES:
        raise ValidationError(
            f"'{name}' is a reserved TeX command name; choose a descriptive name"
        )

    return name


_CMPD_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def validate_cmpd_key(raw: str) -> str:
    """Validate the key passed to ``\\cmpd{...}``.

    The key is not typeset directly; it identifies the compound number.  Keep
    it to characters that are safe inside a TeX argument and useful in labels.
    """

    if not isinstance(raw, str):
        raise ValidationError("compound label must be text")

    key = raw.strip()
    if not key:
        raise ValidationError("compound label must not be empty")

    if not _CMPD_KEY_RE.fullmatch(key):
        raise ValidationError(
            "compound label must contain only ASCII letters, digits, '.', '_', "
            "':' or '-', and must not start with punctuation"
        )

    return key


def validate_annotation(raw: str, field: str) -> str:
    """Validate one-line TeX text such as a sum formula or molecular weight.

    TeX markup is allowed, but newlines, unescaped percent signs, unescaped
    parameter characters and unbalanced braces are rejected because they would
    break the generated ``\\AzidName`` definition.
    """

    if not isinstance(raw, str):
        raise ValidationError(f"{field} must be text")

    if "\n" in raw or "\r" in raw or "\x00" in raw:
        raise ValidationError(f"{field} must be a single line without NUL bytes")

    if any(ord(char) < 32 and char != "\t" for char in raw):
        raise ValidationError(f"{field} must not contain control characters")

    value = raw.strip()
    if not value:
        raise ValidationError(f"{field} must not be empty")

    for character, explanation in {
        "%": "a comment character",
        "#": "a macro parameter character",
    }.items():
        if any(
            char == character and not _is_escaped(value, index)
            for index, char in enumerate(value)
        ):
            raise ValidationError(
                f"{field} contains an unescaped '{character}' ({explanation}); "
                f"write '\\{character}' if you need the literal character"
            )

    trailing_backslashes = len(value) - len(value.rstrip("\\"))
    if trailing_backslashes % 2:
        raise ValidationError(
            f"{field} must not end with an unescaped backslash because it would "
            "escape the closing brace of the generated macro"
        )

    depth = 0
    cursor = 0
    while cursor < len(value):
        char = value[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise ValidationError(f"{field} has an unbalanced closing brace")
        cursor += 1

    if depth:
        raise ValidationError(f"{field} has an unbalanced opening brace")

    return value


def validate_identifier(raw: str) -> str:
    """Validate a SMILES/InChI/file/PubChem identifier passed as one argument."""

    if not isinstance(raw, str):
        raise ValidationError("identifier must be text")

    if "\n" in raw or "\r" in raw or "\x00" in raw:
        raise ValidationError("identifier must be a single line without NUL bytes")

    value = raw.strip()
    if not value:
        raise ValidationError("identifier must not be empty")

    if len(value) > 20_000:
        raise ValidationError("identifier is too long (maximum 20000 characters)")

    if any(ord(char) < 32 and char != "\t" for char in value):
        raise ValidationError("identifier must not contain control characters")

    return value


def validate_m2c_arg(raw: str) -> str:
    """Validate one extra mol2chemfig command-line argument."""

    if not isinstance(raw, str):
        raise ValidationError("mol2chemfig arguments must be text")

    if not raw:
        raise ValidationError("mol2chemfig arguments must not be empty")

    if "\n" in raw or "\r" in raw or "\x00" in raw:
        raise ValidationError("mol2chemfig arguments must be single-line text")

    return raw
