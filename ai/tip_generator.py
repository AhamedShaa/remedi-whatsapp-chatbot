"""Health tip selection and delivery logic."""
import random
from typing import Optional

from jobs.health_tips import HEALTH_TIPS
from utils.logger import logger


def get_tip_for_conditions(conditions: list) -> Optional[str]:
    """Return a random health tip for one of the patient's conditions."""
    if not conditions:
        return None
    available = [c for c in conditions if c in HEALTH_TIPS]
    if not available:
        return None
    condition = random.choice(available)
    return random.choice(HEALTH_TIPS[condition])


def format_tip_message(patient_name: str, tip: str) -> str:
    return (
        f"💡 *Health Tip for You, {patient_name}!*\n\n"
        f"{tip}\n\n"
        "Stay healthy! 🌟\n\nType *CARE* for the menu."
    )
