import pytest
from unittest.mock import patch, MagicMock
from app.models.interview import Interview, InterviewStatus
from app.services.sarvam_service import SarvamService, SarvamConfigError, SarvamAPIError
from app.services.mongo_service import MongoInterview, MongoInterviewReport


def test_sarvam_service_prompt_generation():
    interview = Interview(
        candidate_name="Priya Sharma",
        job_title="Senior Backend Engineer",
        duration_minutes=20,
        difficulty="Advanced",
        jd_text="Enterprise Go services, PostgreSQL optimization, Kafka streaming, gRPC.",
        resume_text="Senior Engineer with 6 years experience building high-throughput microservices in Go.",
        interview_plan={
            "job_title": "Senior Backend Engineer",
            "company_requirements_summary": "High-throughput microservices using Go and Kafka.",
            "candidate_summary": "Senior Go developer with strong distributed systems background.",
            "candidate_projects": ["Scaled Kafka ingestion pipeline to 80k events/sec."],
            "candidate_studies": ["B.Tech in Computer Science from IIT Delhi"],
            "resume_skills_found": ["Go", "Kafka", "PostgreSQL", "Docker", "gRPC"],
            "sections": [
                {
                    "title": "Kafka Architecture Deep-Dive",
                    "questions": [
                        {
                            "question_text": "How do you manage consumer lag and partition rebalancing under sudden traffic spikes?"
                        }
                    ]
                }
            ]
        }
    )

    service = SarvamService(api_key="mock_key")
    prompt = service.get_sarvam_system_prompt(interview)

    assert "Priya Sharma" in prompt
    assert "Senior Backend Engineer" in prompt
    assert "Kafka" in prompt
    assert "Scaled Kafka ingestion" in prompt
    assert "IIT Delhi" in prompt
    # Verify critical behavioral prompt constraints
    assert "NO PARROTING" in prompt or "NEVER REPEAT" in prompt
    assert "Hmm, ok" in prompt or "Got it" in prompt
    assert "CV" in prompt or "cv" in prompt


def test_sarvam_initial_greeting():
    interview = Interview(
        candidate_name="Rohan Verma",
        job_title="Full Stack Engineer"
    )

    service = SarvamService(api_key="mock_key")
    greeting = service.get_initial_greeting(interview)

    assert "Rohan Verma" in greeting["text"]
    assert "Full Stack Engineer" in greeting["text"]
    # Check that it asks to explain about themselves / CV
    assert "explain a bit about yourself" in greeting["text"].lower() or "cv" in greeting["text"].lower()
    assert greeting["role"] == "interviewer"


def test_sarvam_synthesize_speech_mock():
    service = SarvamService(api_key="test_sarvam_key", speaker="meera")

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audios": ["bW9ja19tcDNfYXVkaW9fZGF0YQ=="]  # base64 for 'mock_mp3_audio_data'
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        audio_b64 = service.synthesize_speech("Hello Rohan! Welcome to your interview.")
        assert audio_b64 == "bW9ja19tcDNfYXVkaW9fZGF0YQ=="
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["api-subscription-key"] == "test_sarvam_key"
        assert kwargs["json"]["speaker"] == "meera"
        assert kwargs["json"]["output_audio_codec"] == "mp3"


def test_sarvam_generate_turn_and_mongo_persistence(prepared_interview):
    prepared_interview.voice_engine = "sarvam"
    prepared_interview.job_title = "Data Platform Architect"

    mock_llm = MagicMock()
    mock_llm.generate_text.return_value = "Got it. How did you structure the schema migration to avoid table locks?"

    service = SarvamService(api_key="test_key", llm_service=mock_llm)

    with patch.object(service, "synthesize_speech", return_value="bW9ja19hdWRpbw=="):
        result = service.generate_turn(
            prepared_interview,
            candidate_message="I designed our ClickHouse cluster handling 2 billion rows.",
            time_in_call_secs=45
        )

    assert "Got it" in result["response_text"]
    assert result["audio_base64"] == "bW9ja19hdWRpbw=="
    assert len(result["transcript"]) >= 2
    assert result["transcript"][-2]["role"] == "candidate"
    assert result["transcript"][-1]["role"] == "interviewer"
    assert "ClickHouse" in result["transcript"][-2]["message"]


def test_sarvam_credentials_endpoint(client, prepared_interview, monkeypatch):
    monkeypatch.setattr("app.config.Config.is_sarvam_configured", classmethod(lambda cls: True))
    monkeypatch.setattr("app.config.Config.SARVAM_API_KEY", "valid_sarvam_key")

    prepared_interview.voice_engine = "sarvam"
    prepared_interview.status = InterviewStatus.PREPARED

    res = client.get(f"/api/interviews/{prepared_interview.id}/conversation-credentials")
    assert res.status_code == 200
    data = res.get_json()

    assert data["success"] is True
    assert data["voice_engine"] == "sarvam"
    assert "text" in data
    assert prepared_interview.candidate_name in data["text"]


def test_sarvam_turn_api_endpoint(client, prepared_interview, monkeypatch):
    monkeypatch.setattr("app.config.Config.is_sarvam_configured", classmethod(lambda cls: True))
    monkeypatch.setattr("app.config.Config.SARVAM_API_KEY", "valid_sarvam_key")

    prepared_interview.voice_engine = "sarvam"
    prepared_interview.status = InterviewStatus.IN_PROGRESS

    with patch("app.services.sarvam_service.SarvamService.generate_turn") as mock_turn:
        mock_turn.return_value = {
            "response_text": "Understood. How did you handle partition failover?",
            "audio_base64": "bW9ja19iYXNlNjQ=",
            "transcript": [
                {"role": "candidate", "message": "I used Kafka replication."},
                {"role": "interviewer", "message": "Understood. How did you handle partition failover?"}
            ],
            "turn_count": 2
        }

        res = client.post(
            f"/api/interviews/{prepared_interview.id}/sarvam/turn",
            json={"candidate_message": "I used Kafka replication.", "time_in_call_secs": 30}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["response_text"] == "Understood. How did you handle partition failover?"
        assert data["audio_base64"] == "bW9ja19iYXNlNjQ="
