"""routes/admin.py — Admin-only endpoints (JWT protected, role=admin)."""
import json
from datetime import datetime

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from config.settings import settings
from core.dependencies import require_role
from utils.logger import logger

router = APIRouter(tags=["admin"])

_admin = Depends(require_role("admin"))

# ── Valid ARQ job names (short alias → registered function name) ──────────────

_JOB_MAP = {
    "blood_test_reminders": "send_blood_test_reminders",
    "health_tips": "send_health_tips",
    "appointment_reminders": "send_appointment_reminders",
    "bp_patterns": "check_bp_patterns",
    "annual_reports": "generate_annual_reports",
}


# ── Request models ────────────────────────────────────────────────────────────

class TriggerJobRequest(BaseModel):
    job_name: str


# ── Existing endpoints (migrated from main.py) ────────────────────────────────

@router.get("/stats", dependencies=[_admin])
async def get_admin_stats(request: Request):
    """Admin dashboard statistics."""
    try:
        return await request.app.state.db.get_admin_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve-patient", dependencies=[_admin])
async def approve_patient(patient_id: str, request: Request):
    """Approve patient enrollment and send welcome message."""
    db = request.app.state.db
    whatsapp = request.app.state.whatsapp

    patient = await db.get_patient_by_id(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    await db.update_patient(patient_id, {
        "approval_status": "approved",
        "payment_status": "completed",
        "approval_date": datetime.utcnow(),
    })
    await db.schedule_blood_tests(patient_id)
    await whatsapp.send_welcome_message(patient["whatsapp_number"], patient["patient_name"])
    return {"status": "success", "message": f"Patient {patient_id} approved"}


@router.post("/approve-by-phone", dependencies=[_admin])
async def approve_by_phone(phone: str, key: str, request: Request):
    """Quick approve by phone number for testing."""
    if key != settings.google_form_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    db = request.app.state.db
    whatsapp = request.app.state.whatsapp

    patient = await db.get_patient_by_phone(phone)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    await db.update_patient(patient["patient_id"], {
        "approval_status": "approved",
        "payment_status": "completed",
        "approval_date": datetime.utcnow(),
    })
    await db.schedule_blood_tests(patient["patient_id"])
    await whatsapp.send_welcome_message(phone, patient["patient_name"])

    return {
        "status": "success",
        "patient_id": patient["patient_id"],
        "message": "Patient approved and welcome message sent",
    }


@router.post("/send-health-tip", dependencies=[_admin])
async def send_health_tip_manual(patient_id: str, condition: str, request: Request):
    """Send a health tip to a specific patient."""
    from jobs.health_tips import send_health_tip_to_patient
    try:
        await send_health_tip_to_patient(
            patient_id, condition,
            request.app.state.db,
            request.app.state.whatsapp,
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-send", dependencies=[_admin])
async def admin_test_send(to: str, key: str, request: Request):
    """Send a test WhatsApp message to validate sending."""
    if key != settings.google_form_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    ok = await request.app.state.whatsapp.send_message(to, "Test message from Remedi bot ✅")
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send test message")
    return {"status": "success"}


@router.post("/trigger-job", dependencies=[_admin])
async def trigger_job(body: TriggerJobRequest):
    """Manually enqueue an ARQ background job for testing."""
    if body.job_name not in _JOB_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown job '{body.job_name}'. Valid jobs: {sorted(_JOB_MAP)}",
        )
    try:
        fn_name = _JOB_MAP[body.job_name]
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await pool.enqueue_job(fn_name)
        await pool.aclose()
        logger.info(f"Admin triggered job: {fn_name}")
        return {"status": "queued", "job": body.job_name}
    except Exception as e:
        logger.opt(exception=True).error(f"Failed to enqueue job {body.job_name}")
        raise HTTPException(status_code=500, detail=str(e))


# ── New patient management endpoints ─────────────────────────────────────────

@router.get("/patients", dependencies=[_admin])
async def list_patients(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    status: str = None,
):
    """List all patients with optional status filter and pagination."""
    db = request.app.state.db
    query = {}
    if status:
        query["approval_status"] = status

    cursor = db.db.patients.find(query, {"_id": 0}).skip(skip).limit(limit)
    patients = await cursor.to_list(length=limit)
    total = await db.db.patients.count_documents(query)

    return {"patients": patients, "total": total, "skip": skip, "limit": limit}


@router.get("/patients/{patient_id}", dependencies=[_admin])
async def get_patient(patient_id: str, request: Request):
    """Full detail for a single patient."""
    patient = await request.app.state.db.get_patient_by_id(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient.pop("_id", None)
    return patient


@router.get("/audit-logs", dependencies=[_admin])
async def get_audit_logs(
    request: Request,
    patient_id: str = None,
    actor_id: str = None,
    limit: int = 100,
):
    """Fetch recent audit log entries."""
    logs = await request.app.state.db.get_audit_logs(
        patient_id=patient_id,
        actor_id=actor_id,
        limit=limit,
    )
    # Strip MongoDB _id from each log
    for log in logs:
        log.pop("_id", None)
    return {"logs": logs, "count": len(logs)}
