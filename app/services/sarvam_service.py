import os
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from flask import current_app, has_app_context
from datetime import datetime, timezone

from app.config import Config
from app.services.llm_service import LLMService, LLMExecutionError
from app.services.elevenlabs_service import build_interview_dynamic_variables
from app.models.interview import InterviewStatus
from app.services.mongo_service import MongoInterview
from app.extensions import db

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "sarvam_system_prompt.txt"


class SarvamConfigError(Exception):
    """Raised when Sarvam credentials or configuration are missing."""
    pass


class SarvamAPIError(Exception):
    """Raised when Sarvam API communication fails."""
    pass


class SarvamService:
    """
    Manages conversational voice interview flow with Sarvam AI:
    - Text-to-Speech (Bulbul model family)
    - Speech-to-Text (Saaras model family)
    - Contextual LLM turn-taking with anti-parroting & natural filler behavior
    - Real-time MongoDB persistence
    """

    BASE_URL = "https://api.sarvam.ai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        speaker: Optional[str] = None,
        tts_model: Optional[str] = None,
        stt_model: Optional[str] = None,
        language_code: Optional[str] = None,
        llm_service: Optional[LLMService] = None
    ):
        cfg_key = current_app.config.get("SARVAM_API_KEY") if has_app_context() else Config.SARVAM_API_KEY
        cfg_voice_id = current_app.config.get("SARVAM_VOICE_ID") if has_app_context() else getattr(Config, "SARVAM_VOICE_ID", "01a0e8fc-9123-73bb-bd4e-04df4741957a")
        cfg_agent_id = current_app.config.get("SARVAM_AGENT_ID") if has_app_context() else getattr(Config, "SARVAM_AGENT_ID", "interview-02c7fae8-dbd6")
        cfg_speaker = current_app.config.get("SARVAM_SPEAKER") if has_app_context() else Config.SARVAM_SPEAKER
        cfg_tts_model = current_app.config.get("SARVAM_TTS_MODEL") if has_app_context() else Config.SARVAM_TTS_MODEL
        cfg_stt_model = current_app.config.get("SARVAM_STT_MODEL") if has_app_context() else Config.SARVAM_STT_MODEL
        cfg_lang = current_app.config.get("SARVAM_LANGUAGE_CODE") if has_app_context() else Config.SARVAM_LANGUAGE_CODE

        self.api_key = api_key if api_key is not None else cfg_key
        self.voice_id = voice_id or cfg_voice_id or "01a0e8fc-9123-73bb-bd4e-04df4741957a"
        self.agent_id = agent_id or cfg_agent_id or "interview-02c7fae8-dbd6"
        self.speaker = speaker or cfg_speaker or "aditya"
        self.tts_model = tts_model or cfg_tts_model or "bulbul:v3"
        self.stt_model = stt_model or cfg_stt_model or "saaras:v4"
        self.language_code = language_code or cfg_lang or "en-IN"
        self.llm = llm_service or LLMService()

    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("your_"))

    def get_sarvam_system_prompt(self, interview: Any) -> str:
        """Construct tailored system instructions for Sarvam AI Voice Agent."""
        template = ""
        try:
            if PROMPT_FILE.exists():
                with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                    template = f.read()
        except Exception as fe:
            print(f"[SarvamService] Prompt file read warning: {fe}", flush=True)

        if not template:
            template = (
                "You are Alex, an elite, professional, and discerning executive interviewer conducting a live spoken evaluation "
                "with {{candidate_name}} for the {{job_title}} position.\n\n"
                "TARGET ROLE & CANDIDATE CONTEXT:\n"
                "- Candidate Name: {{candidate_name}}\n"
                "- Target Job Title: {{job_title}}\n"
                "- Employer & Role Requirements from JD:\n{{company_requirements}}\n"
                "- Candidate Profile & Resume:\n{{candidate_details}}\n"
                "- Pre-Planned Questions:\n{{planned_questions}}\n\n"
                "CRITICAL VOICE INTERVIEW RULES:\n"
                "1. NEVER repeat, rephrase, or parrot back what the candidate just said.\n"
                "2. Acknowledge with a brief conversational filler: 'Hmm, ok.', 'Got it.', 'Understood.', 'Makes sense.'.\n"
                "3. Ask ONE targeted, discerning follow-up question probing for individual ownership, concrete metrics, or domain technical depth.\n"
                "4. Keep your response spoken, concise, and professional (1-2 sentences max).\n"
            )

        dyn = build_interview_dynamic_variables(interview)
        prompt = template
        for k, v in dyn.items():
            prompt = prompt.replace(f"{{{{{k}}}}}", str(v))
        return prompt

    def get_initial_greeting(self, interview: Any) -> Dict[str, Any]:
        """Generate and synthesize opening greeting asking candidate to explain about their CV."""
        candidate_name = getattr(interview, "candidate_name", "Candidate")
        job_title = getattr(interview, "job_title", "the target position")
        
        greeting_text = (
            f"Hello {candidate_name}! Welcome to your interview for the {job_title} position. "
            f"I am Alex, your interviewer today. To get started, could you please explain a bit about yourself and walk me through your CV?"
        )

        audio_b64 = None
        if self.is_configured():
            try:
                audio_b64 = self.synthesize_speech(greeting_text)
            except Exception as e:
                print(f"[SarvamService] Warning: TTS synthesis failed for greeting: {e}")

        return {
            "text": greeting_text,
            "audio_base64": audio_b64,
            "speaker": self.speaker,
            "voice_id": self.voice_id,
            "agent_id": self.agent_id,
            "role": "interviewer"
        }

    def synthesize_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speaker: Optional[str] = None,
        language_code: Optional[str] = None
    ) -> str:
        """
        Call Sarvam AI Text-to-Speech REST API (Bulbul).
        Uses specified voice_id or speaker, returns base64 encoded audio string (MP3 format).
        """
        if not self.is_configured():
            raise SarvamConfigError("SARVAM_API_KEY is not configured in .env file.")

        clean_text = text.strip()
        if not clean_text:
            return ""

        url = f"{self.BASE_URL}/text-to-speech"
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }
        if self.agent_id:
            headers["x-agent-id"] = self.agent_id

        payload = {
            "text": clean_text[:2000],
            "language_code": language_code or self.language_code,
            "model": self.tts_model,
            "speech_sample_rate": 22050,
            "pace": 1.0,
            "output_audio_codec": "mp3"
        }

        target_voice = voice_id or self.voice_id
        if target_voice:
            payload["voice_id"] = target_voice
        if speaker or self.speaker:
            payload["speaker"] = speaker or self.speaker

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if not resp.ok:
                raise SarvamAPIError(f"Sarvam TTS error ({resp.status_code}): {resp.text}")

            data = resp.json()
            audios = data.get("audios") or []
            if audios and isinstance(audios, list) and len(audios) > 0:
                return audios[0]
            if "audio" in data and isinstance(data["audio"], str):
                return data["audio"]

            raise SarvamAPIError("Sarvam TTS did not return audio in response.")
        except requests.exceptions.RequestException as e:
            if isinstance(e, SarvamAPIError):
                raise
            raise SarvamAPIError(f"Connection error with Sarvam TTS API: {str(e)}")

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language_code: Optional[str] = None
    ) -> str:
        """
        Call Sarvam AI Speech-to-Text REST API (Saaras).
        Transcribes incoming audio file binary.
        """
        if not self.is_configured():
            raise SarvamConfigError("SARVAM_API_KEY is not configured in .env file.")

        url = f"{self.BASE_URL}/speech-to-text"
        headers = {
            "api-subscription-key": self.api_key
        }
        mime_type = "audio/webm" if filename.lower().endswith(".webm") else "audio/mp4" if filename.lower().endswith(".mp4") else "audio/wav"
        files = {
            "file": (filename, audio_bytes, mime_type)
        }
        data = {
            "model": self.stt_model,
            "mode": "transcribe",
            "language-code": language_code or self.language_code
        }

        try:
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=25)
            if not resp.ok:
                raise SarvamAPIError(f"Sarvam STT error ({resp.status_code}): {resp.text}")

            res_json = resp.json()
            return res_json.get("transcript", "").strip()
        except requests.exceptions.RequestException as e:
            if isinstance(e, SarvamAPIError):
                raise
            raise SarvamAPIError(f"Connection error with Sarvam STT API: {str(e)}")

    def generate_turn(
        self,
        interview: Any,
        candidate_message: str,
        time_in_call_secs: int = 0
    ) -> Dict[str, Any]:
        """
        Processes candidate input turn:
        1. Appends candidate message to interview transcript.
        2. Prompts LLM with tailored Sarvam system prompt (enforcing no repetition + natural fillers).
        3. Cleans Alex's reply.
        4. Synthesizes voice audio via Sarvam TTS.
        5. Persists entire transcript to MongoDB in real time.
        """
        candidate_text = candidate_message.strip()
        if not candidate_text:
            return {
                "response_text": "Got it. Could you expand on that?",
                "audio_base64": None,
                "transcript": interview.transcript or []
            }

        transcript = list(interview.transcript or [])
        transcript.append({
            "role": "candidate",
            "message": candidate_text,
            "time_in_call_secs": time_in_call_secs
        })

        system_prompt = self.get_sarvam_system_prompt(interview)

        # Build running dialogue context
        history_lines = []
        for turn in transcript[-10:]:
            r = "Interviewer (Alex)" if turn.get("role") in ("interviewer", "agent", "assistant") else "Candidate"
            history_lines.append(f"{r}: {turn.get('message', '')}")
        context_str = "\n".join(history_lines)

        user_prompt = (
            f"CONVERSATION HISTORY (Last turns):\n{context_str}\n\n"
            f"The candidate just said: \"{candidate_text}\"\n\n"
            "INSTRUCTIONS FOR ALEX'S NEXT TURN:\n"
            "1. NEVER repeat, rephrase, or parrot back what the candidate just said.\n"
            "2. Acknowledge naturally with a brief conversational filler if appropriate (\"Hmm, ok.\", \"Got it.\", \"Understood.\", \"Makes sense.\").\n"
            "3. Ask ONE targeted, discerning follow-up question probing for individual ownership, concrete metrics, or domain technical depth.\n"
            "4. Keep your response spoken, concise, and professional (1-2 sentences max).\n"
            "Respond ONLY with Alex's spoken words:"
        )

        try:
            alex_reply = self.llm.generate_text(system_prompt, user_prompt, max_tokens=180, temperature=0.7)
            alex_clean = self._clean_llm_speech(alex_reply)
        except Exception as e:
            print(f"[SarvamService] Turn generation notice (fallback engaged): {e}", flush=True)
            alex_clean = self._get_fallback_question(interview, candidate_text, len(transcript))

        transcript.append({
            "role": "interviewer",
            "message": alex_clean,
            "time_in_call_secs": time_in_call_secs + 2
        })
        interview.transcript = transcript

        # Synthesize audio with Sarvam TTS
        audio_b64 = None
        if self.is_configured():
            try:
                audio_b64 = self.synthesize_speech(alex_clean)
            except Exception as te:
                print(f"[SarvamService] TTS synthesis warning: {te}", flush=True)

        # Real-time MongoDB persistence
        self._persist_to_mongo(interview)

        return {
            "response_text": alex_clean,
            "audio_base64": audio_b64,
            "transcript": transcript,
            "turn_count": len(transcript)
        }

    def _get_fallback_question(self, interview: Any, candidate_message: str, turn_count: int) -> str:
        """Dynamic, context-aware fallback questions so turns never repeat the same line."""
        # 1. Pull next pre-planned question from the interview's actual generated plan
        plan = getattr(interview, "interview_plan", None) or {}
        sections = plan.get("sections", []) if isinstance(plan, dict) else []
        planned_questions = []
        for sec in sections:
            for q in sec.get("questions", []):
                q_text = q.get("question_text", "").strip()
                if q_text:
                    planned_questions.append(q_text)

        # Candidate turn index
        q_idx = max(0, (turn_count // 2) - 1)
        if planned_questions and q_idx < len(planned_questions):
            fillers = ["Got it.", "Understood.", "Makes sense.", "Hmm, ok."]
            filler = fillers[q_idx % len(fillers)]
            return f"{filler} {planned_questions[q_idx]}"

        # 2. Rotating domain questions
        rotations = [
            "Got it. Can you walk me through your personal contribution to that project?",
            "Understood. Could you share a challenging technical hurdle you faced in that work and how you resolved it?",
            "Makes sense. What measurable outcomes or key metrics did you achieve from that effort?",
            "Hmm, ok. How did you collaborate with teammates or cross-functional stakeholders on that initiative?",
            "Got it. If you were to approach that project or problem again today, what would you do differently?"
        ]
        return rotations[turn_count % len(rotations)]

    def _persist_to_mongo(self, interview: Any) -> None:
        """Helper to reliably persist transcript changes to MongoDB."""
        try:
            if isinstance(interview, MongoInterview):
                interview.save()
            else:
                db.session.commit()
                if Config.is_mongo_configured():
                    m_doc = MongoInterview.find_by_id(interview.id) or MongoInterview(interview.to_dict())
                    m_doc.transcript = interview.transcript
                    m_doc.status = interview.status
                    m_doc.save()
        except Exception as me:
            print(f"[SarvamService] Mongo sync error: {me}", flush=True)

    @staticmethod
    def _clean_llm_speech(raw: str) -> str:
        """Strip markdown, json artifacts, and prefix labels like 'Alex:'."""
        cleaned = raw.strip()

        # 1. Strip common prefixes like 'Alex:', 'Interviewer:', 'Response:'
        for prefix in ("Alex:", "Interviewer:", "AI:", "Response:"):
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()

        # 2. Remove markdown code fences if present
        if cleaned.startswith("```"):
            import re
            m = re.search(r"^```(?:json)?\s*\n?(.*?)\n?```$", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(1).strip()
            else:
                cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        # 3. Unpack JSON if returned as a JSON object
        if (cleaned.startswith("{") and cleaned.endswith("}")) or ('"response"' in cleaned or '"message"' in cleaned):
            try:
                parsed = json.loads(cleaned)
                for key in ("response", "message", "text", "speech", "content"):
                    if key in parsed and isinstance(parsed[key], str):
                        cleaned = parsed[key].strip()
                        break
            except Exception:
                pass

        # 4. Strip surrounding single or double quotes
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1].strip()

        return cleaned
