"""
Seed script to create a sample Content Creator interview and evaluation report.
Run with: python seed_demo.py
"""

from app import create_app
from app.extensions import db
from app.models.interview import Interview, InterviewReport, InterviewStatus, InterviewEvent
from datetime import datetime, timezone, timedelta

app = create_app("development")

with app.app_context():
    # Check if demo interview already exists
    existing = Interview.query.filter_by(candidate_name="Maya Chen").first()
    if existing:
        print(f"[INFO] Demo interview for 'Maya Chen' already exists (ID: {existing.id}).")
        print(f"[LINK] View report at: http://localhost:5000/reports/{existing.id}")
        exit(0)

    demo_interview = Interview(
        candidate_name="Maya Chen",
        candidate_email="maya.chen@example.com",
        job_title="Content Creator / Writer",
        duration_minutes=15,
        difficulty="Intermediate",
        language="English",
        status=InterviewStatus.COMPLETED,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        started_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=45),
        completed_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=30),
        jd_text="""
Role: Content Creator & Strategist
Location: Remote
About the Role:
We are looking for a creative, data-informed Content Creator / Writer to lead our storytelling initiatives.
Responsibilities:
- Plan, write, and edit high-impact articles, social content, and monthly newsletters.
- Conduct keyword research and optimize content for search intent without sacrificing quality.
- Collaborate with product and design teams to ensure unified brand voice.
- Track content engagement analytics (dwell time, conversion rate, social reach) and iterate.
Required Skills:
- 3+ years in editorial writing, content marketing, or creative copywriting.
- Solid understanding of SEO principles and tools (e.g., Ahrefs, Semrush, Google Search Console).
- Experience working with content management systems (WordPress, Webflow, Notion).
- Strong communication, portfolio ownership, and editorial calendar management.
        """.strip(),
        resume_text="""
Maya Chen - Content Writer & Brand Storyteller
Summary: 4 years of experience producing high-engagement B2B and consumer content.
Work Experience:
- Senior Content Specialist at CreativePillar (2022 - Present):
  * Wrote 80+ in-depth technical blogs and customer case studies, driving a 120% YoY increase in organic search traffic.
  * Established the company's brand voice framework and editorial guidelines.
  * Designed monthly newsletter reaching 45,000 subscribers with an average 38% open rate.
- Content Creator at SparkDigital (2020 - 2022):
  * Managed social media copywriting and scheduled weekly editorial calendars across Twitter/X and LinkedIn.
  * Executed A/B tests on blog headlines, boosting average click-through rate by 22%.
Education: B.A. in English & Media Studies, University of Washington
Skills: Copywriting, SEO, Google Analytics, WordPress, Editorial Strategy, Brand Voice.
        """.strip(),
        interview_plan={
            "job_title": "Content Creator / Writer",
            "responsibilities": [
                "Plan, write, and edit high-impact articles and social copy",
                "Conduct keyword research and optimize for search intent",
                "Maintain brand voice consistency across all marketing assets",
                "Track content KPIs and iterate on underperforming assets"
            ],
            "required_competencies": [
                {
                    "id": "content_strategy",
                    "name": "Content Strategy & Editorial Planning",
                    "weight": 25,
                    "difficulty": "Intermediate",
                    "objective": "Assess structured editorial planning and cross-channel campaigns.",
                    "expected_evidence": "Concrete workflows, calendar cadence, and theme alignment."
                },
                {
                    "id": "audience_seo",
                    "name": "Audience Research & SEO Optimization",
                    "weight": 25,
                    "difficulty": "Intermediate",
                    "objective": "Evaluate keyword research and search intent understanding.",
                    "expected_evidence": "Clear balance of human value with on-page optimization."
                },
                {
                    "id": "writing_quality",
                    "name": "Writing Quality & Brand Voice",
                    "weight": 25,
                    "difficulty": "Advanced",
                    "objective": "Gauge clarity, tone adaptation, and narrative craftsmanship.",
                    "expected_evidence": "Explains tone modulation across different formats."
                },
                {
                    "id": "performance_analytics",
                    "name": "Content Performance & Analytics",
                    "weight": 25,
                    "difficulty": "Intermediate",
                    "objective": "Assess data-driven iteration and metric tracking.",
                    "expected_evidence": "Mentions dwell time, conversions, and diagnostic iteration."
                }
            ],
            "resume_skills_found": [
                "Technical blogging",
                "SEO keyword research",
                "Brand voice guidelines",
                "Newsletter creation",
                "A/B headline testing"
            ],
            "skill_gaps": [
                "Video script production",
                "Direct response ad copywriting"
            ],
            "sections": [
                {
                    "section_id": "intro",
                    "title": "Welcome & Introduction",
                    "target_duration_minutes": 2,
                    "questions": [
                        {
                            "id": "q1",
                            "question_text": "Hi Maya! Welcome. Could you share what excites you most about this Content Creator position?",
                            "competency_id": "writing_quality",
                            "expected_evidence": "Enthusiasm and career vision.",
                            "follow_up_guidance": "Ask about favorite written formats."
                        }
                    ]
                }
            ]
        },
        transcript=[
            {
                "role": "interviewer",
                "message": "Welcome Maya! I'm Alex, your AI interviewer. To kick off our conversation, could you walk me through your process for developing a quarterly editorial calendar?",
                "time_in_call_secs": 12
            },
            {
                "role": "candidate",
                "message": "Thanks Alex. I always start by auditing our previous quarter's top performers and interviewing our customer support and sales teams to uncover recurring pain points. Then, I map out core monthly themes and balance high-intent search queries with thought leadership pieces in a central Notion calendar.",
                "time_in_call_secs": 42
            },
            {
                "role": "interviewer",
                "message": "That's a thoughtful approach. How do you ensure your content ranks well on search engines without feeling robotic or overloaded with keywords?",
                "time_in_call_secs": 68
            },
            {
                "role": "candidate",
                "message": "My philosophy is that search algorithms reward reader engagement above all else. I focus on matching the exact search intent of the user, answering their primary question within the first two paragraphs, and using semantic subheadings. Keywords fit naturally into conversational phrasing rather than forced repetition.",
                "time_in_call_secs": 115
            },
            {
                "role": "interviewer",
                "message": "When you notice that a published piece has high impressions but low dwell time or high bounce rates, how do you diagnose and fix it?",
                "time_in_call_secs": 140
            },
            {
                "role": "candidate",
                "message": "I check the heatmaps and scroll depth first. Usually, a high bounce rate means either the title promised something the introduction didn't immediately deliver, or the page had readability friction like dense walls of text. I test revising the intro hook, adding visual callouts or charts, and clarifying the key takeaways.",
                "time_in_call_secs": 195
            },
            {
                "role": "interviewer",
                "message": "Excellent breakdown. Finally, how do you adapt your writing voice when shifting between technical educational guides and high-energy social copy?",
                "time_in_call_secs": 220
            },
            {
                "role": "candidate",
                "message": "I maintain a brand tone matrix. For technical guides, the tone is authoritative, concise, and structured. For social channels, I shorten sentence length, lead with a strong counter-intuitive insight, and adopt an approachable peer-to-peer conversational tone while maintaining the core brand values.",
                "time_in_call_secs": 265
            }
        ]
    )

    demo_report = InterviewReport(
        interview_id=demo_interview.id,
        overall_score=85,
        overall_summary="Maya displayed exceptional domain mastery in content strategy, audience intent research, and brand tone modulation. Her answers were concrete, structured, and backed by measurable methodologies.",
        competency_scores=[
            {
                "id": "content_strategy",
                "name": "Content Strategy & Editorial Planning",
                "score": 4,
                "weight": 25,
                "rationale": "Demonstrated a clear framework for customer-centric editorial calendars and theme scheduling.",
                "supporting_quote": "I audit previous performers and interview customer support and sales teams to uncover recurring pain points.",
                "improvement_recommendation": "Incorporate multi-channel repurposing workflows to turn pillar articles into bite-sized newsletters and audio snippets."
            },
            {
                "id": "audience_seo",
                "name": "Audience Research & SEO Optimization",
                "score": 5,
                "weight": 25,
                "rationale": "Outstanding balance of semantic search intent with natural, engaging storytelling.",
                "supporting_quote": "Search algorithms reward reader engagement above all else... keywords fit naturally into conversational phrasing.",
                "improvement_recommendation": "Explore programmatic SEO structures and topic clusters for enterprise domains."
            },
            {
                "id": "writing_quality",
                "name": "Writing Quality & Brand Voice",
                "score": 4,
                "weight": 25,
                "rationale": "Articulated a disciplined tone matrix approach to tailoring brand voice across technical and social formats.",
                "supporting_quote": "For technical guides, the tone is authoritative... for social channels, I shorten sentence length and lead with counter-intuitive insights.",
                "improvement_recommendation": "Incorporate executive thought leadership ghostwriting frameworks."
            },
            {
                "id": "performance_analytics",
                "name": "Content Performance & Analytics",
                "score": 4,
                "weight": 25,
                "rationale": "Sound diagnostic ability using scroll depth, heatmaps, and iterative hook testing.",
                "supporting_quote": "I check heatmaps and scroll depth first... I test revising the intro hook and adding visual callouts.",
                "improvement_recommendation": "Deepen experience with multi-touch revenue attribution and pipeline influence tracking."
            }
        ],
        strengths=[
            "Disciplined editorial planning rooted in cross-departmental customer research.",
            "Sophisticated audience-first SEO philosophy prioritizing engagement over keyword density.",
            "Proven ability to diagnose content drop-off and iterate systematically."
        ],
        improvement_areas=[
            "Multi-touch revenue attribution across extended B2B sales cycles.",
            "Multimedia content repurposing into video scripts and micro-podcasts."
        ],
        evidence=[
            "Explained systematic diagnosis of low dwell-time articles using scroll maps and intro restructuring.",
            "Shared cross-functional feedback loop with sales and support for topic discovery.",
            "Demonstrated brand tone matrix methodology for modulating voice across channels."
        ],
        suggested_practice_questions=[
            "How would you approach conducting a content prune across 300 legacy blog posts?",
            "Describe how you measure the pipeline revenue generated by an organic blog article.",
            "Walk through how you handle conflicting feedback from creative directors and product managers."
        ],
        recommendations=[
            "Study advanced Google Search Console performance data and semantic internal linking.",
            "Complete a masterclass on B2B revenue attribution and lead nurture sequencing.",
            "Experiment with AI-assisted research and draft outline acceleration."
        ],
        assessment_limitations="This evaluation is generated by AI based strictly on the spoken responses in the candidate's interview transcript. It provides developmental insights for human review and should not be used as an autonomous hiring decision."
    )

    db.session.add(demo_interview)
    db.session.flush()
    demo_report.interview_id = demo_interview.id
    db.session.add(demo_report)
    db.session.commit()

    print(f"[SUCCESS] Demo interview seeded successfully! ID: {demo_interview.id}")
    print(f"[LINK] View report at: http://localhost:5000/reports/{demo_interview.id}")
