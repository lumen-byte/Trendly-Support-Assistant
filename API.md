# API Documentation (API.md)

This document details the REST API endpoints exposed by the Trendly Support Assistant FastAPI server.

---

## 1. Chat Endpoint

*   **URL**: `/api/chat`
*   **Method**: `POST`
*   **Content-Type**: `application/json`

### Request Payload
```json
{
  "session_id": "trendly-web-demo",
  "message": "Hi, check my order status."
}
```

### Response Payload
```json
{
  "response": "To help you with your order, could you please share your registered email address or phone number?",
  "session": {
    "session_id": "trendly-web-demo",
    "customer_id": null,
    "customer_name": null,
    "customer_email": null,
    "customer_phone": null,
    "is_authenticated": false,
    "current_order_id": null,
    "current_return": null,
    "current_exchange": null,
    "conversation_summary": "",
    "escalated": false,
    "escalation_reason": null,
    "escalation_summary": null,
    "messages": [
      {
        "role": "user",
        "content": "Hi, check my order status."
      },
      {
        "role": "assistant",
        "content": "To help you with your order, could you please share your registered email address or phone number?"
      }
    ],
    "tool_traces": []
  }
}
```

---

## 2. Session Memory State Endpoint

*   **URL**: `/api/session/{session_id}`
*   **Method**: `GET`

### Response Payload
Returns the complete structured memory state of the specified session ID:
```json
{
  "session_id": "trendly-web-demo",
  "customer_id": "C-101",
  "customer_name": "Marcus Bell",
  "customer_email": "marcus.bell@example.com",
  "customer_phone": "+1-415-555-0102",
  "is_authenticated": true,
  "current_order_id": "TR-4530",
  "current_return": {
    "sku": "TR-KRT-033",
    "reason": "return_request",
    "has_box": true,
    "is_damaged": false,
    "validation_status": "APPROVED",
    "rejection_reason": null,
    "refund_deduction": 0.0
  },
  "current_exchange": null,
  "conversation_summary": "",
  "escalated": false,
  "escalation_reason": null,
  "escalation_summary": null,
  "messages": [ ... ],
  "tool_traces": [ ... ]
}
```

---

## 3. Clear Session Endpoint

*   **URL**: `/api/session/{session_id}/clear`
*   **Method**: `POST`

### Response Payload
```json
{
  "status": "SUCCESS",
  "message": "Session trendly-web-demo has been reset."
}
```

---

## 4. Human Escalations Endpoint

*   **URL**: `/api/escalations`
*   **Method**: `GET`

### Response Payload
Lists all active human handoff requests:
```json
{
  "success": true,
  "escalations": [
    {
      "session_id": "trendly-web-demo",
      "customer_name": "Marcus Bell",
      "customer_email": "marcus.bell@example.com",
      "escalation_reason": "Lost parcel claim raised for order TR-4526.",
      "summary": {
        "customer_details": "Name: Marcus Bell, Email: marcus.bell@example.com, Phone: +1-415-555-0102",
        "order_details": "Active Order ID: TR-4526",
        "issue_summary": "Lost parcel claim raised for order TR-4526.",
        "attempted_actions": "Authenticated: True. Tools run: ['validate_customer_identity', 'lookup_customer_orders']",
        "suggested_next_step": "Initiate carrier lost claim refund or free replacement request.",
        "priority": "HIGH",
        "reason": "Lost parcel claim raised for order TR-4526."
      },
      "timestamp": "2026-08-05T14:35:22"
    }
  ]
}
```
