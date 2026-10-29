from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.models.interview import Interview, InterviewEvent
from app.services.elevenlabs_service import ElevenLabsService, ElevenLabsAPIError
from app.extensions import db


class TranscriptValidationError(Exception):
    """Raised when transcript is missing or insufficient for objective evaluation."""
    pass


class TranscriptService:
    """Manages transcript ingestion, sync with ElevenLabs API, and validation."""

    def __init__(self, elevenlabs_service: Optional[ElevenLabsService] = None):
        self.elevenlabs = elevenlabs_service or ElevenLabsService()

    def sync_transcript(
        self,
        interview: Interview,
        conversation_id: Optional[str] = None,
        client_transcript: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Sync transcript from ElevenLabs API or fallback to client-side reported turns.
        """
        conv_id = conversation_id or interview.elevenlabs_conversation_id
        if conv_id:
            interview.elevenlabs_conversation_id = conv_id

        fetched_transcript: List[Dict[str, Any]] = []

        # Attempt API sync if we have conversation_id and credentials
        if conv_id and self.elevenlabs.is_configured() and self.elevenlabs.api_key:
            try:
                fetched_transcript = self.elevenlabs.fetch_conversation_transcript(conv_id)
            except Exception as e:
                # Log event, fall back to client transcript
                event = InterviewEvent(
                    interview_id=interview.id,
                    event_type="transcript_fetch_warning",
                    event_data={"error": str(e), "conversation_id": conv_id}
                )
                db.session.add(event)

        # Merge or fall back
        if fetched_transcript:
            interview.transcript = fetched_transcript
        elif client_transcript:
            interview.transcript = client_transcript
        elif not interview.transcript:
            interview.transcript = []

        try:
            from app.services.mongo_service import MongoInterview
            from app.config import Config
            if isinstance(interview, MongoInterview):
                interview.save()
            else:
                db.session.commit()
                if Config.is_mongo_configured():
                    m_doc = MongoInterview.find_by_id(interview.id) or MongoInterview(interview.to_dict())
                    m_doc.transcript = interview.transcript
                    if conv_id:
                        m_doc.elevenlabs_conversation_id = conv_id
                    m_doc.save()
        except Exception as me:
            print(f"[TranscriptService] Mongo sync warning: {me}")
            db.session.commit()

        return interview.transcript or []

    @staticmethod
    def validate_transcript_for_evaluation(transcript: Optional[List[Dict[str, Any]]]) -> None:
        """
        Validate that the transcript has sufficient content to evaluate.
        Requires at least 2 distinct speech turns and some substantive candidate words.
        """
        if not transcript or not isinstance(transcript, list) or len(transcript) < 2:
            raise TranscriptValidationError(
                "Interview transcript is empty or too brief to generate an objective evaluation. "
                "At least 2 conversation exchanges are required."
            )

        candidate_words = 0
        candidate_turns = 0
        for item in transcript:
            role = item.get("role", "")
            msg = item.get("message", "")
            if role in ("candidate", "user"):
                candidate_turns += 1
                candidate_words += len(msg.split())

        if candidate_turns == 0 or candidate_words < 2:
            raise TranscriptValidationError(
                "Insufficient candidate responses recorded in the transcript. "
                "The candidate must provide at least one response to generate an evaluation."
            )

    @staticmethod
    def format_transcript_as_text(transcript: Optional[List[Dict[str, Any]]]) -> str:
        """Format list of transcript dictionaries into readable transcript text."""
        if not transcript:
            return "No transcript recorded."

        lines = []
        for turn in transcript:
            role_label = "Interviewer (AI)" if turn.get("role") in ("interviewer", "agent") else "Candidate"
            time_str = ""
            if "time_in_call_secs" in turn:
                secs = int(turn["time_in_call_secs"])
                time_str = f" [{secs // 60:02d}:{secs % 60:02d}]"
            lines.append(f"{role_label}{time_str}: {turn.get('message', '').strip()}")

        return "\n\n".join(lines)
