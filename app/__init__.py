import os
import warnings
from datetime import datetime

# Suppress known Windows TLS root certificate negative serial number deprecation warning
warnings.filterwarnings("ignore", message=".*Parsed a negative serial number.*")
try:
    from cryptography.utils import CryptographyDeprecationWarning
    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except Exception:
    pass

from flask import Flask, render_template
from app.config import config_by_name, Config, INSTANCE_DIR
from app.extensions import db
from app.routes.dashboard import dashboard_bp
from app.routes.interviews import interviews_bp
from app.routes.reports import reports_bp
from app.routes.api import api_bp
from app.routes.auth import auth_bp
from app.routes.admin import admin_bp


def create_app(config_name: str = "development") -> Flask:
    """Application factory for AI Interview Studio."""
    app = Flask(__name__, instance_path=str(INSTANCE_DIR))
    
    # Load configuration
    cfg = config_by_name.get(config_name, Config)
    app.config.from_object(cfg)

    # Ensure upload and instance directories exist safely
    try:
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    except OSError:
        pass
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(interviews_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)

    # Custom Jinja filters
    @app.template_filter("format_dt")
    def format_dt(value, fmt="%b %d, %Y • %I:%M %p"):
        if not value:
            return "—"
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.strftime(fmt)
            except Exception:
                return value
        return value.strftime(fmt)

    @app.template_filter("status_badge_class")
    def status_badge_class(status: str) -> str:
        mapping = {
            "draft": "badge-gray",
            "prepared": "badge-blue",
            "in_progress": "badge-amber",
            "awaiting_finalization": "badge-indigo",
            "completed": "badge-emerald",
            "interrupted": "badge-orange",
            "failed": "badge-rose",
        }
        return mapping.get((status or "").lower(), "badge-gray")

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("base.html", error_title="404 - Page Not Found", error_message="The requested resource could not be found."), 404

    @app.errorhandler(413)
    def request_entity_too_large(error):
        max_mb = app.config.get("MAX_CONTENT_LENGTH", 10485760) // (1024 * 1024)
        return render_template("base.html", error_title="413 - File Too Large", error_message=f"Uploaded file exceeds the maximum limit of {max_mb} MB."), 413

    @app.errorhandler(500)
    def internal_error(error):
        return render_template("base.html", error_title="500 - Internal Server Error", error_message="An unexpected server error occurred."), 500

    # Auto-create tables in development and testing, ensuring SQLite columns are synchronized
    try:
        with app.app_context():
            db.create_all()
            # Safe migration for existing SQLite database files if columns are missing
            try:
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    res = conn.execute(text("PRAGMA table_info(interviews)"))
                    cols = [r[1] for r in res.fetchall()]
                    if cols:
                        if "llm_provider" not in cols:
                            conn.execute(text("ALTER TABLE interviews ADD COLUMN llm_provider VARCHAR(50) DEFAULT 'gemini'"))
                        if "voice_engine" not in cols:
                            conn.execute(text("ALTER TABLE interviews ADD COLUMN voice_engine VARCHAR(50) DEFAULT 'elevenlabs'"))
                        if "user_id" not in cols:
                            conn.execute(text("ALTER TABLE interviews ADD COLUMN user_id VARCHAR(100) DEFAULT NULL"))
                        if "resume_data_base64" not in cols:
                            conn.execute(text("ALTER TABLE interviews ADD COLUMN resume_data_base64 TEXT DEFAULT NULL"))
                        if "resume_mimetype" not in cols:
                            conn.execute(text("ALTER TABLE interviews ADD COLUMN resume_mimetype VARCHAR(100) DEFAULT NULL"))
                        conn.commit()
            except Exception as mig_err:
                app.logger.debug(f"Migration check skipped: {mig_err}")
    except Exception as db_err:
        app.logger.warning(f"Database initialization warning: {db_err}")

    return app


# Default top-level application instance for Vercel, WSGI servers, and CLI runners
_default_env = os.getenv("FLASK_ENV", "production")
if os.getenv("FLASK_ENV") != "testing":
    try:
        app = create_app(_default_env)
    except Exception:
        app = None

