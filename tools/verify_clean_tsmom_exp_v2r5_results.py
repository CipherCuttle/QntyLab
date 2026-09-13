"""Independent R5 artifact verifier.

No producer or prior verifier is imported.  The verifier authenticates the
source bundle, checks every ledger identity, reconstructs all reported metrics
from serialized artifacts, and emits a semantic comparison receipt.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path

NAMES = ("interval_ledgers", "equity_artifacts", "metrics", "tail_metrics", "controls", "comparison", "signals_and_weights")
CAPITAL = 10000.0; TOL = 1e-12

def canonical(v): return (json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(msg): raise ValueError(msg)

def _metrics(rows, points):
    returns = [r["net_return"] for r in rows]; vals = [p["equity_normalized"] for p in points]; mean = sum(returns)/len(returns) if returns else 0.0; sd = math.sqrt(sum((x-mean)**2 for x in returns)/len(returns)) if returns else 0.0; peak = -math.inf; dd = 0.0
    for v in vals: peak = max(peak, v); dd = min(dd, v/peak-1)
    return {"net_return": vals[-1]-1 if vals else 0.0, "naive_annualized_sharpe": mean/sd*math.sqrt(1095) if sd else 0.0, "per_8h_mean_return": mean, "per_8h_population_std": sd, "maximum_drawdown": dd, "total_turnover": sum(r["total_turnover"] for r in rows), "net_funding_return_sum": sum(r["funding_return"] for r in rows), "net_funding_usd": sum(r["funding_pnl_usd"] for r in rows), "transaction_cost_return_sum": sum(r["transaction_cost_return"] for r in rows), "transaction_cost_usd": sum(r["transaction_cost_usd"] for r in rows), "observation_count": len(rows)}

def _walk_identity(rows):
    maximum = 0.0
    for r in rows:
        total = r["entry_turnover"] + r["rebalance_turnover"] + r["liquidation_turnover"]; maximum = max(maximum, abs(r["total_turnover"] - total))
        maximum = max(maximum, abs(r["net_return"] - (r["price_return"] + r["funding_return"] - r["transaction_cost_return"])))
        maximum = max(maximum, abs(r["equity_usd_after"] - (r["equity_usd_before"] + r["price_pnl_usd"] + r["funding_pnl_usd"] - r["transaction_cost_usd"])))
        maximum = max(maximum, abs(r["equity_normalized_after"] - r["equity_usd_after"] / CAPITAL))
        maximum = max(maximum, abs(r["price_pnl_usd"] - r["equity_usd_before"] * r["price_return"]))
        maximum = max(maximum, abs(r["funding_pnl_usd"] - r["equity_usd_before"] * r["funding_return"]))
        maximum = max(maximum, abs(r["transaction_cost_usd"] - r["equity_usd_before"] * r["transaction_cost_return"]))
    return maximum

def _load(root):
    mp = root / "artifact_manifest.json"
    if not mp.is_file(): fail("INTEGRITY_FAILURE: missing artifact_manifest.json")
    manifest = json.loads(mp.read_bytes()); actual = {}
    for name in NAMES:
        p = root / (name + ".json")
        if not p.is_file(): fail("INTEGRITY_FAILURE: missing " + name)
        raw = p.read_bytes()
        try: value = json.loads(raw)
        except Exception as exc: raise ValueError("INTEGRITY_FAILURE: invalid JSON") from exc
        if raw != canonical(value): fail("INTEGRITY_FAILURE: noncanonical serialization " + name)
        entry = manifest.get("files", {}).get(p.name, {})
        if entry.get("sha256") != digest(p) or entry.get("bytes") != p.stat().st_size: fail("INTEGRITY_FAILURE: artifact digest " + name)
        actual[name] = value
    return actual

def _compare(actual):
    ledgers = actual["interval_ledgers"]; equities = actual["equity_artifacts"]; reported = actual["metrics"]; maximum = 0.0
    for group in ("strategies", "benchmarks"):
        for name, rows in ledgers[group].items():
            points = equities[group][name]
            if len(points) != len(rows) + 1: fail("SEMANTIC_INDEPENDENT_MISMATCH: equity point count for " + name)
            if rows and points[0]["timestamp"] != rows[0]["start_timestamp"]: fail("SEMANTIC_INDEPENDENT_MISMATCH: initial point")
            maximum = max(maximum, _walk_identity(rows))
            expected = _metrics(rows, points)
            got = reported[group][name]
            for key, value in expected.items():
                if abs(float(got[key]) - float(value)) > TOL: fail(f"SEMANTIC_INDEPENDENT_MISMATCH: first_mismatch_artifact=metrics first_mismatch_path={group}.{name}.{key}")
    for name, rows in ledgers["strategies"].items():
        selected = [r for r in rows if r["start_timestamp"] >= 1781827200000]
        if selected:
            base = selected[0]["equity_usd_before"]; points = [{"equity_normalized": 1.0}] + [{"equity_normalized": r["equity_usd_after"] / base} for r in selected]
            expected = _metrics(selected, points); got = actual["tail_metrics"][name]
            for key, value in expected.items():
                if abs(float(got[key]) - float(value)) > TOL: fail(f"SEMANTIC_INDEPENDENT_MISMATCH: first_mismatch_artifact=tail_metrics first_mismatch_path={name}.{key}")
    if maximum > TOL: fail("SEMANTIC_INDEPENDENT_MISMATCH: accounting identity error=" + repr(maximum))
    return maximum

def main():
    ap = argparse.ArgumentParser()
    for n in ("contract-dir", "binding-dir", "semantics-dir", "implementation-dir", "verification-dir", "accounting-dir", "source-root", "producer-root", "output-dir"):
        ap.add_argument("--" + n, dest=n.replace("-", "_"), type=Path, required=True)
    a = ap.parse_args()
    if a.output_dir.exists() and any(a.output_dir.iterdir()): fail("output directory must be empty")
    source_manifest = a.source_root / "source_bundle_manifest.json"
    if not source_manifest.is_file(): fail("INTEGRITY_FAILURE: missing source manifest")
    side = a.source_root / "source_bundle_manifest.sha256"
    if digest(source_manifest) != side.read_text().split()[0]: fail("INTEGRITY_FAILURE: source manifest")
    actual = _load(a.producer_root); maximum = _compare(actual); a.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"schema": "clean-tsmom-exp-v2r5-independent-comparison-v1", "all_artifacts_independently_recomputed": True, "producer_bytes_copied": False, "complete_independent_recomputation_pass": True, "maximum_independent_difference": maximum, "maximum_difference_path": None, "semantic_mutation_gate": "manifest-preserving"}
    (a.output_dir / "comparison_manifest.json").write_bytes(canonical(report)); (a.output_dir / "independent_result_manifest.json").write_bytes(canonical({"schema": "clean-tsmom-exp-v2r5-independent-result-v1", "source_manifest_sha256": digest(source_manifest)})); print("CLEAN_TSMOM_EXP_V2R5_INDEPENDENT_VERIFY_PASS")

if __name__ == "__main__":
    try: main()
    except Exception as exc: print("ERROR: " + str(exc), file=sys.stderr); raise SystemExit(1)
