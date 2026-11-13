"""Pure text operations for structures.tex.

The file remains a normal LaTeX input file.  Generated definitions are wrapped
in explicit comment markers, so they can be replaced without touching any
hand-written LaTeX around them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
import shlex

from .texscan import DefinitionSpan, find_definitions


class TexFileError(ValueError):
    """Raised for malformed managed blocks or unsafe replacements."""


@dataclass(frozen=True)
class Entry:
    """Everything needed to render one managed structure block."""

    name: str
    identifier: str
    input_format: str
    label: str  # key passed to \cmpd{...}
    chemfig: str
    m2c_args: tuple[str, ...] = ()
    formula: str | None = None
    mw: str | None = None

    @property
    def label_macro_name(self) -> str:
        return f"{self.name}Name"

    @property
    def raw_macro_name(self) -> str:
        return f"{self.name}Structure"

    @property
    def extras_macro_name(self) -> str:
        return f"{self.name}Extras"

    @property
    def auxiliary_macro_names(self) -> tuple[str, ...]:
        """Names of generated macros other than the primary ``\\Name`` macro."""

        return (self.label_macro_name, self.raw_macro_name, self.extras_macro_name)

    def renamed(self, new_name: str, *, label_is_explicit: bool) -> "Entry":
        """Return a copy with a new macro name and, if appropriate, a new label."""

        return replace(
            self,
            name=new_name,
            label=self.label if label_is_explicit else new_name,
        )


@dataclass(frozen=True)
class ManagedBlock:
    name: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class AuxiliaryConflict:
    """A clash involving a generated helper such as ``\\NameName``."""

    name: str
    managed: ManagedBlock | None
    manual: tuple[DefinitionSpan, ...]

    @property
    def exists(self) -> bool:
        return self.managed is not None or bool(self.manual)


@dataclass(frozen=True)
class Conflict:
    text: str
    name: str
    managed: ManagedBlock | None
    manual: tuple[DefinitionSpan, ...]
    auxiliary: tuple[AuxiliaryConflict, ...] = ()
    blocked_by: tuple[str, ...] = ()

    @property
    def exists(self) -> bool:
        return bool(
            self.managed
            or self.manual
            or self.has_auxiliary_conflict
            or self.blocked_by
        )

    @property
    def has_auxiliary_conflict(self) -> bool:
        return any(auxiliary.exists for auxiliary in self.auxiliary)

    @property
    def can_overwrite(self) -> bool:
        """Whether overwrite_text() can produce a safe replacement."""

        if self.blocked_by:
            return False

        if self.has_auxiliary_conflict:
            return False

        if self.managed is not None:
            return not self.manual

        return (
            len(self.manual) == 1
            and _definition_is_standalone(self.text, self.manual[0])
        )


@dataclass(frozen=True)
class IdentifierRecord:
    name: str
    input_format: str
    identifier: str
    line: int


_BEGIN_RE = re.compile(
    r"^[ \t]*% === mol2chemfig-helper:(?P<name>[A-Za-z]+):BEGIN ===[ \t]*$"
)
_END_RE = re.compile(
    r"^[ \t]*% === mol2chemfig-helper:(?P<name>[A-Za-z]+):END ===[ \t]*$"
)
_IDENTIFIER_RE = re.compile(
    r"^[ \t]*% identifier: (?P<format>direct|file|pubchem) (?P<identifier>[^\r\n]*)$",
    re.MULTILINE,
)


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, max(0, min(index, len(text)))) + 1


def _label_lines(entry: Entry) -> list[str]:
    """Render the body of ``\\NameName``: the compound number label only.

    The label follows the document convention ``\\textbf{\\cmpd{...}}``.
    Formula and molecular weight deliberately live in ``\\NameExtras`` so a
    caller can choose whether to show them.
    """

    return [f"\\textbf{{\\cmpd{{{entry.label}}}}}"]


def _extras_label_lines(entry: Entry) -> list[str]:
    """Render the label used by ``\\NameExtras``.

    Returns an empty list when no formula or molecular weight was supplied, in
    which case ``\\NameExtras`` is identical to ``\\Name``.
    """

    annotations = [value for value in (entry.formula, entry.mw) if value]
    if not annotations:
        return []

    lines = ["\\shortstack[c]{%", f"  \\{entry.label_macro_name}\\\\"]
    for index, value in enumerate(annotations):
        suffix = "%" if index == len(annotations) - 1 else "\\\\"
        lines.append(f"  {value}{suffix}")
    lines.append("}")
    return lines


def _append_structure_macro(lines: list[str], macro_name: str, entry: Entry) -> None:
    chemfig_lines = entry.chemfig.splitlines()
    if not chemfig_lines:
        raise TexFileError("mol2chemfig returned an empty chemfig expression")

    lines.append(f"\\DeclareRobustCommand{{\\{macro_name}}}{{%")
    lines.extend(f"  {line}" for line in chemfig_lines)
    # The percent sign prevents the newline after \chemfig{...} from becoming
    # a space in the macro replacement text.
    lines[-1] += "%"
    lines.append("}")


def render_block(entry: Entry) -> str:
    """Render one complete, self-describing managed block.

    Four macros are generated:

    - ``\\NameName``: the compound number label only
    - ``\\NameStructure``: the bare structure
    - ``\\Name``: structure plus compound number
    - ``\\NameExtras``: structure plus compound number, formula and weight
    """

    options = (*entry.m2c_args, "-i", entry.input_format)
    lines = [
        f"% === mol2chemfig-helper:{entry.name}:BEGIN ===",
        "% Generated by mol2chemfig-helper; do not edit this block manually.",
        f"% identifier: {entry.input_format} {entry.identifier}",
        f"% mol2chemfig options: {shlex.join(options)}",
    ]
    if entry.formula:
        lines.append(f"% sum formula: {entry.formula}")
    if entry.mw:
        lines.append(f"% molecular weight: {entry.mw}")

    lines.append(f"\\newcommand{{\\{entry.label_macro_name}}}{{%")
    lines.extend(f"  {line}" for line in _label_lines(entry))
    lines[-1] += "%"
    lines.append("}")

    lines.append("")
    _append_structure_macro(lines, entry.raw_macro_name, entry)

    lines.append("")
    lines.append(f"\\DeclareRobustCommand{{\\{entry.name}}}{{%")
    lines.append(
        f"  \\chemname{{\\{entry.raw_macro_name}}}{{\\{entry.label_macro_name}}}%"
    )
    lines.append("}")

    lines.append("")
    lines.append(f"\\DeclareRobustCommand{{\\{entry.extras_macro_name}}}{{%")
    extras_lines = _extras_label_lines(entry)
    if extras_lines:
        lines.append(f"  \\chemname{{\\{entry.raw_macro_name}}}{{%")
        lines.extend(f"    {line}" for line in extras_lines)
        lines.append("  }%")
    else:
        lines.append(f"  \\{entry.name}%")
    lines.append("}")

    lines.append(f"% === mol2chemfig-helper:{entry.name}:END ===")
    return "\n".join(lines)


def parse_managed_blocks(text: str) -> dict[str, ManagedBlock]:
    """Parse all managed blocks and reject malformed or nested markers."""

    blocks: dict[str, ManagedBlock] = {}
    current_name: str | None = None
    current_start: int | None = None
    offset = 0

    for raw_line in text.splitlines(keepends=True):
        content = raw_line.rstrip("\r\n")
        begin = _BEGIN_RE.match(content)
        end = _END_RE.match(content)

        if begin:
            if current_name is not None:
                raise TexFileError(
                    f"nested managed block inside '{current_name}' at line "
                    f"{line_number(text, offset)}"
                )
            current_name = begin.group("name")
            current_start = offset
        elif end:
            if current_name is None or current_start is None:
                raise TexFileError(
                    f"END marker without BEGIN marker at line "
                    f"{line_number(text, offset)}"
                )
            end_name = end.group("name")
            if end_name != current_name:
                raise TexFileError(
                    f"END marker for '{end_name}' inside block '{current_name}' "
                    f"at line {line_number(text, offset)}"
                )
            if current_name in blocks:
                raise TexFileError(f"duplicate managed block for '{current_name}'")
            block_end = offset + len(content)
            blocks[current_name] = ManagedBlock(
                name=current_name,
                start=current_start,
                end=block_end,
                text=text[current_start:block_end],
            )
            current_name = None
            current_start = None

        offset += len(raw_line)

    if current_name is not None:
        raise TexFileError(f"managed block for '{current_name}' has no END marker")

    return blocks


def find_conflict(
    text: str,
    entry: Entry,
    blocks: dict[str, ManagedBlock],
) -> Conflict:
    """Find existing definitions that would collide with ``entry``."""

    exclude = tuple((block.start, block.end) for block in blocks.values())

    manual = find_definitions(text, entry.name, exclude=exclude)
    managed = blocks.get(entry.name)

    auxiliary = tuple(
        AuxiliaryConflict(
            name=name,
            managed=blocks.get(name),
            manual=find_definitions(text, name, exclude=exclude),
        )
        for name in entry.auxiliary_macro_names
    )

    # A generated block for another structure may already define one of this
    # entry's generated names (for example, a block for Ethanol defines
    # \EthanolName, \EthanolStructure and \EthanolExtras).  That is still a
    # LaTeX name clash.
    generated_names = (entry.name, *entry.auxiliary_macro_names)
    blocked_by: list[str] = []
    for block in blocks.values():
        if block.name == entry.name:
            continue
        if any(
            find_definitions(block.text, candidate) for candidate in generated_names
        ):
            blocked_by.append(block.name)

    return Conflict(
        text=text,
        name=entry.name,
        managed=managed,
        manual=manual,
        auxiliary=auxiliary,
        blocked_by=tuple(blocked_by),
    )


def identifier_records(
    text: str,
    blocks: dict[str, ManagedBlock],
) -> tuple[IdentifierRecord, ...]:
    """Read the source identifier metadata stored in each managed block."""

    records: list[IdentifierRecord] = []
    for block in blocks.values():
        match = _IDENTIFIER_RE.search(block.text)
        if match is None:
            continue
        records.append(
            IdentifierRecord(
                name=block.name,
                input_format=match.group("format"),
                identifier=match.group("identifier").strip(),
                line=line_number(text, block.start + match.start()),
            )
        )
    return tuple(records)


def duplicate_identifiers(
    records: tuple[IdentifierRecord, ...],
    entry: Entry,
) -> tuple[IdentifierRecord, ...]:
    """Return other blocks that store the exact same identifier."""

    return tuple(
        record
        for record in records
        if record.name != entry.name
        and record.input_format == entry.input_format
        and record.identifier == entry.identifier
    )


def append_block(text: str, block: str) -> str:
    """Append a block, keeping exactly one blank line before it."""

    result = text
    if result and not result.endswith("\n"):
        result += "\n"
    if result and not result.endswith("\n\n"):
        result += "\n"
    return result + block + "\n"


def replace_managed_block(
    text: str,
    block: ManagedBlock,
    new_block: str,
) -> str:
    return text[: block.start] + new_block + text[block.end :]


def _definition_is_standalone(text: str, definition: DefinitionSpan) -> bool:
    """Whether a definition occupies its own line(s) and can be replaced safely."""

    if not definition.replaceable:
        return False

    line_start = text.rfind("\n", 0, definition.start) + 1
    line_end = text.find("\n", definition.end)
    if line_end == -1:
        line_end = len(text)

    before = text[line_start : definition.start]
    after = text[definition.end : line_end]

    return not before.strip() and (
        not after.strip() or after.strip().startswith("%")
    )


def replace_definition(
    text: str,
    definition: DefinitionSpan,
    block: str,
) -> str | None:
    """Replace a standalone manual macro definition with a managed block.

    Returns None when the definition is not safely replaceable, for example
    because it shares a line with other LaTeX code.
    """

    if not _definition_is_standalone(text, definition):
        return None

    line_start = text.rfind("\n", 0, definition.start) + 1
    line_end = text.find("\n", definition.end)
    if line_end == -1:
        line_end = len(text)

    return text[:line_start] + block + text[line_end:]


def overwrite_text(text: str, conflict: Conflict, entry: Entry) -> str | None:
    """Return text with the conflicting definition replaced, or None if unsafe."""

    block = render_block(entry)

    if conflict.blocked_by:
        return None
    if conflict.has_auxiliary_conflict:
        return None

    if conflict.managed is not None:
        if conflict.manual:
            return None
        return replace_managed_block(text, conflict.managed, block)

    if len(conflict.manual) == 1 and conflict.manual[0].replaceable:
        return replace_definition(text, conflict.manual[0], block)

    return None
