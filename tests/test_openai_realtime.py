import pytest
from io import BytesIO
from app.models.interview import Interview, InterviewStatus
from app.services.openai_realtime_service import OpenAIRealtimeService, OpenAIRealtimeConfigError
from app.extensions import db


def test_openai_realtime_service_system_instruction():
    interview = Interview(
        candidate_name="Alex Johnson",
        job_title="Content Creator & Content Writer",
        interview_plan={
            "required_competencies": [
                {
                    "name": "Content Strategy",
                    "objective": "Test editorial calendar and audience reach",
                    "expected_evidence": "Examples of campaigns and analytics metrics"
                }
            ],
            "sections": [
                {"title": "Background & Experience", "target_duration_minutes": 3},
                {"title": "Competency Deep Dive", "target_duration_minutes": 8}
            ]
        }
    )
    service = OpenAIRealtimeService(api_key="mock-key")
    prompt = service.build_system_instruction(interview)

    assert "Alex Johnson" in prompt
    assert "Content Creator & Content Writer" in prompt
    assert "Content Strategy" in prompt
    assert "CRITICAL SPOKEN VOICE GUIDELINES" in prompt


def test_openai_realtime_service_mock_session(app):
    interview = Interview(
        candidate_name="Alex Johnson",
        job_title="Content Creator & Content Writer"
    )
    service = OpenAIRealtimeService(api_key="mock-key")
    session_data = service.create_realtime_session(interview)

    assert session_data["is_mock"] is True
    assert "client_secret" in session_data
    assert session_data["client_secret"].startswith("ek_mock")
    assert session_data["model"] == service.model
    assert session_data["voice"] == service.voice


def test_openai_realtime_service_relay(app):
    service = OpenAIRealtimeService(api_key="mock-key")
    fake_offer = "v=0\r\no=alice 2890844526 2890844526 IN IP4 127.0.0.1\r\ns=Offer\r\n"
    answer = service.relay_sdp_offer(fake_offer, "ek_mock_token")

    assert "v=0" in answer
    assert "MockOpenAISDPAnswer" in answer


def test_openai_realtime_credentials_endpoint(client, prepared_interview):
    prepared_interview.voice_engine = "openai_realtime"
    db.session.commit()

    res = client.get(f"/api/interviews/{prepared_interview.id}/conversation-credentials")
    assert res.status_code == 200
    data = res.get_json()

    assert data["success"] is True
    assert data["voice_engine"] == "openai_realtime"
    assert "client_secret" in data
    assert data["client_secret"].startswith("ek_mock")


def test_openai_realtime_relay_endpoint(client, prepared_interview):
    payload = {
        "sdp": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\n",
        "client_secret": "ek_mock_token_test",
        "model": "gpt-realtime-2.1"
    }
    res = client.post(f"/api/interviews/{prepared_interview.id}/openai-realtime/relay", json=payload)
    assert res.status_code == 200
    data = res.get_json()

    assert data["success"] is True
    assert "sdp" in data
    assert "MockOpenAISDPAnswer" in data["sdp"]


def test_dashboard_renders_openai_realtime_option(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert 'id="dashboard_voice_engine"' not in html


def test_user_preferences_accepts_openai_realtime(client):
    res = client.post("/api/user/preferences", json={
        "llm_provider": "openai",
        "voice_engine": "openai_realtime"
    })
    assert res.status_code == 200
    data = res.get_json()

    assert data["success"] is True
    assert data["voice_engine"] == "openai_realtime"


def test_create_interview_with_openai_realtime(client, sample_pdf_bytes):
    resume_file = (BytesIO(sample_pdf_bytes), "resume.pdf")

    res = client.post("/api/interviews", data={
        "candidate_name": "Taylor Swift",
        "job_title": "Lead Copywriter",
        "duration_minutes": "15",
        "difficulty": "Intermediate",
        "language": "English",
        "llm_provider": "openai",
        "voice_engine": "openai_realtime",
        "resume_file": resume_file
    }, content_type="multipart/form-data")

    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True

    created = db.session.get(Interview, data["interview_id"])
    assert created is not None
    assert created.voice_engine == "openai_realtime"
    assert created.llm_provider == "openai"


def test_openai_realtime_client_secrets_payload_includes_session_type(monkeypatch):
    import requests
    from unittest.mock import MagicMock

    interview = Interview(
        candidate_name="Jane Doe",
        job_title="Software Architect"
    )
    service = OpenAIRealtimeService(api_key="sk-live-test-key-12345")

    captured_requests = []

    def mock_post(url, headers=None, json=None, data=None, timeout=None):
        captured_requests.append({"url": url, "headers": headers, "json": json})
        resp = MagicMock()
        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {
            "value": "ek_realtime_test_token_999",
            "expires_at": 1800000000,
            "session": {
                "id": "sess_test_123",
                "type": "realtime"
            }
        }
        return resp

    monkeypatch.setattr(requests, "post", mock_post)

    session_data = service.create_realtime_session(interview)

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["url"] == "https://api.openai.com/v1/realtime/client_secrets"
    assert "session" in req["json"]
    assert req["json"]["session"]["type"] == "realtime"
    assert req["json"]["session"]["model"] == service.model
    # GA structure: voice is nested under audio.output.voice, not flat on session
    assert "voice" not in req["json"]["session"]
    assert req["json"]["session"]["audio"]["output"]["voice"] == service.voice
    assert session_data["client_secret"] == "ek_realtime_test_token_999"
    assert session_data["session_id"] == "sess_test_123"
    assert session_data["is_mock"] is False


def test_openai_realtime_client_secrets_retry_on_audio_input_rejection(monkeypatch):
    import requests
    from unittest.mock import MagicMock

    interview = Interview(
        candidate_name="Jane Doe",
        job_title="Software Architect"
    )
    service = OpenAIRealtimeService(api_key="sk-live-test-key-12345")

    captured_requests = []

    def mock_post(url, headers=None, json=None, data=None, timeout=None):
        captured_requests.append({"url": url, "json": json})
        resp = MagicMock()
        if len(captured_requests) == 1:
            resp.ok = False
            resp.status_code = 400
            resp.text = "Unknown parameter: 'session.audio.input.turn_detection'."
            resp.json.return_value = {"error": {"message": "Unknown parameter: 'session.audio.input.turn_detection'."}}
            return resp

        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {
            "value": "ek_realtime_retry_token_555",
            "session": {"id": "sess_retry_123", "type": "realtime"}
        }
        return resp

    monkeypatch.setattr(requests, "post", mock_post)

    session_data = service.create_realtime_session(interview)

    assert len(captured_requests) == 2
    retry_req = captured_requests[1]
    assert retry_req["json"]["session"]["audio"]["output"]["voice"] == service.voice
    assert "input" not in retry_req["json"]["session"]["audio"]
    assert session_data["client_secret"] == "ek_realtime_retry_token_555"
