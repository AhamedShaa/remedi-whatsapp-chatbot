"""Quick setup: Register and approve a test patient"""
import requests
import json

PHONE = "94779848704"  # Change this to your WhatsApp number
SECRET = "remedi_google_form_secret"

print("=" * 60)
print("QUICK PATIENT SETUP FOR TESTING")
print("=" * 60)

# Step 1: Register patient
print("\n1. Registering patient via Google Form endpoint...")
registration = {
    "patient_name": "Ahmed Shaa",
    "whatsapp_number": PHONE,
    "age": 30,
    "gender": "Male",
    "health_conditions": ["Diabetes", "Hypertension"],
    "medications": "Metformin 500mg, Amlodipine 5mg",
    "allergies": "None",
    "emergency_contact": "+94771234567",
    "secret_key": SECRET
}

try:
    response = requests.post(
        "http://localhost:8000/google-form-submission",
        json=registration
    )
    print(f"   Status: {response.status_code}")
    result = response.json()
    print(f"   Response: {result}")
    
    if response.status_code == 200:
        if result["status"] == "success":
            print(f"   ✓ Patient created: {result['patient_id']}")
        elif result["status"] == "exists":
            print(f"   ⚠ Patient already exists: {result['patient_id']}")
    else:
        print(f"   ✗ Registration failed")
        exit(1)
        
except Exception as e:
    print(f"   ✗ Error: {e}")
    exit(1)

# Step 2: Auto-approve patient
print("\n2. Auto-approving patient for testing...")
try:
    response = requests.post(
        f"http://localhost:8000/admin/approve-by-phone?phone={PHONE}&key={SECRET}"
    )
    print(f"   Status: {response.status_code}")
    result = response.json()
    print(f"   Response: {result}")
    
    if response.status_code == 200:
        print(f"   ✓ Patient approved: {result['patient_id']}")
        print(f"   ✓ Welcome message sent to WhatsApp!")
    else:
        print(f"   ✗ Approval failed: {result}")
        
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("SETUP COMPLETE!")
print("=" * 60)
print("\n📱 Next steps:")
print("1. Check your WhatsApp for the welcome message")
print("2. Type 'CARE' to see the main menu")
print("3. Try the features:")
print("   • Option 1: Teleconsultation")
print("   • Option 2: Upload Report")
print("   • Option 3: Log Blood Pressure")
print("   • Option 4: Request Home Visit")
print("   • Option 5: Chat with Doctor")
print("\n" + "=" * 60)
