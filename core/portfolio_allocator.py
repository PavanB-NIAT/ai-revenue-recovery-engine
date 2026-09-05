"""
Contextual Intent & Cross-Rail Autonomous Payment Recovery Engine
Version B — Portfolio Recovery Allocator (Supervisory Experimental Layer).

Evaluates the allocation of finite recovery attempt capacity across a cohort of
failed digital payment transactions, comparing natural Arrival Order (FIFO) against
Economic Expected-Value (EV) Prioritized Allocation.

Guarantees order-independent downstream execution simulation so that individual
transaction/action simulated outcomes are identical across both policies.
"""

import copy
import hashlib
import json
import os
import random
import sys
from pathlib import Path

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent import AutonomousRecoveryPipeline


class DeterministicExecutionKernel:
    """
    Order-independent downstream execution simulator.
    
    Generates a deterministic pseudo-random stream derived strictly from:
    SHA-256(base_seed : transaction_id : action : hop)
    
    Guarantees that a given transaction and action produce the exact same
    simulated outcome (success/failure and response code) regardless of the order
    in which policies execute transactions.
    """

    def __init__(self, base_seed=1337):
        self.base_seed = base_seed

    def _get_rng(self, tx_id, action, hop=1):
        key = f"{self.base_seed}:{tx_id}:{action}:{hop}"
        seed_int = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
        return random.Random(seed_int)

    def execute(self, action, tx, context, hop=1):
        rng = self._get_rng(tx["transaction_id"], action, hop)

        if action == "SWITCH_SECONDARY_PG":
            pg_health = context.get("secondary_pg_health", 0.50)
            cbs_health = context.get("bank_cbs_health", 1.0)
            prob = pg_health * (1.0 if cbs_health >= 0.70 else 0.20)
            success = rng.random() < prob
            code = "SECONDARY_PG_200_OK" if success else (
                "SECONDARY_PG_504_GATEWAY_TIMEOUT" if pg_health < 0.70 else "SECONDARY_PG_ISSUER_UNAVAILABLE"
            )
            return success, code

        elif action == "TRIGGER_CROSS_RAIL_UPI":
            intent = context.get("intent_score", 0.50)
            if context.get("session_active"):
                pref_boost = 0.08 if context.get("customer_preferred_rail") == "UPI" else 0.0
                prob = min((0.80 + pref_boost) * (0.85 + 0.15 * intent), 0.96)
            else:
                prob = 0.25 * intent
            success = rng.random() < prob
            code = "UPI_INTENT_CAPTURED" if success else "UPI_APP_DISMISSED_OR_CANCELLED"
            return success, code

        elif action == "DISPATCH_FRICTIONLESS_AUTH_LINK":
            intent = context.get("intent_score", 0.50)
            base = 0.85 if context.get("session_active") else 0.30
            prob = base * (0.80 + 0.20 * intent)
            success = rng.random() < prob
            code = "AUTH_RECOMPLETED_200_OK" if success else "OTP_TIMEOUT_NO_ENTRY"
            return success, code

        elif action == "DISPATCH_ASYNC_RECOVERY_LINK":
            intent = context.get("intent_score", 0.50)
            latency_factor = 0.80 if context.get("time_since_failure_sec", 60) < 60 else 0.50
            prob = intent * latency_factor
            success = rng.random() < prob
            code = "ASYNC_LINK_PAID_SUCCESS" if success else "ASYNC_LINK_EXPIRED_NO_ACTION"
            return success, code

        elif action == "SCHEDULE_MANDATE_BATCH":
            has_mandate = context.get("customer_has_saved_mandate", False)
            cbs_health = context.get("bank_cbs_health", 1.0)
            prob = 0.90 if (has_mandate and cbs_health >= 0.70) else 0.15
            success = rng.random() < prob
            code = "MANDATE_DEBIT_CONFIRMED" if success else "MANDATE_EXECUTION_DECLINED"
            return success, code

        elif action == "BLIND_SAME_RAIL_RETRY":
            cbs_health = context.get("bank_cbs_health", 0.50)
            prob = cbs_health * 0.40
            success = rng.random() < prob
            code = "SAME_RAIL_RETRY_SUCCESS" if success else "SAME_RAIL_BOUNCE_OR_DECLINE"
            return success, code

        return False, "UNKNOWN_ACTION_DECLINED"


class PortfolioRecoveryAllocator:
    """
    Supervisory Allocation Layer.
    
    Operates above transaction-level pipelines to evaluate and allocate
    finite recovery capacity across an eligible cohort of payment failures.
    """

    def __init__(self, base_seed=1337):
        self.base_seed = base_seed
        self.kernel = DeterministicExecutionKernel(base_seed=base_seed)

    def extract_contextual_opportunities(self, transactions):
        """
        Inspects each transaction using the frozen Version-A contextual pipeline.
        
        Evaluates failure semantics, environment health, session posture, candidate
        generation, and policy/economic guardrails.
        
        Returns a standardized list of eligible opportunities (EV > 0, non-terminal).
        Both Policy A and Policy B receive this exact same opportunity set.
        """
        eligible_opportunities = []
        excluded_summary = {
            "terminal_failures": 0,
            "negative_ev": 0,
            "no_viable_candidates": 0
        }

        for idx, tx in enumerate(transactions):
            pipeline = AutonomousRecoveryPipeline(copy.deepcopy(tx))
            failure = pipeline.stage_1_understand_failure()

            # Guardrail 1: Terminal Security Failure Exclusion
            if failure["is_terminal"]:
                excluded_summary["terminal_failures"] += 1
                continue

            env = pipeline.stage_2_environment_state()
            posture = pipeline.stage_3_customer_posture()
            candidates = pipeline.stage_4_rank_candidates(failure, env, posture)

            if not candidates:
                excluded_summary["no_viable_candidates"] += 1
                continue

            selected = candidates[0]
            allowed, reason, ev = pipeline.stage_6_guardrails(selected, failure)

            # Guardrail 2: Economic Eligibility (EV > 0)
            if not allowed or ev <= 0:
                excluded_summary["negative_ev"] += 1
                continue

            # Eligible Opportunity
            eligible_opportunities.append({
                "cohort_index": idx,
                "transaction_id": tx["transaction_id"],
                "amount": tx["amount"],
                "currency": tx.get("currency", "INR"),
                "failure_category": tx.get("failure_category", "UNKNOWN"),
                "error_code": tx.get("error_code", "UNKNOWN"),
                "action": selected["action"],
                "confidence": round(selected["confidence"], 4),
                "expected_value": round(ev, 2),
                "context": copy.deepcopy(tx.get("context", {})),
                "raw_tx": copy.deepcopy(tx),
                "rationale": selected["rationale"]
            })

        return eligible_opportunities, excluded_summary

    def execute_policy_fifo(self, opportunities, capacity_limit):
        """
        Policy A: Arrival-Order Allocation (FIFO).
        Processes eligible opportunities sequentially until attempt capacity is exhausted.
        """
        attempts_used = 0
        recovered_gmv = 0
        successful_recoveries = 0
        failed_executions = 0
        trace = []

        for opp in opportunities:
            tx_id = opp["transaction_id"]
            amount = opp["amount"]
            action = opp["action"]
            context = opp["context"]

            if attempts_used >= capacity_limit:
                trace.append({
                    "transaction_id": tx_id,
                    "amount": amount,
                    "action": action,
                    "expected_value": opp["expected_value"],
                    "status": "STARVED_CAPACITY_EXHAUSTED",
                    "attempts": 0,
                    "success": False,
                    "revenue_recovered": 0
                })
                continue

            # Execute attempt via deterministic order-independent kernel
            attempts_used += 1
            success, code = self.kernel.execute(action, opp["raw_tx"], context, hop=1)

            if success:
                successful_recoveries += 1
                recovered_gmv += amount
                status = "RECOVERED"
            else:
                failed_executions += 1
                status = "EXECUTION_FAILED"

            trace.append({
                "transaction_id": tx_id,
                "amount": amount,
                "action": action,
                "expected_value": opp["expected_value"],
                "downstream_code": code,
                "status": status,
                "attempts": 1,
                "success": success,
                "revenue_recovered": amount if success else 0
            })

        op_costs = attempts_used * 15.0
        net_recovered = recovered_gmv - op_costs
        eff = (successful_recoveries / attempts_used * 100) if attempts_used > 0 else 0.0

        return {
            "policy_name": "FIFO_ARRIVAL_ORDER",
            "capacity_limit": capacity_limit,
            "opportunities_evaluated": len(opportunities),
            "attempts_used": attempts_used,
            "successful_recoveries": successful_recoveries,
            "failed_executions": failed_executions,
            "starved_transactions": sum(1 for t in trace if t["status"] == "STARVED_CAPACITY_EXHAUSTED"),
            "recovered_gmv": recovered_gmv,
            "operational_costs": op_costs,
            "net_recovered": net_recovered,
            "recovery_efficiency_pct": round(eff, 1),
            "execution_trace": trace
        }

    def execute_policy_portfolio(self, opportunities, capacity_limit):
        """
        Policy B: Portfolio Economic Allocation.
        Sorts the identical eligible opportunities by Expected Value (EV) descending,
        allocating attempt capacity to the highest-yield opportunities first.
        """
        # Sort opportunities by EV descending (secondary tie-breaker: confidence)
        prioritized = sorted(
            opportunities,
            key=lambda x: (x["expected_value"], x["confidence"], x["amount"]),
            reverse=True
        )

        attempts_used = 0
        recovered_gmv = 0
        successful_recoveries = 0
        failed_executions = 0
        trace = []

        for opp in prioritized:
            tx_id = opp["transaction_id"]
            amount = opp["amount"]
            action = opp["action"]
            context = opp["context"]

            if attempts_used >= capacity_limit:
                trace.append({
                    "transaction_id": tx_id,
                    "amount": amount,
                    "action": action,
                    "expected_value": opp["expected_value"],
                    "status": "STARVED_CAPACITY_EXHAUSTED",
                    "attempts": 0,
                    "success": False,
                    "revenue_recovered": 0
                })
                continue

            # Execute attempt via deterministic order-independent kernel
            attempts_used += 1
            success, code = self.kernel.execute(action, opp["raw_tx"], context, hop=1)

            if success:
                successful_recoveries += 1
                recovered_gmv += amount
                status = "RECOVERED"
            else:
                failed_executions += 1
                status = "EXECUTION_FAILED"

            trace.append({
                "transaction_id": tx_id,
                "amount": amount,
                "action": action,
                "expected_value": opp["expected_value"],
                "downstream_code": code,
                "status": status,
                "attempts": 1,
                "success": success,
                "revenue_recovered": amount if success else 0
            })

        op_costs = attempts_used * 15.0
        net_recovered = recovered_gmv - op_costs
        eff = (successful_recoveries / attempts_used * 100) if attempts_used > 0 else 0.0

        return {
            "policy_name": "PORTFOLIO_EV_ALLOCATOR",
            "capacity_limit": capacity_limit,
            "opportunities_evaluated": len(opportunities),
            "attempts_used": attempts_used,
            "successful_recoveries": successful_recoveries,
            "failed_executions": failed_executions,
            "starved_transactions": sum(1 for t in trace if t["status"] == "STARVED_CAPACITY_EXHAUSTED"),
            "recovered_gmv": recovered_gmv,
            "operational_costs": op_costs,
            "net_recovered": net_recovered,
            "recovery_efficiency_pct": round(eff, 1),
            "execution_trace": trace
        }

    def run_controlled_experiment(self, transactions, capacity_limit=20):
        """
        Executes the controlled finite-capacity experiment:
        1. Extracts shared contextual opportunity set.
        2. Evaluates Policy A (Arrival Order) at capacity_limit.
        3. Evaluates Policy B (Portfolio Allocator) at capacity_limit.
        4. Evaluates sensitivity across K in [10, 20, 30, 43].
        5. Performs diagnostic comparison against Version-A canonical benchmark.
        """
        total_risk = sum(tx["amount"] for tx in transactions)
        opportunities, exclusions = self.extract_contextual_opportunities(transactions)

        # 1. Primary Benchmark Execution (K = capacity_limit)
        res_fifo = self.execute_policy_fifo(opportunities, capacity_limit)
        res_portfolio = self.execute_policy_portfolio(opportunities, capacity_limit)

        # 2. Comparative Deltas
        gmv_delta = res_portfolio["recovered_gmv"] - res_fifo["recovered_gmv"]
        net_delta = res_portfolio["net_recovered"] - res_fifo["net_recovered"]
        pct_gain = (gmv_delta / res_fifo["recovered_gmv"] * 100) if res_fifo["recovered_gmv"] > 0 else 0.0

        if gmv_delta > 0:
            classification = "PORTFOLIO_OUTPERFORMS_FIFO"
        elif gmv_delta == 0:
            classification = "EQUAL_PERFORMANCE"
        else:
            classification = "PORTFOLIO_UNDERPERFORMS_FIFO"

        # 3. Sensitivity Analysis across capacity thresholds
        sensitivity = {}
        for k in [10, 20, 30, 43]:
            k_fifo = self.execute_policy_fifo(opportunities, k)
            k_port = self.execute_policy_portfolio(opportunities, k)
            k_delta = k_port["recovered_gmv"] - k_fifo["recovered_gmv"]
            sensitivity[f"K_{k}"] = {
                "capacity_k": k,
                "fifo_recovered": k_fifo["recovered_gmv"],
                "portfolio_recovered": k_port["recovered_gmv"],
                "delta_gmv": k_delta,
                "pct_gain": round((k_delta / k_fifo["recovered_gmv"] * 100) if k_fifo["recovered_gmv"] > 0 else 0.0, 1),
                "fifo_successes": k_fifo["successful_recoveries"],
                "portfolio_successes": k_port["successful_recoveries"]
            }

        # 4. Diagnostic Comparison against Version-A Canonical Benchmark
        version_a_canonical_gmv = 130224.0
        k43_portfolio_gmv = sensitivity["K_43"]["portfolio_recovered"]
        k43_delta_vs_version_a = k43_portfolio_gmv - version_a_canonical_gmv

        diagnostic = {
            "version_a_canonical_gmv": version_a_canonical_gmv,
            "version_a_lifecycle": "Multi-hop dynamic state reassessment (up to 2 hops)",
            "version_b_k43_gmv": k43_portfolio_gmv,
            "version_b_scope": "Single initial opportunity allocation under capacity K",
            "numerical_delta": k43_delta_vs_version_a,
            "scope_explanation": (
                "Version-A executes dynamic multi-hop state reassessment after failed Hop 1 attempts. "
                "Version-B intentionally evaluates allocation of initial recovery opportunities under "
                "finite capacity. At K=43, Version-B represents the single-hop frontier."
            )
        }

        return {
            "experiment_name": "Controlled Finite-Capacity Allocation Experiment",
            "primary_capacity_k": capacity_limit,
            "total_transactions_evaluated": len(transactions),
            "gross_revenue_at_risk": total_risk,
            "eligible_opportunities_count": len(opportunities),
            "exclusions_summary": exclusions,
            "policy_comparison_primary_k": {
                "fifo_policy": res_fifo,
                "portfolio_policy": res_portfolio,
                "metrics_delta": {
                    "gmv_recovered_delta": gmv_delta,
                    "net_financial_delta": net_delta,
                    "percentage_gain": round(pct_gain, 1),
                    "empirical_classification": classification
                }
            },
            "capacity_sensitivity": sensitivity,
            "k43_diagnostic_comparison": diagnostic,
            "methodology_disclaimer": "Measured result -- not a guaranteed improvement. Synthetic simulation experiment."
        }
