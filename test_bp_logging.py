"""Test BP Logging functionality"""
import asyncio
from database.mongodb import MongoDB
from utils.whatsapp_client import WhatsAppClient
from handlers.bp_handler import BPHandler
from dotenv import load_dotenv

load_dotenv()

async def test_bp_logging():
    print("=" * 60)
    print("BP LOGGING TEST")
    print("=" * 60)
    
    # Initialize
    db = MongoDB()
    await db.connect()
    
    whatsapp = WhatsAppClient()
    handler = BPHandler(db, whatsapp)
    
    # Get test patient
    phone = "94779848704"
    patient = await db.get_patient_by_phone(phone)
    
    if not patient:
        print("❌ Patient not found. Run setup_test_patient.py first!")
        await db.disconnect()
        return
    
    print(f"\n✓ Testing with patient: {patient['patient_name']}")
    print(f"  Patient ID: {patient['patient_id']}")
    
    # Test different BP readings
    test_cases = [
        ("120/80", "Normal"),
        ("135/85", "Elevated"),
        ("145/95", "High"),
        ("185/120", "Critical")
    ]
    
    print("\n" + "=" * 60)
    print("Choose a test case:")
    for i, (reading, level) in enumerate(test_cases, 1):
        print(f"{i}. {reading} mmHg - {level}")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice in ['1', '2', '3', '4']:
        bp_reading = test_cases[int(choice) - 1][0]
        print(f"\n📊 Testing with: {bp_reading}")
        
        # Create mock state
        state = {
            "phone_number": phone,
            "patient": patient,
            "context": {"text": bp_reading},
            "waiting_for": "bp_reading"
        }
        
        # Process BP reading
        await handler._process_bp_reading(phone, patient, bp_reading)
        
        print("\n✅ Check your WhatsApp for the BP alert message!")
    else:
        print("Invalid choice")
    
    await db.disconnect()
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(test_bp_logging())
