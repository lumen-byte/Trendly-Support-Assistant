import pytest
from app.tools import (
    validate_customer_identity,
    lookup_customer_orders,
    get_order_details,
    calculate_return_eligibility,
    claim_delay_compensation,
    search_policy,
    escalate_to_human,
    get_or_create_session,
    sessions_db
)

def test_tool_authenticate_and_lookup():
    session_id = "test-session-1"
    
    # 1. Start unauthenticated lookup
    res = lookup_customer_orders(session_id)
    assert res["success"] is False
    assert "authentication required" in res["message"].lower()

    # 2. Authenticate
    res_auth = validate_customer_identity(session_id, "ananya.rao@example.com")
    assert res_auth["success"] is True
    assert res_auth["customer_id"] == "C-100"

    # 3. Lookup customer orders (should succeed now)
    res_orders = lookup_customer_orders(session_id)
    assert res_orders["success"] is True
    assert len(res_orders["orders"]) == 3

def test_tool_order_details_and_security():
    session_id = "test-session-2"
    # Authenticate as C-101
    validate_customer_identity(session_id, "marcus.bell@example.com")

    # Access owned order (TR-4522)
    res_detail = get_order_details(session_id, "TR-4522")
    assert res_detail["success"] is True
    assert res_detail["order_id"] == "TR-4522"

    # Try to access C-100's order (TR-4521) -> Should be blocked!
    res_detail_blocked = get_order_details(session_id, "TR-4521")
    assert res_detail_blocked["success"] is False
    assert "access denied" in res_detail_blocked["message"].lower()

def test_tool_return_eligibility_and_escalate():
    session_id = "test-session-3"
    # Authenticate as C-101
    validate_customer_identity(session_id, "marcus.bell@example.com")

    # Happy path return Cotton Tee
    res_eligible = calculate_return_eligibility(session_id, "TR-4522", "TR-TSH-002")
    assert res_eligible["success"] is True
    assert res_eligible["eligible"] is True

    # Try Socks (innerwear)
    res_socks = calculate_return_eligibility(session_id, "TR-4522", "TR-SOK-031")
    assert res_socks["success"] is True
    assert res_socks["eligible"] is False
    assert res_socks["reason_code"] == "NON_RETURNABLE_CATEGORY"

    # Lost parcel (TR-4526) -> triggers human escalation
    res_lost = calculate_return_eligibility(session_id, "TR-4526", "TR-BAG-011")
    assert res_lost["success"] is False
    assert res_lost["escalated"] is True
    
    session = get_or_create_session(session_id)
    assert session.escalated is True
    assert session.escalation_summary is not None
    assert session.escalation_summary["priority"] == "HIGH"

def test_tool_delay_compensation():
    session_id = "test-session-4"
    # Authenticate as C-103
    validate_customer_identity(session_id, "+34-600-555-104")

    # TR-4525 is delayed
    res = claim_delay_compensation(session_id, "TR-4525")
    assert res["success"] is True
    assert res["eligible"] is True
    assert res["store_credit_amount"] == 250.0

def test_tool_policy_search():
    res = search_policy("Can I return socks?")
    assert res["success"] is True
    assert len(res["results"]) > 0
