from datetime import date
from app.database import OrderDatabase
from app.rules import PolicyRulesEngine, calculate_business_days_between

def test_calculate_business_days_between():
    # July 15 (Wed) to July 20 (Mon) -> 3 business days: Thu, Fri, Mon
    start = date(2026, 7, 15)
    end = date(2026, 7, 20)
    assert calculate_business_days_between(start, end) == 3

    # July 15 (Wed) to July 16 (Thu) -> 1 business day
    assert calculate_business_days_between(date(2026, 7, 15), date(2026, 7, 16)) == 1

    # July 17 (Fri) to July 20 (Mon) -> 1 business day (only Mon)
    assert calculate_business_days_between(date(2026, 7, 17), date(2026, 7, 20)) == 1

def test_return_eligibility_in_transit():
    db = OrderDatabase()
    order = db.get_order("TR-4521") # in_transit
    # SKU: TR-DRS-014
    res = PolicyRulesEngine.evaluate_return_eligibility(order, "TR-DRS-014")
    assert res.eligible is False
    assert res.reason_code == "NOT_DELIVERED"
    assert res.action_allowed == "NONE"

def test_return_eligibility_happy_path_and_socks():
    db = OrderDatabase()
    order = db.get_order("TR-4522") # delivered July 14, 2026. Current date Aug 5. (22 days)
    
    # Cotton Tee (Apparel) - Happy Path
    res1 = PolicyRulesEngine.evaluate_return_eligibility(order, "TR-TSH-002")
    assert res1.eligible is True
    assert res1.reason_code == "SUCCESS"
    assert res1.action_allowed == "REFUND_OR_EXCHANGE"

    # Socks (Innerwear) - Non-returnable
    res2 = PolicyRulesEngine.evaluate_return_eligibility(order, "TR-SOK-031")
    assert res2.eligible is False
    assert res2.reason_code == "NON_RETURNABLE_CATEGORY"
    assert res2.action_allowed == "NONE"

def test_return_eligibility_expired():
    db = OrderDatabase()
    order = db.get_order("TR-4523") # delivered June 5, 2026. Current date Aug 5. (>30 days)
    res = PolicyRulesEngine.evaluate_return_eligibility(order, "TR-JKT-008")
    assert res.eligible is False
    assert res.reason_code == "EXPIRED"
    assert "expired" in res.message.lower()

def test_return_eligibility_lost_parcel():
    db = OrderDatabase()
    order = db.get_order("TR-4526") # lost_in_transit
    res = PolicyRulesEngine.evaluate_return_eligibility(order, "TR-BAG-011")
    assert res.eligible is False
    assert res.reason_code == "LOST_PARCEL"
    assert res.action_allowed == "ESCALATE"

def test_return_eligibility_jewellery():
    db = OrderDatabase()
    order = db.get_order("TR-4527") # delivered July 23. Today Aug 5.
    res = PolicyRulesEngine.evaluate_return_eligibility(order, "TR-EAR-042") # jewellery category
    assert res.eligible is False
    assert res.reason_code == "NON_RETURNABLE_CATEGORY"

def test_return_eligibility_final_sale():
    db = OrderDatabase()
    order = db.get_order("TR-4528") # delivered July 19. Today Aug 5.
    res = PolicyRulesEngine.evaluate_return_eligibility(order, "TR-SHR-009") # final sale apparel
    assert res.eligible is True
    assert res.reason_code == "FINAL_SALE_EXCHANGE_ONLY"
    assert res.action_allowed == "EXCHANGE_ONLY"

def test_return_eligibility_cancelled():
    db = OrderDatabase()
    order = db.get_order("TR-4529") # cancelled
    res = PolicyRulesEngine.evaluate_return_eligibility(order, "TR-SCF-027")
    assert res.eligible is False
    assert res.reason_code == "CANCELLED"

def test_delay_compensation():
    db = OrderDatabase()
    order = db.get_order("TR-4525") # delayed, expected July 15. Today Aug 5.
    res = PolicyRulesEngine.evaluate_delay_compensation(order)
    assert res.eligible is True
    assert res.store_credit_amount == 250.0

    order_ok = db.get_order("TR-4522") # delivered
    res_ok = PolicyRulesEngine.evaluate_delay_compensation(order_ok)
    assert res_ok.eligible is False
