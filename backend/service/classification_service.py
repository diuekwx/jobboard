"""Decide what a job-related e-mail *is* - a confirmation, a rejection, or
neither - and for whom.

Two layers:

1. ``run_rules`` - deterministic. Sender domain is the primary company signal;
   ATS vendor domains (Greenhouse, Lever, Workday, ...) are explicitly *not*
   treated as the employer. Cheap, no network, no cost.
2. ``classify_with_llm`` - a single structured-JSON call, used only when the
   rules are not high-confidence.

``classify_email`` orchestrates the two and returns a :class:`Decision` whose
``kind`` is one of :data:`KIND_CONFIRMATION`, :data:`KIND_REJECTION` or
:data:`KIND_OTHER`. Rejections outrank confirmations: a rejection that opens
with "Thank you for your interest in Acme" is still a rejection.
"""

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.service import schedule_parser

logger = logging.getLogger(__name__)

# What an e-mail turned out to be.
KIND_CONFIRMATION = "confirmation"  # "we received your application"
KIND_REJECTION = "rejection"        # "we're moving forward with other candidates"
KIND_ASSESSMENT = "assessment"      # "please complete this online assessment"
KIND_INTERVIEW = "interview"        # "let's schedule an interview" / "you're booked for"
KIND_OTHER = "other"                # anything else: alerts, offers, noise

KINDS = (KIND_CONFIRMATION, KIND_REJECTION, KIND_ASSESSMENT, KIND_INTERVIEW, KIND_OTHER)

# The two kinds that move a live application into "In Process", best stage last.
ADVANCING_KINDS = (KIND_ASSESSMENT, KIND_INTERVIEW)

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

# Assessment platforms and interview schedulers. Same rule as an ATS: the mail
# comes from the vendor, so the sender domain says nothing about the employer.
VENDOR_DOMAINS = {
    "hackerrank.com", "hackerrankforwork.com", "hackerearth.com",
    "codility.com", "codesignal.com", "coderbyte.com", "codesubmit.io",
    "devskiller.com", "testgorilla.com", "imocha.io", "vervoe.com",
    "byteboard.dev", "woven.teams", "karat.com", "qualified.io",
    "hirevue.com", "spark-hire.com", "sparkhire.com", "willo.video",
    "myinterview.com", "pymetrics.com", "plum.io", "traitify.com",
    "calendly.com", "goodtime.io", "modernloop.io", "prelude.co",
    "cronofy.com", "hire.withgoogle.com", "x.ai", "chilipiper.com",
    "savvycal.com", "cal.com", "youcanbook.me",
}

ATS_DOMAINS |= VENDOR_DOMAINS

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

# Rejection wording, split by how much a single hit is worth.
#
# A "strong" phrase is one that essentially only appears in a decline. A "weak"
# phrase is rejection-flavoured but also shows up in interview invites and
# newsletters ("we wish you the best"), so two of them are needed before the
# rules will call it on their own - otherwise the LLM gets the final say.
_REJECTION_STRONG_PATTERNS = [
    r"we regret to inform",
    r"regret to (?:inform|advise|let you know)",
    r"(?:decided|chosen|elected|opted) (?:to )?(?:move|go|proceed|continue) (?:forward|ahead|on) with (?:other|another)",
    r"(?:moving|move|proceeding|going) (?:forward|ahead) with other (?:candidates|applicants)",
    r"(?:will |we )?(?:are |will )?not (?:be )?(?:moving|move|proceeding|progressing|continuing) (?:forward|ahead|you)",
    r"not (?:be )?(?:moving|proceeding) (?:forward|ahead) with your (?:application|candidacy)",
    r"(?:decided|chosen|elected|opted) not to (?:move|proceed|continue|advance|progress|go)",
    r"(?:pursue|pursuing|move forward with) other (?:candidates|applicants|applications)",
    r"other candidates whose (?:qualifications|experience|background|skills)",
    r"(?:your )?application (?:was|has been|is) (?:unfortunately )?(?:not successful|unsuccessful)",
    r"(?:were|was) not selected (?:for|to)",
    r"not (?:been )?selected (?:for|to move|to advance|to continue)",
    r"no longer (?:be )?(?:under|in) consideration",
    r"not (?:be )?(?:moving|considered) (?:you )?(?:further|forward) (?:for|at)",
    r"we (?:are|will be|have decided to be) unable to (?:offer|move|proceed|progress)",
    r"(?:we (?:have|'ve) )?(?:filled|closed) (?:this|the) (?:position|role|req|requisition)",
    r"(?:this|the) (?:position|role|req|requisition) (?:has been|is now) (?:filled|closed)",
    r"(?:has been|is) no longer (?:open|available)",
    r"decided to move forward with (?:a|other) candidate",
    r"not (?:a|the) (?:right|best) (?:fit|match) (?:for|at) (?:this|the) (?:time|role|position)",
    r"will not be (?:extending|advancing|inviting)",
    r"(?:unable|not able) to (?:progress|advance|move forward with) your "
    r"(?:application|candidacy)",
    r"not (?:be )?progressing (?:with )?your (?:application|candidacy)",
]

_REJECTION_WEAK_PATTERNS = [
    r"unfortunately",
    r"we (?:wish|want to wish) you (?:the )?(?:best|success|good luck|well)",
    r"(?:best|good) (?:of )?luck (?:in|with|on) your (?:job |career )?(?:search|hunt|endeavors|endeavours)",
    r"keep your (?:resume|résumé|cv|application|profile|details|information) on file",
    r"encourage you to (?:apply|re-?apply|continue to apply)",
    r"(?:many|a large number of|numerous|highly) (?:qualified )?(?:applicants|candidates|applications)",
    r"(?:this|the) (?:decision|process) was (?:not )?(?:an? )?(?:easy|difficult)",
    r"(?:we|i) appreciate the time you (?:took|invested|spent)",
    r"(?:will|we)(?:'ll| will)? (?:not )?(?:be )?keep(?:ing)? (?:you )?in mind for future",
    r"future (?:\w+ )?(?:openings|opportunities|roles|positions)",
    r"keep in (?:touch|contact)(?: with you)? (?:regarding|about|for)",
    r"decision (?:regarding|on|about) your application",
    r"update (?:on|regarding) your application",
]

# --- next-stage wording ------------------------------------------------------
#
# An e-mail that asks the candidate to sit a test, or to book / attend an
# interview, is the signal that an application is live. Both lists describe an
# action the recipient is being asked to take *now* - "we invite candidates who
# advance to an interview" is a description of the process, not an invitation,
# and is filtered out by _HEDGE below.

_ASSESSMENT_PATTERNS = [
    r"(?:online|coding|technical|skills?|written|pre-?employment|hiring) assessment",
    r"assessment (?:link|invitation|invite|test|round|stage)",
    r"take[- ]?home\s*(?:assignment|assessment|project|challenge|exercise|test|task)?",
    r"coding (?:challenge|exercise|test|task|assignment)",
    r"(?:complete|start|begin|take|finish|submit) (?:the|your|this|a|an) "
    r"(?:online |coding |technical |short )?(?:assessment|challenge|test|exercise|assignment)",
    r"invit(?:ed|ation|e you) to (?:complete|take|start) (?:an?|the|our|this)",
    r"work sample (?:test|exercise|assignment)",
    r"(?:hackerrank|codility|codesignal|coderbyte|hackerearth|devskiller|"
    r"testgorilla|imocha|vervoe|byteboard|codesubmit|woven|karat|qualified\.io|pymetrics)",
    r"aptitude test",
    r"technical screen(?:ing)? (?:test|exercise|challenge)",
]

_INTERVIEW_PATTERNS = [
    r"(?:schedule|book|set ?up|arrange|confirm) (?:an?|your|the|this) "
    r"(?:initial |first |final |follow-?up |brief |short |\d+[- ]?minute )?"
    r"(?:interview|phone screen|screening call|call|chat|conversation|meeting)",
    r"interview (?:invitation|invite|request|confirmation)",
    r"invit(?:e|ed|ing|ation) (?:you )?(?:to|for) (?:an?|the) (?:interview|conversation|chat|call)",
    r"(?:would like|we'?d like|we would love|excited) to (?:speak|chat|talk|meet|connect) with you",
    r"move(?:d)? (?:you )?(?:forward|ahead|on) to (?:the |an? )?(?:interview|next round|next stage)",
    r"(?:your|the) interview (?:is|has been|will be) (?:scheduled|confirmed|booked|set)",
    r"(?:phone|video|technical|onsite|on-?site|panel|final|behavioural|behavioral) interview",
    r"phone screen(?:ing)?\b",
    r"(?:next|second|third|final) round",
    r"(?:pick|choose|select|share|let us know) (?:a|your|some|the) "
    r"(?:time|times|slot|slots|availability|available)",
    r"(?:your |please )?availability (?:for|to) (?:an?|the|this) "
    r"(?:interview|call|chat|conversation|meeting|screen)",
    r"(?:calendly|goodtime|modernloop|chilipiper|savvycal|youcanbook|cronofy|hirevue|"
    r"spark-?hire|willo\.video|myinterview)",
    r"speak with (?:the|our) (?:hiring manager|recruiter|team)",
    r"recruiter (?:screen|call|chat)",
]

# Process descriptions and conditional promises read exactly like invitations
# ("candidates who advance will be invited to an interview"). A stage hit that
# sits right after one of these does not count.
_HEDGE = re.compile(
    r"\b(?:if|should you|in the event|those who|candidates who|applicants who|"
    r"may be|might be|could be|will be (?:contacted|invited|reached)|"
    r"typically|usually|generally|next steps? (?:in|of) (?:our|the) process|"
    r"our (?:hiring |interview )?process|what to expect|do not|don'?t|no longer)\b",
    re.I,
)
# How far back to look for hedging wording before a stage phrase.
_HEDGE_WINDOW = 120

# Soft rejection phrases ("keep in touch about future opportunities") are also
# how a recruiter opens a cold pitch. A weak-signals-only verdict therefore
# also requires some sign the mail is about an application the recipient made.
_ABOUT_AN_APPLICATION = re.compile(
    r"your (?:job )?(?:application|candidacy|submission)"
    r"|application (?:id|number|reference|status)"
    r"|\bapplicants?\b"
    r"|\bapplied\b"
    r"|\bapply(?:ing)?\b",
    re.I,
)

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
    kind: str  # KIND_CONFIRMATION | KIND_REJECTION | KIND_OTHER
    company: Optional[str]
    role: Optional[str]
    confidence: str  # "high" | "low"

    @property
    def is_application(self) -> bool:
        return self.kind == KIND_CONFIRMATION

    @property
    def is_rejection(self) -> bool:
        return self.kind == KIND_REJECTION


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


# ATS platforms where the email subdomain really is the employer's tenant slug
# (e.g. acme.greenhouse.io). iCIMS/Workday/etc. send from a *shared* subdomain
# like talent.icims.com, so they are deliberately excluded here.
_TENANT_SUBDOMAIN_ATS = {
    "greenhouse.io", "greenhouse-mail.io", "lever.co", "hire.lever.co",
    "jobs.lever.co", "ashbyhq.com", "smartrecruiters.com", "teamtailor.com",
    "teamtailormail.com", "recruitee.com", "breezy.hr", "bamboohr.com",
}
_SUBDOMAIN_INFRA_SLUGS = {
    "mail", "email", "e", "em", "jobs", "job", "hire", "hiring", "us", "eu",
    "app", "apps", "noreply", "www", "careers", "career", "talent", "talents",
    "auto", "autoreply", "reply", "replies", "notification", "notifications",
    "notify", "messaging", "message", "bounce", "bounces", "system", "alerts",
    "alert", "updates", "info", "donotreply", "smtp", "mailer", "send", "outbound",
}


def _company_from_ats_subdomain(domain: str) -> Optional[str]:
    """``acme.greenhouse.io`` -> ``"Acme"`` - only for ATS hosts whose email
    subdomain is the employer's tenant, not shared infra like ``talent.icims.com``."""
    for ats in _TENANT_SUBDOMAIN_ATS:
        if domain.endswith("." + ats):
            slug = domain[: -(len(ats) + 1)].split(".")[-1].replace("-", " ")
            if slug.replace(" ", "") in _SUBDOMAIN_INFRA_SLUGS:
                return None
            cleaned = _clean_name(slug)
            if cleaned and len(cleaned) >= 2:
                return cleaned.title() if cleaned.islower() else cleaned
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

    # ATS platforms append " @ icims", " | Greenhouse", etc. to the sender name.
    name = re.sub(
        r"\s*[@|/]\s*(?:icims|greenhouse|lever|workday|myworkday|ashby|ashbyhq|"
        r"smartrecruiters|workable|jobvite|taleo|successfactors|teamtailor)\s*$",
        "", name or "", flags=re.I,
    ).strip()

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


def _haystack(subject: str, body: str) -> str:
    return f"{subject or ''}\n{(body or '')[:2500]}".lower()


def looks_like_confirmation(subject: str, body: str) -> bool:
    hay = _haystack(subject, body)
    return any(re.search(p, hay) for p in _CONFIRMATION_PATTERNS)


def _rejection_scan(subject: str, body: str) -> tuple[bool, int]:
    """``(hit_an_unmistakable_phrase, number_of_usable_soft_hits)``.

    Soft hits are zeroed out when nothing in the mail refers to an application,
    so recruiter outreach offering to "keep in touch about future
    opportunities" is not read as a decline.
    """
    hay = _haystack(subject, body)
    strong = any(re.search(p, hay) for p in _REJECTION_STRONG_PATTERNS)
    if not _ABOUT_AN_APPLICATION.search(hay):
        return strong, 0
    weak = sum(1 for p in _REJECTION_WEAK_PATTERNS if re.search(p, hay))
    return strong, weak


def looks_like_rejection(subject: str, body: str) -> tuple[bool, str]:
    """``(is_rejection, strength)`` where strength is ``"strong"`` | ``"weak"`` | ``"none"``.

    One unmistakable phrase, or two softer ones, is enough. A single soft hit
    ("unfortunately") is reported as no rejection - the LLM can still say
    otherwise.
    """
    strong, weak = _rejection_scan(subject, body)
    if strong:
        return True, "strong"
    if weak >= 2:
        return True, "weak"
    return False, "none"


def _unhedged_hits(hay: str, patterns: list[str]) -> int:
    """How many separate phrases in ``hay`` point at this stage.

    A hit preceded by hedging wording within :data:`_HEDGE_WINDOW` characters is
    thrown away: "candidates who advance will be invited to an interview"
    describes the process, "we'd like to invite you to an interview" is one, and
    only the second should move an application forward.

    Overlapping spans count once. Several patterns match the same sentence
    ("share your availability for a call" hits two), and a second phrase is only
    evidence when it is a second phrase.
    """
    spans = sorted(
        (m.start(), m.end())
        for pattern in patterns
        for m in re.finditer(pattern, hay)
        if not _HEDGE.search(hay, max(0, m.start() - _HEDGE_WINDOW), m.start())
    )
    hits, covered_to = 0, -1
    for start, end in spans:
        if start >= covered_to:
            hits += 1
            covered_to = end
    return hits


def _stage_scan(subject: str, body: str) -> tuple[int, int]:
    """``(interview_hits, assessment_hits)`` after hedged wording is dropped."""
    hay = _haystack(subject, body)
    return (
        _unhedged_hits(hay, _INTERVIEW_PATTERNS),
        _unhedged_hits(hay, _ASSESSMENT_PATTERNS),
    )


def looks_like_next_stage(subject: str, body: str) -> Optional[str]:
    """:data:`KIND_INTERVIEW`, :data:`KIND_ASSESSMENT` or ``None``.

    An interview outranks an assessment when both are mentioned - "your
    technical interview will include a coding exercise" is an interview.
    """
    interview, assessment = _stage_scan(subject, body)
    if interview:
        return KIND_INTERVIEW
    if assessment:
        return KIND_ASSESSMENT
    return None


def run_rules(from_header: str, subject: str, body: str) -> RuleResult:
    name, _email, domain = parse_from(from_header)
    strong_rej, weak_rej = _rejection_scan(subject, body)
    is_conf = looks_like_confirmation(subject, body)
    from_ats = is_ats_domain(domain)
    company, conf = _guess_company(name, domain, subject, body)
    role = _guess_role(subject, body)

    # Rejections routinely open with confirmation wording ("Thank you for your
    # interest in Acme...") so they are checked first and win the tie.
    if strong_rej or weak_rej >= 2:
        confidence = "high" if (strong_rej and company and conf == "high") else "low"
        return RuleResult(KIND_REJECTION, company, role, confidence)

    # Next-stage mail also opens with thanks ("Thanks for applying - the next
    # step is a short assessment"), so it is settled before confirmation too.
    interview_hits, assessment_hits = _stage_scan(subject, body)
    if interview_hits or assessment_hits:
        kind = KIND_INTERVIEW if interview_hits else KIND_ASSESSMENT
        hits = interview_hits or assessment_hits
        # Two independent phrases, a known company and no decline wording is
        # enough to skip the model; anything thinner gets a second opinion.
        confidence = (
            "high" if (hits >= 2 and company and conf == "high" and weak_rej == 0) else "low"
        )
        return RuleResult(kind, company, role, confidence)

    if not (is_conf or (from_ats and company)):
        return RuleResult(KIND_OTHER, company, role, "low")

    # A high-confidence verdict skips the LLM entirely, so only claim it when
    # nothing about the mail hints at a decline. One soft hit under confirmation
    # wording is exactly how a rejection reads, and the phrase lists will never
    # cover every employer's way of saying no - hand those to the model.
    confidence = (
        "high" if (is_conf and company and conf == "high" and weak_rej == 0) else "low"
    )
    return RuleResult(KIND_CONFIRMATION, company, role, confidence)


# ---------------------------------------------------------------------------
# LLM layer
# ---------------------------------------------------------------------------

try:  # optional dependency / optional feature
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore

    def Field(*_a, **_kw):  # type: ignore
        return None

# The LLM is reached over an OpenAI-compatible API - works with a local runtime
# (Ollama: http://localhost:11434/v1), OpenRouter, Groq, Gemini's OpenAI
# endpoint, a self-hosted LiteLLM proxy, etc. Set LLM_BASE_URL + LLM_API_KEY +
# CLASSIFIER_MODEL to match. Local/self-hosted endpoints and ":free" model ids
# never spend money; anything else needs CLASSIFIER_ALLOW_PAID=1.
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL")
    or os.getenv("OPENROUTER_BASE_URL")
    or "http://localhost:11434/v1"
)
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "qwen3:8b")

_ALLOW_PAID = os.getenv("CLASSIFIER_ALLOW_PAID", "0") not in ("", "0", "false", "False")
_IS_LOCAL = any(h in LLM_BASE_URL for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1"))
_IS_FREE = (
    _IS_LOCAL
    or CLASSIFIER_MODEL.endswith(":free")
    or CLASSIFIER_MODEL == "openrouter/free"
)
# qwen3 and other reasoning models emit <think>…</think>; ask them not to.
_NO_THINK = "qwen3" in CLASSIFIER_MODEL.lower()

_llm_client = None
_llm_disabled = False

_LLM_SYSTEM = (
    "You classify emails for a job-application tracker. You are given one email's "
    "From header, Subject, and a plain-text excerpt.\n\n"
    "Set `category` to exactly one of:\n"
    "- \"confirmation\": an automated acknowledgement from an employer or its "
    "applicant tracking system that THE RECIPIENT submitted an application.\n"
    "- \"rejection\": the employer is declining the recipient - moving forward "
    "with other candidates, the role was filled, the recipient was not selected, "
    "or the application is no longer under consideration.\n"
    "- \"assessment\": the recipient is asked to complete a test, take-home, "
    "coding challenge or work sample as part of their application.\n"
    "- \"interview\": the recipient is invited to interview, asked for their "
    "availability or to book a slot, or told an interview is scheduled.\n"
    "- \"other\": anything else, including job alerts and newsletters, recruiter "
    "cold outreach, and offers.\n\n"
    "A rejection usually opens with polite confirmation wording (\"Thank you for "
    "your interest in Acme\") - if the email declines the candidate anywhere in "
    "the text the category is \"rejection\", never \"confirmation\".\n\n"
    "Next-step emails also open with thanks (\"Thanks for applying! The next "
    "step is a short assessment\") - when the recipient is actually being asked "
    "to sit a test or to interview, prefer \"assessment\" or \"interview\" over "
    "\"confirmation\". A description of the process (\"candidates who advance "
    "are invited to interview\") is NOT an invitation - that is "
    "\"confirmation\" or \"other\". If the email mentions both an interview and "
    "an assessment, choose \"interview\".\n\n"
    "For \"assessment\" and \"interview\", set `when` to the interview time or "
    "the assessment deadline as an ISO 8601 timestamp (\"2026-03-17T14:00:00Z\"), "
    "converting any stated timezone to UTC. Use an empty string when the email "
    "names no date. Never invent one.\n\n"
    "Report `company` as the employer the person applied to - NEVER the ATS vendor "
    "(Greenhouse, Lever, Workday, Ashby, iCIMS, SmartRecruiters, Workable, and the "
    "like). Use an empty string for `company` or `role` when you cannot tell. Keep "
    "`role` short, e.g. \"Software Engineer Intern\". Set `confidence` to how sure "
    "you are of the category.\n\n"
    "Reply with a single JSON object and nothing else - no prose, no code fences."
)


class EmailClassification(BaseModel):  # type: ignore[misc]
    category: str = Field(
        description='One of "confirmation", "rejection", "assessment", "interview", "other".'
    )
    company: str = Field(
        description="Employer the recipient applied to (never the ATS vendor). Empty string if unknown."
    )
    role: str = Field(
        description='Short job title, e.g. "Software Engineer Intern". Empty string if unknown.'
    )
    confidence: str = Field(
        description='One of "high", "medium", "low" - how sure you are of the category.'
    )
    when: str = Field(
        default="",
        description="Interview time or assessment deadline as an ISO 8601 UTC "
                    "timestamp. Empty string if the email names no date.",
    )


def _get_client():
    global _llm_client, _llm_disabled
    if _llm_disabled:
        return None
    if _llm_client is None:
        if not LLM_API_KEY and not _IS_LOCAL:
            logger.warning("LLM_API_KEY not set - LLM email classification disabled")
            _llm_disabled = True
            return None
        if not _IS_FREE and not _ALLOW_PAID:
            logger.warning(
                "CLASSIFIER_MODEL=%r is not local or ':free' and CLASSIFIER_ALLOW_PAID "
                "is not set - LLM classification disabled to avoid spending money",
                CLASSIFIER_MODEL,
            )
            _llm_disabled = True
            return None
        try:
            from openai import OpenAI

            _llm_client = OpenAI(
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY or "local",
                max_retries=0,  # we do our own backoff
                default_headers={"X-Title": "job-application-tracker"},
            )
        except Exception:
            logger.exception("could not initialise OpenRouter client - LLM classification disabled")
            _llm_disabled = True
            return None
    return _llm_client


LLM_MAX_ATTEMPTS = int(os.getenv("CLASSIFIER_MAX_ATTEMPTS", "3"))


def _is_rate_limit(exc: Exception) -> bool:
    for attr in ("status_code", "code", "http_status"):
        if getattr(exc, attr, None) in (429, 500, 502, 503, 529):
            return True
    blob = str(exc).lower()
    return any(s in blob for s in ("429", "rate limit", "rate_limit", "quota",
                                   "resource_exhausted", "overloaded", "unavailable",
                                   "timeout", "502", "503", "529"))


def _call_llm(user_content: str, max_tokens: int):
    """One chat-completions request in JSON mode, with retry/backoff on
    rate-limit / transient errors. Returns the parsed JSON object, or None."""
    client = _get_client()
    if client is None:
        return None

    import json

    system = _LLM_SYSTEM + ("\n\n/no_think" if _NO_THINK else "")
    delay = 3.0
    for attempt in range(1, LLM_MAX_ATTEMPTS + 1):
        try:
            resp = client.chat.completions.create(
                model=CLASSIFIER_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=max_tokens,
            )
            text = (resp.choices[0].message.content or "").strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
            try:
                return json.loads(text)
            except ValueError:
                m = re.search(r"[\{\[].*[\}\]]", text, re.S)  # unwrap fences / prose
                return json.loads(m.group(0)) if m else None
        except Exception as exc:
            if attempt < LLM_MAX_ATTEMPTS and _is_rate_limit(exc):
                logger.warning(
                    "LLM rate-limited (%s); retry %d/%d in %.0fs",
                    exc.__class__.__name__, attempt, LLM_MAX_ATTEMPTS, delay,
                )
                time.sleep(delay)
                delay *= 3
                continue
            logger.exception("LLM request failed")
            return None


def _coerce_category(d: dict) -> str:
    """Normalise whatever the model said into one of :data:`KINDS`.

    Also understands the older boolean shape (``is_application_confirmation``)
    so a model that was prompt-cached on the previous schema still parses.
    """
    raw = str(d.get("category") or d.get("kind") or d.get("label") or "").strip().lower()
    if raw.startswith("reject") or raw in ("declined", "decline", "no"):
        return KIND_REJECTION
    if raw.startswith(("interview", "screen")) or raw in ("phone screen", "scheduling"):
        return KIND_INTERVIEW
    if raw.startswith(("assessment", "test", "challenge", "take")) or raw in (
        "coding challenge", "take home", "online assessment", "oa",
    ):
        return KIND_ASSESSMENT
    if raw.startswith("confirm") or raw in ("application", "applied", "acknowledgement"):
        return KIND_CONFIRMATION
    if raw:
        return KIND_OTHER
    if "is_application_confirmation" in d:
        return KIND_CONFIRMATION if bool(d["is_application_confirmation"]) else KIND_OTHER
    return KIND_OTHER


def _to_classification(d: dict) -> Optional[EmailClassification]:
    try:
        return EmailClassification(
            category=_coerce_category(d),
            company=str(d.get("company") or ""),
            role=str(d.get("role") or ""),
            confidence=str(d.get("confidence") or "low"),
            when=str(d.get("when") or d.get("datetime") or d.get("date") or ""),
        )
    except Exception:
        return None


def classify_with_llm(from_header: str, subject: str, body: str) -> Optional[EmailClassification]:
    """Single-email classification (used by tests / one-offs; the sync endpoint
    uses the batched path below)."""
    content = (
        f"From: {from_header}\nSubject: {subject}\n\n{(body or '')[:2500]}\n\n"
        'Respond with JSON: {"category": '
        '"confirmation"|"rejection"|"assessment"|"interview"|"other", '
        '"company": "...", "role": "...", "confidence": "high"|"medium"|"low", '
        '"when": "<ISO 8601 UTC or empty>"}. '
        'Use "" for company, role or when if unknown.'
    )
    data = _call_llm(content, 400)
    if not isinstance(data, dict):
        return None
    result = _to_classification(data)
    if result is None:
        logger.warning("unparseable LLM classification (subject=%r): %r", subject, data)
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    kind: str  # one of KINDS
    company: Optional[str]
    role: Optional[str]
    needs_review: bool
    method: str  # "rules" | "llm" | "rules+llm" | "deferred"
    # Interview slot or assessment deadline, aware UTC. Only ever set for an
    # advancing kind, and only when the e-mail actually names a date.
    when: Optional[datetime] = None
    duration: Optional[timedelta] = None

    @property
    def is_application(self) -> bool:
        return self.kind == KIND_CONFIRMATION

    @property
    def is_rejection(self) -> bool:
        return self.kind == KIND_REJECTION

    @property
    def is_advance(self) -> bool:
        """Does this e-mail move a live application into the next stage?"""
        return self.kind in ADVANCING_KINDS


@dataclass
class EmailInput:
    key: str  # opaque id (e.g. Gmail message id) used to align results
    from_header: str
    subject: str
    body: str
    # When the mail arrived - the anchor for "within 48 hours" and for choosing
    # the year of a date written without one. Defaults to now.
    received_at: Optional[datetime] = None


def _nothing(method: str) -> Decision:
    return Decision(KIND_OTHER, None, None, False, method)


def _parse_llm_when(raw: str) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _with_schedule(
    decision: Decision,
    subject: str,
    body: str,
    received_at: Optional[datetime],
    llm_when: str = "",
) -> Decision:
    """Attach the interview slot / assessment deadline to an advancing decision.

    The offline parser goes first because it is anchored to the e-mail's own
    timestamp; the model's answer is a fallback for wording the patterns miss,
    and is discarded unless it lands in the same plausible window.
    """
    if not decision.is_advance:
        return decision
    anchor = received_at or datetime.now(timezone.utc)
    when = schedule_parser.parse_when(subject, body, received_at=anchor)
    if when is None:
        candidate = _parse_llm_when(llm_when)
        if schedule_parser._plausible(candidate, anchor):
            when = candidate
    decision.when = when
    decision.duration = schedule_parser.parse_duration(subject, body) if when else None
    return decision


def _merge(rule: RuleResult, llm: Optional[EmailClassification]) -> Decision:
    if llm is None:
        # LLM unavailable/skipped/errored - trust rules, flag for a human look.
        if rule.kind == KIND_OTHER:
            return _nothing("rules")
        return Decision(rule.kind, rule.company, rule.role, True, "rules")

    method = "rules+llm" if rule.kind != KIND_OTHER else "llm"
    if llm.category == KIND_OTHER:
        # The rules only shout "rejection" on unambiguous wording, so keep that
        # verdict when the model shrugs - but send it for review.
        if rule.kind == KIND_REJECTION and rule.confidence == "high":
            return Decision(KIND_REJECTION, rule.company, rule.role, True, method)
        return _nothing(method)

    company = (llm.company or "").strip() or rule.company
    role = (llm.role or "").strip() or rule.role
    needs_review = (not company) or (llm.confidence or "").lower() == "low"
    return Decision(llm.category, company, role, needs_review, method)


def classify_email(
    from_header: str,
    subject: str,
    body: str,
    *,
    use_llm: bool = True,
    received_at: Optional[datetime] = None,
) -> Decision:
    rule = run_rules(from_header, subject, body)
    if rule.kind != KIND_OTHER and rule.company and rule.confidence == "high":
        decision = Decision(rule.kind, rule.company, rule.role, False, "rules")
        return _with_schedule(decision, subject, body, received_at)
    llm = classify_with_llm(from_header, subject, body) if use_llm else None
    decision = _merge(rule, llm)
    return _with_schedule(decision, subject, body, received_at, llm.when if llm else "")


BATCH_SIZE = int(os.getenv("CLASSIFIER_BATCH_SIZE", "10"))


def _classify_chunk_llm(chunk: list[EmailInput]) -> dict[str, EmailClassification]:
    """Classify up to BATCH_SIZE emails in a single request."""
    parts = [
        f"=== EMAIL {i} ===\nFrom: {it.from_header}\nSubject: {it.subject}\n\n"
        f"{(it.body or '')[:1800]}"
        for i, it in enumerate(chunk)
    ]
    content = (
        "Classify each email below.\n\n" + "\n\n".join(parts) + "\n\n"
        'Respond with JSON: {"results": [{"index": <int>, '
        '"category": "confirmation"|"rejection"|"assessment"|"interview"|"other", '
        '"company": "...", "role": "...", "confidence": "high"|"medium"|"low", '
        '"when": "<ISO 8601 UTC or empty>"}, ...]} - exactly one object per email, '
        "where index is the number after 'EMAIL'. Use \"\" for company, role or "
        "when if unknown."
    )
    data = _call_llm(content, 300 * len(chunk) + 256)
    if data is None:
        return {}  # call path already logged why
    rows = data.get("results") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        logger.warning("LLM batch response had no 'results' list (%d emails): %r", len(chunk), data)
        return {}

    out: dict[str, EmailClassification] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row["index"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= idx < len(chunk):
            parsed = _to_classification(row)
            if parsed is not None:
                out[chunk[idx].key] = parsed
    return out


def classify_emails(
    items: list[EmailInput],
    *,
    use_llm: bool = True,
    llm_budget: Optional[int] = None,
) -> dict[str, Decision]:
    """Classify many emails, batching LLM calls. Returns {key: Decision}.

    ``llm_budget`` caps how many emails may be sent to the LLM this run. Emails
    over the budget get a Decision with ``method == "deferred"`` - the caller
    should persist nothing for those so they are reclassified on the next run.
    """
    from dataclasses import replace

    rules: dict[str, RuleResult] = {}
    results: dict[str, Decision] = {}
    pending: list[EmailInput] = []

    def settle(it: EmailInput, decision: Decision, llm_when: str = "") -> None:
        results[it.key] = _with_schedule(
            decision, it.subject, it.body, it.received_at, llm_when
        )

    for it in items:
        r = run_rules(it.from_header, it.subject, it.body)
        rules[it.key] = r
        if r.kind != KIND_OTHER and r.company and r.confidence == "high":
            settle(it, Decision(r.kind, r.company, r.role, False, "rules"))
        else:
            pending.append(it)

    if not use_llm:
        # LLM off entirely: the rules verdict is final (not deferred).
        for it in pending:
            settle(it, _merge(rules[it.key], None))
        return results

    budget = len(pending) if llm_budget is None else max(0, llm_budget)
    to_llm, overflow = pending[:budget], pending[budget:]

    for start in range(0, len(to_llm), BATCH_SIZE):
        chunk = to_llm[start:start + BATCH_SIZE]
        llm_map = _classify_chunk_llm(chunk)
        for it in chunk:
            llm = llm_map.get(it.key)
            settle(it, _merge(rules[it.key], llm), llm.when if llm else "")

    # over budget this run - persist nothing, reclassify next run
    for it in overflow:
        results[it.key] = replace(_merge(rules[it.key], None), method="deferred")

    return results
