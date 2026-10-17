from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from database import supabase
from models import *
from typing import List, Optional
from datetime import datetime, date
import os
import secrets
import uuid
import json

app = FastAPI(title="Lawyer Booking API", docs_url=None, redoc_url=None, openapi_url=None)

# --- Security for Swagger UI ---
security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    # Default username: admin, password: lawyer2026 (change in .env later)
    correct_username = secrets.compare_digest(credentials.username, os.getenv("ADMIN_USERNAME", "Abeer"))
    correct_password = secrets.compare_digest(credentials.password, os.getenv("ADMIN_PASSWORD", "ASKEoOEUEI#$@#$@@#@#$@#@#$_sdfjkkjsdkjmdikkdyfijdj"))
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
# -------------------------------

# --- Secure Swagger Routes ---
@app.get("/docs", include_in_schema=False)
async def get_documentation(username: str = Depends(get_current_username)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="API Documentation")

@app.get("/openapi.json", include_in_schema=False)
async def openapi(username: str = Depends(get_current_username)):
    return get_openapi(title=app.title, version=app.version, routes=app.routes)
# -------------------------------

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, change this to the frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Lawyer API is running"}

# ==========================================
# SERVICES
# ==========================================
@app.get("/api/services", response_model=List[ServiceResponse], summary="جلب الخدمات")
def get_services(active_only: bool = True):
    """يجلب قائمة بجميع الخدمات المتوفرة في النظام لكي يراها العميل"""
    query = supabase.table('services').select('*')
    if active_only:
        query = query.eq('is_active', True)
    response = query.execute()
    return response.data

@app.post("/api/services", response_model=ServiceResponse, summary="إضافة خدمة جديدة")
def create_service(service: ServiceCreate, username: str = Depends(get_current_username)):
    """يقوم المحامي بإنشاء خدمة جديدة بالسعر والمدة الزمنية"""
    response = supabase.table('services').insert(service.model_dump()).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create service")
    return response.data[0]

@app.put("/api/services/{service_id}", response_model=ServiceResponse)
def update_service(service_id: str, service: ServiceCreate, username: str = Depends(get_current_username)):
    response = supabase.table('services').update(service.model_dump()).eq('id', service_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Service not found")
    return response.data[0]

# ==========================================
# CLIENTS
# ==========================================
@app.get("/api/clients", summary="جلب كل العملاء")
def get_clients(username: str = Depends(get_current_username)):
    """يجلب قائمة بجميع العملاء المسجلين في النظام، مرتبين من الأحدث للأقدم."""
    response = supabase.table('clients').select('*').order('created_at', desc=True).execute()
    return response.data

@app.delete("/api/clients/{client_id}", summary="حذف عميل")
def delete_client(client_id: str, username: str = Depends(get_current_username)):
    """يحذف عميل معين من قاعدة البيانات بشكل نهائي."""
    try:
        response = supabase.table('clients').delete().eq('id', client_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Client not found")
        return {"message": "Client deleted successfully"}
    except Exception as e:
        error_msg = str(e).lower()
        if "foreign key" in error_msg or "23503" in error_msg or "violates foreign key constraint" in error_msg:
            raise HTTPException(status_code=400, detail="لا يمكن حذف هذا العميل لوجود حجوزات سابقة مرتبطة به. يرجى حذف حجوزاته أولاً.")
        raise HTTPException(status_code=500, detail="حدث خطأ أثناء الحذف")

# ==========================================
# BOOKINGS
# ==========================================
@app.post("/api/bookings", response_model=BookingResponse, summary="إنشاء حجز جديد")
def create_booking(booking: BookingCreatePublic):
    """الرابط الذي يستخدمه موقع العميل لإنشاء حجز جديد مع التأكد من عدم وجود تعارض"""
    service_res = supabase.table('services').select('*').eq('id', str(booking.service_id)).execute()
    if not service_res.data:
        raise HTTPException(status_code=404, detail="Service not found")
    
    service_data = service_res.data[0]
    current_price = service_data['price']

    # 2. Check for double booking / overlapping booking
    req_time_str = str(booking.booking_time)
    req_parts = req_time_str.split(':')
    req_start = int(req_parts[0]) * 60 + int(req_parts[1])
    req_dur = int(service_data.get('duration_minutes', 30))
    req_end = req_start + req_dur

    existing_bookings = supabase.table('bookings')\
        .select('booking_time, service:services(duration_minutes)')\
        .eq('booking_date', str(booking.booking_date))\
        .in_('status', ['pending', 'confirmed', 'completed'])\
        .execute()

    for eb in (existing_bookings.data or []):
        eb_time_parts = str(eb['booking_time']).split(':')
        eb_start = int(eb_time_parts[0]) * 60 + int(eb_time_parts[1])
        eb_dur = 30
        if eb.get('service') and isinstance(eb['service'], dict) and eb['service'].get('duration_minutes'):
            eb_dur = int(eb['service']['duration_minutes'])
        eb_end = eb_start + eb_dur

        if max(req_start, eb_start) < min(req_end, eb_end):
            raise HTTPException(status_code=400, detail="هذا الموعد يتعارض مع حجز قائم، برجاء اختيار موعد آخر")

    # 3. Find or create client by phone
    client_res = supabase.table('clients').select('*').eq('phone', booking.phone).execute()
    if client_res.data:
        client_id = client_res.data[0]['id']
    else:
        # Create new client
        new_client = {
            "phone": booking.phone,
            "full_name": booking.full_name,
            "email": booking.email
        }
        create_client_res = supabase.table('clients').insert(new_client).execute()
        client_id = create_client_res.data[0]['id']

    # 4. Create the booking
    new_booking = {
        "client_id": client_id,
        "service_id": str(booking.service_id),
        "booking_date": str(booking.booking_date),
        "booking_time": str(booking.booking_time),
        "price_at_booking": current_price,
        "notes": booking.notes,
        "source": "online",
        "case_type": booking.case_type
    }
    
    try:
        booking_res = supabase.table('bookings').insert(new_booking).execute()
        return booking_res.data[0]
    except Exception as e:
        # Fallback if case_type column is not yet migrated in Supabase table
        if "case_type" in str(e).lower():
            del new_booking["case_type"]
            prefix = f"[نوع القضية: {booking.case_type}]" if booking.case_type else ""
            if prefix:
                new_booking["notes"] = f"{prefix}\n{booking.notes}" if booking.notes else prefix
            booking_res = supabase.table('bookings').insert(new_booking).execute()
            data = booking_res.data[0]
            data["case_type"] = booking.case_type
            return data
        raise e

@app.get("/api/bookings", summary="جلب كل الحجوزات")
def get_bookings(username: str = Depends(get_current_username)):
    """يجلب كل الحجوزات لكي يراها المحامي في لوحة التحكم"""
    response = supabase.table('bookings').select('*, client:clients(*), service:services(*)').order('booking_date', desc=True).order('booking_time', desc=True).execute()
    data = response.data or []
    for b in data:
        # If case_type column does not exist or is empty, extract from notes if present
        if not b.get('case_type') and b.get('notes') and '[نوع القضية:' in b.get('notes'):
            try:
                m = re.search(r'\[نوع القضية:\s*([^\]]+)\]', b['notes'])
                if m:
                    b['case_type'] = m.group(1).strip()
            except Exception:
                pass
    return data

@app.put("/api/bookings/{booking_id}/status", summary="تغيير حالة الحجز")
def update_booking_status(booking_id: str, status_update: BookingStatusUpdate, username: str = Depends(get_current_username)):
    """يسمح بتغيير حالة الحجز (مثلاً من pending إلى completed)"""
    response = supabase.table('bookings').update({"status": status_update.status}).eq('id', booking_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    return response.data[0]

@app.delete("/api/bookings/{booking_id}", summary="حذف حجز")
def delete_booking(booking_id: str, username: str = Depends(get_current_username)):
    """يحذف حجز معين من النظام تماماً."""
    response = supabase.table('bookings').delete().eq('id', booking_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"message": "Booking deleted successfully"}

@app.get("/api/bookings/available-slots")
def get_available_slots(date_str: str, service_id: Optional[str] = None):
    # 1. Get settings
    settings_res = supabase.table('settings').select('value').eq('key', 'working_hours').execute()
    if not settings_res.data:
        start_time = "10:00"
        end_time = "18:00"
        work_days = [1,2,3,4,5,6] # ISO 1=Mon, 6=Sat
    else:
        schedule = settings_res.data[0]['value']
        start_time = schedule.get('start', '10:00')
        end_time = schedule.get('end', '18:00')
        work_days = schedule.get('days', [1,2,3,4,5,6])
    
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if dt.isoweekday() not in work_days:
            return [] # Day is off
    except:
        pass

    # 2. Determine requested service duration (default to 30 mins)
    duration_minutes = 30
    if service_id:
        try:
            s_res = supabase.table('services').select('duration_minutes').eq('id', service_id).execute()
            if s_res.data and s_res.data[0].get('duration_minutes'):
                duration_minutes = int(s_res.data[0]['duration_minutes'])
        except Exception as e:
            print("Error fetching service duration:", e)

    # Helper functions to convert between time string and minutes from midnight
    def time_to_minutes(t_str: str) -> int:
        parts = str(t_str).split(':')
        return int(parts[0]) * 60 + int(parts[1])

    def minutes_to_timestr(mins: int) -> str:
        h = mins // 60
        m = mins % 60
        return f"{h:02d}:{m:02d}:00"

    try:
        start_min = time_to_minutes(start_time)
        end_min = time_to_minutes(end_time)
    except:
        start_min = 10 * 60
        end_min = 18 * 60

    # 3. Get booked slots for the date with service durations
    booked_res = supabase.table('bookings')\
        .select('booking_time, service:services(duration_minutes)')\
        .eq('booking_date', date_str)\
        .in_('status', ['pending', 'confirmed', 'completed'])\
        .execute()

    occupied_ranges = []
    for b in (booked_res.data or []):
        try:
            b_start = time_to_minutes(b['booking_time'])
            b_dur = 30
            if b.get('service') and isinstance(b['service'], dict) and b['service'].get('duration_minutes'):
                b_dur = int(b['service']['duration_minutes'])
            b_end = b_start + b_dur
            occupied_ranges.append((b_start, b_end))
        except Exception as err:
            print("Error parsing booked time range:", err)

    # 4. Generate candidate slots in 15-minute steps
    # 15 minutes allows flexible chaining of 15, 30, 45, 60 min appointments
    step_minutes = 15
    available_slots = []

    current_min = start_min
    while current_min + duration_minutes <= end_min:
        slot_start = current_min
        slot_end = current_min + duration_minutes

        # Check for overlap: max(A, C) < min(B, D)
        has_conflict = False
        for (occ_start, occ_end) in occupied_ranges:
            if max(slot_start, occ_start) < min(slot_end, occ_end):
                has_conflict = True
                break

        if not has_conflict:
            available_slots.append(minutes_to_timestr(slot_start))

        current_min += step_minutes

    return available_slots

# ==========================================
# DASHBOARD STATS
# ==========================================
@app.get("/api/stats", summary="إحصائيات لوحة التحكم")
def get_dashboard_stats(username: str = Depends(get_current_username)):
    """يحسب الأرباح الكلية وعدد العملاء والحجوزات القادمة لعرضها في الشاشة الرئيسية للأدمن"""
    clients = supabase.table('clients').select('id', count='exact').execute()
    total_clients = clients.count
    
    # Get total revenue (excluding cancelled)
    completed_bookings = supabase.table('bookings').select('price_at_booking').in_('status', ['pending', 'confirmed', 'completed']).execute()
    total_revenue = sum(float(b['price_at_booking'] or 0) for b in completed_bookings.data)
    
    # Get upcoming bookings
    today = str(date.today())
    upcoming_bookings = supabase.table('bookings').select('id', count='exact').gte('booking_date', today).in_('status', ['pending', 'confirmed']).execute()
    total_upcoming = upcoming_bookings.count
    
    return {
        "total_clients": total_clients,
        "total_revenue": total_revenue,
        "upcoming_bookings": total_upcoming
    }

# ==========================================
# SETTINGS
# ==========================================
@app.get("/api/settings")
def get_settings():
    response = supabase.table('settings').select('*').execute()
    return {item['key']: item['value'] for item in response.data}

@app.put("/api/settings/{key}")
def update_setting(key: str, setting: SettingUpdate, username: str = Depends(get_current_username)):
    response = supabase.table('settings').update({"value": setting.value}).eq('key', key).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Setting not found")
    return response.data[0]

# ==========================================
# CONTACT MESSAGES (الرسائل والاستفسارات)
# ==========================================
LOCAL_MESSAGES_FILE = os.path.join(os.path.dirname(__file__), "messages_store.json")

def _read_local_messages() -> list:
    if os.path.exists(LOCAL_MESSAGES_FILE):
        try:
            with open(LOCAL_MESSAGES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def _write_local_messages(msgs: list) -> None:
    try:
        with open(LOCAL_MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

@app.post("/api/messages", summary="إرسال استفسار جديد")
def create_message(msg: MessageCreate):
    new_id = str(uuid.uuid4())
    now_iso = datetime.utcnow().isoformat()
    record = {
        "id": new_id,
        "name": msg.name,
        "phone": msg.phone,
        "subject": msg.subject,
        "message": msg.message,
        "is_read": False,
        "created_at": now_iso
    }

    # 1. Try Supabase messages table
    try:
        res = supabase.table('messages').insert(record).execute()
        if res.data:
            return {"message": "تم إرسال رسالتك بنجاح", "id": new_id}
    except Exception:
        pass

    # 2. Try Supabase settings table (contact_messages)
    try:
        settings_res = supabase.table('settings').select('value').eq('key', 'contact_messages').execute()
        current_list = settings_res.data[0]['value'] if settings_res.data else []
        current_list.insert(0, record)
        if settings_res.data:
            supabase.table('settings').update({'value': current_list}).eq('key', 'contact_messages').execute()
        else:
            supabase.table('settings').insert({'key': 'contact_messages', 'value': current_list}).execute()
        return {"message": "تم إرسال رسالتك بنجاح", "id": new_id}
    except Exception:
        pass

    # 3. Fallback to local file store
    msgs = _read_local_messages()
    msgs.insert(0, record)
    _write_local_messages(msgs)
    return {"message": "تم إرسال رسالتك بنجاح", "id": new_id}

@app.get("/api/messages", summary="جلب جميع الرسائل")
def get_messages(username: str = Depends(get_current_username)):
    # 1. Try Supabase messages table
    try:
        res = supabase.table('messages').select('*').order('created_at', desc=True).execute()
        if res.data is not None and len(res.data) > 0:
            return res.data
    except Exception:
        pass

    # 2. Try Supabase settings
    try:
        settings_res = supabase.table('settings').select('value').eq('key', 'contact_messages').execute()
        if settings_res.data and settings_res.data[0]['value']:
            return settings_res.data[0]['value']
    except Exception:
        pass

    # 3. Fallback to local
    return _read_local_messages()

@app.patch("/api/messages/{message_id}/read", summary="تحديث حالة القراءة")
def toggle_message_read(message_id: str, is_read: bool = True, username: str = Depends(get_current_username)):
    # 1. Try Supabase messages
    try:
        supabase.table('messages').update({'is_read': is_read}).eq('id', message_id).execute()
    except Exception:
        pass

    # 2. Try Supabase settings
    try:
        settings_res = supabase.table('settings').select('value').eq('key', 'contact_messages').execute()
        if settings_res.data:
            msgs = settings_res.data[0]['value']
            for m in msgs:
                if m.get('id') == message_id:
                    m['is_read'] = is_read
            supabase.table('settings').update({'value': msgs}).eq('key', 'contact_messages').execute()
    except Exception:
        pass

    # 3. Local fallback
    msgs = _read_local_messages()
    for m in msgs:
        if m.get('id') == message_id:
            m['is_read'] = is_read
    _write_local_messages(msgs)
    return {"message": "تم التحديث بنجاح"}

@app.delete("/api/messages/{message_id}", summary="حذف رسالة")
def delete_message(message_id: str, username: str = Depends(get_current_username)):
    # 1. Try Supabase messages
    try:
        supabase.table('messages').delete().eq('id', message_id).execute()
    except Exception:
        pass

    # 2. Try Supabase settings
    try:
        settings_res = supabase.table('settings').select('value').eq('key', 'contact_messages').execute()
        if settings_res.data:
            msgs = [m for m in settings_res.data[0]['value'] if m.get('id') != message_id]
            supabase.table('settings').update({'value': msgs}).eq('key', 'contact_messages').execute()
    except Exception:
        pass

    # 3. Local fallback
    msgs = [m for m in _read_local_messages() if m.get('id') != message_id]
    _write_local_messages(msgs)
    return {"message": "تم حذف الرسالة بنجاح"}

