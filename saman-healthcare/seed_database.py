#!/usr/bin/env python3
"""
Database Seed Script - Populate healthcare.db with demo data
Run this once to fill the database with sample patients, doctors, and appointments
"""

import requests
import json
from datetime import datetime, timedelta

API_URL = "http://127.0.0.1:8000/api"

# Demo patients
patients = [
    {
        "id": "P1001",
        "name": "Sanath Deo",
        "age": 45,
        "gender": "Male",
        "phone": "+91 98765 43210",
        "email": "sanath@example.com",
        "blood_group": "O+",
        "address": "123 Main St, City",
        "medical_history": "Hypertension,Diabetes Type 2"
    },
    {
        "id": "P1002",
        "name": "Priya Sharma",
        "age": 32,
        "gender": "Female",
        "phone": "+91 87654 32109",
        "email": "priya@example.com",
        "blood_group": "B+",
        "address": "456 Oak Ave, Town",
        "medical_history": "Asthma,Allergies"
    },
    {
        "id": "P1003",
        "name": "Rajesh Kumar",
        "age": 58,
        "gender": "Male",
        "phone": "+91 76543 21098",
        "email": "rajesh@example.com",
        "blood_group": "A+",
        "address": "789 Pine Rd, Village",
        "medical_history": "Heart Disease,High Cholesterol"
    },
    {
        "id": "P1004",
        "name": "Anjali Verma",
        "age": 28,
        "gender": "Female",
        "phone": "+91 65432 10987",
        "email": "anjali@example.com",
        "blood_group": "AB-",
        "address": "321 Elm St, City",
        "medical_history": "PCOD"
    },
    {
        "id": "P1005",
        "name": "Vikram Singh",
        "age": 52,
        "gender": "Male",
        "phone": "+91 54321 09876",
        "email": "vikram@example.com",
        "blood_group": "O-",
        "address": "654 Birch Ln, Town",
        "medical_history": "Arthritis,Migraine"
    }
]

# Demo doctors
doctors = [
    {
        "id": "D2001",
        "name": "Dr. Amelia Johnson",
        "specialization": "General Medicine",
        "phone": "+91 11111 11111",
        "email": "amelia@hospital.com",
        "qualification": "MBBS, MD",
        "experience_years": 15
    },
    {
        "id": "D2002",
        "name": "Dr. Ravi Patel",
        "specialization": "Cardiology",
        "phone": "+91 22222 22222",
        "email": "ravi@hospital.com",
        "qualification": "MBBS, DM",
        "experience_years": 12
    },
    {
        "id": "D2003",
        "name": "Dr. Sophia Lee",
        "specialization": "Pediatrics",
        "phone": "+91 33333 33333",
        "email": "sophia@hospital.com",
        "qualification": "MBBS, DCH",
        "experience_years": 10
    }
]

# Demo appointments (relative to today)
def get_appointments():
    today = datetime.now()
    return [
        {
            "id": "A001",
            "patient_id": "P1001",
            "doctor_id": "D2001",
            "appointment_date": today.strftime("%Y-%m-%d"),
            "appointment_time": "09:30",
            "status": "completed",
            "reason": "General Checkup"
        },
        {
            "id": "A002",
            "patient_id": "P1002",
            "doctor_id": "D2001",
            "appointment_date": today.strftime("%Y-%m-%d"),
            "appointment_time": "10:15",
            "status": "ongoing",
            "reason": "Follow-up"
        },
        {
            "id": "A003",
            "patient_id": "P1003",
            "doctor_id": "D2002",
            "appointment_date": today.strftime("%Y-%m-%d"),
            "appointment_time": "11:00",
            "status": "upcoming",
            "reason": "Heart Checkup"
        },
        {
            "id": "A004",
            "patient_id": "P1004",
            "doctor_id": "D2003",
            "appointment_date": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
            "appointment_time": "02:00",
            "status": "scheduled",
            "reason": "Routine Checkup"
        },
        {
            "id": "A005",
            "patient_id": "P1005",
            "doctor_id": "D2002",
            "appointment_date": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
            "appointment_time": "03:30",
            "status": "scheduled",
            "reason": "Cardiology Consultation"
        }
    ]

# Demo attendance
def get_attendance():
    today = datetime.now()
    return [
        {
            "id": "AT001",
            "doctor_id": "D2001",
            "patient_name": "Sanath Deo",
            "check_in_time": "09:25",
            "check_out_time": "09:45",
            "attendance_date": today.strftime("%Y-%m-%d"),
            "duration_minutes": 20
        },
        {
            "id": "AT002",
            "doctor_id": "D2001",
            "patient_name": "Priya Sharma",
            "check_in_time": "10:10",
            "check_out_time": None,
            "attendance_date": today.strftime("%Y-%m-%d"),
            "duration_minutes": 8
        },
        {
            "id": "AT003",
            "doctor_id": "D2002",
            "patient_name": "Rajesh Kumar",
            "check_in_time": None,
            "check_out_time": None,
            "attendance_date": today.strftime("%Y-%m-%d"),
            "duration_minutes": None
        }
    ]

def seed_data():
    """Add all demo data to the database"""
    total = 0
    
    print("🌱 Seeding healthcare database...")
    print("-" * 50)
    
    # Add patients
    print("📋 Adding patients...")
    for patient in patients:
        try:
            response = requests.post(
                f"{API_URL}/patients",
                json={"action": "add", **patient},
                timeout=5
            )
            if response.json().get("success"):
                print(f"  ✓ {patient['name']} ({patient['id']})")
                total += 1
            else:
                print(f"  ✗ Failed: {patient['name']}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print()
    
    # Add doctors
    print("👨‍⚕️  Adding doctors...")
    for doctor in doctors:
        try:
            response = requests.post(
                f"{API_URL}/doctors",
                json={"action": "add", **doctor},
                timeout=5
            )
            if response.json().get("success"):
                print(f"  ✓ {doctor['name']} ({doctor['id']})")
                total += 1
            else:
                print(f"  ✗ Failed: {doctor['name']}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print()
    
    # Add appointments
    print("📅 Adding appointments...")
    for appointment in get_appointments():
        try:
            response = requests.post(
                f"{API_URL}/appointments",
                json={"action": "add", **appointment},
                timeout=5
            )
            if response.json().get("success"):
                print(f"  ✓ {appointment['patient_id']} → {appointment['doctor_id']}")
                total += 1
            else:
                print(f"  ✗ Failed: {appointment['id']}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print()
    
    # Add attendance
    print("✓ Adding attendance records...")
    for record in get_attendance():
        try:
            response = requests.post(
                f"{API_URL}/attendance",
                json={"action": "add", **record},
                timeout=5
            )
            if response.json().get("success"):
                print(f"  ✓ {record['patient_name']} - {record['check_in_time']}")
                total += 1
            else:
                print(f"  ✗ Failed: {record['id']}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print()
    print("-" * 50)
    print(f"✅ Seeding complete! Added {total} records.")
    print()
    print("Dashboard URLs:")
    print("  • Lightweight: http://127.0.0.1:8000/doctor-dashboard.html")
    print("  • Detailed:    http://127.0.0.1:8000/doctor-details-dashboard.html")

if __name__ == "__main__":
    try:
        seed_data()
    except KeyboardInterrupt:
        print("\n\n❌ Seed cancelled by user.")
    except Exception as e:
        print(f"\n\n❌ Seed failed: {e}")
        print("\nMake sure the server is running: python3 app.py")
