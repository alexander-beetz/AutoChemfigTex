from __future__ import annotations

import unittest

from mol2chemfig_helper.validation import (
    ValidationError,
    normalize_name,
    validate_identifier,
    validate_label,
    validate_m2c_arg,
)


class NameValidationTests(unittest.TestCase):
    def test_accepts_control_word_names(self) -> None:
        self.assertEqual(normalize_name("Azid"), "Azid")
        self.assertEqual(normalize_name("\\ParaAlkin"), "ParaAlkin")
        self.assertEqual(normalize_name("  Product  "), "Product")

    def test_rejects_invalid_names(self) -> None:
        for value in ("", " ", "2Azid", "Az-id", "Az id", "Az_id", "Azid@home"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalize_name(value)

    def test_rejects_reserved_tex_names(self) -> None:
        for value in ("begin", "end", "newcommand", "relax"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalize_name(value)


class LabelValidationTests(unittest.TestCase):
    def test_accepts_plain_and_simple_tex_labels(self) -> None:
        self.assertEqual(validate_label("Azid"), "Azid")
        self.assertEqual(
            validate_label(r"p-\textit{nitrophenyl} azide"),
            r"p-\textit{nitrophenyl} azide",
        )
        self.assertEqual(validate_label(r"100\% pure"), r"100\% pure")

    def test_rejects_unescaped_special_characters(self) -> None:
        for value in ("100% pure", "C#N", "a\nb", "{unbalanced", "unbalanced}"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_label(value)

    def test_rejects_control_characters(self) -> None:
        with self.assertRaises(ValidationError):
            validate_label("bad\x00label")

    def test_rejects_trailing_unescaped_backslash(self) -> None:
        with self.assertRaises(ValidationError):
            validate_label("bad\\")
        self.assertEqual(validate_label("line break\\\\"), "line break\\\\")


class IdentifierValidationTests(unittest.TestCase):
    def test_accepts_normal_identifiers(self) -> None:
        self.assertEqual(validate_identifier("  C1=CC=CC=C1  "), "C1=CC=CC=C1")
        self.assertEqual(validate_identifier("996"), "996")
        self.assertEqual(validate_identifier("file with spaces.mol"), "file with spaces.mol")

    def test_rejects_multiline_and_empty_identifiers(self) -> None:
        for value in ("", "  ", "CCO\nCCO", "CCO\r", "CCO\x00"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_identifier(value)

    def test_m2c_argument_validation(self) -> None:
        self.assertEqual(validate_m2c_arg("-z"), "-z")
        with self.assertRaises(ValidationError):
            validate_m2c_arg("")
        with self.assertRaises(ValidationError):
            validate_m2c_arg("-z\n-x")


if __name__ == "__main__":
    unittest.main()
