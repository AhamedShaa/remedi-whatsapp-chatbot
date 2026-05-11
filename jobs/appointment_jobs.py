"""Appointment reminder jobs (24 h, 2 h, 15 min before)."""
from datetime import datetime

from config.settings import settings
from utils.logger import logger


async def send_appointment_reminders(db, whatsapp) -> None:
    """Send tiered reminders for upcoming appointments."""
    logger.info("Running appointment reminder job")
    try:
        now = datetime.utcnow()
        upcoming = await db.get_upcoming_appointments(hours_ahead=25)

        for apt in upcoming:
            patient = await db.get_patient_by_id(apt["patient_id"])
            if not patient:
                continue

            phone = patient["whatsapp_number"]
            hours_until = (apt["scheduled_date"] - now).total_seconds() / 3600

            if 23.5 <= hours_until <= 24.5 and not apt.get("reminder_24h_sent"):
                await _send_24h(whatsapp, phone, patient, apt)
                await db.update_appointment(apt["appointment_id"], {"reminder_24h_sent": True})

            elif 1.75 <= hours_until <= 2.25 and not apt.get("reminder_2h_sent"):
                await _send_2h(whatsapp, phone, patient, apt)
                await db.update_appointment(apt["appointment_id"], {"reminder_2h_sent": True})

            elif 0.2 <= hours_until <= 0.3 and not apt.get("link_sent"):
                await _send_link(whatsapp, phone, patient, apt)
                await db.update_appointment(apt["appointment_id"], {
                    "link_sent": True, "status": "link_sent"
                })

        logger.info(f"Processed {len(upcoming)} appointment reminders")
    except Exception:
        logger.exception("Error in appointment reminder job")


async def _send_24h(whatsapp, phone: str, patient: dict, apt: dict) -> None:
    day = apt["scheduled_date"].strftime("%A, %B %d")
    await whatsapp.send_message(phone, f"""⏰ *Appointment Tomorrow*

Hi {patient['patient_name']}! Your teleconsultation is tomorrow.

📅 {day} at {apt.get('scheduled_time', '')}
👨‍⚕️ {apt.get('doctor_name', 'Your doctor')}
🆔 {apt['appointment_id']}

Prepare your reports and medications list. Meeting link arrives 15 min before.

Need to reschedule? Type *CARE*.""")


async def _send_2h(whatsapp, phone: str, patient: dict, apt: dict) -> None:
    await whatsapp.send_message(phone, f"""⏰ *Appointment in 2 Hours*

Hi {patient['patient_name']}! Your consultation with {apt.get('doctor_name', 'your doctor')} starts in 2 hours at {apt.get('scheduled_time', '')}.

✅ Reports ready?  ✅ Quiet space?  ✅ Stable internet?

Meeting link coming shortly!""")


async def _send_link(whatsapp, phone: str, patient: dict, apt: dict) -> None:
    link = apt.get("meeting_link", "https://meet.remedi.lk/join")
    await whatsapp.send_message(phone, f"""🎥 *Your Meeting Link*

Hi {patient['patient_name']}! Your appointment starts in 15 minutes.

🔗 *Join Now:* {link}
👨‍⚕️ {apt.get('doctor_name', 'Your doctor')}

Having issues? Call {settings.support_phone}""")
