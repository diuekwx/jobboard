"""Gmail wire helpers: query building, header lookup, MIME body decoding.

Company / role inference and the "is this a job application?" decision live in
``backend.service.classification_service``.
"""

import base64
import re
from html.parser import HTMLParser

# --- Gmail search query -------------------------------------------------------

_ATS_FROM = " OR ".join([
    "greenhouse.io", "lever.co", "myworkday.com", "myworkdayjobs.com",
    "ashbyhq.com", "icims.com", "smartrecruiters.com", "workable.com",
    "jobvite.com", "bamboohr.com", "teamtailor.com", "breezy.hr",
    "recruitee.com", "hire.google.com", "eightfold.ai",
])

_SUBJECT_TERMS = " OR ".join([
    '"thank you for applying"', '"thanks for applying"',
    '"thank you for your application"', '"thank you for your interest"',
    '"application received"', '"application submitted"',
    '"we received your application"', '"received your application"',
    '"application has been received"', '"application confirmation"',
    '"your application"', '"successfully submitted"', '"we got your application"',
    # rejection-shaped subjects
    '"application update"', '"update on your application"',
    '"regarding your application"', '"application status"',
    '"status of your application"', '"your recent application"',
    '"your candidacy"', '"your job application"',
])

# Phrases distinctive enough to search unqualified, i.e. against the message
# body as well. Rejection subjects are often bland ("Acme") while the decline
# itself is unmistakable in the body, so subject-only matching misses them.
_BODY_TERMS = " OR ".join([
    '"we regret to inform"',
    '"moving forward with other candidates"',
    '"move forward with other candidates"',
    '"pursue other candidates"',
    '"other candidates whose"',
    '"not moving forward with your application"',
    '"will not be moving forward"',
    '"no longer under consideration"',
    '"your application was not successful"',
    '"not been selected"',
    '"position has been filled"',
    '"not to progress"',
    '"unable to progress your application"',
    '"not to move forward"',
    '"no longer available at this time"',
])


def build_query(after_epoch: int) -> str:
    """Gmail query for candidate application e-mails received after ``after_epoch`` (unix seconds).

    Deliberately broad — the classifier does the real filtering. Searches all
    mail (not just the inbox) so filtered/labelled recruiting mail is still seen.
    Covers both application confirmations and rejections.
    """
    return (
        f"(subject:({_SUBJECT_TERMS}) OR from:({_ATS_FROM}) OR ({_BODY_TERMS})) "
        f"after:{after_epoch} -in:chats"
    )


# --- header lookup ----------------------------------------------------------

def get_header(headers, name: str) -> str:
    name_l = name.lower()
    for h in headers or []:
        if (h.get("name") or "").lower() == name_l:
            return h.get("value") or ""
    return ""


# --- MIME body decoding ----------------------------------------------------

def _b64url_decode(data: str) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return ""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._chunks).split())


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        return parser.text()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def extract_body_text(payload: dict, limit: int = 4000) -> str:
    """Walk a Gmail message ``payload`` and return decoded text.

    Prefers ``text/plain`` parts; falls back to stripped ``text/html``.
    """
    plain, html = [], []
    stack = [payload or {}]
    while stack:
        part = stack.pop()
        if part.get("parts"):
            stack.extend(part["parts"])
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        mime = part.get("mimeType", "")
        decoded = _b64url_decode(data)
        if mime == "text/plain":
            plain.append(decoded)
        elif mime == "text/html":
            html.append(decoded)

    text = "\n".join(p for p in plain if p).strip()
    if not text:
        text = _html_to_text("\n".join(h for h in html if h))
    return text[:limit]
