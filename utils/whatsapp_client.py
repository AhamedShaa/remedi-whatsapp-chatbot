# utils/whatsapp_client.py - WhatsApp Cloud API Client
import aiohttp
import base64
from config.settings import settings
from utils.logger import logger

class WhatsAppClient:
    def __init__(self):
        self.token = settings.whatsapp_access_token
        self.api_url = (
            f"https://graph.facebook.com/{settings.whatsapp_api_version}"
            f"/{settings.whatsapp_phone_number_id}"
        )
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        logger.info(
            f"WhatsAppClient configured: api_version={settings.whatsapp_api_version}, "
            f"phone_number_id={settings.whatsapp_phone_number_id}"
        )
    
    async def send_message(self, to, text):
        """Send text message"""
        try:
            if not self.token or not self.api_url:
                logger.error("Cannot send message: client not configured (missing token or api_url)")
                return False
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"body": text}
            }
            logger.debug(f"Sending WhatsApp text payload to {self.api_url}/messages: {payload}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/messages",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"Message sent to {to}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Failed to send message (status {response.status}): {error_text}"
                        )
                        return False
        
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False
    
    async def send_interactive_buttons(self, to, body_text, buttons):
        """Send interactive button message"""
        try:
            if not self.token or not self.api_url:
                logger.error("Cannot send interactive message: client not configured (missing token or api_url)")
                return False
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body_text},
                    "action": {
                        "buttons": buttons  # Max 3 buttons
                    }
                }
            }
            logger.debug(f"Sending WhatsApp interactive buttons payload: {payload}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/messages",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"Interactive message sent to {to}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Failed to send interactive message (status {response.status}): {error_text}"
                        )
                        return False
        
        except Exception as e:
            logger.error(f"Error sending interactive message: {str(e)}")
            return False
    
    async def send_interactive_list(self, to, body_text, button_text, sections):
        """Send interactive list message"""
        try:
            if not self.token or not self.api_url:
                logger.error("Cannot send interactive list: client not configured (missing token or api_url)")
                return False
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": body_text},
                    "action": {
                        "button": button_text,
                        "sections": sections
                    }
                }
            }
            logger.debug(f"Sending WhatsApp interactive list payload: {payload}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/messages",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"Interactive list sent to {to}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to send interactive list: {error_text}")
                        return False
        
        except Exception as e:
            logger.error(f"Error sending interactive list: {str(e)}")
            return False
    
    async def send_media(self, to, media_type, media_url, caption=None):
        """Send media message (image, document, etc.)"""
        try:
            if not self.token or not self.api_url:
                logger.error("Cannot send media: client not configured (missing token or api_url)")
                return False
            media_data = {
                "link": media_url
            }
            
            if caption:
                media_data["caption"] = caption
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": media_type,
                media_type: media_data
            }
            logger.debug(f"Sending WhatsApp media payload: {payload}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/messages",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"Media sent to {to}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Failed to send media (status {response.status}): {error_text}"
                        )
                        return False
        
        except Exception as e:
            logger.error(f"Error sending media: {str(e)}")
            return False
    
    async def download_media(self, media_id):
        """Download media file from WhatsApp"""
        try:
            # Step 1: Get media URL
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://graph.facebook.com/{settings.whatsapp_api_version}/{media_id}",
                    headers={"Authorization": f"Bearer {self.token}"}
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get media URL: {await response.text()}")
                        return None
                    
                    media_data = await response.json()
                    media_url = media_data.get("url")
                    mime_type = media_data.get("mime_type")
                
                # Step 2: Download actual file
                async with session.get(
                    media_url,
                    headers={"Authorization": f"Bearer {self.token}"}
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download media: {await response.text()}")
                        return None
                    
                    file_bytes = await response.read()
                    base64_data = base64.b64encode(file_bytes).decode('utf-8')
                    
                    return {
                        "mime_type": mime_type,
                        "base64": base64_data,
                        "size": len(file_bytes)
                    }
        
        except Exception as e:
            logger.error(f"Error downloading media: {str(e)}")
            return None
    
    async def mark_as_read(self, message_id):
        """Mark message as read"""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/messages",
                    headers=self.headers,
                    json=payload
                ) as response:
                    return response.status == 200
        
        except Exception as e:
            logger.error(f"Error marking message as read: {str(e)}")
            return False
    
    # Convenience methods for specific messages
    
    async def send_welcome_message(self, to, patient_name):
        """Send welcome message after approval"""
        message = f"""🎉 *Welcome to Remedi Chronic Care, {patient_name}!*

Your account has been activated! You now have full access to:

✅ Teleconsultations with doctors
✅ Lab report uploads with instant analysis
✅ Blood pressure monitoring & alerts
✅ Home visit requests (Colombo area)
✅ Direct doctor chat
✅ Personalized health tips 2x weekly
✅ Blood test reminders

📱 *Get Started*

Type *CARE* anytime to see the menu and access all features.

We're here to support your health journey every step of the way!

Questions? Call us at {settings.support_phone}"""
        
        await self.send_message(to, message)

    async def send_payment_reminder(self, to, patient_name):
        """Send payment reminder"""
        message = f"""Hi {patient_name}! 👋

We noticed your payment is still pending.

Complete your payment to activate your Remedi Chronic Care account:

{settings.payment_link}

After payment, you'll get immediate access to:
• Doctor consultations
• Report analysis
• Health monitoring
• And much more!

Need help? Contact {settings.support_phone}"""
        
        await self.send_message(to, message)