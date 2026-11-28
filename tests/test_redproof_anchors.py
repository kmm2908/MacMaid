"""A mutant whose anchor no longer matches never runs, so its rule goes unproven."""
import re
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUTANTS = runpy.run_path(str(ROOT / "tools" / "redproof_dev_junk.py"))["MUTANTS"]


def test_every_mutation_anchor_matches_the_current_code_exactly_once():
    stale = [label for label, rel, old, _, _ in MUTANTS if (ROOT / rel).read_text().count(old) != 1]
    assert stale == []


def test_every_test_a_mutant_names_still_exists():
    defined = {name for path in (ROOT / "tests").glob("test_*.py")
               for name in re.findall(r"^def (test_\w+)", path.read_text(), re.MULTILINE)}
    missing = {name for *_, expected in MUTANTS for name in expected
               if name.split("[")[0] not in defined}
    assert missing == set()
