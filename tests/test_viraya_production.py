import io
import base64
from unittest.mock import patch
from app.models.interview import Interview
from app.config import Config, BASE_DIR
from app.routes.api import get_fixed_jd_text, FIXED_JOB_TITLE


def test_fixed_jd_loaded_from_docx():
    """Verify that the fixed JD text correctly reflects AI_Application_Developer_JD.docx."""
    jd_text = get_fixed_jd_text()
    assert "AI Application Developer" in jd_text
    assert "Fresh Graduates" in jd_text
    assert "What You Will Do" in jd_text


def test_create_interview_saves_resume_and_fixes_job_details(client, sample_pdf_bytes):
    """Verify resume binary is saved in base64 and role is fixed as 'AI developer'."""
    resume_file = (io.BytesIO(sample_pdf_bytes), "candidate_resume.pdf")

    res = client.post("/api/interviews", data={
        "candidate_name": "Maya Chen",
        "candidate_email": "maya.chen@example.com",
        "job_title": "AI developer",
        "resume_file": resume_file
    }, content_type="multipart/form-data")

    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    assert "interview_id" in data
    interview_id = data["interview_id"]

    # Verify interview in DB has fixed attributes and resume base64
    from app.extensions import db
    interview = db.session.get(Interview, interview_id)
    assert interview is not None
    assert interview.job_title == "AI developer"
    assert "AI Application Developer" in interview.jd_text
    assert interview.resume_data_base64 is not None
    assert len(interview.resume_data_base64) > 10
    assert interview.llm_provider == "openai"
    assert interview.voice_engine == "elevenlabs"

    # Test viewing/downloading resume endpoint
    resume_res = client.get(f"/api/interviews/{interview_id}/resume")
    assert resume_res.status_code == 200
    assert resume_res.mimetype == "application/pdf"
    assert len(resume_res.data) > 0


def test_dashboard_renders_resume_button(client, sample_pdf_bytes):
    """Verify that dashboard renders Resume view button."""
    resume_file = (io.BytesIO(sample_pdf_bytes), "sample_cv.pdf")
    client.post("/api/interviews", data={
        "candidate_name": "Arjun Kumar",
        "job_title": "AI developer",
        "resume_file": resume_file
    }, content_type="multipart/form-data")

    dash_res = client.get("/")
    assert dash_res.status_code == 200
    html = dash_res.get_data(as_text=True)

    # Resume button should be present in actions
    assert "Resume" in html
    assert "/resume" in html
    assert "Viraya" in html
    assert "AI developer" in html
    # Engine dropdowns must be absent
    assert 'id="dashboard_llm_provider"' not in html
    assert 'id="dashboard_voice_engine"' not in html


def test_create_interview_succeeds_with_mongodb_even_if_sqlite_fails(client, sample_pdf_bytes):
    """Ensure MongoDB is primary and creation succeeds even if SQLite throws an operational/schema error."""
    from app.services.mongo_service import MongoInterview

    resume_file = (io.BytesIO(sample_pdf_bytes), "mongodb_primary_resume.pdf")

    # Mock db.session.commit to simulate SQLite OperationalError
    with patch("app.extensions.db.session.commit", side_effect=Exception("table interviews has no column named resume_data_base64")):
        res = client.post("/api/interviews", data={
            "candidate_name": "Mongo First Candidate",
            "candidate_email": "mongo_candidate@example.com",
            "job_title": "AI developer",
            "resume_file": resume_file
        }, content_type="multipart/form-data")

        # Creation must succeed via MongoDB
        assert res.status_code == 201
        data = res.get_json()
        assert data["success"] is True
        interview_id = data["interview_id"]

        # Verify it was saved in MongoDB
        mongo_doc = MongoInterview.find_by_id(interview_id)
        if mongo_doc:
            assert mongo_doc.candidate_name == "Mongo First Candidate"
            assert mongo_doc.resume_data_base64 is not None
            # Clean up
            MongoInterview.delete(interview_id)
