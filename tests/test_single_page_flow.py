import io
import pytest
from app.models.interview import Interview, InterviewStatus
from app.extensions import db
from app.services.mongo_service import MongoInterview


def test_landing_page_accessible_without_login(unauth_client):
    """Verify landing page loads directly for candidates without requiring login."""
    res = unauth_client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Viraya Company's Interview AI Bot" in html
    assert "AI developer" in html
    assert 'name="candidate_name"' in html
    assert 'name="candidate_email"' in html
    assert 'name="resume_file"' in html
    assert 'name="captcha"' in html
    assert "Start Interview" in html


def test_captcha_refresh_and_verification(unauth_client, sample_pdf_bytes):
    """Verify math captcha generation and validation."""
    # 1. Fetch fresh captcha
    res = unauth_client.get("/api/captcha/refresh")
    assert res.status_code == 200
    data = res.get_json()
    assert "question" in data
    assert "=" in data["question"]

    with unauth_client.session_transaction() as sess:
        expected_answer = sess.get("captcha_answer")

    assert expected_answer is not None

    resume_file = (io.BytesIO(sample_pdf_bytes), "test_captcha_cv.pdf")

    # 2. Submit with WRONG captcha -> 400
    fail_res = unauth_client.post("/api/interviews", data={
        "candidate_name": "Captcha Tester",
        "candidate_email": "captcha_fail@example.com",
        "job_title": "AI developer",
        "captcha": "wrong_9999",
        "resume_file": resume_file
    }, content_type="multipart/form-data")
    assert fail_res.status_code == 400
    fail_data = fail_res.get_json()
    assert "Incorrect verification answer" in fail_data["error"]

    # 3. Submit with CORRECT captcha -> 201
    resume_file_valid = (io.BytesIO(sample_pdf_bytes), "test_captcha_cv.pdf")
    ok_res = unauth_client.post("/api/interviews", data={
        "candidate_name": "Captcha Tester",
        "candidate_email": "captcha_ok@example.com",
        "job_title": "AI developer",
        "captcha": expected_answer,
        "resume_file": resume_file_valid
    }, content_type="multipart/form-data")
    assert ok_res.status_code == 201
    assert ok_res.get_json()["success"] is True


def test_one_time_email_restriction(unauth_client, sample_pdf_bytes):
    """Verify that once an email is used for an interview, it cannot be used again."""
    import uuid
    email = f"unique_applicant_{uuid.uuid4().hex[:8]}@viraya.com"

    # Step 1: Check check-email endpoint before creation
    check_before = unauth_client.get(f"/api/check-email?email={email}")
    assert check_before.status_code == 200
    assert check_before.get_json()["available"] is True

    # Step 2: First interview creation succeeds
    resume_1 = (io.BytesIO(sample_pdf_bytes), "applicant_cv.pdf")
    res1 = unauth_client.post("/api/interviews", data={
        "candidate_name": "First Attempt Applicant",
        "candidate_email": email,
        "job_title": "AI developer",
        "resume_file": resume_1
    }, content_type="multipart/form-data")
    assert res1.status_code == 201
    int_id = res1.get_json()["interview_id"]

    # Step 3: Check check-email endpoint after creation -> shows already used
    check_after = unauth_client.get(f"/api/check-email?email={email}")
    assert check_after.status_code == 200
    assert check_after.get_json()["available"] is False
    assert "already been used" in check_after.get_json()["message"]

    # Step 4: Second interview creation with the SAME email must be rejected!
    resume_2 = (io.BytesIO(sample_pdf_bytes), "applicant_cv_attempt2.pdf")
    res2 = unauth_client.post("/api/interviews", data={
        "candidate_name": "Second Attempt Applicant",
        "candidate_email": email,
        "job_title": "AI developer",
        "resume_file": resume_2
    }, content_type="multipart/form-data")

    assert res2.status_code == 400
    err_json = res2.get_json()
    assert "already been used" in err_json["error"]
    assert "Each candidate may only interview once" in err_json["error"]


def test_live_interview_page_accessible_without_login(unauth_client, sample_pdf_bytes):
    """Verify that live interview session room does not require user login."""
    resume_file = (io.BytesIO(sample_pdf_bytes), "candidate_resume.pdf")
    create_res = unauth_client.post("/api/interviews", data={
        "candidate_name": "Direct Live Candidate",
        "candidate_email": "direct_live@viraya.com",
        "job_title": "AI developer",
        "resume_file": resume_file
    }, content_type="multipart/form-data")
    assert create_res.status_code == 201
    int_id = create_res.get_json()["interview_id"]

    # Unauthenticated candidate visits live room directly
    live_res = unauth_client.get(f"/interviews/{int_id}/live")
    assert live_res.status_code == 200
    assert b"Direct Live Candidate" in live_res.data
    assert b"Viraya" in live_res.data


def test_completed_page_shows_exact_required_message_and_no_scores(unauth_client, app):
    """Verify completion page displays exact required message and does not expose scores/reports."""
    with app.app_context():
        interview = Interview(
            candidate_name="Finalized Candidate",
            candidate_email="finalized@example.com",
            job_title="AI developer",
            jd_text="AI developer JD",
            resume_text="Resume text",
            status=InterviewStatus.COMPLETED
        )
        db.session.add(interview)
        db.session.commit()
        interview_id = interview.id

    # Candidate visits /interviews/<id>/completed
    res = unauth_client.get(f"/interviews/{interview_id}/completed")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Exact required wording
    assert "Your first interview round is complete. Viraya will reach out to shortlisted candidates for the second round" in html
    assert "Finalized Candidate" in html

    # Scores and evaluations must NOT be visible
    assert "Overall Score" not in html
    assert "Competency Breakdown" not in html
    assert "Recommendations" not in html


def test_report_route_restricted_to_admin(unauth_client, app):
    """Verify /reports/<id> redirects candidates to /completed, and only admin can view it."""
    with app.app_context():
        interview = Interview(
            candidate_name="Secret Score Candidate",
            candidate_email="secret@example.com",
            job_title="AI developer",
            jd_text="AI developer JD",
            resume_text="Resume text",
            status=InterviewStatus.COMPLETED
        )
        db.session.add(interview)
        db.session.commit()
        interview_id = interview.id

    # Candidate visits /reports/<id> -> redirected to completed page
    cand_res = unauth_client.get(f"/reports/{interview_id}", follow_redirects=False)
    assert cand_res.status_code == 302
    assert f"/interviews/{interview_id}/completed" in cand_res.headers["Location"]

    # Candidate visits /reports/<id>/download -> redirected to completed page
    dl_res = unauth_client.get(f"/reports/{interview_id}/download", follow_redirects=False)
    assert dl_res.status_code == 302
    assert f"/interviews/{interview_id}/completed" in dl_res.headers["Location"]

    # Admin visits /admin/ -> allowed
    unauth_client.post("/login", data={"email": "admin@gmail.com", "password": "admin@2004"}, follow_redirects=True)
    admin_res = unauth_client.get("/admin/")
    assert admin_res.status_code == 200
    assert b"Secret Score Candidate" in admin_res.data
