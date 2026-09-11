"""Simple backend for the Saman Healthcare demo login page with SQLite database."""

# Import Python's built-in modules so the demo does not need external packages.
import base64
import hashlib
import hmac
import json
import os
import platform
import secrets
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Import database module
from database import (
    init_database, get_patients, get_patient, add_patient, update_patient, get_doctors,
    get_doctor, get_appointments, add_appointment, update_appointment_status, get_attendance, add_attendance,
    get_prescriptions, add_prescription, authenticate_patient, authenticate_doctor,
    get_lab_reports, add_lab_report, get_referrals, add_referral,
    add_notification, get_notifications, mark_notifications_read,
    register_patient, register_doctor, patient_exists, doctor_exists,
    phone_exists_patient, phone_exists_doctor, account_id_exists, normalize_phone,
    get_profile, update_profile, get_two_step_enabled, set_two_step_enabled,
    set_security_pin, verify_security_pin, change_account_password,
    verify_account_identity, reset_account_credentials
)


def load_local_environment():
    """Load simple KEY=value settings from a local .env file without extra packages."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_environment()


# Store demo accounts in memory for this local prototype only.
DEMO_USERS = {
    "patient": {
        "patient_id": "P1001",
        "phone": "+923001234567",
        "password": "patient123",
    },
    "doctor": {
        "doctor_id": "D2001",
        "phone": "+923009876543",
        "password": "doctor123",
    },
}

# Keep temporary OTP challenges in memory for this local prototype only.
# Keep password-reset OTP challenges separate from login OTP challenges.
RESET_CHALLENGES = {}

# Keep verified reset tokens separate from OTP challenges.
RESET_TOKENS = {}

# Keep temporary two-step setup challenges in memory for five minutes.
SECURITY_CHALLENGES = {}

# Keep newly registered demo accounts grouped by account type in memory.
REGISTERED_USERS = {"patient": [], "doctor": []}

# Track failed login attempts per user to trigger the human verification challenge.
FAILED_LOGIN_ATTEMPTS = {}

# Keep OTP codes valid for five minutes.
OTP_LIFETIME_SECONDS = 300


def tee_runtime_info():
    """Return platform and Trusted Execution Environment capability metadata."""
    system_name = platform.system().lower()
    platform_map = {
        "windows": "windows",
        "darwin": "mac",
        "linux": "linux",
        "android": "android",
        "ios": "ios",
    }
    runtime_platform = platform_map.get(system_name, system_name or "unknown")
    device_class = "mobile" if runtime_platform in {"android", "ios"} else "desktop"
    tee_supported = runtime_platform in {"windows", "mac", "android", "ios", "linux"}
    return {
        "platform": runtime_platform,
        "device_class": device_class,
        "trusted_execution_environment": {
            "supported": tee_supported,
            "enabled": tee_supported,
            "name": "TEE" if tee_supported else "Unsupported",
            "status": "available" if tee_supported else "not_available",
        },
    }


def failed_attempt_key(role, identifier):
    """Normalize the account identifier used for failed-login tracking."""
    return f"{role}:{str(identifier).strip().lower()}"


def clear_failed_attempts(role, identifier):
    """Reset the failed-login counter after a successful login or verification."""
    FAILED_LOGIN_ATTEMPTS.pop(failed_attempt_key(role, identifier), None)


def record_failed_attempt(role, identifier):
    """Increase the failed-login counter and return the new count."""
    key = failed_attempt_key(role, identifier)
    attempts = FAILED_LOGIN_ATTEMPTS.get(key, 0) + 1
    FAILED_LOGIN_ATTEMPTS[key] = attempts
    return attempts


class HealthcareRequestHandler(SimpleHTTPRequestHandler):
    """Serve the frontend files and handle login API requests."""

    def do_OPTIONS(self):
        """Allow browser preflight requests from locally opened frontend files."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """Return a small health response or serve a frontend file."""
        # Use this endpoint to quickly check whether the backend is running.
        if self.path == "/api/health":
            health_payload = {
                "status": "ok",
                "message": "Backend is running.",
                **tee_runtime_info(),
            }
            self.send_json(200, health_payload)
            return

        # Keep the existing HTML and CSS files available from this same server.
        super().do_GET()

    def do_POST(self):
        """Route login and OTP verification requests."""
        # Reject unknown API paths instead of treating them as authentication requests.
        valid_paths = {
            "/api/login",
            "/api/register",
            "/api/send-login-details",
            "/api/forgot-password/request",
            "/api/forgot-password/verify",
            "/api/forgot-password/reset",
            "/api/patients",
            "/api/doctors",
            "/api/appointments",
            "/api/attendance",
            "/api/prescriptions",
            "/api/lab-reports",
            "/api/referrals",
            "/api/profile",
            "/api/security",
            "/api/security/set-pin",
            "/api/verify-pin",
            "/api/verify-password",
            "/api/human-verify",
            "/api/account-password",
            "/api/notifications",
        }
        if self.path not in valid_paths:
            self.send_json(404, {"message": "Endpoint not found."})
            return

        # Parse the shared JSON request body before handling either endpoint.
        request_data = self.read_json_body()
        if request_data is None:
            return

        # Send a new OTP challenge when the login form requests two-step verification.
        if self.path == "/api/login":
            self.handle_login(request_data)
            return

        # Create a new Patient or Doctor account from the registration form.
        if self.path == "/api/register":
            self.handle_registration(request_data)
            return

        # Send the newly created account identifier to its verified phone number.
        if self.path == "/api/send-login-details":
            self.handle_send_login_details(request_data)
            return

        # Start the password-reset OTP flow.
        if self.path == "/api/forgot-password/request":
            self.handle_password_reset_request(request_data)
            return

        # Verify the reset OTP before opening the new-password page.
        if self.path == "/api/forgot-password/verify":
            self.handle_password_reset_verification(request_data)
            return

        # Change the password only after the reset OTP is verified.
        if self.path == "/api/forgot-password/reset":
            self.handle_password_reset(request_data)
            return

        # Handle database API endpoints for patients, doctors, appointments, etc.
        if self.path == "/api/patients":
            self.handle_patients(request_data)
            return
        if self.path == "/api/doctors":
            self.handle_doctors(request_data)
            return
        if self.path == "/api/appointments":
            self.handle_appointments(request_data)
            return
        if self.path == "/api/attendance":
            self.handle_attendance_api(request_data)
            return
        if self.path == "/api/prescriptions":
            self.handle_prescriptions_api(request_data)
            return
        if self.path == "/api/lab-reports":
            self.handle_lab_reports_api(request_data)
            return
        if self.path == "/api/referrals":
            self.handle_referrals_api(request_data)
            return
        if self.path == "/api/profile":
            self.handle_profile_api(request_data)
            return
        if self.path == "/api/security":
            self.handle_security_api(request_data)
            return
        if self.path == "/api/security/set-pin":
            self.handle_security_pin(request_data)
            return
        if self.path == "/api/verify-pin":
            self.handle_pin_verification(request_data)
            return
        if self.path == "/api/verify-password":
            self.handle_password_verification(request_data)
            return
        if self.path == "/api/human-verify":
            self.handle_human_verification(request_data)
            return
        if self.path == "/api/account-password":
            self.handle_account_password(request_data)
            return
        if self.path == "/api/notifications":
            self.handle_notifications_api(request_data)
            return


    def read_json_body(self):
        """Read and decode one JSON request body."""
        # Read only the number of bytes declared by the client.
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            request_body = self.rfile.read(content_length)
            return json.loads(request_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"message": "Please send valid JSON."})
            return None

    def handle_login(self, login_data):
        """Validate a password or security PIN login credential."""
        # Pull the fields sent by the login form.
        role = login_data.get("role", "").lower()
        identifier = login_data.get("identifier", "").strip()
        pin = login_data.get("password", "")

        # Validate the basic request shape before checking account details.
        if role not in ["patient", "doctor"] or not identifier or not pin:
            self.send_json(400, {"message": "Role, login ID, and security PIN are required."})
            return

        # The security PIN is always the first login credential.
        if not verify_security_pin(role, identifier, pin):
            failed_count = record_failed_attempt(role, identifier)
            if failed_count >= 2:
                self.send_json(403, {
                    "message": "Too many failed attempts. Human verification is required.",
                    "requires_human_verification": True,
                    "role": role,
                    "failed_attempts": failed_count,
                })
            else:
                self.send_json(401, {
                    "message": "The security PIN is not correct.",
                    "failed_attempts": failed_count,
                })
            return

        clear_failed_attempts(role, identifier)
        two_step_enabled = get_two_step_enabled(role, identifier)
        if two_step_enabled:
            self.send_json(202, {
                "message": "PIN verified. Enter your password to continue.",
                "requires_password": True,
                "role": role,
            })
            return

        self.send_json(200, {"message": "Login successful.", "role": role})
        return

    def handle_password_verification(self, data):
        """Verify the password after a security PIN has been accepted."""
        role = data.get("role", "").lower()
        identifier = data.get("identifier", "").strip()
        password = data.get("password", "")
        account = authenticate_patient(identifier, password) if role == "patient" else authenticate_doctor(identifier, password)
        if account:
            clear_failed_attempts(role, identifier)
            self.send_json(200, {"message": "Password verified. Login successful.", "role": role})
            return

        failed_count = record_failed_attempt(role, identifier)
        if failed_count >= 2:
            self.send_json(403, {
                "message": "Too many failed attempts. Human verification is required.",
                "requires_human_verification": True,
                "role": role,
                "failed_attempts": failed_count,
            })
            return

        self.send_json(401, {"message": "The password is not correct.", "failed_attempts": failed_count})

    def handle_human_verification(self, data):
        """Allow the user to reset failed-login tracking after a human verification challenge."""
        role = data.get("role", "").lower()
        identifier = data.get("identifier", "").strip()
        if role not in ["patient", "doctor"] or not identifier:
            self.send_json(400, {"message": "Role and identifier are required."})
            return

        clear_failed_attempts(role, identifier)
        self.send_json(200, {"message": "Human verification passed. You can try again.", "role": role})

    def handle_registration(self, registration_data):
        """Validate and register a new account in the database."""
        # Read the common account fields sent by both registration modes.
        role = registration_data.get("role", "").lower()
        phone = normalize_phone(registration_data.get("phone", ""))
        password = registration_data.get("password", "")
        security_pin = str(registration_data.get("security_pin", "")).strip()

        # Reject incomplete registrations before creating an account.
        date_of_birth = registration_data.get("date_of_birth", "").strip()
        aadhaar_last_4 = str(registration_data.get("aadhaar_last_4", "")).strip()

        if role not in ["patient", "doctor"] or not phone or not password or len(password) < 8 or not security_pin.isdigit() or len(security_pin) != 4:
            self.send_json(400, {"message": "Account type, phone, password (min 8 chars), and matching 4-digit PIN are required."})
            return
        if not date_of_birth or len(aadhaar_last_4) != 4 or not aadhaar_last_4.isdigit():
            self.send_json(400, {"message": "Date of birth and the last 4 digits of Aadhaar are required."})
            return

        # Prevent accounts from using duplicate phone numbers
        if phone_exists_patient(phone):
            self.send_json(409, {"message": "An account with this phone number already exists."})
            return

        # Generate an ID that is checked against both patient and doctor accounts.
        account_prefix = "D" if role == "doctor" else "P"
        account_id = None
        for _ in range(20):
            candidate_id = f"{account_prefix}{secrets.randbelow(90_000_000) + 10_000_000}"
            if not account_id_exists(candidate_id):
                account_id = candidate_id
                break

        if not account_id:
            self.send_json(503, {"message": "Could not create a unique account ID. Please try again."})
            return

        # Get role-specific fields
        if role == "patient":
            name = registration_data.get("name", "Patient").strip()
            email = registration_data.get("email", "").strip() or None
            age = registration_data.get("age")
            gender = registration_data.get("gender")
            blood_group = registration_data.get("blood_group")
            
            # Register in database
            success = register_patient(account_id, name, phone, email, password, age, gender, blood_group,
                                      security_pin, date_of_birth, aadhaar_last_4)
        else:  # doctor
            name = registration_data.get("name", "Doctor").strip()
            email = registration_data.get("email", "").strip() or None
            specialization = registration_data.get("specialization")
            qualification = registration_data.get("qualification")
            experience = registration_data.get("experience")
            doctor_type = registration_data.get("doctor_type")
            license_number = registration_data.get("license_number")
            department = registration_data.get("department")
            hospital = registration_data.get("hospital")
            
            # Register in database
            success = register_doctor(account_id, name, phone, email, password, specialization, qualification,
                                      experience, security_pin, doctor_type, license_number, department,
                                      hospital, date_of_birth, aadhaar_last_4)

        if not success:
            self.send_json(409, {"message": "The account details are already in use. Please try again."})
            return

        # Return the generated ID so the user can use it later if needed.
        self.send_json(201, {
            "message": "Registration successful.",
            "role": role,
            "account_id": account_id,
            "phone": phone,
        })

    def handle_send_login_details(self, login_data):
        """Send a new account's non-sensitive login identifiers through WhatsApp."""
        role = login_data.get("role", "").lower()
        account_id = login_data.get("account_id", "").strip()
        phone = normalize_phone(login_data.get("phone", ""))

        if role not in ["patient", "doctor"] or not account_id or not phone:
            self.send_json(400, {"message": "Role, account ID, and phone number are required."})
            return

        account = self.find_account(role, account_id)
        if not account or account.get("phone") != phone:
            self.send_json(404, {"message": "The account details could not be verified."})
            return

        delivery_result = send_whatsapp_login_details(phone, role, account_id)
        self.send_json(200 if delivery_result["sent"] else 502, {
            "message": delivery_result["message"],
            "whatsapp_url": delivery_result.get("whatsapp_url"),
        })

    def find_account(self, role, identifier):
        """Find an account by phone or account ID (from database or demo)."""
        if role == "patient":
            account = authenticate_patient(identifier, "")  # This won't work without password, so use different approach
            # Try to get from database by ID or phone
            from database import get_db
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT id, phone, email FROM patient_accounts WHERE id = ? OR phone = ?', (identifier, normalize_phone(identifier)))
            result = c.fetchone()
            conn.close()
            if result:
                return {'patient_id': result['id'], 'phone': result['phone'], 'email': result['email']}
        else:  # doctor
            from database import get_db
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT id, phone, email FROM doctor_accounts WHERE id = ? OR phone = ?', (identifier, normalize_phone(identifier)))
            result = c.fetchone()
            conn.close()
            if result:
                return {'doctor_id': result['id'], 'phone': result['phone'], 'email': result['email']}
        
        # Fallback to demo account
        demo_account = DEMO_USERS.get(role, {})
        if identifier in {demo_account.get("patient_id"), demo_account.get("doctor_id")} or normalize_phone(identifier) == normalize_phone(demo_account.get("phone")):
            return demo_account
        
        return None

    def handle_password_reset_request(self, reset_data):
        """Verify DOB and Aadhaar identity, then issue a time-limited password reset token."""
        role = reset_data.get("role", "").lower()
        identifier = reset_data.get("identifier", "").strip()
        date_of_birth = reset_data.get("date_of_birth", "").strip()
        aadhaar_last_4 = str(reset_data.get("aadhaar_last_4", "")).strip()

        if role not in ["patient", "doctor"] or not identifier or not date_of_birth or len(aadhaar_last_4) != 4 or not aadhaar_last_4.isdigit():
            self.send_json(400, {"message": "Please provide your role, identifier, date of birth, and Aadhaar last 4 digits."})
            return

        account = self.find_account(role, identifier)
        if not account:
            self.send_json(401, {"message": "We could not find that account."})
            return

        if not verify_account_identity(role, identifier, date_of_birth, aadhaar_last_4):
            self.send_json(401, {"message": "The date of birth or Aadhaar last 4 digits do not match your account."})
            return

        account_id = account.get("patient_id") or account.get("doctor_id") or account.get("id") or identifier
        account["id"] = account_id
        reset_token = secrets.token_urlsafe(24)
        RESET_TOKENS[reset_token] = {
            "role": role,
            "account": account,
            "expires_at": time.time() + OTP_LIFETIME_SECONDS,
        }
        self.send_json(200, {
            "message": "Identity verified. Please set your new login PIN and password.",
            "reset_token": reset_token,
        })

    def handle_password_reset(self, reset_data):
        """Update the account password and security PIN with a verified reset token."""
        reset_token = reset_data.get("reset_token", "")
        new_password = reset_data.get("new_password", "")
        new_pin = str(reset_data.get("new_pin", "")).strip()
        token_data = RESET_TOKENS.get(reset_token)

        if not token_data or time.time() > token_data["expires_at"]:
            RESET_TOKENS.pop(reset_token, None)
            self.send_json(401, {"message": "This password reset session has expired."})
            return
        if not new_password or len(new_password) < 8:
            self.send_json(400, {"message": "Password must be at least 8 characters."})
            return
        if not new_pin.isdigit() or len(new_pin) != 4:
            self.send_json(400, {"message": "New login PIN must contain exactly 4 digits."})
            return

        account = token_data["account"]
        account_id = account.get("id") or account.get("patient_id") or account.get("doctor_id") or account.get("phone")
        if not account_id:
            RESET_TOKENS.pop(reset_token, None)
            self.send_json(400, {"message": "The account could not be identified for password recovery."})
            return

        success = reset_account_credentials(token_data["role"], account_id, new_password, new_pin)
        RESET_TOKENS.pop(reset_token, None)
        if not success:
            self.send_json(400, {"message": "The account could not be updated. Please try again."})
            return

        self.send_json(200, {"message": "Password and login PIN changed successfully."})

    def handle_password_reset_verification(self, verification_data):
        """Verify the reset OTP and issue a short-lived reset token."""
        # Read the challenge identifier and code entered on the OTP step.
        challenge_id = verification_data.get("challenge_id", "")
        otp_code = verification_data.get("otp", "")
        challenge = RESET_CHALLENGES.get(challenge_id)

        # Reject invalid or expired OTP challenges.
        if not challenge or time.time() > challenge["expires_at"]:
            RESET_CHALLENGES.pop(challenge_id, None)
            self.send_json(401, {"message": "This reset code has expired."})
            return

        # Compare the submitted OTP with the stored hash.
        if not hmac.compare_digest(challenge["otp_hash"], self.hash_otp(otp_code)):
            self.send_json(401, {"message": "The OTP is not correct."})
            return

        # Create a separate token so the password page cannot skip OTP verification.
        reset_token = secrets.token_urlsafe(24)
        RESET_TOKENS[reset_token] = {
            "account": challenge["account"],
            "expires_at": time.time() + OTP_LIFETIME_SECONDS,
        }
        RESET_CHALLENGES.pop(challenge_id, None)
        self.send_json(200, {"message": "OTP verified.", "reset_token": reset_token})

    @staticmethod
    def hash_otp(otp_code):
        """Create a stable hash for comparing a temporary OTP."""
        # Hashing prevents the in-memory store from holding raw OTP values.
        return hashlib.sha256(otp_code.encode("utf-8")).hexdigest()

    def handle_patients(self, data):
        """Handle patient database operations"""
        action = data.get("action")
        try:
            if action == "get_all":
                patients = get_patients()
                self.send_json(200, {"patients": patients})
            elif action == "get":
                patient = get_patient(data.get("patient_id"))
                self.send_json(200 if patient else 404, {"patient": patient})
            elif action == "add":
                success = add_patient(data)
                self.send_json(201 if success else 400, {"success": success})
            elif action == "update":
                patient_id = data.get("patient_id") or data.get("id")
                success = update_patient(patient_id, data)
                self.send_json(200 if success else 404, {"success": success})
            else:
                self.send_json(400, {"message": "Invalid action"})
        except Exception as e:
            self.send_json(500, {"message": str(e)})

    def handle_doctors(self, data):
        """Handle doctor database operations"""
        action = data.get("action")
        try:
            if action == "get_all":
                doctors = get_doctors()
                self.send_json(200, {"doctors": doctors})
            elif action == "get":
                doctor = get_doctor(data.get("doctor_id"))
                self.send_json(200 if doctor else 404, {"doctor": doctor})
            else:
                self.send_json(400, {"message": "Invalid action"})
        except Exception as e:
            self.send_json(500, {"message": str(e)})

    def handle_appointments(self, data):
        """Handle appointment database operations"""
        action = data.get("action")
        try:
            if action == "get_all":
                appointments = get_appointments()
                self.send_json(200, {"appointments": appointments})
            elif action == "get":
                filter_by = data.get("filter_by")
                filter_value = data.get("filter_value")
                appointments = get_appointments(filter_by, filter_value)
                self.send_json(200, {"appointments": appointments})
            elif action == "add":
                success = add_appointment(data)
                if success and data.get("patient_id") and data.get("doctor_id"):
                    add_notification(data["doctor_id"], f"New appointment request from patient {data['patient_id']}.", data["patient_id"])
                    add_notification(data["patient_id"], f"Appointment request sent to doctor {data['doctor_id']}.", data["doctor_id"])
                self.send_json(201 if success else 400, {"success": success})
            elif action == "update_status":
                appointment = update_appointment_status(data)
                if not appointment:
                    self.send_json(404, {"message": "Appointment not found."})
                    return
                if data.get("status") == "completed" and appointment.get("patient_id"):
                    add_notification(appointment["patient_id"], "Your visit has been marked completed.", appointment.get("doctor_id"))
                self.send_json(200, {"appointment": appointment})
            else:
                self.send_json(400, {"message": "Invalid action"})
        except Exception as e:
            self.send_json(500, {"message": str(e)})

    def handle_attendance_api(self, data):
        """Handle attendance database operations"""
        action = data.get("action")
        try:
            if action == "get_all":
                attendance = get_attendance()
                self.send_json(200, {"attendance": attendance})
            elif action == "get":
                doctor_id = data.get("doctor_id")
                date = data.get("date")
                attendance = get_attendance(doctor_id, date)
                self.send_json(200, {"attendance": attendance})
            elif action == "add":
                success = add_attendance(data)
                self.send_json(201 if success else 400, {"success": success})
            else:
                self.send_json(400, {"message": "Invalid action"})
        except Exception as e:
            self.send_json(500, {"message": str(e)})

    def handle_prescriptions_api(self, data):
        """Handle prescription database operations"""
        action = data.get("action")
        try:
            if action == "get_all":
                prescriptions = get_prescriptions()
                self.send_json(200, {"prescriptions": prescriptions})
            elif action == "get":
                patient_id = data.get("patient_id")
                doctor_id = data.get("doctor_id")
                prescriptions = get_prescriptions(patient_id, doctor_id)
                self.send_json(200, {"prescriptions": prescriptions})
            elif action == "add":
                success = add_prescription(data)
                if success and data.get("patient_id"):
                    add_notification(data["patient_id"], f"New prescription added: {data.get('medicine_name', 'Medication')}.", data.get("doctor_id"))
                self.send_json(201 if success else 400, {"success": success})
            else:
                self.send_json(400, {"message": "Invalid action"})
        except Exception as e:
            self.send_json(500, {"message": str(e)})

    def handle_lab_reports_api(self, data):
        """Handle lab report database operations."""
        action = data.get("action")
        if action == "get":
            self.send_json(200, {"reports": get_lab_reports(data.get("patient_id"), data.get("doctor_id"))})
        elif action == "get_all":
            self.send_json(200, {"reports": get_lab_reports()})
        elif action == "add":
            success = add_lab_report(data)
            if success and data.get("patient_id"):
                add_notification(data["patient_id"], f"New lab report available: {data.get('report_type', 'Report')}.", data.get("doctor_id"))
            self.send_json(201 if success else 400, {"success": success})
        else:
            self.send_json(400, {"message": "Invalid action"})

    def handle_referrals_api(self, data):
        """Handle referral database operations."""
        action = data.get("action")
        if action == "get":
            self.send_json(200, {"referrals": get_referrals(data.get("patient_id"), data.get("doctor_id"))})
        elif action == "get_all":
            self.send_json(200, {"referrals": get_referrals()})
        elif action == "add":
            success = add_referral(data)
            if success and data.get("patient_id"):
                add_notification(data["patient_id"], f"New referral created: {data.get('referred_to', 'Referral')}.", data.get("doctor_id"))
            self.send_json(201 if success else 400, {"success": success})
        else:
            self.send_json(400, {"message": "Invalid action"})

    def handle_profile_api(self, data):
        """Get or update the logged-in user's profile."""
        role = data.get("role", "").lower()
        identifier = data.get("identifier", "").strip()
        action = data.get("action", "get")
        profile = get_profile(role, identifier)
        if not profile:
            self.send_json(404, {"message": "Profile not found."})
            return
        if action == "get":
            self.send_json(200, {"profile": profile})
            return
        if action == "update":
            success = update_profile(role, profile["id"], data)
            self.send_json(200 if success else 400, {"success": success})
            return
        self.send_json(400, {"message": "Invalid action"})

    def handle_security_api(self, data):
        """Get or update account security preferences."""
        role = data.get("role", "").lower()
        identifier = data.get("identifier", "").strip()
        action = data.get("action", "get")
        if action == "get":
            self.send_json(200, {"two_step_enabled": get_two_step_enabled(role, identifier)})
            return
        if action == "update":
            success = set_two_step_enabled(role, identifier, bool(data.get("enabled")))
            self.send_json(200 if success else 404, {"success": success, "two_step_enabled": bool(data.get("enabled"))})
            return
        self.send_json(400, {"message": "Invalid action"})

    def handle_security_pin(self, data):
        """Create or replace the security PIN for an account."""
        role = data.get("role", "").lower()
        identifier = data.get("identifier", "").strip()
        pin = str(data.get("pin", "")).strip()
        if role not in ["patient", "doctor"] or not identifier or not pin.isdigit() or len(pin) != 4:
            self.send_json(400, {"message": "Security PIN must contain exactly 4 digits."})
            return
        success = set_security_pin(role, identifier, pin)
        self.send_json(200 if success else 404, {"success": success, "message": "Security PIN saved." if success else "Account not found."})

    def handle_pin_verification(self, data):
        """Verify the security PIN after password login."""
        role = data.get("role", "").lower()
        identifier = data.get("identifier", "").strip()
        pin = str(data.get("pin", "")).strip()
        if verify_security_pin(role, identifier, pin):
            self.send_json(200, {"message": "Security PIN verified. Login successful.", "role": role})
            return
        self.send_json(401, {"message": "The security PIN is not correct."})

    def handle_account_password(self, data):
        """Change the logged-in account password."""
        role = data.get("role", "").lower()
        identifier = data.get("identifier", "").strip()
        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")
        if role not in ["patient", "doctor"] or len(new_password) < 8:
            self.send_json(400, {"message": "New password must be at least 8 characters."})
            return
        success = change_account_password(role, identifier, current_password, new_password)
        self.send_json(200 if success else 401, {
            "success": success,
            "message": "Password changed successfully." if success else "Current password is not correct."
        })

    def handle_notifications_api(self, data):
        """Read or clear the logged-in account's notification feed."""
        recipient_id = data.get("recipient_id", "").strip()
        if not recipient_id:
            self.send_json(400, {"message": "Recipient ID is required."})
            return
        if data.get("action") == "mark_read":
            mark_notifications_read(recipient_id)
            self.send_json(200, {"success": True})
            return
        notifications, unread = get_notifications(recipient_id)
        self.send_json(200, {"notifications": notifications, "unread": unread})

    def do_GET(self):
        """Return a small health response or serve a frontend file."""
        # Parse URL for API requests
        parsed_url = urlparse(self.path)

        # Use this endpoint to quickly check whether the backend is running.
        if parsed_url.path == "/api/health":
            health_payload = {
                "status": "ok",
                "message": "Backend is running.",
                **tee_runtime_info(),
            }
            self.send_json(200, health_payload)
            return

        # API GET endpoints for data retrieval
        if parsed_url.path == "/api/patients":
            query = parse_qs(parsed_url.query)
            patient_id = query.get("id", [None])[0]
            if patient_id:
                patient = get_patient(patient_id)
                self.send_json(200 if patient else 404, {"patient": patient})
            else:
                patients = get_patients()
                self.send_json(200, {"patients": patients})
            return
        
        if parsed_url.path == "/api/doctors":
            query = parse_qs(parsed_url.query)
            doctor_id = query.get("id", [None])[0]
            if doctor_id:
                doctor = get_doctor(doctor_id)
                self.send_json(200 if doctor else 404, {"doctor": doctor})
            else:
                doctors = get_doctors()
                self.send_json(200, {"doctors": doctors})
            return
        
        if parsed_url.path == "/api/appointments":
            appointments = get_appointments()
            self.send_json(200, {"appointments": appointments})
            return

        # Keep the existing HTML and CSS files available from this same server.
        super().do_GET()

    def send_json(self, status_code, payload):
        """Send a JSON response with the headers required by the browser."""
        # Convert the Python dictionary into UTF-8 JSON bytes.
        response_body = json.dumps(payload).encode("utf-8")

        # Send the HTTP status and content headers first.
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

        # Write the response body back to the browser.
        self.wfile.write(response_body)


def send_sms_otp(phone_number, otp_code):
    """Send an OTP through a Twilio SMS-enabled phone number."""
    if not phone_number.startswith("+") or not phone_number[1:].isdigit():
        return {"sent": False, "message": "SMS requires an international phone number such as +923001234567."}
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    sms_from = os.getenv("TWILIO_SMS_FROM")

    if not all((account_sid, auth_token, sms_from)):
        return {
            "sent": False,
            "message": "SMS is not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_SMS_FROM before requesting an OTP.",
        }

    form_data = urlencode({
        "From": sms_from,
        "To": phone_number,
        "Body": f"Your Saman Healthcare verification code is {otp_code}.",
    }).encode("utf-8")
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    request = Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data=form_data,
        headers={"Authorization": f"Basic {credentials}"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            json.load(response)
        return {"sent": True, "message": "OTP sent by SMS."}
    except HTTPError as error:
        provider_message = error.read().decode("utf-8", errors="replace")
        print(f"SMS delivery failed ({error.code}): {provider_message}")
        return {"sent": False, "message": "Twilio rejected the SMS. Check that TWILIO_SMS_FROM is SMS-enabled."}
    except Exception as error:
        print(f"SMS delivery failed: {error}")
        return {"sent": False, "message": "The OTP could not be sent by SMS through Twilio."}


def send_whatsapp_login_details(phone_number, role, account_id):
    """Send non-sensitive account identifiers through Twilio WhatsApp or local mode."""
    if not phone_number.startswith("+") or not phone_number[1:].isdigit():
        return {"sent": False, "message": "WhatsApp requires an international phone number such as +923001234567."}
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    whatsapp_from = os.getenv("TWILIO_WHATSAPP_FROM")
    account_label = "Patient" if role == "patient" else "Doctor"
    message = (
        f"Saman Healthcare account created. {account_label} login ID: {account_id}. "
        f"Phone login: {phone_number}. Use your password to log in."
    )
    phone_digits = ''.join(character for character in phone_number if character.isdigit())
    whatsapp_url = f"https://wa.me/{phone_digits}?text={quote(message)}"

    if not all((account_sid, auth_token, whatsapp_from)):
        return {
            "sent": True,
            "message": "Login details are ready. Use the WhatsApp link to send them.",
            "whatsapp_url": whatsapp_url,
        }

    sender = whatsapp_from if whatsapp_from.startswith("whatsapp:") else f"whatsapp:{whatsapp_from}"
    form_data = urlencode({
        "From": sender,
        "To": f"whatsapp:{phone_number}",
        "Body": message,
    }).encode("utf-8")
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    request = Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data=form_data,
        headers={"Authorization": f"Basic {credentials}"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            json.load(response)
        return {"sent": True, "message": "Login details sent to WhatsApp.", "whatsapp_url": whatsapp_url}
    except HTTPError as error:
        provider_message = error.read().decode("utf-8", errors="replace")
        print(f"WhatsApp delivery failed ({error.code}): {provider_message}")
        return {"sent": False, "message": "Twilio rejected the WhatsApp message."}
    except Exception as error:
        print(f"WhatsApp delivery failed: {error}")
        return {"sent": False, "message": "The WhatsApp message could not be sent through Twilio."}
    except Exception as error:
        print(f"WhatsApp delivery failed: {error}")
        return {"sent": False, "message": "The login details could not be sent to WhatsApp."}


def create_demo_seed_data():
    """Create a small set of demo patients and appointments for initial dashboard data."""
    # Demo doctors
    if not doctor_exists("D2001"):
        register_doctor("D2001", "Dr. Martin Deo", "+923009876543", "doctor@demo.com", "doctor123",
                       "General Medicine", "MBBS, FCPS", 15, "1234", "General Practitioner",
                       "DOC100001", "General Medicine", "City Care Hospital", "1990-02-14", "5678")
    if not doctor_exists("D2002"):
        register_doctor("D2002", "Dr. Priya Sharma", "+923001234567", "priya@demo.com", "doctor123",
                       "Cardiology", "MD Cardio", 12, "1234", "Cardiologist",
                       "DOC100002", "Cardiology", "City Care Hospital", "1987-06-09", "9012")
    if not doctor_exists("D2003"):
        register_doctor("D2003", "Dr. Arun Kumar", "+923004567890", "arun@demo.com", "doctor123",
                       "Internal Medicine", "MBBS, MD", 10, "1234", "Internal Medicine",
                       "DOC100003", "Internal Medicine", "City Care Hospital", "1985-11-21", "3456")

    # Demo patients
    patient_seed = [
        ("P1001", "Demo Patient", "+923001234567", "patient@demo.com", 30, "Male", "O+", "1995-05-15", "1234", "House 12, Gulshan Avenue"),
        ("P1002", "Ayesha Khan", "+923002345678", "ayesha@demo.com", 27, "Female", "A+", "1998-10-08", "4321", "Lane 7, Model Town"),
        ("P1003", "Usman Ali", "+923003456789", "usman@demo.com", 41, "Male", "B+", "1984-03-26", "8765", "Block C, Peshawar Road"),
        ("P1004", "Sara Ahmed", "+923004567890", "sara@demo.com", 34, "Female", "AB+", "1991-12-19", "2468", "Apartment 9, Gulistan"),
    ]

    for patient_id, name, phone, email, age, gender, blood_group, dob, aadhaar, address in patient_seed:
        if not patient_exists(patient_id):
            register_patient(patient_id, name, phone, email, "patient123", age, gender, blood_group,
                             "1234", dob, aadhaar)
            from database import get_db
            conn = get_db()
            conn.execute('UPDATE patients SET address = ? WHERE id = ?', (address, patient_id))
            conn.commit()
            conn.close()

    # Add a few sample appointments for the demo patient
    from database import get_db
    conn = get_db()
    existing = conn.execute('SELECT COUNT(*) FROM appointments WHERE patient_id = ?', ("P1001",)).fetchone()[0]
    if existing == 0:
        conn.execute(
            '''INSERT INTO appointments (doctor_id, patient_id, appointment_date, appointment_time, status, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            ("D2001", "P1001", "2026-09-14", "10:30 AM", "confirmed", "Follow-up consultation and review of medications.", "2026-09-11T09:00:00")
        )
    conn.commit()
    conn.close()


# Start the local server when this file is run directly.
if __name__ == "__main__":
    # Initialize database
    init_database()
    create_demo_seed_data()

    server_address = ("127.0.0.1", 8000)
    server = ThreadingHTTPServer(server_address, HealthcareRequestHandler)
    print("Saman Healthcare running at http://127.0.0.1:8000")
    print("Demo patient login: P1001 / patient123")
    print("Demo doctor login: D2001 / doctor123")
    print("Database: healthcare.db (SQLite)")
    print("SMS OTP: " + ("Twilio configured" if all(os.getenv(key) for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SMS_FROM")) else "NOT configured"))

    try:
        # Keep accepting browser requests until the user stops the server.
        server.serve_forever()
    except KeyboardInterrupt:
        # Close the socket cleanly when the server is stopped with Ctrl+C.
        print("\nServer stopped.")
        server.server_close()
