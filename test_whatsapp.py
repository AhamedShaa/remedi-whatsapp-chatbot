"""Quick diagnostic script to test WhatsApp configuration"""
import os
import asyncio
from dotenv import load_dotenv
from utils.whatsapp_client import WhatsAppClient

load_dotenv()

async def test_config():
    print("=" * 50)
    print("WHATSAPP CONFIGURATION DIAGNOSTIC")
    print("=" * 50)
    
    # Check env variables
    print("\n1. Environment Variables:")
    print(f"   WHATSAPP_ACCESS_TOKEN: {'✓ SET' if os.getenv('WHATSAPP_ACCESS_TOKEN') else '✗ MISSING'}")
    if os.getenv('WHATSAPP_ACCESS_TOKEN'):
        print(f"      First 20 chars: {os.getenv('WHATSAPP_ACCESS_TOKEN')[:20]}...")
    
    print(f"   WHATSAPP_PHONE_NUMBER_ID: {os.getenv('WHATSAPP_PHONE_NUMBER_ID') or '✗ MISSING'}")
    print(f"   WHATSAPP_API_VERSION: {os.getenv('WHATSAPP_API_VERSION', 'v18.0 (default)')}")
    
    # Initialize client
    print("\n2. WhatsApp Client Initialization:")
    try:
        client = WhatsAppClient()
        print(f"   API URL: {client.api_url}")
        print(f"   Token configured: {'✓ YES' if client.token else '✗ NO'}")
        print(f"   Headers: Authorization header present: {'✓ YES' if 'Authorization' in client.headers else '✗ NO'}")
    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        return
    
    # Optional: Test send (uncomment and add your number to test)
    print("\n3. Test Send (Optional):")
    test_number = input("   Enter WhatsApp number to test (E.164 format, e.g., 9477XXXXXXX) or press Enter to skip: ").strip()
    
    if test_number:
        print(f"   Attempting to send test message to {test_number}...")
        try:
            result = await client.send_message(test_number, "🔧 Test message from Remedi diagnostic script")
            if result:
                print("   ✓ Message sent successfully!")
            else:
                print("   ✗ Message send failed (check server logs for details)")
        except Exception as e:
            print(f"   ✗ ERROR: {e}")
    else:
        print("   Skipped test send")
    
    print("\n" + "=" * 50)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_config())
