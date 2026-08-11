-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- 1. Services Table
create table public.services (
    id uuid default uuid_generate_v4() primary key,
    name text not null,
    description text,
    duration_minutes integer not null default 30,
    price numeric(10, 2) not null default 0.00,
    is_active boolean not null default true,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 2. Clients Table
create table public.clients (
    id uuid default uuid_generate_v4() primary key,
    phone text not null unique,
    full_name text not null,
    email text,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 3. Bookings Table
create type booking_status as enum ('pending', 'confirmed', 'completed', 'cancelled');
create type booking_source as enum ('online', 'manual');

create table public.bookings (
    id uuid default uuid_generate_v4() primary key,
    client_id uuid references public.clients(id) not null,
    service_id uuid references public.services(id) not null,
    booking_date date not null,
    booking_time time not null,
    status booking_status default 'pending' not null,
    price_at_booking numeric(10, 2) not null,
    notes text,
    source booking_source default 'online' not null,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 4. Settings Table
create table public.settings (
    key text primary key,
    value jsonb not null,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Insert default settings
insert into public.settings (key, value) values 
('work_schedule', '{"start_time": "10:00", "end_time": "18:00", "slot_duration_minutes": 30, "off_days": [5, 6]}'), -- 5=Friday, 6=Saturday
('contact_info', '{"phone": "01000000000", "email": "info@lawyer.com", "address": "القاهرة، مصر"}');
