"""Rules-layer behaviour for rejection e-mails. No network, no LLM."""

import pytest

from backend.service.classification_service import (
    KIND_CONFIRMATION,
    KIND_INTERVIEW,
    KIND_OTHER,
    KIND_REJECTION,
    classify_email,
    looks_like_rejection,
    run_rules,
)

FROM = "Acme Careers <no-reply@acme.com>"


def kind(subject, body, from_header=FROM):
    return classify_email(from_header, subject, body, use_llm=False).kind


REJECTIONS = [
    "After careful consideration we have decided to move forward with other candidates.",
    "We regret to inform you that you were not selected for this position.",
    "We will not be moving forward with your application at this time.",
    "Your application was not successful on this occasion.",
    "We have decided not to proceed with your candidacy.",
    "We chose to pursue other candidates whose experience more closely matches the role.",
    "Your application is no longer under consideration.",
    "This position has been filled.",
    "Unfortunately, we received many qualified applicants for this role.",
]


@pytest.mark.parametrize("body", REJECTIONS)
def test_rejection_wording_is_detected(body):
    assert kind("Your application to Acme", body) == KIND_REJECTION


def test_rejection_outranks_the_confirmation_wording_it_opens_with():
    body = (
        "Thank you for your interest in Acme and for taking the time to apply. "
        "After careful review we have decided to move forward with other candidates."
    )
    assert kind("Thank you for applying to Acme", body) == KIND_REJECTION


def test_plain_confirmation_is_still_a_confirmation():
    body = "Thank you for applying to Acme. We have received your application for Software Engineer Intern."
    assert kind("Thank you for applying to Acme", body) == KIND_CONFIRMATION


def test_single_soft_signal_is_not_enough_on_its_own():
    body = "Thanks for applying to Acme! Unfortunately our portal was slow today."
    assert kind("Thank you for applying to Acme", body) == KIND_CONFIRMATION
    assert looks_like_rejection("Thank you for applying to Acme", body) == (False, "none")


def test_two_soft_signals_are_enough():
    body = (
        "We appreciate the time you took to apply. We received many qualified "
        "applicants and will keep your resume on file for future openings."
    )
    assert looks_like_rejection("An update", body)[0] is True


def test_interview_invite_is_not_a_rejection():
    body = "We would love to schedule a 30 minute conversation. Please pick a time that works."
    assert kind("Next steps", body) == KIND_INTERVIEW


def test_job_alert_is_neither():
    assert kind(
        "10 new jobs for you",
        "Here are jobs matching your saved search.",
        from_header="LinkedIn <jobs-noreply@linkedin.com>",
    ) == KIND_OTHER


def test_rejection_keeps_company_and_role():
    rule = run_rules(
        FROM,
        "Your application for the Backend Engineer position at Acme",
        "We regret to inform you that we are moving forward with other candidates.",
    )
    assert rule.kind == KIND_REJECTION
    assert rule.company == "Acme"
    assert rule.role == "Backend Engineer"
    assert rule.is_rejection and not rule.is_application


# Verbatim from a real Amazon decline that the first cut of the rules read as a
# confirmation: it opens with "Thank you for your application", says no with
# "decided not to progress" (a verb the strong list did not have), and arrives
# from the employer's own domain - which handed it a high-confidence company and
# so skipped the LLM that would have caught it.
AMAZON_FROM = "noreply@mail.amazon.jobs"
AMAZON_SUBJECT = "Amazon application: Status update"
AMAZON_BODY = (
    "Hi Jerison, "
    "Thank you for your application for the position of Software Development "
    "Engineer Internship - Fall 2026 (US) (ID: 3012345). After careful "
    "consideration, we've decided not to progress with your application for "
    "this role. While we're unable to share additional details about this "
    "decision, we'd like to keep in touch regarding future job opportunities. "
    "Thanks again for your interest in working at Amazon. "
    "Best regards, Amazon Recruiting Team"
)


def test_employer_own_domain_decline_is_a_rejection():
    rule = run_rules(AMAZON_FROM, AMAZON_SUBJECT, AMAZON_BODY)
    assert rule.kind == KIND_REJECTION
    assert rule.company == "Amazon"
    assert rule.role.startswith("Software Development Engineer")


def test_soft_decline_signal_forfeits_the_llm_skipping_shortcut():
    """A confirmation carrying one soft decline hint must not be marked
    high-confidence, or the sync never sends it to the model."""
    body = (
        "Thank you for applying to Acme. Unfortunately our careers portal was "
        "slow while you submitted."
    )
    rule = run_rules("Acme <no-reply@acme.com>", "Thank you for applying", body)
    assert rule.kind == KIND_CONFIRMATION
    assert rule.confidence == "low"


def test_clean_confirmation_keeps_the_shortcut():
    body = "Thank you for applying to Acme. We have received your application."
    rule = run_rules("Acme <no-reply@acme.com>", "Thank you for applying", body)
    assert rule.kind == KIND_CONFIRMATION
    assert rule.confidence == "high"


# "keep in touch about future opportunities" is rejection boilerplate AND the
# way a recruiter opens a cold pitch, so a soft-signals-only verdict needs some
# sign the mail is about an application the recipient actually made.
NOT_REJECTIONS = [
    ("Jane <jane@acmerecruiting.com>", "Opportunities at Acme",
     "I came across your profile. I'd love to keep in touch about future job "
     "opportunities at Acme."),
    ("Sam <sam@globex.com>", "Great chatting",
     "Great speaking today. Let's keep in touch regarding future roles on the team."),
    ("Acme <news@acme.com>", "Acme monthly",
     "See our future openings and keep in touch for news about the company."),
]


@pytest.mark.parametrize(("from_header", "subject", "body"), NOT_REJECTIONS)
def test_soft_phrases_without_an_application_are_not_declines(from_header, subject, body):
    assert run_rules(from_header, subject, body).kind != KIND_REJECTION


def test_ats_sender_does_not_become_the_company():
    rule = run_rules(
        "Acme via Greenhouse <no-reply@acme.greenhouse.io>",
        "Update on your application",
        "We have decided to move forward with other candidates.",
    )
    assert rule.kind == KIND_REJECTION
    assert rule.company == "Acme"
