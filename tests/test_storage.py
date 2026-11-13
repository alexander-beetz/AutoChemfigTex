from __future__ import annotations

import codecs
from pathlib import Path
import tempfile
import unittest

from mol2chemfig_helper.storage import (
    STARTER_TEXT,
    StorageError,
    read_document,
    write_document,
)


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdirectory = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdirectory.cleanup)
        self.directory = Path(self.tempdirectory.name)

    def test_missing_file_requires_create(self) -> None:
        with self.assertRaises(StorageError):
            read_document(self.directory / "structures.tex")

    def test_missing_file_can_be_created(self) -> None:
        document = read_document(self.directory / "structures.tex", create=True)
        self.assertEqual(document.text, STARTER_TEXT)
        self.assertFalse(document.existed)

    def test_round_trip_preserves_crlf_bom_and_mode(self) -> None:
        path = self.directory / "structures.tex"
        path.write_bytes(
            codecs.BOM_UTF8
            + b"% header\r\n\\newcommand{\\Old}{x}\r\n"
        )
        path.chmod(0o640)

        document = read_document(path)
        self.assertEqual(document.newline, "\r\n")
        self.assertTrue(document.has_bom)
        self.assertEqual(document.mode, 0o640)
        self.assertNotIn("\r", document.text)

        write_document(document, document.text + "\\newcommand{\\New}{y}\n")
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(codecs.BOM_UTF8))
        self.assertIn(b"\r\n\\newcommand{\\New}{y}\r\n", raw)
        self.assertNotIn(b"\n\n\\newcommand{\\New}", raw)
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)

    def test_backup_is_written(self) -> None:
        path = self.directory / "structures.tex"
        path.write_text("old\n", encoding="utf-8")
        document = read_document(path)
        write_document(document, "new\n", backup=True)
        self.assertEqual(path.read_text(encoding="utf-8"), "new\n")
        self.assertEqual(
            (self.directory / "structures.tex.bak").read_text(encoding="utf-8"),
            "old\n",
        )

    def test_invalid_utf8_is_rejected(self) -> None:
        path = self.directory / "structures.tex"
        path.write_bytes(b"\xff\xfe")
        with self.assertRaises(StorageError):
            read_document(path)


if __name__ == "__main__":
    unittest.main()
