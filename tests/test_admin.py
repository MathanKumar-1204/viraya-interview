import pytest
from datetime import datetime, timedelta, timezone
from app.models.interview import Interview, InterviewStatus
from app.extensions import db
from app.services.mongo_service import MongoUser, MongoInterview


def test_admin_login_success(unauth_client):
    """Test admin login with valid credentials (admin@gmail.com / admin@2004)."""
    res = unauth_client.post(
        "/login",
        data={"email": "admin@gmail.com", "password": "admin@2004"},
        follow_redirects=False
    )
    # Must redirect to /admin
    assert res.status_code == 302
    assert "/admin" in res.headers["Location"]

    # Follow redirect and verify admin dashboard loads
    follow_res = unauth_client.get(res.headers["Location"])
    assert follow_res.status_code == 200
    assert b"Admin Portal" in follow_res.data
    assert b"All Interviews (Newest to Oldest)" in follow_res.data


def test_admin_login_wrong_password(unauth_client):
    """Test admin login with wrong password fails."""
    res = unauth_client.post(
        "/login",
        data={"email": "admin@gmail.com", "password": "wrongpassword123"},
        follow_redirects=True
    )
    assert res.status_code == 200
    assert b"Invalid email or password" in res.data
    assert b"Admin Portal" not in res.data


def test_non_admin_cannot_access_admin_portal(client):
    """Regular logged in user cannot access /admin."""
    # `client` fixture is logged in as regular test user
    res = client.get("/admin", follow_redirects=False)
    # Must redirect to login
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

    follow_res = client.get("/admin", follow_redirects=True)
    assert b"Admin access restricted" in follow_res.data


def test_unauthenticated_user_cannot_access_admin_portal(unauth_client):
    """Unauthenticated visitor cannot access /admin."""
    res = unauth_client.get("/admin", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_admin_interviews_ordered_new_to_old(unauth_client, app):
    """Test that interviews on /admin are ordered strictly from newest to oldest."""
    now = datetime.now(timezone.utc)
    
    with app.app_context():
        # Clean or set up 3 test interviews with distinct created_at dates
        t1 = now - timedelta(days=5)  # Oldest
        t2 = now - timedelta(days=2)  # Middle
        t3 = now                      # Newest

        i1 = Interview(
            candidate_name="Candidate Oldest",
            job_title="AI developer",
            jd_text="Job Description 1",
            resume_text="Resume 1",
            created_at=t1,
            status=InterviewStatus.DRAFT
        )
        i2 = Interview(
            candidate_name="Candidate Middle",
            job_title="AI developer",
            jd_text="Job Description 2",
            resume_text="Resume 2",
            created_at=t2,
            status=InterviewStatus.IN_PROGRESS
        )
        i3 = Interview(
            candidate_name="Candidate Newest",
            job_title="AI developer",
            jd_text="Job Description 3",
            resume_text="Resume 3",
            created_at=t3,
            status=InterviewStatus.COMPLETED
        )
        db.session.add_all([i1, i2, i3])
        db.session.commit()

        # Log in as admin
        login_res = unauth_client.post(
            "/login",
            data={"email": "admin@gmail.com", "password": "admin@2004"},
            follow_redirects=True
        )
        assert login_res.status_code == 200

        # Fetch /admin
        admin_res = unauth_client.get("/admin")
        assert admin_res.status_code == 200

        body = admin_res.data.decode("utf-8")
        pos_newest = body.find("Candidate Newest")
        pos_middle = body.find("Candidate Middle")
        pos_oldest = body.find("Candidate Oldest")

        assert pos_newest != -1, "Candidate Newest should be found"
        assert pos_middle != -1, "Candidate Middle should be found"
        assert pos_oldest != -1, "Candidate Oldest should be found"

        # Verify ordering: Newest appears BEFORE Middle, Middle appears BEFORE Oldest
        assert pos_newest < pos_middle < pos_oldest, "Interviews must be ordered from newest to oldest"


def test_admin_delete_interview_endpoint(unauth_client, app):
    """Test that admin can delete an interview."""
    with app.app_context():
        item = Interview(
            candidate_name="Delete Candidate",
            job_title="AI developer",
            jd_text="Job Description to delete",
            resume_text="Resume to delete",
            status=InterviewStatus.DRAFT
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    # Log in as admin
    unauth_client.post(
        "/login",
        data={"email": "admin@gmail.com", "password": "admin@2004"},
        follow_redirects=True
    )

    # Delete as admin
    del_res = unauth_client.post(
        f"/admin/interviews/{item_id}/delete",
        headers={"X-Requested-With": "XMLHttpRequest"}
    )
    assert del_res.status_code == 200
    assert del_res.json.get("status") == "success"

    with app.app_context():
        assert db.session.get(Interview, item_id) is None
