"""Frictionless ways in: a calendar feed link, syllabus files, screenshots.

Each importer returns courses in the same shape as canvas.pull():
{"name", "code", "term", "syllabus", "modules", "items": [{title, due, kind, source, description}]}
"""
import io
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from . import canvas, llm

DEFAULT_TZ = "America/New_York"


# ================================================================ file text, any format

TEXT_TYPES = ["pdf", "docx", "pptx", "xlsx", "txt", "md", "html", "htm", "csv", "rtf",
              "png", "jpg", "jpeg", "webp"]


def file_text(name: str, data: bytes) -> str:
    n = name.lower()
    if n.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    if n.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    if n.endswith(".pptx"):
        from pptx import Presentation
        prs = Presentation(io.BytesIO(data))
        out = []
        for i, slide in enumerate(prs.slides, 1):
            out.append(f"--- Slide {i} ---")
            for shape in slide.shapes:
                if shape.has_text_frame:
                    out.append(shape.text_frame.text)
                if getattr(shape, "has_table", False) and shape.has_table:
                    for row in shape.table.rows:
                        out.append(" | ".join(c.text for c in row.cells))
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                out.append("Notes: " + slide.notes_slide.notes_text_frame.text)
        return "\n".join(out)
    if n.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"--- {ws.title} ---")
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    out.append(" | ".join("" if v is None else str(v) for v in row))
        return "\n".join(out)
    if n.endswith((".png", ".jpg", ".jpeg", ".webp")):
        mime = "image/png" if n.endswith(".png") else "image/webp" if n.endswith(".webp") else "image/jpeg"
        return llm.read_image_text(data, mime)
    text = data.decode("utf-8", errors="ignore")
    if n.endswith((".html", ".htm")):
        return canvas.strip_html(text)
    if n.endswith(".rtf"):
        text = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", text)
    return text


# ================================================================ calendar feed (.ics link)

def _unfold(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _ics_value(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").strip()


def _ics_date(key: str, val: str, tz: str) -> str | None:
    val = val.strip()
    try:
        if "VALUE=DATE" in key or len(val) == 8:
            return datetime.strptime(val[:8], "%Y%m%d").date().isoformat()
        dt = datetime.strptime(val[:15], "%Y%m%dT%H%M%S")
        if val.endswith("Z"):
            dt = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
        return dt.date().isoformat()
    except ValueError:
        return None


def parse_ics_feed(text: str, tz: str = DEFAULT_TZ, today: date | None = None) -> list[dict]:
    """Events -> courses. Canvas feeds put the course in brackets: 'Essay draft [English 9]'."""
    today = today or date.today()
    events, cur = [], None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, val = line.split(":", 1)
            name = key.split(";")[0]
            if name == "SUMMARY":
                cur["summary"] = _ics_value(val)
            elif name == "DTSTART":
                cur["due"] = _ics_date(key, val, tz)
            elif name == "DESCRIPTION":
                cur["description"] = _ics_value(val)[:600]
    courses: dict[str, dict] = {}
    for e in events:
        s = e.get("summary", "").strip()
        if not s or not e.get("due") or e["due"] < today.isoformat():
            continue
        m = re.match(r"^(.*?)\s*\[([^\]]+)\]\s*$", s)
        title, course = (m.group(1), m.group(2)) if m else (s, "My calendar")
        c = courses.setdefault(course, {"name": course, "code": "", "term": "", "syllabus": "",
                                        "modules": [], "items": []})
        c["items"].append({"title": title, "due": e["due"], "kind": canvas.kind_of(title),
                           "source": "Calendar feed", "description": e.get("description", "")})
    return list(courses.values())


def fetch_ics(url: str, tz: str = DEFAULT_TZ) -> list[dict]:
    url = url.strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not url.startswith("http"):
        url = "https://" + url
    r = requests.get(url, timeout=20)
    if r.status_code in (401, 403, 404):
        raise ValueError("That link didn't work. Copy the Calendar Feed link again from Canvas.")
    r.raise_for_status()
    if "BEGIN:VCALENDAR" not in r.text[:2000]:
        raise ValueError("That link isn't a calendar feed. In Canvas, open Calendar and copy the 'Calendar Feed' link.")
    return parse_ics_feed(r.text, tz)


# ================================================================ syllabus files & screenshots

MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
DATE_RE = re.compile(rf"\b(?:(?P<mon>{MONTHS})[a-z]*\.?\s+(?P<day>\d{{1,2}})(?:,?\s+(?P<yr>\d{{4}}))?"
                     rf"|(?P<m>\d{{1,2}})/(?P<d>\d{{1,2}})(?:/(?P<y>\d{{2,4}}))?)\b", re.I)


def _resolve(m, today: date) -> str | None:
    try:
        if m.group("mon"):
            mon = datetime.strptime(m.group("mon")[:3].title(), "%b").month
            day, yr = int(m.group("day")), m.group("yr")
        else:
            mon, day, yr = int(m.group("m")), int(m.group("d")), m.group("y")
        year = int(yr) + (2000 if yr and len(yr) == 2 else 0) if yr else today.year
        d = date(year, mon, day)
        if not yr and d < today - timedelta(days=60):
            d = date(year + 1, mon, day)  # spring dates in a fall-written syllabus
        return d.isoformat()
    except (ValueError, TypeError):
        return None


def syllabus_dates_offline(text: str, today: date | None = None) -> list[dict]:
    """Rule-based: lines that mention a test/quiz/due word and a date."""
    today = today or date.today()
    items = []
    for line in text.splitlines():
        if not re.search(r"\b(exam|midterm|final|test|quiz|due|project|essay|paper|presentation)\b", line, re.I):
            continue
        m = DATE_RE.search(line)
        if not m:
            continue
        due = _resolve(m, today)
        if not due or due < today.isoformat():
            continue
        title = re.sub(r"\s+", " ", DATE_RE.sub("", line)).strip(" -–:|,.")[:80] or "Deadline"
        items.append({"title": title, "due": due, "kind": canvas.kind_of(title),
                      "source": "Syllabus", "description": ""})
    return items


def course_from_file(name: str, text: str) -> dict:
    base = re.sub(r"[_\-]+", " ", re.sub(r"\.[a-z0-9]+$", "", name, flags=re.I))
    base = re.sub(r"\bsyllabus\b", "", base, flags=re.I).strip() or "My class"
    items = [] if llm.live() else syllabus_dates_offline(text)  # live: framework reads dates with Claude
    return {"name": base.title() if base.islower() else base, "code": "", "term": "",
            "syllabus": text[:20000], "modules": [], "items": items}


def courses_from_screenshot(data: bytes, mime: str) -> list[dict]:
    courses: dict[str, dict] = {}
    for it in llm.read_image_deadlines(data, mime, date.today().isoformat()):
        cname = it.get("course") or "My calendar"
        c = courses.setdefault(cname, {"name": cname, "code": "", "term": "", "syllabus": "",
                                       "modules": [], "items": []})
        c["items"].append({"title": it.get("title", "Deadline"), "due": it.get("due"),
                           "kind": it.get("kind") or canvas.kind_of(it.get("title", "")),
                           "source": "Screenshot", "description": ""})
    return list(courses.values())


# ================================================================ merging sources

def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 1 and w not in {"the", "and", "of", "class", "course"}}


def merge(courses: list[dict]) -> list[dict]:
    """Combine courses from different sources when their names overlap (e.g. 'Bio 9H' feed + 'Biology 9 Honors syllabus')."""
    out: list[dict] = []
    for c in courses:
        match = None
        for o in out:
            a, b = _words(c["name"]), _words(o["name"])
            if a and b and (a <= b or b <= a or len(a & b) >= 2):
                match = o
                break
        if match is None:
            out.append({**c, "items": list(c["items"]), "modules": list(c["modules"])})
            continue
        if len(c["name"]) > len(match["name"]) and c["items"]:
            match["name"] = c["name"]
        match["syllabus"] = (match["syllabus"] + "\n\n" + c["syllabus"]).strip()
        match["modules"] += [m for m in c["modules"] if m not in match["modules"]]
        have = {i["title"].lower() for i in match["items"]}
        match["items"] += [i for i in c["items"] if i["title"].lower() not in have]
    for i, c in enumerate(out):
        c.setdefault("id", f"c{i}")
    return out
