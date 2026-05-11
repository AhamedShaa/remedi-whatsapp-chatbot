"""routes/doctor.py — Doctor-facing endpoints (JWT protected, role=doctor or admin)."""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.dependencies import require_role
from database.minio_client import minio_client
from utils.logger import logger

router = APIRouter(tags=["doctor"])

_doctor_or_admin = Depends(require_role("doctor", "admin"))


# ── Request models ────────────────────────────────────────────────────────────

class ConsultationNoteRequest(BaseModel):
    note: str
    appointment_id: str | None = None


# ── Authorization helper ──────────────────────────────────────────────────────

async def _assert_patient_access(db, patient_id: str, current_user: dict) -> None:
    """Raise 403 if a doctor tries to access a patient not assigned to them."""
    if current_user["role"] == "admin":
        return
    apt = await db.db.appointments.find_one(
        {"patient_id": patient_id, "doctor_id": current_user["user_id"]}
    )
    if not apt:
        raise HTTPException(
            status_code=403,
            detail="Patient is not assigned to you",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/my-patients")
async def my_patients(
    request: Request,
    current_user: dict = Depends(require_role("doctor", "admin")),
):
    """Return patients who have appointments assigned to the requesting doctor."""
    db = request.app.state.db
    doctor_id = current_user["user_id"]

    pipeline = [
        {"$match": {"doctor_id": doctor_id}},
        {"$group": {"_id": "$patient_id"}},
    ]
    results = await db.db.appointments.aggregate(pipeline).to_list(length=None)
    patient_ids = [r["_id"] for r in results]

    if not patient_ids:
        return {"patients": [], "total": 0}

    cursor = db.db.patients.find({"patient_id": {"$in": patient_ids}}, {"_id": 0})
    patients = await cursor.to_list(length=None)
    return {"patients": patients, "total": len(patients)}


@router.get("/patients/{patient_id}")
async def get_patient(
    patient_id: str,
    request: Request,
    current_user: dict = Depends(require_role("doctor", "admin")),
):
    """Full patient detail including recent reports and BP readings."""
    db = request.app.state.db
    await _assert_patient_access(db, patient_id, current_user)

    patient = await db.get_patient_by_id(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient.pop("_id", None)

    recent_reports = await db.get_patient_reports(patient_id, limit=5)
    for r in recent_reports:
        r.pop("_id", None)

    recent_bp = await db.get_recent_bp_readings(patient_id, limit=10)
    for r in recent_bp:
        r.pop("_id", None)

    return {
        "patient": patient,
        "recent_reports": recent_reports,
        "recent_bp_readings": recent_bp,
    }


@router.get("/patients/{patient_id}/reports")
async def get_patient_reports(
    patient_id: str,
    request: Request,
    current_user: dict = Depends(require_role("doctor", "admin")),
):
    """All lab reports for a patient with presigned MinIO download URLs."""
    db = request.app.state.db
    await _assert_patient_access(db, patient_id, current_user)

    reports = await db.get_patient_reports(patient_id, limit=50)
    for report in reports:
        report.pop("_id", None)
        if report.get("minio_object"):
            try:
                report["download_url"] = await minio_client.get_report_url(report["minio_object"])
            except Exception:
                report["download_url"] = None

    return {"reports": reports, "count": len(reports)}


@router.get("/patients/{patient_id}/bp-history")
async def get_bp_history(
    patient_id: str,
    request: Request,
    current_user: dict = Depends(require_role("doctor", "admin")),
):
    """BP readings for the last 90 days, formatted for charting."""
    db = request.app.state.db
    await _assert_patient_access(db, patient_id, current_user)

    readings = await db.get_recent_bp_readings(patient_id, days=90)

    chart_data = [
        {
            "date": (
                r["reading_date"].isoformat()
                if isinstance(r.get("reading_date"), datetime)
                else str(r.get("reading_date", ""))
            ),
            "systolic": r.get("systolic"),
            "diastolic": r.get("diastolic"),
            "pulse": r.get("pulse"),
        }
        for r in readings
    ]

    if readings:
        avg_sys = round(sum(r.get("systolic", 0) for r in readings) / len(readings))
        avg_dia = round(sum(r.get("diastolic", 0) for r in readings) / len(readings))
    else:
        avg_sys = avg_dia = 0

    return {
        "patient_id": patient_id,
        "period_days": 90,
        "readings": chart_data,
        "count": len(readings),
        "averages": {"systolic": avg_sys, "diastolic": avg_dia},
    }


@router.post("/patients/{patient_id}/notes")
async def add_note(
    patient_id: str,
    body: ConsultationNoteRequest,
    request: Request,
    current_user: dict = Depends(require_role("doctor", "admin")),
):
    """Save a consultation note for a patient."""
    db = request.app.state.db
    await _assert_patient_access(db, patient_id, current_user)

    note_doc = {
        "patient_id": patient_id,
        "doctor_id": current_user["user_id"],
        "doctor_name": current_user.get("name", ""),
        "note": body.note,
        "appointment_id": body.appointment_id,
        "created_at": datetime.utcnow(),
    }
    await db.db.consultation_notes.insert_one(note_doc)
    logger.info(f"Consultation note saved: patient={patient_id} doctor={current_user['user_id']}")
    return {"status": "saved", "patient_id": patient_id}


@router.get("/queue")
async def doctor_queue(
    request: Request,
    current_user: dict = Depends(require_role("doctor", "admin")),
):
    """Patients currently waiting in doctor chat (from Redis conversation state)."""
    redis = request.app.state.redis
    queue = []

    try:
        keys = await redis.client.keys("conv:*")
        for key in keys:
            raw = await redis.client.get(key)
            if not raw:
                continue
            state = json.loads(raw)
            if state.get("waiting_for") != "doctor_chat":
                continue
            # Doctors only see their own queue; admins see all
            if (
                current_user["role"] == "doctor"
                and state.get("doctor_id") != current_user["user_id"]
            ):
                continue
            phone = key.removeprefix("conv:")
            queue.append({
                "phone": phone,
                "doctor_id": state.get("doctor_id"),
                "doctor_name": state.get("doctor_name"),
            })
    except Exception:
        logger.opt(exception=True).error("Failed to fetch doctor queue from Redis")

    return {"queue": queue, "count": len(queue)}
