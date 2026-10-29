import uuid
from datetime import datetime, timezone
from app.extensions import db


class InterviewStatus:
    DRAFT = "draft"
    PREPARED = "prepared"
    IN_PROGRESS = "in_progress"
    AWAITING_FINALIZATION = "awaiting_finalization"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"

    ALL = {DRAFT, PREPARED, IN_PROGRESS, AWAITING_FINALIZATION, COMPLETED, INTERRUPTED, FAILED}


class Interview(db.Model):
    __tablename__ = "interviews"

    id = db.Column(db.String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    candidate_name = db.Column(db.String(150), nullable=False)
    candidate_email = db.Column(db.String(150), nullable=True)
    job_title = db.Column(db.String(150), nullable=False)
    
    # Document inputs & extractions
    jd_text = db.Column(db.Text, nullable=False)
    resume_text = db.Column(db.Text, nullable=False)
    jd_filename = db.Column(db.String(255), nullable=True)
    resume_filename = db.Column(db.String(255), nullable=True)
    resume_data_base64 = db.Column(db.Text, nullable=True)
    resume_mimetype = db.Column(db.String(100), nullable=True)
    
    # Interview Configuration
    user_id = db.Column(db.String(100), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False, default=15)
    difficulty = db.Column(db.String(50), nullable=False, default="Intermediate")
    language = db.Column(db.String(50), nullable=False, default="English")
    llm_provider = db.Column(db.String(50), nullable=False, default="openai")  # Fixed to openai
    voice_engine = db.Column(db.String(50), nullable=False, default="elevenlabs")  # Fixed to elevenlabs
    
    # Status Lifecycle
    status = db.Column(db.String(30), nullable=False, default=InterviewStatus.DRAFT)
    
    # Structured Analysis & Plan
    jd_analysis = db.Column(db.JSON, nullable=True)
    resume_analysis = db.Column(db.JSON, nullable=True)
    interview_plan = db.Column(db.JSON, nullable=True)
    
    # Live Session Data
    elevenlabs_conversation_id = db.Column(db.String(100), nullable=True)
    transcript = db.Column(db.JSON, nullable=True)  # List of {role, message, timestamp}
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Error tracking (safe for display, no credentials)
    error_message = db.Column(db.Text, nullable=True)

    # Relationships
    report = db.relationship("InterviewReport", backref="interview", uselist=False, cascade="all, delete-orphan")
    events = db.relationship("InterviewEvent", backref="interview", lazy="dynamic", cascade="all, delete-orphan", order_by="InterviewEvent.created_at.asc()")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "candidate_name": self.candidate_name,
            "candidate_email": self.candidate_email,
            "job_title": self.job_title,
            "duration_minutes": self.duration_minutes,
            "difficulty": self.difficulty,
            "language": self.language,
            "llm_provider": self.llm_provider,
            "voice_engine": self.voice_engine,
            "status": self.status,
            "jd_analysis": self.jd_analysis,
            "resume_analysis": self.resume_analysis,
            "interview_plan": self.interview_plan,
            "elevenlabs_conversation_id": self.elevenlabs_conversation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "has_report": bool(self.report),
            "overall_score": self.report.overall_score if self.report else None,
            "resume_filename": self.resume_filename,
            "has_resume": bool(self.resume_data_base64 or self.resume_text),
            "error_message": self.error_message
        }


class InterviewReport(db.Model):
    __tablename__ = "interview_reports"

    id = db.Column(db.String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    interview_id = db.Column(db.String(36), db.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    overall_score = db.Column(db.Integer, nullable=False)  # 0 to 100
    overall_summary = db.Column(db.Text, nullable=False)
    
    # Detailed structured evaluation fields
    competency_scores = db.Column(db.JSON, nullable=False)  # List of competency objects
    strengths = db.Column(db.JSON, nullable=False)          # List of strength items
    improvement_areas = db.Column(db.JSON, nullable=False)  # List of areas to improve
    evidence = db.Column(db.JSON, nullable=False)           # Evidence observations
    suggested_practice_questions = db.Column(db.JSON, nullable=False)
    recommendations = db.Column(db.JSON, nullable=False)
    assessment_limitations = db.Column(db.Text, nullable=False)
    
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "interview_id": self.interview_id,
            "overall_score": self.overall_score,
            "overall_summary": self.overall_summary,
            "competency_scores": self.competency_scores,
            "strengths": self.strengths,
            "improvement_areas": self.improvement_areas,
            "evidence": self.evidence,
            "suggested_practice_questions": self.suggested_practice_questions,
            "recommendations": self.recommendations,
            "assessment_limitations": self.assessment_limitations,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class InterviewEvent(db.Model):
    __tablename__ = "interview_events"

    id = db.Column(db.String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    interview_id = db.Column(db.String(36), db.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    event_data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
