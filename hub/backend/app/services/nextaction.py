"""Next action required (PS 2: Complaint/Case Tracking).

An officer may state the next step and a due date when logging an action. When they do not, the hub suggests one with a
simple rule based on the last action. The days below are ASSUMPTIONS about AICTE practice (editable here); the screen
labels a rule-based step as "suggested" and an officer's own as "set by the officer".
"""
from datetime import date, datetime, timedelta

# last action type -> (next step, days after that action it is due). None = nothing further is needed.
RULES = {
    "Acknowledged": ("Assign an officer and start the review", 7),
    "Under Review": ("Decide the next step: ask for documents, order an inspection, or close", 7),
    "Documents Sought": ("Wait for the institution's documents, then review them", 15),
    "Reply Sought from Institution": ("Wait for the institution's reply, then review it", 15),
    "Show-Cause Notice Issued": ("Wait for the institution's reply to the show-cause notice", 15),
    "Inspection Ordered": ("Receive and review the inspection report", 21),
    "Penalty Proposed": ("Obtain approval for the proposed penalty", 15),
    "Transferred": ("Receiving bureau to acknowledge and start the review", 7),
    "Escalated to Competent Authority": ("Competent authority to decide", 7),
    "Closed - No Action": None,
    "Disposed - Unsubstantiated": None,
    "Disposed - Action Taken": None,
}


def _day(x):
    return x.date() if isinstance(x, datetime) else x


def view(case, last_action_type: str | None, today: date | None = None) -> dict:
    """{text, due, source, overdue} for one case. source: officer / rule / none."""
    today = today or date.today()
    if case.status == "unverified_institution":
        return {"text": "Pick the institution in Needs review", "due": None, "source": "rule", "overdue": False}
    if case.status == "Disposed":
        return {"text": None, "due": None, "source": "none", "overdue": False}
    if case.next_action:
        due = case.next_action_due
        return {"text": case.next_action, "due": due.isoformat() if due else None, "source": "officer", "overdue": bool(due and due < today)}
    rule = RULES.get(last_action_type or "Acknowledged", ("Review the case and decide the next step", 7))
    if rule is None:
        return {"text": None, "due": None, "source": "none", "overdue": False}
    text, days = rule
    base = _day(case.last_action_at) if case.last_action_at else _day(case.received_at)
    due = base + timedelta(days=days)
    return {"text": text, "due": due.isoformat(), "source": "rule", "overdue": due < today}
