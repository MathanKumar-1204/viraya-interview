"""
Authentication Blueprint for AI Interview Studio.
Handles user signup, login, session state, and route protection backed by MongoDB.
"""
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.services.mongo_service import MongoUser

auth_bp = Blueprint("auth", __name__)


ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "admin@2004"


def login_required(f):
    """Decorator requiring an active user session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required. Please log in."}), 401
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator requiring an active admin session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        is_admin_user = (
            "user_id" in session
            and session.get("is_admin") is True
            and (session.get("user_email") or "").lower() == ADMIN_EMAIL.lower()
        )
        if not is_admin_user:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Admin access required."}), 403
            flash("Admin access restricted. Please log in with admin credentials.", "danger")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """Register a new user account in MongoDB."""
    if "user_id" in session:
        if session.get("is_admin"):
            return redirect(url_for("admin.admin_dashboard"))
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        if not name:
            flash("Full name is required.", "danger")
            return render_template("signup.html", name=name, email=email)
        if not email or "@" not in email:
            flash("A valid email address is required.", "danger")
            return render_template("signup.html", name=name, email=email)
        if email.lower() == ADMIN_EMAIL.lower():
            flash("The administrator email is reserved. Please sign in via the login page.", "warning")
            return redirect(url_for("auth.login", email=email))
        if not password or len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("signup.html", name=name, email=email)
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("signup.html", name=name, email=email)

        # Check existing user
        try:
            existing = MongoUser.find_by_email(email)
            if existing:
                flash(f"An account with email '{email}' already exists. Please log in.", "warning")
                return redirect(url_for("auth.login", email=email))

            user = MongoUser.create(name=name, email=email, password=password)

            # Auto-login upon registration
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_email"] = user.email
            session["is_admin"] = False
            session.permanent = True

            flash(f"Welcome to AI Interview Studio, {user.name}!", "success")
            return redirect(url_for("dashboard.index"))

        except Exception as e:
            flash(f"Registration error: {str(e)}", "danger")
            return render_template("signup.html", name=name, email=email)

    return render_template("signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate an existing user."""
    if "user_id" in session:
        if session.get("is_admin"):
            return redirect(url_for("admin.admin_dashboard"))
        return redirect(url_for("dashboard.index"))

    next_url = request.args.get("next") or request.form.get("next") or url_for("dashboard.index")
    prefill_email = request.args.get("email", "")

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html", email=email, next=next_url)

        clean_email = email.lower()

        # Dedicated admin authentication (admin@gmail.com / admin@2004)
        if clean_email == ADMIN_EMAIL.lower():
            if password != ADMIN_PASSWORD:
                flash("Invalid email or password. Please try again.", "danger")
                return render_template("login.html", email=email, next=next_url)

            # Ensure admin user document exists in MongoDB if available
            admin_user = None
            try:
                admin_user = MongoUser.find_by_email(ADMIN_EMAIL)
                if not admin_user:
                    admin_user = MongoUser.create(name="Administrator", email=ADMIN_EMAIL, password=ADMIN_PASSWORD)
            except Exception:
                pass

            session["user_id"] = admin_user.id if admin_user else "admin_master_id"
            session["user_name"] = "Administrator"
            session["user_email"] = ADMIN_EMAIL
            session["is_admin"] = True
            session.permanent = True

            flash("Welcome Administrator! Access granted to Admin Portal.", "success")
            target_url = next_url if (next_url and next_url != url_for("dashboard.index")) else url_for("admin.admin_dashboard")
            return redirect(target_url)

        try:
            user = MongoUser.find_by_email(clean_email)
            if not user or not MongoUser.verify_password(user.password, password):
                flash("Invalid email or password. Please try again.", "danger")
                return render_template("login.html", email=email, next=next_url)

            # Set user session
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_email"] = user.email
            session["is_admin"] = False
            session.permanent = True

            flash(f"Welcome back, {user.name}!", "success")
            # If regular user had /admin in next_url, redirect them to dashboard
            target_url = url_for("dashboard.index") if (next_url and "/admin" in next_url) else next_url
            return redirect(target_url)

        except Exception as e:
            flash(f"Login error: {str(e)}", "danger")
            return render_template("login.html", email=email, next=next_url)

    return render_template("login.html", email=prefill_email, next=next_url)


@auth_bp.route("/logout")
def logout():
    """Clear active user session."""
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)
    session.pop("is_admin", None)
    session.pop("active_interview", None)
    session.pop("active_report", None)
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("auth.login"))
