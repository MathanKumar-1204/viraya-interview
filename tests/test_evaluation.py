import pytest
from app.services.evaluation_service import EvaluationService, CompetencyScoreItem
from app.services.transcript_service import TranscriptService, TranscriptValidationError
from app.models.interview import InterviewStatus


def test_calculate_weighted_overall_score():
    scores = [
        CompetencyScoreItem(
            id="c1",
            name="Strategy",
            score=4,  # (4/5)*40 = 32
            weight=40,
            rationale="Good",
            improvement_recommendation="Keep going"
        ),
        CompetencyScoreItem(
            id="c2",
            name="SEO",
            score=5,  # (5/5)*30 = 30
            weight=30,
            rationale="Great",
            improvement_recommendation="None"
        ),
        CompetencyScoreItem(
            id="c3",
            name="Writing",
            score=3,  # (3/5)*30 = 18
            weight=30,
            rationale="Okay",
            improvement_recommendation="Practice"
        )
    ]
    # Total points = 32 + 30 + 18 = 80 out of 100
    overall = EvaluationService.calculate_weighted_overall_score(scores)
    assert overall == 80


def test_calculate_weighted_score_with_not_assessed():
    scores = [
        CompetencyScoreItem(
            id="c1",
            name="Strategy",
            score=4,  # (4/5)*50 = 40
            weight=50,
            rationale="Good",
            improvement_recommendation="None"
        ),
        CompetencyScoreItem(
            id="c2",
            name="Analytics",
            score=None,  # Not Assessed!
            weight=50,
            rationale="Topic not reached in interview",
            improvement_recommendation="N/A"
        )
    ]
    # Weight of assessed is 50. Weighted points = 40. Normalized overall = (40 / 50) * 100 = 80
    overall = EvaluationService.calculate_weighted_overall_score(scores)
    assert overall == 80


def test_transcript_validation_empty_fails():
    with pytest.raises(TranscriptValidationError) as exc:
        TranscriptService.validate_transcript_for_evaluation([])
    assert "empty or too brief" in str(exc.value).lower()


def test_transcript_validation_no_candidate_words_fails():
    transcript = [
        {"role": "interviewer", "message": "Hello, welcome to the interview."},
        {"role": "candidate", "message": "Hi."}  # Only 1 word!
    ]
    with pytest.raises(TranscriptValidationError) as exc:
        TranscriptService.validate_transcript_for_evaluation(transcript)
    assert "insufficient candidate responses" in str(exc.value).lower()


def test_transcript_validation_success():
    transcript = [
        {"role": "interviewer", "message": "Hello! Can you describe your past content marketing achievements?"},
        {"role": "candidate", "message": "Certainly. In my last position I developed a technical blog series that generated over 25,000 monthly visits."}
    ]
    # Should not raise
    TranscriptService.validate_transcript_for_evaluation(transcript)


def test_finalize_and_idempotency(client, prepared_interview):
    # Call 1: Finalize
    res1 = client.post(
        f"/api/interviews/{prepared_interview.id}/finalize",
        json={"conversation_id": "test_conv_123"}
    )
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert data1["success"] is True
    assert data1["status"] == InterviewStatus.COMPLETED
    assert "report_url" in data1

    # Call 2: Duplicate finalize call should succeed idempotently
    res2 = client.post(
        f"/api/interviews/{prepared_interview.id}/finalize",
        json={"conversation_id": "test_conv_123"}
    )
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["success"] is True
    assert data2["status"] == InterviewStatus.COMPLETED


def test_view_report_page(client, prepared_interview):
    # Finalize to create report
    client.post(f"/api/interviews/{prepared_interview.id}/finalize")

    # Render report page
    res = client.get(f"/reports/{prepared_interview.id}")
    assert res.status_code == 200
    assert b"Candidate Evaluation Report" in res.data
    assert b"Executive Performance Summary" in res.data


def test_download_report_pdf(client, prepared_interview):
    client.post(f"/api/interviews/{prepared_interview.id}/finalize")

    res = client.get(f"/reports/{prepared_interview.id}/download")
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "application/pdf"
    assert len(res.data) > 1000  # Generated PDF has bytes
