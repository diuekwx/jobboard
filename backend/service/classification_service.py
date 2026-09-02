"""Decide whether an e-mail is a job-application confirmation, and for whom.

Two layers:

1. ``run_rules`` - deterministic. Sender domain is the primary company signal;
   ATS vendor domains (Greenhouse, Lever, Workday, ...) are explicitly *not*
   treated as the employer. Cheap, no network, no cost.
2. ``classify_with_llm`` - a single ``gemini-2.5-flash`` call with a structured
   (Pydantic) JSON response, used only when the rules are not high-confidence.

``classify_email`` orchestrates the two and returns a :class:`Decision`.
"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule layer
# ---------------------------------------------------------------------------

GENERIC_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com",
    "ymail.com", "icloud.com", "me.com", "aol.com", "protonmail.com",
    "proton.me", "live.com", "msn.com", "gmx.com", "mail.com",
}

# Applicant-tracking / recruiting platforms: the sender domain is the vendor,
# never the employer. Matched against the full domain and its registered
# (last-two-label) form.
ATS_DOMAINS = {
    "greenhouse.io", "greenhouse-mail.io", "us.greenhouse.io",
    "lever.co", "hire.lever.co", "jobs.lever.co",
    "myworkday.com", "workday.com", "myworkdayjobs.com", "myworkdaysite.com",
    "ashbyhq.com",
    "icims.com",
    "smartrecruiters.com", "smartrecruitersmail.com",
    "workable.com", "workablemail.com",
    "bamboohr.com",
    "jobvite.com", "jobvitemail.com",
    "taleo.net", "successfactors.com",
    "paylocity.com", "paycomonline.net", "adp.com",
    "hire.google.com", "notify.hire.google.com",
    "paradox.ai", "olivia.paradox.ai",
    "eightfold.ai", "beamery.com", "gem.co", "teamtailor.com",
    "teamtailormail.com", "rippling.com", "ripplingmail.com", "breezy.hr",
    "recruitee.com", "join.com", "pinpointhq.com", "dover.com",
}

_CONFIRMATION_PATTERNS = [
    r"thank you for applying",
    r"thanks for applying",
    r"thank you for your (?:application|interest)",
    r"appreciate your interest",
    r"application (?:has been |was )?(?:received|submitted|completed)",
    r"we(?:'ve| have) received your application",
    r"we(?:'ve| have)? got your application",
    r"your application (?:to|for|with|has been|was)",
    r"application confirmation",
    r"successfully (?:applied|submitted)",
    r"received your application for",
    r"has been (?:received|submitted) successfully",
]

_GENERIC_NAME = re.compile(
    r"\b(?:no[-\s]?reply|noreply|donotreply|do[-\s]?not[-\s]?reply|recruit(?:ing|ment)?|"
    r"talent(?:\s+acquisition)?|careers?|jobs|hr|human\s+resources|hiring(?:\s+team)?|"
    r"notifications?|team|people\s+ops|peopleops|candidate|applicant|workday|greenhouse|"
    r"lever|ashby|icims|smartrecruiters|workable)\b",
    re.I,
)

_NAME_SUFFIX = re.compile(
    r"[\s,\-|]*(?:careers?|recruiting|recruitment|talent(?:\s+acquisition)?|hr|"
    r"hiring\s+team|people\s+team|jobs|team|notifications?)\s*$",
    re.I,
)

_ROLE_PHRASE = re.compile(
    r"(?:for the|for a|for our|to the|as an?|position of|role of|regarding the)\s+"
    r"(?P<role>[A-Za-z0-9][\w /&+.\-]{2,60}?)\s+"
    r"(?:position|role|opening|opportunity|req|requisition|at|with|\()",
    re.I,
)
_ROLE_IN_SUBJECT = re.compile(r"^(?P<role>[\w /&+.\-]{3,60}?)\s+(?:at|@|-|–|—|with)\s+\S", re.I)

_COMPANY_PHRASE = re.compile(
    r"\b(?:applying to|application (?:to|at|with|for a position at)|position at|role at|"
    r"opportunity at|interest in(?: joining| working (?:at|for))?|interest in|joining)\s+"
    r"(?P<co>[A-Z][\w&.\-]*(?:\s+[A-Z0-9][\w&.\-]*){0,3})",
)
_COMPANY_AT_END = re.compile(r"\bat\s+(?P<co>[A-Z][\w&.\-]*(?:\s+[A-Z0-9][\w&.\-]*){0,3})\s*[!.]?\s*$")


@dataclass
class RuleResult:
    is_application: bool
    company: Optional[str]
    role: Optional[str]
    confidence: str  # "high" | "low"


def parse_from(value: str):
    """``"Acme Careers <no-reply@acme.com>"`` -> ``("Acme Careers", "no-reply@acme.com", "acme.com")``."""
    if not value:
        return "", "", ""
    m = re.match(
        r'\s*(?:"?(?P<name>[^"<]*?)"?\s*)?<?(?P<email>[^<>@\s]+@[^<>\s]+?)>?\s*$', value
    )
    if not m:
        return value.strip(), "", ""
    name = (m.group("name") or "").strip().strip('"').strip()
    email = (m.group("email") or "").strip().lower().rstrip(">")
    domain = email.split("@", 1)[1] if "@" in email else ""
    return name, email, domain


def _registered_domain(domain: str) -> str:
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def is_ats_domain(domain: str) -> bool:
    if not domain:
        return False
    return domain in ATS_DOMAINS or _registered_domain(domain) in ATS_DOMAINS


def _clean_name(raw: str) -> Optional[str]:
    name = re.sub(r"\s+", " ", raw or "").strip(" \t\r\n-–—|·•,")
    name = _NAME_SUFFIX.sub("", name).strip(" \t\r\n-–—|·•,")
    if not name or len(name) < 2 or _GENERIC_NAME.search(name):
        return None
    return name


def _company_from_domain(domain: str) -> Optional[str]:
    if not domain or domain in GENERIC_MAIL_DOMAINS or is_ats_domain(domain):
        return None
    labels = domain.split(".")
    label = labels[-2] if len(labels) >= 2 else labels[0]
    # step past mail-infra subdomains that shadow the brand
    if label in ("mail", "email", "smtp", "mailer", "notify", "notifications",
                 "e", "em", "send", "sendgrid", "mkto", "hs"):
        label = labels[-3] if len(labels) >= 3 else label
    if len(label) < 2:
        return None
    return label.replace("-", " ").title()


def _company_from_ats_subdomain(domain: str) -> Optional[str]:
    """``acme.greenhouse.io`` -> ``"Acme"`` (the tenant slug on an ATS host)."""
    for ats in ATS_DOMAINS:
        if domain.endswith("." + ats):
            slug = domain[: -(len(ats) + 1)].split(".")[-1]
            if slug and slug not in ("mail", "email", "jobs", "hire", "us", "eu",
                                     "app", "no-reply", "noreply", "www", "careers"):
                return slug.replace("-", " ").title()
    return None


def _guess_role(subject: str, body: str) -> Optional[str]:
    for text in (subject or "", (body or "")[:800]):
        m = _ROLE_PHRASE.search(text)
        if m:
            role = re.sub(r"\s+", " ", m.group("role")).strip(" .-")
            if role and not _GENERIC_NAME.search(role):
                return role
    if subject:
        m = _ROLE_IN_SUBJECT.match(subject.strip())
        if m:
            role = m.group("role").strip()
            if role and not _GENERIC_NAME.search(role):
                return role
    return None


def _guess_company(name: str, domain: str, subject: str, body: str):
    """Returns ``(company, confidence)`` where confidence is ``"high"`` | ``"low"``."""
    for fn in (_company_from_domain, _company_from_ats_subdomain):
        c = fn(domain)
        if c:
            return c, "high"

    cleaned = _clean_name(name)
    if cleaned:
        return cleaned, "low"

    for text in (subject or "", (body or "")[:1000]):
        for rx in (_COMPANY_PHRASE, _COMPANY_AT_END):
            m = rx.search(text)
            if m:
                co = re.sub(r"\s+", " ", m.group("co")).strip(" .-")
                if co and not _GENERIC_NAME.search(co):
                    return co, "low"
    return None, "low"


def looks_like_confirmation(subject: str, body: str) -> bool:
    hay = f"{subject or ''}\n{(body or '')[:1500]}".lower()
    return any(re.search(p, hay) for p in _CONFIRMATION_PATTERNS)


def run_rules(from_header: str, subject: str, body: str) -> RuleResult:
    name, _email, domain = parse_from(from_header)
    is_conf = looks_like_confirmation(subject, body)
    from_ats = is_ats_domain(domain)
    company, conf = _guess_company(name, domain, subject, body)
    role = _guess_role(subject, body)

    is_app = is_conf or (from_ats and bool(company))
    if not is_app:
        return RuleResult(False, company, role, "low")

    confidence = "high" if (is_conf and company and conf == "high") else "low"
    return RuleResult(True, company, role, confidence)


# ---------------------------------------------------------------------------
# LLM layer
# ---------------------------------------------------------------------------

try:  # optional dependency / optional feature
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore

    def Field(*_a, **_kw):  # type: ignore
        return None

CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "gemini-2.5-flash")

_llm_client = None
_llm_disabled = False

_LLM_SYSTEM = (
    "You classify emails for a job-application tracker. You are given one email's "
    "From header, Subject, and a plain-text excerpt.\n\n"
    "Decide whether it is a confirmation that THE RECIPIENT submitted a job "
    "application - an automated acknowledgement from an employer or its applicant "
    "tracking system. These are NOT confirmations: job alerts and newsletters, "
    "recruiter cold outreach, interview scheduling, assessment invites, rejections, "
    "and offers.\n\n"
    "Report `company` as the employer the person applied to - NEVER the ATS vendor "
    "(Greenhouse, Lever, Workday, Ashby, iCIMS, SmartRecruiters, Workable, and the "
    "like). Use an empty string for `company` or `role` when you cannot tell. Keep "
    "`role` short, e.g. \"Software Engineer Intern\". Set `confidence` to how sure "
    "you are that this is an application confirmation."
)


class EmailClassification(BaseModel):  # type: ignore[misc]
    is_application_confirmation: bool = Field(
        description="True only if this email confirms the recipient submitted a job application."
    )
    company: str = Field(
        description="Employer the recipient applied to (never the ATS vendor). Empty string if unknown."
    )
    role: str = Field(
        description='Short job title, e.g. "Software Engineer Intern". Empty string if unknown.'
    )
    confidence: str = Field(
        description='One of "high", "medium", "low" - how sure this is an application confirmation.'
    )


def _get_client():
    global _llm_client, _llm_disabled
    if _llm_disabled:
        return None
    if _llm_client is None:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set - LLM email classification disabled")
            _llm_disabled = True
            return None
        try:
            from google import genai

            _llm_client = genai.Client(api_key=api_key)
        except Exception:
            logger.exception("could not initialise Gemini client - LLM classification disabled")
            _llm_disabled = True
            return None
    return _llm_client


def classify_with_llm(from_header: str, subject: str, body: str) -> Optional[EmailClassification]:
    client = _get_client()
    if client is None:
        return None

    content = f"From: {from_header}\nSubject: {subject}\n\n{(body or '')[:2500]}"
    try:
        from google.genai import types

        resp = client.models.generate_content(
            model=CLASSIFIER_MODEL,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=_LLM_SYSTEM,
                response_mime_type="application/json",
                response_schema=EmailClassification,
                temperature=0.0,
                max_output_tokens=512,
                # this is a mechanical extraction task - no need to burn tokens "thinking"
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        parsed = resp.parsed
        if parsed is None:
            logger.warning("Gemini returned no parseable classification (subject=%r)", subject)
        return parsed
    except Exception:
        logger.exception("LLM classification failed (subject=%r)", subject)
        return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    is_application: bool
    company: Optional[str]
    role: Optional[str]
    needs_review: bool
    method: str  # "rules" | "llm" | "rules+llm"


def classify_email(from_header: str, subject: str, body: str) -> Decision:
    rule = run_rules(from_header, subject, body)

    # Fast path: rules are confident enough to act without spending a token.
    if rule.is_application and rule.company and rule.confidence == "high":
        return Decision(True, rule.company, rule.role, False, "rules")

    llm = classify_with_llm(from_header, subject, body)

    if llm is not None:
        method = "rules+llm" if rule.is_application else "llm"
        if llm.is_application_confirmation:
            company = (llm.company or "").strip() or rule.company
            role = (llm.role or "").strip() or rule.role
            needs_review = (not company) or (llm.confidence or "").lower() == "low"
            return Decision(True, company, role, needs_review, method)
        # LLM says it isn't an application; trust it (the confident-rule case
        # already returned above).
        return Decision(False, None, None, False, method)

    # LLM unavailable - fall back to the rule verdict, flagged for a human look.
    if rule.is_application:
        return Decision(True, rule.company, rule.role, True, "rules")
    return Decision(False, None, None, False, "rules")
