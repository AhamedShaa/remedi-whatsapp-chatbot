from datetime import datetime
from config.settings import settings
from utils.logger import logger


class HomeVisitHandler:
    def __init__(self, db, whatsapp, redis_client):
        self.db = db
        self.whatsapp = whatsapp
        self.redis = redis_client

    async def handle(self, state):
        """Handle home visit request."""
        phone = state["phone_number"]
        patient = state["patient"]
        await self._request_home_visit(phone, patient)
        await self.redis.clear_conversation_state(phone)
        return state

    async def _request_home_visit(self, phone: str, patient: dict) -> None:
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
{settings.emergency_phone}

Type *CARE* for main menu."""

        await self.whatsapp.send_message(phone, message)
        await self._notify_hello_doctor_team(patient)
        logger.info(f"Home visit requested by patient {patient['patient_id']}")

    async def _notify_hello_doctor_team(self, patient: dict) -> None:
        notification_data = {
            "patient_id": patient["patient_id"],
            "patient_name": patient["patient_name"],
            "phone": patient["whatsapp_number"],
            "address": patient.get("address", "Not provided"),
            "conditions": patient.get("health_conditions", []),
            "request_time": datetime.utcnow(),
            "priority": "high" if patient.get("is_high_risk") else "normal",
        }
        logger.info(f"Hello Doctor notification: {notification_data}")
        # TODO: await hello_doctor_api.create_visit_request(notification_data)
