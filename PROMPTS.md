# Prompts Documentation (PROMPTS.md)

This document maps all prompt templates used by the Trendly Support Assistant, their objectives, inputs, constraints, and iteration history.

---

## 1. System Prompt
*   **Location**: `app/prompts.py` -> `SYSTEM_PROMPT`
*   **Objective**: Establish persona, temporal boundaries, and hard rules.
*   **Inputs**: `current_date` (Dynamic datetime context).
*   **Constraints**:
    *   No invented policies (say "I don't have enough information from the Trendly policy...").
    *   No collection of cards, CVVs, or bank details.
    *   No unauthorized credits/coupons.
    *   Strict customer-data isolation.
    *   Handoff to human for lost parcels.

---

## 2. Planner Prompt
*   **Location**: `app/prompts.py` -> `PLANNER_PROMPT`
*   **Objective**: Directs the planner agent's reasoning loop. Employs a ReAct planning loop.
*   **Inputs**:
    *   `customer_id` / Authentication status.
    *   `current_order_id` in context.
    *   `conversation_history` (Formatted list of previous turns).
    *   `user_message` (Current user query).
    *   `escalated` (Escalation state flag).
*   **Constraints**: Output MUST be a single, parseable JSON block matching the expected schema.
*   **Expected Output Schema**:
    ```json
    {
      "thought": "Reasoning about current state and missing details",
      "tool_name": "validate_customer_identity" | "lookup_customer_orders" | "get_order_details" | "calculate_return_eligibility" | "search_policy" | "claim_delay_compensation" | "escalate_to_human" | null,
      "tool_inputs": { ... },
      "clarification_needed": true | false,
      "response": "Response content if tool_name is null"
    }
    ```

---

## 3. Policy QA Prompt
*   **Location**: `app/prompts.py` -> `POLICY_QA_PROMPT`
*   **Objective**: Answers policy questions, strictly grounded in retrieved chunks.
*   **Inputs**:
    *   `retrieved_chunks` (RAG search outcomes).
    *   `conversation_history`.
    *   `query` (User query).
*   **Constraints**:
    *   Answer ONLY from retrieved text chunks.
    *   Include citations (e.g. `[Section 1.5]`).
    *   If missing details, state: "I don't have enough information from the Trendly policy. I'll connect you with a human support agent."

---

## 4. Response Generation Prompt
*   **Location**: `app/prompts.py` -> `RESPONSE_GENERATION_PROMPT`
*   **Objective**: Explains calculations and eligibility checks in consumer-friendly language.
*   **Inputs**:
    *   Customer details, current order, and return state details.
    *   `tool_results` (Output from the PolicyRulesEngine).
    *   `user_message`.
*   **Constraints**: Must match the decision computed by the `PolicyRulesEngine` (cannot override or invent eligibility exceptions). Include appropriate policy citations.

---

## 5. Escalation Summary Prompt
*   **Location**: `app/prompts.py` -> `ESCALATION_SUMMARY_PROMPT`
*   **Objective**: Computes a detailed conversation handoff card.
*   **Inputs**: Customer identity, active order, escalation reason, and history.
*   **Expected Output Schema**:
    ```json
    {
      "customer_details": "Customer info card",
      "order_details": "Active order status & items",
      "issue_summary": "Problem statement",
      "attempted_actions": "Summary of tools run by assistant",
      "suggested_next_step": "Actionable item for human agent",
      "priority": "HIGH" | "MEDIUM" | "LOW",
      "reason": "Escalation trigger"
    }
    ```

---

## 🔒 Iteration & Guardrail Notes
1.  **Jinja2 Templating**: Keeping prompt text separate from logic (`app/prompts.py`) prevents inline SQL/Python string injection and enables runtime prompt updates without redeploying code.
2.  **Structured JSON Mode**: Configured `response_mime_type: "application/json"` to ensure structural compliance, preventing LLM formatting failure.
3.  **Deterministic Interceptors**: As a secondary guardrail against jailbreaks, raw user inputs are checked for injection keywords (like "ignore limits") and CC/IFSC regex matches *before* sending them to the LLM.
