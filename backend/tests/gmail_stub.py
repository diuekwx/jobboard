"""A fake Gmail API, so the sync endpoint can be driven end to end offline.

conftest wires these into the ``stub_gmail`` / ``connected`` fixtures; the
helpers here are plain functions the test modules import directly.
"""

import base64

from backend.api import gmail as gmail_api


def message(mid, thread, from_header, subject, body, received):
    """One raw Gmail message, shaped the way the endpoint expects to read it."""
    return {
        "id": mid,
        "threadId": thread,
        "internalDate": str(int(received.timestamp() * 1000)),
        "payload": {
            "headers": [
                {"name": "From", "value": from_header},
                {"name": "Subject", "value": subject},
            ],
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
        },
    }


class _Exec:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class _Messages:
    def __init__(self, messages):
        self._messages = messages

    def list(self, **kw):
        start = int(kw.get("pageToken") or 0)
        size = kw.get("maxResults") or 100
        page = self._messages[start:start + size]
        result = {"messages": [{"id": m["id"]} for m in page]}
        if start + size < len(self._messages):
            result["nextPageToken"] = str(start + size)
        return _Exec(result)

    def get(self, *, userId, id, format):
        found = next(m for m in self._messages if m["id"] == id)
        if found.get("fetch_error"):
            raise RuntimeError("simulated Gmail fetch failure")
        return _Exec(found)


class FakeGmail:
    def __init__(self, messages):
        self._messages = _Messages(messages)

    def users(self):
        return self

    def messages(self):
        return self._messages


class _User:
    """Only ``.id`` is read off the user inside the endpoint."""

    def __init__(self, user_id):
        self.id = user_id


def sync(db, user_id):
    """Run one pass of the sync endpoint against the stubbed mailbox."""
    return gmail_api.fetch_job_applications(current_user=_User(user_id), db=db)
