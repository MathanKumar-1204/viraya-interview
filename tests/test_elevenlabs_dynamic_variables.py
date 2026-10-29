import pytest
from app.models.interview import Interview, InterviewStatus
from app.services.elevenlabs_service import build_interview_dynamic_variables, ElevenLabsService
from app.services.interview_planner import InterviewPlannerService, InterviewPlanSchema
from app.services.evaluation_service import EvaluationService, CompetencyScoreItem


def test_build_interview_dynamic_variables():
    interview = Interview(
        candidate_name="Alex Mercer",
        job_title="Principal Cloud Architect",
        duration_minutes=20,
        difficulty="Advanced",
        jd_text="Enterprise multi-cloud architecture, Kubernetes, Terraform, zero-trust security.",
        resume_text="Cloud Engineer with 8 years experience at MegaCorp. Migrated 400 microservices to AWS.",
        interview_plan={
            "job_title": "Principal Cloud Architect",
            "company_requirements_summary": "Lead enterprise cloud migration to AWS using Terraform and Kubernetes.",
            "candidate_summary": "Senior cloud architect with deep AWS and Kubernetes migration background.",
            "candidate_projects": [
                "Migrated 400 microservices from on-prem to AWS EKS with zero downtime.",
                "Automated multi-region infrastructure using Terraform and GitHub Actions."
            ],
            "candidate_studies": [
                "B.S. in Computer Science from University of Washington",
                "AWS Certified Solutions Architect - Professional"
            ],
            "resume_skills_found": ["AWS", "Kubernetes", "Terraform", "Docker", "Python", "Go"],
            "sections": [
                {
                    "title": "Resume Deep-Dive",
                    "questions": [
                        {
                            "id": "q1",
                            "question_text": "How did you design the traffic routing cutover during the 400 microservice migration?",
                            "expected_evidence": "Use of Canary/Blue-Green deployments, Route53, and ingress controller metrics."
                        }
                    ]
                },
                {
                    "title": "Technical Problem Solving",
                    "questions": [
                        {
                            "id": "q2",
                            "question_text": "What strategies do you enforce for zero-trust security across distributed Kubernetes clusters?",
                            "expected_evidence": "Service mesh mTLS, network policies, IAM roles for service accounts."
                        }
                    ]
                }
            ]
        }
    )

    vars_map = build_interview_dynamic_variables(interview)

    assert vars_map["candidate_name"] == "Alex Mercer"
    assert vars_map["job_title"] == "Principal Cloud Architect"
    assert "Terraform and Kubernetes" in vars_map["company_requirements"]
    assert "Migrated 400 microservices" in vars_map["candidate_details"]
    assert "AWS Certified Solutions Architect" in vars_map["candidate_details"]
    assert "traffic routing cutover" in vars_map["planned_questions"].lower()
    assert "zero-trust security" in vars_map["planned_questions"].lower()
    assert vars_map["interview_duration"] == "20 minutes"
    assert vars_map["difficulty_level"] == "Advanced"


def test_elevenlabs_credentials_include_rich_dynamic_variables(client, prepared_interview, monkeypatch):
    monkeypatch.setattr(
        "app.services.elevenlabs_service.ElevenLabsService._request_signed_url",
        lambda self: "wss://api.elevenlabs.io/v1/convai/conversation?signed_url=mock"
    )
    prepared_interview.voice_engine = "elevenlabs"
    prepared_interview.job_title = "Lead Machine Learning Engineer"
    prepared_interview.jd_text = "Deploying large language models, Triton Inference Server, vLLM, and PyTorch optimization."
    prepared_interview.interview_plan = {
        "job_title": "Lead Machine Learning Engineer",
        "company_requirements_summary": "High-throughput LLM serving using vLLM and TensorRT-LLM.",
        "candidate_summary": "ML Engineer specializing in inference optimization and distributed training.",
        "candidate_projects": ["Optimized Llama-3 serving throughput by 3.2x using vLLM and flash-attention."],
        "candidate_studies": ["M.S. in Artificial Intelligence, Carnegie Mellon University"],
        "resume_skills_found": ["PyTorch", "vLLM", "CUDA", "Triton", "Python"],
        "sections": [
            {
                "title": "LLM Inference Deep-Dive",
                "questions": [
                    {
                        "question_text": "How do you profile and mitigate KV-cache memory fragmentation under high concurrent load?"
                    }
                ]
            }
        ]
    }

    res = client.get(f"/api/interviews/{prepared_interview.id}/conversation-credentials")
    assert res.status_code == 200
    data = res.get_json()

    assert data["success"] is True
    assert "dynamic_variables" in data
    dyn = data["dynamic_variables"]
    assert dyn["candidate_name"] == prepared_interview.candidate_name
    assert dyn["job_title"] == "Lead Machine Learning Engineer"
    assert "vLLM" in dyn["company_requirements"]
    assert "flash-attention" in dyn["candidate_details"].lower()
    assert "kv-cache" in dyn["planned_questions"].lower()
    assert "KV-cache" in dyn["planned_questions"]


def test_evaluation_service_performance_dimensions():
    dims = [
        CompetencyScoreItem(
            id="domain_mastery",
            name="Domain & Technical Mastery",
            score=88,
            weight=30,
            rationale="Demonstrated strong understanding of distributed systems.",
            improvement_recommendation="Deepen familiarity with asynchronous replication edge cases."
        ),
        CompetencyScoreItem(
            id="problem_solving",
            name="Problem Solving & Critical Thinking",
            score=82,
            weight=25,
            rationale="Structured debugging approach effectively.",
            improvement_recommendation="Quantify network latency trade-offs earlier in the discussion."
        ),
        CompetencyScoreItem(
            id="execution_impact",
            name="Practical Execution & Project Impact",
            score=85,
            weight=20,
            rationale="Clear evidence of individual project ownership.",
            improvement_recommendation="Highlight team mentoring impact."
        ),
        CompetencyScoreItem(
            id="communication_clarity",
            name="Communication Clarity & Articulation",
            score=80,
            weight=15,
            rationale="Clear answers with minimal buzzwords.",
            improvement_recommendation="Use STAR structure consistently."
        ),
        CompetencyScoreItem(
            id="role_calibration",
            name="Role & Requirement Alignment",
            score=90,
            weight=10,
            rationale="Excellent match for the target senior scope.",
            improvement_recommendation="None."
        )
    ]

    transcript = [
        {"role": "interviewer", "message": "Can you describe how you architected the backend?"},
        {"role": "candidate", "message": "In our architecture we deployed Go microservices on AWS EKS with gRPC inter-service communication and PostgreSQL for storage. We achieved sub-20ms latency across 50,000 requests per second."},
        {"role": "interviewer", "message": "How did you handle failovers?"},
        {"role": "candidate", "message": "We configured multi-AZ read replicas with automated failover via AWS Aurora and implemented exponential backoff with circuit breakers on the client side."}
    ]

    overall = EvaluationService.calculate_weighted_overall_score(dims, transcript=transcript)
    # Expected weighted: (88*30 + 82*25 + 85*20 + 80*15 + 90*10) / 100 = (2640 + 2050 + 1700 + 1200 + 900) / 100 = 8490 / 100 = 85
    assert overall == 85
    assert dims[0].benchmark_level == "Proficient"
    assert dims[4].benchmark_level == "Exceptional"


def test_interview_plan_schema_dict_normalization():
    raw_payload = {
        "job_title": "Full Stack Developer",
        "candidate_summary": "Experienced developer",
        "candidate_projects": [
            {"project_name": "E-commerce platform", "role": "Lead Developer"},
            {"project_name": "Payment Gateway API", "role": "Backend Engineer", "technologies": ["Python", "FastAPI"]}
        ],
        "candidate_studies": [
            {"degree": "Bachelor of Science in Computer Science", "institution": "State University", "year": "2020"},
            {"certification": "AWS Certified Solutions Architect", "year": "2021"}
        ],
        "company_requirements_summary": [
            "Experience with microservices",
            "Strong database design skills"
        ],
        "sections": [
            {
                "title": "Intro",
                "questions": [
                    "Can you introduce yourself?",
                    {"question_text": "Tell me about your lead developer role on the e-commerce platform."}
                ]
            }
        ]
    }

    schema = InterviewPlanSchema.model_validate(raw_payload)
    assert len(schema.candidate_projects) == 2
    assert "E-commerce platform" in schema.candidate_projects[0]
    assert "Lead Developer" in schema.candidate_projects[0]
    assert "Payment Gateway API" in schema.candidate_projects[1]
    assert "FastAPI" in schema.candidate_projects[1]

    assert len(schema.candidate_studies) == 2
    assert "Bachelor of Science" in schema.candidate_studies[0]
    assert "State University" in schema.candidate_studies[0]
    assert "AWS Certified Solutions Architect" in schema.candidate_studies[1]

    assert "Experience with microservices" in schema.company_requirements_summary
    assert len(schema.sections[0].questions) == 2
    assert schema.sections[0].questions[0].question_text == "Can you introduce yourself?"
    assert "e-commerce platform" in schema.sections[0].questions[1].question_text
