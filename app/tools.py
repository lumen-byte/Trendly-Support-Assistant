import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.config import SIMULATED_CURRENT_DATE
from app.database import OrderDatabase
from app.rules import PolicyRulesEngine
from app.rag import PolicyRetrievalEngine
from app.state import ConversationSession, ReturnRequestState, ExchangeRequestState

# Initialize engines once
db_engine = OrderDatabase()
rag_engine = PolicyRetrievalEngine()

# Session storage (In-memory dict for demo/production FastAPI)
# Session objects will be managed here
sessions_db: Dict[str, ConversationSession] = {}

def get_or_create_session(session_id: str) -> ConversationSession:
    if session_id not in sessions_db:
        sessions_db[session_id] = ConversationSession(session_id=session_id)
    return sessions_db[session_id]

# Tool Definitions

def validate_customer_identity(session_id: str, identifier: str) -> Dict[str, Any]:
    """
    Authenticate customer using their email or phone number.
    Updates session memory with customer details.
    """
    session = get_or_create_session(session_id)
    customer = db_engine.find_customer_by_contact(identifier)
    
    if customer:
        session.authenticate_customer(customer)
        return {
            "success": True,
            "message": f"Successfully authenticated customer {customer.name} (ID: {customer.customer_id}).",
            "customer_id": customer.customer_id,
            "customer_name": customer.name
        }
    else:
        return {
            "success": False,
            "message": f"Could not find any customer with contact details matching '{identifier}'. Please double-check your email or phone."
        }

def lookup_customer_orders(session_id: str) -> Dict[str, Any]:
    """
    Retrieves all orders for the authenticated customer.
    """
    session = get_or_create_session(session_id)
    if not session.is_authenticated or not session.customer_id:
        return {
            "success": False,
            "message": "Authentication required. Please provide your email or phone number to verify your identity first."
        }
        
    orders = db_engine.get_customer_orders(session.customer_id)
    if not orders:
        return {
            "success": True,
            "message": "No orders found for this customer.",
            "orders": []
        }
        
    # Expose order summaries
    orders_summary = []
    for o in orders:
        orders_summary.append({
            "order_id": o.order_id,
            "status": o.status,
            "placed_at": o.placed_at,
            "total": o.total,
            "items_count": len(o.items)
        })
        
    return {
        "success": True,
        "message": f"Found {len(orders)} orders for customer {session.customer_name}.",
        "orders": orders_summary
    }

def get_order_details(session_id: str, order_id: str) -> Dict[str, Any]:
    """
    Retrieves complete details of a specific order.
    Performs security check to isolate data access.
    """
    session = get_or_create_session(session_id)
    if not session.is_authenticated or not session.customer_id:
        return {
            "success": False,
            "message": "Authentication required. Please provide your email or phone number first."
        }

    # Cross-customer access check
    order = db_engine.get_order(order_id)
    if not order:
        return {
            "success": False,
            "message": f"Order {order_id} does not exist."
        }
        
    if order.customer_id != session.customer_id:
        # PII / Security Breach Attempt - Block and raise warning
        return {
            "success": False,
            "message": "Access Denied: You are not authorized to view this order. Customer ID mismatch."
        }
        
    # Update active order in session
    session.current_order_id = order_id
    
    # Return formatted order details (clean representation)
    items_list = []
    for it in order.items:
        items_list.append({
            "sku": it.sku,
            "name": it.name,
            "category": it.category,
            "size": it.size,
            "price": it.price,
            "qty": it.qty,
            "final_sale": it.final_sale,
            "shipped": it.shipped,
            "backorder_eta": it.backorder_eta
        })
        
    return {
        "success": True,
        "order_id": order.order_id,
        "status": order.status,
        "placed_at": order.placed_at,
        "delivered_at": order.delivered_at,
        "expected_delivery": order.expected_delivery,
        "carrier": order.carrier,
        "tracking_number": order.tracking_number,
        "payment_method": order.payment_method,
        "shipping_city": order.shipping_city,
        "items": items_list,
        "total": order.total,
        "cancelled_at": order.cancelled_at,
        "refund_status": order.refund_status
    }

def calculate_return_eligibility(
    session_id: str, 
    order_id: str, 
    sku: str, 
    is_damaged_or_wrong: bool = False,
    has_original_shoe_box: bool = True
) -> Dict[str, Any]:
    """
    Evaluates return/exchange eligibility deterministically using the rules engine.
    Stores the result in the conversation session state.
    """
    session = get_or_create_session(session_id)
    if not session.is_authenticated or not session.customer_id:
        return {
            "success": False,
            "message": "Authentication required. Please provide your email or phone number first."
        }

    # Verify ownership
    order = db_engine.get_order(order_id)
    if not order:
        return {"success": False, "message": f"Order {order_id} not found."}
        
    if order.customer_id != session.customer_id:
        return {"success": False, "message": "Access Denied: You are not authorized to process returns for this order."}

    # Evaluate using Policy Rules Engine
    result = PolicyRulesEngine.evaluate_return_eligibility(
        order=order,
        sku=sku,
        is_damaged_or_wrong=is_damaged_or_wrong,
        has_original_shoe_box=has_original_shoe_box,
        current_date=SIMULATED_CURRENT_DATE
    )

    # Save to session return memory
    session.current_return = ReturnRequestState(
        sku=sku,
        reason="damaged_or_wrong" if is_damaged_or_wrong else "return_request",
        has_box=has_original_shoe_box,
        is_damaged=is_damaged_or_wrong,
        validation_status="APPROVED" if result.eligible else "REJECTED",
        rejection_reason=None if result.eligible else result.message,
        refund_deduction=result.refund_amount_deduction
    )

    # If the policy requires escalation (e.g. Lost Parcel)
    if result.reason_code == "LOST_PARCEL":
        escalation_res = escalate_to_human(session_id, "Carrier marked parcel lost in transit.")
        return {
            "success": False,
            "escalated": True,
            "message": result.message,
            "escalation_summary": escalation_res["summary"]
        }

    return {
        "success": True,
        "eligible": result.eligible,
        "reason_code": result.reason_code,
        "message": result.message,
        "action_allowed": result.action_allowed,
        "refund_deduction": result.refund_amount_deduction,
        "store_credit_allowed": result.store_credit_allowed,
        "original_refund_allowed": result.original_refund_allowed
    }

def claim_delay_compensation(session_id: str, order_id: str) -> Dict[str, Any]:
    """
    Check if order qualifies for delay compensation. If yes, processes store credit of 250.
    """
    session = get_or_create_session(session_id)
    if not session.is_authenticated or not session.customer_id:
        return {"success": False, "message": "Authentication required."}

    # Verify ownership
    order = db_engine.get_order(order_id)
    if not order or order.customer_id != session.customer_id:
        return {"success": False, "message": "Access Denied / Order not found."}

    result = PolicyRulesEngine.evaluate_delay_compensation(order, SIMULATED_CURRENT_DATE)
    if result.eligible:
        return {
            "success": True,
            "eligible": True,
            "message": result.message,
            "store_credit_amount": result.store_credit_amount
        }
    else:
        return {
            "success": True,
            "eligible": False,
            "message": result.message
        }

def search_policy(query: str) -> Dict[str, Any]:
    """
    Search the Trendly shipping and returns policy (RAG) for matching content chunks.
    """
    results = rag_engine.retrieve(query, top_k=2)
    chunks_list = []
    
    # We enforce a RAG confidence threshold. If similarity is too low (e.g. < 0.25 on our TF-IDF/embeddings),
    # it means the query is completely outside our policy context.
    low_confidence = True
    for chunk, score in results:
        if score > 0.25:
            low_confidence = False
        chunks_list.append({
            "section_id": chunk.section_id,
            "title": chunk.title,
            "text": chunk.text,
            "score": score
        })
        
    return {
        "success": True,
        "results": chunks_list,
        "low_confidence": low_confidence
    }

def escalate_to_human(session_id: str, reason: str) -> Dict[str, Any]:
    """
    Escalate the session to a human support agent.
    Creates a detailed Handoff Summary containing priority, attempted actions, and next steps.
    """
    session = get_or_create_session(session_id)
    session.escalated = True
    session.escalation_reason = reason
    
    # Generate Handoff Summary deterministically based on memory variables
    customer_info = f"Name: {session.customer_name or 'Unknown'}, Email: {session.customer_email or 'N/A'}, Phone: {session.customer_phone or 'N/A'}"
    
    # Analyze priority
    priority = "MEDIUM"
    suggested_step = "Review customer query and chat logs."
    
    lower_reason = reason.lower()
    if "lost" in lower_reason or "lost-parcel" in lower_reason:
        priority = "HIGH"
        suggested_step = "Initiate carrier lost claim refund or free replacement request."
    elif "bank" in lower_reason or "cod" in lower_reason:
        priority = "HIGH"
        suggested_step = "Send secure bank detail collection link for COD refund."
    elif "payment" in lower_reason or "charge" in lower_reason:
        priority = "HIGH"
        suggested_step = "Check payment gateway logs for transaction status."
        
    summary = {
        "customer_details": customer_info,
        "order_details": f"Active Order ID: {session.current_order_id or 'None'}",
        "issue_summary": reason,
        "attempted_actions": f"Authenticated: {session.is_authenticated}. Tools run: {[t.tool_name for t in session.tool_traces]}",
        "suggested_next_step": suggested_step,
        "priority": priority,
        "reason": reason
    }
    
    session.escalation_summary = summary
    return {
        "success": True,
        "message": f"Escalated to human support agent. Reason: {reason}",
        "summary": summary
    }
