import json
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure repo root is available on sys.path regardless of execution working directory
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent import AutonomousRecoveryPipeline, run_baseline_evaluation, execute_downstream_action

class TestContextualRecoveryEngineAdversarial(unittest.TestCase):
    
    def test_01_same_failure_different_context_different_decisions(self):
        """
        Adversarial Test 1: The same failure type (GATEWAY_TIMEOUT) must produce 3
        distinct outcomes depending on session posture and gateway health.
        """
        base_ctx = {
            "bank_cbs_health": 0.95,
            "customer_upi_intent_supported": True,
            "customer_has_saved_mandate": False,
            "customer_preferred_rail": "CARDS",
            "is_terminal_failure": False
        }
        
        # Tx 1: In checkout + healthy secondary PG -> SWITCH_SECONDARY_PG
        tx_1 = {
            "transaction_id": "tx_adv_1a", "amount": 2500, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE",
            "initial_retry_count": 0,
            "context": {**base_ctx, "session_active": True, "secondary_pg_health": 0.95, "intent_score": 0.90, "time_since_failure_sec": 5}
        }
        
        # Tx 2: Abandoned checkout + degraded secondary PG -> DISPATCH_ASYNC_RECOVERY_LINK
        tx_2 = {
            "transaction_id": "tx_adv_1b", "amount": 2500, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE",
            "initial_retry_count": 0,
            "context": {**base_ctx, "session_active": False, "secondary_pg_health": 0.40, "intent_score": 0.85, "time_since_failure_sec": 85}
        }
        
        # Tx 3: Abandoned checkout + low intent + low value (INR 49) -> SUPPRESSED_NEGATIVE_EV
        tx_3 = {
            "transaction_id": "tx_adv_1c", "amount": 49, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE",
            "initial_retry_count": 0,
            "context": {**base_ctx, "session_active": False, "secondary_pg_health": 0.35, "intent_score": 0.30, "time_since_failure_sec": 120}
        }
        
        res_1 = AutonomousRecoveryPipeline(tx_1).run_lifecycle()
        res_2 = AutonomousRecoveryPipeline(tx_2).run_lifecycle()
        res_3 = AutonomousRecoveryPipeline(tx_3).run_lifecycle()
        
        act_1 = res_1["lifecycle_trace"][0].get("action_executed")
        act_2 = res_2["lifecycle_trace"][0].get("action_executed")
        status_3 = res_3["final_status"]
        
        self.assertEqual(act_1, "SWITCH_SECONDARY_PG")
        self.assertEqual(act_2, "DISPATCH_ASYNC_RECOVERY_LINK")
        self.assertEqual(status_3, "SUPPRESSED_NEGATIVE_EV")
        print("\n[PASS] Same failure type produced 3 distinct contextual actions/decisions.")

    def test_02_active_vs_abandoned_session_posture(self):
        """
        Adversarial Test 2: In-session actions (e.g. UPI Intent modal) must NEVER be
        selected when customer session has been abandoned.
        """
        # Bank down with active session -> can trigger UPI intent modal
        tx_active = {
            "transaction_id": "tx_adv_active", "amount": 1000, "currency": "INR",
            "error_code": "BANK_CBS_DOWN", "failure_category": "BANK_DOWNTIME",
            "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.80, "bank_cbs_health": 0.10,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": True,
                "customer_preferred_rail": "UPI", "intent_score": 0.85, "time_since_failure_sec": 10,
                "is_terminal_failure": False
            }
        }
        # Bank down with abandoned session -> cannot pop modal; must queue mandate or async link
        tx_abandoned = {
            "transaction_id": "tx_adv_abandoned", "amount": 1000, "currency": "INR",
            "error_code": "BANK_CBS_DOWN", "failure_category": "BANK_DOWNTIME",
            "initial_retry_count": 0,
            "context": {
                "session_active": False, "secondary_pg_health": 0.80, "bank_cbs_health": 0.10,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": True,
                "customer_preferred_rail": "UPI", "intent_score": 0.85, "time_since_failure_sec": 75,
                "is_terminal_failure": False
            }
        }
        res_active = AutonomousRecoveryPipeline(tx_active).run_lifecycle()
        res_abandoned = AutonomousRecoveryPipeline(tx_abandoned).run_lifecycle()
        
        self.assertEqual(res_active["lifecycle_trace"][0]["action_executed"], "TRIGGER_CROSS_RAIL_UPI")
        self.assertEqual(res_abandoned["lifecycle_trace"][0]["action_executed"], "SCHEDULE_MANDATE_BATCH")
        print("\n[PASS] Session posture properly separates active in-checkout modal from asynchronous mandate batching.")

    def test_03_healthy_vs_degraded_alternate_gateways(self):
        """
        Adversarial Test 3: If secondary card PG is degraded (< 65%), PG switch must be rejected.
        """
        tx_healthy = {
            "transaction_id": "tx_pg_healthy", "amount": 3000, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.92, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS", "intent_score": 0.90, "time_since_failure_sec": 5, "is_terminal_failure": False
            }
        }
        tx_degraded = {
            "transaction_id": "tx_pg_degraded", "amount": 3000, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.50, # Degraded secondary PG
                "bank_cbs_health": 0.95, "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS", "intent_score": 0.90, "time_since_failure_sec": 5, "is_terminal_failure": False
            }
        }
        res_healthy = AutonomousRecoveryPipeline(tx_healthy).run_lifecycle()
        res_degraded = AutonomousRecoveryPipeline(tx_degraded).run_lifecycle()
        
        self.assertEqual(res_healthy["lifecycle_trace"][0]["action_executed"], "SWITCH_SECONDARY_PG")
        self.assertEqual(res_degraded["lifecycle_trace"][0]["action_executed"], "TRIGGER_CROSS_RAIL_UPI")
        print("\n[PASS] Degraded secondary PG switches candidate to UPI Intent.")

    def test_04_alternate_rail_available_vs_unavailable(self):
        """
        Adversarial Test 4: When issuing bank is down, if UPI intent is unavailable,
        engine must fall back to mandate or declare exhausted.
        """
        # Bank CBS down, UPI available
        tx_upi_avail = {
            "transaction_id": "tx_rail_avail", "amount": 2000, "currency": "INR",
            "error_code": "BANK_CBS_DOWN", "failure_category": "BANK_DOWNTIME", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.90, "bank_cbs_health": 0.10,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "UPI", "intent_score": 0.90, "time_since_failure_sec": 10, "is_terminal_failure": False
            }
        }
        # Bank CBS down, UPI UNAVAILABLE, no mandate, session active
        tx_no_rail = {
            "transaction_id": "tx_no_rail", "amount": 2000, "currency": "INR",
            "error_code": "BANK_CBS_DOWN", "failure_category": "BANK_DOWNTIME", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.90, "bank_cbs_health": 0.10,
                "customer_upi_intent_supported": False, # UPI unavailable
                "customer_has_saved_mandate": False, "customer_preferred_rail": "CARDS",
                "intent_score": 0.90, "time_since_failure_sec": 10, "is_terminal_failure": False
            }
        }
        res_avail = AutonomousRecoveryPipeline(tx_upi_avail).run_lifecycle()
        res_no_rail = AutonomousRecoveryPipeline(tx_no_rail).run_lifecycle()
        
        self.assertEqual(res_avail["lifecycle_trace"][0]["action_executed"], "TRIGGER_CROSS_RAIL_UPI")
        self.assertEqual(res_no_rail["final_status"], "EXHAUSTED_NO_VIABLE_STRATEGIES")
        print("\n[PASS] Engine respects rail availability and halts when no alternate rail exists.")

    def test_05_customer_previous_rail_affinity(self):
        """
        Adversarial Test 5: Preferred rail affinity breaks ties and boosts confidence.
        """
        # When both PG switch and UPI are viable on infrastructure timeout:
        tx_card_pref = {
            "transaction_id": "tx_card_pref", "amount": 1500, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.92, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS", "intent_score": 0.90, "time_since_failure_sec": 5, "is_terminal_failure": False
            }
        }
        tx_upi_pref = {
            "transaction_id": "tx_upi_pref", "amount": 1500, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.75, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "UPI", "intent_score": 0.90, "time_since_failure_sec": 5, "is_terminal_failure": False
            }
        }
        res_card = AutonomousRecoveryPipeline(tx_card_pref).run_lifecycle()
        res_upi = AutonomousRecoveryPipeline(tx_upi_pref).run_lifecycle()
        
        self.assertEqual(res_card["lifecycle_trace"][0]["action_executed"], "SWITCH_SECONDARY_PG")
        self.assertEqual(res_upi["lifecycle_trace"][0]["action_executed"], "TRIGGER_CROSS_RAIL_UPI")
        print("\n[PASS] Customer rail affinity correctly steers recovery selection.")

    def test_06_economic_guardrail_suppression_low_vs_high_value(self):
        """
        Adversarial Test 6: Verify economic guardrail suppresses low ticket / low EV
        attempts while approving high ticket attempts.
        """
        # Low ticket (INR 49) with degraded intent -> EV is negative (less than routing fee INR 18)
        tx_micro = {
            "transaction_id": "tx_micro_ev", "amount": 49, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": False, "secondary_pg_health": 0.40, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "UPI", "intent_score": 0.25, "time_since_failure_sec": 120, "is_terminal_failure": False
            }
        }
        # Same degraded intent, but high value (INR 5000) -> EV is comfortably positive
        tx_macro = {
            "transaction_id": "tx_macro_ev", "amount": 5000, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": False, "secondary_pg_health": 0.40, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "UPI", "intent_score": 0.25, "time_since_failure_sec": 120, "is_terminal_failure": False
            }
        }
        res_micro = AutonomousRecoveryPipeline(tx_micro).run_lifecycle()
        res_macro = AutonomousRecoveryPipeline(tx_macro).run_lifecycle()
        
        self.assertEqual(res_micro["final_status"], "SUPPRESSED_NEGATIVE_EV")
        self.assertNotEqual(res_macro["final_status"], "SUPPRESSED_NEGATIVE_EV")
        print(f"\n[PASS] Economic guardrail suppressed INR 49 order (EV <= 0) but approved INR 5000 order.")

    def test_07_terminal_security_failure_zero_retry(self):
        """
        Adversarial Test 7: Terminal fraud / stolen card blocks must NEVER be retried.
        """
        tx = {
            "transaction_id": "tx_term", "amount": 12000, "currency": "INR",
            "error_code": "CARD_BLOCKED_OR_STOLEN", "failure_category": "TERMINAL_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.95, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS", "intent_score": 0.50, "time_since_failure_sec": 5, "is_terminal_failure": True
            }
        }
        res = AutonomousRecoveryPipeline(tx).run_lifecycle()
        self.assertEqual(res["final_status"], "SUPPRESSED_TERMINAL_FAILURE")
        self.assertEqual(res["total_attempts"], 0)
        print("\n[PASS] Terminal security block immediately halted.")

    def test_08_max_retry_circuit_breaker(self):
        """
        Adversarial Test 8: Transactions with initial retries >= 3 are halted immediately.
        """
        tx = {
            "transaction_id": "tx_circuit", "amount": 5000, "currency": "INR",
            "error_code": "BANK_CBS_DOWN", "failure_category": "BANK_DOWNTIME", "initial_retry_count": 3,
            "context": {
                "session_active": True, "secondary_pg_health": 0.95, "bank_cbs_health": 0.20,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "UPI", "intent_score": 0.90, "time_since_failure_sec": 10, "is_terminal_failure": False
            }
        }
        res = AutonomousRecoveryPipeline(tx).run_lifecycle()
        self.assertEqual(res["final_status"], "CIRCUIT_BROKEN_MAX_RETRIES")
        self.assertEqual(res["total_attempts"], 0)
        print("\n[PASS] Policy max-retry circuit breaker enforced.")

    @patch("agent.execute_downstream_action")
    def test_09_primary_recovery_succeeds_single_hop(self, mock_exec):
        """
        Adversarial Test 9: Successful execution terminates on Hop 1 and credits GMV.
        """
        mock_exec.return_value = (True, "SECONDARY_PG_200_OK")
        tx = {
            "transaction_id": "tx_single_hop", "amount": 1499, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.92, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS", "intent_score": 0.90, "time_since_failure_sec": 5, "is_terminal_failure": False
            }
        }
        res = AutonomousRecoveryPipeline(tx).run_lifecycle()
        self.assertEqual(res["final_status"], "RECOVERED")
        self.assertEqual(res["total_attempts"], 1)
        self.assertEqual(res["recovered_revenue"], 1499)
        print("\n[PASS] Single-hop recovery terminates immediately on success.")

    @patch("agent.execute_downstream_action")
    def test_10_primary_fails_reassessment_different_fallback_succeeds(self, mock_exec):
        """
        Adversarial Test 10: Primary action fails in Hop 1; state reassessment mutates
        context, excludes failed action, and successfully recovers in Hop 2.
        """
        # Hop 1 fails (Secondary PG timeout); Hop 2 succeeds (Async Link paid)
        mock_exec.side_effect = [
            (False, "SECONDARY_PG_504_GATEWAY_TIMEOUT"),
            (True, "ASYNC_LINK_PAID_SUCCESS")
        ]
        tx = {
            "transaction_id": "tx_reassess", "amount": 3500, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.85, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS", "intent_score": 0.85, "time_since_failure_sec": 10, "is_terminal_failure": False
            }
        }
        res = AutonomousRecoveryPipeline(tx).run_lifecycle()
        hop_1 = res["lifecycle_trace"][0]
        hop_2 = res["lifecycle_trace"][2]
        
        self.assertEqual(hop_1["action_executed"], "SWITCH_SECONDARY_PG")
        self.assertFalse(hop_1["success"])
        self.assertEqual(hop_2["action_executed"], "DISPATCH_ASYNC_RECOVERY_LINK")
        self.assertTrue(hop_2["success"])
        self.assertEqual(res["final_status"], "RECOVERED")
        print("\n[PASS] Hop 1 failure triggered context mutation and successful Hop 2 fallback.")

    @patch("agent.execute_downstream_action")
    def test_11_duplicate_strategy_prevention(self, mock_exec):
        """
        Adversarial Test 11: A strategy attempted in Hop 1 can NEVER be selected in Hop 2.
        """
        mock_exec.side_effect = [
            (False, "SECONDARY_PG_504_GATEWAY_TIMEOUT"),
            (False, "ASYNC_LINK_EXPIRED_NO_ACTION")
        ]
        tx = {
            "transaction_id": "tx_no_dupes", "amount": 2500, "currency": "INR",
            "error_code": "GATEWAY_TIMEOUT", "failure_category": "INFRASTRUCTURE_FAILURE", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.85, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS", "intent_score": 0.80, "time_since_failure_sec": 10, "is_terminal_failure": False
            }
        }
        pipe = AutonomousRecoveryPipeline(tx)
        res = pipe.run_lifecycle()
        
        actions_executed = [t["action_executed"] for t in res["lifecycle_trace"] if "action_executed" in t]
        self.assertEqual(len(actions_executed), len(set(actions_executed)), "Duplicate action was executed in lifecycle!")
        print("\n[PASS] Strict duplicate strategy prevention verified across multi-hop lifecycle.")

    @patch("agent.execute_downstream_action")
    def test_12_bounded_max_hops_termination(self, mock_exec):
        """
        Adversarial Test 12: Ensure pipeline never loops beyond MAX_HOPS (2) and stops cleanly.
        """
        mock_exec.return_value = (False, "MOCK_PERSISTENT_DOWNSTREAM_DECLINE")
        tx = {
            "transaction_id": "tx_bounded_hops", "amount": 2500, "currency": "INR",
            "error_code": "AUTHENTICATION_FAILED", "failure_category": "USER_FRICTION", "initial_retry_count": 0,
            "context": {
                "session_active": True, "secondary_pg_health": 0.90, "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True, "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS", "intent_score": 0.85, "time_since_failure_sec": 10, "is_terminal_failure": False
            }
        }
        pipe = AutonomousRecoveryPipeline(tx)
        res = pipe.run_lifecycle()
        
        self.assertLessEqual(res["total_attempts"], 2)
        self.assertEqual(res["final_status"], "ABANDONED_AFTER_MAX_HOPS")
        self.assertEqual(res["recovered_revenue"], 0)
        print("\n[PASS] Bounded execution terminated cleanly at max hops without infinite loop.")

    def test_13_shared_batch_baseline_vs_contextual(self):
        """
        Adversarial Test 13: Exact same batch evaluated by both Baseline and Contextual engines.
        """
        with open("data/failed_batch.json", "r") as f:
            batch = json.load(f)
            
        base_res = run_baseline_evaluation(batch)
        self.assertGreaterEqual(base_res["attempts"], 80)
        self.assertGreater(base_res["penalties"], 0, "Baseline failed to incur penalties on dead rails!")
        
        contextual_recoveries = 0
        for tx in batch:
            res = AutonomousRecoveryPipeline(tx).run_lifecycle()
            if res["final_status"] == "RECOVERED":
                contextual_recoveries += 1
                
        self.assertGreater(contextual_recoveries, base_res["recoveries"])
        print(f"\n[PASS] Batch parity verified: Baseline recoveries: {base_res['recoveries']} vs Contextual: {contextual_recoveries}")


if __name__ == "__main__":
    unittest.main()
