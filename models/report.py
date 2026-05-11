from datetime import datetime
from typing import Literal, List, Optional

from pydantic import BaseModel


class TestResult(BaseModel):
    parameter: str
    value: str
    unit: str = ""
    reference_range: str = ""
    status: Literal["normal", "elevated", "low", "critical"] = "normal"


class LabReportResult(BaseModel):
    lab_name: Optional[str] = None
    test_date: Optional[str] = None
    results: List[TestResult] = []
    critical_flags: List[str] = []
    extraction_notes: Optional[str] = None


# ── Persistence models (used by MongoDB layer) ────────────────────────────────

class ReportCreate(BaseModel):
    patient_id: str
    lab_name: Optional[str] = None
    test_date: Optional[str] = None
    results: List[TestResult] = []


class ReportResponse(BaseModel):
    report_id: str
    patient_id: str
    lab_name: Optional[str] = None
    test_date: Optional[str] = None
    upload_date: datetime
    results: List[TestResult] = []
    alert_level: str = "unknown"  # green | yellow | red | critical
    minio_object: Optional[str] = None
    is_processed: bool = False
