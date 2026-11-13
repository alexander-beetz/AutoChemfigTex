from __future__ import annotations

import subprocess
import unittest

from mol2chemfig_helper.converter import (
    ConversionError,
    build_command,
    convert,
    extract_chemfig,
)


class CommandTests(unittest.TestCase):
    def test_command_is_shell_free_and_uses_double_dash(self) -> None:
        self.assertEqual(
            build_command("mol2chemfig", ("-f", "-w"), "direct", "-weird"),
            ("mol2chemfig", "-f", "-w", "-i", "direct", "--", "-weird"),
        )


class ExtractTests(unittest.TestCase):
    def test_extracts_single_expression(self) -> None:
        self.assertEqual(
            extract_chemfig("\\chemfig{-[:30]N=[:30]N}\n"),
            "\\chemfig{-[:30]N=[:30]N}",
        )

    def test_extracts_multiline_expression_with_comments(self) -> None:
        stdout = (
            "\\chemfig{\n"
            "  -[:30]N% 1\n"
            "  =[:30]N% 2\n"
            "}\n"
            "% trailing comment\n"
        )
        result = extract_chemfig(stdout)
        self.assertTrue(result.startswith("\\chemfig{"))
        self.assertTrue(result.endswith("}"))
        self.assertIn("N% 2", result)

    def test_rejects_missing_wrapper(self) -> None:
        with self.assertRaises(ConversionError):
            extract_chemfig("-[:30]N=[:30]N\n")

    def test_rejects_trailing_code(self) -> None:
        with self.assertRaises(ConversionError):
            extract_chemfig("\\chemfig{-N=N}\nmore text\n")

    def test_rejects_unbalanced_output(self) -> None:
        with self.assertRaises(ConversionError):
            extract_chemfig("\\chemfig{-N=N\n")

    def test_rejects_empty_output(self) -> None:
        with self.assertRaises(ConversionError):
            extract_chemfig("   \n")


class ConvertTests(unittest.TestCase):
    def test_success(self) -> None:
        seen: dict[str, object] = {}

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen["command"] = command
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, 0, "\\chemfig{-N=N}\n", "")

        result = convert(
            "mol2chemfig",
            ("-f", "-w"),
            "direct",
            "N=N",
            runner=runner,  # type: ignore[arg-type]
        )
        self.assertEqual(result.chemfig, "\\chemfig{-N=N}")
        self.assertEqual(
            seen["command"],
            ["mol2chemfig", "-f", "-w", "-i", "direct", "--", "N=N"],
        )

    def test_nonzero_exit_reports_stderr(self) -> None:
        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 2, "", "bad molecule")

        with self.assertRaisesRegex(ConversionError, "bad molecule"):
            convert("mol2chemfig", (), "direct", "bad", runner=runner)  # type: ignore[arg-type]

    def test_missing_executable(self) -> None:
        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError(command[0])

        with self.assertRaisesRegex(ConversionError, "not found"):
            convert("missing", (), "direct", "CCO", runner=runner)  # type: ignore[arg-type]

    def test_timeout(self) -> None:
        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(command, 1)

        with self.assertRaisesRegex(ConversionError, "timed out"):
            convert("mol2chemfig", (), "direct", "CCO", timeout=1, runner=runner)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
