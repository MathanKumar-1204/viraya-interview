import pytest
from app.models.interview import Interview
from app.services.gemini_live_service import GeminiLiveService, extract_clean_speech


def test_extract_clean_speech():
    # JSON object with "response"
    raw_json = '{\n  "response": "That\'s awesome to hear, Mathan! What specific types of content do you focus on?"\n}'
    assert extract_clean_speech(raw_json) == "That's awesome to hear, Mathan! What specific types of content do you focus on?"

    # JSON with markdown fence
    fenced_json = '```json\n{"message": "Welcome to the interview!"}\n```'
    assert extract_clean_speech(fenced_json) == "Welcome to the interview!"

    # Plain conversational speech
    plain = "Great to meet you! Could you describe your background?"
    assert extract_clean_speech(plain) == "Great to meet you! Could you describe your background?"

    # Outer quotes
    quoted = '"Welcome to the team!"'
    assert extract_clean_speech(quoted) == "Welcome to the team!"


def test_gemini_live_service_greeting_and_turn(app):
    interview = Interview(
        candidate_name="Mathan",
        job_title="Content Creator & Content Writer",
        interview_plan={
            "required_competencies": [
                {"name": "Content Strategy", "objective": "Test planning", "expected_evidence": "Calendars"}
            ]
        }
    )
    service = GeminiLiveService()
    greeting = service.get_initial_greeting(interview)
    assert greeting["role"] == "interviewer"
    assert "Content Creator & Content Writer" in greeting["message"]
    assert "Mathan" in greeting["message"]

    # Process turn with mock/gemini
    turn = service.process_turn(interview, "I have been writing articles and creating scripts for 4 years.", [])
    assert turn["role"] == "interviewer"
    assert len(turn["message"]) > 0
    # Must not contain raw json braces
    assert not turn["message"].startswith("{")
    assert '"response":' not in turn["message"]


def test_create_interview_with_custom_jd(client, sample_pdf_bytes):
    from io import BytesIO
    resume_file = (BytesIO(sample_pdf_bytes), "resume.pdf")
    
    # Post with custom jd_text and job_title
    res = client.post("/api/interviews", data={
        "candidate_name": "Test User",
        "job_title": "Senior Copywriter & SEO Lead",
        "jd_text": "Must have 5+ years writing experience, SEO keyword research, and team leadership.",
        "duration_minutes": "15",
        "difficulty": "Intermediate",
        "language": "English",
        "llm_provider": "mock",
        "voice_engine": "gemini_live",
        "resume_file": resume_file
    }, content_type="multipart/form-data")

    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    assert data["interview"]["job_title"] == "Senior Copywriter & SEO Lead"
    
    from app.extensions import db
    interview = db.session.get(Interview, data["interview_id"])
    assert interview.job_title == "Senior Copywriter & SEO Lead"
    assert "Must have 5+ years" in interview.jd_text
    assert interview.voice_engine == "gemini_live"
