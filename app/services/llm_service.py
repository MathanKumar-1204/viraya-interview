import json
import re
from typing import Type, TypeVar, Optional, Any, Dict
from pydantic import BaseModel
from openai import OpenAI
from flask import current_app, has_app_context
from app.config import Config

T = TypeVar("T", bound=BaseModel)


class LLMConfigError(Exception):
    """Raised when LLM configuration or credentials are missing or invalid."""
    pass


class LLMExecutionError(Exception):
    """Raised when LLM API call or response parsing fails."""
    pass


def clean_json_text(text: str) -> str:
    """Strip markdown code fence blocks if present."""
    text = text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"^```(?:json)?\s*\n(.*?)```$", text, re.DOTALL | re.MULTILINE)
    if match:
        return match.group(1).strip()
    # Sometimes markdown starts without newline
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


class LLMService:
    """Wrapper around LLM providers with structured output validation."""

    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
        cfg_provider = current_app.config.get("LLM_PROVIDER") if has_app_context() else Config.LLM_PROVIDER
        cfg_key = current_app.config.get("LLM_API_KEY") if has_app_context() else Config.LLM_API_KEY
        cfg_model = current_app.config.get("LLM_MODEL") if has_app_context() else Config.LLM_MODEL
        cfg_url = current_app.config.get("LLM_BASE_URL") if has_app_context() else Config.LLM_BASE_URL

        is_test_env = (has_app_context() and current_app.config.get("TESTING")) or cfg_provider == "mock"
        if is_test_env and cfg_provider == "mock" and (provider is None or provider == "mock" or not has_app_context() or current_app.config.get("TESTING")):
            self.provider = "mock"
        else:
            self.provider = (provider if provider is not None else cfg_provider or "gemini").lower().strip()

        # Provider-specific credential and model resolution
        if api_key is not None:
            self.api_key = api_key
        elif self.provider == "gemini":
            self.api_key = (current_app.config.get("GEMINI_API_KEY") if has_app_context() else Config.GEMINI_API_KEY) or cfg_key
        elif self.provider == "openai":
            self.api_key = (current_app.config.get("OPENAI_API_KEY") if has_app_context() else Config.OPENAI_API_KEY) or (cfg_key if cfg_key and not cfg_key.startswith("AIza") else "")
        elif self.provider == "claude":
            self.api_key = (current_app.config.get("ANTHROPIC_API_KEY") if has_app_context() else Config.ANTHROPIC_API_KEY) or ""
        else:
            self.api_key = cfg_key

        if model is not None:
            self.model = model
        elif self.provider == "gemini":
            self.model = (current_app.config.get("GEMINI_MODEL") if has_app_context() else Config.GEMINI_MODEL) or "gemini-3.8-flash"
        elif self.provider == "openai":
            self.model = (current_app.config.get("OPENAI_MODEL") if has_app_context() else Config.OPENAI_MODEL) or "gpt-4o-mini"
        elif self.provider == "claude":
            self.model = (current_app.config.get("CLAUDE_MODEL") if has_app_context() else Config.CLAUDE_MODEL) or "claude-3-5-sonnet-20241022"
        else:
            self.model = cfg_model

        self.base_url = base_url if base_url is not None else cfg_url

    def _get_openai_client(self) -> OpenAI:
        if not self.api_key or self.api_key.startswith("your_"):
            raise LLMConfigError(
                "OpenAI API key is not configured. Please set OPENAI_API_KEY (or LLM_API_KEY) in your .env file "
                "(or choose Google Gemini on the setup screen)."
            )

        kwargs = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    # Backward compatibility alias
    _get_client = _get_openai_client

    def _call_openai(self, system_prompt: str, user_prompt: str, json_mode: bool = True) -> str:
        """Call OpenAI API using direct requests (resilient against httpx2 decompression issues) with SDK fallback."""
        if not self.api_key or self.api_key.startswith("your_"):
            raise LLMConfigError(
                "OpenAI API key is not configured. Please set OPENAI_API_KEY (or LLM_API_KEY) in your .env file "
                "(or choose Google Gemini on the setup screen)."
            )

        model = self.model or "gpt-4o-mini"
        if "gemini" in model.lower() or "claude" in model.lower():
            model = "gpt-4o-mini"

        base_url = (self.base_url or "https://api.openai.com/v1").rstrip("/")
        endpoint = f"{base_url}/chat/completions"

        messages = [
            {
                "role": "system",
                "content": system_prompt + ("\n\nCRITICAL: Return ONLY a valid JSON object matching the requested schema." if json_mode else "")
            },
            {"role": "user", "content": user_prompt}
        ]

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.2 if json_mode else 0.7,
            "max_tokens": 4000 if json_mode else 500,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 1. Primary: Direct HTTP request via requests (immune to httpx2 brotli process() bug)
        try:
            import requests
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=90)
            if resp.ok:
                data = resp.json()
                choices = data.get("choices", [])
                if choices and choices[0].get("message", {}).get("content"):
                    return choices[0]["message"]["content"]
                raise LLMExecutionError("OpenAI returned an empty response.")
            else:
                err_body = resp.text
                if resp.status_code == 429 or "insufficient_quota" in err_body or "credit_balance_exhausted" in err_body:
                    raise LLMExecutionError(
                        "OpenAI credit balance is exhausted or rate limit reached (Error 429). "
                        "To use Google Gemini instead, select Gemini on the setup screen or set LLM_PROVIDER=gemini."
                    )
                raise LLMExecutionError(f"OpenAI API returned HTTP {resp.status_code}: {err_body}")
        except LLMExecutionError:
            raise
        except Exception as req_err:
            # 2. Secondary fallback: Official SDK client (if requests had a local socket issue)
            try:
                client = self._get_openai_client()
                kwargs: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 4000,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                sdk_resp = client.chat.completions.create(**kwargs)
                raw = sdk_resp.choices[0].message.content or ""
                if not raw:
                    raise LLMExecutionError("OpenAI SDK returned an empty response.")
                return raw
            except Exception as sdk_err:
                err_str = str(sdk_err)
                if "credit_balance_exhausted" in err_str or "insufficient_quota" in err_str or "429" in err_str:
                    raise LLMExecutionError(
                        "OpenAI credit balance is exhausted (Error 429). "
                        "To use Google Gemini instead, select Gemini on the setup screen."
                    )
                raise LLMExecutionError(f"OpenAI request failed: {err_str} (Direct request error: {req_err})")

    def _call_claude(self, system_prompt: str, user_prompt: str) -> str:
        """Call Anthropic Claude API for structured analysis."""
        if not self.api_key or self.api_key.startswith("your_"):
            raise LLMConfigError(
                "Anthropic Claude API key is not configured. Please set ANTHROPIC_API_KEY in your .env file "
                "(or choose Google Gemini on the setup screen)."
            )

        # Try using anthropic official SDK if installed
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model or "claude-3-5-sonnet-20241022",
                max_tokens=4000,
                temperature=0.2,
                system=system_prompt + "\n\nCRITICAL: Return ONLY a valid JSON object strictly matching the schema. No markdown fences or commentary.",
                messages=[{"role": "user", "content": user_prompt}]
            )
            if response.content and len(response.content) > 0:
                return response.content[0].text
            raise LLMExecutionError("Claude returned an empty response.")
        except ImportError:
            # Fallback to direct HTTP request using requests
            import requests
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": self.model or "claude-3-5-sonnet-20241022",
                "max_tokens": 4000,
                "temperature": 0.2,
                "system": system_prompt + "\n\nCRITICAL: Return ONLY a valid JSON object strictly matching the schema. No markdown code blocks.",
                "messages": [{"role": "user", "content": user_prompt}]
            }
            try:
                res = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)
                if not res.ok:
                    raise LLMExecutionError(f"Claude API request failed ({res.status_code}): {res.text}")
                data = res.json()
                parts = data.get("content", [])
                if parts and len(parts) > 0:
                    return parts[0].get("text", "")
                raise LLMExecutionError("Claude returned an empty response.")
            except Exception as e:
                raise LLMExecutionError(f"Claude request error: {str(e)}")

    def _call_gemini(self, system_prompt: str, user_prompt: str, json_mode: bool = True) -> str:
        """Call Google Gemini using the google-genai SDK or legacy fallback."""
        if self.provider == "mock":
            return (
                "That is a great perspective. Could you share a specific project or metric where that "
                "content strategy delivered measurable impact?"
            )

        if not self.api_key or self.api_key.startswith("your_"):
            raise LLMConfigError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY (or LLM_API_KEY) in your .env file "
                "(or set LLM_PROVIDER=mock for offline testing)."
            )

        # Normalize model name if user entered e.g. "gemini-flash" or "gpt-4o"
        gemini_model = self.model
        if "gpt" in gemini_model.lower() or gemini_model == "gemini-2.0-flash":
            gemini_model = "gemini-3.8-flash"
        if not gemini_model.startswith("gemini-"):
            gemini_model = f"gemini-{gemini_model}"

        # Candidate models to attempt in order if a 404 deprecation occurs
        candidate_models = [gemini_model]
        for fallback in ("gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash"):
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        if json_mode:
            combined_prompt = (
                f"{system_prompt}\n\n"
                f"--- Target Input Data ---\n"
                f"{user_prompt}\n\n"
                f"CRITICAL: Return ONLY a valid JSON object strictly matching the schema."
            )
            config_params = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            )
        else:
            combined_prompt = (
                f"{system_prompt}\n\n"
                f"{user_prompt}\n\n"
                f"INSTRUCTION: Speak naturally to the candidate in spoken conversational English. Do NOT output JSON. Do NOT wrap in curly braces or quotes."
            )
            config_params = types.GenerateContentConfig(
                temperature=0.7,
            )

        last_error = None
        for model_to_try in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_to_try,
                    contents=combined_prompt,
                    config=config_params
                )
                if not response or not response.text:
                    raise LLMExecutionError("Gemini returned an empty response.")
                return response.text

            except Exception as e:
                err_str = str(e)
                last_error = err_str

                # If 404 NOT_FOUND / no longer available, try the next candidate model
                if "404" in err_str or "NOT_FOUND" in err_str or "no longer available" in err_str:
                    continue

                if "CONSUMER_SUSPENDED" in err_str:
                    raise LLMExecutionError(
                        "Your Google Gemini API key or project has been suspended by Google (403 CONSUMER_SUSPENDED). "
                        "Google has disabled project 788089823893 associated with this key. "
                        "Please generate a new API key at https://aistudio.google.com/apikey under an active project, "
                        "or set LLM_PROVIDER=mock in .env to test immediately."
                    )
                if "PERMISSION_DENIED" in err_str or "403" in err_str:
                    raise LLMExecutionError(
                        f"Gemini API permission denied (403): {err_str}. Please verify that the Gemini API is enabled for your project."
                    )
                if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                    raise LLMExecutionError("Gemini API rate limit or quota exceeded (429 Resource Exhausted). Please verify your Google AI Studio quota.")
                if "API_KEY_INVALID" in err_str or "API key not valid" in err_str:
                    raise LLMConfigError("The provided Gemini API key is invalid. Please verify your GEMINI_API_KEY in .env.")
                raise LLMExecutionError(f"Gemini API call failed: {err_str}")

        raise LLMExecutionError(f"Gemini API call failed across candidate models {candidate_models}: {last_error}")

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 250,
        temperature: float = 0.7
    ) -> str:
        """
        Generate conversational spoken text using the configured LLM provider (Gemini, OpenAI, Claude, or Mock).
        Returns plain conversational spoken text (not JSON).
        Resilient: if the primary provider encounters an issue (e.g. rate limit), falls back to alternate configured providers.
        """
        if self.provider == "mock":
            return "Got it. Can you tell me more about your recent experience and the technologies you used?"

        providers_to_try = [self.provider]
        for alt in ("gemini", "openai", "claude"):
            if alt not in providers_to_try:
                providers_to_try.append(alt)

        last_error = None
        for prov in providers_to_try:
            try:
                if prov == "gemini":
                    key = self.api_key if self.provider == "gemini" and self.api_key else (
                        (current_app.config.get("GEMINI_API_KEY") if has_app_context() else Config.GEMINI_API_KEY)
                        or (Config.LLM_API_KEY if Config.LLM_API_KEY and Config.LLM_API_KEY.startswith("AIza") else "")
                    )
                    if not key or key.startswith("your_"):
                        continue
                    orig_prov, orig_key = self.provider, self.api_key
                    self.provider, self.api_key = "gemini", key
                    try:
                        raw = self._call_gemini(system_prompt, user_prompt, json_mode=False)
                        if raw and raw.strip():
                            return raw.strip()
                    finally:
                        self.provider, self.api_key = orig_prov, orig_key

                elif prov == "openai":
                    key = self.api_key if self.provider == "openai" and self.api_key else (
                        (current_app.config.get("OPENAI_API_KEY") if has_app_context() else Config.OPENAI_API_KEY)
                        or (Config.LLM_API_KEY if Config.LLM_API_KEY and not Config.LLM_API_KEY.startswith("AIza") else "")
                    )
                    if not key or key.startswith("your_"):
                        continue
                    orig_prov, orig_key = self.provider, self.api_key
                    self.provider, self.api_key = "openai", key
                    try:
                        raw = self._call_openai(system_prompt, user_prompt, json_mode=False)
                        if raw and raw.strip():
                            return raw.strip()
                    finally:
                        self.provider, self.api_key = orig_prov, orig_key

                elif prov == "claude":
                    key = self.api_key if self.provider == "claude" and self.api_key else (
                        (current_app.config.get("ANTHROPIC_API_KEY") if has_app_context() else Config.ANTHROPIC_API_KEY)
                    )
                    if not key or key.startswith("your_"):
                        continue
                    orig_prov, orig_key = self.provider, self.api_key
                    self.provider, self.api_key = "claude", key
                    try:
                        raw = self._call_claude(system_prompt, user_prompt)
                        if raw and raw.strip():
                            return raw.strip()
                    finally:
                        self.provider, self.api_key = orig_prov, orig_key

            except Exception as e:
                last_error = e
                print(f"[LLMService] generate_text provider '{prov}' notice: {e}", flush=True)

        if last_error:
            raise last_error

        raise LLMConfigError("No valid LLM provider credentials configured.")

    def generate_json(self, system_prompt: str, user_prompt: str, response_model: Type[T]) -> T:
        """Call LLM (Gemini, OpenAI, or Mock) and parse the response into the specified Pydantic model."""
        if self.provider == "mock":
            return self._generate_mock_response(response_model, user_prompt)

        raw_content = ""

        if self.provider == "gemini":
            raw_content = self._call_gemini(system_prompt, user_prompt, json_mode=True)
        elif self.provider == "claude":
            raw_content = self._call_claude(system_prompt, user_prompt)
        else:
            raw_content = self._call_openai(system_prompt, user_prompt, json_mode=True)

        try:
            cleaned = clean_json_text(raw_content)
            data = json.loads(cleaned)

            if isinstance(data, dict):
                # If wrapped in a single top-level container key
                wrapper_keys = (
                    "interview_plan", "plan", "interview", "evaluation", 
                    "evaluation_report", "report", "response", "data", "result", "output"
                )
                for key in wrapper_keys:
                    if key in data and isinstance(data[key], dict) and len(data) == 1:
                        data = data[key]
                        break

            try:
                return response_model.model_validate(data)
            except Exception as first_err:
                # If data contains nested metadata dictionaries, merge them into root
                if isinstance(data, dict):
                    merged = dict(data)
                    for meta_key in ("interview_metadata", "metadata", "plan_metadata"):
                        if meta_key in data and isinstance(data[meta_key], dict):
                            for k, v in data[meta_key].items():
                                if k not in merged or not merged[k]:
                                    merged[k] = v
                    try:
                        return response_model.model_validate(merged)
                    except Exception:
                        pass
                raise first_err

        except json.JSONDecodeError as jde:
            raise LLMExecutionError(f"LLM returned invalid JSON: {str(jde)}")
        except Exception as e:
            if isinstance(e, (LLMConfigError, LLMExecutionError)):
                raise
            raise LLMExecutionError(f"Response validation failed: {str(e)}")

    def _generate_mock_response(self, response_model: Type[T], user_prompt: str) -> T:
        """Deterministic, comprehensive mock responses for testing and offline development."""
        schema_name = response_model.__name__

        if schema_name == "InterviewPlanSchema":
            return response_model.model_validate({
                "job_title": "Content Creator & Strategist",
                "responsibilities": [
                    "Develop engaging multi-platform editorial content strategies",
                    "Produce high-quality written articles, scripts, and social assets",
                    "Conduct audience research and keyword analysis",
                    "Collaborate with marketing and design teams to ensure brand voice consistency",
                    "Track content KPIs and iterate based on engagement analytics"
                ],
                "required_competencies": [
                    {
                        "id": "content_strategy",
                        "name": "Content Strategy & Editorial Planning",
                        "weight": 25,
                        "difficulty": "Intermediate",
                        "objective": "Assess ability to plan, calendar, and execute multi-channel content roadmaps.",
                        "expected_evidence": "Candidate describes structured editorial workflows, persona segmentation, and scheduling tools."
                    },
                    {
                        "id": "audience_seo",
                        "name": "Audience Research & SEO Optimization",
                        "weight": 20,
                        "difficulty": "Intermediate",
                        "objective": "Evaluate understanding of search intent, keyword targeting, and reader psychology.",
                        "expected_evidence": "References keyword research methods, search intent mapping, and analytics tools like Google Analytics or Semrush."
                    },
                    {
                        "id": "writing_quality",
                        "name": "Writing Quality & Brand Voice Adaptation",
                        "weight": 25,
                        "difficulty": "Advanced",
                        "objective": "Gauge narrative craft, headline hooks, tone modulation, and proofreading rigor.",
                        "expected_evidence": "Explains how they tailor tone across technical vs consumer pieces and handle revision feedback."
                    },
                    {
                        "id": "performance_analytics",
                        "name": "Content Performance & Iteration",
                        "weight": 15,
                        "difficulty": "Intermediate",
                        "objective": "Assess data-driven optimization and metric tracking.",
                        "expected_evidence": "Mentions concrete KPIs (retention, click-through, conversions) and A/B test methodologies."
                    },
                    {
                        "id": "creative_problem_solving",
                        "name": "Creative Problem Solving & Execution Under Deadlines",
                        "weight": 15,
                        "difficulty": "Intermediate",
                        "objective": "Evaluate prioritization, managing creative block, and stakeholder feedback cycles.",
                        "expected_evidence": "Shares a real story of turning around a high-stakes campaign under tight deadlines."
                    }
                ],
                "resume_skills_found": [
                    "Long-form blogging",
                    "Social media copywriting",
                    "SEO keyword research",
                    "WordPress and CMS management",
                    "Audience analytics"
                ],
                "skill_gaps": [
                    "Multi-channel video scriptwriting",
                    "Direct response email funnel copywriting"
                ],
                "sections": [
                    {
                        "section_id": "intro",
                        "title": "Introduction & Agenda",
                        "target_duration_minutes": 2,
                        "questions": [
                            {
                                "id": "q_intro_1",
                                "question_text": "Welcome! I'm Alex, your AI interviewer today. To get us started, could you briefly introduce yourself and what drew you to this Content Creator role?",
                                "competency_id": "writing_quality",
                                "expected_evidence": "Clear communication, career trajectory, enthusiasm for the position.",
                                "follow_up_guidance": "If brief, ask what specific aspect of content creation energizes them most."
                            }
                        ]
                    },
                    {
                        "section_id": "resume_deep_dive",
                        "title": "Resume & Project Highlights",
                        "target_duration_minutes": 4,
                        "questions": [
                            {
                                "id": "q_resume_1",
                                "question_text": "Looking at your background, you led several content initiatives. Could you walk me through a specific piece of content or campaign you're particularly proud of?",
                                "competency_id": "content_strategy",
                                "expected_evidence": "Specific project details, goal setting, creative process, and measurable outcomes.",
                                "follow_up_guidance": "Ask what challenges arose during production and how they overcame them."
                            }
                        ]
                    },
                    {
                        "section_id": "competencies",
                        "title": "Core Competency Assessment",
                        "target_duration_minutes": 6,
                        "questions": [
                            {
                                "id": "q_comp_1",
                                "question_text": "How do you approach discovering audience search intent and tailoring your content so it ranks well without sacrificing engaging storytelling?",
                                "competency_id": "audience_seo",
                                "expected_evidence": "Balancing user value with on-page SEO best practices.",
                                "follow_up_guidance": "Inquire which tools they rely on for competitive research."
                            },
                            {
                                "id": "q_comp_2",
                                "question_text": "When writing for different brand personas or shifting from technical documentation to conversational social copy, how do you adjust your voice?",
                                "competency_id": "writing_quality",
                                "expected_evidence": "Methodical approach to brand guidelines, tone frameworks, and vocabulary.",
                                "follow_up_guidance": "Ask how they handle conflicting feedback from internal reviewers."
                            }
                        ]
                    },
                    {
                        "section_id": "scenario",
                        "title": "Scenario & Problem Solving",
                        "target_duration_minutes": 4,
                        "questions": [
                            {
                                "id": "q_scen_1",
                                "question_text": "Imagine a flagship article you published sees high initial click-throughs but a 90% bounce rate within 15 seconds. How would you diagnose the problem and iterate?",
                                "competency_id": "performance_analytics",
                                "expected_evidence": "Diagnostic mindset: intro hook, layout readability, mismatch with search intent, fast remediation plan.",
                                "follow_up_guidance": "Ask what specific analytics metrics they would inspect first."
                            }
                        ]
                    },
                    {
                        "section_id": "closing",
                        "title": "Closing & Candidate Questions",
                        "target_duration_minutes": 2,
                        "questions": [
                            {
                                "id": "q_close_1",
                                "question_text": "Thank you for sharing your insights today! Before we conclude, what questions do you have about the team, the role, or our content vision?",
                                "competency_id": "creative_problem_solving",
                                "expected_evidence": "Thoughtful, engaged candidate questions.",
                                "follow_up_guidance": "Answer gracefully and wrap up the session warmly."
                            }
                        ]
                    }
                ],
                "conduct_guidelines": "Maintain a natural conversational cadence. Prompt the candidate for measurable examples if responses lack specifics."
            })

        elif schema_name == "EvaluationReportSchema":
            return response_model.model_validate({
                "overall_summary": "The candidate demonstrated strong foundational storytelling skills, clear communication, and an organized approach to content planning. They provided practical examples of audience engagement and showed familiarity with on-page SEO best practices.",
                "overall_score": 82,
                "competency_scores": [
                    {
                        "id": "content_strategy",
                        "name": "Content Strategy & Editorial Planning",
                        "score": 4,
                        "weight": 25,
                        "rationale": "Demonstrated a disciplined approach to building content calendars and aligning topics with brand themes.",
                        "supporting_quote": "I mapped out our monthly themes around customer pain points and created a reusable content calendar that cut turnaround times by 30%.",
                        "improvement_recommendation": "Incorporate multi-channel repurposing workflows (e.g. turning pillar articles into newsletters and micro-videos) to scale reach."
                    },
                    {
                        "id": "audience_seo",
                        "name": "Audience Research & SEO Optimization",
                        "score": 4,
                        "weight": 20,
                        "rationale": "Solid grasp of search intent research and on-page optimization balance.",
                        "supporting_quote": "We focused on answering long-tail questions rather than keyword stuffing, which increased our organic dwell time.",
                        "improvement_recommendation": "Deepen experience with topic clusters and programmatic internal linking strategies."
                    },
                    {
                        "id": "writing_quality",
                        "name": "Writing Quality & Brand Voice Adaptation",
                        "score": 4,
                        "weight": 25,
                        "rationale": "Spoke articulately and outlined a clear methodology for mastering distinct brand tones.",
                        "supporting_quote": "I develop voice guidelines with 'do this / not that' examples so everyone on the team stays cohesive.",
                        "improvement_recommendation": "Experiment with more data-driven storytelling frameworks and executive ghostwriting."
                    },
                    {
                        "id": "performance_analytics",
                        "name": "Content Performance & Iteration",
                        "score": 3,
                        "weight": 15,
                        "rationale": "Understands fundamental web engagement metrics like bounce rate, session duration, and pageviews.",
                        "supporting_quote": "When bounce rates were high, I restructured the above-the-fold content and introduced interactive callouts.",
                        "improvement_recommendation": "Gain exposure to full-funnel attribution and revenue-influence tracking."
                    },
                    {
                        "id": "creative_problem_solving",
                        "name": "Creative Problem Solving & Execution Under Deadlines",
                        "score": 4,
                        "weight": 15,
                        "rationale": "Showed composure and structured prioritization when handling tight turnaround times.",
                        "supporting_quote": "During product launches, I prioritize minimum-viable content assets and iterate based on first-day feedback.",
                        "improvement_recommendation": "Establish pre-mortems and stakeholder sign-off templates to streamline approvals."
                    }
                ],
                "strengths": [
                    "Strong audience-first mindset that prioritizes reader clarity over vanity metrics.",
                    "Articulate verbal communication and structured storytelling.",
                    "Practical familiarity with editorial workflows and content calendar management."
                ],
                "improvement_areas": [
                    "Deeper familiarity with full-funnel content attribution and conversion metrics.",
                    "Scaling content creation through structured video and multimedia repurposing."
                ],
                "evidence": [
                    "Explained how adjusting above-the-fold content reduced bounce rate on top landing pages.",
                    "Shared a concrete workflow for building team voice guidelines.",
                    "Demonstrated structured handling of urgent stakeholder editorial requests."
                ],
                "suggested_practice_questions": [
                    "How do you measure content attribution when dealing with long B2B or B2C sales cycles?",
                    "Walk through how you would conduct an audit of 200 legacy articles to decide what to update, merge, or prune.",
                    "Describe your process for pitching an unconventional creative campaign to skeptical executives."
                ],
                "recommendations": [
                    "Study advanced Google Search Console performance reporting and semantic topic clustering.",
                    "Complete a course on B2B conversion copywriting and email lead nurture sequences.",
                    "Explore AI-assisted research and repurposing workflows to double editorial velocity."
                ],
                "assessment_limitations": "This evaluation is generated by AI based exclusively on the transcript of the conducted interview. It is designed as developmental feedback for self-improvement and human hiring team review, not as an automated hiring decision."
            })

        raise LLMExecutionError(f"No mock handler implemented for model {schema_name}")
