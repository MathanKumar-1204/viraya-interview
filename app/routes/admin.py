"""
Admin Blueprint for Viraya Company's Interview AI Bot.
Provides an administrative portal strictly accessible by admin@gmail.com with admin@2004.
Displays all candidate interviews across the platform sorted from newest to oldest.
"""
from datetime import datetime, timezone
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.config import Config
from app.models.interview import Interview, InterviewStatus
from app.services.mongo_service import MongoInterview
from app.routes.auth import login_required, admin_required
from app.extensions import db

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _parse_datetime(dt):
    """Normalize datetime or ISO string to UTC-aware datetime for robust sorting."""
    if not dt:
        return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    return datetime.min.replace(tzinfo=timezone.utc)


@admin_bp.route("", strict_slashes=False)
@admin_bp.route("/", strict_slashes=False)
@login_required
@admin_required
def admin_dashboard():
    """
    Main Admin Dashboard view.
    Displays all interviews across the platform strictly ordered from new to old.
    """
    interview_map = {}

    # 1. Fetch from MongoDB Atlas
    if Config.is_mongo_configured():
        try:
            mongo_interviews = MongoInterview.find_by_user(user_id=None)
            for mi in mongo_interviews:
                interview_map[str(mi.id)] = mi
        except Exception as e:
            logger.error(f"[Admin] Error querying Mongo interviews: {e}")

    # 2. Fetch from SQLite fallback if available and merge
    try:
        sql_interviews = Interview.query.order_by(Interview.created_at.desc()).all()
        for si in sql_interviews:
            sid = str(si.id)
            if sid not in interview_map:
                interview_map[sid] = si
    except Exception as e:
        logger.debug(f"[Admin] SQLite interviews query skipped/empty: {e}")

    # Convert to list and sort strictly New-to-Old (created_at descending)
    all_interviews = list(interview_map.values())
    all_interviews.sort(
        key=lambda item: _parse_datetime(getattr(item, "created_at", None)),
        reverse=True
    )

    # Compute platform-wide administrative statistics
    total_count = len(all_interviews)
    completed_count = sum(
        1 for i in all_interviews
        if getattr(i, "status", "") == "completed" or getattr(i, "report", None) or getattr(i, "has_report", False)
    )
    in_progress_count = sum(
        1 for i in all_interviews
        if getattr(i, "status", "") in ("in_progress", "prepared", "awaiting_finalization")
    )

    score_values = []
    for i in all_interviews:
        rep = getattr(i, "report", None)
        if rep and getattr(rep, "overall_score", None) is not None:
            score_values.append(rep.overall_score)
        elif getattr(i, "overall_score", None) is not None:
            score_values.append(i.overall_score)

    avg_score = round(sum(score_values) / len(score_values)) if score_values else 0

    return render_template(
        "admin_dashboard.html",
        interviews=all_interviews,
        total_count=total_count,
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        avg_score=avg_score,
        InterviewStatus=InterviewStatus
    )


@admin_bp.route("/interviews/<interview_id>/delete", methods=["POST", "DELETE"])
@login_required
@admin_required
def delete_interview(interview_id: str):
    """Admin endpoint to delete an interview record from MongoDB and SQLite."""
    deleted_mongo = False
    deleted_sql = False

    # Mongo deletion
    try:
        deleted_mongo = MongoInterview.delete(interview_id)
    except Exception as e:
        logger.error(f"[Admin] Error deleting Mongo interview {interview_id}: {e}")

    # SQLite deletion
    try:
        sql_item = db.session.get(Interview, interview_id)
        if sql_item:
            db.session.delete(sql_item)
            db.session.commit()
            deleted_sql = True
    except Exception as e:
        db.session.rollback()
        logger.error(f"[Admin] Error deleting SQLite interview {interview_id}: {e}")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({
            "status": "success",
            "interview_id": interview_id,
            "deleted": deleted_mongo or deleted_sql
        })

    flash(f"Interview {interview_id} successfully deleted.", "info")
    return redirect(url_for("admin.admin_dashboard"))
