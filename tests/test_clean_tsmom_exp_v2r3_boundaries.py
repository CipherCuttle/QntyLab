import ast
from pathlib import Path

ROOT=Path(__file__).parents[1]

def test_verifier_has_no_producer_or_dynamic_invocation_imports():
    source=(ROOT/'tools/verify_clean_tsmom_exp_v2r3_results.py').read_text()
    tree=ast.parse(source)
    banned=('qntylab.clean_tsmom_exp_v2r3','tools.run_clean_tsmom_exp_v2r3','qntylab.clean_tsmom_exp_v2r2')
    assert not any(any(x in ast.unparse(n) for x in banned) for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom)))
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in {'system','run'} for n in ast.walk(tree))
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {'eval','exec'} for n in ast.walk(tree))

def test_r3_contract_sidecars_exist_and_old_implementations_remain_unmodified():
    r3=ROOT/'experiments/clean_tsmom/v2r3'
    for name in ('real_execution_binding_r3','implementation_manifest_r3'):
        assert (r3/(name+'.json')).is_file() and (r3/(name+'.sha256')).is_file()
    assert 'SYNTHETIC_FIXTURE' in (ROOT/'qntylab/clean_tsmom_exp_v2r2.py').read_text()
