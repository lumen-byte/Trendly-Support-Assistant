# Trendly Agentic Support Assistant

A production-grade, state-management-driven AI support agent and interactive dashboard built for Trendly. The system handles shipping, returns, refunds, and exchanges securely and deterministically, combining LLM orchestration with rigid rule-based business logic.

---

## Core Features

- **Dynamic Intent-Based Authentication**: Unauthenticated guest users can freely search and ask general policy questions (RAG). Any transactional query (such as looking up order details, requesting refunds, or claiming delay credits) dynamically triggers contact verification, securing customer data.
- **Deterministic Return Eligibility Engine**: All eligibility checks (30-day delivery window subtraction, hygiene category exclusions, final sale size-exchange rules, and footwear box deductions) are evaluated programmatically in pure Python. The LLM only translates these results into conversational explanations, preventing refund hallucinations.
- **Advanced Policy QA RAG Engine**: Indexes the policy document by semantic section boundaries. Uses custom cosine similarity mapping with synonym query expansion (e.g. mapping "earrings" to "jewellery") to resolve natural queries without external binary database dependencies.
- **Safety Interceptor Layer**: Scrubs incoming queries for credit cards, CVVs, and bank transfer routing codes. Filters jailbreak patterns and prompt injections, automatically locking sessions and triggering human escalation upon safety breaches.
- **Cross-Customer Data Isolation**: Enforces security boundaries by verifying that the authenticated customer ID matches the requested order ID before exposing details.
- **Interactive Live Dashboard**: A dual-panel interface displaying the active conversation alongside a developer-focused memory inspector showing variables, tool execution inputs/outputs, and active human escalation handoff cards.

---

## Quick Start

### 1. Prerequisites
Ensure you have Python 3.8+ installed on your system.

### 2. Installation
Clone the repository and install the dependencies:
```bash
pip install -r requirements.txt
```

### 3. Setup Environment
Create a .env file in the root directory (or set the environment variable directly):
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
Note: If no API key is set, the system will automatically run in a deterministic rule-based fallback planner mode, allowing you to fully inspect and test all scenarios offline.

### 4. Running the Dashboard Server
Start the FastAPI server:
```bash
python -m uvicorn app.main:app --reload --port 8000
```
Open your browser and navigate to: http://localhost:8000

### 5. Running the Test Suite
Run the extensive automated testing harness:
```bash
python -m pytest
```

---

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py                 # Global configurations & simulated date (2026-08-05)
│   ├── database.py               # Order Engine database abstraction layer
│   ├── rules.py                  # Deterministic Return Eligibility Rules Engine
│   ├── rag.py                    # RAG Policy Retrieval Engine (with query synonym expansion)
│   ├── safety.py                 # Safety Guardrails Layer (PII & injection checks)
│   ├── state.py                  # Conversation Session Memory schemas
│   ├── agent.py                  # Agent Orchestrator & Conversational Loop
│   ├── tools.py                  # Exposed Planner Tools (ownership & validation)
│   ├── prompts.py                # Isolated Jinja2 prompt templates
│   └── templates/                # Static assets/UI templates (served in app/main.py)
├── tests/
│   ├── test_database.py          # Database integrity & isolation tests
│   ├── test_rules.py             # Deterministic rules evaluation tests
│   ├── test_safety.py            # Guardrails, CC & Prompt injection tests
│   ├── test_rag.py               # Policy chunking & similarity query tests
│   └── test_agent.py             # E2E multi-turn conversational tests
├── orders.json                   # Provided Customer & Order database (Do not modify)
├── trendly_policy.md             # Provided Shipping & Returns policy doc (Source of Truth)
├── requirements.txt              # Package dependencies
├── PROMPTS.md                    # Detailed prompts & instructions documentation
├── ARCHITECTURE.md               # Visual representations & component details
├── SOLUTION.md                   # Key trade-offs, architecture choices & discovery questions
├── TESTING.md                    # Detailed test plans & verification scenarios
└── API.md                        # API endpoints & payloads documentation
```

---

## Technology Stack Selection and Rationale

1. **FastAPI & Uvicorn**: Chosen for high performance, native async capabilities, and seamless Pydantic validation (simplifies JSON request-response serialization).
2. **Pydantic**: Used for strict, declarative data modeling of database records, rules, and memory states, ensuring type safety.
3. **Google Gemini (1.5 Flash)**: High-speed, cost-efficient, and supports native JSON-mode formatting.
4. **Keyword Similarity Indexing with synonym query expansion**: Built a deterministic keyword indexer in rag.py as a fallback. It uses synonym expansion to map domain concepts (such as "earrings", "socks") to policy terms ("jewellery", "innerwear"). This provides a 100% free vector similarity search without requiring complex C++ compilation dependencies (like local FAISS or ChromaDB) which frequently fail to compile on Windows.

---

## AI Usage Note
- **AI-Generated Components**: Fast-creation of boilerplate code (FastAPI routing, Tailwind classes, and Pydantic schemas).
- **Human-Authored Components**: Core design pattern isolating the deterministic Rules Engine (rules.py) from LLM planning, custom query expansion synonym rules (rag.py), turn isolation logic using [System Tool Result] trace checks (agent.py), security context access boundaries (database.py ownership verification), and extensive E2E edge-case tests.
