from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class PatientCreate(BaseModel):
    patient_name: str
    whatsapp_number: str
    age: int
    gender: str
    health_conditions: List[str] = []
    medications: str = ""
    allergies: str = "None"
    emergency_contact: str = ""
    payment_status: str = "pending"


class PatientUpdate(BaseModel):
    patient_name: Optional[str] = None
    age: Optional[int] = None
    medications: Optional[str] = None
    allergies: Optional[str] = None
    emergency_contact: Optional[str] = None
    health_conditions: Optional[List[str]] = None
    approval_status: Optional[str] = None
    payment_status: Optional[str] = None
    is_high_risk: Optional[bool] = None


class PatientResponse(BaseModel):
    patient_id: str
    patient_name: str
    whatsapp_number: str
    age: int
    gender: str
    health_conditions: List[str] = []
    medications: str = ""
    approval_status: str
    payment_status: str
    is_high_risk: bool = False
    enrollment_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
