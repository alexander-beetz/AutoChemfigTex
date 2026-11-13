"""Run mol2chemfig and validate its output."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Callable, Sequence

from .texscan import TexScanError, find_matching_brace


class ConversionError(RuntimeError):
    """Raised when mol2chemfig cannot produce a usable \\chemfig expression."""


@dataclass(frozen=True)
class ConversionResult:
    chemfig: str
    command: tuple[str, ...]
    stderr: str


Runner = Callable[..., subprocess.CompletedProcess]


def build_command(
    executable: str,
    options: Sequence[str],
    input_format: str,
    identifier: str,
) -> tuple[str, ...]:
    """Build a shell-free command.

    ``--`` prevents an identifier beginning with ``-`` from being interpreted
    as another mol2chemfig option.
    """

    return (
        executable,
        *options,
        "-i",
        input_format,
        "--",
        identifier,
    )


def extract_chemfig(stdout: str) -> str:
    """Extract one ``\\chemfig{...}`` expression from mol2chemfig's output."""

    text = stdout.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ConversionError("mol2chemfig produced no output")

    command = "\\chemfig"
    if not text.startswith(command):
        raise ConversionError(
            "mol2chemfig output does not start with \\chemfig{...}; "
            "use the -w option and do not use -l"
        )

    brace = text.find("{", len(command))
    if brace == -1:
        raise ConversionError("mol2chemfig output has no opening brace after \\chemfig")
    if text[len(command) : brace].strip():
        raise ConversionError("unexpected text between \\chemfig and its opening brace")

    try:
        closing = find_matching_brace(text, brace)
    except TexScanError as exc:
        raise ConversionError(f"cannot parse mol2chemfig output: {exc}") from exc

    trailing = text[closing + 1 :]
    for line in trailing.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("%"):
            raise ConversionError("unexpected text after the \\chemfig{...} expression")

    return text[: closing + 1]


def convert(
    executable: str,
    options: Sequence[str],
    input_format: str,
    identifier: str,
    *,
    timeout: float = 120.0,
    runner: Runner | None = None,
) -> ConversionResult:
    """Run mol2chemfig and return its validated chemfig expression."""

    command = build_command(executable, options, input_format, identifier)
    run = runner or subprocess.run

    try:
        process = run(
            list(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ConversionError(
            f"mol2chemfig executable not found: {executable!r}. "
            "Install mol2chemfigPy3 or pass --mol2chemfig /path/to/mol2chemfig"
        ) from exc
    except PermissionError as exc:
        raise ConversionError(
            f"cannot execute mol2chemfig: {executable!r} is not executable"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(
            f"mol2chemfig timed out after {timeout:g} seconds"
        ) from exc
    except OSError as exc:
        raise ConversionError(f"cannot run mol2chemfig: {exc}") from exc

    if process.returncode != 0:
        details = (process.stderr or process.stdout or "").strip()
        if len(details) > 4000:
            details = details[-4000:]
        message = f"mol2chemfig failed with exit code {process.returncode}"
        if details:
            message += f":\n{details}"
        raise ConversionError(message)

    return ConversionResult(
        chemfig=extract_chemfig(process.stdout or ""),
        command=command,
        stderr=process.stderr or "",
    )
