from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


class DoctorCreate(BaseModel):
    name: str
    email: str
    specialty: str
    whatsapp_number: Optional[str] = None
    password: str


class DoctorUpdate(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    whatsapp_number: Optional[str] = None
    status: Optional[str] = None  # online | offline | busy


class DoctorResponse(BaseModel):
    doctor_id: str
    name: str
    email: str
    specialty: str
    status: str = "offline"
    created_at: Optional[datetime] = None


class DoctorLogin(BaseModel):
    email: str
    password: str
