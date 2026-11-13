"""Command-line workflow for adding structures to structures.tex."""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import sys

from . import __version__
from .converter import ConversionError, convert
from .storage import StorageError, read_document, write_document
from .texfile import (
    Conflict,
    Entry,
    TexFileError,
    append_block,
    duplicate_identifiers,
    find_conflict,
    identifier_records,
    line_number,
    overwrite_text,
    parse_managed_blocks,
    render_block,
)
from .validation import (
    ValidationError,
    normalize_name,
    validate_identifier,
    validate_label,
    validate_m2c_arg,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="m2c-structure",
        description=(
            "Convert a chemical structure with mol2chemfig and add it to "
            "structures.tex as a named LaTeX macro."
        ),
    )
    parser.add_argument(
        "identifier",
        help="SMILES, InChI, molfile path or PubChem CID (see --format)",
    )
    parser.add_argument(
        "name",
        help="LaTeX macro name, for example Azid or ParaAlkin",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        help="directory containing structures.tex (default: current directory)",
    )
    parser.add_argument(
        "-C",
        "--dir",
        dest="dir_option",
        help="directory containing structures.tex; alternative to the positional argument",
    )
    parser.add_argument(
        "--file",
        default="structures.tex",
        help="filename inside the target directory (default: structures.tex)",
    )
    parser.add_argument(
        "--format",
        choices=("direct", "file", "pubchem"),
        default="direct",
        help="how mol2chemfig should interpret the identifier (default: direct)",
    )
    parser.add_argument(
        "--label",
        help="display label stored in \\NameName (default: the macro name)",
    )
    parser.add_argument(
        "--no-name-macro",
        action="store_true",
        help="do not generate the auxiliary \\NameName display-label macro",
    )
    parser.add_argument(
        "--mol2chemfig",
        default="mol2chemfig",
        metavar="PATH",
        help="mol2chemfig executable (default: mol2chemfig from PATH)",
    )
    parser.add_argument(
        "--m2c-arg",
        action="append",
        default=None,
        metavar="ARG",
        help="extra mol2chemfig option; may be repeated (for example --m2c-arg=-z)",
    )
    parser.add_argument(
        "--terse",
        action="store_true",
        help="add mol2chemfig's -z (terse output) option",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing definition without asking",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show the proposed diff but do not write the file",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="copy structures.tex to structures.tex.bak before writing",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="create structures.tex if it does not exist",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        metavar="SECONDS",
        help="mol2chemfig timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="do not print the diff",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except (ValidationError, StorageError, TexFileError, ConversionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\naborted", file=sys.stderr)
        return 130


def _resolve_directory(args: argparse.Namespace) -> Path:
    if args.directory and args.dir_option:
        raise ValidationError(
            "pass the target directory either positionally or with --dir, not both"
        )

    directory = Path(args.dir_option or args.directory or ".").expanduser()
    if not directory.exists():
        raise ValidationError(f"target directory does not exist: {directory}")
    if not directory.is_dir():
        raise ValidationError(f"target is not a directory: {directory}")
    return directory.resolve()


def _resolve_file(directory: Path, filename: str) -> Path:
    candidate = Path(filename)
    if (
        candidate.is_absolute()
        or len(candidate.parts) != 1
        or candidate.name in {"", ".", ".."}
    ):
        raise ValidationError(
            "--file must be a plain filename inside the target directory"
        )

    path = (directory / candidate.name).resolve()
    if path.parent != directory:
        raise ValidationError(
            f"resolved structures file is outside the target directory: {path}"
        )
    if path.exists() and path.is_dir():
        raise ValidationError(f"target file is a directory: {path}")
    return path


def _run(args: argparse.Namespace) -> int:
    name = normalize_name(args.name)
    label_is_explicit = args.label is not None
    label = validate_label(args.label if label_is_explicit else name)
    identifier = validate_identifier(args.identifier)

    if args.timeout <= 0:
        raise ValidationError("--timeout must be greater than zero")

    extra_args = [validate_m2c_arg(value) for value in (args.m2c_arg or [])]
    if args.terse:
        extra_args.append("-z")

    directory = _resolve_directory(args)
    path = _resolve_file(directory, args.file)
    document = read_document(path, create=args.create)

    conversion = convert(
        executable=args.mol2chemfig,
        options=("-f", "-w", *extra_args),
        input_format=args.format,
        identifier=identifier,
        timeout=args.timeout,
    )

    entry = Entry(
        name=name,
        identifier=identifier,
        input_format=args.format,
        label=label,
        chemfig=conversion.chemfig,
        m2c_args=("-f", "-w", *extra_args),
        generate_name_macro=not args.no_name_macro,
    )

    text = document.text
    interactive = sys.stdin.isatty()

    while True:
        blocks = parse_managed_blocks(text)
        conflict = find_conflict(text, entry, blocks)
        records = identifier_records(text, blocks)

        for record in duplicate_identifiers(records, entry):
            print(
                f"warning: this identifier is already stored as \\{record.name} "
                f"(line {record.line}); continuing with \\{entry.name}",
                file=sys.stderr,
            )

        rendered = render_block(entry)

        if not conflict.exists:
            proposed = append_block(text, rendered)
            _show_diff(text, proposed, path, quiet=args.quiet)
            if args.dry_run:
                print("dry run: no changes written", file=sys.stderr)
                return 0
            write_document(document, proposed, backup=args.backup)
            print(f"added \\{entry.name} to {path}")
            return 0

        if (
            conflict.managed is not None
            and conflict.managed.text == rendered
            and not conflict.manual
            and conflict.aux_managed is None
            and not conflict.aux_manual
        ):
            print(f"\\{entry.name} is already up to date in {path}")
            return 0

        candidate = overwrite_text(text, conflict, entry)
        _describe_conflict(text, conflict, path)
        if candidate is not None:
            _show_diff(text, candidate, path, quiet=args.quiet)
        elif not args.quiet:
            print("The existing definition cannot be replaced automatically.")
            print("New managed block:")
            print(rendered)

        if args.dry_run:
            print("dry run: no changes written", file=sys.stderr)
            return 0 if candidate is not None else 1

        if args.overwrite:
            if candidate is None:
                raise ValidationError(
                    f"cannot overwrite \\{entry.name} automatically; "
                    "choose another name"
                )
            write_document(document, candidate, backup=args.backup)
            print(f"updated \\{entry.name} in {path}")
            return 0

        if not interactive:
            raise ValidationError(
                f"\\{entry.name} already exists; rerun interactively, "
                "use --overwrite, or choose another name"
            )

        choice = _ask_conflict(can_overwrite=candidate is not None)
        if choice == "abort":
            print("aborted", file=sys.stderr)
            return 0
        if choice == "overwrite":
            if candidate is None:
                continue
            write_document(document, candidate, backup=args.backup)
            print(f"updated \\{entry.name} in {path}")
            return 0

        new_name = _ask_new_name()
        if new_name is None:
            print("aborted", file=sys.stderr)
            return 0
        entry = entry.renamed(new_name, label_is_explicit=label_is_explicit)
        # text and document are deliberately unchanged; re-analyse with the
        # new name before deciding whether to append or prompt again.


def _describe_conflict(text: str, conflict: Conflict, path: Path) -> None:
    if conflict.managed is not None:
        print(
            f"\\{conflict.name} already has a managed block at lines "
            f"{line_number(text, conflict.managed.start)}-"
            f"{line_number(text, conflict.managed.end)} in {path}.",
            file=sys.stderr,
        )
    for definition in conflict.manual:
        print(
            f"\\{conflict.name} has a manual definition at line "
            f"{line_number(text, definition.start)}.",
            file=sys.stderr,
        )
    if conflict.aux_managed is not None:
        print(
            f"the label macro \\{conflict.name}Name has its own managed block.",
            file=sys.stderr,
        )
    for definition in conflict.aux_manual:
        print(
            f"the label macro \\{conflict.name}Name has a manual definition "
            f"at line {line_number(text, definition.start)}.",
            file=sys.stderr,
        )
    for block_name in conflict.blocked_by:
        print(
            f"the managed block for \\{block_name} already defines "
            f"\\{conflict.name} or its label macro.",
            file=sys.stderr,
        )


def _ask_conflict(*, can_overwrite: bool) -> str:
    prompt = (
        "  [o] Overwrite existing definition\n"
        "  [n] Enter a new name\n"
        "  [a] Abort\n"
        if can_overwrite
        else "  [n] Enter a new name\n  [a] Abort\n"
    )
    print(prompt, end="", file=sys.stderr)

    while True:
        try:
            answer = input("Choice: ").strip().lower()
        except EOFError as exc:
            raise KeyboardInterrupt from exc

        if can_overwrite and answer in {"o", "overwrite"}:
            return "overwrite"
        if answer in {"n", "new"}:
            return "new"
        if answer in {"a", "abort", ""}:
            return "abort"
        print("Please enter one of the listed choices.", file=sys.stderr)


def _ask_new_name() -> str | None:
    while True:
        try:
            raw = input("New structure name (empty to abort): ").strip()
        except EOFError as exc:
            raise KeyboardInterrupt from exc

        if not raw:
            return None
        try:
            return normalize_name(raw)
        except ValidationError as exc:
            print(f"error: {exc}", file=sys.stderr)


def _show_diff(
    old_text: str,
    new_text: str,
    path: Path,
    *,
    quiet: bool,
) -> None:
    if quiet:
        return

    diff = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"{path} (current)",
            tofile=f"{path} (proposed)",
            lineterm="",
        )
    )
    if diff:
        print("\n".join(diff))
    else:
        print("No textual changes.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
