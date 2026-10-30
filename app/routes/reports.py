from flask import Blueprint, render_template, abort, send_file, flash, redirect, url_for, session
from app.models.interview import Interview, InterviewReport
from app.services.pdf_report_service import PDFReportService
from app.services.session_store import get_or_restore_report
from app.routes.auth import login_required
from app.extensions import db

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/<interview_id>")
def view_report(interview_id: str):
    """View generated evaluation report (strictly restricted to Administrator)."""
    # Candidates are never shown scores or evaluation reports
    if not session.get("is_admin") and "user_id" not in session:
        return redirect(url_for("interviews.interview_completed", interview_id=interview_id))

    interview, report = get_or_restore_report(interview_id)
    if not interview:
        abort(404, description="Interview not found.")

    if not report:
        flash("No evaluation report is available for this interview yet.", "warning")
        return redirect(url_for("admin.admin_dashboard"))

    return render_template(
        "report.html",
        interview=interview,
        report=report
    )


@reports_bp.route("/<interview_id>/download")
def download_pdf(interview_id: str):
    """Download evaluation report as a styled PDF (strictly restricted to Administrator)."""
    if not session.get("is_admin") and "user_id" not in session:
        return redirect(url_for("interviews.interview_completed", interview_id=interview_id))

    interview, report = get_or_restore_report(interview_id)
    if not interview or not report:
        abort(404, description="Report not found.")

    pdf_buffer = PDFReportService.generate_pdf(interview, interview.report)
    safe_name = interview.candidate_name.replace(" ", "_")
    filename = f"Evaluation_Report_{safe_name}_{interview.id[:8]}.pdf"

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )
