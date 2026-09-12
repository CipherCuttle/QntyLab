import ast
from pathlib import Path
def test_independent_verifier_has_no_producer_import_or_invocation():
    tree=ast.parse((Path(__file__).parents[1]/"tools/verify_clean_tsmom_exp_v2_results.py").read_text())
    names=[n.module or "" for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert all("clean_tsmom_exp_v2" not in n for n in names)
