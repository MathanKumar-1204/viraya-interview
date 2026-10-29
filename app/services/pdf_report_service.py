import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from app.models.interview import Interview, InterviewReport


class PDFReportService:
    """Generates clean, professional PDF reports using ReportLab."""

    @classmethod
    def generate_pdf(cls, interview: Interview, report: InterviewReport) -> io.BytesIO:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
        )

        styles = getSampleStyleSheet()

        # Custom styles
        primary_color = colors.HexColor("#4338ca")  # Indigo
        dark_text = colors.HexColor("#1e293b")
        muted_text = colors.HexColor("#64748b")
        light_bg = colors.HexColor("#f8fafc")
        border_color = colors.HexColor("#e2e8f0")

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=primary_color,
            spaceAfter=4,
        )

        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            textColor=muted_text,
            spaceAfter=15,
        )

        section_heading = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontSize=13,
            leading=17,
            textColor=primary_color,
            spaceBefore=14,
            spaceAfter=6,
        )

        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=9.5,
            leading=14,
            textColor=dark_text,
        )

        bold_style = ParagraphStyle(
            "BodyBold",
            parent=body_style,
            fontName="Helvetica-Bold",
        )

        quote_style = ParagraphStyle(
            "Quote",
            parent=body_style,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155"),
            fontName="Helvetica-Oblique",
            leftIndent=10,
        )

        disclaimer_style = ParagraphStyle(
            "Disclaimer",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=muted_text,
            alignment=TA_CENTER,
        )

        story = []

        # Header Title
        story.append(Paragraph("AI Interview Studio", title_style))
        story.append(Paragraph("Candidate Performance & Developmental Evaluation Report", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=12))

        # Metadata Block
        if isinstance(report.created_at, datetime):
            date_str = report.created_at.strftime("%B %d, %Y")
        elif isinstance(report.created_at, str):
            try:
                date_str = datetime.fromisoformat(report.created_at.replace("Z", "+00:00")).strftime("%B %d, %Y")
            except Exception:
                date_str = report.created_at
        else:
            date_str = datetime.now().strftime("%B %d, %Y")
        meta_data = [
            [
                Paragraph(f"<b>Candidate:</b> {interview.candidate_name}", body_style),
                Paragraph(f"<b>Role:</b> {interview.job_title}", body_style),
            ],
            [
                Paragraph(f"<b>Date:</b> {date_str}", body_style),
                Paragraph(f"<b>Duration:</b> {interview.duration_minutes} minutes ({interview.difficulty})", body_style),
            ],
            [
                Paragraph(f"<b>Status:</b> {interview.status.capitalize()}", body_style),
                Paragraph(f"<b>Overall Score:</b> <b><font color='#4338ca'>{report.overall_score}/100</font></b>", body_style),
            ]
        ]
        meta_table = Table(meta_data, colWidths=[260, 270])
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), light_bg),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 14))

        # Executive Summary
        story.append(Paragraph("Executive Summary", section_heading))
        story.append(Paragraph(report.overall_summary, body_style))
        story.append(Spacer(1, 12))

        # Performance Dimensions Breakdown Table
        story.append(Paragraph("Performance Dimensions & Real-Time Evaluation Rubric", section_heading))
        comp_rows = [
            [
                Paragraph("<b>Dimension</b>", bold_style),
                Paragraph("<b>Weight</b>", bold_style),
                Paragraph("<b>Score / Benchmark</b>", bold_style),
                Paragraph("<b>Findings, Evidence & Candidate Suggestions</b>", bold_style),
            ]
        ]

        for c in (report.competency_scores or []):
            name = c.get("name", "Performance Dimension")
            weight = f"{c.get('weight', 20)}%"
            score_val = c.get("score")
            benchmark = c.get("benchmark_level", "")
            
            if score_val is not None:
                display_num = score_val if score_val > 5 else round(score_val * 20)
                score_text = f"<b>{display_num}/100</b>"
                if benchmark:
                    score_text += f"<br/><font color='#4338ca' size='7'>{benchmark}</font>"
            else:
                score_text = "Not Assessed"
            
            findings = f"<b>Observation:</b> {c.get('rationale', '')}"
            if c.get("supporting_quote"):
                findings += f"<br/><font color='#475569'><i>\"{c.get('supporting_quote')}\"</i></font>"
            if c.get("improvement_recommendation"):
                findings += f"<br/><b>Candidate Actionable Suggestion:</b> {c.get('improvement_recommendation')}"

            comp_rows.append([
                Paragraph(f"<b>{name}</b>", body_style),
                Paragraph(weight, body_style),
                Paragraph(score_text, body_style),
                Paragraph(findings, body_style),
            ])

        comp_table = Table(comp_rows, colWidths=[130, 45, 65, 290])
        comp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(comp_table)
        story.append(Spacer(1, 14))

        # Strengths & Improvement Areas
        story.append(Paragraph("Demonstrated Strengths", section_heading))
        for s in (report.strengths or []):
            story.append(Paragraph(f"• {s}", body_style))
            story.append(Spacer(1, 2))

        story.append(Spacer(1, 8))
        story.append(Paragraph("Areas for Growth & Improvement", section_heading))
        for a in (report.improvement_areas or []):
            story.append(Paragraph(f"• {a}", body_style))
            story.append(Spacer(1, 2))

        story.append(Spacer(1, 8))
        story.append(Paragraph("Suggested Practice Questions", section_heading))
        for q in (report.suggested_practice_questions or []):
            story.append(Paragraph(f"• {q}", body_style))
            story.append(Spacer(1, 2))

        story.append(Spacer(1, 8))
        story.append(Paragraph("Actionable Recommendations & Next Steps", section_heading))
        for r in (report.recommendations or []):
            story.append(Paragraph(f"• {r}", body_style))
            story.append(Spacer(1, 2))

        # Disclaimer
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=0.5, color=border_color, spaceAfter=8))
        story.append(Paragraph(f"<b>Assessment Note:</b> {report.assessment_limitations}", disclaimer_style))

        doc.build(story)
        buffer.seek(0)
        return buffer
