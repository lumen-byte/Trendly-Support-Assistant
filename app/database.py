import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, date
from app.config import ORDERS_JSON_PATH

class Customer(BaseModel):
    customer_id: str
    name: str
    email: str
    phone: str

class OrderItem(BaseModel):
    sku: str
    name: str
    category: str
    size: str
    qty: int
    price: float
    final_sale: bool = False
    shipped: Optional[bool] = None
    backorder_eta: Optional[str] = None

class Order(BaseModel):
    order_id: str
    customer_id: str
    status: str  # in_transit, delivered, partially_shipped, delayed, lost_in_transit, cancelled
    placed_at: str
    delivered_at: Optional[str] = None
    expected_delivery: Optional[str] = None
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
    payment_method: str
    shipping_city: str
    items: List[OrderItem]
    total: float
    cancelled_at: Optional[str] = None
    refund_status: Optional[str] = None

class OrderDatabase:
    """
    Abstrated interface for the orders.json dataset.
    This acts as the Order Engine, preventing raw JSON exposure
    and enforcing secure customer context isolation.
    """
    def __init__(self, json_path: str = str(ORDERS_JSON_PATH)):
        self.json_path = json_path
        self._load_data()

    def _load_data(self):
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.customers: Dict[str, Customer] = {
            c["customer_id"]: Customer(**c) for c in data.get("customers", [])
        }
        self.orders: Dict[str, Order] = {
            o["order_id"]: Order(**o) for o in data.get("orders", [])
        }

    def get_customer(self, customer_id: str) -> Optional[Customer]:
        return self.customers.get(customer_id)

    def find_customer_by_contact(self, identifier: str) -> Optional[Customer]:
        """
        Lookup customer by email or phone number.
        """
        clean_identifier = identifier.strip().lower()
        for customer in self.customers.values():
            if customer.email.lower() == clean_identifier:
                return customer
            # Clean non-digits for comparison if phone is input
            clean_phone = "".join(filter(str.isdigit, customer.phone))
            clean_input = "".join(filter(str.isdigit, clean_identifier))
            if clean_input and clean_phone and clean_input in clean_phone:
                return customer
        return None

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

    def get_customer_orders(self, customer_id: str) -> List[Order]:
        return [o for o in self.orders.values() if o.customer_id == customer_id]

    def verify_order_ownership(self, order_id: str, customer_id: str) -> bool:
        """
        Security check to prevent cross-customer access.
        """
        order = self.get_order(order_id)
        if not order:
            return False
        return order.customer_id == customer_id
