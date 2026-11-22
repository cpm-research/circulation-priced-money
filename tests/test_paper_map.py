"""The map in paper/README.md from each table and figure of the paper to the code that writes it, against the paper's
source and the two scripts: every table and figure of the source is in the map under its number and label, the file
the map names is the file the source reads, and the function the map names is in the script that writes it. Nothing
is run."""
import re
import unittest
from pathlib import Path

from scripts import paper_figures, paper_numbers

PAPER = Path(__file__).resolve().parents[1] / "paper"
FLOAT = re.compile(r"\\begin\{(table|figure|longtable)\*?\}(.*?)\\end\{\1\*?\}", re.S)
READS = re.compile(r"\\input\{(tables/[^}]+)\}|\\includegraphics(?:\[[^\]]*\])?\{(figures/[^}.]+)")
ROW = re.compile(r"^\| (Table|Figure) (\d+) \| `([^`]+)` \|([^|]*)\|([^|]*)\|([^|]*)\|$", re.M)
SCRIPT = {"tables": paper_numbers, "figures": paper_figures}


def source():
    """The paper's source with each section file in place of the line that reads it."""
    def expand(text):
        swap = lambda m: expand((PAPER / (m.group(1) + ".tex")).read_text(encoding="utf-8"))
        return re.sub(r"\\input\{(sections/[^}]+)\}", swap, text)
    return expand((PAPER / "cpm.tex").read_text(encoding="utf-8"))


def floats():
    """Each table and figure in the order of the source, which is the order LaTeX numbers them in: (kind, number,
    label) and the file it reads, None where it is typed in the source."""
    count, found = {"Table": 0, "Figure": 0}, {}
    for m in FLOAT.finditer(source()):
        kind = "Figure" if m.group(1) == "figure" else "Table"
        count[kind] += 1
        label = re.search(r"\\label\{([^}]+)\}", m.group(2)).group(1)
        read = READS.search(m.group(2))
        found[kind, count[kind], label] = None if read is None else (
            read.group(1) + ".tex" if read.group(1) else read.group(2) + ".pdf")
    return found


def mapped():
    """The rows of the map: (kind, number, label) and the file and function each names."""
    text = (PAPER / "README.md").read_text(encoding="utf-8")
    return {(kind, int(number), label): (file.strip(), function.strip())
            for kind, number, label, file, function, _ in ROW.findall(text)}


class PaperMapTest(unittest.TestCase):
    def test_every_table_and_figure_is_in_the_map_under_its_number(self):
        self.assertEqual(sorted(mapped()), sorted(floats()))

    def test_the_file_and_the_function_are_the_ones_the_paper_uses(self):
        rows = mapped()
        for key, read in floats().items():
            file, function = rows[key]
            if read is None:                       # typed in the source: the map names no file and no function
                self.assertNotIn("tables/", file, key)
                self.assertNotIn("figures/", file, key)
                self.assertEqual(function, "", key)
                continue
            self.assertEqual(file, f"`{read}`", key)
            self.assertTrue((PAPER / read).exists(), read)
            script = SCRIPT[read.split("/")[0]]
            self.assertTrue(callable(getattr(script, function.strip("`"), None)), (key, function))


if __name__ == "__main__":
    unittest.main()
