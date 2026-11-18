"""Turn raw Canvas data into a study framework, and list what's still missing.

For each course: a short subject name, its topics, every dated deadline (from Canvas
and from the syllabus), which topic each deadline covers, and questions for the
student about anything Lumo couldn't work out.
"""
import json
import re
from datetime import date

from . import llm


def _guess_topic(title: str, topics: list[str]) -> str:
    t = title.lower()
    best, score = "", 0
    for topic in topics:
        words = [w for w in re.findall(r"[a-z]{4,}", topic.lower())]
        s = sum(w in t for w in words)
        m = re.search(r"unit\s*(\d+)", t)
        if m and re.search(rf"unit\s*{m.group(1)}\b", topic.lower()):
            s += 3
        if s > score:
            best, score = topic, s
    return best


def _offline_extract(course: dict) -> dict:
    topics = [re.sub(r"^(unit|module|week)\s*\d+\s*[:\-]\s*", "", m, flags=re.I).strip() or m
              for m in course.get("modules", []) if m]
    syl = course.get("syllabus", "")
    extra = []
    for m in re.finditer(r"([A-Z][\w ]{0,30}?(?:midterm|final|exam|test))[^.]*?\((?:date )?TBA\)|"
                         r"((?:midterm|final) exam[^.]*?TBA)", syl, re.I):
        extra.append({"title": (m.group(1) or m.group(2)).strip().capitalize()[:60], "due": None,
                      "kind": "exam", "topic": ""})
    # match "Unit 4 test" to the "Unit 4: ..." module even though the topic name drops the prefix
    item_topics = {}
    for it in course.get("items", []):
        m = re.search(r"unit\s*(\d+)", it["title"], re.I)
        if not m:
            continue
        for mod, topic in zip(course.get("modules", []), topics):
            if re.search(rf"unit\s*{m.group(1)}\b", mod, re.I):
                item_topics[it["title"]] = topic
    return {"subject": course["name"], "topics": topics, "extra_deadlines": extra,
            "item_topics": item_topics, "questions": []}


def _llm_extract(course: dict, level: str) -> dict:
    items = [{"title": i["title"], "due": i["due"], "kind": i["kind"]} for i in course["items"]][:60]
    prompt = f"""You are setting up a study plan for a {level} student with ADHD.
Course: {course['name']} ({course.get('code', '')}), term {course.get('term', '')}.
Canvas modules: {json.dumps(course.get('modules', [])[:40])}
Canvas items (assignments, quizzes, calendar events): {json.dumps(items)}
Syllabus text:
<<<
{course.get('syllabus', '')[:15000]}
>>>
Today is {date.today().isoformat()}.

Work out:
- subject: a short subject name for this course (e.g. "Biology", "Algebra I").
- topics: the course's teachable topics in order, 3-15 short names.
- extra_deadlines: tests, exams, projects or due dates mentioned in the syllabus that are NOT already in the Canvas items. Use ISO dates when the syllabus gives one (assume the current school year), else null.
- item_topics: for each Canvas item title that maps to a topic, the topic it covers.
- questions: up to 4 short questions for the student about things a study plan needs but you can't tell (e.g. a test date marked TBA, what a test covers). Don't ask about things already answered.
Return JSON: {{"subject": str, "topics": [str], "extra_deadlines": [{{"title": str, "due": "YYYY-MM-DD"|null, "kind": "exam|quiz|assignment", "topic": str}}], "item_topics": {{"title": "topic"}}, "questions": [str]}}"""
    return llm._call(prompt, max_tokens=2000)


def build(courses: list[dict], level: str) -> list[dict]:
    out = []
    for c in courses:
        try:
            x = _llm_extract(c, level) if llm.live() else _offline_extract(c)
        except Exception:
            x = _offline_extract(c)
        topics = [t for t in x.get("topics", []) if t] or [m for m in c.get("modules", []) if m]
        deadlines = []
        seen = set()
        for it in c["items"] + [{**e, "source": "Syllabus"} for e in x.get("extra_deadlines", [])]:
            key = it["title"].strip().lower()
            if key in seen:
                continue
            seen.add(key)
            topic = (x.get("item_topics", {}).get(it["title"]) or it.get("topic")
                     or _guess_topic(it["title"], topics))
            deadlines.append({"title": it["title"], "due": it.get("due"), "kind": it.get("kind", "assignment"),
                              "topic": topic or "", "source": it.get("source", "Canvas")})
        today = date.today().isoformat()
        deadlines = [d for d in deadlines if not d["due"] or d["due"] >= today]
        out.append({"course": c["name"], "subject": x.get("subject") or c["name"], "topics": topics,
                    "deadlines": deadlines, "syllabus": c.get("syllabus", ""),
                    "llm_questions": x.get("questions", [])[:4]})
    return out


def gaps(fw: list[dict]) -> list[dict]:
    """Questions Lumo needs answered before the plan is complete."""
    qs = []
    for ci, c in enumerate(fw):
        if not c["syllabus"].strip():
            qs.append({"id": f"{ci}-syl", "course": ci, "type": "file",
                       "q": f"I couldn't find a syllabus for {c['course']}. Upload it, or class notes, so lessons match your class."})
        if not c["topics"]:
            qs.append({"id": f"{ci}-topics", "course": ci, "type": "topics",
                       "q": f"What topics is {c['course']} covering this term? (comma-separated)"})
        for di, d in enumerate(c["deadlines"]):
            if d["kind"] in ("exam", "quiz") and not d["due"]:
                qs.append({"id": f"{ci}-{di}-due", "course": ci, "deadline": di, "type": "date",
                           "q": f"When is “{d['title']}” in {c['course']}?"})
            elif d["kind"] == "assignment" and not d["due"]:
                qs.append({"id": f"{ci}-{di}-due", "course": ci, "deadline": di, "type": "date",
                           "q": f"When is “{d['title']}” due in {c['course']}? (skip if you don't know)"})
            if d["kind"] in ("exam", "quiz") and not d["topic"]:
                qs.append({"id": f"{ci}-{di}-topic", "course": ci, "deadline": di, "type": "topic",
                           "q": f"What does “{d['title']}” cover?"})
        if not any(d["kind"] == "exam" for d in c["deadlines"]):
            qs.append({"id": f"{ci}-exam", "course": ci, "type": "new_exam",
                       "q": f"Any tests coming up in {c['course']} that aren't on Canvas? Add one, or skip."})
        for k, q in enumerate(c.get("llm_questions", [])):
            qs.append({"id": f"{ci}-llm{k}", "course": ci, "type": "note", "q": q})
    return qs


def to_profile_deadlines(fw: list[dict]) -> list[dict]:
    out = []
    for c in fw:
        for d in c["deadlines"]:
            if d["due"]:
                out.append({"title": d["title"], "subject": c["subject"], "topic": d["topic"] or d["title"],
                            "due": d["due"], "kind": d["kind"], "source": d["source"]})
    return out
