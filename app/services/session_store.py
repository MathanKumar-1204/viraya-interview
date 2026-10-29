"""
Cross-container session recovery service for serverless hosting (e.g. Vercel).
Ensures interviews and reports survive across isolated Lambda execution environments.
"""
from typing import Optional, Tuple, Any, Union
from flask import session
from app.models.interview import Interview, InterviewReport, InterviewStatus
from app.services.mongo_service import MongoInterview, MongoInterviewReport, get_mongo_db
from app.config import Config
from app.extensions import db

DEFAULT_JOB_TITLE = "Target Role"
DEFAULT_JD = "Evaluate role-specific technical competencies, project execution, and problem-solving abilities."


def get_or_restore_interview(interview_id: str) -> Optional[Any]:
    """Retrieve interview from MongoDB, SQLite database, or restore from signed session cookie on serverless cold-starts."""
    # 1. Primary: Check MongoDB
    if Config.is_mongo_configured():
        try:
            mongo_doc = MongoInterview.find_by_id(interview_id)
            if mongo_doc:
                if mongo_doc.report and mongo_doc.status != InterviewStatus.COMPLETED:
                    mongo_doc.status = InterviewStatus.COMPLETED
                return mongo_doc
        except Exception as e:
            print(f"[SessionStore] Mongo lookup error: {e}")

    # 2. Secondary: Check SQLAlchemy (SQLite / Postgres)
    interview = db.session.get(Interview, interview_id)
    if interview:
        if interview.report and interview.status != InterviewStatus.COMPLETED:
            interview.status = InterviewStatus.COMPLETED
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        return interview

    # 3. Fallback: Restore from signed cookie session
    cached = session.get("active_interview")
    if cached and (cached.get("id") == interview_id or cached.get("interview_id") == interview_id):
        try:
            restored = Interview(
                id=interview_id,
                user_id=cached.get("user_id") or session.get("user_id"),
                candidate_name=cached.get("candidate_name", "Candidate"),
                candidate_email=cached.get("candidate_email"),
                job_title=cached.get("job_title", DEFAULT_JOB_TITLE),
                jd_text=cached.get("jd_text") or DEFAULT_JD,
                resume_text=cached.get("resume_text", ""),
                duration_minutes=int(cached.get("duration_minutes", 15)),
                difficulty=cached.get("difficulty", "Intermediate"),
                language=cached.get("language", "English"),
                llm_provider=cached.get("llm_provider", "gemini"),
                voice_engine=cached.get("voice_engine", "elevenlabs"),
                interview_plan=cached.get("interview_plan"),
                transcript=cached.get("transcript", []),
                status=cached.get("status", InterviewStatus.PREPARED)
            )
            db.session.add(restored)
            db.session.commit()

            # Save to Mongo as well if available
            if Config.is_mongo_configured():
                try:
                    m_doc = MongoInterview(restored.to_dict())
                    m_doc.save()
                    return m_doc
                except Exception:
                    pass

            return restored
        except Exception:
            db.session.rollback()

    return None


def get_or_restore_report(interview_id: str) -> Tuple[Optional[Any], Optional[Any]]:
    """Retrieve interview and its report, restoring from MongoDB or signed session if missing."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return None, None

    if interview.report:
        if interview.status != InterviewStatus.COMPLETED:
            interview.status = InterviewStatus.COMPLETED
            if isinstance(interview, MongoInterview):
                try:
                    interview.save()
                except Exception:
                    pass
            else:
                try:
                    db.session.commit()
                except Exception:
                    pass
        return interview, interview.report

    cached_rep = session.get("active_report")
    if cached_rep and cached_rep.get("interview_id") == interview_id:
        try:
            if isinstance(interview, MongoInterview):
                report_obj = MongoInterviewReport(cached_rep)
                interview.report = report_obj
                interview.save()
                return interview, report_obj

            report = InterviewReport(
                id=cached_rep.get("id"),
                interview_id=interview_id,
                overall_score=cached_rep.get("overall_score", 75),
                overall_summary=cached_rep.get("overall_summary", ""),
                competency_scores=cached_rep.get("competency_scores", []),
                strengths=cached_rep.get("strengths", []),
                improvement_areas=cached_rep.get("improvement_areas", []),
                evidence=cached_rep.get("evidence", []),
                suggested_practice_questions=cached_rep.get("suggested_practice_questions", []),
                recommendations=cached_rep.get("recommendations", []),
                assessment_limitations=cached_rep.get("assessment_limitations", "")
            )
            db.session.add(report)
            interview.status = InterviewStatus.COMPLETED
            db.session.commit()
            return interview, report
        except Exception:
            db.session.rollback()

    return interview, None
