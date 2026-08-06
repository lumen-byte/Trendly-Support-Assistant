import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.agent import AgentOrchestrator
from app.tools import get_or_create_session, sessions_db
from app.state import ConversationSession

app = FastAPI(
    title="Trendly Support Assistant API",
    description="Production-grade Agentic Support Assistant Backend",
    version="1.0.0"
)

# Enable CORS for local testing/frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Orchestrator once
orchestrator = AgentOrchestrator()

# Pydantic Schemas for API
class ChatRequest(BaseModel):
    session_id: str
    message: str

class SessionResponse(BaseModel):
    session_id: str
    customer_id: Optional[str]
    customer_name: Optional[str]
    customer_email: Optional[str]
    customer_phone: Optional[str]
    is_authenticated: bool
    current_order_id: Optional[str]
    current_return: Optional[Dict[str, Any]]
    current_exchange: Optional[Dict[str, Any]]
    conversation_summary: str
    escalated: bool
    escalation_reason: Optional[str]
    escalation_summary: Optional[Dict[str, Any]]
    messages: List[Dict[str, str]]
    tool_traces: List[Dict[str, Any]]
    llm_active: bool  # Exposes the orchestration mode (Gemini vs Fallback)

class ChatResponse(BaseModel):
    response: str
    session: SessionResponse

def _format_session_response(session: ConversationSession) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        customer_id=session.customer_id,
        customer_name=session.customer_name,
        customer_email=session.customer_email,
        customer_phone=session.customer_phone,
        is_authenticated=session.is_authenticated,
        current_order_id=session.current_order_id,
        current_return=session.current_return.dict() if session.current_return else None,
        current_exchange=session.current_exchange.dict() if session.current_exchange else None,
        conversation_summary=session.conversation_summary,
        escalated=session.escalated,
        escalation_reason=session.escalation_reason,
        escalation_summary=session.escalation_summary,
        messages=session.messages,
        tool_traces=[t.dict() for t in session.tool_traces],
        llm_active=orchestrator.use_api
    )

# REST API Endpoints

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Process a new message within a session.
    Returns the agent response and the updated session memory state.
    """
    if not request.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required.")
        
    try:
        response_text = orchestrator.process_message(request.session_id, request.message)
        session = get_or_create_session(request.session_id)
        return ChatResponse(
            response=response_text,
            session=_format_session_response(session)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Orchestrator Error: {str(e)}")

@app.get("/api/session/{session_id}", response_model=SessionResponse)
async def get_session_endpoint(session_id: str):
    """
    Retrieve the current memory/state variables for a given session.
    """
    session = get_or_create_session(session_id)
    return _format_session_response(session)

@app.post("/api/session/{session_id}/clear")
async def clear_session_endpoint(session_id: str):
    """
    Reset and clear the memory state for a given session.
    """
    session = get_or_create_session(session_id)
    session.clear_session()
    return {"status": "SUCCESS", "message": f"Session {session_id} has been reset."}

@app.get("/api/escalations")
async def get_escalations_endpoint():
    """
    Retrieve list of all active human escalations across all active sessions.
    This acts as the agent handoff dashboard.
    """
    escalations = []
    for s_id, session in sessions_db.items():
        if session.escalated:
            escalations.append({
                "session_id": s_id,
                "customer_name": session.customer_name,
                "customer_email": session.customer_email,
                "escalation_reason": session.escalation_reason,
                "summary": session.escalation_summary,
                "timestamp": session.tool_traces[-1].timestamp if session.tool_traces else None
            })
    return {"success": True, "escalations": escalations}

# HTML Dashboard UI

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """
    Serve the interactive support agent dashboard.
    Shows the chat window, live memory manager values, system trace logs, and human escalations queue.
    """
    # Embedded HTML for clean self-containment
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trendly Agentic Support Dashboard</title>
    <!-- Google Fonts Outfit -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <!-- Tailwind CSS (Direct CDN) -->
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {
            font-family: 'Outfit', sans-serif;
            background: linear-gradient(135deg, #0b0f19 0%, #111827 100%);
        }
        .glass-panel {
            background: rgba(17, 24, 39, 0.7);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        ::-webkit-scrollbar {
            width: 6px;
        }
        ::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.2);
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }
    </style>
</head>
<body class="text-gray-100 min-h-screen flex flex-col">
    <!-- Header -->
    <header class="w-full py-4 px-6 glass-panel border-b border-gray-800 flex justify-between items-center shadow-lg">
        <div class="flex items-center space-x-3">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-yellow-400 via-orange-500 to-red-500 flex items-center justify-center font-bold text-xl shadow-md text-white">T</div>
            <div>
                <h1 class="text-xl font-bold tracking-tight text-white flex items-center">
                    Trendly Support Assistant
                    <span id="agent-mode-badge" class="ml-3"></span>
                </h1>
                <p class="text-xs text-gray-400">FDE Assessment - Production Grade Architecture Demonstration</p>
            </div>
        </div>
        <div class="flex items-center space-x-5">
            <!-- Simulated Date Badge -->
            <div class="hidden sm:flex items-center space-x-2 bg-gray-900/60 border border-gray-800 px-3 py-1.5 rounded-xl text-xs text-gray-300">
                <span class="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></span>
                <span>Simulated System Date: <strong>2026-08-05</strong></span>
            </div>
            <!-- Session Switcher -->
            <div class="flex items-center space-x-2 bg-gray-900/60 border border-gray-850 px-3 py-1.5 rounded-xl">
                <span class="text-xs text-gray-400">Session ID:</span>
                <input type="text" id="session-input" value="trendly-web-demo" onchange="changeSession(this.value)" 
                       class="bg-gray-950 border border-gray-800 rounded-lg px-2 py-0.5 text-xs text-yellow-400 font-bold focus:outline-none focus:border-yellow-500/80 w-32 text-center">
            </div>
            <button onclick="resetSession()" class="px-3 py-1.5 rounded-lg border border-gray-700 hover:border-red-500 hover:text-red-400 text-xs transition duration-200 bg-gray-900/40">Reset State</button>
        </div>
    </header>

    <!-- Main Content Grid -->
    <main class="flex-1 grid grid-cols-1 lg:grid-cols-3 p-6 gap-6 max-w-7xl mx-auto w-full overflow-hidden">
        
        <!-- Left Panel: Session Memory State & Test Cases -->
        <section class="glass-panel rounded-2xl p-5 flex flex-col space-y-4 shadow-xl overflow-y-auto max-h-[82vh]">
            <h2 class="text-md font-semibold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2">Active Memory State</h2>
            
            <!-- Auth Status -->
            <div class="bg-gray-900/60 p-4 rounded-xl border border-gray-800 space-y-3">
                <div class="flex justify-between items-center">
                    <span class="text-xs text-gray-400 uppercase tracking-wider font-medium">Authentication</span>
                    <span id="state-auth" class="text-xs font-semibold px-2 py-0.5 rounded bg-red-500/20 text-red-400 font-mono">UNAUTHENTICATED</span>
                </div>
                <div class="space-y-1.5">
                    <div class="flex justify-between text-xs"><span class="text-gray-400">Customer ID:</span><span id="state-cust-id" class="text-gray-200">-</span></div>
                    <div class="flex justify-between text-xs"><span class="text-gray-400">Name:</span><span id="state-cust-name" class="text-gray-200 font-semibold">-</span></div>
                    <div class="flex justify-between text-xs"><span class="text-gray-400">Email:</span><span id="state-cust-email" class="text-gray-200 font-mono">-</span></div>
                    <div class="flex justify-between text-xs"><span class="text-gray-400">Phone:</span><span id="state-cust-phone" class="text-gray-200 font-mono">-</span></div>
                </div>
            </div>

            <!-- Context variables -->
            <div class="bg-gray-900/60 p-4 rounded-xl border border-gray-800 space-y-3">
                <span class="text-xs text-gray-400 uppercase tracking-wider font-medium block">Context Variables</span>
                <div class="space-y-2">
                    <div class="flex justify-between text-xs"><span class="text-gray-400">Current Order ID:</span><span id="state-order-id" class="text-yellow-400 font-mono font-semibold">-</span></div>
                    
                    <div class="border-t border-gray-800/80 pt-2">
                        <span class="text-[10px] text-gray-400 font-medium block mb-1">Return State</span>
                        <div id="state-return-details" class="text-xs text-gray-300 bg-gray-950/40 p-2.5 rounded border border-gray-800/50">None</div>
                    </div>
                </div>
            </div>

            <!-- Escalation Details -->
            <div id="escalation-panel" class="bg-gray-900/60 p-4 rounded-xl border border-red-900/40 space-y-2 hidden">
                <span class="text-xs text-red-400 uppercase tracking-wider font-semibold flex items-center">
                    <span class="w-2 h-2 bg-red-500 rounded-full mr-2 animate-ping"></span>
                    Escalated to Human Agent
                </span>
                <div id="escalation-details" class="text-xs text-gray-300 space-y-1"></div>
            </div>

            <!-- Test Cases quick lookup -->
            <div class="bg-gray-900/60 p-4 rounded-xl border border-gray-800 space-y-3">
                <span class="text-xs text-gray-400 uppercase tracking-wider font-medium block">Test Case Database Quick-Click</span>
                <p class="text-[10px] text-gray-500">Click any order ID to automatically insert it into the chat input field.</p>
                <div class="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
                    <div onclick="selectOrder('TR-4521')" class="p-2 bg-gray-950/45 rounded border border-gray-850 hover:border-yellow-500/50 cursor-pointer transition flex justify-between items-center text-xs">
                        <span>TR-4521 (Ananya)</span>
                        <span class="px-1.5 py-0.5 text-[9px] rounded bg-blue-500/20 text-blue-400 font-semibold uppercase">In Transit</span>
                    </div>
                    <div onclick="selectOrder('TR-4530')" class="p-2 bg-gray-950/45 rounded border border-gray-850 hover:border-yellow-500/50 cursor-pointer transition flex justify-between items-center text-xs">
                        <span>TR-4530 (Marcus)</span>
                        <span class="px-1.5 py-0.5 text-[9px] rounded bg-green-500/20 text-green-400 font-semibold uppercase">Happy Return</span>
                    </div>
                    <div onclick="selectOrder('TR-4526')" class="p-2 bg-gray-950/45 rounded border border-gray-850 hover:border-yellow-500/50 cursor-pointer transition flex justify-between items-center text-xs">
                        <span>TR-4526 (Marcus)</span>
                        <span class="px-1.5 py-0.5 text-[9px] rounded bg-red-500/20 text-red-400 font-semibold uppercase font-mono">Lost parcel</span>
                    </div>
                    <div onclick="selectOrder('TR-4527')" class="p-2 bg-gray-950/45 rounded border border-gray-850 hover:border-yellow-500/50 cursor-pointer transition flex justify-between items-center text-xs">
                        <span>TR-4527 (Priya)</span>
                        <span class="px-1.5 py-0.5 text-[9px] rounded bg-orange-500/20 text-orange-400 font-semibold uppercase">Jewellery</span>
                    </div>
                    <div onclick="selectOrder('TR-4528')" class="p-2 bg-gray-950/45 rounded border border-gray-850 hover:border-yellow-500/50 cursor-pointer transition flex justify-between items-center text-xs">
                        <span>TR-4528 (Diego)</span>
                        <span class="px-1.5 py-0.5 text-[9px] rounded bg-purple-500/20 text-purple-400 font-semibold uppercase">Final Sale</span>
                    </div>
                    <div onclick="selectOrder('TR-4523')" class="p-2 bg-gray-950/45 rounded border border-gray-850 hover:border-yellow-500/50 cursor-pointer transition flex justify-between items-center text-xs">
                        <span>TR-4523 (Priya)</span>
                        <span class="px-1.5 py-0.5 text-[9px] rounded bg-gray-500/20 text-gray-400 font-semibold uppercase">Expired window</span>
                    </div>
                    <div onclick="selectOrder('TR-4525')" class="p-2 bg-gray-950/45 rounded border border-gray-850 hover:border-yellow-500/50 cursor-pointer transition flex justify-between items-center text-xs">
                        <span>TR-4525 (Diego)</span>
                        <span class="px-1.5 py-0.5 text-[9px] rounded bg-yellow-500/20 text-yellow-400 font-semibold uppercase">Delayed Order</span>
                    </div>
                </div>
            </div>
        </section>

        <!-- Middle Panel: Chat Interface -->
        <section class="lg:col-span-2 glass-panel rounded-2xl flex flex-col shadow-xl overflow-hidden min-h-[500px]">
            <!-- Chat Header -->
            <div class="px-5 py-4 border-b border-gray-800 flex justify-between items-center bg-gray-900/30">
                <span class="text-sm font-semibold tracking-wider text-gray-300">CONVERSATION</span>
                <div class="flex items-center space-x-2">
                    <span id="ping-indicator" class="w-2.5 h-2.5 rounded-full bg-green-500"></span>
                    <span class="text-xs text-gray-400">System Connected</span>
                </div>
            </div>

            <!-- Chat Message Area -->
            <div id="chat-messages" class="flex-1 p-5 overflow-y-auto space-y-4 max-h-[420px]">
                <div class="flex items-start space-x-3">
                    <div class="w-8 h-8 rounded-lg bg-gray-800 flex items-center justify-center font-bold text-sm text-yellow-500">AI</div>
                    <div class="bg-gray-800 text-gray-100 p-3 rounded-2xl rounded-tl-none max-w-[85%] text-sm leading-relaxed">
                        Hello! Welcome to Trendly Support. How can I help you with your shipping, cancellations, or return questions today?
                    </div>
                </div>
            </div>

            <!-- Input Container -->
            <div class="p-4 border-t border-gray-800 bg-gray-900/20">
                <form id="chat-form" onsubmit="sendMessage(event)" class="flex space-x-2">
                    <input type="text" id="user-input" placeholder="Type your message here (e.g., Hi, check my order status...)" 
                           class="flex-1 bg-gray-950/60 border border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-yellow-500/80 transition duration-200">
                    <button type="submit" class="bg-gradient-to-r from-yellow-400 via-orange-500 to-red-500 hover:opacity-95 text-white font-medium text-sm px-6 py-3 rounded-xl shadow-md transition duration-200">
                        Send
                    </button>
                </form>
            </div>
        </section>
        
        <!-- Bottom panel: Tool traces -->
        <section class="lg:col-span-3 glass-panel rounded-2xl p-5 shadow-xl">
            <h2 class="text-md font-semibold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 mb-3">System Execution Traces (Tool Calls & Audits)</h2>
            <div id="traces-container" class="space-y-2 max-h-[220px] overflow-y-auto text-xs font-mono text-gray-400">
                <div class="p-3 bg-gray-950/40 rounded-lg border border-gray-850">System initialized. No tools executed in this session yet.</div>
            </div>
        </section>

    </main>

    <!-- Footer -->
    <footer class="py-4 text-center text-xs text-gray-500 border-t border-gray-900 mt-auto">
        Trendly Support Engine &copy; 2026. Made with Google Gemini & FastAPI.
    </footer>

    <!-- Frontend logic -->
    <script>
        let sessionId = "trendly-web-demo";
        const messageContainer = document.getElementById("chat-messages");
        const tracesContainer = document.getElementById("traces-container");

        function selectOrder(orderId) {
            const inputField = document.getElementById("user-input");
            inputField.value = orderId;
            inputField.focus();
        }

        async function changeSession(newId) {
            const cleanId = newId.trim();
            if (!cleanId) return;
            sessionId = cleanId;
            document.getElementById("session-input").value = cleanId;
            
            // Reload context for new session ID
            try {
                const r = await fetch(`/api/session/${sessionId}`);
                const data = await r.json();
                
                // Reset chat UI and rebuild messages
                messageContainer.innerHTML = "";
                if (data.messages && data.messages.length > 0) {
                    data.messages.forEach(m => appendMessage(m.role, m.content));
                } else {
                    messageContainer.innerHTML = `
                        <div class="flex items-start space-x-3">
                            <div class="w-8 h-8 rounded-lg bg-gray-800 flex items-center justify-center font-bold text-sm text-yellow-500">AI</div>
                            <div class="bg-gray-800 text-gray-100 p-3 rounded-2xl rounded-tl-none max-w-[85%] text-sm leading-relaxed">
                                Session changed to "${sessionId}". Hello! How can I help you today?
                            </div>
                        </div>
                    `;
                }
                updateState(data);
                document.getElementById("user-input").disabled = data.escalated;
            } catch (e) {
                console.error("Error changing session", e);
            }
        }

        async function resetSession() {
            try {
                await fetch(`/api/session/${sessionId}/clear`, { method: "POST" });
                messageContainer.innerHTML = `
                    <div class="flex items-start space-x-3">
                        <div class="w-8 h-8 rounded-lg bg-gray-800 flex items-center justify-center font-bold text-sm text-yellow-500">AI</div>
                        <div class="bg-gray-800 text-gray-100 p-3 rounded-2xl rounded-tl-none max-w-[85%] text-sm leading-relaxed">
                            State reset. Hello! How can I help you today?
                        </div>
                    </div>
                `;
                updateState(null);
                document.getElementById("user-input").disabled = false;
            } catch (e) {
                console.error("Error clearing session", e);
            }
        }

        function updateState(session) {
            const modeBadge = document.getElementById("agent-mode-badge");
            
            if (!session) {
                document.getElementById("state-auth").className = "text-xs font-semibold px-2 py-0.5 rounded bg-red-500/20 text-red-400 font-mono";
                document.getElementById("state-auth").innerText = "UNAUTHENTICATED";
                document.getElementById("state-cust-id").innerText = "-";
                document.getElementById("state-cust-name").innerText = "-";
                document.getElementById("state-cust-email").innerText = "-";
                document.getElementById("state-cust-phone").innerText = "-";
                document.getElementById("state-order-id").innerText = "-";
                document.getElementById("state-return-details").innerText = "None";
                document.getElementById("escalation-panel").classList.add("hidden");
                modeBadge.className = "hidden";
                tracesContainer.innerHTML = '<div class="p-3 bg-gray-950/40 rounded-lg border border-gray-850">System initialized. No tools executed in this session yet.</div>';
                return;
            }

            // LLM Mode status badge
            modeBadge.className = "ml-3 px-2 py-0.5 text-xs rounded font-semibold uppercase tracking-wider border transition";
            if (session.llm_active) {
                modeBadge.className += " bg-purple-500/20 text-purple-400 border-purple-500/30";
                modeBadge.innerText = "Live LLM Mode";
            } else {
                modeBadge.className += " bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
                modeBadge.innerText = "Fallback Planner Mode";
            }

            // Auth update
            if (session.is_authenticated) {
                document.getElementById("state-auth").className = "text-xs font-semibold px-2 py-0.5 rounded bg-green-500/20 text-green-400 font-mono";
                document.getElementById("state-auth").innerText = "AUTHENTICATED";
                document.getElementById("state-cust-id").innerText = session.customer_id;
                document.getElementById("state-cust-name").innerText = session.customer_name;
                document.getElementById("state-cust-email").innerText = session.customer_email;
                document.getElementById("state-cust-phone").innerText = session.customer_phone;
            } else {
                document.getElementById("state-auth").className = "text-xs font-semibold px-2 py-0.5 rounded bg-red-500/20 text-red-400 font-mono";
                document.getElementById("state-auth").innerText = "UNAUTHENTICATED";
                document.getElementById("state-cust-id").innerText = "-";
                document.getElementById("state-cust-name").innerText = "-";
                document.getElementById("state-cust-email").innerText = "-";
                document.getElementById("state-cust-phone").innerText = "-";
            }

            // Context update
            document.getElementById("state-order-id").innerText = session.current_order_id || "-";
            
            if (session.current_return) {
                const ret = session.current_return;
                document.getElementById("state-return-details").innerHTML = `
                    <div class="space-y-1 text-xs">
                        <div><strong>SKU:</strong> <span class="font-mono text-yellow-500">${ret.sku}</span></div>
                        <div><strong>Status:</strong> <span class="${ret.validation_status === 'APPROVED' ? 'text-green-400' : 'text-red-400'} font-semibold">${ret.validation_status}</span></div>
                        <div><strong>Reason:</strong> ${ret.reason.replace('_', ' ')}</div>
                        ${ret.refund_deduction > 0 ? `<div class="text-orange-400"><strong>Box Deduction:</strong> \u20b9${ret.refund_deduction}</div>` : ''}
                    </div>
                `;
            } else {
                document.getElementById("state-return-details").innerText = "None";
            }

            // Escalation
            if (session.escalated) {
                document.getElementById("escalation-panel").classList.remove("hidden");
                const esc = session.escalation_summary || {};
                document.getElementById("escalation-details").innerHTML = `
                    <div class="space-y-1 text-gray-300 mt-2 bg-red-950/20 p-3 rounded-lg border border-red-900/30">
                        <div><strong>Priority:</strong> <span class="text-red-400 font-bold">${esc.priority || 'MEDIUM'}</span></div>
                        <div><strong>Reason:</strong> ${session.escalation_reason}</div>
                        <div><strong>Suggested Action:</strong> ${esc.suggested_next_step || '-'}</div>
                    </div>
                `;
                document.getElementById("user-input").disabled = true;
            } else {
                document.getElementById("escalation-panel").classList.add("hidden");
                document.getElementById("user-input").disabled = false;
            }

            // Update traces
            if (session.tool_traces && session.tool_traces.length > 0) {
                tracesContainer.innerHTML = session.tool_traces.map(t => `
                    <div class="p-3 bg-gray-950/45 rounded-lg border border-gray-800 space-y-1.5">
                        <div class="flex justify-between items-center text-gray-300">
                            <span class="text-yellow-400 font-semibold">🔧 Tool Execution: ${t.tool_name}</span>
                            <span class="text-[10px] text-gray-500 font-mono">${t.timestamp}</span>
                        </div>
                        <div class="grid grid-cols-2 gap-2 mt-1">
                            <div><span class="text-gray-500">Inputs:</span> <pre class="bg-gray-900/60 p-1.5 rounded border border-gray-800/40 text-[10px] text-gray-355 overflow-x-auto">${JSON.stringify(t.inputs, null, 2)}</pre></div>
                            <div><span class="text-gray-500">Outputs:</span> <pre class="bg-gray-900/60 p-1.5 rounded border border-gray-800/40 text-[10px] text-gray-355 overflow-x-auto">${JSON.stringify(t.outputs, null, 2)}</pre></div>
                        </div>
                    </div>
                `).reverse().join(''); // Show latest traces on top
            }
        }

        async function sendMessage(event) {
            event.preventDefault();
            const inputField = document.getElementById("user-input");
            const message = inputField.value.trim();
            if (!message) return;

            // Append User message
            appendMessage("user", message);
            inputField.value = "";

            try {
                const response = await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ session_id: sessionId, message: message })
                });
                const data = await response.json();
                
                if (data.response) {
                    appendMessage("assistant", data.response);
                }
                updateState(data.session);
            } catch (e) {
                console.error("Error sending chat", e);
                appendMessage("assistant", "Sorry, an internal connection issue occurred. Please check your console.");
            }
        }

        function appendMessage(role, text) {
            const isUser = role === "user";
            const avatar = isUser ? "U" : "AI";
            const bgClass = isUser ? "bg-gradient-to-r from-yellow-400/25 to-orange-500/25 border border-yellow-500/10 text-gray-100 rounded-tr-none" : "bg-gray-800 text-gray-100 rounded-tl-none";
            const avatarBg = isUser ? "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30" : "bg-gray-800 text-yellow-500 border border-gray-700";
            
            const messageHtml = `
                <div class="flex items-start space-x-3 ${isUser ? 'flex-row-reverse space-x-reverse' : ''}">
                    <div class="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm border ${avatarBg}">${avatar}</div>
                    <div class="${bgClass} p-3 rounded-2xl max-w-[85%] text-sm leading-relaxed white-space-pre-wrap">${text.replace(/\\n/g, '<br>')}</div>
                </div>
            `;
            messageContainer.insertAdjacentHTML("beforeend", messageHtml);
            messageContainer.scrollTop = messageContainer.scrollHeight;
        }

        // Initialize state
        fetch(`/api/session/${sessionId}`).then(r => r.json()).then(data => updateState(data));
    </script>
</body>
</html>
    """
