import json
import os
import random

def generate_failed_batch(num_transactions=50, seed=42):
    random.seed(seed)
    
    # 8 Scenario Archetypes with realistic domain context
    # Each scenario defines failure semantics and realistic initial environmental signals
    scenario_archetypes = [
        # Scenario 1: Primary Gateway Timeout - Active Checkout, Secondary PG Healthy
        {
            "error_code": "GATEWAY_TIMEOUT",
            "category": "INFRASTRUCTURE_FAILURE",
            "description": "Primary PG upstream connection timeout (HTTP 504)",
            "context_builder": lambda: {
                "session_active": True,
                "secondary_pg_health": round(random.uniform(0.85, 0.98), 2),
                "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True,
                "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS",
                "intent_score": round(random.uniform(0.80, 0.95), 2),
                "time_since_failure_sec": random.randint(3, 12),
                "is_terminal_failure": False
            }
        },
        # Scenario 2: Primary Gateway Timeout - Session Abandoned, Secondary PG Degraded
        {
            "error_code": "GATEWAY_TIMEOUT",
            "category": "INFRASTRUCTURE_FAILURE",
            "description": "Primary PG upstream connection timeout; user closed checkout window",
            "context_builder": lambda: {
                "session_active": False,
                "secondary_pg_health": round(random.uniform(0.30, 0.55), 2), # Degraded secondary
                "bank_cbs_health": 0.90,
                "customer_upi_intent_supported": True,
                "customer_has_saved_mandate": False,
                "customer_preferred_rail": "UPI",
                "intent_score": round(random.uniform(0.30, 0.75), 2),
                "time_since_failure_sec": random.randint(60, 150),
                "is_terminal_failure": False
            }
        },
        # Scenario 3: Bank CBS Down - Active Checkout, Cross-Rail UPI Intent Available
        {
            "error_code": "BANK_CBS_DOWN",
            "category": "BANK_DOWNTIME",
            "description": "Issuing bank Core Banking System unresponsive (ISO 91)",
            "context_builder": lambda: {
                "session_active": True,
                "secondary_pg_health": 0.90,
                "bank_cbs_health": 0.15, # Hard CBS outage
                "customer_upi_intent_supported": True,
                "customer_has_saved_mandate": False,
                "customer_preferred_rail": "UPI",
                "intent_score": round(random.uniform(0.85, 0.98), 2),
                "time_since_failure_sec": random.randint(5, 20),
                "is_terminal_failure": False
            }
        },
        # Scenario 4: Bank CBS Down - Inactive Session, Saved Mandate on File
        {
            "error_code": "BANK_CBS_DOWN",
            "category": "BANK_DOWNTIME",
            "description": "Issuing bank CBS offline during subscription auto-debit",
            "context_builder": lambda: {
                "session_active": False,
                "secondary_pg_health": 0.85,
                "bank_cbs_health": 0.10,
                "customer_upi_intent_supported": False,
                "customer_has_saved_mandate": True,
                "customer_preferred_rail": "NETBANKING",
                "intent_score": 0.60,
                "time_since_failure_sec": random.randint(45, 180),
                "is_terminal_failure": False
            }
        },
        # Scenario 5: Insufficient Funds - Saved Autopay Mandate Available
        {
            "error_code": "INSUFFICIENT_FUNDS",
            "category": "LIQUIDITY_LIMIT",
            "description": "Customer balance below transaction total (ISO 51)",
            "context_builder": lambda: {
                "session_active": False,
                "secondary_pg_health": 0.95,
                "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True,
                "customer_has_saved_mandate": True,
                "customer_preferred_rail": "CARDS",
                "intent_score": 0.65,
                "time_since_failure_sec": random.randint(30, 90),
                "is_terminal_failure": False
            }
        },
        # Scenario 6: Insufficient Funds - No Mandate, Active In-Checkout Session
        {
            "error_code": "INSUFFICIENT_FUNDS",
            "category": "LIQUIDITY_LIMIT",
            "description": "Customer debit card declined for balance; user still in modal",
            "context_builder": lambda: {
                "session_active": True,
                "secondary_pg_health": 0.95,
                "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True,
                "customer_has_saved_mandate": False,
                "customer_preferred_rail": "UPI",
                "intent_score": round(random.uniform(0.75, 0.90), 2),
                "time_since_failure_sec": random.randint(4, 15),
                "is_terminal_failure": False
            }
        },
        # Scenario 7: Authentication Friction - 3DS OTP Dropped / Timeout
        {
            "error_code": "AUTHENTICATION_FAILED",
            "category": "USER_FRICTION",
            "description": "3DS OTP challenge abandoned or expired during ACS redirect",
            "context_builder": lambda: {
                "session_active": random.choice([True, False]),
                "secondary_pg_health": 0.92,
                "bank_cbs_health": 0.92,
                "customer_upi_intent_supported": True,
                "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS",
                "intent_score": round(random.uniform(0.80, 0.95), 2),
                "time_since_failure_sec": random.randint(15, 60),
                "is_terminal_failure": False
            }
        },
        # Scenario 8: Terminal Security Block - Stolen / Restricted Card
        {
            "error_code": "CARD_BLOCKED_OR_STOLEN",
            "category": "TERMINAL_FAILURE",
            "description": "Card flagged by issuer as stolen/lost or blocked for fraud",
            "context_builder": lambda: {
                "session_active": True,
                "secondary_pg_health": 0.95,
                "bank_cbs_health": 0.95,
                "customer_upi_intent_supported": True,
                "customer_has_saved_mandate": False,
                "customer_preferred_rail": "CARDS",
                "intent_score": 0.40,
                "time_since_failure_sec": random.randint(5, 30),
                "is_terminal_failure": True
            }
        }
    ]

    banks = ["HDFC", "ICICI", "SBI", "AXIS", "KOTAK"]
    rails = ["CARDS", "UPI", "NETBANKING"]
    amounts = [299, 499, 999, 1499, 2499, 4999, 8500, 15000]

    transactions = []

    for i in range(1, num_transactions + 1):
        archetype = scenario_archetypes[(i - 1) % len(scenario_archetypes)]
        ctx = archetype["context_builder"]()
        
        # Inject occasional edge cases:
        # e.g., prior attempts already near limit
        initial_retries = 3 if i % 13 == 0 else (1 if i % 4 == 0 else 0)
        
        # Low value micro-transaction to test economic guardrails
        amount = 49 if i % 17 == 0 else random.choice(amounts)

        transactions.append({
            "transaction_id": f"txn_fail_{1000 + i}",
            "user_id": f"cust_{random.randint(500, 900)}",
            "amount": amount,
            "currency": "INR",
            "primary_rail": random.choice(rails),
            "issuing_bank": random.choice(banks),
            "error_code": archetype["error_code"],
            "failure_category": archetype["category"],
            "error_description": archetype["description"],
            "initial_retry_count": initial_retries,
            "context": ctx,
            "timestamp": "2026-09-05T10:30:00Z"
        })

    os.makedirs("data", exist_ok=True)
    with open("data/failed_batch.json", "w") as f:
        json.dump(transactions, f, indent=2)

    print(f"Generated {len(transactions)} scenario-driven, context-rich transactions in data/failed_batch.json")
    return transactions

if __name__ == "__main__":
    generate_failed_batch()