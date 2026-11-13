from __future__ import annotations

import unittest

from mol2chemfig_helper.validation import (
    ValidationError,
    normalize_name,
    validate_annotation,
    validate_cmpd_key,
    validate_identifier,
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


class CmpdKeyValidationTests(unittest.TestCase):
    def test_accepts_plain_keys(self) -> None:
        for value in ("Azid", "azid", "compound-1", "cmpd.1:a", "1"):
            with self.subTest(value=value):
                self.assertEqual(validate_cmpd_key(value), value)

    def test_rejects_unsafe_or_empty_keys(self) -> None:
        for value in ("", " ", "bad label", "bad{label}", "bad\\label", "bad%label"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_cmpd_key(value)


class AnnotationValidationTests(unittest.TestCase):
    def test_accepts_formula_and_weight_text(self) -> None:
        self.assertEqual(validate_annotation("C6H6", "sum formula"), "C6H6")
        self.assertEqual(
            validate_annotation(r"\ce{C6H6}", "sum formula"), r"\ce{C6H6}"
        )
        self.assertEqual(validate_annotation("78.11", "molecular weight"), "78.11")
        self.assertEqual(validate_annotation(r"100\% pure", "sum formula"), r"100\% pure")

    def test_rejects_unsafe_or_empty_annotations(self) -> None:
        for value in ("", " ", "a\nb", "100% pure", "C#N", "{unbalanced", "unbalanced}"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_annotation(value, "sum formula")

    def test_rejects_control_characters(self) -> None:
        with self.assertRaises(ValidationError):
            validate_annotation("bad\x00label", "molecular weight")

    def test_rejects_trailing_unescaped_backslash(self) -> None:
        with self.assertRaises(ValidationError):
            validate_annotation("bad\\", "sum formula")
        self.assertEqual(
            validate_annotation("line break\\\\", "sum formula"), "line break\\\\"
        )


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
