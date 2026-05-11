# DEPRECATED - replaced by ARQ worker in jobs/worker.py
# Kept for reference only - do not import this
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from config.settings import settings
from utils.logger import logger

def start_scheduler(db, whatsapp):
    """Start all background jobs"""
    scheduler = AsyncIOScheduler()
    
    # Blood test reminders - Daily at 9 AM
    scheduler.add_job(
        send_blood_test_reminders,
        CronTrigger(hour=9, minute=0),
        args=[db, whatsapp],
        id="blood_test_reminders",
        name="Send blood test reminders",
        replace_existing=True
    )
    
    # Health tips - Monday and Thursday at 10 AM
    scheduler.add_job(
        send_health_tips,
        CronTrigger(day_of_week='mon,thu', hour=10, minute=0),
        args=[db, whatsapp],
        id="health_tips",
        name="Send health tips",
        replace_existing=True
    )
    
    # Appointment reminders - Every hour
    scheduler.add_job(
        send_appointment_reminders,
        IntervalTrigger(hours=1),
        args=[db, whatsapp],
        id="appointment_reminders",
        name="Send appointment reminders",
        replace_existing=True
    )
    
    # Annual reports - Daily at 8 AM
    scheduler.add_job(
        generate_annual_reports,
        CronTrigger(hour=8, minute=0),
        args=[db, whatsapp],
        id="annual_reports",
        name="Generate annual reports",
        replace_existing=True
    )
    
    # Pattern detection - Every 6 hours
    scheduler.add_job(
        detect_health_patterns,
        IntervalTrigger(hours=6),
        args=[db, whatsapp],
        id="pattern_detection",
        name="Detect health patterns",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Background scheduler started")
    return scheduler


# ==================== JOB FUNCTIONS ====================

async def send_blood_test_reminders(db, whatsapp):
    """Send blood test reminders to patients"""
    try:
        logger.info("Starting blood test reminder job")
        
        # Get tests due in next 7 days
        due_tests = await db.get_due_blood_tests(days_ahead=7)
        
        for item in due_tests:
            patient = item
            test = item["next_blood_tests"]
            
            # Format reminder message
            days_until = (test["due_date"] - datetime.utcnow()).days
            frequency_text = test["frequency"].replace("_", " ").title()
            
            message = f"""📅 *Blood Test Reminder*

Hi {patient['patient_name']}!

Your {frequency_text} blood test for *{test['condition']}* is due in {days_until} days.

*Tests Required:*
• {test['test_name']}

📋 *Important Notes:*
• Fasting may be required (8-12 hours)
• Schedule at any lab convenient for you
• Request home collection if needed

*Ready to upload results?*
Reply with *2* when you have your report.

Questions? Call {settings.support_phone}"""
            
            await whatsapp.send_message(patient["whatsapp_number"], message)
        
        logger.info(f"Sent {len(due_tests)} blood test reminders")
    
    except Exception as e:
        logger.exception(f"Error in blood test reminders job: {str(e)}")


async def send_health_tips(db, whatsapp):
    """Send personalized health tips"""
    try:
        logger.info("Starting health tips job")
        
        from jobs.health_tips import get_health_tip, HEALTH_TIPS
        
        # Get all active patients
        patients_cursor = db.db.patients.find({
            "approval_status": "approved",
            "is_active": True
        })
        
        patients = await patients_cursor.to_list(length=None)
        sent_count = 0
        
        for patient in patients:
            # Check if tip was sent recently (less than 3 days ago)
            last_tip = patient.get("last_health_tip_sent")
            if last_tip and (datetime.utcnow() - last_tip).days < 3:
                continue
            
            # Get random tip for patient's conditions
            conditions = patient.get("health_conditions", [])
            if not conditions:
                continue
            
            tip = get_health_tip(conditions)
            if tip:
                message = f"""💡 *Health Tip*

Hi {patient['patient_name']}!

{tip}

Stay healthy! 🌟

Type *CARE* for menu."""
                
                await whatsapp.send_message(patient["whatsapp_number"], message)
                
                # Update last tip sent time
                await db.update_patient(patient["patient_id"], {
                    "last_health_tip_sent": datetime.utcnow()
                })
                
                sent_count += 1
        
        logger.info(f"Sent {sent_count} health tips")
    
    except Exception as e:
        logger.exception(f"Error in health tips job: {str(e)}")


async def send_appointment_reminders(db, whatsapp):
    """Send appointment reminders at 24h, 2h, and 15 min before"""
    try:
        logger.info("Starting appointment reminders job")
        
        now = datetime.utcnow()
        
        # Get appointments in next 25 hours (for 24h reminders)
        appointments_24h = await db.get_upcoming_appointments(hours_ahead=25)
        
        for apt in appointments_24h:
            time_until = apt["scheduled_date"] - now
            hours_until = time_until.total_seconds() / 3600
            
            patient = await db.get_patient_by_id(apt["patient_id"])
            
            # 24-hour reminder
            if 23 <= hours_until <= 25 and not apt.get("reminder_24h_sent"):
                message = f"""📅 *Appointment Reminder - Tomorrow*

Hi {patient['patient_name']}!

Your teleconsultation is scheduled for tomorrow:

*Date:* {apt['scheduled_date'].strftime('%B %d, %Y')}
*Time:* {apt['scheduled_time']}
*Doctor:* {apt.get('doctor_name', 'TBD')}

📋 *Please prepare:*
• Recent lab reports
• Current medication list
• Questions you want to discuss

Need to reschedule? Reply *RESCHEDULE*"""
                
                await whatsapp.send_message(patient["whatsapp_number"], message)
                await db.update_appointment(apt["appointment_id"], {"reminder_24h_sent": True})
            
            # 2-hour reminder
            elif 1.5 <= hours_until <= 2.5 and not apt.get("reminder_2h_sent"):
                message = f"""⏰ *Appointment in 2 Hours*

Hi {patient['patient_name']}!

Your teleconsultation is in 2 hours:

*Time:* {apt['scheduled_time']}
*Doctor:* {apt.get('doctor_name', 'TBD')}

📱 *Preparation:*
• Be in a quiet location
• Ensure stable internet connection
• Have your reports ready

The video link will arrive 15 minutes before your appointment."""
                
                await whatsapp.send_message(patient["whatsapp_number"], message)
                await db.update_appointment(apt["appointment_id"], {"reminder_2h_sent": True})
            
            # 15-minute reminder with link
            elif 0.2 <= hours_until <= 0.3 and not apt.get("link_sent"):
                meeting_link = apt.get("meeting_link", "https://meet.remedi.lk/join")
                
                message = f"""🎥 *Your Appointment Starts Soon!*

Hi {patient['patient_name']}!

Your teleconsultation starts in 15 minutes.

*Join Link:*
{meeting_link}

*Doctor:* {apt.get('doctor_name', 'TBD')}

Having technical issues? Call {settings.support_phone}

See you soon! 👨‍⚕️"""
                
                await whatsapp.send_message(patient["whatsapp_number"], message)
                await db.update_appointment(apt["appointment_id"], {
                    "link_sent": True,
                    "status": "link_sent"
                })
        
        logger.info("Appointment reminders processed")
    
    except Exception as e:
        logger.exception(f"Error in appointment reminders job: {str(e)}")


async def generate_annual_reports(db, whatsapp):
    """Generate and send annual health reports"""
    try:
        logger.info("Starting annual reports job")
        
        # Find patients with enrollment anniversary today
        today = datetime.utcnow()
        one_year_ago = today.replace(year=today.year - 1)
        
        # Get patients enrolled exactly 1 year ago (±1 day)
        patients_cursor = db.db.patients.find({
            "enrollment_date": {
                "$gte": one_year_ago.replace(hour=0, minute=0, second=0),
                "$lte": one_year_ago.replace(hour=23, minute=59, second=59)
            },
            "approval_status": "approved"
        })
        
        patients = await patients_cursor.to_list(length=None)
        
        for patient in patients:
            # Generate annual report (would call PDF generation service)
            report_data = await generate_patient_annual_report(patient, db)
            
            # Send report
            message = f"""🎉 *Your Annual Health Report*

Hi {patient['patient_name']}!

Congratulations on completing one year with Remedi Chronic Care!

📊 *Your Year in Review:*

• *Test Completion Rate:* {report_data['test_completion_rate']}%
• *Total Consultations:* {report_data['total_consultations']}
• *Reports Uploaded:* {report_data['reports_uploaded']}
• *Days with Controlled Readings:* {report_data['controlled_days']}

Your detailed PDF report is attached.

Thank you for trusting us with your health! 💙

Type *CARE* to continue your journey."""
            
            await whatsapp.send_message(patient["whatsapp_number"], message)
            
            # TODO: Send PDF attachment
            # await whatsapp.send_media(
            #     patient["whatsapp_number"],
            #     "document",
            #     report_data['pdf_url'],
            #     "Annual Health Report"
            # )
        
        logger.info(f"Generated {len(patients)} annual reports")
    
    except Exception as e:
        logger.exception(f"Error in annual reports job: {str(e)}")


async def detect_health_patterns(db, whatsapp):
    """Detect concerning health patterns"""
    try:
        logger.info("Starting pattern detection job")
        
        # Get all active patients
        patients_cursor = db.db.patients.find({
            "approval_status": "approved",
            "is_active": True
        })
        
        patients = await patients_cursor.to_list(length=None)
        
        for patient in patients:
            # Check BP patterns for hypertension patients
            if "Hypertension" in patient.get("health_conditions", []):
                await check_bp_patterns(patient, db, whatsapp)
            
            # Check for missed tests
            await check_missed_tests(patient, db, whatsapp)
        
        logger.info("Pattern detection completed")
    
    except Exception as e:
        logger.exception(f"Error in pattern detection job: {str(e)}")


async def check_bp_patterns(patient, db, whatsapp):
    """Check for concerning BP patterns"""
    readings = await db.get_recent_bp_readings(patient["patient_id"], days=7)
    
    if len(readings) < 3:
        return
    
    # Check for upward trend
    values = [(r['systolic'], r['diastolic']) for r in readings[:3]]
    
    if all(values[i][0] > values[i+1][0] for i in range(len(values)-1)):
        # Upward trend detected
        message = f"""📈 *BP Trend Alert*

Hi {patient['patient_name']},

We've noticed an upward trend in your blood pressure over the past week.

Please review your:
• Medication adherence
• Sodium intake
• Stress levels
• Physical activity

Would you like to schedule a consultation?

Reply *1* for Yes or *2* for No"""
        
        await whatsapp.send_message(patient["whatsapp_number"], message)


async def check_missed_tests(patient, db, whatsapp):
    """Check for overdue tests"""
    tests = patient.get("next_blood_tests", [])
    
    overdue_tests = [
        t for t in tests
        if t["due_date"] < datetime.utcnow() and not t["completed"]
    ]
    
    if overdue_tests:
        message = f"""⚠️ *Overdue Tests*

Hi {patient['patient_name']},

You have {len(overdue_tests)} overdue test(s):

"""
        for test in overdue_tests[:3]:  # Show max 3
            days_overdue = (datetime.utcnow() - test["due_date"]).days
            message += f"• {test['test_name']} ({days_overdue} days overdue)\n"
        
        message += f"""
Please schedule these tests soon for proper health monitoring.

Reply *2* to upload results when ready.

Questions? Call {settings.support_phone}"""
        
        await whatsapp.send_message(patient["whatsapp_number"], message)


async def generate_patient_annual_report(patient, db):
    """Generate annual report data for a patient"""
    # Calculate statistics
    total_tests = len(patient.get("next_blood_tests", []))
    completed_tests = sum(1 for t in patient.get("next_blood_tests", []) if t.get("completed"))
    
    completion_rate = (completed_tests / total_tests * 100) if total_tests > 0 else 0
    
    return {
        "test_completion_rate": round(completion_rate),
        "total_consultations": patient.get("total_consultations", 0),
        "reports_uploaded": patient.get("total_reports_uploaded", 0),
        "controlled_days": patient.get("days_with_controlled_readings", 0),
        "pdf_url": None  # Would generate PDF here
    }