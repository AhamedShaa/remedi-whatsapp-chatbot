# handlers/bp_handler.py - Blood Pressure Logging Handler
from datetime import datetime, timedelta
import re
from utils.logger import logger

class BPHandler:
    def __init__(self, db, whatsapp, redis_client):
        self.db = db
        self.whatsapp = whatsapp
        self.redis = redis_client
    
    async def handle(self, state):
        """Main handler for BP logging flow"""
        phone = state["phone_number"]
        patient = state["patient"]
        text = state["context"]["text"].strip()
        waiting_for = state.get("waiting_for", "")
        
        # Check if we're waiting for BP input
        if waiting_for == "bp_reading":
            await self._process_bp_reading(phone, patient, text)
        else:
            # First time - prompt for BP reading
            await self._prompt_for_bp(phone)
            await self.redis.set_conversation_state(
                phone,
                {"stage": "bp_logging", "waiting_for": "bp_reading"}
            )
        
        return state
    
    async def _prompt_for_bp(self, phone):
        """Send initial prompt for BP reading"""
        message = """🩺 *Blood Pressure Logging*

Please enter your blood pressure reading in this format:
*systolic/diastolic*

Example: 120/80

📋 *Tips for accurate measurement:*
• Rest for 5 minutes before measuring
• Sit in a comfortable position
• Take reading at the same time each day
• Ensure arm is at heart level

Enter your reading now:"""
        
        await self.whatsapp.send_message(phone, message)
    
    async def _process_bp_reading(self, phone, patient, text):
        """Process and analyze BP reading"""
        # Parse BP reading
        bp_data = self._parse_bp_reading(text)
        
        if not bp_data:
            await self.whatsapp.send_message(
                phone,
                "❌ Invalid format. Please enter your BP as: systolic/diastolic\n\nExample: 120/80"
            )
            return
        
        systolic = bp_data["systolic"]
        diastolic = bp_data["diastolic"]
        
        # Validate ranges
        if not self._validate_bp_ranges(systolic, diastolic):
            await self.whatsapp.send_message(
                phone,
                f"⚠️ The reading {systolic}/{diastolic} seems unusual.\n\nPlease double-check and re-enter, or type *CARE* to return to menu."
            )
            return
        
        # Save to database
        reading_data = {
            "patient_id": patient["patient_id"],
            "systolic": systolic,
            "diastolic": diastolic,
            "reading_date": datetime.utcnow(),
            "recorded_at": datetime.utcnow()
        }
        
        reading_id = await self.db.save_bp_reading(reading_data)
        logger.info(f"BP reading saved: {reading_id} for patient {patient['patient_id']}")
        
        # Classify and send appropriate alert
        await self._send_bp_alert(phone, patient, systolic, diastolic)
        
        await self.redis.clear_conversation_state(phone)
    
    def _parse_bp_reading(self, text):
        """Parse BP reading from text (e.g., '120/80')"""
        # Match pattern: number/number
        match = re.match(r'^(\d{2,3})\s*/\s*(\d{2,3})$', text.strip())
        
        if match:
            systolic = int(match.group(1))
            diastolic = int(match.group(2))
            return {"systolic": systolic, "diastolic": diastolic}
        
        return None
    
    def _validate_bp_ranges(self, systolic, diastolic):
        """Validate BP reading is within possible human ranges"""
        # Systolic should be between 60 and 250
        # Diastolic should be between 40 and 150
        # Systolic should be higher than diastolic
        if systolic < 60 or systolic > 250:
            return False
        if diastolic < 40 or diastolic > 150:
            return False
        if systolic <= diastolic:
            return False
        return True
    
    async def _send_bp_alert(self, phone, patient, systolic, diastolic):
        """Classify BP and send appropriate alert"""
        # Get recent readings for context
        recent_readings = await self.db.get_recent_bp_readings(
            patient["patient_id"],
            limit=7
        )
        
        # Calculate 7-day average
        avg_7day = await self.db.get_bp_average(patient["patient_id"], days=7)
        
        # Classify BP level
        level = self._classify_bp_level(systolic, diastolic)
        
        # Send appropriate message based on level
        if level == "critical":
            await self._send_critical_alert(phone, patient, systolic, diastolic)
        elif level == "high":
            await self._send_high_alert(phone, patient, systolic, diastolic, recent_readings)
        elif level == "elevated":
            await self._send_elevated_alert(phone, patient, systolic, diastolic, recent_readings)
        else:  # normal
            await self._send_normal_message(phone, patient, systolic, diastolic, avg_7day)
        
        # Check for 3-day elevated pattern
        if len(recent_readings) >= 3:
            await self._check_3day_pattern(phone, patient, recent_readings)
    
    def _classify_bp_level(self, systolic, diastolic):
        """Classify BP reading into normal/elevated/high/critical"""
        # Critical: >180/115 (Hypertensive Crisis)
        if systolic > 180 or diastolic > 115:
            return "critical"
        
        # High: Stage 2 Hypertension (140-179/90-114)
        if systolic >= 140 or diastolic >= 90:
            return "high"
        
        # Elevated: Stage 1 Hypertension (130-139/80-89)
        if systolic >= 130 or diastolic >= 80:
            return "elevated"
        
        # Normal: <130/80
        return "normal"
    
    async def _send_normal_message(self, phone, patient, systolic, diastolic, avg_7day):
        """Send message for normal BP reading (Green)"""
        now = datetime.utcnow()
        
        avg_text = ""
        if avg_7day["systolic"] > 0:
            avg_text = f"\n\n📊 *7-Day Average:* {avg_7day['systolic']}/{avg_7day['diastolic']} mmHg"
        
        message = f"""✅ *Blood Pressure Logged - Normal*

📋 *Your Reading:*
{systolic}/{diastolic} mmHg
🕐 {now.strftime('%B %d, %Y at %I:%M %p')}

✨ *Status:* Normal
🎯 *Target:* Less than 130/80 mmHg

🎉 Great job, {patient['patient_name']}! Your blood pressure is within the healthy range.{avg_text}

💪 *Keep it up by:*
• Taking medications as prescribed
• Following a low-sodium diet
• Exercising regularly
• Managing stress

Type *CARE* to return to the main menu."""
        
        await self.whatsapp.send_message(phone, message)
    
    async def _send_elevated_alert(self, phone, patient, systolic, diastolic, recent_readings):
        """Send message for elevated BP (Yellow)"""
        now = datetime.utcnow()
        
        # Show last 3 readings
        trend_text = "\n\n📈 *Recent Readings:*"
        for reading in recent_readings[:3]:
            date_str = reading["reading_date"].strftime('%b %d')
            trend_text += f"\n• {reading['systolic']}/{reading['diastolic']} mmHg ({date_str})"
        
        message = f"""⚠️ *Blood Pressure Logged - Elevated*

📋 *Your Reading:*
{systolic}/{diastolic} mmHg
🕐 {now.strftime('%B %d, %Y at %I:%M %p')}

⚠️ *Status:* Stage 1 Hypertension
🎯 *Target:* Less than 130/80 mmHg{trend_text}

📝 *Recommended Actions:*
1️⃣ Check if you took your medication on time
2️⃣ Reduce salt intake today
3️⃣ Avoid caffeine and reduce stress
4️⃣ Recheck your BP in 4 hours

Would you like me to remind you to check again in 4 hours? Reply *YES* or *NO*.

Need to talk to a doctor? Type *CARE* for menu options."""
        
        await self.whatsapp.send_message(phone, message)
    
    async def _send_high_alert(self, phone, patient, systolic, diastolic, recent_readings):
        """Send message for high BP (Red)"""
        now = datetime.utcnow()
        
        # Show last 3 readings
        trend_text = "\n\n📈 *Recent Readings:*"
        for reading in recent_readings[:3]:
            date_str = reading["reading_date"].strftime('%b %d')
            trend_text += f"\n• {reading['systolic']}/{reading['diastolic']} mmHg ({date_str})"
        
        message = f"""🔴 *ALERT: High Blood Pressure*

📋 *Your Reading:*
{systolic}/{diastolic} mmHg
🕐 {now.strftime('%B %d, %Y at %I:%M %p')}

🔴 *Status:* Stage 2 Hypertension
⚠️ *This reading is concerning*{trend_text}

🚨 *Immediate Actions:*
1️⃣ Rest for 15 minutes
2️⃣ Recheck your blood pressure
3️⃣ Take your prescribed medication if you missed it
4️⃣ Contact your doctor if still high

💬 *Get Help Now:*
Reply with:
*1* - Schedule urgent teleconsult
*2* - Request home visit (Colombo)
*3* - Call doctor immediately

Or type *CARE* for more options."""
        
        await self.whatsapp.send_message(phone, message)
    
    async def _send_critical_alert(self, phone, patient, systolic, diastolic):
        """Send message for critical BP (Emergency)"""
        now = datetime.utcnow()
        
        message = f"""🚨 *EMERGENCY: Hypertensive Crisis*

📋 *Your Reading:*
{systolic}/{diastolic} mmHg
🕐 {now.strftime('%B %d, %Y at %I:%M %p')}

⚠️ *This is a MEDICAL EMERGENCY*

Your blood pressure is dangerously high (above 180/115).

❗ *Are you experiencing any of these?*
• Severe headache
• Chest pain
• Vision changes
• Difficulty breathing

*Reply YES or NO now*"""
        
        await self.whatsapp.send_message(phone, message)
        
        # Follow up with action steps
        import asyncio
        await asyncio.sleep(2)
        
        action_message = """🚨 *Emergency Actions:*

*If you answered YES:*
🏥 Go to the nearest hospital IMMEDIATELY
📞 Call emergency services: 1990

*If you answered NO:*
1️⃣ Sit down and rest quietly
2️⃣ Recheck your BP in 5 minutes
3️⃣ Call the Remedi doctor RIGHT NOW

📞 *Emergency Contact:*
+94771234567

Please confirm you've taken action by replying *DONE*."""
        
        await self.whatsapp.send_message(phone, action_message)
    
    async def _check_3day_pattern(self, phone, patient, recent_readings):
        """Check for 3-day elevated BP pattern"""
        if len(recent_readings) < 3:
            return
        
        # Get last 3 readings (most recent first)
        last_3 = recent_readings[:3]
        
        # Check if all 3 are elevated (systolic >= 130 or diastolic >= 80)
        all_elevated = all(
            r["systolic"] >= 130 or r["diastolic"] >= 80
            for r in last_3
        )
        
        if not all_elevated:
            return
        
        # Calculate average
        avg_systolic = sum(r["systolic"] for r in last_3) // 3
        avg_diastolic = sum(r["diastolic"] for r in last_3) // 3
        
        # Send trend alert
        await asyncio.sleep(3)  # Slight delay after main alert
        
        trend_message = f"""📊 *3-Day Trend Alert*

Your blood pressure has been elevated for 3 consecutive days:

📈 *Last 3 Readings:*"""
        
        for reading in last_3:
            date_str = reading["reading_date"].strftime('%b %d')
            trend_message += f"\n• {reading['systolic']}/{reading['diastolic']} mmHg ({date_str})"
        
        trend_message += f"""

📊 *3-Day Average:* {avg_systolic}/{avg_diastolic} mmHg
🎯 *Target:* Less than 130/80 mmHg

⚠️ Your average is above target. This pattern needs attention.

*What would you like to do?*
Reply with:
*1* - Book teleconsult with doctor
*2* - Request doctor callback
*3* - Continue monitoring

Type *CARE* for main menu."""
        
        await self.whatsapp.send_message(phone, trend_message)

# For import compatibility
import asyncio
