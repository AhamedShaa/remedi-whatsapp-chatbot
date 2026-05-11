"""handlers/report_handler.py — Lab report upload and AI analysis flow."""
import base64
import json
import re
from datetime import datetime
from typing import Literal

from config.settings import settings
from database.minio_client import minio_client
from ai.client import ai_client, AIServiceError
from ai.pdf_extractor import pdf_extractor, PDFExtractionError
from models.report import LabReportResult, TestResult
from utils.logger import logger


# ── Helpers ──────────────────────────────────────────────────────────────────

def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap JSON in."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def determine_alert_level(
    result: LabReportResult,
) -> Literal["green", "yellow", "red", "critical"]:
    if result.critical_flags or any(r.status == "critical" for r in result.results):
        return "critical"
    abnormal = [r for r in result.results if r.status in ("elevated", "low")]
    if len(abnormal) > 2:
        return "red"
    if abnormal:
        return "yellow"
    return "green"


def _result_line(r: TestResult, show_range: bool = False) -> str:
    unit = f" {r.unit}" if r.unit else ""
    base = f"• {r.parameter}: {r.value}{unit}"
    if r.status == "critical":
        return f"{base} 🚨"
    if r.status in ("elevated", "low"):
        tag = "⚠️"
        if show_range and r.reference_range:
            return f"{base} {tag} (Range: {r.reference_range})"
        return f"{base} {tag}"
    return f"{base} ✓"


# ── Handler ───────────────────────────────────────────────────────────────────

class ReportHandler:
    def __init__(self, db, whatsapp, redis_client):
        self.db = db
        self.whatsapp = whatsapp
        self.redis = redis_client

    async def handle(self, state: dict) -> dict:
        phone = state["phone_number"]
        patient = state["patient"]
        patient_id = patient["patient_id"]
        patient_name = patient["patient_name"]

        try:
            await self._run_flow(state, phone, patient_id, patient_name, patient)
        except Exception:
            logger.opt(exception=True).error(
                f"Unhandled error in ReportHandler for patient {patient_id}"
            )
            await self.whatsapp.send_message(
                phone,
                f"Something went wrong analysing your report.\n"
                f"Please try again or contact us at {settings.support_phone}",
            )
            await self.redis.clear_conversation_state(phone)

        return state

    async def _run_flow(
        self,
        state: dict,
        phone: str,
        patient_id: str,
        patient_name: str,
        patient: dict,
    ) -> None:
        message_type = state["context"]["message_type"]
        media_id = state["context"].get("media_id")
        mime_type = state["context"].get("mime_type", "application/pdf")
        waiting_for = state.get("waiting_for", "")

        logger.info(
            f"ReportHandler._run_flow: patient={patient_id} "
            f"waiting_for={waiting_for!r} message_type={message_type} "
            f"media_id={'yes' if media_id else 'no'}"
        )

        # ── STEP 1: First entry — set Redis state THEN ask for PDF ───────────
        if waiting_for != "report_upload":
            logger.info(f"ReportHandler: first entry for {patient_id}, persisting report_upload state")
            await self.redis.set_conversation_state(
                phone,
                {"stage": "awaiting_report_upload", "waiting_for": "report_upload"},
            )
            await self.whatsapp.send_message(
                phone,
                "Please send your lab report as a PDF file.\n"
                "Photos are not supported yet.\n"
                "Make sure all values are clearly visible.",
            )
            return

        # ── STEP 1b: Continuation — must receive a document ──────────────────
        if not media_id or message_type != "document":
            logger.info(
                f"ReportHandler: still waiting for PDF from {patient_id}, "
                f"got message_type={message_type}"
            )
            await self.whatsapp.send_message(
                phone,
                "Please send your lab report as a PDF file.\n"
                "Photos are not supported yet.",
            )
            # Keep waiting_for as "report_upload" — do not clear state
            return

        # ── STEP 2: Download from WhatsApp ────────────────────────────────────
        media_data = await self.whatsapp.download_media(media_id)
        if not media_data:
            await self.whatsapp.send_message(
                phone,
                f"Could not download your file. Please try sending it again.\n"
                f"If the problem continues contact us at {settings.support_phone}",
            )
            return

        await self.whatsapp.send_message(
            phone,
            "📊 Received your report! Analysing now...\n"
            "This usually takes 30–60 seconds.",
        )

        b64_data: str = media_data["base64"]
        file_bytes: bytes = base64.b64decode(b64_data)

        # ── STEP 3: Generate report ID ────────────────────────────────────────
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        report_id = f"RPT-{patient_id}-{timestamp}"
        logger.info(f"Processing report {report_id} for patient {patient_id}")

        # ── STEP 4: Save original to MinIO (best-effort) ──────────────────────
        object_name: str | None = None
        try:
            object_name = await minio_client.upload_report(
                patient_id, file_bytes, mime_type, report_id
            )
        except Exception:
            logger.opt(exception=True).warning(
                f"MinIO upload failed for {report_id} — analysis continues"
            )

        # ── STEP 5: Extract text from PDF ─────────────────────────────────────
        try:
            extracted_text = await pdf_extractor.extract_from_base64(b64_data)
        except PDFExtractionError:
            await self.whatsapp.send_message(
                phone,
                "We could not read your PDF. Please make sure:\n"
                "✓ The file is a proper PDF (not a photo)\n"
                "✓ File size is under 10 MB\n"
                "✓ The PDF is not password protected\n\n"
                f"If the problem continues send it to {settings.support_phone}",
            )
            await self.redis.clear_conversation_state(phone)
            return

        # ── STEP 6: AI analysis ───────────────────────────────────────────────
        conditions: list = patient.get("health_conditions", [])
        raw_json = await ai_client.analyze_report(
            extracted_text=extracted_text,
            patient_conditions=conditions,
            trace_name="analyze_lab_report",
        )

        try:
            analysis_data = json.loads(_strip_json_fences(raw_json))
        except json.JSONDecodeError:
            logger.warning(f"First JSON parse failed for {report_id}, retrying")
            raw_json = await ai_client.complete(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Return ONLY valid JSON, no other text:\n" + raw_json
                        ),
                    }
                ],
                trace_name="analyze_lab_report_retry",
            )
            try:
                analysis_data = json.loads(_strip_json_fences(raw_json))
            except json.JSONDecodeError as exc:
                logger.error(f"JSON parse retry also failed for {report_id}: {exc}")
                await self.whatsapp.send_message(
                    phone,
                    f"Something went wrong analysing your report.\n"
                    f"Please try again or contact us at {settings.support_phone}",
                )
                await self.redis.clear_conversation_state(phone)
                return

        # ── STEP 7: Validate with Pydantic ────────────────────────────────────
        result = LabReportResult(**analysis_data)
        logger.bind(report_id=report_id, result_count=len(result.results)).info(
            "Lab report parsed successfully"
        )

        # ── STEP 8: Determine alert level ─────────────────────────────────────
        alert_level = determine_alert_level(result)
        logger.info(f"Report {report_id} alert_level={alert_level}")

        # ── STEP 9: Save to MongoDB ───────────────────────────────────────────
        await self.db.save_report({
            "report_id": report_id,
            "patient_id": patient_id,
            "upload_date": datetime.utcnow(),
            "minio_object": object_name,
            "lab_name": result.lab_name,
            "test_date": result.test_date,
            "results": [r.model_dump() for r in result.results],
            "critical_flags": result.critical_flags,
            "alert_level": alert_level,
            "extraction_notes": result.extraction_notes,
        })

        # ── STEP 10: Send WhatsApp response ───────────────────────────────────
        await self._send_alert(phone, patient_name, result, alert_level, report_id)

        # ── STEP 11: Clear conversation state ─────────────────────────────────
        await self.redis.clear_conversation_state(phone)

    # ── Alert messages ────────────────────────────────────────────────────────

    async def _send_alert(
        self,
        phone: str,
        patient_name: str,
        result: LabReportResult,
        alert_level: str,
        report_id: str,
    ) -> None:
        if alert_level == "green":
            await self._send_green(phone, patient_name, result, report_id)
        elif alert_level == "yellow":
            await self._send_yellow(phone, patient_name, result, report_id)
        elif alert_level == "red":
            await self._send_red(phone, patient_name, result, report_id)
        else:
            await self._send_critical(phone, patient_name, result, report_id)

    async def _send_green(
        self,
        phone: str,
        patient_name: str,
        result: LabReportResult,
        report_id: str,
    ) -> None:
        lines = "\n".join(_result_line(r) for r in result.results)
        await self.whatsapp.send_message(
            phone,
            f"✅ *Lab Report Analysis Complete*\n\n"
            f"Great news {patient_name}! All your results are within normal ranges.\n\n"
            f"📋 *Results Summary:*\n{lines}\n\n"
            f"Keep up the great work! Continue your current management plan.\n\n"
            f"*Report ID:* {report_id}\n"
            f"Type *CARE* to return to the main menu.",
        )

    async def _send_yellow(
        self,
        phone: str,
        patient_name: str,
        result: LabReportResult,
        report_id: str,
    ) -> None:
        normal = [r for r in result.results if r.status == "normal"]
        abnormal = [r for r in result.results if r.status in ("elevated", "low")]

        normal_lines = "\n".join(_result_line(r) for r in normal)
        abnormal_lines = "\n".join(_result_line(r, show_range=True) for r in abnormal)

        sections = ""
        if normal_lines:
            sections += f"{normal_lines}\n"
        if abnormal_lines:
            sections += f"{abnormal_lines}"

        await self.whatsapp.send_message(
            phone,
            f"⚠️ *Lab Report Analysis Complete*\n\n"
            f"Hi {patient_name}, most results look good but some values need attention.\n\n"
            f"📋 *Results Summary:*\n{sections}\n\n"
            f"*Recommendations:*\n"
            f"- Discuss these results with your doctor\n"
            f"- Consider booking a teleconsult (reply *1*)\n\n"
            f"*Report ID:* {report_id}",
        )

    async def _send_red(
        self,
        phone: str,
        patient_name: str,
        result: LabReportResult,
        report_id: str,
    ) -> None:
        concerning = [r for r in result.results if r.status in ("elevated", "low", "critical")]
        lines = "\n".join(
            f"• {r.parameter}: {r.value}{' ' + r.unit if r.unit else ''}"
            f"{' (Range: ' + r.reference_range + ')' if r.reference_range else ''}"
            for r in concerning
        )
        await self.whatsapp.send_message(
            phone,
            f"🔴 *Important: Results Need Attention*\n\n"
            f"Hi {patient_name}, some of your results are significantly outside normal ranges.\n\n"
            f"*Concerning Results:*\n{lines}\n\n"
            f"*Please consult a doctor within 48 hours.*\n\n"
            f"Reply with:\n"
            f"*1* - Book teleconsult\n"
            f"*4* - Request home visit\n"
            f"*5* - Chat with doctor now\n\n"
            f"*Report ID:* {report_id}",
        )

    async def _send_critical(
        self,
        phone: str,
        patient_name: str,
        result: LabReportResult,
        report_id: str,
    ) -> None:
        critical = [r for r in result.results if r.status == "critical"]
        if not critical and result.critical_flags:
            # Fall back to named flags when result objects don't carry status="critical"
            lines = "\n".join(f"• {flag}" for flag in result.critical_flags)
        else:
            lines = "\n".join(
                f"• {r.parameter}: {r.value}{' ' + r.unit if r.unit else ''} 🚨"
                for r in critical
            )
        await self.whatsapp.send_message(
            phone,
            f"🚨 *URGENT: Critical Values Detected*\n\n"
            f"{patient_name}, your report shows values that need IMMEDIATE medical attention.\n\n"
            f"*Critical Values:*\n{lines}\n\n"
            f"⚠️ Please seek medical care IMMEDIATELY.\n\n"
            f"Options:\n"
            f"• Go to nearest hospital emergency\n"
            f"• Call Remedi doctor: {settings.emergency_phone}\n"
            f"• Reply *5* to chat with doctor now\n\n"
            f"Please reply *YES* to confirm you have seen this alert.",
        )
