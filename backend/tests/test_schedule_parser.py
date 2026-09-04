"""Date extraction for interview invites and assessment deadlines."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.service.schedule_parser import parse_duration, parse_when

RECEIVED = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)


def when(body, subject="", received=RECEIVED):
    return parse_when(subject, body, received_at=received)


ABSOLUTE = [
    ("Your interview is on Tuesday, March 17, 2026 at 2:00 PM UTC.",
     datetime(2026, 3, 17, 14, 0, tzinfo=timezone.utc)),
    ("We have you booked for March 17 at 2pm.",
     datetime(2026, 3, 17, 14, 0, tzinfo=timezone.utc)),
    ("The call is 17 March 2026, 14:00 GMT.",
     datetime(2026, 3, 17, 14, 0, tzinfo=timezone.utc)),
    ("Scheduled for 03/17/2026 2:00 PM.",
     datetime(2026, 3, 17, 14, 0, tzinfo=timezone.utc)),
    ("Event start: 2026-03-17T14:00:00Z",
     datetime(2026, 3, 17, 14, 0, tzinfo=timezone.utc)),
    # a date with no clock time lands on midnight, not nothing
    ("Please complete the assessment by March 17.",
     datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)),
]


@pytest.mark.parametrize(("body", "expected"), ABSOLUTE)
def test_absolute_dates(body, expected):
    assert when(body) == expected


def test_timezone_abbreviations_are_converted_to_utc():
    assert when("Interview: March 17, 2026 at 2:00 PM EST") == datetime(
        2026, 3, 17, 19, 0, tzinfo=timezone.utc
    )
    assert when("Interview: March 17, 2026 at 2:00 PM PDT") == datetime(
        2026, 3, 17, 21, 0, tzinfo=timezone.utc
    )


def test_a_day_over_twelve_flips_a_numeric_date_to_day_first():
    # 17/03 cannot be month 17, so it has to read as 17 March
    assert when("Booked for 17/03/2026.") == datetime(2026, 3, 17, tzinfo=timezone.utc)


def test_year_is_inferred_as_the_nearest_reading_ahead():
    # a January date in a December mail belongs to the following year
    december = datetime(2026, 12, 20, 9, 0, tzinfo=timezone.utc)
    assert when("Your interview is January 5.", received=december) == datetime(
        2027, 1, 5, tzinfo=timezone.utc
    )


RELATIVE = [
    ("Please complete the assessment within 48 hours.", timedelta(hours=48)),
    ("The link expires in 5 days.", timedelta(days=5)),
    ("You have 2 weeks to submit.", timedelta(weeks=2)),
    # five business days is a calendar week
    ("Please finish within 5 business days.", timedelta(days=7)),
]


@pytest.mark.parametrize(("body", "delta"), RELATIVE)
def test_relative_deadlines(body, delta):
    assert when(body) == RECEIVED + delta


def test_a_bare_weekday_resolves_to_the_next_one():
    # RECEIVED is a Tuesday; "by Friday" is three days later
    assert when("Please book a slot by Friday.") == datetime(2026, 3, 13, tzinfo=timezone.utc)


def test_an_absolute_date_beats_a_relative_one():
    body = "Complete within 48 hours - the deadline is March 17, 2026 at 5:00 PM UTC."
    assert when(body) == datetime(2026, 3, 17, 17, 0, tzinfo=timezone.utc)


IMPLAUSIBLE = [
    "Copyright 2019 Acme Inc. All rights reserved.",          # footer year
    "You have been a member since 03/04/2011.",               # far in the past
    "Our next hiring cycle opens January 2030.",              # far in the future
    "No date in this email at all, just prose about the role.",
]


@pytest.mark.parametrize("body", IMPLAUSIBLE)
def test_dates_outside_the_believable_window_are_dropped(body):
    assert when(body) is None


def test_a_bare_number_is_not_a_time():
    # "3 days" must not be read as 03:00 on some date
    assert when("Acme has 3 offices and 500 staff.") is None


def test_duration_is_read_when_stated():
    assert parse_duration("", "A 45 minute conversation with the team.") == timedelta(minutes=45)
    assert parse_duration("", "Block off 1 hour for the panel.") == timedelta(hours=1)
    assert parse_duration("", "No length mentioned here.") is None
    # implausible spans are ignored rather than turned into a meeting
    assert parse_duration("", "Our 40 hour work week is flexible.") is None
