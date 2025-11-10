"""Test Google Form webhook submission"""
import requests
import json

# Test data matching Google Form structure
test_submission = {
    "patient_name": "Ahmed Test",
    "whatsapp_number": "94779848704",  # Your number
    "age": 35,
    "gender": "Male",
    "health_conditions": ["Diabetes", "Hypertension"],
    "medications": "Metformin 500mg, Amlodipine 5mg",
    "allergies": "None",
    "emergency_contact": "+94771234567",
    "payment_status": "pending",
    "secret_key": "remedi_google_form_secret"
}

print("=" * 60)
print("TESTING GOOGLE FORM WEBHOOK")
print("=" * 60)

print("\nSubmitting test patient registration...")
print(json.dumps(test_submission, indent=2))

try:
    response = requests.post(
        "http://localhost:8000/google-form-submission",
        json=test_submission,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Body: {response.json()}")
    
    if response.status_code == 200:
        result = response.json()
        if result["status"] == "success":
            print(f"\n✓ SUCCESS! Patient ID: {result['patient_id']}")
            print("  Check your WhatsApp for confirmation message!")
        elif result["status"] == "exists":
            print(f"\n⚠ Patient already registered: {result['patient_id']}")
    else:
        print(f"\n✗ FAILED: {response.text}")

except Exception as e:
    print(f"\n✗ ERROR: {e}")

print("\n" + "=" * 60)
