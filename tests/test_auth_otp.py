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
    })
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
        yield client


def register_user(client, email="new@example.com"):
    return client.post("/register", data={
        "name": "New User", "email": email, "password": "Password123", "confirm_password": "Password123"
    })


def test_registration_hashes_password_and_logs_in_directly(client):
    response = register_user(client)
    assert response.status_code == 302
    assert "snapshot" in response.location or "/reports" in response.location
    with client.application.app_context():
        user = User.query.filter_by(email="new@example.com").one()
        assert user.email_verified is True
        assert user.password_hash != "Password123"
        assert user.check_password("Password123")
    assert client.get("/snapshot").status_code == 200


def test_duplicate_email_and_invalid_password(client):
    register_user(client)
    client.get("/logout")
    duplicate = client.post("/register", data={"name": "Other", "email": "new@example.com", "password": "Password123", "confirm_password": "Password123"})
    assert b"already exists" in duplicate.data
    client.get("/logout")
    invalid_login = client.post("/login", data={"email": "new@example.com", "password": "wrong-password"})
    assert b"Invalid email or password" in invalid_login.data


def test_forgot_password_resets_password_directly(client):
    register_user(client)
    client.get("/logout")
    response = client.post("/forgot-password", data={"email": "new@example.com"})
    assert response.status_code == 302
    assert "/reset-password" in response.location
    response = client.post("/reset-password", data={"password": "NewPassword123", "confirm_password": "NewPassword123"})
    assert response.status_code == 302
    assert client.post("/login", data={"email": "new@example.com", "password": "Password123"}).status_code == 200
    assert client.post("/login", data={"email": "new@example.com", "password": "NewPassword123"}).status_code == 302


def test_login_and_logout_flow(client):
    register_user(client, "login-test@example.com")
    client.get("/logout")
    response = client.post("/login", data={"email": "login-test@example.com", "password": "Password123"})
    assert response.status_code == 302
    assert "snapshot" in response.location or "/reports" in response.location


def test_protected_ai_route_requires_login(client):
    assert client.get("/ai-advisor").status_code == 302
    assert client.post("/ai-advisor/chat", json={"question": "hello"}).status_code == 302
