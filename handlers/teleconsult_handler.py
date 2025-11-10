# handlers/teleconsult_handler.py
import logging
from datetime import datetime, timedelta
import uuid
import os

logger = logging.getLogger(__name__)

class TeleconsultHandler:
    def __init__(self, db, whatsapp):
        self.db = db
        self.whatsapp = whatsapp
    
    async def handle(self, state):
        """Handle teleconsultation booking"""
        phone = state["phone_number"]
        patient = state["patient"]
        text = state["context"]["text"]
        waiting_for = state["waiting_for"]
        
        if not waiting_for or waiting_for != "appointment_selection":
            # Show available slots
            await self._show_available_slots(phone, patient)
            # Update state
            await self.db.update_patient_conversation_state(
                patient["patient_id"],
                {"stage": "teleconsult", "waiting_for": "appointment_selection"}
            )
        else:
            # User selected a slot
            await self._book_appointment(state, text)
        
        return state
    
    async def _show_available_slots(self, phone, patient):
        """Display available appointment slots"""
        # Generate all possible slots
        all_slots = self._generate_slots()
        
        # Filter out booked slots
        available_slots = await self._filter_available_slots(all_slots)
        
        if not available_slots:
            await self.whatsapp.send_message(
                phone,
                "❌ Sorry, no slots available in the next 7 days. Please try again later or contact support."
            )
            await self.db.update_patient_conversation_state(patient["patient_id"], None)
            return
        
        # Show only next 15 available slots for better UX
        display_slots = available_slots[:15]
        
        message = f"""📞 *Book Teleconsultation*

Hi {patient['patient_name']}!

*Next Available Slots:*

"""
        for i, slot in enumerate(display_slots, 1):
            day = slot['date'].strftime('%A, %b %d')
            message += f"*{i}.* {day} at {slot['time']} - {slot['doctor']}\n"
        
        message += f"""
💡 Reply with slot number (1-{len(display_slots)}) to book.
📅 30-minute consultation per slot.

Or reply *CANCEL* to go back."""
        
        await self.whatsapp.send_message(phone, message)
    
    async def _filter_available_slots(self, slots):
        """Filter out already booked slots"""
        available = []
        
        for slot in slots:
            # Check if slot is already booked
            existing = await self.db.db.appointments.find_one({
                "scheduled_date": slot['date'],
                "status": {"$nin": ["cancelled", "completed"]}
            })
            
            if not existing:
                available.append(slot)
        
        return available
    
    def _generate_slots(self, days_ahead=7):
        """Generate available appointment slots (30-minute intervals, 9 AM - 5 PM)"""
        slots = []
        start_date = datetime.now() + timedelta(days=1)  # Start from tomorrow
        
        # Doctor rotation for variety
        doctors = ['Dr. Silva', 'Dr. Perera', 'Dr. Fernando']
        
        # Generate slots for next N days
        for day in range(days_ahead):
            current_date = start_date + timedelta(days=day)
            
            # Skip weekends
            if current_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                continue
            
            # Generate 30-minute slots from 9 AM to 5 PM
            for hour in range(9, 17):  # 9 AM to 4:30 PM (last slot ends at 5 PM)
                for minute in [0, 30]:
                    slot_time = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                    # Skip past times for today
                    if slot_time <= datetime.now():
                        continue
                    
                    # Assign doctor (rotate for variety)
                    doctor_index = (hour + minute // 30) % len(doctors)
                    
                    # Format time display
                    time_str = slot_time.strftime('%I:%M %p')
                    
                    slots.append({
                        'date': slot_time,
                        'time': time_str,
                        'doctor': doctors[doctor_index],
                        'duration_minutes': 30
                    })
        
        return slots
    
    async def _book_appointment(self, state, text):
        """Book selected appointment"""
        phone = state["phone_number"]
        patient = state["patient"]
        
        # Check for cancel
        if text.upper() == "CANCEL":
            await self.whatsapp.send_message(
                phone,
                "Booking cancelled. Type *CARE* to see the menu."
            )
            await self.db.update_patient_conversation_state(patient["patient_id"], None)
            return
        
        # Validate slot selection
        try:
            slot_num = int(text.strip())
            
            # Get available slots (same as displayed to user)
            all_slots = self._generate_slots()
            available_slots = await self._filter_available_slots(all_slots)
            display_slots = available_slots[:15]
            
            if slot_num < 1 or slot_num > len(display_slots):
                await self.whatsapp.send_message(
                    phone,
                    f"❌ Invalid selection. Please choose a number between 1 and {len(display_slots)}."
                )
                return
            
            selected_slot = display_slots[slot_num - 1]
            
            # Double-check slot is still available (race condition protection)
            still_available = await self.db.db.appointments.find_one({
                "scheduled_date": selected_slot['date'],
                "status": {"$nin": ["cancelled", "completed"]}
            })
            
            if still_available:
                await self.whatsapp.send_message(
                    phone,
                    "❌ Sorry, this slot was just booked by someone else. Please choose another slot.\n\nType *1* to see available slots again."
                )
                return
            
            # Create appointment
            appointment_id = await self._create_appointment(patient, selected_slot)
            
            # Send confirmation
            await self._send_booking_confirmation(phone, patient, selected_slot, appointment_id)
            
            # Update patient stats (if method exists)
            try:
                await self.db.increment_patient_stat(patient["patient_id"], "total_consultations")
            except AttributeError:
                pass  # Method doesn't exist yet
            
            # Clear conversation state
            await self.db.update_patient_conversation_state(patient["patient_id"], None)
            
        except ValueError:
            await self.whatsapp.send_message(
                phone,
                "❌ Please enter a valid number or *CANCEL* to go back."
            )
    
    async def _create_appointment(self, patient, slot):
        """Create appointment in database"""
        appointment_id = f"APT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        appointment = {
            "appointment_id": appointment_id,
            "patient_id": patient["patient_id"],
            "type": "teleconsult",
            "scheduled_date": slot['date'],
            "scheduled_time": slot['time'],
            "doctor_name": slot['doctor'],
            "status": "scheduled",
            "meeting_link": f"https://meet.remedi.lk/{appointment_id}",
            "reminder_24h_sent": False,
            "reminder_2h_sent": False,
            "link_sent": False
        }
        
        await self.db.create_appointment(appointment)
        return appointment_id
    
    async def _send_booking_confirmation(self, phone, patient, slot, appointment_id):
        """Send appointment confirmation message"""
        day = slot['date'].strftime('%A, %B %d, %Y')
        
        support_phone = os.getenv('SUPPORT_PHONE', '94706112112')
        
        message = f"""✅ *Appointment Confirmed!*

Hi {patient['patient_name']}, your teleconsultation is booked!

📅 *Details:*
• Date: {day}
• Time: {slot['time']} (30 min)
• Doctor: {slot['doctor']}
• ID: {appointment_id}

⏰ *Reminders:*
You'll receive automatic reminders:
• 24 hours before appointment
• 2 hours before appointment
• Meeting link 15 minutes before

📋 *Please Prepare:*
• Recent lab reports
• Current medications list
• Questions for the doctor
• Quiet place for video call

🔗 *Meeting Link:*
Will be sent 15 minutes before your appointment.

Need to reschedule? Contact: {support_phone}

Type *CARE* for main menu."""
        
        await self.whatsapp.send_message(phone, message)


# handlers/home_visit_handler.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class HomeVisitHandler:
    def __init__(self, db, whatsapp):
        self.db = db
        self.whatsapp = whatsapp
    
    async def handle(self, state):
        """Handle home visit request"""
        phone = state["phone_number"]
        patient = state["patient"]
        
        await self._request_home_visit(phone, patient)
        
        # Clear conversation state
        await self.db.update_patient_conversation_state(patient["patient_id"], None)
        
        return state
    
    async def _request_home_visit(self, phone, patient):
        """Process home visit request"""
        message = f"""🏠 *Home Visit Request Received*

Hi {patient['patient_name']}!

Your request has been received. A doctor from *Hello Doctor* will contact you within *2 hours* to schedule your home visit.

📋 *Please have ready:*
• Your Patient ID: {patient['patient_id']}
• Complete address in Colombo
• Preferred time slot
• Reason for visit

📞 *Contact:*
They'll call: {patient['whatsapp_number']}

⏰ *What's Next?*
1. Hello Doctor team will call you
2. Confirm address and time
3. Doctor visits your home
4. Consultation and treatment

💰 *Payment:*
Payment details will be shared during the call.

Need urgent help? Call us now:
{os.getenv('EMERGENCY_PHONE')}

Type *CARE* for main menu."""
        
        await self.whatsapp.send_message(phone, message)
        
        # Notify Hello Doctor team (integrate with their API)
        await self._notify_hello_doctor_team(patient)
        
        # Log request
        logger.info(f"Home visit requested by patient {patient['patient_id']}")
    
    async def _notify_hello_doctor_team(self, patient):
        """Notify Hello Doctor team about the request"""
        # This would integrate with Hello Doctor's API
        # For now, we'll just log it
        
        notification_data = {
            "patient_id": patient["patient_id"],
            "patient_name": patient["patient_name"],
            "phone": patient["whatsapp_number"],
            "address": patient.get("address", "Not provided"),
            "conditions": patient.get("health_conditions", []),
            "request_time": datetime.utcnow(),
            "priority": "high" if patient.get("is_high_risk") else "normal"
        }
        
        logger.info(f"Hello Doctor notification: {notification_data}")
        
        # TODO: Implement actual API call
        # await hello_doctor_api.create_visit_request(notification_data)


# handlers/doctor_chat_handler.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DoctorChatHandler:
    def __init__(self, db, whatsapp):
        self.db = db
        self.whatsapp = whatsapp
    
    async def handle(self, state):
        """Handle doctor chat functionality"""
        phone = state["phone_number"]
        patient = state["patient"]
        text = state["context"]["text"]
        waiting_for = state["waiting_for"]
        
        if not waiting_for or waiting_for != "doctor_chat":
            # First time - check doctor availability
            await self._initiate_chat(phone, patient)
        else:
            # Ongoing chat - forward message to doctor
            await self._forward_to_doctor(state, text)
        
        return state
    
    async def _initiate_chat(self, phone, patient):
        """Initiate chat with doctor"""
        # Check if any doctor is available
        doctor_available = await self._check_doctor_availability()
        
        if doctor_available:
            await self._connect_to_doctor(phone, patient, doctor_available)
        else:
            await self._send_unavailable_message(phone, patient)
    
    async def _check_doctor_availability(self):
        """Check if any doctor is currently available"""
        # This would integrate with your doctor dashboard
        # For now, simulate availability
        
        # In production, query doctor availability from database
        # doctors = await self.db.db.doctors.find({"status": "online"}).to_list(1)
        
        # Simulate doctor availability (for demo)
        import random
        if random.random() > 0.5:  # 50% chance
            return {
                "name": "Dr. Silva",
                "id": "DOC-001",
                "specialty": "General Practitioner"
            }
        return None
    
    async def _connect_to_doctor(self, phone, patient, doctor):
        """Connect patient to available doctor"""
        message = f"""💬 *Chat with Doctor*

Hi {patient['patient_name']}!

*{doctor['name']}* ({doctor['specialty']}) has joined the chat.

You can now ask your health questions. The doctor will respond shortly.

📝 Please describe your concern clearly.

Type *END CHAT* to finish the consultation."""
        
        await self.whatsapp.send_message(phone, message)
        
        # Update conversation state to doctor chat mode
        await self.db.update_patient_conversation_state(
            patient["patient_id"],
            {
                "stage": "doctor_chat",
                "waiting_for": "doctor_chat",
                "doctor_id": doctor['id'],
                "doctor_name": doctor['name'],
                "chat_started": datetime.utcnow()
            }
        )
        
        # Notify doctor dashboard
        await self._notify_doctor_dashboard(patient, doctor)
    
    async def _send_unavailable_message(self, phone, patient):
        """Send message when no doctor available"""
        message = f"""💬 *Doctor Chat*

Hi {patient['patient_name']}!

All doctors are currently busy with other patients.

*Estimated wait time:* 15 minutes

*What would you like to do?*

*1.* ⏳ Wait (we'll notify when available)
*2.* 📞 Schedule teleconsultation instead
*3.* 📝 Leave a message for callback

Reply with 1, 2, or 3."""
        
        await self.whatsapp.send_message(phone, message)
        
        # Add to queue
        await self._add_to_chat_queue(patient)
    
    async def _forward_to_doctor(self, state, text):
        """Forward patient message to doctor"""
        phone = state["phone_number"]
        patient = state["patient"]
        conv_state = state["patient"].get("conversation_state", {})
        
        # Check for end chat command
        if text.upper() == "END CHAT":
            await self._end_chat(phone, patient)
            return
        
        # Save message to conversation history
        if not patient.get("conversation_history"):
            patient["conversation_history"] = []
        
        message_entry = {
            "timestamp": datetime.utcnow(),
            "sender": "patient",
            "message": text
        }
        
        await self.db.db.patients.update_one(
            {"patient_id": patient["patient_id"]},
            {"$push": {"conversation_history": message_entry}}
        )
        
        # Forward to doctor dashboard
        await self._notify_doctor_dashboard(patient, {
            "id": conv_state.get("doctor_id"),
            "name": conv_state.get("doctor_name")
        }, text)
        
        # Send acknowledgment
        await self.whatsapp.send_message(
            phone,
            "✓ Message sent to doctor. They'll respond shortly..."
        )
        
        logger.info(f"Chat message from {patient['patient_id']}: {text}")
    
    async def _end_chat(self, phone, patient):
        """End chat session"""
        message = f"""💬 *Chat Ended*

Thank you for using Remedi Doctor Chat!

If you need further assistance:
• Type *CARE* for main menu
• Call {os.getenv('SUPPORT_PHONE')}

Take care! 🌟"""
        
        await self.whatsapp.send_message(phone, message)
        
        # Clear conversation state
        await self.db.update_patient_conversation_state(patient["patient_id"], None)
        
        # Archive chat history (optional)
        # await self._archive_chat(patient)
    
    async def _add_to_chat_queue(self, patient):
        """Add patient to waiting queue"""
        queue_entry = {
            "patient_id": patient["patient_id"],
            "patient_name": patient["patient_name"],
            "phone": patient["whatsapp_number"],
            "conditions": patient.get("health_conditions", []),
            "is_high_risk": patient.get("is_high_risk", False),
            "queued_at": datetime.utcnow(),
            "status": "waiting"
        }
        
        # In production, save to queue collection
        # await self.db.db.chat_queue.insert_one(queue_entry)
        
        logger.info(f"Added {patient['patient_id']} to chat queue")
    
    async def _notify_doctor_dashboard(self, patient, doctor, message=None):
        """Notify doctor dashboard about chat request/message"""
        notification = {
            "type": "chat_request" if not message else "new_message",
            "patient_id": patient["patient_id"],
            "patient_name": patient["patient_name"],
            "conditions": patient.get("health_conditions", []),
            "is_high_risk": patient.get("is_high_risk", False),
            "doctor_id": doctor.get("id"),
            "message": message,
            "timestamp": datetime.utcnow()
        }
        
        # In production, this would:
        # 1. Send websocket notification to doctor dashboard
        # 2. Send push notification to doctor's mobile app
        # 3. Log in doctor notification queue
        
        logger.info(f"Doctor notification: {notification}")
        
        # TODO: Implement actual notification system
        # await doctor_websocket.send_notification(doctor['id'], notification)
        # await push_notification.send_to_doctor(doctor['id'], notification)