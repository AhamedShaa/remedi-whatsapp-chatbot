# handlers/report_handler.py - Handle report uploads and AI analysis
import os
import logging
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import asyncio

logger = logging.getLogger(__name__)

class ReportHandler:
    def __init__(self, db, whatsapp):
        self.db = db
        self.whatsapp = whatsapp
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    async def handle(self, state):
        """Handle report upload flow"""
        phone = state["phone_number"]
        patient = state["patient"]
        message_type = state["context"]["message_type"]
        waiting_for = state["waiting_for"]
        
        if not waiting_for or waiting_for != "report_upload":
            # First time - ask for report
            await self._request_report(phone)
            # Update state to wait for upload
            await self.db.update_patient_conversation_state(
                patient["patient_id"],
                {"stage": "upload_report", "waiting_for": "report_upload"}
            )
        else:
            # User sent something - check if it's media
            if message_type in ["image", "document"]:
                await self._process_report(state)
            else:
                await self.whatsapp.send_message(
                    phone,
                    "Please send your lab report as a clear photo or PDF document. Make sure all values are visible."
                )
        
        return state
    
    async def _request_report(self, phone):
        """Request report from user"""
        message = """📄 *Upload Lab Report*

Please send your lab report as:
• Clear photo (JPG/PNG)
• PDF document

Make sure:
✓ All values are clearly visible
✓ Report is recent and complete
✓ File size is under 10MB

Send your report now..."""
        
        await self.whatsapp.send_message(phone, message)
    
    async def _process_report(self, state):
        """Process uploaded report with AI"""
        phone = state["phone_number"]
        patient = state["patient"]
        media_id = state["context"]["media_id"]
        
        try:
            # Show processing message
            await self.whatsapp.send_message(
                phone,
                "⏳ Processing your report...\n\nThis will take 3-5 seconds."
            )
            
            # Download media file
            file_data = await self.whatsapp.download_media(media_id)
            
            # Extract text using vision model
            report_data = await self._extract_report_data(file_data)
            
            if not report_data:
                await self.whatsapp.send_message(
                    phone,
                    "❌ Sorry, I couldn't process this report. Please ensure:\n\n" +
                    "✓ Image is clear and focused\n" +
                    "✓ All values are visible\n" +
                    "✓ File is a valid image or PDF\n\n" +
                    "Please try uploading again."
                )
                return
            
            # Save report to database
            report_id = await self._save_report(patient["patient_id"], report_data, file_data)
            
            # Analyze results and send feedback
            await self._analyze_and_send_feedback(phone, patient, report_data)
            
            # Update patient stats
            await self.db.increment_patient_stat(patient["patient_id"], "total_reports_uploaded")
            
            # Clear conversation state
            await self.db.update_patient_conversation_state(patient["patient_id"], None)
            
        except Exception as e:
            logger.error(f"Error processing report: {str(e)}", exc_info=True)
            await self.whatsapp.send_message(
                phone,
                f"❌ Error processing report: {str(e)}\n\n" +
                f"Please contact support at {os.getenv('SUPPORT_PHONE')}"
            )
    
    async def _extract_report_data(self, file_data):
        """Extract data from report using GPT-4 Vision"""
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a medical lab report analyzer. Extract all test results from the image.

Return a JSON object with this structure:
{
  "laboratory_name": "Lab name",
  "test_date": "YYYY-MM-DD",
  "tests": [
    {
      "parameter": "Test name",
      "value": "Numeric value",
      "unit": "Unit",
      "reference_range": "Normal range",
      "status": "normal/low/high/critical"
    }
  ]
}

For status determination:
- normal: value within reference range
- low: below reference range  
- high: above reference range
- critical: dangerously outside range

If you cannot read the image clearly, return null."""),
                ("human", [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{file_data['base64']}"}
                    },
                    {"type": "text", "text": "Extract all test results from this lab report."}
                ])
            ])
            
            parser = JsonOutputParser()
            chain = prompt | self.llm | parser
            
            result = await chain.ainvoke({})
            return result
            
        except Exception as e:
            logger.error(f"Error extracting report data: {str(e)}")
            return None
    
    async def _save_report(self, patient_id, report_data, file_data):
        """Save report to database"""
        report = {
            "report_id": f"RPT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "patient_id": patient_id,
            "laboratory_name": report_data.get("laboratory_name"),
            "test_date": report_data.get("test_date"),
            "upload_date": datetime.utcnow(),
            "test_results": report_data.get("tests", []),
            "overall_status": self._determine_overall_status(report_data.get("tests", [])),
            "file_url": file_data.get("url"),
            "is_processed": True
        }
        
        return await self.db.save_report(report)
    
    def _determine_overall_status(self, tests):
        """Determine overall report status"""
        if not tests:
            return "unknown"
        
        statuses = [test.get("status") for test in tests]
        
        if "critical" in statuses:
            return "critical"
        elif "high" in statuses or "low" in statuses:
            # Check if severely abnormal
            severe_count = sum(1 for s in statuses if s in ["high", "low"])
            if severe_count > len(statuses) * 0.5:
                return "red"
            else:
                return "yellow"
        else:
            return "green"
    
    async def _analyze_and_send_feedback(self, phone, patient, report_data):
        """Analyze results and send appropriate feedback"""
        tests = report_data.get("tests", [])
        overall_status = self._determine_overall_status(tests)
        
        if overall_status == "green":
            await self._send_green_alert(phone, patient, tests)
        elif overall_status == "yellow":
            await self._send_yellow_alert(phone, patient, tests)
        elif overall_status == "red":
            await self._send_red_alert(phone, patient, tests)
        elif overall_status == "critical":
            await self._send_critical_alert(phone, patient, tests)
    
    async def _send_green_alert(self, phone, patient, tests):
        """Send feedback for normal results"""
        message = f"""✅ *Great News, {patient['patient_name']}!*

All your test results are within normal ranges:

"""
        for test in tests:
            message += f"• *{test['parameter']}*: {test['value']} {test['unit']} (Target: {test['reference_range']})\n"
        
        message += f"""
🎉 Keep up the excellent work! Continue your current management plan:
• Take medications as prescribed
• Follow your diet plan
• Stay physically active
• Monitor regularly

Type *CARE* anytime to access the menu."""
        
        await self.whatsapp.send_message(phone, message)
    
    async def _send_yellow_alert(self, phone, patient, tests):
        """Send feedback for attention needed"""
        abnormal_tests = [t for t in tests if t['status'] in ['high', 'low']]
        
        message = f"""⚠️ *Attention Needed, {patient['patient_name']}*

Some values need attention:

"""
        for test in abnormal_tests:
            message += f"• *{test['parameter']}*: {test['value']} {test['unit']}\n"
            message += f"  Target: {test['reference_range']} ({test['status'].upper()})\n\n"
        
        message += """📋 *Recommendations:*
• Review your diet and exercise
• Ensure medication compliance
• Increase monitoring frequency
• Consider lifestyle modifications

Would you like to schedule a follow-up consultation?

*1.* Yes, schedule teleconsult
*2.* No, I'll monitor myself

Type *CARE* for main menu."""
        
        await self.whatsapp.send_message(phone, message)
    
    async def _send_red_alert(self, phone, patient, tests):
        """Send feedback for concerning results"""
        concerning_tests = [t for t in tests if t['status'] in ['high', 'low']]
        
        message = f"""🔴 *Concerning Results, {patient['patient_name']}*

These values are significantly outside target range:

"""
        for test in concerning_tests:
            message += f"• *{test['parameter']}*: {test['value']} {test['unit']}\n"
            message += f"  Target: {test['reference_range']}\n"
            message += f"  Status: {test['status'].upper()}\n\n"
        
        message += f"""⚠️ *Action Required*

We strongly recommend consulting a doctor within 48 hours.

*Choose an option:*

*1.* 📞 Schedule Teleconsult
*2.* 🏠 Request Home Visit (Colombo)
*3.* 📱 Call Doctor Now: {os.getenv('SUPPORT_PHONE')}

Reply with 1, 2, or 3."""
        
        await self.whatsapp.send_message(phone, message)
        
        # Flag patient as high-risk
        await self.db.update_patient(patient["patient_id"], {"is_high_risk": True})
    
    async def _send_critical_alert(self, phone, patient, tests):
        """Send feedback for emergency results"""
        critical_tests = [t for t in tests if t['status'] == 'critical']
        
        message = f"""🚨 *URGENT - Critical Results*

{patient['patient_name']}, your results show DANGEROUSLY ABNORMAL values:

"""
        for test in critical_tests:
            message += f"• *{test['parameter']}*: {test['value']} {test['unit']}\n"
            message += f"  CRITICAL - Immediate action needed!\n\n"
        
        message += f"""⚠️ *IMMEDIATE MEDICAL ATTENTION REQUIRED*

*Choose now:*

*1.* 🏥 Go to nearest hospital
*2.* 📱 Call Remedi Doctor: {os.getenv('EMERGENCY_PHONE')}

This is an emergency. Please confirm you're taking action."""
        
        await self.whatsapp.send_message(phone, message)
        
        # Send alert to admin/doctor dashboard
        await self._notify_medical_team(patient, critical_tests)
        
        # Mark as critical high-risk
        await self.db.update_patient(patient["patient_id"], {
            "is_high_risk": True,
            "last_critical_alert": datetime.utcnow()
        })
    
    async def _notify_medical_team(self, patient, critical_tests):
        """Notify medical team of critical results"""
        # This would integrate with your admin dashboard
        logger.critical(f"CRITICAL ALERT for patient {patient['patient_id']}: {critical_tests}")
        # Send notification to admin system
        # await self.admin_notifier.send_critical_alert(patient, critical_tests)