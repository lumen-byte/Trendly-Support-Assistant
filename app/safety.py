import re
from typing import Optional, Tuple
from app.database import OrderDatabase

# Regex patterns for safety
CREDIT_CARD_REGEX = re.compile(r'\b(?:\d[ -]*?){13,19}\b')
CVV_REGEX = re.compile(r'\b\d{3,4}\b')
BANK_ACCOUNT_REGEX = re.compile(r'\b\d{9,18}\b') # Standard Indian/US bank accounts
IFSC_REGEX = re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b', re.IGNORECASE)

PROMPT_INJECTION_KEYWORDS = [
    "ignore all previous", "ignore previous instructions", "system prompt",
    "developer mode", "override policy", "you are now a", "jailbreak",
    "ignore limits", "ignore constraints", "new instructions", "forget rules"
]

class SafetyGuardrails:
    """
    Security and Safety Layer.
    Performs input/output verification to prevent jailbreaks, prompt injections,
    PII leakage, bank detail collections, and cross-customer data leakage.
    """
    
    @classmethod
    def check_input_safety(cls, user_message: str) -> Tuple[bool, str, str]:
        """
        Scan user input for prompt injections, bank account numbers, or CVVs.
        Returns (is_safe, error_reason_code, human_readable_response)
        """
        lower_msg = user_message.lower()
        
        # 1. Prompt Injection check
        for keyword in PROMPT_INJECTION_KEYWORDS:
            if keyword in lower_msg:
                return (
                    False, 
                    "PROMPT_INJECTION", 
                    "I cannot perform this operation. My instructions and policies are fixed and cannot be modified."
                )

        # 2. Bank / PII Detail Collection check (Section 3.3 & 7)
        # We must prevent collecting bank details or credit cards.
        if CREDIT_CARD_REGEX.search(user_message):
            return (
                False,
                "PII_CREDIT_CARD",
                "For security reasons, please do not share credit card numbers in chat. Trendly will never ask for your card details here."
            )
            
        if CVV_REGEX.search(user_message) and ("cvv" in lower_msg or "pin" in lower_msg or "code" in lower_msg):
            return (
                False,
                "PII_CVV",
                "For security reasons, please do not share your CVV or PIN in chat."
            )
            
        if IFSC_REGEX.search(user_message) or (BANK_ACCOUNT_REGEX.search(user_message) and ("account number" in lower_msg or "bank" in lower_msg or "ifsc" in lower_msg)):
            return (
                False,
                "PII_BANK_DETAILS",
                "I am not authorized to collect bank details. Please connect with a human support agent who will collect them via a secure link."
            )

        return True, "SAFE", ""

    @classmethod
    def verify_order_access(
        cls, 
        db: OrderDatabase, 
        order_id: str, 
        authenticated_customer_id: Optional[str]
    ) -> Tuple[bool, str]:
        """
        Verify that the authenticated customer owns the order they are querying.
        Prevents Cross-Customer Data Leakage (Section 7).
        """
        if not authenticated_customer_id:
            return False, "You must be authenticated to check order status."
            
        order = db.get_order(order_id)
        if not order:
            return False, f"Order {order_id} not found."
            
        if order.customer_id != authenticated_customer_id:
            return False, "Access Denied: You are not authorized to view or modify this order."
            
        return True, "SUCCESS"

    @classmethod
    def check_output_safety(cls, llm_response: str) -> Tuple[bool, str]:
        """
        Ensures the model output does not include:
        - Fake policies / unauthorized discounts
        - Bank collections
        """
        lower_resp = llm_response.lower()
        
        # 1. Prevent unauthorized goodwill credits or waivers
        # Exception: "250 store credit" (delay) and "150" (courier ship) are permitted.
        # Check for phrases like "discount coupon", "promo code", "50% off", "waive the fee"
        unauthorized_discount_keywords = [
            "discount code", "coupon code", "promo code", "discount coupon", 
            "percent off", "percentage off", "goodwill credit", "store credit of 500",
            "store credit of 1000", "waive the charge", "waive the shipping fee"
        ]
        for keyword in unauthorized_discount_keywords:
            if keyword in lower_resp:
                # If the LLM generates unauthorized discount, we replace it or block it.
                return False, "I don't have enough information from the Trendly policy to offer custom discounts or waivers. I'll connect you with a human support agent."
                
        # 2. Prevent LLM from asking for bank details
        if "bank account" in lower_resp or "ifsc" in lower_resp or "cvv" in lower_resp or "card number" in lower_resp:
            return False, "I cannot collect your bank details in chat. I will escalate this to a human support agent to provide a secure link."

        return True, llm_response
