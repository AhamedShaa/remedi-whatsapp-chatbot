"""Create a test patient in MongoDB and schedule their blood tests.

Usage:
    python scripts/create_test_patient.py --phone "+94 70 551 1444" --name "Alavudeen" --approve
    python scripts/create_test_patient.py --phone "94779848704" --approve
    python scripts/create_test_patient.py --phone "94779848704"

The script normalises the WhatsApp number (strips spaces and leading +),
checks for an existing record so it's safe to run more than once, and
prints the patient_id on success.
"""
import argparse
import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from database.mongodb import MongoDB


def parse_args():
    parser = argparse.ArgumentParser(description="Create a test patient in MongoDB.")
    parser.add_argument("--phone", required=True,
                        help='WhatsApp number, e.g. "+94 70 551 1444" or "94779848704"')
    parser.add_argument("--name", default="Test Patient",
                        help="Patient display name (default: Test Patient)")
    parser.add_argument("--conditions", default="Diabetes,Hypertension",
                        help="Comma-separated health conditions (default: Diabetes,Hypertension)")
    parser.add_argument("--approve", action="store_true",
                        help="Set approval_status and payment_status to approved and is_active=True")
    return parser.parse_args()


def normalise_phone(raw: str) -> str:
    return re.sub(r"[\s+]", "", raw)


async def main() -> None:
    args = parse_args()
    phone = normalise_phone(args.phone)
    conditions = [c.strip() for c in args.conditions.split(",")]

    patient_base = {
        "patient_name": args.name,
        "whatsapp_number": phone,
        "date_of_birth": "1980-01-15",
        "gender": "Male",
        "health_conditions": conditions,
        "nic_number": "800115123V",
        "approval_status": "approved" if args.approve else "pending",
        "payment_status": "approved" if args.approve else "pending",
        "is_active": args.approve,
        "conversation_state": None,
    }

    db = MongoDB()
    await db.connect()

    try:
        existing = await db.get_patient_by_phone(phone)
        if existing:
            print(f"Patient already exists: {existing['patient_id']}")
            await db.schedule_blood_tests(existing["patient_id"])
            print("Blood tests (re)scheduled.")
            return

        patient_id = await db._generate_patient_id()
        doc = {
            **patient_base,
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
