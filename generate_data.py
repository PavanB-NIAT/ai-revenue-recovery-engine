import json
import random
import os

failure_matrix = [
    {
        "error_code": "GATEWAY_TIMEOUT",
        "category": "INFRASTRUCTURE_FAILURE",
        "description": "Primary PG upstream connection timeout",
        "recommended_fallback": "SECONDARY_PG_SWITCH"
    },
    {
        "error_code": "BANK_SERVER_DOWN",
        "category": "BANK_DOWNTIME",
        "description": "Issuing bank CBS unresponsive",
        "recommended_fallback": "CROSS_RAIL_UPI_COLLECT"
    },
    {
        "error_code": "INSUFFICIENT_FUNDS",
        "category": "LIQUIDITY_LIMIT",
        "description": "Customer account balance below order amount",
        "recommended_fallback": "SMART_PAYDAY_SCHEDULED_RETRY"
    },
    {
        "error_code": "AUTHENTICATION_FAILED",
        "category": "USER_FRICTION",
        "description": "3DS OTP entry timed out or dropped",
        "recommended_fallback": "WHATSAPP_INSTANT_INTENT_LINK"
    }
]

banks = ["HDFC", "ICICI", "SBI", "AXIS", "KOTAK"]
rails = ["CARDS", "UPI", "NETBANKING", "MANDATE"]

transactions = []
random.seed(42)

for i in range(1, 51):
    scenario = random.choice(failure_matrix)
    tx_id = f"txn_fail_{1000 + i}"
    amount = random.choice([399, 799, 1499, 2999, 5499, 12000])
    
    transactions.append({
        "transaction_id": tx_id,
        "merchant_id": "merch_razor_test_01",
        "user_id": f"cust_{random.randint(500, 900)}",
        "amount": amount,
        "primary_rail": random.choice(rails),
        "issuing_bank": random.choice(banks),
        "error_code": scenario["error_code"],
        "failure_category": scenario["category"],
        "error_description": scenario["description"],
        "retry_attempt": random.randint(0, 3),
        "user_cart_value": amount,
        "timestamp": "2026-09-05T10:30:00Z"
    })

os.makedirs("data", exist_ok=True)
with open("data/failed_batch.json", "w") as f:
    json.dump(transactions, f, indent=2)

print("Successfully generated 50 synthetic failed transactions in data/failed_batch.json")