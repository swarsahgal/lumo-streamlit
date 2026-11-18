"""Interest matcher: a Thompson-sampling bandit per subject.

Each (subject, interest) pair keeps a Beta(alpha, beta) belief about how well
that interest works as a hook for that subject. After each lesson we reward the
pair with the share of questions answered right on the first try, so the matcher
learns which interest teaches which subject best for this student.
"""
import random


def _key(subject: str, interest: str) -> str:
    return f"{subject}::{interest}"


def pick_interest(stats: dict, subject: str, interests: list[str], rng=random) -> str:
    """Sample each arm's Beta posterior and return the interest with the highest draw."""
    if not interests:
        return "everyday life"
    best, best_draw = interests[0], -1.0
    for interest in interests:
        a, b = stats.get(_key(subject, interest), [1.0, 1.0])
        draw = rng.betavariate(a, b)
        if draw > best_draw:
            best, best_draw = interest, draw
    return best


def update(stats: dict, subject: str, interest: str, reward: float) -> None:
    """reward in [0, 1]: fractional success, added to alpha / beta."""
    reward = max(0.0, min(1.0, reward))
    a, b = stats.get(_key(subject, interest), [1.0, 1.0])
    stats[_key(subject, interest)] = [a + reward, b + (1 - reward)]


def table(stats: dict, subjects: list[str], interests: list[str]) -> list[dict]:
    """Rows for the parent view: estimated fit and lessons taught per pair."""
    rows = []
    for s in subjects:
        for i in interests:
            a, b = stats.get(_key(s, i), [1.0, 1.0])
            n = a + b - 2
            if n <= 0:
                continue
            rows.append({"Subject": s, "Interest": i,
                         "Fit": round(a / (a + b) * 100), "Lessons": int(round(n))})
    rows.sort(key=lambda r: (r["Subject"], -r["Fit"]))
    return rows
