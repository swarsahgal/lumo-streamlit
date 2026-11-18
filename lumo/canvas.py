"""Canvas LMS connection: courses, syllabus, assignments, quizzes and calendar events.

Uses the Canvas REST API with the student's personal access token
(Canvas > Account > Settings > + New Access Token). The token is kept only in
the browser session and is never written to disk.
"""
import html
import io
import re
from datetime import date, datetime, timedelta, timezone

import requests

TIMEOUT = 20


class CanvasError(Exception):
    pass


def normalize_base(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise CanvasError("Enter your school's Canvas address, e.g. canvas.myschool.edu")
    if not url.startswith("http"):
        url = "https://" + url
    return re.sub(r"/api/v1.*$", "", url)


class Canvas:
    def __init__(self, base_url: str, token: str):
        self.base = normalize_base(base_url)
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token.strip()}"

    def _get(self, path, params=None, paginate=True, limit=500):
        url = path if path.startswith("http") else f"{self.base}/api/v1{path}"
        params = dict(params or {})
        params.setdefault("per_page", 100)
        out = []
        while url and len(out) < limit:
            r = self.s.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 401:
                raise CanvasError("Canvas didn't accept that token. Check it hasn't expired.")
            if r.status_code == 403:
                raise CanvasError("Canvas blocked that request. Your school may limit API access.")
            if r.status_code == 404:
                return out if paginate else None
            r.raise_for_status()
            data = r.json()
            if not paginate:
                return data
            out.extend(data if isinstance(data, list) else [data])
            url, params = r.links.get("next", {}).get("url"), None
        return out

    # ---- reads
    def me(self) -> dict:
        return self._get("/users/self/profile", paginate=False) or {}

    def courses(self) -> list[dict]:
        cs = self._get("/courses", {"enrollment_state": "active",
                                    "include[]": ["syllabus_body", "term"]})
        return [c for c in cs if c.get("name") and not c.get("access_restricted_by_date")]

    def assignments(self, course_id) -> list[dict]:
        return self._get(f"/courses/{course_id}/assignments", {"order_by": "due_at"})

    def events(self, course_id, start: date, end: date) -> list[dict]:
        return self._get("/calendar_events", {"type": "event", "context_codes[]": f"course_{course_id}",
                                              "start_date": start.isoformat(), "end_date": end.isoformat()})

    def modules(self, course_id) -> list[dict]:
        return self._get(f"/courses/{course_id}/modules", limit=60)

    def syllabus_file_text(self, course_id) -> str:
        """Look for an uploaded file named like a syllabus and return its text."""
        files = self._get(f"/courses/{course_id}/files", {"search_term": "syllabus"}, limit=10)
        for f in files:
            name = (f.get("display_name") or "").lower()
            if not name.endswith((".pdf", ".txt", ".md", ".html")):
                continue
            r = self.s.get(f["url"], timeout=TIMEOUT)
            if not r.ok:
                continue
            if name.endswith(".pdf"):
                from pypdf import PdfReader
                return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)
            return strip_html(r.text)
        return ""


# ---------------------------------------------------------------- helpers

def strip_html(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</tr>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def _day(iso: str | None):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().date().isoformat()
    except ValueError:
        return None


EXAM_WORDS = re.compile(r"\b(exam|midterm|final|test|quiz|assessment)\b", re.I)


def kind_of(name: str, is_quiz: bool = False) -> str:
    if re.search(r"\b(exam|midterm|final|test)\b", name, re.I):
        return "exam"
    if is_quiz or re.search(r"\bquiz\b", name, re.I):
        return "quiz"
    return "assignment"


def pull(cv: Canvas, today: date | None = None, horizon_days: int = 120) -> dict:
    """Everything Lumo needs from Canvas, as plain dicts."""
    today = today or date.today()
    end = today + timedelta(days=horizon_days)
    me = cv.me()
    courses = []
    for c in cv.courses():
        cid = c["id"]
        items = []
        for a in cv.assignments(cid):
            due = _day(a.get("due_at"))
            items.append({"title": a.get("name", "Assignment"), "due": due,
                          "kind": kind_of(a.get("name", ""), bool(a.get("is_quiz_assignment") or a.get("quiz_id"))),
                          "source": "Canvas assignment",
                          "description": strip_html(a.get("description") or "")[:600]})
        for e in cv.events(cid, today, end):
            items.append({"title": e.get("title", "Event"), "due": _day(e.get("start_at")),
                          "kind": kind_of(e.get("title", "")), "source": "Canvas calendar",
                          "description": strip_html(e.get("description") or "")[:600]})
        syllabus = strip_html(c.get("syllabus_body") or "")
        if len(syllabus) < 200:
            try:
                syllabus = (syllabus + "\n" + cv.syllabus_file_text(cid)).strip()
            except Exception:
                pass
        try:
            mods = [m.get("name", "") for m in cv.modules(cid)]
        except Exception:
            mods = []
        courses.append({"id": cid, "name": c.get("name"), "code": c.get("course_code", ""),
                        "term": (c.get("term") or {}).get("name", ""),
                        "syllabus": syllabus[:20000], "modules": mods, "items": items})
    return {"student": {"name": (me.get("short_name") or me.get("name") or "").split(" ")[0],
                        "canvas_id": me.get("id")},
            "courses": courses}


# ---------------------------------------------------------------- sample data (no Canvas account needed)

def sample(today: date | None = None) -> dict:
    t = today or date.today()
    d = lambda n: (t + timedelta(days=n)).isoformat()
    return {
        "student": {"name": "Maya", "canvas_id": "sample"},
        "courses": [
            {"id": 101, "name": "Biology 9 Honors", "code": "BIO9H", "term": "Fall",
             "modules": ["Unit 3: Cells", "Unit 4: Cell Energy", "Unit 5: Genetics"],
             "syllabus": ("Biology 9 Honors. Grading: tests 50%, labs 30%, homework 20%. "
                          "Unit 3 Cells: organelles, membranes, transport. "
                          f"Unit 4 Cell Energy: photosynthesis and cellular respiration; Unit 4 test on {d(9)}. "
                          "Unit 5 Genetics: DNA, Mendel, Punnett squares. Midterm exam covers Units 1-4 (date TBA). "
                          "Lab reports are due one week after each lab."),
             "items": [
                 {"title": "Photosynthesis lab report", "due": d(4), "kind": "assignment", "source": "Canvas assignment", "description": ""},
                 {"title": "Unit 4 quiz: cellular respiration", "due": d(6), "kind": "quiz", "source": "Canvas assignment", "description": ""},
                 {"title": "Unit 4 test", "due": d(9), "kind": "exam", "source": "Canvas calendar", "description": ""},
             ]},
            {"id": 102, "name": "English 9", "code": "ENG9", "term": "Fall",
             "modules": ["Persuasive writing", "To Kill a Mockingbird"],
             "syllabus": ("English 9. Persuasive essay unit: thesis statements, topic sentences, evidence. "
                          "Reading: To Kill a Mockingbird, chapters 1-15 by the unit test. "
                          "Final essay due at end of unit."),
             "items": [
                 {"title": "Persuasive essay draft", "due": d(7), "kind": "assignment", "source": "Canvas assignment", "description": ""},
                 {"title": "Mockingbird reading check", "due": d(11), "kind": "quiz", "source": "Canvas assignment", "description": ""},
                 {"title": "Final persuasive essay", "due": None, "kind": "assignment", "source": "Canvas assignment", "description": ""},
             ]},
            {"id": 103, "name": "Algebra I", "code": "ALG1", "term": "Fall",
             "modules": ["Linear equations", "Systems of equations"],
             "syllabus": "",
             "items": [
                 {"title": "Systems of equations test", "due": d(13), "kind": "exam", "source": "Canvas calendar", "description": ""},
             ]},
        ],
    }
