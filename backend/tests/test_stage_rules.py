"""Rules-layer behaviour for next-step e-mails. No network, no LLM."""

from datetime import datetime, timezone

import pytest

from backend.service.classification_service import (
    KIND_ASSESSMENT,
    KIND_CONFIRMATION,
    KIND_INTERVIEW,
    KIND_OTHER,
    KIND_REJECTION,
    classify_email,
    looks_like_next_stage,
    run_rules,
)

FROM = "Acme Careers <no-reply@acme.com>"
RECEIVED = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)


def decide(subject, body, from_header=FROM):
    return classify_email(
        from_header, subject, body, use_llm=False, received_at=RECEIVED
    )


ASSESSMENTS = [
    "Please complete the online assessment linked below within 5 days.",
    "The next step is a take-home assignment; you can start whenever you are ready.",
    "We'd like you to complete a short coding challenge before we talk.",
    "Your HackerRank test is ready. The link expires in 72 hours.",
    "Please take the technical assessment at your convenience.",
    "Attached is a work sample exercise for the role.",
]


@pytest.mark.parametrize("body", ASSESSMENTS)
def test_assessment_wording_is_detected(body):
    assert decide("Next step at Acme", body).kind == KIND_ASSESSMENT


INTERVIEWS = [
    "We would like to invite you to an interview with the team.",
    "Let's schedule a 30 minute call - please pick a time that works for you.",
    "Your interview has been scheduled for next week.",
    "We'd like to set up a phone screen with our recruiter.",
    "Please share your availability for a technical interview.",
    "Book a time with the hiring manager here: https://calendly.com/acme/intro",
]


@pytest.mark.parametrize("body", INTERVIEWS)
def test_interview_wording_is_detected(body):
    assert decide("Next step at Acme", body).kind == KIND_INTERVIEW


def test_interview_outranks_an_assessment_when_both_appear():
    body = (
        "We would like to invite you to a technical interview. It will include "
        "a short coding exercise, so bring your laptop."
    )
    assert looks_like_next_stage("Interview at Acme", body) == KIND_INTERVIEW


def test_next_step_outranks_the_confirmation_wording_it_opens_with():
    body = (
        "Thank you for applying to Acme! We have received your application. "
        "The next step is a short online assessment - please complete it within "
        "48 hours."
    )
    assert decide("Thank you for applying to Acme", body).kind == KIND_ASSESSMENT


def test_a_rejection_that_mentions_the_interview_is_still_a_rejection():
    body = (
        "Thank you for taking the time to interview with us. After careful "
        "consideration we have decided to move forward with other candidates."
    )
    assert decide("Update on your application", body).kind == KIND_REJECTION


HEDGED = [
    # describing the process, not inviting anyone
    ("Thank you for applying to Acme. Candidates who advance will be invited to "
     "an interview with the hiring manager."),
    ("Thanks for applying! If your background is a match we will reach out to "
     "schedule a call."),
    ("Thank you for your application. Our hiring process is a phone screen "
     "followed by a technical interview."),
]


@pytest.mark.parametrize("body", HEDGED)
def test_describing_the_process_is_not_an_invitation(body):
    assert decide("Thank you for applying to Acme", body).kind == KIND_CONFIRMATION


def test_a_job_alert_is_still_nothing():
    assert decide(
        "10 new jobs for you",
        "Here are jobs matching your saved search.",
        from_header="LinkedIn <jobs-noreply@linkedin.com>",
    ).kind == KIND_OTHER


def test_the_interview_time_rides_along_with_the_decision():
    body = (
        "We would like to invite you to an interview on March 17, 2026 at "
        "2:00 PM UTC. The conversation will run 45 minutes."
    )
    decision = decide("Interview invitation - Acme", body)
    assert decision.kind == KIND_INTERVIEW
    assert decision.is_advance
    assert decision.when == datetime(2026, 3, 17, 14, 0, tzinfo=timezone.utc)
    assert decision.duration.total_seconds() == 45 * 60


def test_an_assessment_deadline_is_read_from_the_relative_wording():
    body = "Please complete the online assessment within 48 hours."
    decision = decide("Your Acme assessment", body)
    assert decision.kind == KIND_ASSESSMENT
    assert decision.when == datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)


def test_a_dateless_invite_still_advances_the_application():
    decision = decide(
        "Next steps at Acme",
        "We would like to invite you to an interview. More details to follow.",
    )
    assert decision.kind == KIND_INTERVIEW
    assert decision.when is None
    assert decision.duration is None


def test_only_a_confirmation_carries_no_schedule():
    decision = decide(
        "Thank you for applying to Acme",
        "We have received your application for Backend Engineer on March 17, 2026.",
    )
    assert decision.kind == KIND_CONFIRMATION
    assert decision.when is None


def test_two_phrases_and_a_known_company_skip_the_model():
    rule = run_rules(
        FROM,
        "Interview invitation for the Backend Engineer role at Acme",
        "We would like to invite you to an interview. Please pick a time that works.",
    )
    assert rule.kind == KIND_INTERVIEW
    assert rule.confidence == "high"
    assert rule.company == "Acme"


def test_one_thin_phrase_gets_a_second_opinion():
    rule = run_rules(FROM, "Next steps", "Please share your availability for a call.")
    assert rule.kind == KIND_INTERVIEW
    assert rule.confidence == "low"


def test_the_assessment_vendor_never_becomes_the_company():
    rule = run_rules(
        "Acme via HackerRank <noreply@hackerrank.com>",
        "Your Acme coding challenge is ready",
        "Please complete the online assessment for Acme within 5 days.",
    )
    assert rule.kind == KIND_ASSESSMENT
    assert (rule.company or "").lower() != "hackerrank"
