import random
from datetime import datetime
from config.settings import settings
from utils.logger import logger


class DoctorChatHandler:
    def __init__(self, db, whatsapp, redis_client):
        self.db = db
        self.whatsapp = whatsapp
        self.redis = redis_client

    async def handle(self, state):
        """Handle doctor live chat."""
        phone = state["phone_number"]
        patient = state["patient"]
        text = state["context"]["text"]
        waiting_for = state["waiting_for"]

        if not waiting_for or waiting_for != "doctor_chat":
            await self._initiate_chat(phone, patient)
        else:
            await self._forward_to_doctor(state, text)
        return state

    async def _initiate_chat(self, phone: str, patient: dict) -> None:
        doctor = await self._check_doctor_availability()
        if doctor:
            await self._connect_to_doctor(phone, patient, doctor)
        else:
            await self._send_unavailable_message(phone, patient)

    async def _check_doctor_availability(self) -> dict | None:
        # In production: query doctors collection for status == "online"
        if random.random() > 0.5:
            return {"name": "Dr. Silva", "id": "DOC-001", "specialty": "General Practitioner"}
        return None

    async def _connect_to_doctor(self, phone: str, patient: dict, doctor: dict) -> None:
        await self.whatsapp.send_message(phone, f"""💬 *Chat with Doctor*

Hi {patient['patient_name']}!

*{doctor['name']}* ({doctor['specialty']}) has joined the chat.

Describe your concern and the doctor will respond shortly.

Type *END CHAT* to finish.""")

        await self.redis.set_conversation_state(phone, {
            "stage": "doctor_chat",
            "waiting_for": "doctor_chat",
            "doctor_id": doctor["id"],
            "doctor_name": doctor["name"],
        })
        await self._notify_doctor_dashboard(patient, doctor)

    async def _send_unavailable_message(self, phone: str, patient: dict) -> None:
        await self.whatsapp.send_message(phone, f"""💬 *Doctor Chat*

Hi {patient['patient_name']}! All doctors are currently with other patients.

*Estimated wait:* 15 minutes

*Options:*
*1.* ⏳ Wait — we'll notify you
*2.* 📞 Schedule teleconsultation
*3.* 📝 Leave a message for callback

Reply with 1, 2, or 3.""")
        await self._add_to_chat_queue(patient)

    async def _forward_to_doctor(self, state: dict, text: str) -> None:
        phone = state["phone_number"]
        patient = state["patient"]
        conv_state = patient.get("conversation_state", {})

        if text.upper() == "END CHAT":
            await self._end_chat(phone, patient)
            return

        await self.db.db.patients.update_one(
            {"patient_id": patient["patient_id"]},
            {"$push": {"conversation_history": {
                "timestamp": datetime.utcnow(),
                "sender": "patient",
                "message": text,
            }}},
        )
        await self._notify_doctor_dashboard(patient, {
            "id": conv_state.get("doctor_id"),
            "name": conv_state.get("doctor_name"),
        }, text)
        await self.whatsapp.send_message(phone, "✓ Message sent to doctor. They'll respond shortly...")
        logger.info(f"Chat message from {patient['patient_id']}: {text}")

    async def _end_chat(self, phone: str, patient: dict) -> None:
        await self.whatsapp.send_message(phone, f"""💬 *Chat Ended*

Thank you for using Remedi Doctor Chat!

• Type *CARE* for main menu
• Call {settings.support_phone}

Take care! 🌟""")
        await self.redis.clear_conversation_state(phone)

    async def _add_to_chat_queue(self, patient: dict) -> None:
        logger.info(f"Added {patient['patient_id']} to chat queue")
        # TODO: await self.db.db.chat_queue.insert_one({...})

    async def _notify_doctor_dashboard(self, patient: dict, doctor: dict, message: str | None = None) -> None:
        notification = {
            "type": "chat_request" if not message else "new_message",
            "patient_id": patient["patient_id"],
            "patient_name": patient["patient_name"],
            "doctor_id": doctor.get("id"),
            "message": message,
            "timestamp": datetime.utcnow(),
        }
        logger.info(f"Doctor notification: {notification}")
        # TODO: await doctor_websocket.send_notification(doctor["id"], notification)
