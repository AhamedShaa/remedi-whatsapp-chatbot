"""Blood pressure and health pattern detection."""
from typing import Optional

from config.settings import settings
from utils.logger import logger


def classify_bp(systolic: int, diastolic: int) -> str:
    """Return 'normal' | 'elevated' | 'high' | 'critical'."""
    if systolic > settings.bp_critical_systolic or diastolic > settings.bp_critical_diastolic:
        return "critical"
    if systolic >= settings.bp_warning_systolic_max or diastolic >= settings.bp_warning_diastolic_max:
        return "high"
    if systolic >= settings.bp_normal_systolic_max or diastolic >= settings.bp_normal_diastolic_max:
        return "elevated"
    return "normal"


def detect_upward_trend(readings: list) -> bool:
    """Return True if the last 3 readings show a rising systolic trend."""
    if len(readings) < 3:
        return False
    values = [r["systolic"] for r in readings[:3]]
    return values[0] > values[1] > values[2]


def detect_sustained_elevation(readings: list, threshold: int = 3) -> bool:
    """Return True if `threshold` or more consecutive readings are elevated."""
    if len(readings) < threshold:
        return False
    return all(
        r["systolic"] >= settings.bp_normal_systolic_max
        or r["diastolic"] >= settings.bp_normal_diastolic_max
        for r in readings[:threshold]
    )


async def check_patient_bp_patterns(patient: dict, db) -> Optional[str]:
    """
    Analyse recent BP readings for a patient and return an alert message,
    or None if no concerning pattern was found.
    """
    readings = await db.get_recent_bp_readings(patient["patient_id"], days=7)
    if len(readings) < 3:
        return None

    if detect_upward_trend(readings):
        return (
            f"📈 *BP Trend Alert*\n\nHi {patient['patient_name']}, your blood pressure "
            "has been rising over the last 3 readings. Please review your medications, "
            "sodium intake, and stress levels.\n\nType *1* to book a teleconsultation."
        )

    if detect_sustained_elevation(readings):
        avg_sys = round(sum(r["systolic"] for r in readings[:3]) / 3)
        avg_dia = round(sum(r["diastolic"] for r in readings[:3]) / 3)
        return (
            f"⚠️ *Sustained Elevation Alert*\n\nHi {patient['patient_name']}, your average "
            f"BP over the last 3 readings is {avg_sys}/{avg_dia} mmHg — above target.\n\n"
            "Type *1* to book a teleconsultation."
        )

    return None
