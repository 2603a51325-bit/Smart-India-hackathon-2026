"""Simple backend for the Saman Healthcare demo login page."""

# Import Python's built-in modules so the demo does not need external packages.
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
OTP_CHALLENGES = {}

# Keep password-reset OTP challenges separate from login OTP challenges.
RESET_CHALLENGES = {}

# Keep verified reset tokens separate from OTP challenges.
RESET_TOKENS = {}

# Keep newly registered demo accounts grouped by account type in memory.
REGISTERED_USERS = {"patient": [], "doctor": []}

# Keep OTP codes valid for five minutes.
OTP_LIFETIME_SECONDS = 300


class HealthcareRequestHandler(SimpleHTTPRequestHandler):
    """Serve the frontend files and handle login API requests."""

    def do_GET(self):
        """Return a small health response or serve a frontend file."""
        # Use this endpoint to quickly check whether the backend is running.
        if self.path == "/api/health":
            self.send_json(200, {"status": "ok", "message": "Backend is running."})
            return

        # Keep the existing HTML and CSS files available from this same server.
        super().do_GET()

    def do_POST(self):
        """Route login and OTP verification requests."""
        # Reject unknown API paths instead of treating them as authentication requests.
        if self.path not in {
            "/api/login",
            "/api/register",
            "/api/verify-otp",
            "/api/forgot-password/request",
            "/api/forgot-password/verify",
            "/api/forgot-password/reset",
        }:
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

        # Verify the code entered in the OTP popup.
        self.handle_otp_verification(request_data)

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
        """Validate login details and optionally create an OTP challenge."""
        # Pull the fields sent by the login form.
        role = login_data.get("role", "").lower()
        identifier = login_data.get("identifier", "").strip()
        password = login_data.get("password", "")
        two_step_enabled = bool(login_data.get("two_step"))

        # Validate the basic request shape before checking account details.
        if role not in DEMO_USERS or not identifier or not password:
            self.send_json(400, {"message": "Role, login ID, and password are required."})
            return

        # Search the built-in demo account and any accounts created by registration.
        accounts = [DEMO_USERS[role], *REGISTERED_USERS[role]]
        account = next((candidate for candidate in accounts if identifier in {
            candidate.get("patient_id"),
            candidate.get("doctor_id"),
            candidate["phone"],
        }), None)
        valid_identifier = account is not None
        valid_password = valid_identifier and password == account["password"]

        # Return a generic failure message so the demo does not reveal which field failed.
        if not valid_identifier or not valid_password:
            self.send_json(401, {"message": "The login details are not correct."})
            return

        # Finish the login immediately when two-step verification is disabled.
        if not two_step_enabled:
            self.send_json(200, {
                "message": "Login successful.",
                "role": role,
            })
            return

        # Generate and store a short-lived challenge before sending its code.
        challenge_id = secrets.token_urlsafe(24)
        otp_code = f"{secrets.randbelow(1_000_000):06d}"
        OTP_CHALLENGES[challenge_id] = {
            "role": role,
            "identifier": identifier,
            "otp_hash": self.hash_otp(otp_code),
            "expires_at": time.time() + OTP_LIFETIME_SECONDS,
        }

        # Use the account's saved phone even when the user logged in with an ID.
        delivery_result = send_whatsapp_otp(account["phone"], otp_code)
        if not delivery_result["sent"]:
            OTP_CHALLENGES.pop(challenge_id, None)
            self.send_json(502, {"message": delivery_result["message"]})
            return

        # Tell the browser to show the OTP popup before login can continue.
        self.send_json(202, {
            "message": delivery_result["message"],
            "requires_otp": True,
            "challenge_id": challenge_id,
        })

    def handle_registration(self, registration_data):
        """Validate and store a simple demo registration account."""
        # Read the common account fields sent by both registration modes.
        role = registration_data.get("role", "").lower()
        phone = registration_data.get("phone", "").strip()
        password = registration_data.get("password", "")

        # Reject incomplete registrations before creating an account.
        if role not in DEMO_USERS or not phone or not password:
            self.send_json(400, {"message": "Account type, phone, and password are required."})
            return

        # Prevent two demo accounts from using the same phone number.
        all_accounts = [*DEMO_USERS.values(), *REGISTERED_USERS["patient"], *REGISTERED_USERS["doctor"]]
        if any(account["phone"] == phone for account in all_accounts):
            self.send_json(409, {"message": "An account with this phone number already exists."})
            return

        # Create a simple account ID and save the new account in memory.
        account_prefix = "D" if role == "doctor" else "P"
        account_id = f"{account_prefix}{secrets.randbelow(9000) + 1000}"
        account_key = "doctor_id" if role == "doctor" else "patient_id"
        REGISTERED_USERS[role].append({
            account_key: account_id,
            "phone": phone,
            "password": password,
        })

        # Return the generated ID so the user can use it later if needed.
        self.send_json(201, {
            "message": "Registration successful.",
            "role": role,
            "account_id": account_id,
        })

    def handle_otp_verification(self, verification_data):
        """Verify an OTP challenge and complete the login."""
        # Read the challenge identifier and six-digit code from the popup.
        challenge_id = verification_data.get("challenge_id", "")
        otp_code = verification_data.get("otp", "")
        challenge = OTP_CHALLENGES.get(challenge_id)

        # Reject missing, expired, or unknown challenges.
        if not challenge or time.time() > challenge["expires_at"]:
            OTP_CHALLENGES.pop(challenge_id, None)
            self.send_json(401, {"message": "This OTP has expired. Please log in again."})
            return

        # Compare hashes instead of storing or comparing the raw OTP directly.
        if not hmac.compare_digest(challenge["otp_hash"], self.hash_otp(otp_code)):
            self.send_json(401, {"message": "The OTP is not correct."})
            return

        # Remove the challenge so the same OTP cannot be reused.
        OTP_CHALLENGES.pop(challenge_id, None)
        self.send_json(200, {
            "message": "OTP verified. Login successful.",
            "role": challenge["role"],
        })

    def find_account(self, role, identifier):
        """Find an account by phone or account ID."""
        # Search built-in and newly registered accounts for the requested role.
        accounts = [DEMO_USERS.get(role, {}), *REGISTERED_USERS.get(role, [])]
        return next((account for account in accounts if identifier in {
            account.get("patient_id"),
            account.get("doctor_id"),
            account.get("phone"),
        }), None)

    def handle_password_reset_request(self, reset_data):
        """Create and deliver a password-reset OTP."""
        # Read the account type and phone or ID entered on the forgot page.
        role = reset_data.get("role", "").lower()
        identifier = reset_data.get("identifier", "").strip()
        account = self.find_account(role, identifier)

        # Do not reveal whether an account exists in a real application.
        if not account:
            self.send_json(401, {"message": "We could not find that account."})
            return

        # Create a separate short-lived challenge for password reset.
        challenge_id = secrets.token_urlsafe(24)
        otp_code = f"{secrets.randbelow(1_000_000):06d}"
        RESET_CHALLENGES[challenge_id] = {
            "role": role,
            "account": account,
            "otp_hash": self.hash_otp(otp_code),
            "expires_at": time.time() + OTP_LIFETIME_SECONDS,
        }

        # Send the reset code to the account's WhatsApp number.
        delivery_result = send_whatsapp_otp(account["phone"], otp_code)
        if not delivery_result["sent"]:
            RESET_CHALLENGES.pop(challenge_id, None)
            self.send_json(502, {"message": delivery_result["message"]})
            return

        # Return only the challenge ID; the OTP itself stays out of the browser response.
        self.send_json(202, {
            "message": delivery_result["message"],
            "challenge_id": challenge_id,
        })

    def handle_password_reset(self, reset_data):
        """Update the account password with a verified reset token."""
        # Read the verified token and replacement password from the new page.
        reset_token = reset_data.get("reset_token", "")
        new_password = reset_data.get("new_password", "")
        token_data = RESET_TOKENS.get(reset_token)

        # Reject invalid, expired, or incomplete reset requests.
        if not token_data or time.time() > token_data["expires_at"]:
            RESET_TOKENS.pop(reset_token, None)
            self.send_json(401, {"message": "This password reset session has expired."})
            return
        if not new_password or len(new_password) < 8:
            self.send_json(400, {"message": "Password must be at least 8 characters."})
            return

        # Update the in-memory account and consume the one-time reset token.
        token_data["account"]["password"] = new_password
        RESET_TOKENS.pop(reset_token, None)
        self.send_json(200, {"message": "Password changed successfully."})

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

    def send_json(self, status_code, payload):
        """Send a JSON response with the headers required by the browser."""
        # Convert the Python dictionary into UTF-8 JSON bytes.
        response_body = json.dumps(payload).encode("utf-8")

        # Send the HTTP status and content headers first.
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()

        # Write the response body back to the browser.
        self.wfile.write(response_body)


def send_whatsapp_otp(phone_number, otp_code):
    """Send an OTP through Twilio WhatsApp or use local console mode."""
    # Read the Twilio settings from environment variables instead of hard-coding secrets.
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    whatsapp_from = os.getenv("TWILIO_WHATSAPP_FROM")

    # Use console mode when credentials are absent so the local demo remains testable.
    if not all((account_sid, auth_token, whatsapp_from)):
        print(f"[LOCAL OTP] Code for {phone_number}: {otp_code}")
        return {
            "sent": True,
            "message": "OTP created in local mode. Check the Python terminal.",
        }

    # Build the WhatsApp message that Twilio will send.
    form_data = urlencode({
        "From": f"whatsapp:{whatsapp_from}",
        "To": f"whatsapp:{phone_number}",
        "Body": f"Your Saman Healthcare verification code is {otp_code}.",
    }).encode("utf-8")

    # Create the HTTP Basic Authentication value required by Twilio.
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    request = Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data=form_data,
        headers={"Authorization": f"Basic {credentials}"},
        method="POST",
    )

    try:
        # Send the request to Twilio and ensure the response is valid JSON.
        with urlopen(request, timeout=10) as response:
            json.load(response)
        return {"sent": True, "message": "OTP sent to your WhatsApp."}
    except Exception as error:
        # Avoid exposing provider credentials or raw provider errors to the browser.
        print(f"WhatsApp delivery failed: {error}")
        return {"sent": False, "message": "The WhatsApp OTP could not be sent."}


# Start the local server when this file is run directly.
if __name__ == "__main__":
    server_address = ("127.0.0.1", 8000)
    server = ThreadingHTTPServer(server_address, HealthcareRequestHandler)
    print("Saman Healthcare running at http://127.0.0.1:8000")
    print("Demo patient login: P1001 / patient123")
    print("Demo doctor login: D2001 / doctor123")

    try:
        # Keep accepting browser requests until the user stops the server.
        server.serve_forever()
    except KeyboardInterrupt:
        # Close the socket cleanly when the server is stopped with Ctrl+C.
        print("\nServer stopped.")
        server.server_close()
