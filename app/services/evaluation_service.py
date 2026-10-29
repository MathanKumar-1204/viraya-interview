import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from app.models.interview import Interview, InterviewReport, InterviewStatus
from app.services.llm_service import LLMService
from app.services.transcript_service import TranscriptService
from app.extensions import db

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "evaluator.txt"


class CompetencyScoreItem(BaseModel):
    id: str = Field(default="")
    name: str = Field(default="Performance Dimension")
    score: Optional[int] = Field(None, ge=0, le=100, description="Score on 0 to 100 scale, or None if Not Assessed")
    weight: int = Field(20, description="Percentage weight from the evaluation model")
    benchmark_level: Optional[str] = Field("Proficient", description="Exceptional, Proficient, Developing, or Significant Gap")
    rationale: str = Field(default="")
    supporting_quote: Optional[str] = None
    improvement_recommendation: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def handle_score_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("id"):
                data["id"] = data.get("dimension_id") or data.get("competency_id") or data.get("slug") or "dim"
            if not data.get("name"):
                data["name"] = data.get("dimension") or data.get("dimension_name") or data.get("title") or "Performance Dimension"
            if not data.get("rationale"):
                data["rationale"] = data.get("feedback") or data.get("assessment") or data.get("reasoning") or ""
            if not data.get("improvement_recommendation"):
                data["improvement_recommendation"] = data.get("recommendation") or data.get("improvement") or data.get("suggestion") or ""

            # Normalize 0-5 scores to 0-100 scale if needed
            raw_score = data.get("score")
            if raw_score is not None:
                try:
                    num_score = float(raw_score)
                    if 0 <= num_score <= 5:
                        data["score"] = int(round(num_score * 20))
                    else:
                        data["score"] = int(round(min(100, max(0, num_score))))
                except (ValueError, TypeError):
                    data["score"] = None

            # Calibrate benchmark level label
            score_val = data.get("score")
            if score_val is not None:
                if score_val >= 90:
                    data["benchmark_level"] = "Exceptional"
                elif score_val >= 75:
                    data["benchmark_level"] = "Proficient"
                elif score_val >= 60:
                    data["benchmark_level"] = "Developing"
                else:
                    data["benchmark_level"] = "Significant Gap"
            else:
                data["benchmark_level"] = "Not Assessed"

        return data


class EvaluationReportSchema(BaseModel):
    overall_summary: str = Field(default="")
    overall_score: int = Field(default=0, ge=0, le=100)
    competency_scores: List[CompetencyScoreItem] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    improvement_areas: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    suggested_practice_questions: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    assessment_limitations: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def extract_nested_report(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for wrapper in ("evaluation_report", "report", "evaluation", "assessment"):
                if wrapper in data and isinstance(data[wrapper], dict) and len(data) <= 2:
                    sub = data[wrapper]
                    data = {**sub, **{k: v for k, v in data.items() if k != wrapper}}
            if not data.get("overall_summary") and data.get("summary"):
                data["overall_summary"] = data.get("summary")
            if not data.get("overall_score") and data.get("score") is not None:
                try:
                    s = float(data.get("score"))
                    data["overall_score"] = int(round(s * 20 if s <= 5 else s))
                except Exception:
                    data["overall_score"] = 0
            if not data.get("competency_scores"):
                data["competency_scores"] = data.get("dimensions") or data.get("dimension_scores") or data.get("competencies") or []
        return data


class EvaluationService:
    """Evaluates interview transcripts against objective role dimensions using a real-time scoring algorithm."""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm = llm_service or LLMService()

    @staticmethod
    def calculate_weighted_overall_score(
        dimension_scores: List[CompetencyScoreItem],
        transcript: Optional[List[Dict[str, Any]]] = None
    ) -> int:
        """
        Calculates an empirical, calibrated overall score (0-100) from assessed dimension scores.
        Applies a calibration adjustment based on candidate turn substance.
        """
        assessed = [c for c in dimension_scores if c.score is not None]
        if not assessed:
            return 0

        total_weight = sum(c.weight for c in assessed)
        if total_weight <= 0:
            total_weight = len(assessed) * 20

        weighted_points = sum(c.score * c.weight for c in assessed)
        raw_overall = round(weighted_points / total_weight)

        # Real-time calibration: evaluate candidate spoken volume and depth
        if transcript:
            candidate_turns = [
                t for t in transcript
                if t.get("role") not in ("interviewer", "agent") and t.get("message", "").strip()
            ]
            total_words = sum(len(t.get("message", "").split()) for t in candidate_turns)
            # If the session was prematurely ended or candidate gave extremely brief answers (< 40 words total)
            if len(candidate_turns) < 2 or total_words < 40:
                raw_overall = min(raw_overall, 35)

        return max(0, min(100, raw_overall))

    def evaluate_interview(self, interview: Interview) -> InterviewReport:
        """
        Evaluate candidate performance and generate an InterviewReport.
        Idempotent: If report already exists, return it directly.
        """
        if interview.report:
            return interview.report

        # Validate transcript has sufficient substance
        TranscriptService.validate_transcript_for_evaluation(interview.transcript)

        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        transcript_text = TranscriptService.format_transcript_as_text(interview.transcript)
        job_title = interview.job_title or "Target Role"
        jd_text = (interview.jd_text or "").strip()
        if not jd_text:
            jd_text = f"Target Role: {job_title}. Core technical and operational responsibilities for {job_title}."

        try:
            user_prompt = prompt_template.format(
                candidate_name=interview.candidate_name,
                job_title=job_title,
                jd_text=jd_text[:8000],
                transcript_text=transcript_text[:12000],
                resume_text=(interview.resume_text or "")[:6000]
            )
        except (KeyError, IndexError, ValueError):
            user_prompt = prompt_template
            for placeholder, val in {
                "{candidate_name}": interview.candidate_name,
                "{job_title}": job_title,
                "{jd_text}": jd_text[:8000],
                "{transcript_text}": transcript_text[:12000],
                "{resume_text}": (interview.resume_text or "")[:6000]
            }.items():
                user_prompt = user_prompt.replace(placeholder, val)

        system_prompt = (
            f"You are a principal talent evaluation director evaluating {interview.candidate_name} for the {job_title} role. "
            "Score the five standard performance dimensions objectively based on transcript evidence, "
            "and provide actionable developmental suggestions. Return valid JSON conforming to EvaluationReportSchema."
        )

        report_data = self.llm.generate_json(system_prompt, user_prompt, EvaluationReportSchema)

        # Calculate calibrated overall score
        calculated_overall = self.calculate_weighted_overall_score(
            report_data.competency_scores,
            transcript=interview.transcript
        )
        report_data.overall_score = calculated_overall

        # Create InterviewReport model
        report = InterviewReport(
            interview_id=interview.id,
            overall_score=report_data.overall_score,
            overall_summary=report_data.overall_summary,
            competency_scores=[c.model_dump() for c in report_data.competency_scores],
            strengths=report_data.strengths,
            improvement_areas=report_data.improvement_areas,
            evidence=report_data.evidence,
            suggested_practice_questions=report_data.suggested_practice_questions,
            recommendations=report_data.recommendations,
            assessment_limitations=report_data.assessment_limitations
        )

        try:
            db.session.add(report)
            interview.status = InterviewStatus.COMPLETED
            db.session.commit()
        except Exception:
            db.session.rollback()

        # Synchronize report into MongoDB for persistent storage
        try:
            from app.services.mongo_service import MongoInterview, MongoInterviewReport
            from app.config import Config
            if isinstance(interview, MongoInterview):
                interview.report = MongoInterviewReport(report.to_dict())
                interview.status = InterviewStatus.COMPLETED
                interview.save()
            elif Config.is_mongo_configured():
                m_doc = MongoInterview.find_by_id(interview.id) or MongoInterview(interview.to_dict())
                m_doc.report = MongoInterviewReport(report.to_dict())
                m_doc.status = InterviewStatus.COMPLETED
                m_doc.save()
        except Exception as me:
            print(f"[EvaluationService] Mongo report sync error: {me}")

        return report
