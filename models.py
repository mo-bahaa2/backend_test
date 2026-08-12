from pydantic import BaseModel, Field, field_validator
import re
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

    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        words = v.strip().split()
        if len(words) < 3:
            raise ValueError('الاسم يجب أن يكون ثلاثياً على الأقل')
        return v.strip()

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r'^(010|011|012|015)\d{8}$', v):
            raise ValueError('رقم الهاتف يجب أن يكون رقم محمول مصري صحيح (11 رقم يبدأ بـ 010 أو 011 أو 012 أو 015)')
        return v

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
    value: Any
