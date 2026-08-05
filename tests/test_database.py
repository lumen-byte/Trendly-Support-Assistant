import pytest
from app.database import OrderDatabase, Order, Customer

def test_database_loads_correctly():
    db = OrderDatabase()
    assert len(db.customers) > 0
    assert len(db.orders) > 0

def test_get_customer():
    db = OrderDatabase()
    customer = db.get_customer("C-100")
    assert customer is not None
    assert customer.name == "Ananya Rao"
    assert customer.email == "ananya.rao@example.com"

def test_find_customer_by_contact():
    db = OrderDatabase()
    # Test email lookup
    c1 = db.find_customer_by_contact("ananya.rao@example.com")
    assert c1 is not None
    assert c1.customer_id == "C-100"

    # Test phone lookup (checking normalization)
    c2 = db.find_customer_by_contact("+91-98765-10001")
    assert c2 is not None
    assert c2.customer_id == "C-100"
    
    c3 = db.find_customer_by_contact("9876510001")
    assert c3 is not None
    assert c3.customer_id == "C-100"

def test_get_order():
    db = OrderDatabase()
    order = db.get_order("TR-4521")
    assert order is not None
    assert order.customer_id == "C-100"
    assert order.total == 3499
    assert len(order.items) == 1
    assert order.items[0].sku == "TR-DRS-014"

def test_get_customer_orders():
    db = OrderDatabase()
    orders = db.get_customer_orders("C-100")
    # C-100 has TR-4521, TR-4524, TR-4529
    assert len(orders) == 3
    order_ids = {o.order_id for o in orders}
    assert "TR-4521" in order_ids
    assert "TR-4524" in order_ids
    assert "TR-4529" in order_ids

def test_verify_order_ownership():
    db = OrderDatabase()
    assert db.verify_order_ownership("TR-4521", "C-100") is True
    assert db.verify_order_ownership("TR-4521", "C-101") is False
    assert db.verify_order_ownership("NON_EXISTENT", "C-100") is False
