"""
MongoDB Service for AI Interview Studio.
Handles database connections, user authentication, and interview/report persistence in MongoDB Atlas.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
try:
    import pymongo
    from bson import ObjectId
    HAS_PYMONGO = True
except ImportError:
    pymongo = None
    ObjectId = None
    HAS_PYMONGO = False
from werkzeug.security import generate_password_hash, check_password_hash
from app.config import Config


_mongo_client: Optional[pymongo.MongoClient] = None


def get_mongo_client() -> Optional[Any]:
    """Get or initialize singleton MongoClient."""
    global _mongo_client
    if not HAS_PYMONGO:
        return None
    uri = Config.MONGO_URI or os.getenv("MONGO_URI", "")
    if not uri:
        return None
    if _mongo_client is None:
        try:
            _mongo_client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        except Exception as e:
            print(f"[MongoService] Connection error: {e}")
            return None
    return _mongo_client


def get_mongo_db():
    """Get active MongoDB database instance."""
    client = get_mongo_client()
    if client is None:
        return None
    db_name = Config.MONGO_DB_NAME or os.getenv("MONGO_DB_NAME")
    if db_name:
        return client[db_name]
    try:
        return client.get_default_database()
    except Exception:
        return client["signup"]


# ============================================================================
# USER AUTHENTICATION & MANAGEMENT
# ============================================================================

class MongoUser:
    """Represents an authenticated user document in MongoDB."""

    def __init__(self, data: Dict[str, Any]):
        self._id = data.get("_id")
        self.id = str(self._id) if self._id else data.get("id", "")
        self.name = data.get("name", "User")
        self.email = (data.get("email") or "").lower().strip()
        self.password = data.get("password", "")
        self.created_at = data.get("created_at") or datetime.now(timezone.utc)
        self.raw = data

    @classmethod
    def verify_password(cls, stored_password: str, candidate_password: str) -> bool:
        """Verify password supporting Werkzeug hash, bcrypt, and plaintext legacy fallbacks."""
        if not stored_password or not candidate_password:
            return False
        # Werkzeug hashes
        if stored_password.startswith(("scrypt:", "pbkdf2:", "argon2:")):
            try:
                return check_password_hash(stored_password, candidate_password)
            except Exception:
                return False
        # Direct string equality for existing test accounts in database
        return stored_password == candidate_password

    @classmethod
    def find_by_email(cls, email: str) -> Optional["MongoUser"]:
        db = get_mongo_db()
        if db is None or not email:
            return None
        doc = db.users.find_one({"email": email.lower().strip()})
        return cls(doc) if doc else None

    @classmethod
    def find_by_id(cls, user_id: str) -> Optional["MongoUser"]:
        db = get_mongo_db()
        if db is None or not user_id:
            return None
        query = {"_id": user_id}
        if ObjectId and ObjectId.is_valid(user_id):
            query = {"$or": [{"_id": ObjectId(user_id)}, {"_id": user_id}]}
        doc = db.users.find_one(query)
        return cls(doc) if doc else None

    @classmethod
    def create(cls, name: str, email: str, password: str) -> "MongoUser":
        db = get_mongo_db()
        if db is None:
            raise RuntimeError("MongoDB connection not available.")

        email_clean = email.lower().strip()
        if db.users.find_one({"email": email_clean}):
            raise ValueError(f"An account with email '{email_clean}' already exists.")

        hashed = generate_password_hash(password)
        now = datetime.now(timezone.utc)
        user_doc = {
            "name": name.strip(),
            "email": email_clean,
            "password": hashed,
            "created_at": now,
            "updated_at": now
        }
        res = db.users.insert_one(user_doc)
        user_doc["_id"] = res.inserted_id
        return cls(user_doc)


# ============================================================================
# INTERVIEW & EVALUATION REPORT DOCUMENTS
# ============================================================================

class MongoInterviewReport:
    """Structured evaluation report wrapper."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        d = data or {}
        self.id = d.get("id") or uuid.uuid4().hex
        self.interview_id = d.get("interview_id", "")
        self.overall_score = d.get("overall_score", 0)
        self.overall_summary = d.get("overall_summary", "")
        self.competency_scores = d.get("competency_scores", [])
        self.strengths = d.get("strengths", [])
        self.improvement_areas = d.get("improvement_areas", [])
        self.evidence = d.get("evidence", [])
        self.suggested_practice_questions = d.get("suggested_practice_questions", [])
        self.recommendations = d.get("recommendations", [])
        self.assessment_limitations = d.get("assessment_limitations", "")
        cat = d.get("created_at")
        if isinstance(cat, str):
            try:
                self.created_at = datetime.fromisoformat(cat.replace("Z", "+00:00"))
            except Exception:
                self.created_at = datetime.now(timezone.utc)
        elif isinstance(cat, datetime):
            self.created_at = cat
        else:
            self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
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
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at
        }


class MongoInterview:
    """Interview document model mapped to MongoDB collection."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        d = data or {}
        self.id = str(d.get("_id") or d.get("id") or uuid.uuid4().hex)
        self.user_id = d.get("user_id")
        self.candidate_name = d.get("candidate_name", "")
        self.candidate_email = d.get("candidate_email")
        self.job_title = d.get("job_title", "") or "Target Role"
        self.jd_text = d.get("jd_text", "")
        self.resume_text = d.get("resume_text", "")
        self.jd_filename = d.get("jd_filename")
        self.resume_filename = d.get("resume_filename")
        self.resume_data_base64 = d.get("resume_data_base64")
        self.resume_mimetype = d.get("resume_mimetype") or "application/pdf"
        self.duration_minutes = int(d.get("duration_minutes", 15))
        self.difficulty = d.get("difficulty", "Intermediate")
        self.language = d.get("language", "English")
        self.llm_provider = d.get("llm_provider", "openai")
        self.voice_engine = d.get("voice_engine", "elevenlabs")
        self.status = d.get("status", "draft")
        self.jd_analysis = d.get("jd_analysis")
        self.resume_analysis = d.get("resume_analysis")
        self.interview_plan = d.get("interview_plan")
        self.elevenlabs_conversation_id = d.get("elevenlabs_conversation_id")
        self.transcript = d.get("transcript") or []
        self.error_message = d.get("error_message")

        # Datetime fields
        def _parse_dt(val):
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                except Exception:
                    return None
            return val

        self.created_at = _parse_dt(d.get("created_at")) or datetime.now(timezone.utc)
        self.updated_at = _parse_dt(d.get("updated_at")) or datetime.now(timezone.utc)
        self.started_at = _parse_dt(d.get("started_at"))
        self.completed_at = _parse_dt(d.get("completed_at"))

        # Embedded Report
        rep_data = d.get("report")
        self.report = MongoInterviewReport(rep_data) if rep_data else None
        if self.report and self.status in ("awaiting_finalization", "draft", "in_progress"):
            self.status = "completed"

    def to_mongo_doc(self) -> Dict[str, Any]:
        return {
            "_id": self.id,
            "id": self.id,
            "user_id": self.user_id,
            "candidate_name": self.candidate_name,
            "candidate_email": self.candidate_email,
            "job_title": self.job_title,
            "jd_text": self.jd_text,
            "resume_text": self.resume_text,
            "jd_filename": self.jd_filename,
            "resume_filename": self.resume_filename,
            "resume_data_base64": self.resume_data_base64,
            "resume_mimetype": self.resume_mimetype,
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
            "transcript": self.transcript,
            "report": self.report.to_dict() if self.report else None,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def to_dict(self) -> Dict[str, Any]:
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
            "transcript": self.transcript,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "started_at": self.started_at.isoformat() if isinstance(self.started_at, datetime) else self.started_at,
            "completed_at": self.completed_at.isoformat() if isinstance(self.completed_at, datetime) else self.completed_at,
            "has_report": bool(self.report),
            "overall_score": self.report.overall_score if self.report else None,
            "resume_filename": self.resume_filename,
            "has_resume": bool(self.resume_data_base64 or self.resume_text),
            "report": self.report.to_dict() if self.report else None,
            "error_message": self.error_message
        }

    def save(self):
        """Upsert interview document in MongoDB collection."""
        db = get_mongo_db()
        if db is None:
            return
        if self.report and self.status in ("awaiting_finalization", "draft", "in_progress"):
            self.status = "completed"
        self.updated_at = datetime.now(timezone.utc)
        doc = self.to_mongo_doc()
        db.interviews.update_one({"_id": self.id}, {"$set": doc}, upsert=True)

    @classmethod
    def find_by_id(cls, interview_id: str) -> Optional["MongoInterview"]:
        """Find interview by ID."""
        db = get_mongo_db()
        if db is None or not interview_id:
            return None
        doc = db.interviews.find_one({"$or": [{"_id": interview_id}, {"id": interview_id}]})
        return cls(doc) if doc else None

    @classmethod
    def find_by_email(cls, email: str) -> Optional["MongoInterview"]:
        """Find an existing interview by candidate email (case-insensitive)."""
        db = get_mongo_db()
        if db is None or not email:
            return None
        import re
        clean_email = email.lower().strip()
        doc = db.interviews.find_one({
            "candidate_email": {"$regex": f"^{re.escape(clean_email)}$", "$options": "i"}
        })
        return cls(doc) if doc else None

    @classmethod
    def find_by_user(cls, user_id: Optional[str] = None) -> List["MongoInterview"]:
        """Find all interviews for a user (or all if user_id is None), ordered by created_at desc."""
        db = get_mongo_db()
        if db is None:
            return []
        query = {}
        if user_id:
            query = {"user_id": str(user_id)}
        cursor = db.interviews.find(query).sort("created_at", pymongo.DESCENDING)
        return [cls(doc) for doc in cursor]

    @classmethod
    def delete(cls, interview_id: str) -> bool:
        """Delete interview document."""
        db = get_mongo_db()
        if db is None:
            return False
        res = db.interviews.delete_one({"$or": [{"_id": interview_id}, {"id": interview_id}]})
        return res.deleted_count > 0
