"""Student profile and progress, kept in session state and saved to a JSON file."""
import io
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

INTEREST_OPTIONS = ["Basketball", "Minecraft", "Video games", "Music", "Soccer",
                    "Dinosaurs", "Drawing", "Space", "Cooking", "Animals"]
SUBJECT_OPTIONS = ["Math", "English", "Science", "History"]


def blank_profile() -> dict:
    return {
        "name": "", "grade": 7, "interests": [], "subjects": ["Math", "English"],
        "materials": {},          # subject -> [{name, text}]
        "deadlines": [],          # [{title, subject, topic, due}]
        "energy": "Okay",
        "bandit": {},             # matcher stats
        "history": [],            # finished lessons
        "review_bank": [],        # [{concept, subject, added}]
        "onboarded": False,
    }


def demo_profile() -> dict:
    today = date.today()
    p = blank_profile()
    p.update({
        "name": "Sam", "grade": 7, "interests": ["Basketball", "Minecraft", "Drawing"],
        "deadlines": [
            {"title": "Paragraph assignment", "subject": "English", "topic": "Paragraph structure",
             "due": (today + timedelta(days=6)).isoformat()},
            {"title": "Unit 4 test", "subject": "Math", "topic": "Equivalent fractions",
             "due": (today + timedelta(days=8)).isoformat()},
        ],
        "onboarded": True,
    })
    return p


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "student"


def save(profile: dict) -> None:
    if not profile.get("name"):
        return
    try:
        DATA_DIR.mkdir(exist_ok=True)
        (DATA_DIR / f"{slug(profile['name'])}.json").write_text(json.dumps(profile, indent=1))
    except OSError:
        pass  # read-only hosts: progress still lives in the session and the download button


def load_saved(name: str):
    path = DATA_DIR / f"{slug(name)}.json"
    if path.exists():
        return {**blank_profile(), **json.loads(path.read_text())}
    return None


def profile() -> dict:
    if "profile" not in st.session_state:
        st.session_state.profile = blank_profile()
    return st.session_state.profile


def extract_text(upload) -> str:
    name = upload.name.lower()
    data = upload.getvalue()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return data.decode("utf-8", errors="ignore")


def parse_ics(text: str, subject: str) -> list[dict]:
    """Minimal .ics reader: each VEVENT's SUMMARY and DTSTART become a deadline."""
    out, cur = [], {}
    for raw in text.splitlines():
        line = raw.strip()
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line.startswith("SUMMARY"):
            cur["title"] = line.split(":", 1)[-1]
        elif line.startswith("DTSTART"):
            val = line.split(":", 1)[-1][:8]
            try:
                cur["due"] = datetime.strptime(val, "%Y%m%d").date().isoformat()
            except ValueError:
                pass
        elif line == "END:VEVENT" and cur.get("title") and cur.get("due"):
            if cur["due"] >= date.today().isoformat():
                out.append({"title": cur["title"], "subject": subject,
                            "topic": cur["title"], "due": cur["due"]})
    return out
