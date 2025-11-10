"""Test MongoDB connection and patient creation"""
import asyncio
import os
from dotenv import load_dotenv
from database.mongodb import MongoDB
from datetime import datetime

load_dotenv()

async def test_mongodb():
    print("=" * 60)
    print("MONGODB CONNECTION TEST")
    print("=" * 60)
    
    # Test connection
    print("\n1. Testing MongoDB connection...")
    db = MongoDB()
    try:
        await db.connect()
        print("   ✓ MongoDB connected successfully!")
        print(f"   Database: {db.db.name}")
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        return
    
    # Test patient creation
    print("\n2. Testing patient creation...")
    test_patient = {
        "patient_name": "Test Patient",
        "whatsapp_number": "94779999999",
        "age": 45,
        "gender": "Male",
        "health_conditions": ["Diabetes", "Hypertension"],
        "payment_status": "pending",
        "approval_status": "pending"
    }
    
    try:
        # Check if test patient exists
        existing = await db.get_patient_by_phone(test_patient["whatsapp_number"])
        if existing:
            print(f"   ⚠ Test patient already exists: {existing['patient_id']}")
        else:
            patient_id = await db.create_patient(test_patient)
            print(f"   ✓ Test patient created: {patient_id}")
        
        # Query the patient
        patient = await db.get_patient_by_phone(test_patient["whatsapp_number"])
        print(f"   ✓ Patient retrieved: {patient['patient_name']} ({patient['patient_id']})")
        
    except Exception as e:
        print(f"   ✗ Patient creation failed: {e}")
    
    # Test collection counts
    print("\n3. Database statistics...")
    try:
        stats = await db.get_admin_stats()
        print(f"   Total patients: {stats['total_patients']}")
        print(f"   Active patients: {stats['active_patients']}")
        print(f"   Pending approvals: {stats['pending_approvals']}")
    except Exception as e:
        print(f"   ✗ Stats retrieval failed: {e}")
    
    # Disconnect
    await db.disconnect()
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_mongodb())
