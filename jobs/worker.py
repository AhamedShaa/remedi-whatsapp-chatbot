"""jobs/worker.py — ARQ async job worker for Remedi Chronic Care.

Run with:
    python jobs/worker.py
    # or via arq CLI:
    arq jobs.worker.WorkerSettings
"""
import json
import random
from datetime import datetime

from arq import cron
from arq.connections import RedisSettings

from config.settings import settings
from utils.logger import logger


# ── Topic lists for AI health tip generation ─────────────────────────────────

_TOPICS: dict[str, list[str]] = {
    "Diabetes": [
        "diet", "exercise", "foot care",
        "blood sugar monitoring", "medication timing",
    ],
    "Hypertension": [
        "sodium reduction", "stress management",
        "sleep hygiene", "home BP monitoring",
    ],
    "High Cholesterol": [
        "heart healthy fats", "fiber intake",
        "exercise", "weight management",
    ],
    "Thyroid Disorder": [
        "medication timing", "symptom tracking",
        "iodine intake", "energy management",
    ],
    "Kidney Disease": [
        "fluid intake", "protein guidelines",
        "medication precautions", "monitoring output",
    ],
}

_DEFAULT_TOPICS = [
    "healthy habits", "sleep quality", "hydration",
    "exercise", "stress management",
]


# ── PART 1: Job functions ─────────────────────────────────────────────────────

async def send_blood_test_reminders(ctx: dict) -> None:
    """Send WhatsApp reminders for blood tests due in the next 7 days."""
    db = ctx["db"]
    whatsapp = ctx["whatsapp"]
    sent = 0

    try:
        due_tests = await db.get_due_blood_tests(days_ahead=7)

        for item in due_tests:
            phone = item.get("whatsapp_number")
            if not phone:
                continue

            patient_name = item.get("patient_name", "there")
            test = item.get("next_blood_tests", {})
            test_name = test.get("test_name", "blood test")
            condition = test.get("condition", "your condition")

            message = (
                f"🩸 *Blood Test Reminder*\n\n"
                f"Hi {patient_name}!\n\n"
                f"Your *{test_name}* test is due in 7 days.\n"
                f"This test monitors your *{condition}*.\n\n"
                f"You can book at any lab or request home collection.\n\n"
                f"Ready to upload results?\n"
                f"Type *CARE* and select option 2."
            )
            await whatsapp.send_message(phone, message)
            sent += 1

        logger.info(f"send_blood_test_reminders: sent {sent} reminders")

    except Exception:
        logger.opt(exception=True).error("send_blood_test_reminders failed")


async def send_health_tips(ctx: dict) -> None:
    """Send AI-generated personalised health tips to all approved patients."""
    db = ctx["db"]
    whatsapp = ctx["whatsapp"]
    ai_client = ctx["ai_client"]
    sent = 0

    try:
        cursor = db.db.patients.find({"approval_status": "approved"})
        patients = await cursor.to_list(length=None)

        for patient in patients:
            phone = patient.get("whatsapp_number")
            conditions = patient.get("health_conditions", [])
            if not phone or not conditions:
                continue

            condition = random.choice(conditions)
            topics = _TOPICS.get(condition, _DEFAULT_TOPICS)
            topic = random.choice(topics)

            try:
                tip = await ai_client.complete(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a health educator for a Sri Lankan chronic care platform. "
                                "Generate ONE concise health tip (2-3 sentences max) that is "
                                "practical and culturally relevant for Sri Lankan patients."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Generate a health tip for a patient with {condition}. "
                                f"Topic: {topic}. Be friendly and encouraging."
                            ),
                        },
                    ],
                    trace_name="health_tip",
                )
            except Exception:
                logger.opt(exception=True).warning(
                    f"AI tip generation failed for patient {patient.get('patient_id')} — skipping"
                )
                continue

            message = (
                f"💡 *Health Tip — {condition}*\n\n"
                f"Hi {patient.get('patient_name', 'there')}!\n\n"
                f"{tip.strip()}\n\n"
                f"Stay healthy! 🌟\n\n"
                f"Type *CARE* for menu."
            )
            await whatsapp.send_message(phone, message)
            await db.update_patient(
                patient["patient_id"],
                {"last_health_tip_sent": datetime.utcnow()},
            )
            sent += 1

        logger.info(f"send_health_tips: sent {sent} tips")

    except Exception:
        logger.opt(exception=True).error("send_health_tips failed")


async def send_appointment_reminders(ctx: dict) -> None:
    """Send 24h, 2h, and 15-min reminders for upcoming appointments."""
    db = ctx["db"]
    whatsapp = ctx["whatsapp"]
    sent_24h = sent_2h = sent_15m = 0

    try:
        now = datetime.utcnow()
        appointments = await db.get_upcoming_appointments(hours_ahead=25)

        for apt in appointments:
            patient_id = apt.get("patient_id")
            appointment_id = apt.get("appointment_id")
            scheduled_date = apt.get("scheduled_date")

            if not all([patient_id, appointment_id, scheduled_date]):
                continue

            patient = await db.get_patient_by_id(patient_id)
            if not patient:
                continue

            phone = patient.get("whatsapp_number")
            if not phone:
                continue

            hours_until = (scheduled_date - now).total_seconds() / 3600
            patient_name = patient["patient_name"]
            time_str = apt.get("scheduled_time", scheduled_date.strftime("%I:%M %p"))
            doctor = apt.get("doctor_name", "your doctor")

            if 23 <= hours_until <= 25 and not apt.get("reminder_24h_sent"):
                message = (
                    f"⏰ *Appointment Reminder — 24 Hours*\n\n"
                    f"Hi {patient_name}!\n\n"
                    f"Your teleconsultation is tomorrow:\n\n"
                    f"📅 *When:* {scheduled_date.strftime('%A, %B %d')}\n"
                    f"🕐 *Time:* {time_str}\n"
                    f"👨‍⚕️ *Doctor:* {doctor}\n"
                    f"🆔 *ID:* {appointment_id}\n\n"
                    f"📋 *Please prepare:*\n"
                    f"• Recent lab reports\n"
                    f"• Current medications\n"
                    f"• Your questions\n\n"
                    f"Meeting link arrives 15 minutes before.\n\n"
                    f"Need help? Type *CARE*"
                )
                await whatsapp.send_message(phone, message)
                await db.update_appointment(appointment_id, {"reminder_24h_sent": True})
                sent_24h += 1

            elif 1.75 <= hours_until <= 2.25 and not apt.get("reminder_2h_sent"):
                message = (
                    f"⏰ *Appointment in 2 Hours*\n\n"
                    f"Hi {patient_name}!\n\n"
                    f"Your teleconsultation is in 2 hours:\n\n"
                    f"🕐 *Time:* {time_str}\n"
                    f"👨‍⚕️ *Doctor:* {doctor}\n\n"
                    f"🎯 *Final checklist:*\n"
                    f"✅ Lab reports ready?\n"
                    f"✅ Medications list prepared?\n"
                    f"✅ Quiet place for video call?\n"
                    f"✅ Stable internet connection?\n\n"
                    f"Meeting link arriving shortly!"
                )
                await whatsapp.send_message(phone, message)
                await db.update_appointment(appointment_id, {"reminder_2h_sent": True})
                sent_2h += 1

            elif 0.2 <= hours_until <= 0.3 and not apt.get("link_sent"):
                meeting_link = apt.get("meeting_link", "https://meet.remedi.lk/join")
                message = (
                    f"🎥 *Your Meeting Link is Ready!*\n\n"
                    f"Hi {patient_name}!\n\n"
                    f"Your appointment with {doctor} starts at {time_str}.\n\n"
                    f"🔗 *Join Now:*\n{meeting_link}\n\n"
                    f"• Join 5 minutes early\n"
                    f"• Check camera/microphone\n"
                    f"• Have reports ready on screen\n\n"
                    f"See you soon! 🌟"
                )
                await whatsapp.send_message(phone, message)
                await db.update_appointment(
                    appointment_id, {"link_sent": True, "status": "link_sent"}
                )
                sent_15m += 1

        logger.info(
            f"send_appointment_reminders: 24h={sent_24h} 2h={sent_2h} 15min={sent_15m}"
        )

    except Exception:
        logger.opt(exception=True).error("send_appointment_reminders failed")


async def check_bp_patterns(ctx: dict) -> None:
    """AI-powered BP trend analysis — alert patients with concerning patterns."""
    db = ctx["db"]
    whatsapp = ctx["whatsapp"]
    ai_client = ctx["ai_client"]
    checked = alerted = 0

    try:
        cursor = db.db.patients.find({"approval_status": "approved"})
        patients = await cursor.to_list(length=None)

        for patient in patients:
            patient_id = patient["patient_id"]
            phone = patient.get("whatsapp_number")
            if not phone:
                continue

            readings = await db.get_recent_bp_readings(patient_id, days=7)
            if len(readings) < 3:
                continue

            checked += 1
            reading_summary = [
                {
                    "systolic": r.get("systolic"),
                    "diastolic": r.get("diastolic"),
                    "date": (
                        r["reading_date"].isoformat()
                        if isinstance(r.get("reading_date"), datetime)
                        else str(r.get("reading_date", ""))
                    ),
                }
                for r in readings
            ]
            conditions = patient.get("health_conditions", [])

            try:
                raw = await ai_client.complete(
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Analyze these BP readings for concerning trends.\n"
                                f"Readings: {json.dumps(reading_summary)}\n"
                                f"Patient conditions: {conditions}\n\n"
                                "Return JSON only:\n"
                                '{"concerning": true/false, '
                                '"reason": "explanation", '
                                '"action": "recommended action"}'
                            ),
                        }
                    ],
                    trace_name="bp_pattern_analysis",
                )
            except Exception:
                logger.opt(exception=True).warning(
                    f"BP AI analysis failed for {patient_id} — skipping"
                )
                continue

            try:
                clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
                analysis = json.loads(clean)
            except json.JSONDecodeError:
                logger.warning(f"BP pattern JSON parse failed for {patient_id}: {raw[:80]!r}")
                continue

            if analysis.get("concerning"):
                reason = analysis.get("reason", "elevated readings detected")
                action = analysis.get("action", "Please consult your doctor")
                message = (
                    f"📈 *BP Pattern Alert*\n\n"
                    f"Hi {patient['patient_name']},\n\n"
                    f"We've noticed a concerning trend in your recent blood pressure readings.\n\n"
                    f"*Observation:* {reason}\n\n"
                    f"*Recommended action:* {action}\n\n"
                    f"To book a consultation:\n"
                    f"Type *CARE* and reply *1* for Teleconsultation.\n\n"
                    f"Emergency? Call {settings.emergency_phone}"
                )
                await whatsapp.send_message(phone, message)
                alerted += 1

        logger.info(f"check_bp_patterns: checked {checked} patients, alerted {alerted}")

    except Exception:
        logger.opt(exception=True).error("check_bp_patterns failed")


async def generate_annual_reports(ctx: dict) -> None:
    """Notify patients on their enrollment anniversary and trigger report generation."""
    db = ctx["db"]
    whatsapp = ctx["whatsapp"]
    triggered = 0

    try:
        today = datetime.utcnow()

        # Match patients whose enrollment_date falls on today's month+day (any year)
        cursor = db.db.patients.find(
            {
                "$expr": {
                    "$and": [
                        {"$eq": [{"$month": "$enrollment_date"}, today.month]},
                        {"$eq": [{"$dayOfMonth": "$enrollment_date"}, today.day]},
                    ]
                },
                "approval_status": "approved",
            }
        )
        patients = await cursor.to_list(length=None)

        for patient in patients:
            phone = patient.get("whatsapp_number")
            if not phone:
                continue

            enrollment_date = patient.get("enrollment_date")
            years = (today.year - enrollment_date.year) if enrollment_date else 1

            tests = patient.get("next_blood_tests", [])
            total_tests = len(tests)
            completed_tests = sum(1 for t in tests if t.get("completed"))
            completion_rate = round(completed_tests / total_tests * 100) if total_tests else 0

            message = (
                f"🎉 *{'Happy Anniversary' if years > 1 else 'One Year'} with Remedi!*\n\n"
                f"Hi {patient.get('patient_name', 'there')}!\n\n"
                f"Congratulations on {years} year{'s' if years > 1 else ''} of proactive "
                f"health management with Remedi Chronic Care!\n\n"
                f"📊 *Your Year in Review:*\n"
                f"• Test completion rate: {completion_rate}%\n"
                f"• Total consultations: {patient.get('total_consultations', 0)}\n"
                f"• Reports uploaded: {patient.get('total_reports_uploaded', 0)}\n\n"
                f"Your detailed annual report is being prepared and will arrive shortly.\n\n"
                f"Thank you for trusting us with your health journey! 💙\n\n"
                f"Type *CARE* to continue."
            )
            await whatsapp.send_message(phone, message)
            triggered += 1

        logger.info(f"generate_annual_reports: triggered {triggered} reports")

    except Exception:
        logger.opt(exception=True).error("generate_annual_reports failed")


# ── PART 2: Startup and shutdown ──────────────────────────────────────────────

async def startup(ctx: dict) -> None:
    """Initialise shared resources into the ARQ job context."""
    from database.mongodb import MongoDB
    from utils.whatsapp_client import WhatsAppClient
    from ai.client import ai_client as _ai_client

    db = MongoDB()
    await db.connect()
    ctx["db"] = db
    ctx["whatsapp"] = WhatsAppClient()
    ctx["ai_client"] = _ai_client
    # ctx["redis"] is pre-populated by ARQ with the connection pool
    logger.info("ARQ worker started")


async def shutdown(ctx: dict) -> None:
    """Clean up shared resources."""
    await ctx["db"].disconnect()
    logger.info("ARQ worker stopped")


# ── PART 3: WorkerSettings ────────────────────────────────────────────────────

class WorkerSettings:
    functions = [
        send_blood_test_reminders,
        send_health_tips,
        send_appointment_reminders,
        check_bp_patterns,
        generate_annual_reports,
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # All times are Sri Lanka time (UTC+5:30)
    cron_jobs = [
        cron(send_blood_test_reminders, hour=8,  minute=0),               # 8am daily
        cron(send_health_tips,          hour=9,  minute=0, weekday={0, 3}),  # Mon+Thu 9am
        cron(send_appointment_reminders,         minute=0),               # every hour :00
        cron(check_bp_patterns,         hour=20, minute=0),               # 8pm daily
        cron(generate_annual_reports,   hour=7,  minute=0),               # 7am daily
    ]

    max_jobs = 10
    job_timeout = 300   # 5 minutes per job
    keep_result = 3600  # keep results 1 hour


# ── PART 4: Entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    from arq import run_worker
    run_worker(WorkerSettings)
