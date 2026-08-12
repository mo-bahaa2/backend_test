from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from database import supabase
from models import *
from typing import List
from datetime import datetime, date
import os
import secrets

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

    # 2. Check for double booking (Race condition prevention)
    existing = supabase.table('bookings').select('id').eq('booking_date', str(booking.booking_date)).eq('booking_time', str(booking.booking_time)).in_('status', ['pending', 'confirmed', 'completed']).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="هذا الموعد تم حجزه للتو، برجاء اختيار موعد آخر")

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
        "source": "online" # or manual if requested from admin
    }
    
    booking_res = supabase.table('bookings').insert(new_booking).execute()
    return booking_res.data[0]

@app.get("/api/bookings", summary="جلب كل الحجوزات")
def get_bookings(username: str = Depends(get_current_username)):
    """يجلب كل الحجوزات لكي يراها المحامي في لوحة التحكم"""
    response = supabase.table('bookings').select('*, client:clients(*), service:services(*)').order('booking_date', desc=True).order('booking_time', desc=True).execute()
    return response.data

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
def get_available_slots(date_str: str):
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
    
    # Generate slots every hour
    all_slots = []
    try:
        start_h = int(start_time.split(':')[0])
        end_h = int(end_time.split(':')[0])
        for h in range(start_h, end_h):
            all_slots.append(f"{h:02d}:00:00")
            all_slots.append(f"{h:02d}:30:00") # 30 min intervals
    except:
        all_slots = ["10:00:00", "11:00:00", "12:00:00", "13:00:00", "14:00:00", "15:00:00", "16:00:00"]
        
    # 2. Get booked slots for the date
    booked_res = supabase.table('bookings').select('booking_time').eq('booking_date', date_str).in_('status', ['pending', 'confirmed', 'completed']).execute()
    booked_times = [b['booking_time'] for b in booked_res.data]
    
    available_slots = [slot for slot in all_slots if slot not in booked_times]
    
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
