from datetime import datetime, timedelta

import pytest

from app import create_app
from extensions import db
from models import User


@pytest.fixture
def client():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "GEMINI_API_KEY": "",
        "OTP_EXPIRY_MINUTES": 5,
        "OTP_RESEND_COOLDOWN_SECONDS": 60,
        "OTP_MAX_ATTEMPTS": 3,
    })
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
        yield client


def register_pending(client, email="new@example.com"):
    response = client.post("/register", data={
        "name": "New User", "email": email, "password": "Password123", "confirm_password": "Password123"
    })
    with client.session_transaction() as session:
        return response, session["_test_otp"]


def test_registration_hashes_password_and_requires_verification(client):
    response, otp = register_pending(client)
    assert response.status_code == 302
    assert "/verify-email" in response.location
    assert client.get("/reports").status_code == 302
    with client.application.app_context():
        user = User.query.filter_by(email="new@example.com").one()
        assert user.email_verified is False
        assert user.password_hash != "Password123"
        assert user.check_password("Password123")
    assert client.post("/verify-email?purpose=registration", data={"otp": otp}).status_code == 302
    with client.application.app_context():
        assert User.query.filter_by(email="new@example.com").one().email_verified is True


def test_duplicate_email_invalid_password_and_wrong_otp(client):
    register_pending(client)
    duplicate = client.post("/register", data={"name": "Other", "email": "new@example.com", "password": "Password123", "confirm_password": "Password123"})
    assert b"already exists" in duplicate.data
    client.get("/logout")
    invalid_login = client.post("/login", data={"email": "new@example.com", "password": "wrong-password"})
    assert b"Invalid email or password" in invalid_login.data
    response, _ = register_pending(client, "second@example.com")
    assert response.status_code == 302
    wrong = client.post("/verify-email?purpose=registration", data={"otp": "000000"})
    assert b"Invalid verification code" in wrong.data


def test_otp_attempt_limit_expiry_and_resend_cooldown(client):
    _, otp = register_pending(client)
    for _ in range(3):
        response = client.post("/verify-email?purpose=registration", data={"otp": "111111"})
    assert b"Too many incorrect attempts" in response.data
    resend = client.post("/verify-email/resend", data={"purpose": "registration"}, follow_redirects=True)
    assert b"Please wait before requesting another code" in resend.data
    with client.application.app_context():
        user = User.query.filter_by(email="new@example.com").one()
        user.otp_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
    expired = client.post("/verify-email?purpose=registration", data={"otp": otp})
    assert b"expired" in expired.data


def test_forgot_password_otp_resets_password_and_invalidates_old_password(client):
    _, otp = register_pending(client)
    client.post("/verify-email?purpose=registration", data={"otp": otp})
    client.post("/logout")
    response = client.post("/forgot-password", data={"email": "new@example.com"})
    assert response.status_code == 302
    with client.session_transaction() as session:
        reset_otp = session["_test_otp"]
    response = client.post("/verify-email?purpose=password_reset", data={"otp": reset_otp})
    assert response.status_code == 302
    assert "/reset-password" in response.location
    response = client.post("/reset-password", data={"password": "NewPassword123", "confirm_password": "NewPassword123"})
    assert response.status_code == 302
    assert client.post("/login", data={"email": "new@example.com", "password": "Password123"}).status_code == 200
    assert client.post("/login", data={"email": "new@example.com", "password": "NewPassword123"}).status_code == 302


def test_unverified_login_redirects_to_otp(client):
    register_pending(client, "pending@example.com")
    client.get("/logout")
    response = client.post("/login", data={"email": "pending@example.com", "password": "Password123"})
    assert response.status_code == 302
    assert "/verify-email" in response.location


def test_password_plus_otp_login_mode(client):
    client.application.config["AUTH_MODE"] = "PASSWORD_ONLY"
    _, otp = register_pending(client, "otp-login@example.com")
    client.post("/verify-email?purpose=registration", data={"otp": otp})
    client.get("/logout")
    client.application.config["AUTH_MODE"] = "PASSWORD_PLUS_OTP"
    response = client.post("/login", data={"email": "otp-login@example.com", "password": "Password123"})
    assert response.status_code == 302
    assert "/verify-email?purpose=login" in response.location
    with client.session_transaction() as session:
        login_otp = session["_test_otp"]
    assert client.post("/verify-email?purpose=login", data={"otp": login_otp}).status_code == 302


def test_protected_ai_route_requires_login(client):
    assert client.get("/ai-advisor").status_code == 302
    assert client.post("/ai-advisor/chat", json={"question": "hello"}).status_code == 302