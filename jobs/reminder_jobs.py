# jobs/reminder_jobs.py
from datetime import datetime, timedelta

from utils.logger import logger

async def send_appointment_reminders(db, whatsapp):
    """Send appointment reminders (24h, 2h, 15min before)"""
    logger.info("Running appointment reminder job")
    
    try:
        now = datetime.utcnow()
        
        # Get appointments in next 24 hours
        upcoming = await db.get_upcoming_appointments(hours_ahead=25)
        
        for appointment in upcoming:
            patient_id = appointment.get("patient_id")
            appointment_id = appointment.get("appointment_id")
            scheduled_date = appointment.get("scheduled_date")
            
            if not all([patient_id, appointment_id, scheduled_date]):
                continue
            
            # Get patient details
            patient = await db.get_patient_by_id(patient_id)
            if not patient:
                continue
            
            phone = patient.get("whatsapp_number")
            time_until = scheduled_date - now
            hours_until = time_until.total_seconds() / 3600
            
            # 24-hour reminder
            if 23.5 <= hours_until <= 24.5 and not appointment.get("reminder_24h_sent"):
                await _send_24h_reminder(whatsapp, phone, patient, appointment)
                await db.update_appointment(appointment_id, {"reminder_24h_sent": True})
                logger.info(f"Sent 24h reminder for {appointment_id}")
            
            # 2-hour reminder
            elif 1.75 <= hours_until <= 2.25 and not appointment.get("reminder_2h_sent"):
                await _send_2h_reminder(whatsapp, phone, patient, appointment)
                await db.update_appointment(appointment_id, {"reminder_2h_sent": True})
                logger.info(f"Sent 2h reminder for {appointment_id}")
            
            # 15-minute reminder (with meeting link)
            elif 0.2 <= hours_until <= 0.3 and not appointment.get("link_sent"):
                await _send_meeting_link(whatsapp, phone, patient, appointment)
                await db.update_appointment(appointment_id, {"link_sent": True})
                logger.info(f"Sent meeting link for {appointment_id}")
        
        logger.info(f"Processed {len(upcoming)} upcoming appointments")
        
    except Exception as e:
        logger.exception(f"Error in appointment reminder job: {str(e)}")


async def _send_24h_reminder(whatsapp, phone, patient, appointment):
    """Send 24-hour reminder"""
    scheduled = appointment['scheduled_date']
    day = scheduled.strftime('%A, %B %d')
    time = appointment.get('scheduled_time', scheduled.strftime('%I:%M %p'))
    doctor = appointment.get('doctor_name', 'your doctor')
    
    message = f"""⏰ *Appointment Reminder - 24 Hours*

Hi {patient['patient_name']}!

Your teleconsultation is tomorrow:

📅 *When:* {day}
🕐 *Time:* {time}
👨‍⚕️ *Doctor:* {doctor}
🆔 *ID:* {appointment['appointment_id']}

📋 *Please prepare:*
• Recent lab reports
• Current medications
• Your questions

You'll receive the meeting link 15 minutes before your appointment.

Need help? Type *CARE*"""
    
    await whatsapp.send_message(phone, message)


async def _send_2h_reminder(whatsapp, phone, patient, appointment):
    """Send 2-hour reminder"""
    scheduled = appointment['scheduled_date']
    time = appointment.get('scheduled_time', scheduled.strftime('%I:%M %p'))
    doctor = appointment.get('doctor_name', 'your doctor')
    
    message = f"""⏰ *Appointment Reminder - 2 Hours*

Hi {patient['patient_name']}!

Your teleconsultation is in 2 hours:

🕐 *Time:* {time}
👨‍⚕️ *Doctor:* {doctor}

🎯 *Final checklist:*
✅ Lab reports ready?
✅ Medications list prepared?
✅ Quiet place for video call?
✅ Stable internet connection?

Meeting link coming in 1 hour 45 minutes!"""
    
    await whatsapp.send_message(phone, message)


async def _send_meeting_link(whatsapp, phone, patient, appointment):
    """Send meeting link 15 minutes before"""
    scheduled = appointment['scheduled_date']
    time = appointment.get('scheduled_time', scheduled.strftime('%I:%M %p'))
    doctor = appointment.get('doctor_name', 'your doctor')
    meeting_link = appointment.get('meeting_link', 'https://meet.remedi.lk/join')
    
    message = f"""🎥 *Your Meeting Link is Ready!*

Hi {patient['patient_name']}!

Your appointment with {doctor} starts at {time}.

🔗 *Join Now:*
{meeting_link}

📱 *Tips for best experience:*
• Join 5 minutes early
• Check camera/microphone
• Have reports ready on screen
• Ensure good lighting

⚠️ Doctor will be available at {time}.

See you soon! 🌟"""
    
    await whatsapp.send_message(phone, message)


async def send_blood_test_reminders(db, whatsapp):
    """Send blood test reminders to patients"""
    logger.info("Running blood test reminder job")
    
    try:
        # Get patients due for blood tests
        today = datetime.utcnow()
        
        # Find patients whose blood test is due within next 3 days
        cursor = db.db.patients.find({
            "approval_status": "approved",
            "next_blood_test_date": {
                "$gte": today,
                "$lte": today + timedelta(days=3)
            },
            "blood_test_reminder_sent": {"$ne": True}
        })
        
        patients = await cursor.to_list(length=None)
        
        for patient in patients:
            phone = patient.get("whatsapp_number")
            test_date = patient.get("next_blood_test_date")
            
            if not phone or not test_date:
                continue
            
            days_until = (test_date - today).days
            
            message = f"""🩸 *Blood Test Reminder*

Hi {patient['patient_name']}!

Your scheduled blood test is due in {days_until} day{'s' if days_until != 1 else ''}.

📅 *Due Date:* {test_date.strftime('%A, %B %d, %Y')}

📋 *Tests Required:*
• Fasting Blood Sugar
• HbA1c
• Lipid Profile
• Kidney Function

⏰ *Important:*
• Fast for 8-12 hours before test
• Take morning medications after test
• Bring previous reports

📍 Visit any Asiri Lab center or request home collection.

Need to schedule? Reply with *BLOOD TEST* or contact support."""
            
            await whatsapp.send_message(phone, message)
            
            # Mark reminder as sent
            await db.db.patients.update_one(
                {"patient_id": patient["patient_id"]},
                {"$set": {"blood_test_reminder_sent": True}}
            )
            
            logger.info(f"Sent blood test reminder to {patient['patient_id']}")
        
        logger.info(f"Processed {len(patients)} blood test reminders")
        
    except Exception as e:
        logger.exception(f"Error in blood test reminder job: {str(e)}")


async def detect_health_patterns(db, whatsapp):
    """Detect concerning health patterns and alert patients"""
    logger.info("Running health pattern detection job")
    
    try:
        # Get all active patients
        cursor = db.db.patients.find({"approval_status": "approved"})
        patients = await cursor.to_list(length=None)
        
        for patient in patients:
            patient_id = patient["patient_id"]
            
            # Check BP patterns
            recent_readings = await db.get_recent_bp_readings(patient_id, days=7)
            
            if len(recent_readings) >= 5:
                # Check for consistently high readings
                high_count = sum(1 for r in recent_readings 
                               if r.get("systolic", 0) >= 140 or r.get("diastolic", 0) >= 90)
                
                if high_count >= 4 and not patient.get("pattern_alert_sent"):
                    phone = patient.get("whatsapp_number")
                    
                    message = f"""⚠️ *Health Pattern Alert*

Hi {patient['patient_name']},

We've noticed your blood pressure readings have been consistently elevated over the past week.

📊 *Your recent trend:*
• {high_count} out of {len(recent_readings)} readings were high

👨‍⚕️ *Recommendation:*
• Schedule a teleconsultation with your doctor
• Review your medications
• Monitor daily and log readings

Would you like to book an appointment now? Reply *1* for Teleconsultation.

This is an automated alert from Remedi Chronic Care."""
                    
                    await whatsapp.send_message(phone, message)
                    
                    # Mark alert as sent
                    await db.db.patients.update_one(
                        {"patient_id": patient_id},
                        {"$set": {"pattern_alert_sent": True, "last_pattern_alert": datetime.utcnow()}}
                    )
                    
                    logger.info(f"Sent pattern alert to {patient_id}")
        
        logger.info("Completed health pattern detection")
        
    except Exception as e:
        logger.exception(f"Error in health pattern detection: {str(e)}")