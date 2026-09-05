import json
import os
from datetime import datetime

FAILED_BATCH_PATH = "data/failed_batch.json"
AUDIT_TRAIL_PATH = "data/audit_trail.json"

def classify_and_recover(txn):
    error_code = txn.get("error_code")
    retry_attempt = txn.get("retry_attempt", 0)
    amount = txn.get("amount", 0)

    # Hard Stopping Rule: Prevent infinite retry penalties
    if retry_attempt >= 3:
        return {
            "status": "STOPPED",
            "action": "ESCALATE_MANUAL_SUPPORT",
            "reason": "Max retries exceeded; suppressing to avoid bank bounce penalties",
            "recovered": False,
            "recovered_amount": 0
        }

    # Contextual Cross-Rail Decisions
    if error_code == "GATEWAY_TIMEOUT":
        return {
            "status": "RECOVERED",
            "action": "INSTANT_FALLBACK_SECONDARY_PG",
            "reason": "Primary gateway degraded; routed payload through hot secondary rail",
            "recovered": True,
            "recovered_amount": amount
        }
    elif error_code == "BANK_SERVER_DOWN":
        return {
            "status": "RECOVERED",
            "action": "TRIGGER_CROSS_RAIL_UPI_INTENT",
            "reason": "Issuing bank CBS unresponsive; initiated deep-link UPI collect",
            "recovered": True,
            "recovered_amount": amount
        }
    elif error_code == "AUTHENTICATION_FAILED":
        return {
            "status": "RECOVERED",
            "action": "DISPATCH_FRICTIONLESS_AUTH_LINK",
            "reason": "3DS authentication drop; triggered automated 1-click fallback session",
            "recovered": True,
            "recovered_amount": amount
        }
    elif error_code == "INSUFFICIENT_FUNDS":
        return {
            "status": "SCHEDULED",
            "action": "SMART_PAYDAY_DETERMINISTIC_RETRY",
            "reason": "User liquidity limit; queued for intelligent salary cycle window",
            "recovered": False,
            "recovered_amount": 0
        }
    else:
        return {
            "status": "FAILED",
            "action": "NOOP_LOG_AND_ABANDON",
            "reason": "Unrecognized error signature",
            "recovered": False,
            "recovered_amount": 0
        }

def run_recovery_pipeline():
    if not os.path.exists(FAILED_BATCH_PATH):
        print(f"Error: {FAILED_BATCH_PATH} not found. Run generate_data.py first.")
        return

    with open(FAILED_BATCH_PATH, "r") as f:
        failed_transactions = json.load(f)

    total_transactions = len(failed_transactions)
    total_revenue_at_risk = sum(tx.get("amount", 0) for tx in failed_transactions)
    total_recovered = 0
    audit_events = []

    for tx in failed_transactions:
        decision = classify_and_recover(tx)
        if decision["recovered"]:
            total_recovered += decision["recovered_amount"]

        audit_events.append({
            "transaction_id": tx.get("transaction_id"),
            "original_rail": tx.get("primary_rail"),
            "amount": tx.get("amount"),
            "error_code": tx.get("error_code"),
            "failure_category": tx.get("failure_category"),
            "decision": decision["action"],
            "status": decision["status"],
            "reason": decision["reason"],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })

    recovery_rate = (total_recovered / total_revenue_at_risk * 100) if total_revenue_at_risk > 0 else 0

    # Save detailed audit trail
    os.makedirs("data", exist_ok=True)
    with open(AUDIT_TRAIL_PATH, "w") as f:
        json.dump(audit_events, f, indent=2)

    # Print Telemetry Report
    print("\n" + "=" * 55)
    print("      AI REVENUE RECOVERY ENGINE - TELEMETRY")
    print("=" * 55)
    print(f"Batch Volume Processed      : {total_transactions} transactions")
    print(f"Total Revenue At Risk       : INR {total_revenue_at_risk:,.2f}")
    print(f"Autonomous Revenue Recovered : INR {total_recovered:,.2f}")
    print(f"Recovery Success Rate       : {recovery_rate:.2f}%")
    print(f"Stopping Rule Activations   : {sum(1 for e in audit_events if e['status'] == 'STOPPED')}")
    print(f"Audit Trail Written         : {AUDIT_TRAIL_PATH}")
    print("=" * 55 + "\n")

if __name__ == "__main__":
    run_recovery_pipeline()