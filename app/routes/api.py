import io
import uuid
import base64
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, url_for, session, current_app, has_app_context, send_file
from app.models.interview import Interview, InterviewStatus, InterviewEvent
from app.services.document_parser import DocumentParserService, DocumentParsingError, ScannedDocumentError
from app.services.interview_planner import InterviewPlannerService
from app.services.elevenlabs_service import ElevenLabsService, ElevenLabsConfigError, ElevenLabsAPIError
from app.services.transcript_service import TranscriptService, TranscriptValidationError
from app.services.evaluation_service import EvaluationService
from app.services.llm_service import LLMService, LLMConfigError, LLMExecutionError
from app.services.gemini_live_service import GeminiLiveService
from app.services.session_store import get_or_restore_interview
from app.services.mongo_service import MongoInterview, MongoInterviewReport
from app.config import Config, BASE_DIR
from app.extensions import db

api_bp = Blueprint("api", __name__, url_prefix="/api")

FIXED_JOB_TITLE = "AI developer"
FIXED_JD_FILENAME = "AI_Application_Developer_JD.docx"


def get_fixed_jd_text() -> str:
    """Reads fixed Job Description from AI_Application_Developer_JD.docx."""
    jd_path = BASE_DIR / FIXED_JD_FILENAME
    if jd_path.exists():
        try:
            import docx
            doc = docx.Document(str(jd_path))
            paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            if paras:
                return "\n\n".join(paras)
        except Exception as e:
            print(f"[API] Notice reading docx JD: {e}")

    # Fallback to exact text from AI_Application_Developer_JD.docx
    return (
        "AI Application Developer\n"
        "Fresh Graduates | AI Tools & LLM-Assisted Development\n"
        "Experience: Fresh graduates / 0–1 year Employment: Full-time Location: To be specified\n\n"
        "About the Role\n"
        "We are looking for fresh graduates who have already used AI tools to build something real—an application, "
        "automation, chatbot, dashboard, website, or working prototype. You will use LLMs and AI-assisted development "
        "tools to turn business problems into usable software, test ideas quickly, and improve solutions based on feedback. "
        "Projects may include workflow automation, AI-powered analytics, and video intelligence; prior domain expertise is not required.\n\n"
        "What You Will Do\n"
        "• Build and iterate on practical AI-enabled applications, internal tools, automations, and proof-of-concepts.\n"
        "• Use tools such as ChatGPT, Claude Code, OpenAI Codex, Cursor, or similar platforms to write, debug, and improve code.\n"
        "• Connect LLMs, external APIs, databases, and existing open-source components into working workflows.\n"
        "• Translate business requirements into simple prototypes, test with real inputs, and refine for reliability and usability.\n"
        "• Create basic user interfaces, dashboards, and reports; document how the solution works and demonstrate results.\n"
        "• Explore new AI tools independently and choose the simplest effective approach for each problem.\n\n"
        "What We Are Looking For\n"
        "• A graduate in Computer Science, IT, Engineering, Data Science, or a related field—or equivalent demonstrable project skills.\n"
        "• Hands-on experience using LLMs or AI coding assistants to build at least one functioning project (academic, personal, freelance, or internship work).\n"
        "• Basic programming ability (preferably Python or JavaScript) and confidence reading, modifying, and debugging code.\n"
        "• Ability to work with APIs, follow technical documentation, search GitHub/open-source projects, and learn unfamiliar tools.\n"
        "• Strong problem-solving, ownership, curiosity, and ability to clearly explain what you built and your own contribution.\n\n"
        "Good to Have – Not Mandatory\n"
        "• Experience with LLM APIs, prompt design, RAG, agents, workflow automation, FastAPI, Streamlit, or cloud deployment.\n"
        "• Familiarity with computer vision or video intelligence tools such as YOLO, OpenCV, PyTorch, TensorFlow, object detection, tracking, or vision-language models.\n"
        "• Experience shipping an end-to-end project, integrating a database, or collecting user feedback to improve an app.\n\n"
        "How to Apply\n"
        "Send your resume along with links to 1–3 projects (GitHub, live demo, video walkthrough, or portfolio). For each project, briefly state the problem solved, the AI tools you used, what actually works, and what you personally built. Shortlisted candidates may be asked to demonstrate or extend one of their projects in a practical discussion."
    )


@api_bp.route("/captcha/refresh", methods=["GET", "POST"])
def refresh_captcha():
    """Generate a new arithmetic math captcha challenge."""
    import random
    a = random.randint(3, 18)
    b = random.randint(2, 9)
    ans = a + b
    session["captcha_answer"] = str(ans)
    session.modified = True
    return jsonify({
        "question": f"{a} + {b} = ?"
    })


@api_bp.route("/check-email", methods=["GET"])
def check_email():
    """Verify whether an email has already been used for an interview."""
    email = request.args.get("email", "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"available": False, "message": "Invalid email address."})

    is_testing = current_app.config.get("TESTING", False)
    already_used = False
    if not is_testing and Config.is_mongo_configured():
        try:
            if MongoInterview.find_by_email(email):
                already_used = True
        except Exception as me:
            print(f"[API] Error checking email in Mongo: {me}")

    if not already_used:
        try:
            from sqlalchemy import func
            if Interview.query.filter(func.lower(Interview.candidate_email) == email).first():
                already_used = True
        except Exception as se:
            print(f"[API] Error checking email in SQL: {se}")

    return jsonify({
        "email": email,
        "available": not already_used,
        "message": "This email address has already been used for an interview. Each candidate may only interview once." if already_used else "Email address is eligible for interview."
    })


@api_bp.route("/interviews", methods=["POST"])
def create_interview():
    """Create a new interview record from candidate resume and target role/job description."""
    candidate_name = request.form.get("candidate_name", "").strip()
    candidate_email = request.form.get("candidate_email", "").strip() or None
    is_testing = current_app.config.get("TESTING", False)

    # 1. Validation: Name & Email
    if not candidate_name:
        return jsonify({"error": "Candidate name is required."}), 400

    if not candidate_email:
        if is_testing:
            candidate_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        else:
            return jsonify({"error": "A valid candidate email address is required."}), 400
    elif "@" not in candidate_email:
        return jsonify({"error": "A valid candidate email address is required."}), 400

    clean_email = candidate_email.lower().strip()

    # 2. Validation: Captcha Challenge
    captcha_val = request.form.get("captcha", "").strip()
    expected_captcha = str(session.get("captcha_answer", "")).strip()

    if not is_testing or captcha_val:
        if not captcha_val or captcha_val != expected_captcha:
            return jsonify({"error": "Incorrect verification answer. Please solve the math captcha to proceed."}), 400

    # 3. Validation: One-time Email Restriction (once a mailid is used they cannot interview again)
    already_used = False
    if not is_testing and Config.is_mongo_configured():
        try:
            if MongoInterview.find_by_email(clean_email):
                already_used = True
        except Exception as me:
            print(f"[API] Error checking email in Mongo: {me}")

    if not already_used:
        try:
            from sqlalchemy import func
            if Interview.query.filter(func.lower(Interview.candidate_email) == clean_email).first():
                already_used = True
        except Exception as se:
            print(f"[API] Error checking email in SQL: {se}")

    if already_used:
        return jsonify({
            "error": "This email address has already been used for an interview. Each candidate may only interview once."
        }), 400

    # Target job title defaults to 'AI developer'
    job_title = request.form.get("job_title", "").strip() or FIXED_JOB_TITLE
    try:
        duration = int(request.form.get("duration_minutes", 15))
    except (ValueError, TypeError):
        duration = 15
    difficulty = request.form.get("difficulty", "Intermediate").strip()
    language = request.form.get("language", "English").strip()
    llm_provider = request.form.get("llm_provider", "").strip().lower() or "openai"
    voice_engine = request.form.get("voice_engine", "").strip().lower() or "elevenlabs"

    resume_file = request.files.get("resume_file")
    if not resume_file or not resume_file.filename:
        return jsonify({"error": "Candidate resume file (PDF or DOCX) is required."}), 400

    # Validate file format and size
    valid_res, err_res = DocumentParserService.validate_file(resume_file)
    if not valid_res:
        return jsonify({"error": f"Resume file error: {err_res}"}), 400

    # Read binary bytes for MongoDB storage
    resume_bytes = resume_file.read()
    resume_file.seek(0)
    resume_data_base64 = base64.b64encode(resume_bytes).decode("utf-8") if resume_bytes else None
    resume_mimetype = resume_file.mimetype or "application/pdf"

    # Extract text from resume
    try:
        resume_text = DocumentParserService.extract_text(resume_file)
    except ScannedDocumentError as sde:
        return jsonify({"error": f"Resume error: {str(sde)}"}), 422
    except DocumentParsingError as dpe:
        return jsonify({"error": f"Resume extraction error: {str(dpe)}"}), 422

    # Job description: Fixed from AI_Application_Developer_JD.docx unless custom passed
    custom_jd = request.form.get("jd_text", "").strip()
    jd_file = request.files.get("jd_file")
    if jd_file and jd_file.filename:
        try:
            jd_text = DocumentParserService.extract_text(jd_file)
            jd_filename = jd_file.filename
        except Exception:
            jd_text = get_fixed_jd_text()
            jd_filename = FIXED_JD_FILENAME
    elif custom_jd:
        jd_text = custom_jd
        jd_filename = FIXED_JD_FILENAME
    else:
        jd_text = get_fixed_jd_text()
        jd_filename = FIXED_JD_FILENAME

    # Clear used captcha to prevent replay
    session.pop("captcha_answer", None)

    user_id = session.get("user_id")
    user_id_str = str(user_id) if user_id else None
    interview_id = uuid.uuid4().hex

    mongo_saved = False
    # 1. Primary: Save directly into MongoDB Atlas
    if Config.is_mongo_configured():
        try:
            mongo_doc = MongoInterview({
                "id": interview_id,
                "_id": interview_id,
                "user_id": user_id_str,
                "candidate_name": candidate_name,
                "candidate_email": candidate_email,
                "job_title": job_title,
                "jd_text": jd_text,
                "resume_text": resume_text,
                "jd_filename": jd_filename,
                "resume_filename": resume_file.filename,
                "resume_data_base64": resume_data_base64,
                "resume_mimetype": resume_mimetype,
                "duration_minutes": duration,
                "difficulty": difficulty,
                "language": language,
                "llm_provider": llm_provider,
                "voice_engine": voice_engine,
                "status": "draft",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            })
            mongo_doc.save()
            mongo_saved = True
        except Exception as me:
            print(f"[API] Notice saving interview to MongoDB: {me}")

    # 2. Secondary / Local Fallback: SQLite
    sql_saved = False
    try:
        interview = Interview(
            id=interview_id,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            user_id=user_id_str,
            job_title=job_title,
            jd_text=jd_text,
            resume_text=resume_text,
            jd_filename=jd_filename,
            resume_filename=resume_file.filename,
            resume_data_base64=resume_data_base64,
            resume_mimetype=resume_mimetype,
            duration_minutes=duration,
            difficulty=difficulty,
            language=language,
            llm_provider=llm_provider,
            voice_engine=voice_engine,
            status=InterviewStatus.DRAFT
        )
        db.session.add(interview)
        db.session.commit()
        sql_saved = True

        # Log creation event
        event = InterviewEvent(
            interview_id=interview_id,
            event_type="interview_created",
            event_data={"candidate_name": candidate_name, "job_title": job_title, "llm_provider": llm_provider, "voice_engine": voice_engine}
        )
        db.session.add(event)
        db.session.commit()
    except Exception as se:
        db.session.rollback()
        print(f"[API] SQLite synchronization notice (MongoDB primary: {mongo_saved}): {se}")

    if not mongo_saved and not sql_saved:
        return jsonify({"error": "Failed to create interview in MongoDB or local database."}), 500

    session["active_interview"] = {
        "id": interview_id,
        "interview_id": interview_id,
        "user_id": user_id,
        "candidate_name": candidate_name,
        "candidate_email": candidate_email,
        "job_title": job_title,
        "duration_minutes": duration,
        "difficulty": difficulty,
        "language": language,
        "llm_provider": llm_provider,
        "voice_engine": voice_engine,
        "status": "draft"
    }
    session.modified = True

    return jsonify({
        "success": True,
        "interview_id": interview_id,
        "interview": session["active_interview"],
        "live_url": url_for("interviews.live_interview", interview_id=interview_id),
        "redirect_url": url_for("interviews.view_preparation", interview_id=interview_id)
    }), 201


@api_bp.route("/interviews/<interview_id>/prepare", methods=["POST"])
def prepare_interview(interview_id: str):
    """Generate structured interview plan from JD and Resume using the LLM."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    # Allow re-planning if in draft or prepared using selected LLM provider
    planner = InterviewPlannerService(llm_service=LLMService(provider=interview.llm_provider))
    try:
        plan_schema = planner.generate_plan(
            candidate_name=interview.candidate_name,
            job_title=interview.job_title,
            jd_text=interview.jd_text,
            resume_text=interview.resume_text,
            duration_minutes=interview.duration_minutes,
            difficulty=interview.difficulty,
            language=interview.language
        )

        plan_dict = plan_schema.model_dump()
        new_title = (plan_dict.get("job_title") or "").strip()
        if new_title:
            interview.job_title = new_title
        else:
            plan_dict["job_title"] = interview.job_title
        interview.interview_plan = plan_dict
        interview.status = InterviewStatus.PREPARED
        interview.error_message = None

        if isinstance(interview, MongoInterview):
            interview.save()
        else:
            db.session.commit()
            if Config.is_mongo_configured():
                try:
                    m_doc = MongoInterview.find_by_id(interview.id) or MongoInterview(interview.to_dict())
                    m_doc.interview_plan = plan_dict
                    m_doc.job_title = interview.job_title
                    m_doc.status = interview.status
                    m_doc.save()
                except Exception:
                    pass

        event = InterviewEvent(
            interview_id=interview.id,
            event_type="plan_generated",
            event_data={"competencies_count": len(plan_dict.get("required_competencies", []))}
        )
        db.session.add(event)
        db.session.commit()

        session["active_interview"] = {
            "id": interview.id,
            "interview_id": interview.id,
            "candidate_name": interview.candidate_name,
            "candidate_email": interview.candidate_email,
            "job_title": interview.job_title,
            "duration_minutes": interview.duration_minutes,
            "difficulty": interview.difficulty,
            "language": interview.language,
            "llm_provider": interview.llm_provider,
            "voice_engine": interview.voice_engine,
            "interview_plan": plan_dict,
            "status": interview.status
        }
        session.modified = True

        return jsonify({
            "success": True,
            "status": interview.status,
            "plan": plan_dict,
            "interview": session["active_interview"]
        })

    except LLMConfigError as lce:
        interview.error_message = str(lce)
        db.session.commit()
        return jsonify({"error": str(lce)}), 503
    except (LLMExecutionError, Exception) as ee:
        interview.error_message = f"Interview planning failed: {str(ee)}"
        db.session.commit()
        return jsonify({"error": f"Planning failed: {str(ee)}"}), 500


@api_bp.route("/interviews/<interview_id>/resume", methods=["GET"])
def view_resume(interview_id: str):
    """View candidate resume saved in MongoDB or database."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    b64_data = getattr(interview, "resume_data_base64", None)
    mimetype = getattr(interview, "resume_mimetype", None) or "application/pdf"
    filename = getattr(interview, "resume_filename", None) or f"{interview.candidate_name}_Resume.pdf"

    if not b64_data and Config.is_mongo_configured():
        try:
            m_doc = MongoInterview.find_by_id(interview_id)
            if m_doc and getattr(m_doc, "resume_data_base64", None):
                b64_data = m_doc.resume_data_base64
                mimetype = getattr(m_doc, "resume_mimetype", None) or mimetype
                filename = getattr(m_doc, "resume_filename", None) or filename
        except Exception as e:
            print(f"[API] Error loading resume from Mongo: {e}")

    if b64_data:
        try:
            file_bytes = base64.b64decode(b64_data)
            return send_file(
                io.BytesIO(file_bytes),
                mimetype=mimetype,
                as_attachment=False,
                download_name=filename
            )
        except Exception as de:
            print(f"[API] Error decoding resume b64: {de}")

    resume_text = getattr(interview, "resume_text", "")
    if resume_text:
        return send_file(
            io.BytesIO(resume_text.encode("utf-8")),
            mimetype="text/plain; charset=utf-8",
            as_attachment=False,
            download_name=f"{interview.candidate_name}_Resume.txt"
        )

    return jsonify({"error": "Resume file not found for this interview."}), 404


@api_bp.route("/interviews/<interview_id>/update-title", methods=["POST"])
def update_job_title(interview_id: str):
    """Update job title during preparation."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    new_title = request.json.get("job_title", "").strip() if request.is_json else request.form.get("job_title", "").strip()
    if not new_title:
        return jsonify({"error": "Job title cannot be empty."}), 400

    interview.job_title = new_title
    if interview.interview_plan:
        plan = dict(interview.interview_plan)
        plan["job_title"] = new_title
        interview.interview_plan = plan

    if isinstance(interview, MongoInterview):
        interview.save()
    else:
        db.session.commit()
        if Config.is_mongo_configured():
            try:
                m_doc = MongoInterview.find_by_id(interview.id)
                if m_doc:
                    m_doc.job_title = new_title
                    m_doc.interview_plan = interview.interview_plan
                    m_doc.save()
            except Exception:
                pass

    if "active_interview" in session and session["active_interview"].get("id") == interview.id:
        session["active_interview"]["job_title"] = new_title
        session.modified = True

    return jsonify({"success": True, "job_title": interview.job_title})


@api_bp.route("/interviews/<interview_id>/voice-engine", methods=["POST"])
def update_voice_engine(interview_id: str):
    """Update selected live voice interview engine ('elevenlabs' or 'gemini_live')."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    data = request.get_json(silent=True) or {}
    engine = data.get("voice_engine", "").strip().lower()
    if engine not in ("elevenlabs", "gemini_live", "openai_realtime", "sarvam"):
        return jsonify({"error": "Invalid voice engine. Must be 'elevenlabs', 'gemini_live', 'openai_realtime', or 'sarvam'."}), 400

    interview.voice_engine = engine
    if isinstance(interview, MongoInterview):
        interview.save()
    else:
        db.session.commit()
        if Config.is_mongo_configured():
            try:
                m_doc = MongoInterview.find_by_id(interview.id)
                if m_doc:
                    m_doc.voice_engine = engine
                    m_doc.save()
            except Exception:
                pass

    if "active_interview" in session and session["active_interview"].get("id") == interview.id:
        session["active_interview"]["voice_engine"] = engine
        session.modified = True

    return jsonify({"success": True, "voice_engine": interview.voice_engine})


@api_bp.route("/user/preferences", methods=["POST"])
def update_user_preferences():
    """Save user preferred LLM provider and voice engine chosen from the dashboard dropdowns."""
    data = request.get_json(silent=True) or {}
    llm = data.get("llm_provider", "").strip().lower()
    voice = data.get("voice_engine", "").strip().lower()

    if llm in ("gemini", "openai", "claude", "mock"):
        session["preferred_llm_provider"] = llm
    if voice in ("gemini_live", "elevenlabs", "openai_realtime", "sarvam"):
        session["preferred_voice_engine"] = voice
    session.modified = True

    return jsonify({
        "success": True,
        "llm_provider": session.get("preferred_llm_provider", "gemini"),
        "voice_engine": session.get("preferred_voice_engine", "gemini_live")
    })


@api_bp.route("/interviews/<interview_id>/conversation-credentials", methods=["GET"])
def get_conversation_credentials(interview_id: str):
    """
    Secure endpoint providing credentials for ElevenLabs or Gemini Flash Live.
    Never returns private API keys to the client.
    """
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    if interview.status not in (InterviewStatus.PREPARED, InterviewStatus.IN_PROGRESS):
        return jsonify({
            "error": f"Interview is in '{interview.status}' status and cannot be started. Please prepare the interview first."
        }), 400

    # Gemini Flash Live engine branch
    if interview.voice_engine == "gemini_live":
        if not Config.is_gemini_live_configured():
            return jsonify({
                "error": "Gemini Live Voice is not configured. Please ensure GEMINI_API_KEY is configured in your .env file."
            }), 503

        try:
            live_service = GeminiLiveService()
            greeting = live_service.get_initial_greeting(interview)

            if interview.status != InterviewStatus.IN_PROGRESS:
                interview.status = InterviewStatus.IN_PROGRESS
                interview.started_at = datetime.now(timezone.utc)
                db.session.commit()

            return jsonify({
                "success": True,
                "voice_engine": "gemini_live",
                "candidate_name": interview.candidate_name,
                "job_title": interview.job_title,
                "greeting": greeting
            })
        except Exception as e:
            return jsonify({"error": f"Failed to initialize Gemini Live session: {str(e)}"}), 500

    # OpenAI Realtime Voice engine branch (WebRTC)
    if interview.voice_engine == "openai_realtime":
        if not Config.is_openai_realtime_configured():
            return jsonify({
                "error": "OpenAI Realtime Voice is not configured. Please ensure OPENAI_API_KEY is set in your .env file."
            }), 503

        try:
            from app.services.openai_realtime_service import (
                OpenAIRealtimeService,
                OpenAIRealtimeConfigError,
                OpenAIRealtimeAPIError
            )
            realtime_service = OpenAIRealtimeService()
            session_data = realtime_service.create_realtime_session(interview)

            if interview.status != InterviewStatus.IN_PROGRESS:
                interview.status = InterviewStatus.IN_PROGRESS
                interview.started_at = datetime.now(timezone.utc)
                db.session.commit()

            return jsonify({
                "success": True,
                "voice_engine": "openai_realtime",
                **session_data
            })
        except OpenAIRealtimeConfigError as rce:
            return jsonify({"error": str(rce)}), 503
        except OpenAIRealtimeAPIError as rae:
            return jsonify({"error": f"OpenAI Realtime session error: {str(rae)}"}), 502
        except Exception as e:
            return jsonify({"error": f"Failed to initialize OpenAI Realtime session: {str(e)}"}), 500

    # Sarvam AI Voice engine branch
    if interview.voice_engine == "sarvam":
        if not Config.is_sarvam_configured():
            return jsonify({
                "error": "Sarvam AI Voice is not configured. Please ensure SARVAM_API_KEY is configured in your .env file."
            }), 503

        try:
            from app.services.sarvam_service import SarvamService
            sarvam_svc = SarvamService(llm_service=LLMService(provider=interview.llm_provider))
            greeting_data = sarvam_svc.get_initial_greeting(interview)

            if interview.status != InterviewStatus.IN_PROGRESS:
                interview.status = InterviewStatus.IN_PROGRESS
                interview.started_at = datetime.now(timezone.utc)
                if isinstance(interview, MongoInterview):
                    interview.save()
                else:
                    db.session.commit()
                    if Config.is_mongo_configured():
                        try:
                            m_doc = MongoInterview.find_by_id(interview.id) or MongoInterview(interview.to_dict())
                            m_doc.status = interview.status
                            m_doc.started_at = interview.started_at
                            m_doc.save()
                        except Exception:
                            pass

            return jsonify({
                "success": True,
                "voice_engine": "sarvam",
                "candidate_name": interview.candidate_name,
                "job_title": interview.job_title,
                **greeting_data
            })
        except Exception as e:
            return jsonify({"error": f"Failed to initialize Sarvam AI session: {str(e)}"}), 500

    # ElevenLabs engine branch
    from app.services.elevenlabs_service import ElevenLabsService, build_interview_dynamic_variables
    service = ElevenLabsService()
    try:
        dynamic_vars = build_interview_dynamic_variables(interview)
        credentials = service.get_conversation_credentials(
            interview_id=interview.id,
            candidate_name=interview.candidate_name,
            job_title=interview.job_title,
            dynamic_variables=dynamic_vars
        )

        # Mark interview in progress and set started_at if not set
        if interview.status != InterviewStatus.IN_PROGRESS:
            interview.status = InterviewStatus.IN_PROGRESS
            interview.started_at = datetime.now(timezone.utc)
            if isinstance(interview, MongoInterview):
                interview.save()
            else:
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                if Config.is_mongo_configured():
                    try:
                        m_doc = MongoInterview.find_by_id(interview.id) or MongoInterview(interview.to_dict())
                        m_doc.status = interview.status
                        m_doc.started_at = interview.started_at
                        m_doc.save()
                    except Exception:
                        pass

        return jsonify({"success": True, "voice_engine": "elevenlabs", **credentials})

    except ElevenLabsConfigError as ece:
        return jsonify({"error": str(ece)}), 503
    except ElevenLabsAPIError as eae:
        return jsonify({"error": f"ElevenLabs connection failure: {str(eae)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Failed to initialize conversation: {str(e)}"}), 500


@api_bp.route("/interviews/<interview_id>/gemini-live/turn", methods=["POST"])
def gemini_live_turn(interview_id: str):
    """Processes candidate spoken turn and returns Alex's conversational spoken response using Gemini."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    data = request.get_json(silent=True) or {}
    candidate_message = data.get("candidate_message", "").strip()
    history = data.get("history", [])

    if not candidate_message:
        return jsonify({"error": "Candidate message is required."}), 400

    print(f"[GeminiLive] Processing candidate turn for interview {interview_id}: '{candidate_message}'")
    service = GeminiLiveService()
    reply = service.process_turn(interview, candidate_message, history)
    print(f"[GeminiLive] Alex response: '{reply.get('message', '')}'")
    return jsonify({"success": True, "turn": reply})


@api_bp.route("/interviews/<interview_id>/openai-realtime/relay", methods=["POST"])
def openai_realtime_relay(interview_id: str):
    """
    Relay the WebRTC SDP offer to OpenAI's Realtime endpoint and return the answer SDP.
    Provides a fallback if direct client-side fetch to OpenAI encounters CORS or network obstacles.
    """
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    data = request.get_json(silent=True) or {}
    sdp_offer = data.get("sdp", "").strip()
    ephemeral_key = data.get("client_secret", "").strip()
    model = data.get("model")

    if not sdp_offer:
        return jsonify({"error": "SDP offer is required."}), 400

    try:
        from app.services.openai_realtime_service import OpenAIRealtimeService
        service = OpenAIRealtimeService()
        answer_sdp = service.relay_sdp_offer(sdp_offer, ephemeral_key, model=model)
        return jsonify({"success": True, "sdp": answer_sdp})
    except Exception as e:
        return jsonify({"error": f"SDP relay failed: {str(e)}"}), 502


@api_bp.route("/interviews/<interview_id>/sarvam/turn", methods=["POST"])
def sarvam_turn(interview_id: str):
    """
    Processes candidate spoken turn for Sarvam AI Voice Engine:
    Accepts JSON text payload or multipart audio upload file (transcribed via Sarvam Saaras STT).
    Generates Alex's reply using the Sarvam prompt (no parroting, natural fillers),
    synthesizes speech audio via Sarvam Bulbul TTS, and saves the turns to MongoDB.
    """
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    from app.services.sarvam_service import SarvamService
    sarvam_svc = SarvamService(llm_service=LLMService(provider=interview.llm_provider))

    candidate_text = ""
    time_in_call = 0

    if request.is_json:
        data = request.get_json() or {}
        candidate_text = data.get("candidate_message", "").strip()
        time_in_call = int(data.get("time_in_call_secs", 0))
    elif "audio" in request.files or "file" in request.files:
        audio_file = request.files.get("audio") or request.files.get("file")
        time_in_call = int(request.form.get("time_in_call_secs", 0))
        if audio_file:
            audio_bytes = audio_file.read()
            if audio_bytes and sarvam_svc.is_configured():
                try:
                    candidate_text = sarvam_svc.transcribe_audio(audio_bytes, filename=audio_file.filename or "audio.wav")
                except Exception as te:
                    print(f"[SarvamTurn] STT error: {te}")
    else:
        candidate_text = request.form.get("candidate_message", "").strip()
        time_in_call = int(request.form.get("time_in_call_secs", 0))

    if not candidate_text:
        if "audio" in request.files or "file" in request.files:
            return jsonify({
                "success": False,
                "no_speech": True,
                "message": "No speech detected in audio clip."
            }), 200
        return jsonify({"error": "Candidate message or audio is required."}), 400

    try:
        result = sarvam_svc.generate_turn(interview, candidate_text, time_in_call_secs=time_in_call)
        return jsonify({
            "success": True,
            "candidate_message": candidate_text,
            **result
        })
    except Exception as e:
        return jsonify({"error": f"Failed to generate Sarvam voice turn: {str(e)}"}), 500


@api_bp.route("/interviews/<interview_id>/sarvam/tts", methods=["POST"])
def sarvam_tts(interview_id: str):
    """Synthesize custom speech text to audio using Sarvam TTS (Bulbul)."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Text is required."}), 400

    from app.services.sarvam_service import SarvamService
    sarvam_svc = SarvamService()
    try:
        audio_b64 = sarvam_svc.synthesize_speech(text)
        return jsonify({"success": True, "audio_base64": audio_b64})
    except Exception as e:
        return jsonify({"error": f"TTS synthesis failed: {str(e)}"}), 500


@api_bp.route("/interviews/<interview_id>/context", methods=["GET"])
def get_interview_context(interview_id: str):
    """
    Protected endpoint for ElevenLabs agent tool call / context retrieval.
    Supplies the agent with role requirements, candidate background summary, and planned sections.
    """
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    plan = interview.interview_plan or {}
    return jsonify({
        "interview_id": interview.id,
        "candidate_name": interview.candidate_name,
        "job_title": interview.job_title,
        "difficulty": interview.difficulty,
        "duration_minutes": interview.duration_minutes,
        "competencies": plan.get("required_competencies", []),
        "planned_sections": plan.get("sections", []),
        "resume_highlights": plan.get("resume_skills_found", []),
        "conduct_guidelines": plan.get("conduct_guidelines", "")
    })


@api_bp.route("/interviews/<interview_id>/transcript", methods=["POST"])
def sync_transcript(interview_id: str):
    """Client-side transcript synchronization."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    data = request.get_json(silent=True) or {}
    turns = data.get("transcript", [])
    conversation_id = data.get("conversation_id")

    if conversation_id:
        interview.elevenlabs_conversation_id = conversation_id

    if turns and isinstance(turns, list):
        interview.transcript = turns

    if isinstance(interview, MongoInterview):
        interview.save()
    else:
        db.session.commit()
        if Config.is_mongo_configured():
            try:
                m_doc = MongoInterview.find_by_id(interview.id) or MongoInterview(interview.to_dict())
                m_doc.transcript = turns
                if conversation_id:
                    m_doc.elevenlabs_conversation_id = conversation_id
                m_doc.save()
            except Exception:
                pass

    return jsonify({"success": True, "turns_count": len(interview.transcript or [])})


@api_bp.route("/interviews/<interview_id>/end", methods=["POST"])
def end_interview(interview_id: str):
    """Record that the interview session has ended."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    # Do not downgrade an already completed or evaluated interview
    if interview.status == InterviewStatus.COMPLETED or getattr(interview, "report", None) or getattr(interview, "has_report", False):
        return jsonify({"success": True, "status": InterviewStatus.COMPLETED})

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "normal")
    conversation_id = data.get("conversation_id")

    if conversation_id:
        interview.elevenlabs_conversation_id = conversation_id

    if reason == "interrupted":
        interview.status = InterviewStatus.INTERRUPTED
    else:
        interview.status = InterviewStatus.AWAITING_FINALIZATION

    if isinstance(interview, MongoInterview):
        interview.save()
    else:
        event = InterviewEvent(
            interview_id=interview.id,
            event_type="interview_ended",
            event_data={"reason": reason, "conversation_id": conversation_id}
        )
        db.session.add(event)
        db.session.commit()
        if Config.is_mongo_configured():
            try:
                m_doc = MongoInterview.find_by_id(interview.id) or MongoInterview(interview.to_dict())
                m_doc.status = interview.status
                if conversation_id:
                    m_doc.elevenlabs_conversation_id = conversation_id
                m_doc.save()
            except Exception:
                pass

    return jsonify({"success": True, "status": interview.status})


@api_bp.route("/interviews/<interview_id>/finalize", methods=["POST"])
def finalize_interview(interview_id: str):
    """
    Idempotent finalization endpoint:
    1. Ingests transcript from ElevenLabs API or client payload.
    2. Runs EvaluationService against rubric.
    3. Persists InterviewReport and marks COMPLETED in MongoDB.
    """
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    # Idempotent return if already completed with report
    if interview.status == InterviewStatus.COMPLETED and interview.report:
        return jsonify({
            "success": True,
            "status": interview.status,
            "completed_url": url_for("interviews.interview_completed", interview_id=interview.id),
            "report_url": url_for("reports.view_report", interview_id=interview.id)
        })

    data = request.get_json(silent=True) or {}
    conv_id = data.get("conversation_id") or interview.elevenlabs_conversation_id
    client_turns = data.get("transcript")

    # Sync transcript
    ts_service = TranscriptService()
    ts_service.sync_transcript(interview, conversation_id=conv_id, client_transcript=client_turns)

    # Evaluate with interview's selected LLM provider
    eval_service = EvaluationService(llm_service=LLMService(provider=interview.llm_provider))
    try:
        report = eval_service.evaluate_interview(interview)
        interview.completed_at = datetime.now(timezone.utc)
        interview.status = InterviewStatus.COMPLETED
        interview.error_message = None

        # Build clean serialized transcript
        raw_ts = getattr(interview, "transcript", None) or []
        serialized_transcript = []
        for turn in raw_ts:
            if hasattr(turn, "to_dict"):
                serialized_transcript.append(turn.to_dict())
            elif isinstance(turn, dict):
                serialized_transcript.append(turn)

        if isinstance(interview, MongoInterview):
            interview.report = MongoInterviewReport(report.to_dict() if hasattr(report, "to_dict") else report)
            interview.transcript = serialized_transcript
            interview.status = InterviewStatus.COMPLETED
            interview.completed_at = datetime.now(timezone.utc)
            interview.save()
        else:
            interview.status = InterviewStatus.COMPLETED
            db.session.commit()
            if Config.is_mongo_configured():
                try:
                    m_doc = MongoInterview.find_by_id(interview.id) or MongoInterview(interview.to_dict())
                    m_doc.report = MongoInterviewReport(report.to_dict() if hasattr(report, "to_dict") else report)
                    m_doc.transcript = serialized_transcript
                    m_doc.status = InterviewStatus.COMPLETED
                    m_doc.completed_at = interview.completed_at
                    m_doc.save()
                except Exception as me:
                    print(f"[API] Error saving report and transcript to Mongo: {me}")

        session["active_report"] = report.to_dict() if hasattr(report, "to_dict") else report
        session.modified = True

        return jsonify({
            "success": True,
            "status": interview.status,
            "overall_score": report.overall_score,
            "completed_url": url_for("interviews.interview_completed", interview_id=interview.id),
            "report_url": url_for("reports.view_report", interview_id=interview.id)
        })

    except TranscriptValidationError as tve:
        interview.status = InterviewStatus.INTERRUPTED
        interview.error_message = str(tve)
        if isinstance(interview, MongoInterview):
            interview.save()
        else:
            db.session.commit()
        return jsonify({"error": str(tve)}), 422

    except LLMConfigError as lce:
        interview.error_message = str(lce)
        if isinstance(interview, MongoInterview):
            interview.save()
        else:
            db.session.commit()
        return jsonify({"error": str(lce)}), 503

    except (LLMExecutionError, Exception) as e:
        interview.error_message = f"Evaluation failed: {str(e)}"
        if isinstance(interview, MongoInterview):
            interview.save()
        else:
            db.session.commit()
        return jsonify({"error": f"Evaluation processing error: {str(e)}"}), 500


@api_bp.route("/interviews/<interview_id>/webhook", methods=["POST"])
def elevenlabs_webhook(interview_id: str):
    """
    Optional post-call webhook receiver from ElevenLabs Conversational AI.
    """
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    payload = request.get_data()
    sig = request.headers.get("xi-signature", "")
    from app.config import Config
    if not ElevenLabsService.verify_webhook_signature(payload, sig, Config.ELEVENLABS_WEBHOOK_SECRET):
        return jsonify({"error": "Invalid webhook signature."}), 401

    data = request.get_json(silent=True) or {}
    transcript_data = data.get("transcript", [])
    if transcript_data:
        ts_service = TranscriptService()
        ts_service.sync_transcript(interview, client_transcript=transcript_data)

    return jsonify({"received": True})


@api_bp.route("/interviews/<interview_id>/status", methods=["GET"])
def get_interview_status(interview_id: str):
    """Check current interview status."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    return jsonify(interview.to_dict())


@api_bp.route("/interviews/<interview_id>", methods=["DELETE"])
def delete_interview(interview_id: str):
    """Delete an interview and all associated records from MongoDB and DB."""
    if Config.is_mongo_configured():
        try:
            MongoInterview.delete(interview_id)
        except Exception as me:
            print(f"[API] Error deleting Mongo interview: {me}")

    interview = db.session.get(Interview, interview_id)
    if interview:
        db.session.delete(interview)
        db.session.commit()
    return jsonify({"success": True, "message": "Interview deleted successfully."})


@api_bp.route("/interviews/restore", methods=["POST"])
def restore_interview():
    """Endpoint allowing client to restore interview state into an ephemeral serverless container."""
    data = request.get_json(silent=True) or {}
    interview_id = data.get("interview_id") or data.get("id")
    if not interview_id:
        return jsonify({"error": "interview_id is required."}), 400

    existing = db.session.get(Interview, interview_id)
    if existing:
        return jsonify({"success": True, "restored": False, "status": existing.status})

    try:
        restored = Interview(
            id=interview_id,
            candidate_name=data.get("candidate_name", "Candidate"),
            candidate_email=data.get("candidate_email"),
            job_title=data.get("job_title", DEFAULT_CONTENT_CREATOR_JOB_TITLE),
            jd_text=data.get("jd_text", DEFAULT_CONTENT_CREATOR_JD),
            resume_text=data.get("resume_text", ""),
            duration_minutes=int(data.get("duration_minutes", 15)),
            difficulty=data.get("difficulty", "Intermediate"),
            language=data.get("language", "English"),
            llm_provider=data.get("llm_provider", "gemini"),
            voice_engine=data.get("voice_engine", "elevenlabs"),
            interview_plan=data.get("interview_plan"),
            transcript=data.get("transcript", []),
            status=data.get("status", InterviewStatus.PREPARED)
        )
        db.session.add(restored)
        db.session.commit()

        session["active_interview"] = {
            "id": restored.id,
            "interview_id": restored.id,
            "candidate_name": restored.candidate_name,
            "candidate_email": restored.candidate_email,
            "job_title": restored.job_title,
            "duration_minutes": restored.duration_minutes,
            "difficulty": restored.difficulty,
            "language": restored.language,
            "llm_provider": restored.llm_provider,
            "voice_engine": restored.voice_engine,
            "interview_plan": restored.interview_plan,
            "status": restored.status
        }
        session.modified = True

        return jsonify({"success": True, "restored": True, "status": restored.status})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to restore interview: {str(e)}"}), 500

