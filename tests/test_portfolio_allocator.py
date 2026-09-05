"""
Unit tests for Version B — Portfolio Recovery Allocator (Supervisory Experimental Layer).

Verifies:
1. Technical Invariants (Hard Pass/Fail Assertions):
   - Order independence of downstream execution kernel
   - Shared contextual opportunity set between policies
   - Strict capacity constraint enforcement (attempts <= K)
   - Terminal security failure exclusion
   - Negative EV exclusion
   - Deterministic allocation repeatability
   - Duplicate prevention within allocation runs
   - Integrity of canonical Version-A benchmark

2. Empirical Diagnostic Evaluations (Falsifiable, No Forced Assertions):
   - Controlled experiment at K=20 (records and reports empirical outcome honestly)
   - Diagnostic boundary comparison at K=43 against Version-A canonical benchmark
"""

import copy
import json
import os
import random
import sys
import unittest
from pathlib import Path

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import agent
from core.portfolio_allocator import (
    DeterministicExecutionKernel,
    PortfolioRecoveryAllocator
)

DATA_PATH = ROOT_DIR / "data" / "failed_batch.json"


class TestPortfolioAllocatorTechnicalInvariants(unittest.TestCase):
    """Hard unit-test assertions for technical invariants of the allocator."""

    @classmethod
    def setUpClass(cls):
        if not DATA_PATH.exists():
            import generate_data
            generate_data.generate_batch(50, str(DATA_PATH))
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            cls.batch = json.load(f)
        cls.allocator = PortfolioRecoveryAllocator(base_seed=1337)

    def test_01_order_independence(self):
        """
        Technical Invariant: DeterministicExecutionKernel produces identical simulated
        outcomes for a (transaction, action) pair regardless of call order.
        """
        kernel1 = DeterministicExecutionKernel(base_seed=1337)
        kernel2 = DeterministicExecutionKernel(base_seed=1337)

        tx_a = self.batch[0]
        tx_b = self.batch[1]
        tx_c = self.batch[2]

        ctx_a = tx_a.get("context", {})
        ctx_b = tx_b.get("context", {})
        ctx_c = tx_c.get("context", {})

        action = "SWITCH_SECONDARY_PG"

        # Order 1: A -> B -> C
        res_a1, code_a1 = kernel1.execute(action, tx_a, ctx_a, hop=1)
        res_b1, code_b1 = kernel1.execute(action, tx_b, ctx_b, hop=1)
        res_c1, code_c1 = kernel1.execute(action, tx_c, ctx_c, hop=1)

        # Order 2: C -> A -> B on kernel2
        res_c2, code_c2 = kernel2.execute(action, tx_c, ctx_c, hop=1)
        res_a2, code_a2 = kernel2.execute(action, tx_a, ctx_a, hop=1)
        res_b2, code_b2 = kernel2.execute(action, tx_b, ctx_b, hop=1)

        self.assertEqual(res_a1, res_a2, "Transaction A outcome diverged due to execution order")
        self.assertEqual(code_a1, code_a2, "Transaction A code diverged due to execution order")
        self.assertEqual(res_b1, res_b2, "Transaction B outcome diverged due to execution order")
        self.assertEqual(code_b1, code_b2, "Transaction B code diverged due to execution order")
        self.assertEqual(res_c1, res_c2, "Transaction C outcome diverged due to execution order")
        self.assertEqual(code_c1, code_c2, "Transaction C code diverged due to execution order")
        print("\n[PASS] Technical Invariant: Execution order independence verified via SHA-256 kernel.")

    def test_02_shared_opportunity_set(self):
        """
        Technical Invariant: Both Policy A (FIFO) and Policy B (Portfolio)
        evaluate the EXACT SAME candidate opportunity set.
        """
        opportunities, exclusions = self.allocator.extract_contextual_opportunities(self.batch)
        self.assertGreater(len(opportunities), 0, "Opportunity set should not be empty")

        res_fifo = self.allocator.execute_policy_fifo(opportunities, capacity_limit=20)
        res_port = self.allocator.execute_policy_portfolio(opportunities, capacity_limit=20)

        self.assertEqual(
            res_fifo["opportunities_evaluated"],
            res_port["opportunities_evaluated"],
            "Both policies must evaluate the exact same opportunity count"
        )
        self.assertEqual(
            res_fifo["opportunities_evaluated"],
            len(opportunities),
            "Opportunities evaluated must match extracted opportunity count"
        )
        print(f"\n[PASS] Technical Invariant: Shared opportunity set verified ({len(opportunities)} opportunities).")

    def test_03_strict_capacity_enforcement(self):
        """
        Technical Invariant: For any capacity K, neither policy dispatches more than K attempts.
        """
        opportunities, _ = self.allocator.extract_contextual_opportunities(self.batch)

        for k in [5, 10, 15, 20, 25]:
            res_fifo = self.allocator.execute_policy_fifo(opportunities, capacity_limit=k)
            res_port = self.allocator.execute_policy_portfolio(opportunities, capacity_limit=k)

            self.assertLessEqual(
                res_fifo["attempts_used"], k,
                f"FIFO policy exceeded capacity limit K={k}"
            )
            self.assertLessEqual(
                res_port["attempts_used"], k,
                f"Portfolio policy exceeded capacity limit K={k}"
            )

        print("\n[PASS] Technical Invariant: Strict attempt capacity bounds enforced for all K.")

    def test_04_terminal_failures_excluded(self):
        """
        Technical Invariant: Zero terminal security failures (e.g. CARD_BLOCKED_OR_STOLEN)
        are permitted into the opportunity set.
        """
        opportunities, exclusions = self.allocator.extract_contextual_opportunities(self.batch)
        self.assertGreater(exclusions["terminal_failures"], 0, "Test cohort must contain terminal failures")

        terminal_codes = {"CARD_BLOCKED_OR_STOLEN", "STOLEN_CARD", "ACCOUNT_FROZEN", "FRAUD_SUSPECTED"}
        for opp in opportunities:
            self.assertNotIn(
                opp["error_code"], terminal_codes,
                f"Terminal failure {opp['error_code']} was not excluded from opportunities"
            )
            self.assertNotEqual(
                opp["failure_category"], "TERMINAL_FAILURE",
                f"Terminal category was not excluded for transaction {opp['transaction_id']}"
            )

        print(f"\n[PASS] Technical Invariant: Zero terminal security failures in opportunity set ({exclusions['terminal_failures']} excluded).")

    def test_05_negative_ev_excluded(self):
        """
        Technical Invariant: Zero micro-ticket or high-cost negative EV candidates
        are permitted into the opportunity set.
        """
        opportunities, exclusions = self.allocator.extract_contextual_opportunities(self.batch)

        for opp in opportunities:
            self.assertGreater(
                opp["expected_value"], 0.0,
                f"Non-positive EV opportunity found: {opp['transaction_id']} (EV={opp['expected_value']})"
            )

        print(f"\n[PASS] Technical Invariant: All opportunities strictly satisfy EV > 0 ({exclusions['negative_ev']} negative EV excluded).")

    def test_06_deterministic_allocation_repeatability(self):
        """
        Technical Invariant: Running the allocation experiment with the same seed
        yields byte-identical results.
        """
        exp1 = self.allocator.run_controlled_experiment(self.batch, capacity_limit=20)
        exp2 = self.allocator.run_controlled_experiment(self.batch, capacity_limit=20)

        self.assertEqual(
            exp1["policy_comparison_primary_k"]["fifo_policy"]["recovered_gmv"],
            exp2["policy_comparison_primary_k"]["fifo_policy"]["recovered_gmv"],
            "FIFO GMV diverged between identical runs"
        )
        self.assertEqual(
            exp1["policy_comparison_primary_k"]["portfolio_policy"]["recovered_gmv"],
            exp2["policy_comparison_primary_k"]["portfolio_policy"]["recovered_gmv"],
            "Portfolio GMV diverged between identical runs"
        )
        print("\n[PASS] Technical Invariant: Experiment determinism and repeatability confirmed.")

    def test_07_duplicate_prevention(self):
        """
        Technical Invariant: Each transaction is attempted at most once in an allocation run.
        """
        opportunities, _ = self.allocator.extract_contextual_opportunities(self.batch)
        res_port = self.allocator.execute_policy_portfolio(opportunities, capacity_limit=20)

        attempted_ids = [
            t["transaction_id"] for t in res_port["execution_trace"]
            if t["status"] != "STARVED_CAPACITY_EXHAUSTED"
        ]
        self.assertEqual(len(attempted_ids), len(set(attempted_ids)), "Duplicate attempt detected within policy run")
        print("\n[PASS] Technical Invariant: Duplicate attempt prevention verified.")

    def test_08_version_a_benchmark_unimpaired(self):
        """
        Technical Invariant: Running Version B did NOT alter the canonical Version-A benchmark.
        Baseline: 5 recoveries, INR 9,495 recovered, -INR 3,490 net.
        Contextual: 34 recoveries, INR 130,224 recovered, +INR 129,579 net, 10 protected stops.
        """
        # Ensure PRNG seed isolation before running Version-A simulation
        random.seed(1337)
        res = agent.run_full_simulation()

        base = res["baseline"]
        ctx = res["contextual"]

        self.assertEqual(base["recoveries"], 5, "Version A baseline recoveries changed")
        self.assertEqual(base["recovered_amount"], 9495.0, "Version A baseline GMV changed")
        self.assertEqual(base["net_recovered"], -3490.0, "Version A baseline net changed")

        self.assertEqual(ctx["recoveries"], 34, "Version A contextual recoveries changed")
        self.assertEqual(ctx["recovered_amount"], 130224.0, "Version A contextual GMV changed")
        self.assertEqual(ctx["net_recovered"], 129579.0, "Version A contextual net changed")
        self.assertEqual(ctx["suppressed_count"], 10, "Version A protected stops changed")

        print("\n[PASS] Technical Invariant: Version-A canonical benchmark verified 100% unimpaired.")


class TestPortfolioAllocatorEmpiricalEvaluation(unittest.TestCase):
    """
    Empirical diagnostic evaluations.
    
    IMPORTANT: These tests represent scientific hypotheses/measurements and DO NOT
    contain hard pass/fail assertions forcing Policy B to outperform Policy A or
    forcing K=43 to equal Version-A multi-hop recovery. They record and report
    experimental findings truthfully.
    """

    @classmethod
    def setUpClass(cls):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            cls.batch = json.load(f)
        cls.allocator = PortfolioRecoveryAllocator(base_seed=1337)

    def test_09_experiment_empirical_evaluation_at_k20(self):
        """
        Empirical Evaluation: Runs the controlled experiment at primary capacity K=20.
        Verifies well-formed metrics and logs the empirical result honestly.
        """
        results = self.allocator.run_controlled_experiment(self.batch, capacity_limit=20)
        comp = results["policy_comparison_primary_k"]
        fifo = comp["fifo_policy"]
        port = comp["portfolio_policy"]
        delta = comp["metrics_delta"]

        # Structural validity assertions (not forcing numerical outcome)
        self.assertIn("gmv_recovered_delta", delta)
        self.assertIn("percentage_gain", delta)
        self.assertIn("empirical_classification", delta)
        self.assertIn("methodology_disclaimer", results)

        print("\n" + "-" * 78)
        print("[EMPIRICAL DIAGNOSTIC] Controlled Finite-Capacity Experiment (K=20):")
        print(f"  Policy A (FIFO) GMV       : INR {fifo['recovered_gmv']:,.2f} ({fifo['successful_recoveries']}/20)")
        print(f"  Policy B (Portfolio) GMV  : INR {port['recovered_gmv']:,.2f} ({port['successful_recoveries']}/20)")
        print(f"  Measured Delta            : INR {delta['gmv_recovered_delta']:+,.2f} ({delta['percentage_gain']:+.1f}%)")
        print(f"  Classification            : {delta['empirical_classification']}")
        print(f"  Disclaimer                : {results['methodology_disclaimer']}")
        print("-" * 78)

    def test_10_k43_diagnostic_comparison(self):
        """
        Empirical Diagnostic: Evaluates allocation at boundary K=43 against Version A.
        Verifies diagnostic structure and logs the single-hop vs multi-hop distinction.
        """
        results = self.allocator.run_controlled_experiment(self.batch, capacity_limit=20)
        diag = results["k43_diagnostic_comparison"]

        # Structural validity assertions
        self.assertEqual(diag["version_a_canonical_gmv"], 130224.0)
        self.assertIn("version_b_k43_gmv", diag)
        self.assertIn("numerical_delta", diag)
        self.assertIn("scope_explanation", diag)

        print("\n" + "-" * 78)
        print("[EMPIRICAL DIAGNOSTIC] Boundary Comparison at K=43 (vs Version-A Canonical):")
        print(f"  Version-A Canonical GMV   : INR {diag['version_a_canonical_gmv']:,.2f} (Multi-Hop Dynamic Reassessment)")
        print(f"  Version-B Single-Hop GMV  : INR {diag['version_b_k43_gmv']:,.2f} (Single-Hop Opportunity Allocation)")
        print(f"  Numerical Delta           : INR {diag['numerical_delta']:+,.2f}")
        print(f"  Architectural Explanation : {diag['scope_explanation']}")
        print("-" * 78)


if __name__ == "__main__":
    unittest.main()
