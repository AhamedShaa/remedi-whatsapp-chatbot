"""Annual patient report generation."""
from datetime import datetime, timedelta

from utils.logger import logger


async def generate_annual_reports(db, whatsapp) -> None:
    """Send annual health summary to patients on their enrollment anniversary."""
    logger.info("Running annual reports job")
    try:
        today = datetime.utcnow()
        one_year_ago = today.replace(year=today.year - 1)

        cursor = db.db.patients.find({
            "enrollment_date": {
                "$gte": one_year_ago.replace(hour=0, minute=0, second=0),
                "$lte": one_year_ago.replace(hour=23, minute=59, second=59),
            },
            "approval_status": "approved",
        })
        patients = await cursor.to_list(length=None)

        for patient in patients:
            summary = _build_summary(patient)
            message = f"""🎉 *Your Annual Health Report*

Hi {patient['patient_name']}! Congratulations on one year with Remedi Chronic Care!

📊 *Year in Review:*
• Test Completion Rate: {summary['completion_rate']}%
• Total Consultations: {summary['consultations']}
• Reports Uploaded: {summary['reports']}

Thank you for trusting us with your health journey! 💙

Type *CARE* to continue."""
            await whatsapp.send_message(patient["whatsapp_number"], message)

        logger.info(f"Sent {len(patients)} annual reports")
    except Exception:
        logger.exception("Error in annual reports job")


def _build_summary(patient: dict) -> dict:
    tests = patient.get("next_blood_tests", [])
    completed = sum(1 for t in tests if t.get("completed"))
    rate = round(completed / len(tests) * 100) if tests else 0
    return {
        "completion_rate": rate,
        "consultations": patient.get("total_consultations", 0),
        "reports": patient.get("total_reports_uploaded", 0),
    }
