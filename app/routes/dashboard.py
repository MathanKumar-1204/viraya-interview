import random
from flask import Blueprint, render_template, session, redirect, url_for
from app.config import Config

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    """Single candidate landing page for Viraya Company's Interview AI Bot."""
    # Generate fresh math challenge for the session
    num1 = random.randint(3, 18)
    num2 = random.randint(2, 9)
    session["captcha_answer"] = str(num1 + num2)
    session.modified = True

    captcha_question = f"{num1} + {num2} = ?"

    return render_template(
        "landing.html",
        captcha_question=captcha_question,
        fixed_role="AI developer"
    )


@dashboard_bp.route("/dashboard")
def legacy_dashboard():
    """Redirect legacy dashboard link."""
    if session.get("is_admin"):
        return redirect(url_for("admin.admin_dashboard"))
    return redirect(url_for("dashboard.index"))
