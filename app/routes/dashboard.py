from flask import Blueprint, render_template, session
from app.models.interview import Interview, InterviewStatus
from app.services.mongo_service import MongoInterview
from app.routes.auth import login_required
from app.config import Config

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    """Home / Dashboard view for the authenticated user."""
    user_id = session.get("user_id")

    # Primary: Query MongoDB interviews strictly for this authenticated user
    interviews = []
    if Config.is_mongo_configured() and user_id:
        try:
            interviews = MongoInterview.find_by_user(str(user_id))
        except Exception as e:
            print(f"[Dashboard] Error fetching from Mongo: {e}")

    # Fallback to SQLAlchemy strictly for this user's interviews
    if not interviews and user_id:
        try:
            interviews = Interview.query.filter_by(user_id=str(user_id)).order_by(Interview.created_at.desc()).all()
        except Exception:
            interviews = []
    
    # Calculate quick dashboard stats
    total_count = len(interviews)
    completed_count = sum(1 for i in interviews if i.status == InterviewStatus.COMPLETED or i.report or getattr(i, "has_report", False))
    in_progress_count = sum(1 for i in interviews if i.status == InterviewStatus.IN_PROGRESS)
    
    scores = [
        (i.report.overall_score if i.report else None) 
        for i in interviews 
        if i.report and getattr(i.report, "overall_score", None) is not None
    ]
    avg_score = round(sum(scores) / len(scores)) if scores else 0

    elevenlabs_ready = Config.is_elevenlabs_configured()
    llm_ready = Config.is_llm_configured()
    preferred_llm = session.get("preferred_llm_provider", Config.LLM_PROVIDER or "gemini")
    default_voice = "sarvam" if Config.is_sarvam_configured() else "gemini_live"
    preferred_voice = session.get("preferred_voice_engine", default_voice)

    return render_template(
        "dashboard.html",
        interviews=interviews,
        total_count=total_count,
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        avg_score=avg_score,
        elevenlabs_ready=elevenlabs_ready,
        sarvam_ready=Config.is_sarvam_configured(),
        llm_ready=llm_ready,
        gemini_ready=Config.is_provider_configured("gemini"),
        openai_ready=Config.is_provider_configured("openai"),
        claude_ready=Config.is_provider_configured("claude"),
        preferred_llm=preferred_llm,
        preferred_voice=preferred_voice,
        InterviewStatus=InterviewStatus
    )
