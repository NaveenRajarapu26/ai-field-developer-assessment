"""Small in-memory business layer. No real refunds or external services."""

from typing import Any

CUSTOMERS: dict[str, dict[str, Any]] = {
    "CUST-12345": {"name": "John", "email": "john@example.com", "balance": 250.0},
    "CUST-67890": {"name": "Sarah", "email": "sarah@example.com", "balance": 500.0},
}


def get_customer_record(customer_id: str) -> dict[str, Any] | None:
    customer = CUSTOMERS.get(customer_id)
    return {"customer_id": customer_id, **customer} if customer else None


def trigger_refund(customer_id: str, amount: float, reason: str) -> dict[str, Any] | None:
    if customer_id not in CUSTOMERS:
        return None
    # No money is transferred. This function does not change customer balances.
    return {
        "status": "simulated",
        "customer_id": customer_id,
        "amount": amount,
        "reason": reason,
        "message": "Refund simulation completed; no payment was processed",
    }
