from flask import Blueprint, render_template, abort, redirect, url_for, flash, session
from app.models.interview import Interview, InterviewStatus
from app.config import Config
from app.services.session_store import get_or_restore_interview
from app.routes.auth import login_required
from app.extensions import db

interviews_bp = Blueprint("interviews", __name__, url_prefix="/interviews")


@interviews_bp.route("/new")
@login_required
def new_interview():
    """Setup page for starting a new interview."""
    elevenlabs_ready = Config.is_elevenlabs_configured()
    llm_ready = Config.is_llm_configured()
    preferred_llm = session.get("preferred_llm_provider", Config.LLM_PROVIDER or "gemini")
    default_voice = "sarvam" if Config.is_sarvam_configured() else "gemini_live"
    preferred_voice = session.get("preferred_voice_engine", default_voice)

    return render_template(
        "interview_setup.html",
        elevenlabs_ready=elevenlabs_ready,
        sarvam_ready=Config.is_sarvam_configured(),
        llm_ready=llm_ready,
        gemini_ready=Config.is_provider_configured("gemini"),
        openai_ready=Config.is_provider_configured("openai"),
        claude_ready=Config.is_provider_configured("claude"),
        preferred_llm=preferred_llm,
        preferred_voice=preferred_voice,
        default_provider=preferred_llm
    )


@interviews_bp.route("/<interview_id>")
@login_required
def view_preparation(interview_id: str):
    """Interview preparation page showing extracted competencies, plan, and gaps."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        abort(404, description="Interview not found.")

    if interview.status == InterviewStatus.COMPLETED or interview.report or getattr(interview, "has_report", False):
        return redirect(url_for("reports.view_report", interview_id=interview.id))

    return render_template(
        "interview_preparation.html",
        interview=interview,
        plan=interview.interview_plan or {},
        elevenlabs_ready=Config.is_elevenlabs_configured(),
        sarvam_ready=Config.is_sarvam_configured(),
        gemini_live_ready=Config.is_gemini_live_configured(),
        openai_realtime_ready=Config.is_openai_realtime_configured(),
        voice_engine=interview.voice_engine,
        llm_provider=interview.llm_provider,
        InterviewStatus=InterviewStatus
    )


@interviews_bp.route("/<interview_id>/live")
@login_required
def live_interview(interview_id: str):
    """Dedicated live conversational voice interview screen."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        abort(404, description="Interview not found.")

    # Redirect completed interviews to report
    if interview.status == InterviewStatus.COMPLETED or interview.report or getattr(interview, "has_report", False):
        return redirect(url_for("reports.view_report", interview_id=interview.id))

    elevenlabs_ready = Config.is_elevenlabs_configured()
    sarvam_ready = Config.is_sarvam_configured()
    gemini_live_ready = Config.is_gemini_live_configured()
    openai_realtime_ready = Config.is_openai_realtime_configured()
    auth_mode = Config.ELEVENLABS_AUTH_MODE
    agent_id = Config.ELEVENLABS_AGENT_ID

    return render_template(
        "live_interview.html",
        interview=interview,
        elevenlabs_ready=elevenlabs_ready,
        sarvam_ready=sarvam_ready,
        gemini_live_ready=gemini_live_ready,
        openai_realtime_ready=openai_realtime_ready,
        voice_engine=interview.voice_engine,
        llm_provider=interview.llm_provider,
        auth_mode=auth_mode,
        agent_id=agent_id,
        InterviewStatus=InterviewStatus
    )


@interviews_bp.route("/<interview_id>/resume")
@login_required
def view_resume(interview_id: str):
    """View candidate resume."""
    return redirect(url_for("api.view_resume", interview_id=interview_id))

