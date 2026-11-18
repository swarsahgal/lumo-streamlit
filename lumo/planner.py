"""Deadline-paced study planner.

Turns each upcoming deadline into short sessions spread across the days before
it (spaced practice instead of one cram night). Energy changes session length,
never the plan's goal.
"""
from datetime import date, timedelta

ENERGY_MINUTES = {"Low": 5, "Okay": 8, "Wired": 12}


def session_days(today: date, due: date) -> list[date]:
    """Days to study for one deadline: spaced out, last one the day before."""
    days_left = (due - today).days
    if days_left <= 0:
        return []
    if days_left == 1:
        return [today]
    gap = 1 if days_left <= 5 else 2
    offsets = set(range(0, days_left, gap)) | {days_left - 1}
    days = [today + timedelta(days=o) for o in sorted(offsets)][-6:]
    return sorted(days)


def build_plan(deadlines: list[dict], today: date | None = None) -> list[dict]:
    """deadlines: [{title, subject, topic, due: 'YYYY-MM-DD'}] -> sessions sorted by day."""
    today = today or date.today()
    plan = []
    for dl in deadlines:
        due = date.fromisoformat(dl["due"])
        for d in session_days(today, due):
            plan.append({"day": d.isoformat(), "subject": dl["subject"],
                         "topic": dl.get("topic") or dl["title"], "for": dl["title"],
                         "due": dl["due"]})
    plan.sort(key=lambda p: (p["day"], p["due"]))
    return plan


def runway(deadlines: list[dict], today: date | None = None, days: int = 10) -> list[dict]:
    """One cell per day for the next `days` days: sessions and deadlines on it."""
    today = today or date.today()
    plan = build_plan(deadlines, today)
    out = []
    for i in range(days):
        d = (today + timedelta(days=i)).isoformat()
        out.append({
            "day": d,
            "sessions": [p for p in plan if p["day"] == d],
            "due": [dl for dl in deadlines if dl["due"] == d],
        })
    return out
