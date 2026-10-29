import io
from app.models.interview import Interview, InterviewReport
from app.extensions import db
from app.services.llm_service import LLMService, LLMConfigError
from app.services.elevenlabs_service import ElevenLabsService, ElevenLabsConfigError
from werkzeug.utils import secure_filename


from unittest.mock import patch


def test_api_key_not_leaked_in_credentials_endpoint(client, prepared_interview):
    with patch("app.services.elevenlabs_service.ElevenLabsService._request_signed_url") as mock_url:
        mock_url.return_value = "wss://api.elevenlabs.io/v1/convai/conversation?signed=mock_token"
        res = client.get(f"/api/interviews/{prepared_interview.id}/conversation-credentials")
        assert res.status_code == 200
        data = res.get_json()
        assert "api_key" not in data
        assert "ELEVENLABS_API_KEY" not in str(data)


def test_path_traversal_filename_sanitization():
    malicious_filename = "../../../etc/passwd.pdf"
    sanitized = secure_filename(malicious_filename)
    assert "/" not in sanitized
    assert ".." not in sanitized
    assert sanitized.endswith(".pdf")


def test_cascade_delete_interview(client, prepared_interview):
    # Finalize first so a report exists
    client.post(f"/api/interviews/{prepared_interview.id}/finalize")
    
    interview_id = prepared_interview.id
    assert InterviewReport.query.filter_by(interview_id=interview_id).first() is not None

    # Delete interview via API
    del_res = client.delete(f"/api/interviews/{interview_id}")
    assert del_res.status_code == 200
    assert del_res.get_json()["success"] is True

    # Check both interview and report are deleted
    assert db.session.get(Interview, interview_id) is None
    assert InterviewReport.query.filter_by(interview_id=interview_id).first() is None


def test_missing_llm_credentials_error_handling():
    service = LLMService(provider="openai", api_key="")
    try:
        service._get_client()
        assert False, "Should have raised LLMConfigError"
    except LLMConfigError as e:
        assert "not configured" in str(e).lower()

    gemini_service = LLMService(provider="gemini", api_key="")
    try:
        gemini_service._call_gemini("sys", "user")
        assert False, "Should have raised LLMConfigError"
    except LLMConfigError as e:
        assert "not configured" in str(e).lower()


def test_missing_elevenlabs_credentials_error_handling():
    service = ElevenLabsService(api_key="", agent_id="", auth_mode="signed_url")
    assert not service.is_configured()
    try:
        service.get_conversation_credentials("id_123", "Candidate", "Role")
        assert False, "Should have raised ElevenLabsConfigError"
    except ElevenLabsConfigError as e:
        assert "not configured" in str(e).lower()
