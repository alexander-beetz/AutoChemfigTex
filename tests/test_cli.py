from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mol2chemfig_helper.cli import main


FAKE_MOL2CHEMFIG = """#!/bin/sh
last=
for arg in "$@"; do last=$arg; done
printf '\\\\chemfig{%s}\\n' "$last"
"""


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdirectory = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdirectory.cleanup)
        self.directory = Path(self.tempdirectory.name)
        self.script = self.directory / "fake-mol2chemfig"
        self.script.write_text(FAKE_MOL2CHEMFIG, encoding="utf-8")
        self.script.chmod(0o755)
        self.structures = self.directory / "structures.tex"
        self.structures.write_text(
            "% hand-written header\n\n\\newcommand{\\Existing}{x}\n",
            encoding="utf-8",
        )

    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def base_args(self, identifier: str, name: str) -> list[str]:
        return [
            identifier,
            name,
            str(self.directory),
            "--mol2chemfig",
            str(self.script),
        ]

    def test_appends_new_structure(self) -> None:
        code, stdout, stderr = self.run_cli(*self.base_args("CCO", "Ethanol"))
        self.assertEqual(code, 0, stderr)
        text = self.structures.read_text(encoding="utf-8")
        self.assertIn("% === mol2chemfig-helper:Ethanol:BEGIN ===", text)
        self.assertIn("% style: named", text)
        self.assertIn("\\newcommand{\\EthanolName}{%", text)
        self.assertIn("  \\textbf{\\cmpd{Ethanol}}%", text)
        self.assertIn("\\DeclareRobustCommand{\\EthanolStructure}{%", text)
        self.assertIn("  \\chemfig{CCO}%", text)
        self.assertIn("\\DeclareRobustCommand{\\Ethanol}{%", text)
        self.assertIn("  \\chemname{\\EthanolStructure}{\\EthanolName}%", text)
        self.assertIn("+\\DeclareRobustCommand", stdout)
        self.assertIn("added \\Ethanol", stdout)

    def test_creates_file_when_requested(self) -> None:
        target = self.directory / "new-structures.tex"
        code, _, stderr = self.run_cli(
            "CCO",
            "Ethanol",
            str(self.directory),
            "--file",
            target.name,
            "--create",
            "--mol2chemfig",
            str(self.script),
        )
        self.assertEqual(code, 0, stderr)
        text = target.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("% structures.tex"))
        self.assertIn("% === mol2chemfig-helper:Ethanol:BEGIN ===", text)

    def test_missing_file_without_create_fails(self) -> None:
        target = self.directory / "missing.tex"
        code, _, stderr = self.run_cli(
            "CCO",
            "Ethanol",
            str(self.directory),
            "--file",
            target.name,
            "--mol2chemfig",
            str(self.script),
        )
        self.assertEqual(code, 1)
        self.assertIn("does not exist", stderr)
        self.assertFalse(target.exists())

    def test_invalid_name_fails_before_running_converter(self) -> None:
        code, _, stderr = self.run_cli(*self.base_args("CCO", "2Invalid"))
        self.assertEqual(code, 1)
        self.assertIn("ASCII letters", stderr)

    def test_duplicate_name_without_overwrite_fails_noninteractively(self) -> None:
        self.assertEqual(self.run_cli(*self.base_args("CCO", "Ethanol"))[0], 0)
        before = self.structures.read_text(encoding="utf-8")
        code, _, stderr = self.run_cli(*self.base_args("CCN", "Ethanol"))
        self.assertEqual(code, 1)
        self.assertIn("already exists", stderr)
        self.assertEqual(self.structures.read_text(encoding="utf-8"), before)

    def test_overwrite_replaces_managed_block(self) -> None:
        self.assertEqual(self.run_cli(*self.base_args("CCO", "Ethanol"))[0], 0)
        code, stdout, stderr = self.run_cli(
            *self.base_args("CCN", "Ethanol"), "--overwrite"
        )
        self.assertEqual(code, 0, stderr)
        text = self.structures.read_text(encoding="utf-8")
        self.assertEqual(text.count("mol2chemfig-helper:Ethanol:BEGIN"), 1)
        self.assertIn("% identifier: direct CCN", text)
        self.assertNotIn("identifier: direct CCO", text)
        self.assertIn("updated \\Ethanol", stdout)

    def test_identical_managed_block_is_left_alone(self) -> None:
        self.assertEqual(self.run_cli(*self.base_args("CCO", "Ethanol"))[0], 0)
        before = self.structures.read_text(encoding="utf-8")
        code, stdout, stderr = self.run_cli(
            *self.base_args("CCO", "Ethanol"), "--overwrite"
        )
        self.assertEqual(code, 0, stderr)
        self.assertIn("already up to date", stdout)
        self.assertEqual(self.structures.read_text(encoding="utf-8"), before)

    def test_overwrite_manual_definition(self) -> None:
        self.structures.write_text(
            "before\n\\DeclareRobustCommand{\\Azid}{\\chemfig{old}}\nafter\n",
            encoding="utf-8",
        )
        code, _, stderr = self.run_cli(
            *self.base_args("N=N", "Azid"), "--overwrite"
        )
        self.assertEqual(code, 0, stderr)
        text = self.structures.read_text(encoding="utf-8")
        self.assertIn("before\n", text)
        self.assertIn("% === mol2chemfig-helper:Azid:BEGIN ===", text)
        self.assertIn("after\n", text)
        self.assertNotIn("chemfig{old}", text)

    def test_non_replaceable_definition_requires_new_name(self) -> None:
        self.structures.write_text("\\let\\Azid\\relax\n", encoding="utf-8")
        code, _, stderr = self.run_cli(
            *self.base_args("N=N", "Azid"), "--overwrite"
        )
        self.assertEqual(code, 1)
        self.assertIn("cannot overwrite", stderr)

    def test_interactive_new_name_appends_second_block(self) -> None:
        self.assertEqual(self.run_cli(*self.base_args("CCO", "Ethanol"))[0], 0)
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
            "builtins.input", side_effect=["n", "EthanolTwo"]
        ):
            code, _, stderr = self.run_cli(*self.base_args("CCN", "Ethanol"))
        self.assertEqual(code, 0, stderr)
        text = self.structures.read_text(encoding="utf-8")
        self.assertIn("% === mol2chemfig-helper:Ethanol:BEGIN ===", text)
        self.assertIn("% === mol2chemfig-helper:EthanolTwo:BEGIN ===", text)
        self.assertIn("\\textbf{\\cmpd{EthanolTwo}}", text)

    def test_interactive_abort_leaves_file_unchanged(self) -> None:
        self.assertEqual(self.run_cli(*self.base_args("CCO", "Ethanol"))[0], 0)
        before = self.structures.read_text(encoding="utf-8")
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
            "builtins.input", side_effect=["a"]
        ):
            code, _, stderr = self.run_cli(*self.base_args("CCN", "Ethanol"))
        self.assertEqual(code, 0)
        self.assertIn("aborted", stderr)
        self.assertEqual(self.structures.read_text(encoding="utf-8"), before)

    def test_dry_run_does_not_write(self) -> None:
        before = self.structures.read_text(encoding="utf-8")
        code, stdout, stderr = self.run_cli(
            *self.base_args("CCO", "Ethanol"), "--dry-run"
        )
        self.assertEqual(code, 0, stderr)
        self.assertIn("dry run", stderr)
        self.assertIn("+\\DeclareRobustCommand", stdout)
        self.assertEqual(self.structures.read_text(encoding="utf-8"), before)

    def test_quiet_suppresses_diff(self) -> None:
        code, stdout, stderr = self.run_cli(
            *self.base_args("CCO", "Ethanol"), "--quiet"
        )
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("+\\DeclareRobustCommand", stdout)
        self.assertIn("added \\Ethanol", stdout)

    def test_custom_compound_label_key(self) -> None:
        code, _, stderr = self.run_cli(
            *self.base_args("CCO", "Ethanol"),
            "--label",
            "ethyl-alcohol",
        )
        self.assertEqual(code, 0, stderr)
        text = self.structures.read_text(encoding="utf-8")
        self.assertIn(r"\textbf{\cmpd{ethyl-alcohol}}", text)

    def test_structure_only_output(self) -> None:
        code, _, stderr = self.run_cli(
            *self.base_args("CCN", "Ethylamine"), "--structure-only"
        )
        self.assertEqual(code, 0, stderr)
        text = self.structures.read_text(encoding="utf-8")
        self.assertIn("% style: structure-only", text)
        self.assertIn("\\DeclareRobustCommand{\\Ethylamine}{%", text)
        self.assertNotIn("EthylamineStructure", text)
        self.assertIn("\\newcommand{\\EthylamineName}{%", text)
        self.assertIn("\\textbf{\\cmpd{Ethylamine}}", text)

    def test_formula_and_molecular_weight_are_in_name_macro(self) -> None:
        code, _, stderr = self.run_cli(
            *self.base_args("CCO", "Ethanol"),
            "--formula",
            "C6H6",
            "--mw",
            "78.11",
        )
        self.assertEqual(code, 0, stderr)
        text = self.structures.read_text(encoding="utf-8")
        self.assertIn("% sum formula: C6H6", text)
        self.assertIn("% molecular weight: 78.11", text)
        self.assertIn("  \\shortstack[c]{%", text)
        self.assertIn("    \\textbf{\\cmpd{Ethanol}}\\\\", text)
        self.assertIn("    C6H6\\\\", text)
        self.assertIn("    78.11%", text)

    def test_invalid_formula_is_rejected(self) -> None:
        code, _, stderr = self.run_cli(
            *self.base_args("CCO", "Ethanol"), "--formula", "100% pure"
        )
        self.assertEqual(code, 1)
        self.assertIn("sum formula", stderr)
        self.assertIn("comment character", stderr)

    def test_invalid_label_key_is_rejected(self) -> None:
        code, _, stderr = self.run_cli(
            *self.base_args("CCO", "Ethanol"), "--label", "bad label"
        )
        self.assertEqual(code, 1)
        self.assertIn("compound label", stderr)

    def test_duplicate_identifier_warns_but_appends(self) -> None:
        self.assertEqual(self.run_cli(*self.base_args("CCO", "Ethanol"))[0], 0)
        code, _, stderr = self.run_cli(*self.base_args("CCO", "EthanolTwo"))
        self.assertEqual(code, 0, stderr)
        self.assertIn("already stored as \\Ethanol", stderr)
        self.assertIn("EthanolTwo", self.structures.read_text(encoding="utf-8"))

    def test_preserves_crlf(self) -> None:
        self.structures.write_bytes(b"% header\r\n\r\n")
        code, _, stderr = self.run_cli(*self.base_args("CCO", "Ethanol"))
        self.assertEqual(code, 0, stderr)
        raw = self.structures.read_bytes()
        self.assertIn(b"\r\n", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))

    def test_backup_is_created(self) -> None:
        before = self.structures.read_text(encoding="utf-8")
        code, _, stderr = self.run_cli(
            *self.base_args("CCO", "Ethanol"), "--backup"
        )
        self.assertEqual(code, 0, stderr)
        backup = self.directory / "structures.tex.bak"
        self.assertEqual(backup.read_text(encoding="utf-8"), before)

    def test_converter_failure_is_reported(self) -> None:
        code, _, stderr = self.run_cli(
            "CCO",
            "Ethanol",
            str(self.directory),
            "--mol2chemfig",
            str(self.directory / "does-not-exist"),
        )
        self.assertEqual(code, 1)
        self.assertIn("not found", stderr)

    def test_rejects_path_outside_target_directory(self) -> None:
        code, _, stderr = self.run_cli(
            "CCO",
            "Ethanol",
            str(self.directory),
            "--file",
            "../outside.tex",
            "--mol2chemfig",
            str(self.script),
        )
        self.assertEqual(code, 1)
        self.assertIn("plain filename", stderr)


if __name__ == "__main__":
    unittest.main()
