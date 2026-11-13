from __future__ import annotations

import unittest

from mol2chemfig_helper.texscan import (
    TexScanError,
    find_definitions,
    find_matching_brace,
    mask_comments,
)


class BraceScannerTests(unittest.TestCase):
    def test_nested_and_escaped_braces(self) -> None:
        text = r"\chemfig{-[:30]N(=[:60]O)-[:330]\{x\}}"
        opening = text.index("{")
        self.assertEqual(find_matching_brace(text, opening), len(text) - 1)

    def test_comments_are_ignored(self) -> None:
        text = "\\chemfig{a% } comment\n{b}}"
        opening = text.index("{")
        self.assertEqual(find_matching_brace(text, opening), len(text) - 1)

    def test_unbalanced_raises(self) -> None:
        with self.assertRaises(TexScanError):
            find_matching_brace(r"\chemfig{a{b}", 8)


class CommentMaskTests(unittest.TestCase):
    def test_replaces_comments_but_keeps_offsets_and_newlines(self) -> None:
        text = "a % comment \\newcommand{\\X}{}\nb"
        masked = mask_comments(text)
        self.assertEqual(len(masked), len(text))
        self.assertNotIn("newcommand", masked)
        self.assertEqual(masked.count("\n"), text.count("\n"))
        self.assertTrue(masked.endswith("\nb"))

    def test_escaped_percent_is_not_a_comment(self) -> None:
        text = "a \\% still code % real comment"
        masked = mask_comments(text)
        self.assertIn(r"\% still code", masked)
        self.assertNotIn("real comment", masked)


class DefinitionFinderTests(unittest.TestCase):
    def test_finds_declare_robust_command_with_nested_body(self) -> None:
        text = (
            "before\n"
            "\\DeclareRobustCommand{\\Azid}{%\n"
            "  \\chemfig{-[:30]N=[:30]N}%\n"
            "}\n"
            "after\n"
        )
        [span] = find_definitions(text, "Azid")
        self.assertTrue(span.replaceable)
        self.assertEqual(span.command, "DeclareRobustCommand")
        self.assertEqual(text[span.start : span.end], text[text.index("\\Declare"):text.index("after") - 1])

    def test_finds_newcommand_and_def_forms(self) -> None:
        text = (
            "\\newcommand\\One[1][x]{\\textbf{#1}}\n"
            "\\newcommand{\\Two}{two}\n"
            "\\def\\Three#1{value #1}\n"
        )
        one = find_definitions(text, "One")[0]
        two = find_definitions(text, "Two")[0]
        three = find_definitions(text, "Three")[0]
        self.assertTrue(one.replaceable)
        self.assertTrue(two.replaceable)
        self.assertTrue(three.replaceable)
        self.assertIn("#1", text[one.start : one.end])
        self.assertIn("two", text[two.start : two.end])
        self.assertIn("#1", text[three.start : three.end])

    def test_finds_xparse_command_body(self) -> None:
        text = "\\DeclareDocumentCommand{\\Four}{m}{value #1}\n"
        [span] = find_definitions(text, "Four")
        self.assertTrue(span.replaceable)
        self.assertIn("value #1", text[span.start : span.end])

    def test_ignores_commented_definitions(self) -> None:
        text = "% \\newcommand{\\Azid}{commented}\n\\newcommand{\\Other}{x}\n"
        self.assertEqual(find_definitions(text, "Azid"), ())

    def test_exact_name_match(self) -> None:
        text = "\\newcommand{\\AzidName}{Azid}\n"
        self.assertEqual(find_definitions(text, "Azid"), ())
        self.assertEqual(len(find_definitions(text, "AzidName")), 1)

    def test_let_is_not_replaceable(self) -> None:
        text = "\\let\\Azid\\relax\n"
        [span] = find_definitions(text, "Azid")
        self.assertFalse(span.replaceable)
        self.assertIn("let", span.reason or "")

    def test_unbalanced_definition_is_not_replaceable(self) -> None:
        text = "\\newcommand{\\Azid}{unclosed\n"
        [span] = find_definitions(text, "Azid")
        self.assertFalse(span.replaceable)

    def test_nested_definition_is_not_replaceable(self) -> None:
        text = (
            "\\newcommand{\\Outer}{%\n"
            "  \\newcommand{\\Azid}{nested}\n"
            "}\n"
        )
        [span] = find_definitions(text, "Azid")
        self.assertFalse(span.replaceable)
        self.assertIn("nested", span.reason or "")

    def test_exclude_ranges(self) -> None:
        text = "\\newcommand{\\Azid}{x}\n"
        span = find_definitions(text, "Azid")[0]
        self.assertEqual(
            find_definitions(text, "Azid", exclude=((0, len(text)),)),
            (),
        )
        self.assertEqual(
            find_definitions(text, "Azid", exclude=((span.start, span.end),)),
            (),
        )


if __name__ == "__main__":
    unittest.main()
