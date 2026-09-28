import secrets
from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import User
from services.email_service import send_otp_email

auth_bp = Blueprint("auth", __name__)


def _valid_email(value):
    local, separator, domain = value.rpartition("@")
    return bool(local and separator and "." in domain and not any(char.isspace() for char in value))


def _password_valid(password):
    return len(password) >= 8


def _mask_email(email):
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if local and domain else email


def _clear_otp(user):
    user.otp_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    user.otp_created_at = None
    user.otp_purpose = None


def _issue_otp(user, purpose, force=False):
    now = datetime.utcnow()
    cooldown = current_app.config["OTP_RESEND_COOLDOWN_SECONDS"]
    if not force and user.otp_created_at and (now - user.otp_created_at).total_seconds() < cooldown:
        return False, "Please wait before requesting another code."

    otp = f"{secrets.randbelow(1_000_000):06d}"
    user.otp_hash = generate_password_hash(otp)
    user.otp_created_at = now
    user.otp_expires_at = now + timedelta(minutes=current_app.config["OTP_EXPIRY_MINUTES"])
    user.otp_attempts = 0
    user.otp_purpose = purpose
    db.session.commit()

    if current_app.testing:
        session["_test_otp"] = otp
    try:
        delivered = send_otp_email(user.email, otp, purpose)
    except Exception:
        delivered = False
    if not delivered and not current_app.testing:
        return True, "Email delivery is not configured. Contact the administrator to enable verification emails."
    return True, "Verification code sent."


def _verify_otp(user, otp, purpose):
    if user.otp_purpose != purpose or not user.otp_hash:
        return False, "Verification code is invalid."
    if user.otp_expires_at and datetime.utcnow() > user.otp_expires_at:
        _clear_otp(user)
        db.session.commit()
        return False, "Verification code has expired. Please request a new code."
    if user.otp_attempts >= current_app.config["OTP_MAX_ATTEMPTS"]:
        return False, "Too many incorrect attempts. Please request a new code."
    if not check_password_hash(user.otp_hash, otp):
        user.otp_attempts += 1
        db.session.commit()
        if user.otp_attempts >= current_app.config["OTP_MAX_ATTEMPTS"]:
            return False, "Too many incorrect attempts. Please request a new code."
        return False, "Invalid verification code."
    _clear_otp(user)
    db.session.commit()
    return True, ""


def _pending_user(purpose):
    key = "password_reset_user_id" if purpose == "password_reset" else "pending_auth_user_id"
    user_id = session.get(key)
    return db.session.get(User, user_id) if user_id else None


def _login_user(user):
    login_user(user, remember=True)
    session["auth_version"] = user.auth_version


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.reports"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        user_type = request.form.get("user_type", "Student")
        if not name or not _valid_email(email) or not _password_valid(password) or password != confirm:
            flash("Enter a valid name, email, matching passwords, and a password of at least 8 characters.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "warning")
        else:
            user = User(name=name, email=email, user_type=user_type, email_verified=False)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            session.clear()
            session["pending_auth_user_id"] = user.id
            session["pending_auth_purpose"] = "registration"
            _, message = _issue_otp(user, "registration")
            flash(message, "info")
            return redirect(url_for("auth.verify_email", purpose="registration"))
    return render_template("auth.html", mode="register")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.reports"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if not user or not user.check_password(request.form.get("password", "")):
            flash("Invalid email or password.", "danger")
        elif not user.email_verified:
            session.clear()
            session["pending_auth_user_id"] = user.id
            session["pending_auth_purpose"] = "registration"
            _, message = _issue_otp(user, "registration")
            flash("Please verify your email before continuing.", "warning")
            flash(message, "info")
            return redirect(url_for("auth.verify_email", purpose="registration"))
        elif current_app.config["AUTH_MODE"] == "PASSWORD_PLUS_OTP":
            session.clear()
            session["pending_auth_user_id"] = user.id
            session["pending_auth_purpose"] = "login"
            _, message = _issue_otp(user, "login", force=True)
            flash(message, "info")
            return redirect(url_for("auth.verify_email", purpose="login"))
        else:
            session.clear()
            _login_user(user)
            return redirect(url_for("main.reports"))
    return render_template("auth.html", mode="login")


@auth_bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    purpose = request.args.get("purpose") or session.get("pending_auth_purpose", "registration")
    user = _pending_user("password_reset" if purpose == "password_reset" else "auth")
    if not user:
        flash("Start the verification process again.", "warning")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        valid, message = _verify_otp(user, request.form.get("otp", "").strip(), purpose)
        if valid:
            if purpose == "password_reset":
                session.pop("password_reset_user_id", None)
                session["password_reset_verified_user_id"] = user.id
                return redirect(url_for("auth.reset_password"))
            session.clear()
            if purpose == "registration":
                user.email_verified = True
                db.session.commit()
                flash("Email verified. You can now log in.", "success")
                return redirect(url_for("auth.login"))
            _login_user(user)
            return redirect(url_for("main.reports"))
        flash(message, "danger")
    return render_template("verify_email.html", email=_mask_email(user.email), purpose=purpose)


@auth_bp.post("/verify-email/resend")
def resend_otp():
    purpose = request.form.get("purpose", "registration")
    user = _pending_user("password_reset" if purpose == "password_reset" else "auth")
    if user:
        _, message = _issue_otp(user, purpose)
        flash(message, "info")
        return redirect(url_for("auth.verify_email", purpose=purpose))
    flash("Start the verification process again.", "warning")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first() if _valid_email(email) else None
        session.clear()
        if user:
            session["password_reset_user_id"] = user.id
            _, message = _issue_otp(user, "password_reset")
            if message.startswith("Please wait"):
                flash(message, "warning")
            else:
                flash("If an account exists for this email, a verification code has been sent.", "info")
        else:
            flash("If an account exists for this email, a verification code has been sent.", "info")
        return redirect(url_for("auth.verify_email", purpose="password_reset")) if user else render_template("auth.html", mode="forgot_password")
    return render_template("auth.html", mode="forgot_password")


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    user_id = session.get("password_reset_verified_user_id")
    user = db.session.get(User, user_id) if user_id else None
    if not user:
        flash("Start the password reset process again.", "warning")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if not _password_valid(password) or password != request.form.get("confirm_password", ""):
            flash("Passwords must match and contain at least 8 characters.", "danger")
        else:
            user.set_password(password)
            user.auth_version += 1
            db.session.commit()
            session.clear()
            flash("Password updated. Please log in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth.html", mode="reset_password")


@auth_bp.get("/logout")
def logout():
    session.clear()
    logout_user()
    return redirect(url_for("main.index"))
