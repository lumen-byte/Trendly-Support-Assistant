# Solution Note & Discovery Questions (SOLUTION.md)

This document provides a review of the solution, architectural trade-offs, limitations, and product discovery questions.

---

## 1. Key Trade-offs

### A. Deterministic Rule Engine vs. LLM Eligibility Reasoning
*   **Approach**: All return and compensation eligibility checks are calculated in pure Python (`rules.py`), and the LLM is only used to translate these rules into conversational explanations.
*   **Trade-off**: While this reduces the LLM's flexibility to handle nuances in natural language return requests directly, it completely eliminates return eligibility hallucinations, preventing unauthorized refund approvals and securing business operations.

### B. In-Memory Session Memory vs. External Session Database (Redis)
*   **Approach**: Sessions are stored in a global dictionary `sessions_db` in `app/tools.py`.
*   **Trade-off**: This approach enables fast, zero-dependency deployment for demo testing but is not horizontally scalable. In production, this would be replaced by a Redis memory store using the same Pydantic schemas.

### C. Local Cosine/Synonym fallbacks vs. Remote Vector DB
*   **Approach**: The RAG engine implements a weighted vocabulary cosine similarity search as a fallback when offline or when no API key is present.
*   **Trade-off**: This reduces complex binary setup requirements (like native FAISS or ChromaDB compilation) for Windows reviewers, but limits context ranking capabilities on large multi-document policies. However, since the policy doc is small, this trade-off is highly optimal.

---

## 2. Known Limitations

1.  **Stateless API**: The FastAPI layer stores state in an in-memory dictionary. If the uvicorn process restarts, all conversation sessions are reset.
2.  **Size Exchanges**: Size exchanges are evaluated, but because the database does not include real-time warehouse inventory tables, we assume the requested size is available. In a production system, we would call an inventory API.
3.  **Local Time Simulation**: The system enforces `2026-08-05` as the simulated current date to align with the provided order histories (placed in June-July 2026). Real deployments would use system time.

---

## 3. Product Discovery Questions (Trendly Ops Team)

These questions focus on operational and business architecture, demonstrating product thinking:

### Q1: COD Refund Flow & Customer Handoff
> "Section 3.3 states COD refunds require bank account details which are collected by a human agent over a secure link. What specific tooling or ticketing systems (e.g. Zendesk, Salesforce) does your human support team use today? We should integrate our handoff service so the secure link is automatically generated and dispatched via SMS/email upon escalation, reducing human handling time."

### Q2: Partial Returns & Free Shipping Threshold Recalculation
> "Section 3.4 says that for partial returns, free shipping eligibility is not recalculated. However, what happens if a customer returns items that drop their original order total below the ₹1,499 free-shipping threshold? Do we charge the ₹99 shipping fee retroactively by deducting it from the refund amount? We must ensure the Rule Engine matches your financial audit guidelines."

### Q3: Replacement Inventory Lock Timeframe
> "For damaged or wrong items reported within 48 hours (Section 6), a replacement is shipped at no cost. How should the assistant handle situations where replacement inventory is out of stock? Should we automatically process a refund, reserve stock from incoming shipments, or place the request on hold in a human queue?"

### Q4: Store Credit Issuance & Expiry Policies
> "Delayed shipments qualify for a ₹250 store credit on request (Section 1.5). How are these credits managed? Do they expire, can they be combined with other discounts, and is there an API we should integrate with to issue these coupon codes dynamically into the customer's wallet?"

### Q5: Failed Pickup Threshold Actions
> "Section 5.3 states returns are closed after 2 failed pickup attempts. What is the operational protocol if a customer contests this closure due to carrier errors? Should the agent escalate immediately, or are they allowed to re-raise a return if they self-ship within the original 30-day window?"
