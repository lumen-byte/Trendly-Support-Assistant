from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel
from app.config import SIMULATED_CURRENT_DATE
from app.database import Order, OrderItem

class EligibilityResult(BaseModel):
    eligible: bool
    reason_code: str  # SUCCESS, EXPIRED, NON_RETURNABLE_CATEGORY, CANCELLED, NOT_DELIVERED, FINAL_SALE_NO_REFUND, ALREADY_RETURNED
    message: str
    action_allowed: str  # REFUND_OR_EXCHANGE, EXCHANGE_ONLY, NONE, ESCALATE
    refund_amount_deduction: float = 0.0
    store_credit_allowed: bool = True
    original_refund_allowed: bool = True

class DelayEligibilityResult(BaseModel):
    eligible: bool
    delay_days: int
    message: str
    store_credit_amount: float = 0.0

def calculate_business_days_between(start_date: date, end_date: date) -> int:
    """
    Calculate the number of business days (Monday to Friday) between two dates.
    """
    if start_date >= end_date:
        return 0
    
    days = 0
    curr = start_date
    while curr < end_date:
        curr += timedelta(days=1)
        if curr.weekday() < 5:  # Monday to Friday are 0 to 4
            days += 1
    return days

class PolicyRulesEngine:
    """
    Deterministic rule engine implementing the business logic for Trendly policies.
    Guarantees policy rules are executed precisely with zero LLM hallucination.
    """
    
    NON_RETURNABLE_CATEGORIES = {"innerwear", "jewellery", "beauty", "fragrance", "mask", "gift_card"}

    @classmethod
    def evaluate_return_eligibility(
        cls, 
        order: Order, 
        sku: str, 
        is_damaged_or_wrong: bool = False,
        has_original_shoe_box: bool = True,
        current_date: date = SIMULATED_CURRENT_DATE
    ) -> EligibilityResult:
        """
        Evaluate if an item is eligible for return or exchange under the policy.
        """
        # 1. Order status checks
        if order.status == "cancelled":
            return EligibilityResult(
                eligible=False,
                reason_code="CANCELLED",
                message="Once an order is cancelled, no return can be raised against it.",
                action_allowed="NONE",
                original_refund_allowed=False,
                store_credit_allowed=False
            )
            
        # Find item in the order
        item: Optional[OrderItem] = None
        for i in order.items:
            if i.sku == sku:
                item = i
                break
                
        if not item:
            return EligibilityResult(
                eligible=False,
                reason_code="ITEM_NOT_FOUND",
                message=f"Item with SKU {sku} does not exist in order {order.order_id}.",
                action_allowed="NONE"
            )

        # 2. Check if lost parcel
        if order.status == "lost_in_transit":
            return EligibilityResult(
                eligible=False,
                reason_code="LOST_PARCEL",
                message="This parcel is marked as lost in transit. This must be escalated to a human agent as a lost-parcel claim, not a return.",
                action_allowed="ESCALATE"
            )

        # 3. Check if delivered
        if order.status != "delivered" or not order.delivered_at:
            return EligibilityResult(
                eligible=False,
                reason_code="NOT_DELIVERED",
                message="This order has not been delivered yet. Returns can only be raised for delivered items.",
                action_allowed="NONE"
            )

        # Parse delivery date
        try:
            # delivered_at format like "2026-07-14T09:20:00Z"
            delivery_datetime = datetime.strptime(order.delivered_at, "%Y-%m-%dT%H:%M:%SZ")
            delivery_date = delivery_datetime.date()
        except ValueError:
            # Fallback if just a date string
            delivery_date = datetime.strptime(order.delivered_at.split("T")[0], "%Y-%m-%d").date()

        # 4. Damaged/Wrong items check (Section 6.1: reported within 48 hours of delivery)
        if is_damaged_or_wrong:
            hours_since_delivery = (datetime.combine(current_date, datetime.min.time()) - datetime.combine(delivery_date, datetime.min.time())).total_seconds() / 3600.0
            if hours_since_delivery <= 48:
                # Under section 6.2, even non-returnable categories are covered if damaged/wrong on arrival
                return EligibilityResult(
                    eligible=True,
                    reason_code="SUCCESS",
                    message="Reported within 48 hours. Eligible for free replacement or full refund, including shipping fees.",
                    action_allowed="REFUND_OR_EXCHANGE",
                    refund_amount_deduction=0.0
                )
            else:
                # If outside 48 hours, standard return window policy applies
                # Note: We should inform the user that since it is outside 48 hours, standard policy rules apply.
                pass

        # 5. Return window check (Section 2.1: 30 calendar days of delivery date)
        days_since_delivery = (current_date - delivery_date).days
        if days_since_delivery > 30:
            return EligibilityResult(
                eligible=False,
                reason_code="EXPIRED",
                message=f"Return window expired. The item was delivered {days_since_delivery} days ago (limit: 30 days).",
                action_allowed="NONE"
            )

        # 6. Non-returnable category check (Section 2.3)
        # Note: If it's a damaged report outside 48h, it is subject to the standard category restrictions.
        if item.category.lower() in cls.NON_RETURNABLE_CATEGORIES or "socks" in item.name.lower():
            return EligibilityResult(
                eligible=False,
                reason_code="NON_RETURNABLE_CATEGORY",
                message=f"Hygiene Policy Exclusion: Items in the category '{item.category}' cannot be returned or exchanged.",
                action_allowed="NONE"
            )

        # 7. Footwear box check (Section 2.5)
        refund_deduction = 0.0
        msg_suffix = ""
        if item.category.lower() == "footwear" and not has_original_shoe_box:
            refund_deduction = 300.0
            msg_suffix = " A ₹300 deduction will be applied to the refund because the original shoe box is missing."

        # 8. Final sale check (Section 2.4: exchange size only - no refund/store credit)
        if item.final_sale:
            return EligibilityResult(
                eligible=True,
                reason_code="FINAL_SALE_EXCHANGE_ONLY",
                message=f"Item is marked Final Sale. It is eligible for size exchange ONLY. No refund or store credit will be issued.{msg_suffix}",
                action_allowed="EXCHANGE_ONLY",
                refund_amount_deduction=refund_deduction,
                original_refund_allowed=False,
                store_credit_allowed=False
            )

        # 9. Clean happy path return/exchange
        return EligibilityResult(
            eligible=True,
            reason_code="SUCCESS",
            message=f"Item is eligible for return or size exchange.{msg_suffix}",
            action_allowed="REFUND_OR_EXCHANGE",
            refund_amount_deduction=refund_deduction
        )

    @classmethod
    def evaluate_delay_compensation(
        cls, 
        order: Order, 
        current_date: date = SIMULATED_CURRENT_DATE
    ) -> DelayEligibilityResult:
        """
        Evaluate if an order qualifies for the ₹250 store credit due to shipment delay (Section 1.5).
        An order is delayed once it is more than 3 business days past its expected delivery date.
        """
        if order.status == "delivered" or order.status == "cancelled":
            return DelayEligibilityResult(
                eligible=False,
                delay_days=0,
                message=f"Order is in '{order.status}' status. Delay compensation is only applicable for delayed active shipments."
            )

        if not order.expected_delivery:
            return DelayEligibilityResult(
                eligible=False,
                delay_days=0,
                message="No expected delivery date is recorded for this order."
            )

        expected_date = datetime.strptime(order.expected_delivery, "%Y-%m-%d").date()
        
        # Calculate business days past the expected delivery date
        business_days_delayed = calculate_business_days_between(expected_date, current_date)
        
        # Must be *more than* 3 business days
        if business_days_delayed > 3:
            return DelayEligibilityResult(
                eligible=True,
                delay_days=business_days_delayed,
                message=f"This order is {business_days_delayed} business days past its expected delivery date. The customer qualifies for a ₹250 store credit.",
                store_credit_amount=250.0
            )
        else:
            return DelayEligibilityResult(
                eligible=False,
                delay_days=business_days_delayed,
                message=f"The order is {business_days_delayed} business days past expected delivery date (limit to qualify: more than 3 business days)."
            )
