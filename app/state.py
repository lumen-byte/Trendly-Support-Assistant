from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.database import Order, Customer

class ReturnRequestState(BaseModel):
    sku: str
    reason: str
    has_box: bool = True
    is_damaged: bool = False
    validation_status: Optional[str] = None # PENDING, APPROVED, REJECTED, ESCALATED
    rejection_reason: Optional[str] = None
    refund_deduction: float = 0.0

class ExchangeRequestState(BaseModel):
    sku: str
    target_size: str
    validation_status: Optional[str] = None # PENDING, APPROVED, REJECTED, ESCALATED
    rejection_reason: Optional[str] = None

class ToolExecutionTrace(BaseModel):
    tool_name: str
    inputs: Dict[str, Any]
    outputs: Any
    timestamp: str

class ConversationSession(BaseModel):
    """
    Session Memory Manager state.
    Maintains persistent structured state variables alongside chat history
    to ensure deterministic context and prevent injection-based memory wipes.
    """
    session_id: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    is_authenticated: bool = False
    
    current_order_id: Optional[str] = None
    current_return: Optional[ReturnRequestState] = None
    current_exchange: Optional[ExchangeRequestState] = None
    
    conversation_summary: str = ""
    clarification_questions: List[str] = Field(default_factory=list)
    tool_traces: List[ToolExecutionTrace] = Field(default_factory=list)
    
    escalated: bool = False
    escalation_reason: Optional[str] = None
    escalation_summary: Optional[Dict[str, Any]] = None
    
    messages: List[Dict[str, str]] = Field(default_factory=list) # List of {"role": "user"/"assistant", "content": "..."}

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def add_trace(self, tool_name: str, inputs: Dict[str, Any], outputs: Any):
        from datetime import datetime
        self.tool_traces.append(ToolExecutionTrace(
            tool_name=tool_name,
            inputs=inputs,
            outputs=outputs,
            timestamp=datetime.now().isoformat()
        ))

    def authenticate_customer(self, customer: Customer):
        self.customer_id = customer.customer_id
        self.customer_name = customer.name
        self.customer_email = customer.email
        self.customer_phone = customer.phone
        self.is_authenticated = True

    def clear_session(self):
        self.customer_id = None
        self.customer_name = None
        self.customer_email = None
        self.customer_phone = None
        self.is_authenticated = False
        self.current_order_id = None
        self.current_return = None
        self.current_exchange = None
        self.conversation_summary = ""
        self.clarification_questions.clear()
        self.tool_traces.clear()
        self.escalated = False
        self.escalation_reason = None
        self.escalation_summary = None
        self.messages.clear()
