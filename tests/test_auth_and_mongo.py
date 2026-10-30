import io
import pytest
from app.services.mongo_service import MongoUser, MongoInterview, MongoInterviewReport, get_mongo_db
from app.config import Config


def test_password_verification():
    from werkzeug.security import generate_password_hash
    pw = "Secret123!"
    hashed = generate_password_hash(pw)
    assert MongoUser.verify_password(hashed, pw) is True
    assert MongoUser.verify_password(hashed, "wrongpw") is False
    # Plaintext fallback check
    assert MongoUser.verify_password("plain123", "plain123") is True
    assert MongoUser.verify_password("plain123", "other") is False


def test_signup_validation_and_flow(unauth_client):
    # Missing fields
    res = unauth_client.post("/signup", data={"name": "", "email": "", "password": "", "confirm_password": ""})
    assert res.status_code == 200
    assert b"Full name is required" in res.data

    # Mismatched passwords
    res = unauth_client.post("/signup", data={
        "name": "Jane Doe",
        "email": "jane@example.com",
        "password": "Password123",
        "confirm_password": "DifferentPassword"
    })
    assert res.status_code == 200
    assert b"Passwords do not match" in res.data

    # Short password
    res = unauth_client.post("/signup", data={
        "name": "Jane Doe",
        "email": "jane@example.com",
        "password": "123",
        "confirm_password": "123"
    })
    assert res.status_code == 200
    assert b"at least 6 characters" in res.data


def test_login_and_logout_flow(unauth_client):
    # Login page renders
    res = unauth_client.get("/login")
    assert res.status_code == 200
    assert b"Welcome Back" in res.data

    # Invalid login credentials
    res = unauth_client.post("/login", data={"email": "nonexistent_user_999@example.com", "password": "wrong"})
    assert res.status_code == 200
    assert b"Invalid email or password" in res.data


def test_unauthenticated_candidate_landing_page(unauth_client):
    # Candidate visiting / gets the single interview setup landing page without login
    res = unauth_client.get("/")
    assert res.status_code == 200
    assert b"Viraya Company" in res.data
    assert b"AI developer" in res.data

    # Unauthenticated user visiting /admin is redirected to login
    res = unauth_client.get("/admin/", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_mongo_interview_model_serialization():
    doc = {
        "id": "mock_interview_abc",
        "user_id": "usr_123",
        "candidate_name": "Sarah Connor",
        "job_title": "Content Creator",
        "duration_minutes": 15,
        "difficulty": "Intermediate",
        "language": "English",
        "llm_provider": "gemini",
        "voice_engine": "elevenlabs",
        "status": "completed",
        "transcript": [
            {"role": "interviewer", "message": "Tell me about your strategy.", "time_in_call_secs": 5},
            {"role": "candidate", "message": "I focus on audience search intent.", "time_in_call_secs": 20}
        ],
        "report": {
            "id": "rep_123",
            "overall_score": 88,
            "overall_summary": "Strong strategic communicator.",
            "competency_scores": [{"name": "Strategy", "score": 4, "weight": 50}],
            "strengths": ["Clear communication"],
            "improvement_areas": ["Analytics depth"],
            "suggested_practice_questions": ["Explain CPC"],
            "recommendations": ["Review Google Analytics 4"]
        }
    }
    interview = MongoInterview(doc)
    assert interview.id == "mock_interview_abc"
    assert interview.user_id == "usr_123"
    assert interview.report is not None
    assert interview.report.overall_score == 88
    assert len(interview.transcript) == 2

    # Check to_dict serialization
    d = interview.to_dict()
    assert d["overall_score"] == 88
    assert d["has_report"] is True
    assert len(d["transcript"]) == 2


def test_dashboard_user_isolation(client, sample_pdf_bytes):
    from io import BytesIO
    from app.extensions import db
    from app.models.interview import Interview

    # Candidate creates an interview via landing page API
    res = client.post("/api/interviews", data={
        "candidate_name": "User 1 Candidate",
        "candidate_email": "user1_unique_test@example.com",
        "job_title": "AI developer",
        "duration_minutes": "15",
        "difficulty": "Intermediate",
        "language": "English",
        "resume_file": (BytesIO(sample_pdf_bytes), "resume.pdf")
    }, content_type="multipart/form-data")
    assert res.status_code == 201
    int_id = res.get_json()["interview_id"]

    # Verify interview stored in DB
    interview = db.session.get(Interview, int_id)
    assert interview is not None
    assert interview.candidate_name == "User 1 Candidate"

    # Public landing page renders cleanly without login
    dash = client.get("/")
    assert dash.status_code == 200
    assert b"Viraya Company" in dash.data


def test_user_preferences_endpoint(client):
    res = client.post("/api/user/preferences", json={
        "llm_provider": "openai",
        "voice_engine": "gemini_live"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["llm_provider"] == "openai"
    assert data["voice_engine"] == "gemini_live"

    # Verify session has stored preferences
    with client.session_transaction() as sess:
        assert sess.get("preferred_llm_provider") == "openai"
        assert sess.get("preferred_voice_engine") == "gemini_live"

