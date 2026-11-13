"""File input/output with newline, BOM and permission preservation."""

from __future__ import annotations

import codecs
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
import tempfile


STARTER_TEXT = (
    "% structures.tex\n"
    "% Structure macros managed by mol2chemfig-helper.\n"
    "\n"
)


class StorageError(OSError):
    """Raised when structures.tex cannot be read or created safely."""


@dataclass(frozen=True)
class Document:
    path: Path
    text: str
    newline: str
    has_bom: bool
    mode: int | None
    existed: bool


def read_document(path: Path, *, create: bool = False) -> Document:
    """Read a UTF-8 LaTeX file and normalize its newlines to ``\\n``."""

    if not path.exists():
        if not create:
            raise StorageError(
                f"{path} does not exist; pass --create to create it"
            )
        return Document(
            path=path,
            text=STARTER_TEXT,
            newline="\n",
            has_bom=False,
            mode=None,
            existed=False,
        )

    raw = path.read_bytes()
    has_bom = raw.startswith(codecs.BOM_UTF8)
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StorageError(f"{path} is not valid UTF-8: {exc}") from exc

    newline = "\r\n" if "\r\n" in decoded else "\n"
    text = decoded.replace("\r\n", "\n").replace("\r", "\n")
    mode = stat.S_IMODE(path.stat().st_mode)

    return Document(
        path=path,
        text=text,
        newline=newline,
        has_bom=has_bom,
        mode=mode,
        existed=True,
    )


def write_document(
    document: Document,
    text: str,
    *,
    backup: bool = False,
) -> None:
    """Atomically replace the file, preserving encoding details and mode."""

    if text and not text.endswith("\n"):
        text += "\n"

    path = document.path
    if backup and document.existed:
        shutil.copy2(path, path.with_name(path.name + ".bak"))

    encoded = text.replace("\n", document.newline).encode("utf-8")
    if document.has_bom:
        encoded = codecs.BOM_UTF8 + encoded

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

        mode = document.mode if document.mode is not None else 0o644
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
