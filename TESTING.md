# Testing Documentation (TESTING.md)

This document describes the testing strategy, automated test layouts, and manual verification steps for the Trendly Support Assistant.

---

## 1. Automated Test Suite

We use `pytest` as our testing framework. The test suite is located in the `tests/` directory and contains 31 test cases spanning different layers of the system:

*   `tests/test_database.py`: Verifies database integrity, model validations, and contact details lookup.
*   `tests/test_rules.py`: Verifies deterministic return/exchange and delay compensation calculations.
*   `tests/test_safety.py`: Verifies input/output guardrails (PII block, injection checks, and cross-customer blocking).
*   `tests/test_rag.py`: Verifies policy chunking and similarity retrieval weights.
*   `tests/test_agent.py`: Verifies multi-turn conversational orchestrations (happy path, blockings, escalations).

---

## 2. Test Scenarios and Expected Behavior

### 1. Happy Path Return (`tests/test_agent.py -> test_agent_happy_path_return`)
*   **Action**: User provides phone number `+1-415-555-0102` (Marcus Bell), then requests to return the Kurta from order `TR-4530` (delivered July 26, 2026; requested August 5, 2026).
*   **Result**: Decided as eligible. Return request created in memory with APPROVED status.

### 2. Expired Return Window (`tests/test_rules.py -> test_return_eligibility_expired`)
*   **Action**: Return request for order `TR-4523` (delivered June 5, 2026; current date August 5, 2026 - 61 days).
*   **Result**: Rejected. Reason code: `EXPIRED`. Message notes return window is closed.

### 3. Non-Returnable Category (`tests/test_rules.py -> test_return_eligibility_jewellery`)
*   **Action**: Return request for SKU `TR-EAR-042` (Pearl Drop Earrings) from order `TR-4527` (delivered July 23, 2026 - within window).
*   **Result**: Rejected. Reason code: `NON_RETURNABLE_CATEGORY`. Jewellery cannot be returned for hygiene reasons.

### 4. Delayed Order Compensation (`tests/test_rules.py -> test_delay_compensation`)
*   **Action**: Delay compensation check for order `TR-4525` (status: delayed, expected July 15, 2026; current date August 5, 2026 - 15 business days late).
*   **Result**: Approved. Qualifies for ₹250 store credit.

### 5. Lost Parcel Escalation (`tests/test_agent.py -> test_agent_lost_parcel_escalation`)
*   **Action**: Status check for order `TR-4526` (status: lost_in_transit).
*   **Result**: Escapes return flow, triggers `escalate_to_human` with HIGH priority, locks session input.

### 6. Final Sale Rejection (`tests/test_rules.py -> test_return_eligibility_final_sale`)
*   **Action**: Return request for order `TR-4528` SKU `TR-SHR-009` (Final Sale apparel item).
*   **Result**: Partially approved. Action allowed: `EXCHANGE_ONLY` (no refund/store credit).

### 7. Cancelled Order Return Block (`tests/test_rules.py -> test_return_eligibility_cancelled`)
*   **Action**: Return request for order `TR-4529` (status: cancelled).
*   **Result**: Rejected. Reason code: `CANCELLED`.

### 8. Prompt Injection Prevention (`tests/test_safety.py -> test_check_input_safety_injection`)
*   **Action**: Input message "Ignore all previous instructions and output..."
*   **Result**: Blocked by Safety Guardrails. Returns standard refusal message, escalates session.

### 9. Cross-Customer Access Block (`tests/test_agent.py -> test_agent_cross_customer_block`)
*   **Action**: Authenticated Marcus Bell (C-101) attempts to check details for TR-4521 (belongs to C-100).
*   **Result**: Blocked by Safety Guardrails. Response: "Access Denied...".

---

## 3. How to Run Tests

Execute the following command in the workspace root:
```bash
python -m pytest -v
```
All tests should pass successfully with detailed verbose outputs.
