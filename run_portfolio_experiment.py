"""
Contextual Intent & Cross-Rail Autonomous Payment Recovery Engine
Version B — Portfolio Recovery Allocator Experiment Runner

Executes the controlled finite-capacity allocation experiment:
Policy A (FIFO Arrival Order) vs Policy B (Portfolio EV Prioritization)
across a shared contextual opportunity set under identical capacity constraints.
"""

import json
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.portfolio_allocator import PortfolioRecoveryAllocator

DATA_PATH = ROOT_DIR / "data" / "failed_batch.json"
OUTPUT_JSON_PATH = ROOT_DIR / "data" / "portfolio_experiment.json"


def load_dataset():
    """Loads canonical failed batch or triggers generator if absent."""
    if not DATA_PATH.exists():
        print(f"[!] Dataset not found at {DATA_PATH}. Running generator...")
        import generate_data
        generate_data.generate_batch(50, str(DATA_PATH))
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def format_inr(amount):
    """Formats float to clean INR string."""
    return f"INR {amount:,.2f}"


def run_experiment(capacity_k=20, base_seed=1337):
    """Executes the finite-capacity experiment and prints structured presentation."""
    transactions = load_dataset()
    allocator = PortfolioRecoveryAllocator(base_seed=base_seed)
    results = allocator.run_controlled_experiment(transactions, capacity_limit=capacity_k)

    # Save artifact to data/portfolio_experiment.json
    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Present Findings
    comp = results["policy_comparison_primary_k"]
    fifo = comp["fifo_policy"]
    port = comp["portfolio_policy"]
    delta = comp["metrics_delta"]
    sens = results["capacity_sensitivity"]
    diag = results["k43_diagnostic_comparison"]
    excl = results["exclusions_summary"]

    succ_diff = port["successful_recoveries"] - fifo["successful_recoveries"]
    fail_diff = port["failed_executions"] - fifo["failed_executions"]
    fifo_eff_str = f"{fifo['recovery_efficiency_pct']:.1f}%"
    port_eff_str = f"{port['recovery_efficiency_pct']:.1f}%"
    eff_diff = port["recovery_efficiency_pct"] - fifo["recovery_efficiency_pct"]
    eff_diff_str = f"{eff_diff:+.1f}%"

    gmv_delta_str = format_inr(delta["gmv_recovered_delta"])
    net_delta_str = format_inr(delta["net_financial_delta"])
    succ_diff_str = f"{succ_diff:+}"
    fail_diff_str = f"{fail_diff:+}"

    print("=" * 84)
    print("      VERSION B: PORTFOLIO RECOVERY ALLOCATOR (SUPERVISORY LAYER)")
    print("           Controlled Finite-Capacity Allocation Experiment")
    print("=" * 84)
    print("PROBLEM STATEMENT:")
    print("  Under operational recovery constraints (SMS/WhatsApp quotas, bank rate limits,")
    print("  agent capacity), a merchant cannot attempt recovery on every failed payment.")
    print("  This experiment isolates the impact of ALLOCATION POLICY on a shared cohort.")
    print("-" * 84)
    print(f"Cohort Size Evaluated      : {results['total_transactions_evaluated']} transactions")
    print(f"Gross Revenue at Risk      : {format_inr(results['gross_revenue_at_risk'])}")
    print(f"Eligible Contextual Set    : {results['eligible_opportunities_count']} opportunities (EV > 0, Non-Terminal)")
    print(f"Guardrail Exclusions       : {excl['terminal_failures']} Terminal Security | {excl['negative_ev']} Negative EV | {excl['no_viable_candidates']} No Viable Path")
    print("Experimental Controls      : Both policies operate on IDENTICAL opportunity set.")
    print("Downstream Simulation      : Deterministic order-independent kernel (SHA-256 seed per tx).")
    print("=" * 84)

    # Table 1: Primary Comparison at K=20
    print(f"\n[TABLE 1] PRIMARY EXPERIMENT COMPARISON AT CAPACITY LIMIT K = {capacity_k}")
    print("-" * 84)
    print(f"{'Performance Metric':<32} | {'Policy A (FIFO)':<18} | {'Policy B (Portfolio)':<22} | {'Delta':<10}")
    print("-" * 84)
    print(f"{'Allocation Rule':<32} | {'Arrival Order':<18} | {'Highest EV First':<22} | {'--':<10}")
    print(f"{'Attempt Capacity (K)':<32} | {str(fifo['capacity_limit']):<18} | {str(port['capacity_limit']):<22} | {'0':<10}")
    print(f"{'Attempts Dispatched':<32} | {str(fifo['attempts_used']):<18} | {str(port['attempts_used']):<22} | {'0':<10}")
    print(f"{'Successful Recoveries':<32} | {str(fifo['successful_recoveries']):<18} | {str(port['successful_recoveries']):<22} | {succ_diff_str:<10}")
    print(f"{'Failed Executions':<32} | {str(fifo['failed_executions']):<18} | {str(port['failed_executions']):<22} | {fail_diff_str:<10}")
    print(f"{'Starved Opportunities':<32} | {str(fifo['starved_transactions']):<18} | {str(port['starved_transactions']):<22} | {'0':<10}")
    print(f"{'Recovered Gross GMV':<32} | {format_inr(fifo['recovered_gmv']):<18} | {format_inr(port['recovered_gmv']):<22} | {gmv_delta_str:<10}")
    print(f"{'Operational Costs (INR 15/att)':<32} | {format_inr(fifo['operational_costs']):<18} | {format_inr(port['operational_costs']):<22} | {'INR 0.00':<10}")
    print(f"{'Net Financial Recovery':<32} | {format_inr(fifo['net_recovered']):<18} | {format_inr(port['net_recovered']):<22} | {net_delta_str:<10}")
    print(f"{'Recovery Efficiency':<32} | {fifo_eff_str:<18} | {port_eff_str:<22} | {eff_diff_str:<10}")
    print("-" * 84)
    print(f"Empirical Evaluation      : {delta['empirical_classification']} ({delta['percentage_gain']:+.1f}% GMV)")
    print(f"Measured Status           : Measured result -- not a guaranteed improvement.")

    # Table 2: Capacity Sensitivity Analysis
    print("\n" + "=" * 84)
    print("               CAPACITY SENSITIVITY ANALYSIS (K in [10, 20, 30, 43])")
    print("=" * 84)
    print(f"{'Capacity (K)':<14} | {'FIFO GMV':<18} | {'Portfolio GMV':<18} | {'Delta GMV':<16} | {'Gain (%)':<10}")
    print("-" * 84)
    for k_key, s in sens.items():
        k_val = s["capacity_k"]
        label = f"K = {k_val}" + (" (Strict)" if k_val == 10 else (" (Primary)" if k_val == 20 else (" (Generous)" if k_val == 30 else " (Boundary)")))
        delta_str = f"{s['delta_gmv']:>+12,.2f}"
        pct_str = f"{s['pct_gain']:>+6.1f}%"
        print(f"{label:<14} | {format_inr(s['fifo_recovered']):<18} | {format_inr(s['portfolio_recovered']):<18} | {delta_str:<16} | {pct_str:<10}")
    print("-" * 84)

    # Diagnostic Section: Boundary K=43 vs Canonical Version A
    print("\n" + "=" * 84)
    print("      DIAGNOSTIC BOUNDARY COMPARISON AT K = 43 (VS VERSION-A BENCHMARK)")
    print("=" * 84)
    print(f"Version-A Canonical GMV    : {format_inr(diag['version_a_canonical_gmv'])} ({diag['version_a_lifecycle']})")
    print(f"Version-B Portfolio GMV    : {format_inr(diag['version_b_k43_gmv'])} ({diag['version_b_scope']})")
    print(f"Numerical Difference       : {format_inr(diag['numerical_delta'])}")
    print("Scope Distinction:")
    print(f"  {diag['scope_explanation']}")
    print("-" * 84)
    print(f"* Full experimental results saved to: {OUTPUT_JSON_PATH}")
    print("=" * 84 + "\n")

    return results


if __name__ == "__main__":
    run_experiment()
