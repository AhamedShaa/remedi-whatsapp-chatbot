# handlers/teleconsult_handler.py
from datetime import datetime, timedelta
import uuid
from config.settings import settings
from utils.logger import logger

class TeleconsultHandler:
    def __init__(self, db, whatsapp, redis_client):
        self.db = db
        self.whatsapp = whatsapp
        self.redis = redis_client
    
    async def handle(self, state):
        """Handle teleconsultation booking"""
        phone = state["phone_number"]
        patient = state["patient"]
        text = state["context"]["text"]
        waiting_for = state["waiting_for"]
        
        if not waiting_for or waiting_for != "appointment_selection":
            # Show available slots
            await self._show_available_slots(phone, patient)
            await self.redis.set_conversation_state(
                phone,
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
            await self.redis.clear_conversation_state(phone)
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
            await self.redis.clear_conversation_state(phone)
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
            
            await self.redis.clear_conversation_state(phone)

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
        
        support_phone = settings.support_phone or '94706112112'
        
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
