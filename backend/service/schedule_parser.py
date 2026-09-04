"""Pull the *when* out of an interview invite or an assessment e-mail.

Deterministic and offline. ``classification_service`` decides what an e-mail
is; this decides what date it points at, so an application that moves into
"In Process" can carry the interview slot or the assessment deadline with it.

Handles the shapes recruiting mail actually uses::

    Tuesday, March 3, 2026 at 2:00 PM EST
    March 3 at 2pm
    3 March 2026, 14:00 GMT
    03/03/2026 2:00 PM
    2026-03-03T14:00:00Z
    please complete within 48 hours
    the link expires in 5 days
    please book a slot by Friday

Absolute dates win over relative ones, and every candidate is sanity-checked
against the e-mail's own timestamp - a footer copyright year or a "member
since 2019" line must never become an interview slot. Results are
timezone-aware UTC; a date with no clock time comes back at midnight.
"""

import re
from datetime import datetime, time, timedelta, timezone
from typing import Optional

# How far either side of the e-mail a parsed date may fall and still be
# believable. A little slack before, because "your interview yesterday" shows
# up in follow-ups; a couple of quarters after, because slots are booked ahead.
MAX_DAYS_BEFORE = 2
MAX_DAYS_AFTER = 240

# Offsets for the abbreviations that turn up in recruiting mail. Anything not
# listed is read as UTC - being an hour or two out on a date we surface is far
# better than dropping the date entirely.
_TZ_OFFSETS = {
    "ut": 0, "utc": 0, "gmt": 0, "z": 0,
    "est": -5, "edt": -4, "et": -5,
    "cst": -6, "cdt": -5, "ct": -6,
    "mst": -7, "mdt": -6, "mt": -7,
    "pst": -8, "pdt": -7, "pt": -8,
    "akst": -9, "akdt": -8, "hst": -10,
    "bst": 1, "wet": 0, "west": 1,
    "cet": 1, "cest": 2, "eet": 2, "eest": 3,
    "ist": 5.5, "jst": 9, "kst": 9, "aest": 10, "aedt": 11,
    "nzst": 12, "nzdt": 13, "sgt": 8, "hkt": 8,
}
_TZ_ALT = "|".join(sorted(_TZ_OFFSETS, key=len, reverse=True))

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
# Full names and the usual abbreviations. Spelled out rather than "mar[a-z]*"
# so "maybe" can never be read as May.
_MONTH_ALT = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)

_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
_WEEKDAY_ALT = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))

# A clock time. Bare digits are only a time when they carry am/pm or minutes -
# otherwise "within 3 days" would read as 03:00.
_TIME_RE = re.compile(
    r"\b(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?)?"
    r"(?:\s*\(?(?P<tz>" + _TZ_ALT + r")\)?\b)?",
    re.I,
)

_ISO_RE = re.compile(
    r"\b(?P<year>20\d{2})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"(?:[T ](?P<hour>\d{1,2}):(?P<minute>\d{2})(?::\d{2})?"
    r"\s*(?P<tz>Z|[+-]\d{2}:?\d{2})?)?",
    re.I,
)

# "March 3", "Mar. 3rd, 2026". The (?!\d) stops the day group from biting the
# first two digits of a bare year - "March 2026" is not the 20th of March.
_MONTH_FIRST_RE = re.compile(
    r"\b(?P<month>" + _MONTH_ALT + r")\.?\s+(?P<day>\d{1,2})(?!\d)(?:st|nd|rd|th)?"
    r"(?:\s*,?\s*(?P<year>20\d{2}))?",
    re.I,
)
# "3 March", "3rd of March 2026"
_DAY_FIRST_RE = re.compile(
    r"\b(?P<day>\d{1,2})(?!\d)(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<month>" + _MONTH_ALT + r")\.?"
    r"(?:\s*,?\s*(?P<year>20\d{2}))?",
    re.I,
)
# "3/17/2026", "3-17". Read US-first (month/day) because that is what the mail
# these come from overwhelmingly uses; a day > 12 in the first slot flips it.
_NUMERIC_RE = re.compile(
    r"\b(?P<first>\d{1,2})[/-](?P<second>\d{1,2})(?:[/-](?P<year>\d{2,4}))?\b"
)

# "within 48 hours", "in the next 3 business days", "expires in 5 days"
_RELATIVE_RE = re.compile(
    r"(?:with?in|in the next|expires? in|you have|complete .{0,20}?within)\s+"
    r"(?P<count>\d{1,3})\s+(?P<unit>hours?|business days?|days?|weeks?)",
    re.I,
)
# "by Friday", "on Tuesday" - resolved to the next such weekday after the mail.
_WEEKDAY_RE = re.compile(
    r"\b(?:by|on|this|next|for)\s+(?:this\s+|next\s+|coming\s+)?"
    r"(?P<weekday>" + _WEEKDAY_ALT + r")\b",
    re.I,
)

# How long the meeting runs, when the mail bothers to say.
_DURATION_RE = re.compile(
    r"\b(?P<count>\d{1,3})(?:\s*|-)(?P<unit>minutes?|mins?|hours?|hrs?)\b", re.I,
)

_ALL_DAY = time(0, 0)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _tz_delta(token: Optional[str]) -> timedelta:
    """UTC offset for a timezone token, defaulting to none (i.e. read as UTC)."""
    if not token:
        return timedelta(0)
    token = token.strip().lower()
    if token.startswith(("+", "-")):  # numeric offset from an ISO stamp
        sign = -1 if token[0] == "-" else 1
        digits = token[1:].replace(":", "")
        try:
            return sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0))
        except ValueError:
            return timedelta(0)
    return timedelta(hours=_TZ_OFFSETS.get(token, 0))


def _plausible(when: Optional[datetime], received_at: datetime) -> bool:
    if when is None:
        return False
    delta = when - _aware(received_at)
    return -timedelta(days=MAX_DAYS_BEFORE) <= delta <= timedelta(days=MAX_DAYS_AFTER)


def _pick_year(month: int, day: int, received_at: datetime) -> int:
    """Year for a date written without one: the reading that lands nearest ahead.

    A "December 12" in a January mail means last December; a "January 5" in a
    December mail means next January.
    """
    base = _aware(received_at)
    best, best_gap = base.year, None
    for year in (base.year - 1, base.year, base.year + 1):
        try:
            candidate = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:  # e.g. Feb 29 in a common year
            continue
        gap = abs((candidate - base).total_seconds())
        # bias towards the future: a past date pays a penalty
        if candidate < base:
            gap *= 3
        if best_gap is None or gap < best_gap:
            best, best_gap = year, gap
    return best


def _find_time(text: str, start: int, end: int):
    """``(time, tz_token)`` for the first clock time in ``text[start:end]``."""
    for m in _TIME_RE.finditer(text, max(0, start), end):
        hour = int(m.group("hour"))
        minute = int(m.group("minute") or 0)
        ampm = (m.group("ampm") or "").replace(".", "").lower()
        if not ampm and m.group("minute") is None:
            continue  # a bare number is not a time
        if ampm:
            if hour > 12:
                continue
            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
        if hour > 23 or minute > 59:
            continue
        return time(hour, minute), m.group("tz")
    return None, None


def _time_near(text: str, match: re.Match):
    """A clock time just after the date, else just before it ("2pm on Mar 3")."""
    found, tz = _find_time(text, match.end(), min(len(text), match.end() + 60))
    if found is None:
        found, tz = _find_time(text, match.start() - 40, match.start())
    return found, tz


def _from_date_match(text: str, match: re.Match, month: int, day: int,
                     year: Optional[int], received_at: datetime):
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    year = year or _pick_year(month, day, received_at)
    clock, tz = _time_near(text, match)
    try:
        naive = datetime.combine(datetime(year, month, day).date(), clock or _ALL_DAY)
    except ValueError:
        return None
    return naive.replace(tzinfo=timezone.utc) - _tz_delta(tz)


def _absolute_candidates(text: str, received_at: datetime):
    for m in _ISO_RE.finditer(text):
        try:
            naive = datetime(
                int(m.group("year")), int(m.group("month")), int(m.group("day")),
                int(m.group("hour") or 0), int(m.group("minute") or 0),
            )
        except ValueError:
            continue
        yield naive.replace(tzinfo=timezone.utc) - _tz_delta(m.group("tz"))

    for regex in (_MONTH_FIRST_RE, _DAY_FIRST_RE):
        for m in regex.finditer(text):
            month = _MONTHS.get(m.group("month")[:3].lower())
            if not month:
                continue
            year = int(m.group("year")) if m.group("year") else None
            when = _from_date_match(text, m, month, int(m.group("day")), year, received_at)
            if when:
                yield when

    for m in _NUMERIC_RE.finditer(text):
        first, second = int(m.group("first")), int(m.group("second"))
        month, day = (second, first) if first > 12 >= second else (first, second)
        raw_year = m.group("year")
        year = None
        if raw_year:
            year = int(raw_year)
            year += 2000 if year < 100 else 0
        when = _from_date_match(text, m, month, day, year, received_at)
        if when:
            yield when


def _relative_candidates(text: str, received_at: datetime):
    base = _aware(received_at)
    for m in _RELATIVE_RE.finditer(text):
        count = int(m.group("count"))
        unit = m.group("unit").lower()
        if unit.startswith("hour"):
            yield base + timedelta(hours=count)
        elif unit.startswith("week"):
            yield base + timedelta(weeks=count)
        elif "business" in unit:
            # five business days is a calendar week; close enough to be useful.
            yield base + timedelta(days=count + 2 * (count // 5))
        else:
            yield base + timedelta(days=count)

    for m in _WEEKDAY_RE.finditer(text):
        target = _WEEKDAYS[m.group("weekday").lower()]
        ahead = (target - base.weekday()) % 7 or 7
        day = (base + timedelta(days=ahead)).date()
        clock, tz = _time_near(text, m)
        yield datetime.combine(day, clock or _ALL_DAY, tzinfo=timezone.utc) - _tz_delta(tz)


def parse_when(subject: str, body: str, *, received_at: datetime) -> Optional[datetime]:
    """First believable date in the e-mail, as an aware UTC datetime, or None.

    Absolute dates are preferred; a relative deadline ("within 48 hours") is
    only used when the mail names no date at all.
    """
    text = f"{subject or ''}\n{(body or '')[:3000]}"
    for candidate in _absolute_candidates(text, received_at):
        if _plausible(candidate, received_at):
            return candidate
    for candidate in _relative_candidates(text, received_at):
        if _plausible(candidate, received_at):
            return candidate
    return None


def parse_duration(subject: str, body: str) -> Optional[timedelta]:
    """How long the meeting or assessment is said to run, if it says."""
    text = f"{subject or ''}\n{(body or '')[:3000]}"
    m = _DURATION_RE.search(text)
    if not m:
        return None
    count = int(m.group("count"))
    unit = m.group("unit").lower()
    span = timedelta(hours=count) if unit.startswith(("hour", "hr")) else timedelta(minutes=count)
    # Guard against picking up "50 hours of onboarding" style prose.
    return span if timedelta(minutes=5) <= span <= timedelta(hours=8) else None
