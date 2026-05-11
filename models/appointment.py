from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AppointmentCreate(BaseModel):
    patient_id: str
    type: str = "teleconsult"  # teleconsult | home_visit
    scheduled_date: datetime
    scheduled_time: str
    doctor_name: str = ""
    notes: str = ""


class AppointmentUpdate(BaseModel):
    status: Optional[str] = None  # scheduled | confirmed | link_sent | completed | cancelled
    doctor_name: Optional[str] = None
    meeting_link: Optional[str] = None
    reminder_24h_sent: Optional[bool] = None
    reminder_2h_sent: Optional[bool] = None
    link_sent: Optional[bool] = None


class AppointmentResponse(BaseModel):
    appointment_id: str
    patient_id: str
    type: str
    scheduled_date: datetime
    scheduled_time: str
    doctor_name: str = ""
    status: str
    meeting_link: Optional[str] = None
    created_at: Optional[datetime] = None
