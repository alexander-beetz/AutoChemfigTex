from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from mol2chemfig_helper.texfile import Entry, render_block


class LatexCompileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("pdflatex") is None:
            raise unittest.SkipTest("pdflatex is not installed")
        if shutil.which("kpsewhich") is None:
            raise unittest.SkipTest("kpsewhich is not installed")
        chemfig = subprocess.run(
            ["kpsewhich", "chemfig.sty"],
            capture_output=True,
            text=True,
            check=False,
        )
        if chemfig.returncode != 0 or not chemfig.stdout.strip():
            raise unittest.SkipTest("chemfig.sty is not installed")

    def compile_document(
        self,
        entry: Entry,
        body: str,
        *,
        cmpd_preamble: str = "\\newcommand{\\cmpd}[1]{#1}\n",
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "structures.tex").write_text(
                render_block(entry) + "\n", encoding="utf-8"
            )
            (directory / "main.tex").write_text(
                "\\documentclass{article}\n"
                "\\usepackage{chemfig}\n"
                "\\usepackage{tikz}\n"
                + cmpd_preamble
                + "\\input{structures.tex}\n"
                "\\begin{document}\n"
                + body
                + "\\end{document}\n",
                encoding="utf-8",
            )

            process = subprocess.run(
                [
                    "pdflatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "main.tex",
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            output = (process.stdout or "")[-4000:] + (process.stderr or "")[-1000:]
            self.assertEqual(process.returncode, 0, output)
            self.assertTrue((directory / "main.pdf").exists())

    def test_named_block_compiles_in_scheme(self) -> None:
        entry = Entry(
            name="Azid",
            identifier="N=N",
            input_format="direct",
            label="Azid",
            chemfig=r"\chemfig{-N=N}",
            m2c_args=("-f", "-w"),
            formula="C6H6",
            mw="78.11",
        )
        self.compile_document(
            entry,
            "\\schemestart\n"
            "\\Azid + \\Azid \\arrow{->} \\Azid\n"
            "\\schemestop\n"
            "\\par\n"
            "\\Azid\n"
            "\\par\n"
            "\\AzidName\n"
            "\\par\n"
            "\\chemname{\\AzidStructure}{\\shortstack[c]{Custom\\\\C6H6}}\n",
        )

    def test_named_block_compiles_with_real_chemnum(self) -> None:
        chemnum = subprocess.run(
            ["kpsewhich", "chemnum.sty"],
            capture_output=True,
            text=True,
            check=False,
        )
        if chemnum.returncode != 0 or not chemnum.stdout.strip():
            self.skipTest("chemnum.sty is not installed")

        entry = Entry(
            name="Azid",
            identifier="N=N",
            input_format="direct",
            label="Azid",
            chemfig=r"\chemfig{-N=N}",
            m2c_args=("-f", "-w"),
            formula="C6H6",
            mw="78.11",
        )
        self.compile_document(
            entry,
            "\\schemestart\n"
            "\\Azid + \\Azid \\arrow{->} \\Azid\n"
            "\\schemestop\n",
            cmpd_preamble="\\usepackage{chemnum}\n",
        )

    def test_structure_only_block_compiles(self) -> None:
        entry = Entry(
            name="Azid",
            identifier="N=N",
            input_format="direct",
            label="Azid",
            chemfig=r"\chemfig{-N=N}",
            m2c_args=("-f", "-w"),
            structure_only=True,
        )
        self.compile_document(entry, "\\chemname{\\Azid}{\\AzidName}\n")


if __name__ == "__main__":
    unittest.main()
