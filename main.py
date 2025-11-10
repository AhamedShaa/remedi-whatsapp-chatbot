# main.py - Main FastAPI application for Remedi Chronic Care
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv
import logging
from datetime import datetime

from database.mongodb import MongoDB
from workflows.conversation_graph import ConversationGraph
from utils.whatsapp_client import WhatsAppClient
from jobs.scheduler import start_scheduler

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,
    handlers=[
        logging.StreamHandler()
    ]
)
# Ensure uvicorn logs are visible
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Remedi Chronic Care API")

# Verify token configuration (support legacy name fallback)
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN") or os.getenv("VERIFY_TOKEN")

# Initialize components
db = MongoDB()
whatsapp = WhatsAppClient()
conversation_graph = ConversationGraph(db, whatsapp)

# Pydantic models
class WebhookMessage(BaseModel):
    object: str
    entry: list

@app.on_event("startup")
async def startup_event():
    """Initialize database and start background jobs"""
    await db.connect()
    start_scheduler(db, whatsapp)
    logger.info("Remedi Chronic Care Bot Started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await db.disconnect()
    logger.info("Remedi Chronic Care Bot Stopped")

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verify WhatsApp webhook (GET) following Meta spec.
    Expected query params:
    hub.mode=subscribe
    hub.verify_token=<YOUR TOKEN>
    hub.challenge=<RANDOM STRING>
    Returns the hub.challenge if verification passes.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if not mode:
        logger.warning("Webhook verify failed: missing hub.mode")
        raise HTTPException(status_code=400, detail="Missing hub.mode")
    if not token:
        logger.warning("Webhook verify failed: missing hub.verify_token")
        raise HTTPException(status_code=400, detail="Missing hub.verify_token")
    if not challenge:
        logger.warning("Webhook verify failed: missing hub.challenge")
        raise HTTPException(status_code=400, detail="Missing hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(content=challenge)
    else:
        logger.error("Webhook verify failed: invalid token or mode", extra={"mode": mode, "token_provided": token})
        raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Handle incoming WhatsApp messages"""
    try:
        body = await request.json()
        print(f"🔔 WEBHOOK RECEIVED: {body}", flush=True)
        logger.info(f"Inbound webhook body: {body}")
        
        if body.get("object") == "whatsapp_business_account":
            entry = body.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            
            if "messages" in value:
                message = value["messages"][0]
                from_number = message["from"]
                message_type = message["type"]
                print(f"📱 MESSAGE from {from_number}: type={message_type}", flush=True)
                logger.info(f"Incoming message {message.get('id')} type={message_type} from={from_number}")
                
                # Extract message content
                message_data = {
                    "from": from_number,
                    "type": message_type,
                    "timestamp": message.get("timestamp")
                }
                
                if message_type == "text":
                    message_data["text"] = message["text"]["body"]
                elif message_type == "image":
                    message_data["media_id"] = message["image"]["id"]
                    message_data["mime_type"] = message["image"].get("mime_type")
                elif message_type == "document":
                    message_data["media_id"] = message["document"]["id"]
                    message_data["mime_type"] = message["document"].get("mime_type")
                elif message_type == "interactive":
                    # Handle button/list responses
                    interactive = message["interactive"]
                    if interactive["type"] == "button_reply":
                        message_data["text"] = interactive["button_reply"]["id"]
                    elif interactive["type"] == "list_reply":
                        message_data["text"] = interactive["list_reply"]["id"]
                
                # Process message through LangGraph workflow
                await conversation_graph.process_message(message_data)
                # Best-effort mark as read
                try:
                    if message.get("id"):
                        await whatsapp.mark_as_read(message.get("id"))
                except Exception:
                    logger.warning("Failed to mark message as read", exc_info=True)
            else:
                logger.info("Webhook received change without messages; ignoring.")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected" if db.client else "disconnected"
    }

@app.post("/admin/approve-patient")
async def approve_patient(patient_id: str):
    """Admin endpoint to approve patient enrollment"""
    try:
        patient = await db.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        
        # Update approval status
        await db.update_patient(patient_id, {
            "approval_status": "approved",
            "payment_status": "completed",
            "approval_date": datetime.utcnow()
        })
        
        # Schedule initial blood tests
        await db.schedule_blood_tests(patient_id)
        
        # Send welcome message
        await whatsapp.send_welcome_message(
            patient["whatsapp_number"],
            patient["patient_name"]
        )
        
        return {"status": "success", "message": f"Patient {patient_id} approved"}
        
    except Exception as e:
        logger.error(f"Error approving patient: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/approve-by-phone")
async def approve_by_phone(phone: str, key: str):
    """Quick approve by phone number for testing
    Usage: POST /admin/approve-by-phone?phone=94779848704&key=remedi_google_form_secret
    """
    try:
        if key != os.getenv("GOOGLE_FORM_SECRET"):
            raise HTTPException(status_code=403, detail="Forbidden")
        
        patient = await db.get_patient_by_phone(phone)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        
        # Auto-approve for testing
        await db.update_patient(patient["patient_id"], {
            "approval_status": "approved",
            "payment_status": "completed",
            "approval_date": datetime.utcnow()
        })
        
        # Schedule blood tests
        await db.schedule_blood_tests(patient["patient_id"])
        
        # Send welcome message
        await whatsapp.send_welcome_message(phone, patient["patient_name"])
        
        return {
            "status": "success",
            "patient_id": patient["patient_id"],
            "message": "Patient approved and welcome message sent"
        }
        
    except Exception as e:
        logger.error(f"Error approving patient: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/send-health-tip")
async def send_health_tip_manual(patient_id: str, condition: str):
    """Admin endpoint to send health tip manually"""
    try:
        from jobs.health_tips import send_health_tip_to_patient
        await send_health_tip_to_patient(patient_id, condition, db, whatsapp)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/stats")
async def get_admin_stats():
    """Get admin dashboard statistics"""
    try:
        stats = await db.get_admin_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/test-send")
async def admin_test_send(to: str, key: str):
    """Admin-only: send a test message to a number to validate WhatsApp sending.
    Requires key to match GOOGLE_FORM_SECRET to avoid abuse.
    """
    if key != os.getenv("GOOGLE_FORM_SECRET"):
        raise HTTPException(status_code=403, detail="Forbidden")
    ok = await whatsapp.send_message(to, "Test message from Remedi bot ✅")
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send test message")
    return {"status": "success"}

@app.post("/google-form-submission")
async def google_form_submission(request: Request):
    """Receive patient registration data from Google Form webhook
    
    Expected data structure:
    {
        "patient_name": "John Doe",
        "whatsapp_number": "94771234567",
        "age": 45,
        "gender": "Male",
        "health_conditions": ["Diabetes", "Hypertension"],
        "medications": "Metformin, Amlodipine",
        "allergies": "None",
        "emergency_contact": "94779999999",
        "payment_status": "pending",
        "secret_key": "remedi_google_form_secret"
    }
    """
    try:
        data = await request.json()
        print(f"📝 GOOGLE FORM SUBMISSION: {data}", flush=True)
        logger.info(f"Google Form submission received: {data}")
        
        # Verify secret key
        if data.get("secret_key") != os.getenv("GOOGLE_FORM_SECRET"):
            logger.warning("Invalid secret key in form submission")
            raise HTTPException(status_code=403, detail="Invalid secret key")
        
        # Remove secret from patient data
        data.pop("secret_key", None)
        
        # Check if patient already exists
        existing = await db.get_patient_by_phone(data["whatsapp_number"])
        if existing:
            logger.info(f"Patient already exists: {existing['patient_id']}")
            return {
                "status": "exists",
                "patient_id": existing["patient_id"],
                "message": "Patient already registered"
            }
        
        # Set default approval status
        data["approval_status"] = "pending"
        if "payment_status" not in data:
            data["payment_status"] = "pending"
        
        # Parse health conditions if string
        if isinstance(data.get("health_conditions"), str):
            data["health_conditions"] = [
                c.strip() for c in data["health_conditions"].split(",")
            ]
        
        # Create patient
        patient_id = await db.create_patient(data)
        logger.info(f"New patient created: {patient_id}")
        
        # Send confirmation message
        await whatsapp.send_message(
            data["whatsapp_number"],
            f"""Thank you for registering with Remedi Chronic Care! 🏥

Your registration has been received. Your Patient ID is: *{patient_id}*

Next steps:
1️⃣ Complete payment: {os.getenv('PAYMENT_LINK')}
2️⃣ Wait for admin approval (usually within 24 hours)
3️⃣ Once approved, type *CARE* to access all features

Questions? Contact us at {os.getenv('SUPPORT_PHONE')}"""
        )
        
        return {
            "status": "success",
            "patient_id": patient_id,
            "message": "Patient registered successfully"
        }
        
    except KeyError as e:
        logger.error(f"Missing required field in form: {e}")
        raise HTTPException(status_code=400, detail=f"Missing required field: {e}")
    except Exception as e:
        logger.error(f"Error processing form submission: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )