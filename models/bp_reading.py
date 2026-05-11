from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class BPReadingCreate(BaseModel):
    patient_id: str
    systolic: int
    diastolic: int
    pulse: Optional[int] = None
    notes: str = ""

    @field_validator("systolic")
    @classmethod
    def systolic_range(cls, v: int) -> int:
        if not 60 <= v <= 250:
            raise ValueError("Systolic must be between 60 and 250")
        return v

    @field_validator("diastolic")
    @classmethod
    def diastolic_range(cls, v: int) -> int:
        if not 40 <= v <= 150:
            raise ValueError("Diastolic must be between 40 and 150")
        return v


class BPReadingResponse(BaseModel):
    id: Optional[str] = None
    patient_id: str
    systolic: int
    diastolic: int
    pulse: Optional[int] = None
    classification: str = "normal"  # normal | elevated | high | critical
    reading_date: datetime
    notes: str = ""
