from pathlib import Path
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, model_validator
from app.services.llm_service import LLMService

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "planner.txt"


def stringify_item(item: Any) -> str:
    """Normalize any string, dict, or primitive into a clean, human-readable string."""
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, (int, float)):
        return str(item)
    if isinstance(item, dict):
        name = (
            item.get("project_name") or
            item.get("project") or
            item.get("title") or
            item.get("name") or
            item.get("degree") or
            item.get("certification") or
            item.get("certificate") or
            item.get("role") or
            ""
        )
        role = item.get("role") if name != item.get("role") else ""
        desc = (
            item.get("description") or
            item.get("details") or
            item.get("summary") or
            item.get("institution") or
            item.get("school") or
            item.get("university") or
            item.get("issuer") or
            ""
        )
        tech = item.get("technologies") or item.get("tools") or item.get("tech_stack") or item.get("skills") or ""
        year = item.get("year") or item.get("date") or item.get("duration") or ""

        parts = []
        if name:
            parts.append(str(name).strip())
        if role:
            parts.append(f"(Role: {str(role).strip()})")
        if desc:
            parts.append(f"- {str(desc).strip()}")
        if tech:
            tech_str = ", ".join(tech) if isinstance(tech, list) else str(tech)
            parts.append(f"[Tech: {tech_str.strip()}]")
        if year:
            parts.append(f"({str(year).strip()})")

        if parts:
            return " ".join(parts).strip()
        # Fallback to key-value string
        return "; ".join(f"{k}: {v}" for k, v in item.items() if v)
    if isinstance(item, list):
        return ", ".join(stringify_item(x) for x in item if x)
    return str(item).strip()


class CompetencyItem(BaseModel):
    id: str = Field(default="", description="Unique slug for the competency e.g. 'system_design'")
    name: str = Field(default="Core Competency", description="Human-readable competency title")
    weight: int = Field(default=20, description="Weight percentage (e.g. 20 for 20%)")
    difficulty: str = Field("Intermediate", description="Beginner, Intermediate, Advanced")
    objective: str = Field(default="", description="What this competency aims to verify")
    expected_evidence: str = Field(default="", description="Tangible examples or behaviors looked for")

    @model_validator(mode="before")
    @classmethod
    def handle_competency_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("id"):
                data["id"] = data.get("competency_id") or data.get("slug") or data.get("dimension_id") or data.get("name", "comp").lower().replace(" ", "_")[:30]
            if not data.get("name"):
                data["name"] = data.get("title") or data.get("competency_name") or data.get("dimension") or data.get("dimension_name") or "Core Competency"
            if not data.get("objective"):
                data["objective"] = data.get("description") or data.get("goal") or data.get("focus") or "Assess candidate proficiency."
            if not data.get("expected_evidence"):
                data["expected_evidence"] = data.get("evidence") or data.get("criteria") or data.get("expected_outcomes") or "Demonstrates clear capability."
            if not data.get("weight") or not isinstance(data.get("weight"), (int, float)):
                data["weight"] = 20
        elif isinstance(data, str):
            return {
                "id": data.lower().replace(" ", "_")[:30],
                "name": data.strip(),
                "weight": 20,
                "objective": f"Assess candidate proficiency in {data.strip()}.",
                "expected_evidence": "Demonstrates clear capability."
            }
        return data


class QuestionItem(BaseModel):
    id: str = Field(default="q_1", description="Question identifier e.g. 'q_1'")
    question_text: str = Field(default="", description="The conversational spoken question")
    competency_id: str = Field(default="", description="Referenced competency id")
    expected_evidence: str = Field(default="", description="What constitutes an adequate answer")
    follow_up_guidance: str = Field(default="", description="How to probe if the candidate answer is vague")

    @model_validator(mode="before")
    @classmethod
    def handle_question_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("id"):
                data["id"] = data.get("question_id") or data.get("qid") or "q_1"
            if not data.get("question_text"):
                data["question_text"] = data.get("question") or data.get("prompt") or data.get("text") or data.get("spoken_question") or ""
            if not data.get("competency_id"):
                data["competency_id"] = data.get("competency") or data.get("dimension") or ""
            if not data.get("expected_evidence"):
                data["expected_evidence"] = data.get("expected_response") or data.get("evaluation_criteria") or data.get("evidence") or ""
            if not data.get("follow_up_guidance"):
                data["follow_up_guidance"] = data.get("follow_up") or data.get("probe") or data.get("adaptive_follow_up") or ""
        elif isinstance(data, str):
            return {
                "id": "q_1",
                "question_text": data.strip(),
                "expected_evidence": "",
                "follow_up_guidance": ""
            }
        return data


class InterviewSection(BaseModel):
    section_id: str = Field(default="section", description="Section slug e.g. 'resume_deep_dive'")
    title: str = Field(default="Section", description="Section title")
    target_duration_minutes: int = Field(default=3, description="Approximate time allocated")
    questions: List[QuestionItem] = Field(default_factory=list, description="Questions in this section")

    @model_validator(mode="before")
    @classmethod
    def handle_section_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("section_id"):
                data["section_id"] = data.get("id") or data.get("slug") or data.get("stage_id") or "section"
            if not data.get("title"):
                data["title"] = data.get("name") or data.get("stage_name") or data.get("section_title") or "Section"
            if not data.get("target_duration_minutes"):
                data["target_duration_minutes"] = data.get("duration_minutes") or data.get("duration") or data.get("time_minutes") or 3
            
            raw_q = (
                data.get("questions") or
                data.get("sample_questions") or
                data.get("planned_questions") or
                data.get("question_list") or
                []
            )
            if isinstance(raw_q, list):
                norm_q = []
                for idx, q in enumerate(raw_q):
                    if isinstance(q, str):
                        norm_q.append({
                            "id": f"q_{idx+1}",
                            "question_text": q.strip(),
                            "expected_evidence": "",
                            "follow_up_guidance": ""
                        })
                    else:
                        norm_q.append(q)
                data["questions"] = norm_q
        elif isinstance(data, str):
            return {
                "section_id": "sec",
                "title": data.strip(),
                "target_duration_minutes": 3,
                "questions": []
            }
        return data


class InterviewPlanSchema(BaseModel):
    job_title: str = Field(default="")
    candidate_summary: str = Field(default="", description="High-signal summary of candidate background and role alignment")
    candidate_projects: List[str] = Field(default_factory=list, description="Specific projects and past achievements from the resume")
    candidate_studies: List[str] = Field(default_factory=list, description="Education, degrees, universities, certifications from resume")
    company_requirements_summary: str = Field(default="", description="Summary of core employer requirements from the JD")
    responsibilities: List[str] = Field(default_factory=list)
    required_competencies: List[CompetencyItem] = Field(default_factory=list)
    resume_skills_found: List[str] = Field(default_factory=list)
    skill_gaps: List[str] = Field(default_factory=list)
    sections: List[InterviewSection] = Field(default_factory=list)
    conduct_guidelines: Optional[str] = None
    rag_questions_retrieved: List[Dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def extract_nested_metadata(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Unnest top-level wrappers like {"interview_plan": {...}} or {"plan": {...}}
            for wrapper in ("interview_plan", "plan", "interview", "output", "data", "result", "response"):
                if wrapper in data and isinstance(data[wrapper], dict) and len(data) <= 3:
                    sub = data[wrapper]
                    data = {**sub, **{k: v for k, v in data.items() if k != wrapper}}

            # 2. Extract nested interview_metadata dictionary if present
            if "interview_metadata" in data and isinstance(data["interview_metadata"], dict):
                meta = data["interview_metadata"]
                for k, v in meta.items():
                    if k not in data or not data[k]:
                        data[k] = v

            # 3. Aggressively map required_competencies synonyms
            if not data.get("required_competencies"):
                data["required_competencies"] = (
                    data.get("competencies") or
                    data.get("performance_dimensions") or
                    data.get("dimensions") or
                    data.get("evaluation_dimensions") or
                    data.get("competency_rubric") or
                    data.get("rubric") or
                    data.get("evaluation_criteria") or
                    data.get("competency_list") or
                    []
                )

            # 4. Aggressively map sections synonyms
            if not data.get("sections"):
                data["sections"] = (
                    data.get("interview_sections") or
                    data.get("interview_stages") or
                    data.get("stages") or
                    data.get("interview_flow") or
                    data.get("flow") or
                    data.get("structured_conversational_interview_flow") or
                    data.get("steps") or
                    data.get("interview_steps") or
                    []
                )

            # 5. Aggressively map resume_skills_found synonyms
            if not data.get("resume_skills_found"):
                data["resume_skills_found"] = (
                    data.get("candidate_skills") or
                    data.get("skills") or
                    data.get("skills_found") or
                    data.get("technical_skills") or
                    data.get("verified_skills") or
                    data.get("demonstrated_skills") or
                    data.get("verified_resume_skills") or
                    []
                )

            # 6. Aggressively map skill_gaps synonyms
            if not data.get("skill_gaps"):
                data["skill_gaps"] = (
                    data.get("areas_to_probe") or
                    data.get("gaps") or
                    data.get("potential_gaps") or
                    data.get("weaknesses") or
                    data.get("areas_for_improvement") or
                    data.get("unverified_claims") or
                    data.get("missing_skills") or
                    []
                )

            # 7. Aggressively map responsibilities synonyms
            if not data.get("responsibilities"):
                data["responsibilities"] = (
                    data.get("key_responsibilities") or
                    data.get("role_responsibilities") or
                    data.get("job_responsibilities") or
                    []
                )

            # 8. Ensure job_title is populated from any synonym
            if not data.get("job_title"):
                data["job_title"] = (
                    data.get("title") or
                    data.get("role") or
                    data.get("position") or
                    data.get("target_role") or
                    data.get("target_position") or
                    ""
                )

            # 9. Map candidate and JD summary synonyms
            if not data.get("candidate_summary"):
                data["candidate_summary"] = data.get("summary") or data.get("candidate_overview") or data.get("overview") or data.get("profile") or ""
            if not data.get("candidate_projects"):
                data["candidate_projects"] = data.get("projects") or data.get("past_projects") or data.get("key_projects") or []
            if not data.get("candidate_studies"):
                data["candidate_studies"] = data.get("studies") or data.get("education") or data.get("academic_background") or data.get("certifications") or []
            if not data.get("company_requirements_summary"):
                data["company_requirements_summary"] = data.get("company_requirements") or data.get("jd_summary") or data.get("requirements_summary") or data.get("role_requirements") or ""

            # 10. Normalize list fields converting any dicts into clean strings
            for list_field in ("candidate_projects", "candidate_studies", "responsibilities", "resume_skills_found", "skill_gaps"):
                val = data.get(list_field)
                if isinstance(val, list):
                    data[list_field] = [stringify_item(x) for x in val if x is not None]
                elif isinstance(val, (str, dict)):
                    data[list_field] = [stringify_item(val)]
                elif val is None:
                    data[list_field] = []

            # 11. Normalize string fields converting lists/dicts into unified text
            for str_field in ("candidate_summary", "company_requirements_summary"):
                val = data.get(str_field)
                if isinstance(val, list):
                    data[str_field] = "\n".join(f"- {stringify_item(x)}" for x in val if x)
                elif isinstance(val, dict):
                    data[str_field] = "\n".join(f"- {k}: {v}" for k, v in val.items() if v)
                elif val is not None:
                    data[str_field] = str(val).strip()

        return data

    @field_validator("required_competencies")
    @classmethod
    def normalize_weights(cls, competencies: List[CompetencyItem]) -> List[CompetencyItem]:
        if not competencies:
            return competencies
        total = sum(c.weight for c in competencies)
        if total != 100 and total > 0:
            diff = 0
            for c in competencies:
                new_w = round((c.weight / total) * 100)
                c.weight = new_w
                diff += new_w
            competencies[0].weight += (100 - diff)
        return competencies


class InterviewPlannerService:
    """Generates structured, role-specific interview plans using the LLM."""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm = llm_service or LLMService()

    def generate_plan(
        self,
        candidate_name: str,
        job_title: str = "Software Engineer",
        jd_text: str = "",
        resume_text: str = "",
        duration_minutes: int = 15,
        difficulty: str = "Intermediate",
        language: str = "English"
    ) -> InterviewPlanSchema:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        effective_jd = (jd_text or "").strip()
        if not effective_jd:
            effective_jd = f"Job Title: {job_title}\nResponsibilities and technical competencies appropriate for a professional {job_title} at {difficulty} level."

        effective_resume = (resume_text or "").strip()

        try:
            user_prompt = prompt_template.format(
                job_title=job_title,
                candidate_name=candidate_name,
                duration_minutes=duration_minutes,
                difficulty=difficulty,
                language=language,
                jd_text=effective_jd[:7000],
                resume_text=effective_resume[:7000]
            )
        except (KeyError, IndexError, ValueError):
            user_prompt = prompt_template
            for placeholder, val in {
                "{job_title}": job_title,
                "{candidate_name}": candidate_name,
                "{duration_minutes}": str(duration_minutes),
                "{difficulty}": difficulty,
                "{language}": language,
                "{jd_text}": effective_jd[:7000],
                "{resume_text}": effective_resume[:7000]
            }.items():
                user_prompt = user_prompt.replace(placeholder, val)

        system_prompt = (
            f"You are an elite talent acquisition architect and interview designer assessing a candidate for {job_title}. "
            "You must thoroughly examine the job description and candidate resume to produce specific, highly customized questions. "
            "Your output must strictly adhere to the InterviewPlanSchema structure in valid JSON format."
        )

        plan = self.llm.generate_json(system_prompt, user_prompt, InterviewPlanSchema)
        if not plan.job_title or not plan.job_title.strip():
            plan.job_title = job_title
        return plan
