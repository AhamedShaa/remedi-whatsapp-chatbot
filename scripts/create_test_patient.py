"""Create a test patient in MongoDB and schedule their blood tests.

Usage:
    python scripts/create_test_patient.py

The script normalises the WhatsApp number (strips spaces), checks for
an existing record so it's safe to run more than once, and prints the
patient_id on success.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Allow imports from the project root regardless of where the script is run from
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from database.mongodb import MongoDB


_WHATSAPP_NUMBER = "94779848704"   # normalised: no spaces

_PATIENT = {
    "patient_name": "Test Patient",
    "whatsapp_number": _WHATSAPP_NUMBER,
    "date_of_birth": "1980-01-15",
    "gender": "Male",
    "health_conditions": ["Diabetes", "Hypertension"],
    "nic_number": "800115123V",
    "approval_status": "pending",
    "payment_status": "pending",
    "conversation_state": None,
}


async def main() -> None:
    db = MongoDB()
    await db.connect()

    try:
        # Idempotency — skip if already exists
        existing = await db.get_patient_by_phone(_WHATSAPP_NUMBER)
        if existing:
            print(f"Patient already exists: {existing['patient_id']}")
            await db.schedule_blood_tests(existing["patient_id"])
            print("Blood tests (re)scheduled.")
            return

        # Build the document
        patient_id = await db._generate_patient_id()
        doc = {
            **_PATIENT,
            "patient_id": patient_id,
            "enrollment_date": datetime.utcnow(),
            "created_at": datetime.utcnow(),
        }
        await db.db.patients.insert_one(doc)
        print(f"Created patient: {patient_id}")

        await db.schedule_blood_tests(patient_id)
        print("Blood tests scheduled.")

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
