import io
from app.models.interview import Interview, InterviewStatus
from unittest.mock import patch


def test_create_interview_success(client, sample_pdf_bytes):
    data = {
        "candidate_name": "Sarah Connor",
        "candidate_email": "sarah@example.com",
        "job_title": "Content Writer",
        "duration_minutes": "15",
        "difficulty": "Intermediate",
        "jd_text": "We are seeking a creative Content Writer to produce technical articles and social posts.",
        "resume_file": (io.BytesIO(sample_pdf_bytes), "sarah_resume.pdf")
    }

    response = client.post("/api/interviews", data=data, content_type="multipart/form-data")
    assert response.status_code == 201
    json_data = response.get_json()
    assert json_data["success"] is True
    assert "interview_id" in json_data


def test_create_interview_missing_resume_fails(client):
    data = {
        "candidate_name": "Sarah Connor",
        "job_title": "Content Writer",
        "jd_text": "Some JD text here"
    }
    response = client.post("/api/interviews", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "resume file" in response.get_json()["error"].lower()


def test_create_interview_missing_candidate_name_fails(client, sample_pdf_bytes):
    data = {
        "candidate_name": "",
        "resume_file": (io.BytesIO(sample_pdf_bytes), "resume.pdf")
    }
    response = client.post("/api/interviews", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "candidate name" in response.get_json()["error"].lower()


def test_create_interview_without_jd_succeeds(client, sample_pdf_bytes):
    data = {
        "candidate_name": "Maya Chen",
        "resume_file": (io.BytesIO(sample_pdf_bytes), "resume.pdf")
    }
    response = client.post("/api/interviews", data=data, content_type="multipart/form-data")
    assert response.status_code == 201
    assert response.get_json()["success"] is True


def test_prepare_interview(client, prepared_interview):
    # Test planning endpoint
    response = client.post(f"/api/interviews/{prepared_interview.id}/prepare")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["status"] == InterviewStatus.PREPARED
    assert "plan" in data
    assert "required_competencies" in data["plan"]


def test_update_job_title(client, prepared_interview):
    response = client.post(
        f"/api/interviews/{prepared_interview.id}/update-title",
        json={"job_title": "Lead Editorial Strategist"}
    )
    assert response.status_code == 200
    assert response.get_json()["job_title"] == "Lead Editorial Strategist"


def test_get_interview_context(client, prepared_interview):
    response = client.get(f"/api/interviews/{prepared_interview.id}/context")
    assert response.status_code == 200
    data = response.get_json()
    assert data["candidate_name"] == prepared_interview.candidate_name
    assert "competencies" in data


def test_conversation_credentials_security(client, prepared_interview):
    with patch("app.services.elevenlabs_service.ElevenLabsService._request_signed_url") as mock_url:
        mock_url.return_value = "wss://api.elevenlabs.io/v1/convai/conversation?signed=mock_token"

        response = client.get(f"/api/interviews/{prepared_interview.id}/conversation-credentials")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "signed_url" in data
        assert "api_key" not in data  # Never expose server API keys!


def test_invalid_interview_id_returns_404(client):
    response = client.get("/api/interviews/non-existent-uuid-12345/status")
    assert response.status_code == 404


def test_live_interview_page_renders(client, prepared_interview):
    response = client.get(f"/interviews/{prepared_interview.id}/live")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'type="module"' in html
    assert "live_interview.js" in html
    assert "audioStatusPill" in html
    assert prepared_interview.candidate_name in html


def test_interview_plan_schema_unwraps_nested_metadata():
    from app.services.interview_planner import InterviewPlanSchema
    nested_input = {
        "interview_metadata": {
            "job_title": "Senior Content Creator",
            "key_responsibilities": ["Draft articles", "Manage calendar"]
        },
        "competencies": [
            {
                "competency_name": "Audience Research",
                "weight": 50,
                "goal": "Verify search intent proficiency"
            },
            {
                "competency_name": "Brand Voice Adaptation",
                "weight": 50,
                "goal": "Verify tone adaptation across formats"
            }
        ]
    }
    plan = InterviewPlanSchema.model_validate(nested_input)
    assert plan.job_title == "Senior Content Creator"
    assert len(plan.required_competencies) == 2
    assert plan.required_competencies[0].name == "Audience Research"
    assert plan.required_competencies[0].weight == 50


def test_create_interview_with_model_selection(client, sample_pdf_bytes):
    for model in ("gemini", "openai", "claude"):
        data = {
            "candidate_name": f"Candidate {model}",
            "llm_provider": model,
            "resume_file": (io.BytesIO(sample_pdf_bytes), "resume.pdf")
        }
        res = client.post("/api/interviews", data=data, content_type="multipart/form-data")
        assert res.status_code == 201
        body = res.get_json()
        assert body["interview"]["llm_provider"] == model


def test_update_voice_engine_endpoints(client, prepared_interview):
    # Switch to gemini_live
    res1 = client.post(
        f"/api/interviews/{prepared_interview.id}/voice-engine",
        json={"voice_engine": "gemini_live"}
    )
    assert res1.status_code == 200
    assert res1.get_json()["voice_engine"] == "gemini_live"

    # Switch back to elevenlabs
    res2 = client.post(
        f"/api/interviews/{prepared_interview.id}/voice-engine",
        json={"voice_engine": "elevenlabs"}
    )
    assert res2.status_code == 200
    assert res2.get_json()["voice_engine"] == "elevenlabs"

    # Reject invalid engine
    res3 = client.post(
        f"/api/interviews/{prepared_interview.id}/voice-engine",
        json={"voice_engine": "invalid_engine"}
    )
    assert res3.status_code == 400


def test_gemini_live_flow_and_turn(client, prepared_interview):
    # Set engine to gemini_live
    client.post(
        f"/api/interviews/{prepared_interview.id}/voice-engine",
        json={"voice_engine": "gemini_live"}
    )

    with patch("app.config.Config.is_gemini_live_configured", return_value=True):
        # Credentials endpoint should return greeting
        res = client.get(f"/api/interviews/{prepared_interview.id}/conversation-credentials")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["voice_engine"] == "gemini_live"
        assert "greeting" in data
        assert "Alex" in data["greeting"]["message"]

        # Turn processing endpoint
        turn_res = client.post(
            f"/api/interviews/{prepared_interview.id}/gemini-live/turn",
            json={
                "candidate_message": "I specialize in writing high-converting SEO articles and newsletters.",
                "history": []
            }
        )
        assert turn_res.status_code == 200
        turn_data = turn_res.get_json()
        assert turn_data["success"] is True
        assert "message" in turn_data["turn"]
        assert len(turn_data["turn"]["message"]) > 5


def test_templates_render_model_and_engine_selectors(client, prepared_interview):
    # Dashboard page has dropdowns removed for production
    dash_res = client.get("/")
    assert dash_res.status_code == 200
    dash_html = dash_res.get_data(as_text=True)
    assert 'id="dashboard_llm_provider"' not in dash_html
    assert 'id="dashboard_voice_engine"' not in dash_html
    assert "Viraya Company" in dash_html or "Start Interview" in dash_html

    # Setup page has fixed role and hidden studio engines
    setup_res = client.get("/interviews/new")
    assert setup_res.status_code == 200
    setup_html = setup_res.get_data(as_text=True)
    assert 'name="llm_provider"' in setup_html
    assert 'name="voice_engine"' in setup_html
    assert 'AI developer' in setup_html

    # Preparation page displays the active configuration
    prep_res = client.get(f"/interviews/{prepared_interview.id}")
    assert prep_res.status_code == 200
    prep_html = prep_res.get_data(as_text=True)
    assert 'Interview Preparation' in prep_html



