"""Healthcare Database Management with SQLite"""

import sqlite3
import json
import os
from datetime import datetime

DB_FILE = "healthcare.db"

def init_database():
    """Initialize database with all required tables"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Patients table
    c.execute('''CREATE TABLE IF NOT EXISTS patients (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        email TEXT,
        age INTEGER,
        gender TEXT,
        blood_group TEXT,
        address TEXT,
        medical_history TEXT,
        date_of_birth TEXT,
        aadhaar_last_4 TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    
    # Doctors table
    c.execute('''CREATE TABLE IF NOT EXISTS doctors (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        email TEXT,
        specialization TEXT,
        qualification TEXT,
        experience INTEGER,
        clinic_address TEXT,
        date_of_birth TEXT,
        aadhaar_last_4 TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    doctor_columns = [row[1] for row in c.execute("PRAGMA table_info(doctors)")]
    for column in ("doctor_type", "license_number", "department", "hospital"):
        if column not in doctor_columns:
            c.execute(f"ALTER TABLE doctors ADD COLUMN {column} TEXT")
    
    # Appointments table
    c.execute('''CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id TEXT,
        patient_id TEXT,
        appointment_date TEXT,
        appointment_time TEXT,
        status TEXT,
        notes TEXT,
        created_at TEXT,
        FOREIGN KEY(doctor_id) REFERENCES doctors(id),
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    )''')
    
    # Attendance table
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT,
        doctor_id TEXT,
        check_in_time TEXT,
        check_out_time TEXT,
        duration_minutes INTEGER,
        date TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(id),
        FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    )''')
    
    # Prescriptions table
    c.execute('''CREATE TABLE IF NOT EXISTS prescriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id TEXT,
        patient_id TEXT,
        medicine_name TEXT,
        dosage TEXT,
        frequency TEXT,
        duration TEXT,
        created_at TEXT,
        FOREIGN KEY(doctor_id) REFERENCES doctors(id),
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    )''')
    
    # Lab Reports table
    c.execute('''CREATE TABLE IF NOT EXISTS lab_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT,
        report_type TEXT,
        report_data TEXT,
        created_at TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    )''')

    # Referrals table
    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT,
        doctor_id TEXT,
        referred_to TEXT,
        reason TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(id),
        FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    )''')

    # Shared patient-doctor notification feed
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_id TEXT NOT NULL,
        sender_id TEXT,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )''')
    
    # Patient Accounts table (for login/authentication)
    c.execute('''CREATE TABLE IF NOT EXISTS patient_accounts (
        id TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        email TEXT,
        account_status TEXT DEFAULT 'active',
        created_at TEXT,
        last_login TEXT
    )''')
    
    # Doctor Accounts table (for login/authentication)
    c.execute('''CREATE TABLE IF NOT EXISTS doctor_accounts (
        id TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        email TEXT,
        account_status TEXT DEFAULT 'active',
        created_at TEXT,
        last_login TEXT
    )''')

    for table in ("patient_accounts", "doctor_accounts"):
        columns = [row[1] for row in c.execute(f"PRAGMA table_info({table})")]
        if "two_step_enabled" not in columns:
            c.execute(f"ALTER TABLE {table} ADD COLUMN two_step_enabled INTEGER DEFAULT 0")
        if "security_pin_hash" not in columns:
            c.execute(f"ALTER TABLE {table} ADD COLUMN security_pin_hash TEXT")

    for table, columns in {
        "patients": ("date_of_birth", "aadhaar_last_4"),
        "doctors": ("date_of_birth", "aadhaar_last_4"),
    }.items():
        existing = [row[1] for row in c.execute(f"PRAGMA table_info({table})")]
        for column in columns:
            if column not in existing:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    
    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_FILE}")

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def get_patients():
    """Get all patients"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM patients ORDER BY updated_at DESC LIMIT 100')
    patients = [dict(row) for row in c.fetchall()]
    conn.close()
    return patients

def get_patient(patient_id):
    """Get specific patient"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
    patient = dict(c.fetchone()) if c.fetchone() else None
    conn.close()
    return patient

def add_patient(patient_data):
    """Add new patient"""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    try:
        c.execute('''INSERT INTO patients 
                    (id, name, phone, email, age, gender, blood_group, address, medical_history, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (patient_data.get('id'), patient_data.get('name'), patient_data.get('phone'),
                  patient_data.get('email'), patient_data.get('age'), patient_data.get('gender'),
                  patient_data.get('blood_group'), patient_data.get('address'),
                  patient_data.get('medical_history'), now, now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False

def update_patient(patient_id, patient_data):
    """Update editable patient information."""
    conn = get_db()
    try:
        conn.execute('''UPDATE patients SET name = ?, phone = ?, email = ?, age = ?, gender = ?,
                        blood_group = ?, address = ?, medical_history = ?, updated_at = ? WHERE id = ?''',
                     (patient_data.get('name'), normalize_phone(patient_data.get('phone')),
                      patient_data.get('email'), patient_data.get('age'), patient_data.get('gender'),
                      patient_data.get('blood_group'), patient_data.get('address'),
                      patient_data.get('medical_history'), datetime.now().isoformat(), patient_id))
        conn.commit()
        changed = conn.total_changes > 0
        conn.close()
        return changed
    except Exception:
        conn.close()
        return False

def get_doctors():
    """Get all doctors"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM doctors ORDER BY updated_at DESC LIMIT 100')
    doctors = [dict(row) for row in c.fetchall()]
    conn.close()
    return doctors

def get_doctor(doctor_id):
    """Get specific doctor"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM doctors WHERE id = ?', (doctor_id,))
    doctor = dict(c.fetchone()) if c.fetchone() else None
    conn.close()
    return doctor

def get_appointments(filter_by=None, value=None):
    """Get appointments"""
    conn = get_db()
    c = conn.cursor()
    if filter_by and value:
        c.execute(f'SELECT * FROM appointments WHERE {filter_by} = ? ORDER BY appointment_date DESC LIMIT 100', (value,))
    else:
        c.execute('SELECT * FROM appointments ORDER BY appointment_date DESC LIMIT 100')
    appointments = [dict(row) for row in c.fetchall()]
    conn.close()
    return appointments

def add_appointment(appointment_data):
    """Add new appointment"""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    try:
        c.execute('''INSERT INTO appointments 
                    (doctor_id, patient_id, appointment_date, appointment_time, status, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (appointment_data.get('doctor_id'), appointment_data.get('patient_id'),
                  appointment_data.get('appointment_date'), appointment_data.get('appointment_time'),
                  appointment_data.get('status', 'scheduled'), appointment_data.get('notes'), now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False

def update_appointment_status(appointment_data):
    """Update an appointment status and return the updated appointment."""
    conn = get_db()
    try:
        if appointment_data.get("appointment_id"):
            cursor = conn.execute('UPDATE appointments SET status = ? WHERE id = ?',
                                  (appointment_data.get("status"), appointment_data.get("appointment_id")))
        else:
            cursor = conn.execute('''UPDATE appointments SET status = ?
                                    WHERE patient_id = ? AND doctor_id = ?''',
                                  (appointment_data.get("status"), appointment_data.get("patient_id"),
                                   appointment_data.get("doctor_id")))
        conn.commit()
        if cursor.rowcount == 0:
            conn.close()
            return None
        if appointment_data.get("appointment_id"):
            row = conn.execute('SELECT * FROM appointments WHERE id = ?', (appointment_data.get("appointment_id"),)).fetchone()
        else:
            row = conn.execute('''SELECT * FROM appointments WHERE patient_id = ? AND doctor_id = ?
                                  ORDER BY id DESC LIMIT 1''',
                               (appointment_data.get("patient_id"), appointment_data.get("doctor_id"))).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        conn.close()
        return None

def get_attendance(doctor_id=None, date=None):
    """Get attendance records"""
    conn = get_db()
    c = conn.cursor()
    if doctor_id and date:
        c.execute('''SELECT a.*, p.name as patient_name FROM attendance a 
                     JOIN patients p ON a.patient_id = p.id 
                     WHERE a.doctor_id = ? AND a.date = ? ORDER BY check_in_time DESC''', (doctor_id, date))
    else:
        c.execute('''SELECT a.*, p.name as patient_name FROM attendance a 
                     JOIN patients p ON a.patient_id = p.id ORDER BY a.date DESC LIMIT 100''')
    records = [dict(row) for row in c.fetchall()]
    conn.close()
    return records

def add_attendance(attendance_data):
    """Add attendance record"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO attendance 
                    (patient_id, doctor_id, check_in_time, check_out_time, duration_minutes, date)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (attendance_data.get('patient_id'), attendance_data.get('doctor_id'),
                  attendance_data.get('check_in_time'), attendance_data.get('check_out_time'),
                  attendance_data.get('duration_minutes'), attendance_data.get('date')))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False

def get_prescriptions(patient_id=None, doctor_id=None):
    """Get prescriptions"""
    conn = get_db()
    c = conn.cursor()
    if patient_id:
        c.execute('SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY created_at DESC', (patient_id,))
    elif doctor_id:
        c.execute('SELECT * FROM prescriptions WHERE doctor_id = ? ORDER BY created_at DESC', (doctor_id,))
    else:
        c.execute('SELECT * FROM prescriptions ORDER BY created_at DESC LIMIT 100')
    prescriptions = [dict(row) for row in c.fetchall()]
    conn.close()
    return prescriptions

def add_prescription(prescription_data):
    """Add prescription"""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    try:
        c.execute('''INSERT INTO prescriptions 
                    (doctor_id, patient_id, medicine_name, dosage, frequency, duration, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (prescription_data.get('doctor_id'), prescription_data.get('patient_id'),
                  prescription_data.get('medicine_name'), prescription_data.get('dosage'),
                  prescription_data.get('frequency'), prescription_data.get('duration'), now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False

def get_lab_reports(patient_id=None, doctor_id=None):
    """Get lab reports for a patient or doctor."""
    conn = get_db()
    c = conn.cursor()
    if patient_id:
        c.execute('SELECT * FROM lab_reports WHERE patient_id = ? ORDER BY created_at DESC', (patient_id,))
    else:
        c.execute('SELECT * FROM lab_reports ORDER BY created_at DESC LIMIT 100')
    reports = [dict(row) for row in c.fetchall()]
    conn.close()
    return reports

def add_lab_report(report_data):
    """Add a lab report."""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO lab_reports (patient_id, report_type, report_data, created_at)
                     VALUES (?, ?, ?, ?)''',
                  (report_data.get('patient_id'), report_data.get('report_type'),
                   report_data.get('report_data'), datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False

def get_referrals(patient_id=None, doctor_id=None):
    """Get referrals for a patient or doctor."""
    conn = get_db()
    c = conn.cursor()
    if patient_id:
        c.execute('SELECT * FROM referrals WHERE patient_id = ? ORDER BY created_at DESC', (patient_id,))
    elif doctor_id:
        c.execute('SELECT * FROM referrals WHERE doctor_id = ? ORDER BY created_at DESC', (doctor_id,))
    else:
        c.execute('SELECT * FROM referrals ORDER BY created_at DESC LIMIT 100')
    referrals = [dict(row) for row in c.fetchall()]
    conn.close()
    return referrals

def add_referral(referral_data):
    """Add a patient referral."""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO referrals (patient_id, doctor_id, referred_to, reason, status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (referral_data.get('patient_id'), referral_data.get('doctor_id'),
                   referral_data.get('referred_to'), referral_data.get('reason'),
                   referral_data.get('status', 'pending'), datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False

def add_notification(recipient_id, message, sender_id=None):
    """Add a notification for a patient or doctor account."""
    conn = get_db()
    try:
        conn.execute('''INSERT INTO notifications (recipient_id, sender_id, message, created_at)
                        VALUES (?, ?, ?, ?)''',
                     (recipient_id, sender_id, message, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False

def canonical_account_id(identifier):
    """Resolve an account ID from either an ID or registered phone number."""
    conn = get_db()
    normalized_phone = normalize_phone(identifier)
    row = conn.execute('''SELECT id FROM patient_accounts WHERE id = ? OR phone = ?
                          UNION ALL SELECT id FROM doctor_accounts WHERE id = ? OR phone = ?
                          LIMIT 1''', (identifier, normalized_phone, identifier, normalized_phone)).fetchone()
    conn.close()
    return row[0] if row else identifier

def get_notifications(recipient_id):
    """Get recent notifications and unread count for an account."""
    conn = get_db()
    recipient_id = canonical_account_id(recipient_id)
    rows = conn.execute('''SELECT * FROM notifications WHERE recipient_id = ?
                          ORDER BY created_at DESC LIMIT 50''', (recipient_id,)).fetchall()
    unread = conn.execute('''SELECT COUNT(*) FROM notifications
                             WHERE recipient_id = ? AND is_read = 0''', (recipient_id,)).fetchone()[0]
    conn.close()
    return [dict(row) for row in rows], unread

def mark_notifications_read(recipient_id):
    """Mark all notifications for an account as read."""
    recipient_id = canonical_account_id(recipient_id)
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE recipient_id = ?', (recipient_id,))
    conn.commit()
    conn.close()

def hash_password(password):
    """Hash password using SHA256"""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()

def normalize_phone(phone):
    """Normalize phone input so registration and login use the same value."""
    return ''.join(character for character in str(phone or '').strip() if character.isdigit() or character == '+')

def verify_password(password, password_hash):
    """Verify password against hash"""
    return hash_password(password) == password_hash

def register_patient(patient_id, name, phone, email, password, age=None, gender=None, blood_group=None,
                    security_pin=None, date_of_birth=None, aadhaar_last_4=None):
    """Register new patient account and create patient record"""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    try:
        phone = normalize_phone(phone)
        # Create account
        password_hash = hash_password(password)
        c.execute('''INSERT INTO patient_accounts (id, password_hash, phone, email, two_step_enabled,
                    security_pin_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (patient_id, password_hash, phone, email, 1, hash_password(security_pin), now))
        
        # Create patient record
        c.execute('''INSERT INTO patients (id, name, phone, email, age, gender, blood_group, date_of_birth,
                    aadhaar_last_4, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (patient_id, name, phone, email, age, gender, blood_group, date_of_birth,
                  (aadhaar_last_4[-4:] if aadhaar_last_4 and len(str(aadhaar_last_4)) >= 4 else aadhaar_last_4),
                  now, now))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False

def register_doctor(doctor_id, name, phone, email, password, specialization=None, qualification=None,
                    experience=None, security_pin=None, doctor_type=None, license_number=None,
                    department=None, hospital=None, date_of_birth=None, aadhaar_last_4=None):
    """Register new doctor account and create doctor record"""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    try:
        phone = normalize_phone(phone)
        # Create account
        password_hash = hash_password(password)
        c.execute('''INSERT INTO doctor_accounts (id, password_hash, phone, email, two_step_enabled,
                    security_pin_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (doctor_id, password_hash, phone, email, 1, hash_password(security_pin), now))
        
        # Create doctor record
        c.execute('''INSERT INTO doctors (id, name, phone, email, doctor_type, license_number, department,
                specialization, qualification, experience, hospital, date_of_birth, aadhaar_last_4, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
             (doctor_id, name, phone, email, doctor_type, license_number, department,
              specialization, qualification, experience, hospital, date_of_birth,
              (aadhaar_last_4[-4:] if aadhaar_last_4 and len(str(aadhaar_last_4)) >= 4 else aadhaar_last_4),
              now, now))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False

def verify_account_identity(role, identifier, date_of_birth, aadhaar_last_4):
    """Check DOB and Aadhaar last-4 digits before allowing a password or PIN reset."""
    profile_table = "patients" if role == "patient" else "doctors"
    account_table = _account_table(role)
    if not date_of_birth or not aadhaar_last_4:
        return False

    normalized_dob = str(date_of_birth).strip()
    normalized_last4 = str(aadhaar_last_4).strip()[-4:]
    if not normalized_dob or len(normalized_last4) != 4 or not normalized_last4.isdigit():
        return False

    conn = get_db()
    row = conn.execute(f'''SELECT p.date_of_birth, p.aadhaar_last_4 FROM {account_table} a
                           JOIN {profile_table} p ON p.id = a.id
                           WHERE a.id = ? OR a.phone = ?''',
                       (identifier, normalize_phone(identifier))).fetchone()
    conn.close()
    if not row:
        return False

    saved_dob = str(row["date_of_birth"] or "").strip()
    saved_last4 = str(row["aadhaar_last_4"] or "").strip()[-4:]
    return saved_dob == normalized_dob and saved_last4 == normalized_last4


def reset_account_credentials(role, identifier, new_password, new_pin=None):
    """Update a password and optionally a login PIN after successful recovery verification."""
    if len(str(new_password)) < 8:
        return False

    table = _account_table(role)
    conn = get_db()
    account = conn.execute(f"SELECT id FROM {table} WHERE id = ? OR phone = ?",
                           (identifier, normalize_phone(identifier))).fetchone()
    if not account:
        conn.close()
        return False

    if new_pin is not None:
        new_pin = str(new_pin).strip()
        if not new_pin.isdigit() or len(new_pin) != 4:
            conn.close()
            return False

    try:
        if new_pin is not None:
            conn.execute(f"UPDATE {table} SET password_hash = ?, security_pin_hash = ? WHERE id = ? OR phone = ?",
                         (hash_password(new_password), hash_password(new_pin), identifier, normalize_phone(identifier)))
        else:
            conn.execute(f"UPDATE {table} SET password_hash = ? WHERE id = ? OR phone = ?",
                         (hash_password(new_password), identifier, normalize_phone(identifier)))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def authenticate_patient(identifier, password):
    """Authenticate patient by ID or phone and password. Returns patient dict or None."""
    conn = get_db()
    c = conn.cursor()
    try:
        # Search by patient ID or normalized phone
        phone_identifier = normalize_phone(identifier)
        c.execute('''SELECT a.id, a.phone, a.email, a.password_hash FROM patient_accounts a
                WHERE a.id = ? OR a.phone = ?''', (identifier, phone_identifier))
        account = c.fetchone()
        conn.close()
        
        if account and verify_password(password, account['password_hash']):
            return {'id': account['id'], 'phone': account['phone'], 'email': account['email']}
        return None
    except Exception as e:
        conn.close()
        return None

def authenticate_doctor(identifier, password):
    """Authenticate doctor by ID or phone and password. Returns doctor dict or None."""
    conn = get_db()
    c = conn.cursor()
    try:
        # Search by doctor ID or normalized phone
        phone_identifier = normalize_phone(identifier)
        c.execute('''SELECT a.id, a.phone, a.email, a.password_hash FROM doctor_accounts a
                WHERE a.id = ? OR a.phone = ?''', (identifier, phone_identifier))
        account = c.fetchone()
        conn.close()
        
        if account and verify_password(password, account['password_hash']):
            return {'id': account['id'], 'phone': account['phone'], 'email': account['email']}
        return None
    except Exception as e:
        conn.close()
        return None

def patient_exists(patient_id):
    """Check if patient ID exists"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT 1 FROM patient_accounts WHERE id = ?', (patient_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def doctor_exists(doctor_id):
    """Check if doctor ID exists"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT 1 FROM doctor_accounts WHERE id = ?', (doctor_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def phone_exists_patient(phone):
    """Check if phone number exists in either account table."""
    conn = get_db()
    c = conn.cursor()
    normalized_phone = normalize_phone(phone)
    c.execute('''SELECT 1 FROM patient_accounts WHERE phone = ?
                 UNION ALL SELECT 1 FROM doctor_accounts WHERE phone = ?''',
              (normalized_phone, normalized_phone))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def phone_exists_doctor(phone):
    """Check if phone number exists in either account table."""
    return phone_exists_patient(phone)

def _account_table(role):
    return "patient_accounts" if role == "patient" else "doctor_accounts"

def get_profile(role, identifier):
    """Get the profile and account settings for a patient or doctor."""
    table = _account_table(role)
    profile_table = "patients" if role == "patient" else "doctors"
    conn = get_db()
    c = conn.cursor()
    normalized_identifier = normalize_phone(identifier)
    c.execute(f'''SELECT a.id, a.phone, a.email, a.two_step_enabled, p.*
                  FROM {table} a JOIN {profile_table} p ON p.id = a.id
                  WHERE a.id = ? OR a.phone = ?''', (identifier, normalized_identifier))
    row = c.fetchone()
    profile = dict(row) if row else None
    conn.close()
    return profile

def update_profile(role, account_id, profile_data):
    """Update editable profile fields while preserving the account ID."""
    table = _account_table(role)
    profile_table = "patients" if role == "patient" else "doctors"
    now = datetime.now().isoformat()
    conn = get_db()
    c = conn.cursor()
    try:
        phone = normalize_phone(profile_data.get("phone", ""))
        duplicate = c.execute(f"SELECT 1 FROM {table} WHERE phone = ? AND id != ?", (phone, account_id)).fetchone()
        other_table = "doctor_accounts" if table == "patient_accounts" else "patient_accounts"
        duplicate = duplicate or c.execute(f"SELECT 1 FROM {other_table} WHERE phone = ?", (phone,)).fetchone()
        if duplicate:
            conn.close()
            return False
        email = profile_data.get("email")
        name = profile_data.get("name")
        if role == "patient":
            c.execute(f'''UPDATE {profile_table} SET name = ?, phone = ?, email = ?, age = ?,
                         gender = ?, blood_group = ?, address = ?, date_of_birth = ?, aadhaar_last_4 = ?, updated_at = ? WHERE id = ?''',
                      (name, phone, email, profile_data.get("age"), profile_data.get("gender"),
                       profile_data.get("blood_group"), profile_data.get("address"),
                       profile_data.get("date_of_birth"), profile_data.get("aadhaar_last_4"), now, account_id))
        else:
                c.execute(f'''UPDATE {profile_table} SET name = ?, phone = ?, email = ?, doctor_type = ?,
                                 license_number = ?, department = ?, specialization = ?, qualification = ?, experience = ?,
                                 hospital = ?, clinic_address = ?, date_of_birth = ?, aadhaar_last_4 = ?, updated_at = ? WHERE id = ?''',
                             (name, phone, email, profile_data.get("doctor_type"), profile_data.get("license_number"),
                              profile_data.get("department"), profile_data.get("specialization"), profile_data.get("qualification"),
                              profile_data.get("experience"), profile_data.get("hospital"), profile_data.get("clinic_address"),
                              profile_data.get("date_of_birth"), profile_data.get("aadhaar_last_4"), now, account_id))
        c.execute(f"UPDATE {table} SET phone = ?, email = ? WHERE id = ?", (phone, email, account_id))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False

def get_two_step_enabled(role, identifier):
    """Return the saved two-step preference for an account."""
    table = _account_table(role)
    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT two_step_enabled FROM {table} WHERE id = ? OR phone = ?",
              (identifier, normalize_phone(identifier)))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0])

def set_two_step_enabled(role, identifier, enabled):
    """Save the two-step preference for an account."""
    table = _account_table(role)
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(f"UPDATE {table} SET two_step_enabled = ? WHERE id = ? OR phone = ?",
                  (1 if enabled else 0, identifier, normalize_phone(identifier)))
        conn.commit()
        changed = c.rowcount > 0
        conn.close()
        return changed
    except Exception:
        conn.close()
        return False

def set_security_pin(role, identifier, pin):
    """Store a hashed security PIN and enable PIN verification."""
    table = _account_table(role)
    conn = get_db()
    try:
        conn.execute(f"UPDATE {table} SET security_pin_hash = ?, two_step_enabled = 1 WHERE id = ? OR phone = ?",
                     (hash_password(pin), identifier, normalize_phone(identifier)))
        conn.commit()
        changed = conn.total_changes > 0
        conn.close()
        return changed
    except Exception:
        conn.close()
        return False

def verify_security_pin(role, identifier, pin):
    """Verify a security PIN for an account."""
    table = _account_table(role)
    conn = get_db()
    row = conn.execute(f"SELECT security_pin_hash FROM {table} WHERE id = ? OR phone = ?",
                       (identifier, normalize_phone(identifier))).fetchone()
    conn.close()
    return bool(row and row[0] and verify_password(pin, row[0]))

def change_account_password(role, identifier, current_password, new_password):
    """Change a password after verifying the current password."""
    table = _account_table(role)
    conn = get_db()
    try:
        row = conn.execute(f"SELECT password_hash FROM {table} WHERE id = ? OR phone = ?",
                           (identifier, normalize_phone(identifier))).fetchone()
        if not row or not verify_password(current_password, row[0]):
            conn.close()
            return False
        conn.execute(f"UPDATE {table} SET password_hash = ? WHERE id = ? OR phone = ?",
                     (hash_password(new_password), identifier, normalize_phone(identifier)))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False

def account_id_exists(account_id):
    """Check whether an ID is already used by any account or profile."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT 1 FROM patient_accounts WHERE id = ?
                 UNION ALL SELECT 1 FROM doctor_accounts WHERE id = ?
                 UNION ALL SELECT 1 FROM patients WHERE id = ?
                 UNION ALL SELECT 1 FROM doctors WHERE id = ?''',
              (account_id, account_id, account_id, account_id))
    exists = c.fetchone() is not None
    conn.close()
    return exists

if __name__ == "__main__":
    init_database()
