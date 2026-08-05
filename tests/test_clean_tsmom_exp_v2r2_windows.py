from qntylab.clean_tsmom_exp_v2r2 import canonical_bytes

def test_canonical_serialization_is_deterministic():
    assert canonical_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}\n'
