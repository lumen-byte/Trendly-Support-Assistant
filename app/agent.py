import json
import re
from typing import Dict, Any, List, Optional, Tuple
import google.generativeai as genai
from jinja2 import Template

from app.config import GEMINI_API_KEY, GEMINI_MODEL, SIMULATED_CURRENT_DATE
from app.state import ConversationSession
from app.safety import SafetyGuardrails
from app.tools import (
    get_or_create_session,
    validate_customer_identity,
    lookup_customer_orders,
    get_order_details,
    calculate_return_eligibility,
    claim_delay_compensation,
    search_policy,
    escalate_to_human,
    db_engine
)
from app.prompts import (
    SYSTEM_PROMPT,
    PLANNER_PROMPT,
    POLICY_QA_PROMPT,
    RESPONSE_GENERATION_PROMPT,
    ESCALATION_SUMMARY_PROMPT
)

class AgentOrchestrator:
    """
    Main Agent Orchestrator.
    Manages the multi-turn conversational loop, planner reasoning,
    tool execution, safety guardrail checks, and human escalation.
    """
    def __init__(self):
        self._initialize_llm()

    def _initialize_llm(self):
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config={"response_mime_type": "application/json"}
            )
            self.qa_model = genai.GenerativeModel(model_name=GEMINI_MODEL) # No JSON constraint for raw QA
            self.use_llm = True
        else:
            self.use_llm = False
            print("[Agent] No GEMINI_API_KEY found. Operating in deterministic rule-based fallback mode.")

    def run_planner_llm(self, prompt: str) -> Dict[str, Any]:
        """
        Executes the planner LLM, requesting a structured JSON response.
        """
        if not self.use_llm:
            raise RuntimeError("LLM is disabled or not configured.")
        
        response = self.model.generate_content(prompt)
        text = response.text.strip()
        # Parse JSON from response
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback if LLM outputs markdown codeblock
            cleaned = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.MULTILINE).strip()
            return json.loads(cleaned)

    def run_qa_llm(self, prompt: str) -> str:
        """
        Executes a raw text generation task (like Policy QA).
        """
        if not self.use_llm:
            return "Policy QA (Fallback): Please refer to the shipping policies."
        response = self.qa_model.generate_content(prompt)
        return response.text.strip()

    def process_message(self, session_id: str, user_message: str) -> str:
        """
        Processes a new user message end-to-end.
        Follows the standard Agentic Flow.
        """
        session = get_or_create_session(session_id)
        
        # 1. Safety Input Verification
        is_safe, reason_code, safety_resp = SafetyGuardrails.check_input_safety(user_message)
        if not is_safe:
            session.add_message("user", user_message)
            session.add_message("assistant", safety_resp)
            if reason_code in ["PROMPT_INJECTION", "PII_BANK_DETAILS"]:
                # Escalate security incidents to a human
                escalate_to_human(session_id, f"Security Violation Blocked: {reason_code}")
            return safety_resp

        # Add user message to history
        session.add_message("user", user_message)

        # 2. Handoff check (If already escalated, prompt human queue message)
        if session.escalated:
            resp = "This conversation has been escalated to a human support agent. A team member will join shortly. Trendly support hours are 9:00 AM – 9:00 PM IST."
            session.add_message("assistant", resp)
            return resp

        # 3. Planner & Tool Execution Loop (Max 5 iterations to prevent runaways)
        response_text = ""
        for iteration in range(5):
            # Render prompts
            history_str = self._format_history(session.messages[:-1]) # history before latest msg
            
            # Choose planner mechanism
            if self.use_llm:
                try:
                    planner_prompt = Template(PLANNER_PROMPT).render(
                        customer_id=session.customer_id,
                        current_order_id=session.current_order_id,
                        escalated=session.escalated,
                        conversation_history=history_str,
                        user_message=user_message
                    )
                    # Add system prompt as instructions
                    full_prompt = f"{Template(SYSTEM_PROMPT).render(current_date=SIMULATED_CURRENT_DATE)}\n\n{planner_prompt}"
                    plan = self.run_planner_llm(full_prompt)
                except Exception as e:
                    print(f"[Agent] Planner LLM execution failed: {e}. Running rule-based parser.")
                    plan = self._rule_based_planner(session, user_message)
            else:
                plan = self._rule_based_planner(session, user_message)

            tool_name = plan.get("tool_name")
            tool_inputs = plan.get("tool_inputs", {})
            
            # Execute tool if selected
            if tool_name:
                print(f"[Agent] Execution Iteration {iteration+1} -> Calling Tool: {tool_name} with {tool_inputs}")
                tool_output = self._execute_tool(session_id, tool_name, tool_inputs)
                session.add_trace(tool_name, tool_inputs, tool_output)
                
                # Append tool result to the conversation context for the next iteration
                # We add a hidden context trace so the planner can see the tool results.
                # In standard LLM, this is passed as a tool message. We append it to the scratchpad.
                user_message += f"\n[System Tool Result: {tool_name} returned {json.dumps(tool_output)}]"
                
                # Check if the tool triggered an escalation
                if session.escalated:
                    response_text = f"I've escalated this request to a human support agent. Summary: {session.escalation_reason}"
                    break
            else:
                # No more tools needed, we have our answer
                response_text = plan.get("response", "")
                break

        # 4. Generate grounded QA or explain returns if LLM is active
        # (This is where we compile final response based on tools results)
        if self.use_llm and not session.escalated:
            try:
                response_text = self._post_process_response(session, user_message, response_text)
            except Exception as e:
                print(f"[Agent] Error during post-processing: {e}")
                # Fallback to the planner's original response text

        # 5. Safety Output Verification
        is_output_safe, finalized_resp = SafetyGuardrails.check_output_safety(response_text)
        if not is_output_safe:
            # If output is unsafe, block and escalate
            escalate_to_human(session_id, "Output safety policy violation.")
            finalized_resp = "I have escalated your request to a human support agent to ensure you receive correct policy information."

        # Add assistant response to history
        session.add_message("assistant", finalized_resp)
        return finalized_resp

    def _execute_tool(self, session_id: str, tool_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Safe Tool Execution wrapper. Handles exceptions and timeouts.
        """
        # Inject session_id
        inputs["session_id"] = session_id
        
        try:
            if tool_name == "validate_customer_identity":
                return validate_customer_identity(session_id, inputs.get("identifier", ""))
            elif tool_name == "lookup_customer_orders":
                return lookup_customer_orders(session_id)
            elif tool_name == "get_order_details":
                return get_order_details(session_id, inputs.get("order_id", ""))
            elif tool_name == "calculate_return_eligibility":
                return calculate_return_eligibility(
                    session_id, 
                    inputs.get("order_id", ""), 
                    inputs.get("sku", ""),
                    is_damaged_or_wrong=inputs.get("is_damaged_or_wrong", False),
                    has_original_shoe_box=inputs.get("has_original_shoe_box", True)
                )
            elif tool_name == "claim_delay_compensation":
                return claim_delay_compensation(session_id, inputs.get("order_id", ""))
            elif tool_name == "search_policy":
                return search_policy(inputs.get("query", ""))
            elif tool_name == "escalate_to_human":
                return escalate_to_human(session_id, inputs.get("reason", ""))
            else:
                return {"success": False, "message": f"Unknown tool: {tool_name}"}
        except Exception as e:
            # Handle tool failure gracefully
            return {
                "success": False, 
                "message": f"An error occurred while running the tool '{tool_name}': {str(e)}"
            }

    def _post_process_response(self, session: ConversationSession, latest_query: str, current_response: str) -> str:
        """
        Format, ground, and double-check response generation.
        """
        # If last tool was a RAG search, use Policy QA prompt to ground the text
        last_trace = session.tool_traces[-1] if session.tool_traces else None
        
        if last_trace and last_trace.tool_name == "search_policy" and last_trace.outputs.get("success"):
            results = last_trace.outputs.get("results", [])
            low_confidence = last_trace.outputs.get("low_confidence", False)
            
            if low_confidence or not results:
                return "I don't have enough information from the Trendly policy. I'll connect you with a human support agent."
                
            # Ground answer using policy chunks
            chunks_str = "\n\n".join([f"[{c['section_id']}] {c['text']}" for c in results])
            history_str = self._format_history(session.messages[:-1])
            
            qa_prompt = Template(POLICY_QA_PROMPT).render(
                retrieved_chunks=chunks_str,
                conversation_history=history_str,
                query=latest_query
            )
            
            return self.run_qa_llm(qa_prompt)
            
        elif last_trace and last_trace.tool_name == "calculate_return_eligibility":
            # Explain return eligibility using policy rules results
            outputs = last_trace.outputs
            return_summary = f"SKU: {session.current_return.sku}, Status: {session.current_return.validation_status}"
            history_str = self._format_history(session.messages[:-1])
            
            gen_prompt = Template(RESPONSE_GENERATION_PROMPT).render(
                customer_name=session.customer_name,
                customer_id=session.customer_id,
                current_order_id=session.current_order_id,
                return_state_summary=return_summary,
                tool_results=json.dumps(outputs),
                user_message=latest_query
            )
            return self.run_qa_llm(gen_prompt)
            
        return current_response

    def _format_history(self, messages: List[Dict[str, str]]) -> str:
        formatted = []
        for m in messages:
            role = "Customer" if m["role"] == "user" else "Assistant"
            formatted.append(f"{role}: {m['content']}")
        return "\n".join(formatted)

    def _rule_based_planner(self, session: ConversationSession, user_message: str) -> Dict[str, Any]:
        """
        Deterministic Rule-Based Planner.
        Serves as the ultimate fallback if the LLM is offline or has no key.
        Guarantees that standard flows (lookup, return, delays, lost parcel) function perfectly.
        """
        # 1. Clean the user message of any system traces
        raw_user_msg = user_message.split("\n[System Tool Result:")[0]
        msg = raw_user_msg.lower()
        
        # Check trace history to see what was just executed in the CURRENT turn
        last_trace = None
        if "[system tool result:" in user_message.lower():
            last_trace = session.tool_traces[-1] if session.tool_traces else None

        # 2. Handle Tool Outputs and Format Final Responses (Executed first)
        if last_trace:
            t_name = last_trace.tool_name
            t_out = last_trace.outputs
            
            # If the tool failed, return the error message directly
            if not t_out.get("success", True):
                return {
                    "tool_name": None,
                    "response": t_out.get("message", "An error occurred during tool execution.")
                }
                
            if t_name == "validate_customer_identity":
                # Check if history has status or return intent
                has_status_intent = any("status" in m["content"].lower() or "order" in m["content"].lower() or "track" in m["content"].lower() for m in session.messages if m["role"] == "user")
                if has_status_intent:
                    return {
                        "tool_name": "lookup_customer_orders",
                        "tool_inputs": {},
                        "response": "Let me fetch your orders list..."
                    }
                else:
                    return {
                        "tool_name": None,
                        "response": f"Successfully authenticated customer {session.customer_name}. How can I help you today?"
                    }
                    
            elif t_name == "lookup_customer_orders":
                orders = t_out.get("orders", [])
                orders_str = "\n".join([f"- Order {o['order_id']}: {o['status'].replace('_', ' ').title()} (Placed: {o['placed_at'][:10]}, Total: \u20b9{o['total']})" for o in orders])
                return {
                    "tool_name": None,
                    "response": f"Successfully authenticated customer {session.customer_name}.\nI found the following orders under your account:\n{orders_str}\n\nHow can I help you today?"
                }
                
            elif t_name == "get_order_details":
                # Check if order is lost in transit
                status = t_out.get("status")
                order_id = t_out.get("order_id")
                if status == "lost_in_transit" or "lost" in msg:
                    return {
                        "tool_name": "escalate_to_human",
                        "tool_inputs": {"reason": f"Lost parcel claim raised for order {order_id}."},
                        "response": f"Order {order_id} is marked lost. Escalating..."
                    }
                
                items_str = "\n".join([f"  * SKU: {i['sku']} - {i['name']} ({i['size']}) | \u20b9{i['price']}" for i in t_out.get("items", [])])
                delivery_info = f"Expected delivery: {t_out.get('expected_delivery')}" if t_out.get("expected_delivery") else f"Delivered at: {t_out.get('delivered_at')}"
                resp_text = (
                    f"Order Details for {order_id}:\n"
                    f"- Status: {status.replace('_', ' ').title()}\n"
                    f"- Payment Method: {t_out.get('payment_method').replace('_', ' ').upper()}\n"
                    f"- Shipping City: {t_out.get('shipping_city')}\n"
                    f"- {delivery_info}\n"
                    f"- Items:\n{items_str}\n"
                    f"- Total: \u20b9{t_out.get('total')}"
                )
                return {
                    "tool_name": None,
                    "response": resp_text
                }
                
            elif t_name == "calculate_return_eligibility":
                eligible = t_out.get("eligible")
                msg_text = t_out.get("message")
                action = t_out.get("action_allowed")
                
                if eligible:
                    return {
                        "tool_name": None,
                        "response": f"Good news! Your item is eligible for return/exchange. Details: {msg_text}"
                    }
                else:
                    if action == "ESCALATE":
                        return {
                            "tool_name": "escalate_to_human",
                            "tool_inputs": {"reason": f"Return evaluation required escalation: {msg_text}"},
                            "response": "Escalating..."
                        }
                    return {
                        "tool_name": None,
                        "response": f"I'm sorry, but this item is not eligible for return. Policy reason: {msg_text}"
                    }
                    
            elif t_name == "claim_delay_compensation":
                eligible = t_out.get("eligible")
                msg_text = t_out.get("message")
                if eligible:
                    return {
                        "tool_name": None,
                        "response": f"Claim Approved: {msg_text}"
                    }
                else:
                    return {
                        "tool_name": None,
                        "response": f"Claim Refused: {msg_text}"
                    }
                    
            elif t_name == "search_policy":
                results = t_out.get("results", [])
                low_conf = t_out.get("low_confidence", False)
                if low_conf or not results:
                    return {
                        "tool_name": "escalate_to_human",
                        "tool_inputs": {"reason": "Out of policy query / low confidence search results."},
                        "response": "I don't have enough information from the Trendly policy. Let me connect you with a human agent."
                    }
                # Return the text of the top chunk
                top_chunk = results[0]
                return {
                    "tool_name": None,
                    "response": f"{top_chunk['text']}\n\nReference: [{top_chunk['title']}]"
                }

        # 3. Define Context-Based Authentication Helper
        def require_auth() -> Optional[Dict[str, Any]]:
            if session.is_authenticated:
                return None
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', raw_user_msg)
            phone_match = re.search(r'\+?\d[\d-]{7,14}\d', raw_user_msg)
            if email_match:
                return {
                    "tool_name": "validate_customer_identity",
                    "tool_inputs": {"identifier": email_match.group(0)},
                    "response": "Verifying your details..."
                }
            elif phone_match:
                return {
                    "tool_name": "validate_customer_identity",
                    "tool_inputs": {"identifier": phone_match.group(0)},
                    "response": "Verifying your details..."
                }
            else:
                return {
                    "tool_name": None,
                    "response": "To help you with your order, could you please share your registered email address or phone number?"
                }

        # 4. Check if they explicitly provided contact details to authenticate
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', raw_user_msg)
        phone_match = re.search(r'\+?\d[\d-]{7,14}\d', raw_user_msg)
        if not session.is_authenticated and (email_match or phone_match):
            auth_plan = require_auth()
            if auth_plan:
                return auth_plan

        # 5. Lost Parcel Claim Detection (Section 1.6)
        if "lost" in msg or "not received" in msg or "where is my" in msg:
            # Active check -> requires auth
            auth_plan = require_auth()
            if auth_plan:
                return auth_plan
                
            orders = db_engine.get_customer_orders(session.customer_id)
            lost_order = None
            order_match = re.search(r'tr-\d{4}', msg)
            specified_order_id = order_match.group(0).upper() if order_match else None
            
            for o in orders:
                if specified_order_id and o.order_id != specified_order_id:
                    continue
                if o.status == "lost_in_transit":
                    lost_order = o
                    break
                    
            if lost_order:
                return {
                    "tool_name": "escalate_to_human",
                    "tool_inputs": {"reason": f"Lost parcel claim raised for order {lost_order.order_id}."},
                    "response": f"Escalating lost parcel claim for {lost_order.order_id}."
                }

        # 6. Return / Exchange Request
        if "return" in msg or "exchange" in msg:
            order_match = re.search(r'tr-\d{4}', msg)
            order_id = order_match.group(0).upper() if order_match else session.current_order_id
            
            # Heuristic to separate active transaction returns from general policy queries
            has_order_id = order_match is not None
            has_personal_indicator = "my" in msg or "i bought" in msg or "i purchased" in msg
            has_action_verb = any(v in msg for v in ["start", "raise", "file", "make", "initiate", "request", "eligible"])
            
            is_active_request = has_order_id or has_personal_indicator or has_action_verb
            
            if is_active_request:
                # Active return request -> requires auth
                auth_plan = require_auth()
                if auth_plan:
                    return auth_plan
                    
                if not order_id:
                    orders = db_engine.get_customer_orders(session.customer_id)
                    if len(orders) == 1:
                        order_id = orders[0].order_id
                    elif len(orders) > 1:
                        return {
                            "tool_name": "lookup_customer_orders",
                            "tool_inputs": {},
                            "response": "Let me look up your orders list."
                        }
                    else:
                        return {
                            "tool_name": None,
                            "response": "I couldn't find any orders placed under your account."
                        }

                # Set current order context
                session.current_order_id = order_id
                order = db_engine.get_order(order_id)
                
                if order:
                    if order.customer_id != session.customer_id:
                        return {
                            "tool_name": None,
                            "response": "Access Denied: You are not authorized to view this order."
                        }
                    
                    sku_match = re.search(r'tr-[a-z]{3}-\d{3}', msg)
                    sku = sku_match.group(0).upper() if sku_match else None
                    
                    if not sku:
                        for item in order.items:
                            if item.name.lower() in msg or item.sku.lower() in msg:
                                sku = item.sku
                                break
                                
                    if not sku and len(order.items) == 1:
                        sku = order.items[0].sku
                    
                    if sku:
                        has_box = "no box" not in msg and "missing box" not in msg and "without box" not in msg
                        is_damaged = "damaged" in msg or "defective" in msg or "wrong" in msg
                        
                        return {
                            "tool_name": "calculate_return_eligibility",
                            "tool_inputs": {
                                "order_id": order_id,
                                "sku": sku,
                                "is_damaged_or_wrong": is_damaged,
                                "has_original_shoe_box": has_box
                            },
                            "response": "Evaluating your return eligibility..."
                        }
                    else:
                        item_names = ", ".join([f"'{i.name}' (SKU: {i.sku})" for i in order.items])
                        return {
                            "tool_name": None,
                            "response": f"Which item in order {order_id} would you like to return/exchange? The items are: {item_names}."
                        }

        # 7. Delay Compensation Claim
        if "delay" in msg or "compensate" in msg or "late" in msg or "credit" in msg:
            auth_plan = require_auth()
            if auth_plan:
                return auth_plan
                
            order_match = re.search(r'tr-\d{4}', msg)
            order_id = order_match.group(0).upper() if order_match else session.current_order_id
            
            if order_id:
                return {
                    "tool_name": "claim_delay_compensation",
                    "tool_inputs": {"order_id": order_id},
                    "response": "Checking delay compensation eligibility..."
                }

        # 8. Order Status lookup (Triggers if they specify Order ID, or query status/tracking keywords)
        order_match = re.search(r'tr-\d{4}', msg)
        is_status_query = "status" in msg or "track" in msg or "where is" in msg or "details" in msg
        is_my_orders_list = "my order" in msg or "my orders" in msg or "list order" in msg or "show order" in msg
        
        if order_match or is_status_query or is_my_orders_list:
            auth_plan = require_auth()
            if auth_plan:
                return auth_plan
                
            order_id = order_match.group(0).upper() if order_match else session.current_order_id
            
            if order_id:
                return {
                    "tool_name": "get_order_details",
                    "tool_inputs": {"order_id": order_id},
                    "response": "Looking up details for your order..."
                }
            else:
                return {
                    "tool_name": "lookup_customer_orders",
                    "tool_inputs": {},
                    "response": "Looking up your orders list..."
                }

        # 9. General Policy QA Search Fallback (Guest search - no auth required)
        return {
            "tool_name": "search_policy",
            "tool_inputs": {"query": raw_user_msg},
            "response": "Searching policy guidelines..."
        }
