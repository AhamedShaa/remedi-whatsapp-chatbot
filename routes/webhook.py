"""routes/webhook.py — WhatsApp webhook and Google Form integration endpoints."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse

from config.settings import settings
from utils.logger import logger

router = APIRouter(tags=["webhook"])


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Verify WhatsApp webhook (GET) following Meta spec."""
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

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(content=challenge)

    logger.bind(mode=mode, token_provided=token).error(
        "Webhook verify failed: invalid token or mode"
    )
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def webhook_handler(request: Request):
    """Handle incoming WhatsApp messages."""
    graph = request.app.state.graph
    whatsapp = request.app.state.whatsapp

    try:
        body = await request.json()
        logger.info(f"Inbound webhook body: {body}")

        if body.get("object") == "whatsapp_business_account":
            entry = body.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})

            if "messages" in value:
                message = value["messages"][0]
                from_number = message["from"]
                message_type = message["type"]
                logger.info(
                    f"Incoming message {message.get('id')} "
                    f"type={message_type} from={from_number}"
                )

                message_data: dict = {
                    "from": from_number,
                    "type": message_type,
                    "timestamp": message.get("timestamp"),
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
                    interactive = message["interactive"]
                    if interactive["type"] == "button_reply":
                        message_data["text"] = interactive["button_reply"]["id"]
                    elif interactive["type"] == "list_reply":
                        message_data["text"] = interactive["list_reply"]["id"]

                await graph.process_message(message_data)

                try:
                    if message.get("id"):
                        await whatsapp.mark_as_read(message["id"])
                except Exception:
                    logger.opt(exception=True).warning("Failed to mark message as read")
            else:
                logger.info("Webhook received change without messages; ignoring.")

        return {"status": "ok"}

    except Exception as e:
        logger.exception(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/google-form-submission")
async def google_form_submission(request: Request):
    """Receive patient registration data from Google Form webhook."""
    db = request.app.state.db
    whatsapp = request.app.state.whatsapp

    try:
        data = await request.json()
        logger.info(f"Google Form submission for number={data.get('whatsapp_number')}")

        if data.get("secret_key") != settings.google_form_secret:
            logger.warning("Invalid secret key in form submission")
            raise HTTPException(status_code=403, detail="Invalid secret key")

        data.pop("secret_key", None)

        existing = await db.get_patient_by_phone(data["whatsapp_number"])
        if existing:
            logger.info(f"Patient already exists: {existing['patient_id']}")
            return {
                "status": "exists",
                "patient_id": existing["patient_id"],
                "message": "Patient already registered",
            }

        data["approval_status"] = "pending"
        data.setdefault("payment_status", "pending")

        if isinstance(data.get("health_conditions"), str):
            data["health_conditions"] = [
                c.strip() for c in data["health_conditions"].split(",")
            ]

        patient_id = await db.create_patient(data)
        logger.info(f"New patient created: {patient_id}")

        await whatsapp.send_message(
            data["whatsapp_number"],
            f"Thank you for registering with Remedi Chronic Care! 🏥\n\n"
            f"Your Patient ID is: *{patient_id}*\n\n"
            f"Next steps:\n"
            f"1️⃣ Complete payment: {settings.payment_link}\n"
            f"2️⃣ Wait for admin approval (usually within 24 hours)\n"
            f"3️⃣ Once approved, type *CARE* to access all features\n\n"
            f"Questions? Contact us at {settings.support_phone}",
        )

        return {"status": "success", "patient_id": patient_id, "message": "Patient registered successfully"}

    except KeyError as e:
        logger.error(f"Missing required field in form: {e}")
        raise HTTPException(status_code=400, detail=f"Missing required field: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing form submission: {e}")
        raise HTTPException(status_code=500, detail=str(e))
