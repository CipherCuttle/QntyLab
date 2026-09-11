from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"expected one patch anchor in {path}, got {text.count(old)}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_execution() -> None:
    path = Path("qntylab/h003_edge_falsification_v0_execution.py")
    old = '''    plan_dir = workspace / "plan"\n    if not plan_dir.exists():\n        h003.write_plan(plan_dir)\n    plan = h003.compile_plan()\n    runs = workspace / "runs"\n'''
    new = '''    plan_dir = workspace / "plan"\n    if not plan_dir.exists():\n        h003.write_plan(plan_dir)\n    plan = h003.compile_plan()\n    ledger_root = research_root or strategy_test.RESEARCH_ROOT\n    runs = workspace / "runs"\n'''
    replace_once(path, old, new)


def patch_test() -> None:
    path = Path("tests/test_h003_edge_falsification_v0_execution.py")
    text = path.read_text(encoding="utf-8")
    marker = "def test_execute_frozen_plan_binds_research_root_before_verification"
    if marker in text:
        raise SystemExit("execution binding regression already present")
    text += '''\n\ndef test_execute_frozen_plan_binds_research_root_before_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:\n    workspace = tmp_path / "workspace"\n    (workspace / "plan").mkdir(parents=True)\n    research_root = tmp_path / "research"\n    research_root.mkdir()\n    seen: dict[str, Path] = {}\n\n    monkeypatch.setattr(execution.h003, "compile_plan", lambda: [])\n\n    def fake_verify(_workspace: Path, *, research_root: Path | None = None):\n        assert research_root is not None\n        seen["research_root"] = research_root\n        return {}\n\n    monkeypatch.setattr(execution, "verify_complete_receipts", fake_verify)\n    receipt = execution.execute_frozen_plan(workspace, research_root=research_root)\n    assert seen["research_root"] == research_root\n    assert receipt["executed_trial_ids"] == []\n    assert receipt["resumed_verified_trial_ids"] == []\n'''
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_execution()
    patch_test()
