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
        chemfig = subprocess.run(
            ["kpsewhich", "chemfig.sty"],
            capture_output=True,
            text=True,
            check=False,
        )
        if chemfig.returncode != 0 or not chemfig.stdout.strip():
            raise unittest.SkipTest("chemfig.sty is not installed")

    def test_generated_block_compiles_with_chemname(self) -> None:
        entry = Entry(
            name="Azid",
            identifier="N=N",
            input_format="direct",
            label="Azid",
            chemfig=r"\chemfig{-N=N}",
            m2c_args=("-f", "-w"),
        )

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "structures.tex").write_text(
                render_block(entry) + "\n", encoding="utf-8"
            )
            (directory / "main.tex").write_text(
                "\\documentclass{article}\n"
                "\\usepackage{chemfig}\n"
                "\\input{structures.tex}\n"
                "\\begin{document}\n"
                "\\schemestart\n"
                "\\chemname{\\Azid}{\\AzidName}\n"
                "\\schemestop\n"
                "\\end{document}\n",
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


if __name__ == "__main__":
    unittest.main()
