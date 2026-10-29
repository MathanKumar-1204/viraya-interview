"""
OpenAI Realtime Voice Interviewer Service.
Manages low-latency, two-way speech-to-speech sessions via WebRTC and OpenAI Realtime API.
"""
import os
import requests
from typing import Dict, Any, Optional
from flask import current_app, has_app_context
from app.models.interview import Interview
from app.config import Config


class OpenAIRealtimeConfigError(Exception):
    """Raised when OpenAI API key or Realtime credentials are not configured."""
    pass


class OpenAIRealtimeAPIError(Exception):
    """Raised when OpenAI Realtime API call fails."""
    pass


class OpenAIRealtimeService:
    """Manages ephemeral session token generation and WebRTC signaling for OpenAI Realtime voice interviews."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, voice: Optional[str] = None):
        cfg_key = current_app.config.get("OPENAI_API_KEY") if has_app_context() else Config.OPENAI_API_KEY
        cfg_model = current_app.config.get("OPENAI_REALTIME_MODEL") if has_app_context() else Config.OPENAI_REALTIME_MODEL
        cfg_voice = current_app.config.get("OPENAI_REALTIME_VOICE") if has_app_context() else Config.OPENAI_REALTIME_VOICE

        self.api_key = api_key or cfg_key or (Config.LLM_API_KEY if Config.LLM_API_KEY and not Config.LLM_API_KEY.startswith("AIza") else "")
        self.model = model or cfg_model or "gpt-4o-realtime-preview-2024-12-17"
        self.voice = voice or cfg_voice or "alloy"

    def is_configured(self) -> bool:
        """Check if valid API credentials are present."""
        return bool(self.api_key and not self.api_key.startswith("your_") and not self.api_key.startswith("AIza"))

    def build_system_instruction(self, interview: Interview) -> str:
        """Construct the prompt guiding Alex during OpenAI Realtime voice interview."""
        from app.services.elevenlabs_service import build_interview_dynamic_variables
        vars_map = build_interview_dynamic_variables(interview)

        return (
            f"You are Alex, a senior, discerning, professional executive interviewer conducting a live spoken interview "
            f"with {vars_map['candidate_name']} for the {vars_map['job_title']} role.\n\n"
            f"TARGET EMPLOYER REQUIREMENTS (FROM JD):\n{vars_map['company_requirements']}\n\n"
            f"CANDIDATE RESUME PROFILE & PROJECTS:\n{vars_map['candidate_details']}\n\n"
            f"PRE-PLANNED QUESTIONS TO ASK:\n{vars_map['planned_questions']}\n\n"
            f"CRITICAL SPOKEN VOICE GUIDELINES & PERSONA:\n"
            f"1. Grounded & Objective Tone: You are a serious, analytical, and respectful professional. "
            f"NEVER be joyous, effusive, or sycophantic. Avoid empty filler praise such as 'Awesome!', 'That's fantastic!', 'I love that!'. "
            f"Acknowledge substantively ('Understood.', 'Noted.', 'That provides good context.') and probe deeper.\n"
            f"2. You are speaking aloud directly over two-way audio. Output ONLY plain, conversational English (no markdown, no bullets, no JSON).\n"
            f"3. Keep each turn short and spoken-friendly (1 to 3 sentences maximum).\n"
            f"4. Ask only ONE focused question per turn. Never overload the candidate.\n"
            f"5. If the candidate interrupts or starts answering, pause immediately.\n"
            f"6. Probe vague answers: if they say 'we built', ask 'What was your specific personal role?'. Require concrete metrics and trade-offs.\n"
            f"7. Follow the pre-planned questions adaptively, pacing the discussion across the {vars_map['interview_duration']} session."
        )

    def create_realtime_session(self, interview: Interview) -> Dict[str, Any]:
        """
        Request a short-lived ephemeral client secret from OpenAI Realtime API.
        Never exposes the master API key to the frontend client.
        """
        instructions = self.build_system_instruction(interview)

        # Testing or mock mode
        is_testing = has_app_context() and current_app.config.get("TESTING")
        cfg_provider = current_app.config.get("LLM_PROVIDER") if has_app_context() else Config.LLM_PROVIDER

        if is_testing or cfg_provider == "mock" or (self.api_key and self.api_key.startswith("mock-")):
            return {
                "client_secret": "ek_mock_realtime_secret_token_12345",
                "session_id": "sess_mock_realtime_12345",
                "model": self.model,
                "voice": self.voice,
                "candidate_name": interview.candidate_name,
                "job_title": interview.job_title,
                "instructions": instructions,
                "is_mock": True
            }

        if not self.is_configured():
            raise OpenAIRealtimeConfigError(
                "OpenAI API key is not configured. Please set OPENAI_API_KEY in your .env file."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # GA schema places voice and input settings inside the nested 'audio' configuration
        session_config = {
            "type": "realtime",
            "model": self.model,
            "instructions": instructions,
            "audio": {
                "output": {
                    "voice": self.voice
                },
                "input": {
                    "transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500
                    }
                }
            }
        }

        client_secrets_payload = {
            "expires_after": {
                "anchor": "created_at",
                "seconds": 600
            },
            "session": session_config
        }

        # Try POST /v1/realtime/client_secrets (GA endpoint), fallback to /v1/realtime/sessions
        try:
            res = requests.post(
                "https://api.openai.com/v1/realtime/client_secrets",
                headers=headers,
                json=client_secrets_payload,
                timeout=15
            )

            # Fallback 1: If audio.input nested parameters are rejected by API variant, try output voice only
            if res.status_code == 400 and ("audio.input" in res.text or "transcription" in res.text or "turn_detection" in res.text):
                res = requests.post(
                    "https://api.openai.com/v1/realtime/client_secrets",
                    headers=headers,
                    json={
                        "expires_after": {"anchor": "created_at", "seconds": 600},
                        "session": {
                            "type": "realtime",
                            "model": self.model,
                            "instructions": instructions,
                            "audio": {
                                "output": {
                                    "voice": self.voice
                                }
                            }
                        }
                    },
                    timeout=15
                )

            # Fallback 2: If endpoint returns 404 (legacy beta endpoint), fallback to /v1/realtime/sessions
            if res.status_code == 404:
                res = requests.post(
                    "https://api.openai.com/v1/realtime/sessions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "voice": self.voice,
                        "modalities": ["audio", "text"],
                        "instructions": instructions
                    },
                    timeout=15
                )

            if not res.ok:
                try:
                    err_json = res.json()
                    err_msg = err_json.get("error", {}).get("message") or str(err_json)
                except Exception:
                    err_msg = res.text
                raise OpenAIRealtimeAPIError(f"OpenAI Realtime session error ({res.status_code}): {err_msg}")

            data = res.json()
            client_secret_obj = data.get("client_secret")
            if isinstance(client_secret_obj, dict):
                ephemeral_key = client_secret_obj.get("value")
            elif isinstance(client_secret_obj, str) and client_secret_obj:
                ephemeral_key = client_secret_obj
            else:
                ephemeral_key = data.get("value")

            if not ephemeral_key:
                raise OpenAIRealtimeAPIError("OpenAI did not return a valid ephemeral client_secret in session response.")

            session_id = data.get("id")
            if not session_id and isinstance(data.get("session"), dict):
                session_id = data.get("session", {}).get("id")

            return {
                "client_secret": ephemeral_key,
                "session_id": session_id or "sess_live",
                "model": self.model,
                "voice": self.voice,
                "candidate_name": interview.candidate_name,
                "job_title": interview.job_title,
                "instructions": instructions,
                "is_mock": False
            }

        except requests.RequestException as e:
            raise OpenAIRealtimeAPIError(f"Failed to connect to OpenAI Realtime endpoint: {str(e)}")

    def relay_sdp_offer(self, sdp_offer: str, ephemeral_key: str, model: Optional[str] = None) -> str:
        """
        Proxy the SDP offer exchange to OpenAI's Realtime WebRTC endpoint.
        Used as a resilient fallback if the client cannot call OpenAI's WebRTC endpoint directly.
        """
        if not sdp_offer:
            raise ValueError("SDP offer cannot be empty.")

        if ephemeral_key.startswith("ek_mock") or Config.LLM_PROVIDER == "mock":
            return (
                "v=0\r\n"
                "o=mock 0 0 IN IP4 127.0.0.1\r\n"
                "s=MockOpenAISDPAnswer\r\n"
                "t=0 0\r\n"
                "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
                "a=rtpmap:111 opus/48000/2\r\n"
            )

        target_model = model or self.model
        headers = {
            "Authorization": f"Bearer {ephemeral_key}",
            "Content-Type": "application/sdp"
        }

        urls_to_try = [
            f"https://api.openai.com/v1/realtime/calls?model={target_model}",
            "https://api.openai.com/v1/realtime/calls",
            f"https://api.openai.com/v1/realtime?model={target_model}"
        ]

        last_error = None
        for url in urls_to_try:
            try:
                res = requests.post(url, data=sdp_offer, headers=headers, timeout=20)
                if res.ok:
                    return res.text
                last_error = f"OpenAI SDP exchange failed ({res.status_code}): {res.text}"
                if res.status_code != 404:
                    break
            except requests.RequestException as e:
                last_error = f"SDP relay request failed: {str(e)}"

        raise OpenAIRealtimeAPIError(last_error or "OpenAI SDP exchange failed.")
