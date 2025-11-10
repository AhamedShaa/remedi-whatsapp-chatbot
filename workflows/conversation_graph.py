# workflows/conversation_graph.py - LangGraph workflow for conversation management
from typing import TypedDict, Annotated, Sequence, Optional, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import operator
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

# Define the conversation state
class ConversationState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    phone_number: str
    patient: dict
    current_stage: str
    waiting_for: str
    context: dict

class ConversationGraph:
    def __init__(self, db, whatsapp):
        self.db = db
        self.whatsapp = whatsapp
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the conversation flow graph"""
        workflow = StateGraph(ConversationState)
        
        # Add nodes for each conversation stage
        workflow.add_node("check_registration", self.check_registration)
        workflow.add_node("handle_trigger", self.handle_trigger)
        workflow.add_node("show_main_menu", self.show_main_menu)
        workflow.add_node("handle_menu_selection", self.handle_menu_selection)
        workflow.add_node("teleconsultation_flow", self.teleconsultation_flow)
        workflow.add_node("upload_report_flow", self.upload_report_flow)
        workflow.add_node("bp_logging_flow", self.bp_logging_flow)
        workflow.add_node("home_visit_flow", self.home_visit_flow)
        workflow.add_node("doctor_chat_flow", self.doctor_chat_flow)
        workflow.add_node("end_conversation", self.end_conversation)
        
        # Set entry point
        workflow.set_entry_point("check_registration")
        
        # Add conditional edges
        workflow.add_conditional_edges(
            "check_registration",
            self.route_after_registration,
            {
                "unregistered": "handle_trigger",
                "pending": "handle_trigger",
                "registered": "handle_trigger"
            }
        )
        
        workflow.add_conditional_edges(
            "handle_trigger",
            self.route_after_trigger,
            {
                "show_menu": "show_main_menu",
                "end": END
            }
        )
        
        workflow.add_conditional_edges(
            "show_main_menu",
            lambda x: "wait_for_selection",
            {
                "wait_for_selection": END
            }
        )
        
        workflow.add_conditional_edges(
            "handle_menu_selection",
            self.route_menu_selection,
            {
                "1": "teleconsultation_flow",
                "2": "upload_report_flow",
                "3": "bp_logging_flow",
                "4": "home_visit_flow",
                "5": "doctor_chat_flow",
                "invalid": "show_main_menu",
                "end": END
            }
        )
        
        # Add edges back to menu after completing flows
        workflow.add_edge("teleconsultation_flow", "end_conversation")
        workflow.add_edge("upload_report_flow", "end_conversation")
        workflow.add_edge("bp_logging_flow", "end_conversation")
        workflow.add_edge("home_visit_flow", "end_conversation")
        workflow.add_edge("doctor_chat_flow", "end_conversation")
        workflow.add_edge("end_conversation", END)
        
        return workflow.compile()
    
    async def process_message(self, message_data):
        """Process incoming message through the graph"""
        try:
            phone = message_data["from"]
            text = message_data.get("text", "").strip()
            message_type = message_data["type"]
            
            # Get or create patient
            patient = await self.db.get_patient_by_phone(phone)
            
            # Get conversation state
            conversation_state = patient.get("conversation_state") if patient else None
            
            # Initialize state
            state = ConversationState(
                messages=[HumanMessage(content=text)],
                phone_number=phone,
                patient=patient,
                current_stage=conversation_state.get("stage", "initial") if conversation_state else "initial",
                waiting_for=conversation_state.get("waiting_for", "") if conversation_state else "",
                context={
                    "message_type": message_type,
                    "media_id": message_data.get("media_id"),
                    "mime_type": message_data.get("mime_type"),
                    "text": text
                }
            )
            
            # Debug logging
            print(f"🔍 DEBUG: current_stage={state['current_stage']}, waiting_for={state['waiting_for']}, text={text}", flush=True)
            logger.info(f"Processing: stage={state['current_stage']}, waiting_for={state['waiting_for']}, text={text}")
            
            # Run through graph
            if text.upper() == "CARE" or not patient:
                # Start from beginning
                result = await self.graph.ainvoke(state)
            elif state["current_stage"] == "awaiting_menu_selection" and text in ["1", "2", "3", "4", "5"]:
                # Handle menu selection - check this BEFORE generic waiting_for
                print(f"✅ Handling menu choice: {text}", flush=True)
                await self._handle_menu_choice(state, text)
                return  # Important: exit after handling menu choice
            elif state["waiting_for"]:
                # Continue from where we left off (other flows)
                result = await self._continue_flow(state)
            else:
                # Default: show menu or guide
                print(f"⚠️ No match, going to menu_selection", flush=True)
                state["current_stage"] = "menu_selection"
                result = await self.graph.ainvoke(state)
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self.whatsapp.send_message(
                phone,
                "Sorry, something went wrong. Please try again or type *CARE* to see the menu."
            )
    
    async def check_registration(self, state: ConversationState):
        """Check if user is registered"""
        patient = state["patient"]
        
        if not patient:
            state["current_stage"] = "unregistered"
        elif patient.get("approval_status") != "approved":
            state["current_stage"] = "pending"
        else:
            state["current_stage"] = "registered"
        
        return state
    
    def route_after_registration(self, state: ConversationState):
        """Route based on registration status"""
        return state["current_stage"]
    
    async def handle_trigger(self, state: ConversationState):
        """Handle CARE trigger word"""
        phone = state["phone_number"]
        text = state["context"]["text"]
        
        if text.upper() == "CARE":
            if state["current_stage"] == "unregistered":
                await self._send_unregistered_message(phone)
                return state
            elif state["current_stage"] == "pending":
                await self._send_pending_message(phone, state["patient"])
                return state
            else:
                state["current_stage"] = "show_menu"
                return state
        else:
            # Not a trigger, guide them depending on registration status
            if state["current_stage"] != "registered":
                await self.whatsapp.send_message(
                    phone,
                    "👋 Welcome to Remedi Chronic Care!\n\nTo access our services, please type *CARE* to get started."
                )
            else:
                await self.whatsapp.send_message(
                    phone,
                    "Please type *CARE* to open the Remedi menu."
                )
        
        return state
    
    def route_after_trigger(self, state: ConversationState):
        """Route after handling trigger"""
        if state["current_stage"] == "show_menu":
            return "show_menu"
        return "end"
    
    async def show_main_menu(self, state: ConversationState):
        """Display main menu"""
        phone = state["phone_number"]
        patient_name = state["patient"]["patient_name"]
        
        message = f"""🏥 *Remedi Chronic Care Menu*

Hi {patient_name}! How can we help you today?

*1.* 📞 Teleconsultation
*2.* 📄 Upload Report
*3.* 🩺 Log Blood Pressure
*4.* 🏠 Request Home Visit (Colombo)
*5.* 💬 Chat with a Doctor

Reply with a number (1-5) to select an option."""
        
        await self.whatsapp.send_message(phone, message)
        
        # Update patient conversation state
        await self.db.update_patient_conversation_state(
            state["patient"]["patient_id"],
            {"stage": "awaiting_menu_selection", "waiting_for": "menu_choice"}
        )
        
        return state
    
    async def handle_menu_selection(self, state: ConversationState):
        """Handle menu option selection"""
        text = state["context"]["text"]
        
        if text in ["1", "2", "3", "4", "5"]:
            state["context"]["menu_choice"] = text
        else:
            state["context"]["menu_choice"] = "invalid"
        
        return state
    
    def route_menu_selection(self, state: ConversationState):
        """Route based on menu selection"""
        choice = state["context"].get("menu_choice", "invalid")
        return choice
    
    async def teleconsultation_flow(self, state: ConversationState):
        """Handle teleconsultation booking"""
        from handlers.teleconsult_handler import TeleconsultHandler
        
        handler = TeleconsultHandler(self.db, self.whatsapp)
        await handler.handle(state)
        return state
    
    async def upload_report_flow(self, state: ConversationState):
        """Handle report upload"""
        from handlers.report_handler import ReportHandler
        
        handler = ReportHandler(self.db, self.whatsapp)
        await handler.handle(state)
        return state
    
    async def bp_logging_flow(self, state: ConversationState):
        """Handle blood pressure logging"""
        from handlers.bp_handler import BPHandler
        
        handler = BPHandler(self.db, self.whatsapp)
        await handler.handle(state)
        return state
    
    async def _continue_flow(self, state: ConversationState):
        """Continue an existing conversation flow"""
        waiting_for = state["waiting_for"]
        
        # Route to appropriate handler based on waiting_for
        if waiting_for == "report_upload":
            return await self.upload_report_flow(state)
        elif waiting_for == "bp_reading":
            return await self.bp_logging_flow(state)
        elif waiting_for == "appointment_selection":
            return await self.teleconsultation_flow(state)
        elif waiting_for == "doctor_chat":
            return await self.doctor_chat_flow(state)
        else:
            # Unknown state, reset to menu
            return await self.show_main_menu(state)
    
    async def home_visit_flow(self, state: ConversationState):
        """Handle home visit request"""
        from handlers.home_visit_handler import HomeVisitHandler
        
        handler = HomeVisitHandler(self.db, self.whatsapp)
        await handler.handle(state)
        return state
    
    async def doctor_chat_flow(self, state: ConversationState):
        """Handle doctor chat"""
        from handlers.doctor_chat_handler import DoctorChatHandler
        
        handler = DoctorChatHandler(self.db, self.whatsapp)
        await handler.handle(state)
        return state
    
    async def end_conversation(self, state: ConversationState):
        """Clean up and end conversation"""
        # Clear conversation state
        await self.db.update_patient_conversation_state(
            state["patient"]["patient_id"],
            None
        )
        return state
    
    async def _handle_menu_choice(self, state: ConversationState, choice: str):
        """Handle menu option selection directly"""
        if choice == "1":
            await self.teleconsultation_flow(state)
        elif choice == "2":
            await self.upload_report_flow(state)
        elif choice == "3":
            await self.bp_logging_flow(state)
        elif choice == "4":
            await self.home_visit_flow(state)
        elif choice == "5":
            await self.doctor_chat_flow(state)
    
    async def _continue_flow_duplicate_remove_this(self, state: ConversationState):
        """Continue an existing conversation flow"""
        waiting_for = state["waiting_for"]
        
        # Route to appropriate handler based on waiting_for
        if waiting_for == "report_upload":
            return await self.upload_report_flow(state)
        elif waiting_for == "bp_reading":
            return await self.bp_logging_flow(state)
        elif waiting_for == "appointment_selection":
            return await self.teleconsultation_flow(state)
        elif waiting_for == "doctor_chat":
            return await self.doctor_chat_flow(state)
        else:
            # Unknown state, reset to menu
            return await self.show_main_menu(state)
    
    async def _send_unregistered_message(self, phone):
        """Send message to unregistered users"""
        message = f"""🏥 *Welcome to Remedi Chronic Care!*

We're here to help you manage your chronic conditions with:

✅ *Blood Test Reminders* - Never miss important tests
✅ *Personalized Health Tips* - 2x weekly guidance
✅ *Easy Report Tracking* - Upload & get instant feedback
✅ *Doctor Consultations* - Teleconsult & home visits

📋 *Ready to get started?*

Please complete our registration form:
{os.getenv('REGISTRATION_FORM_URL')}

After completing the form and payment approval, you'll have full access to all our chronic care features!

Need help? Contact us at {os.getenv('SUPPORT_PHONE')}"""
        
        await self.whatsapp.send_message(phone, message)
    
    async def _send_pending_message(self, phone, patient):
        """Send message to pending approval users"""
        if patient.get("payment_status") != "completed":
            message = f"""Hi {patient['patient_name']}! 👋

Your enrollment is almost complete! 

To activate your Remedi Chronic Care account, please complete the payment:

{os.getenv('PAYMENT_LINK')}

Once payment is confirmed, you'll get immediate access to all features.

Questions? Contact us at {os.getenv('SUPPORT_PHONE')}"""
        else:
            message = f"""Hi {patient['patient_name']}! 👋

Thank you for your payment! Your application is under review.

You'll receive confirmation within 24 hours, and then you can access all Remedi Chronic Care features.

Questions? Contact us at {os.getenv('SUPPORT_PHONE')}"""
        
        await self.whatsapp.send_message(phone, message)