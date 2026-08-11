from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import date, time, datetime
from uuid import UUID

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = 30
    price: float = 0.0
    is_active: bool = True

class ServiceCreate(ServiceBase):
    pass

class ServiceResponse(ServiceBase):
    id: UUID
    created_at: datetime

class BookingCreatePublic(BaseModel):
    full_name: str
    phone: str
    email: Optional[str] = None
    service_id: UUID
    booking_date: date
    booking_time: time
    notes: Optional[str] = None

class BookingCreateManual(BookingCreatePublic):
    pass

class BookingStatusUpdate(BaseModel):
    status: str # pending, confirmed, completed, cancelled

class BookingResponse(BaseModel):
    id: UUID
    client_id: UUID
    service_id: UUID
    booking_date: date
    booking_time: time
    status: str
    price_at_booking: float
    notes: Optional[str]
    source: str
    created_at: datetime
    
    # Relationships for convenience
    client: Optional[dict] = None
    service: Optional[dict] = None

class SettingUpdate(BaseModel):
    value: dict
