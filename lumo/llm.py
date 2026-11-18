"""Claude-backed lesson generation and teach-back grading, with an offline demo fallback."""
import json
import os
import re

import streamlit as st

DEFAULT_MODEL = "claude-sonnet-5-5"
HOOK_LEVELS = ["full", "partial", "light", "none"]

SYSTEM = (
    "You are Lumo, a warm study companion for students with ADHD, from elementary school through college. "
    "Write short, concrete, upbeat text pitched at the student's level. "
    "Never shame mistakes; wrong answers get a gentle nudge, never a red X. "
    "Never ask for personal information. Keep everything school-appropriate. "
    "When class material is provided, stay faithful to it and do not invent facts "
    "that contradict it. Reply with JSON only, no prose before or after."
)


def _secret(name: str):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name)


def api_key():
    return _secret("ANTHROPIC_API_KEY")


def model():
    return _secret("LUMO_MODEL") or DEFAULT_MODEL


def live() -> bool:
    return bool(api_key())


def _call(prompt: str, max_tokens: int = 2500) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key())
    msg = client.messages.create(
        model=model(), max_tokens=max_tokens, system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("Lumo got an unexpected reply. Try again.")
    return json.loads(match.group(0))


# ---------------------------------------------------------------- lessons

def generate_lesson(subject: str, topic: str, grade, interest: str,
                    material: str = "", weak_spots: list[str] | None = None) -> dict:
    if not live():
        return offline_lesson(subject, topic, interest)
    excerpt = (material or "").strip()[:12000]
    weak = ", ".join(weak_spots or []) or "none yet"
    prompt = f"""Make a 4-step micro-lesson.
Student level: {grade}. Subject: {subject}. Topic: {topic}.
Hook interest: {interest}. Concepts this student found hard before: {weak}.

Fade the hook across the steps:
- step 1 hook_level "full": the whole explanation and question live inside {interest}.
- step 2 hook_level "partial": {interest} appears only as a light example.
- step 3 hook_level "light": a passing mention of {interest} at most.
- step 4 hook_level "none": a plain school-style question with NO mention of {interest}. This step measures transfer.
Each explanation is 2-4 short sentences. Each question has exactly 4 choices, one correct.
Give two hints per question that nudge without giving the answer away.

Class material (may be empty; if present, base the lesson on it):
<<<
{excerpt}
>>>

Return JSON exactly in this shape:
{{"topic": str, "interest": str,
  "steps": [{{"hook_level": "full|partial|light|none", "title": str, "explain": str,
             "question": str, "choices": [str, str, str, str], "answer_index": 0-3,
             "hints": [str, str], "why": str}}],
  "teachback_prompt": str,
  "key_points": [str, str, str]}}
key_points are the 2-3 ideas a good teach-back must include."""
    data = _call(prompt)
    _validate(data)
    return data


def _validate(data: dict) -> None:
    steps = data.get("steps") or []
    if len(steps) < 2:
        raise ValueError("Lesson came back incomplete. Try again.")
    for i, s in enumerate(steps):
        s.setdefault("hook_level", HOOK_LEVELS[min(i, 3)])
        s.setdefault("title", f"Step {i + 1}")
        s["choices"] = list(s.get("choices", []))[:4]
        if len(s["choices"]) < 2:
            raise ValueError("A question came back without choices. Try again.")
        s["answer_index"] = int(s.get("answer_index", 0)) % len(s["choices"])
        s.setdefault("hints", ["Read the question once more.", "Rule out one choice first."])
        s.setdefault("why", "")
    data.setdefault("key_points", [])
    data.setdefault("teachback_prompt", f"Explain {data.get('topic', 'this')} in your own words.")


# ---------------------------------------------------------------- teach-back

def grade_teachback(topic: str, prompt_text: str, key_points: list[str], answer: str) -> dict:
    if not answer.strip():
        return {"got": [], "missing": key_points, "reply": "Give it a try in your own words, even one sentence."}
    if not live():
        return offline_grade(key_points, answer)
    prompt = f"""A student was asked: "{prompt_text}" (topic: {topic}).
Key points a complete answer covers: {json.dumps(key_points)}.
Student's explanation: \"\"\"{answer[:2000]}\"\"\"

Judge generously: credit a key point if the idea is there in the student's own words.
Return JSON: {{"got": [key points they covered, short], "missing": [key points not covered, short],
"reply": "one or two encouraging sentences that name what they did well and the one thing to add"}}"""
    return _call(prompt, max_tokens=800)


# ---------------------------------------------------------------- topics from files

def suggest_topics(subject: str, material: str) -> list[str]:
    if not material.strip():
        return []
    if not live():
        heads = [l.strip("#*- \t") for l in material.splitlines()
                 if 3 < len(l.strip()) < 60 and (l.strip().startswith("#") or l.strip().istitle())]
        return list(dict.fromkeys(heads))[:6]
    prompt = f"""From this {subject} class material, list up to 8 teachable topics a
student would study for a test, each 2-5 words.
<<<
{material[:12000]}
>>>
Return JSON: {{"topics": [str]}}"""
    try:
        return _call(prompt, max_tokens=400).get("topics", [])[:6]
    except Exception:
        return []


# ================================================================ offline demo content

NOUNS = {
    "basketball": ("free throws", "shots", "a basketball team"),
    "minecraft": ("diamond blocks", "blocks", "a Minecraft build"),
    "video games": ("coins", "levels", "a video game"),
    "music": ("beats", "notes", "a song"),
    "soccer": ("penalty kicks", "goals", "a soccer match"),
    "dinosaurs": ("dinosaur eggs", "fossils", "a dig site"),
    "drawing": ("sketches", "pages", "a sketchbook"),
}


def _nouns(interest):
    return NOUNS.get(interest.lower(), (f"{interest} cards", f"{interest} items", interest))


def offline_lesson(subject: str, topic: str, interest: str) -> dict:
    lesson = _offline_lesson(subject, topic, interest)
    t = f"{subject} {topic}".lower()
    lesson["sample"] = not any(w in t for w in ("fraction", "paragraph", "sentence", "english", "essay", "writing"))
    return lesson


def _offline_lesson(subject: str, topic: str, interest: str) -> dict:
    a, b, scene = _nouns(interest)
    if any(w in f"{subject} {topic}".lower() for w in ("eng", "paragraph", "sentence", "essay", "writing")):
        steps = [
            {"hook_level": "full", "title": "Find the main idea",
             "explain": f"A paragraph is like {scene}: one big idea holds it together. The topic sentence says that big idea, usually first.",
             "question": f"Which sentence could start a paragraph about why {interest.lower()} takes skill?",
             "choices": [f"{interest.capitalize()} takes more planning than most people think.",
                         f"I did some {interest.lower()} yesterday after school.",
                         "My friend has a new phone.",
                         "Some people like pizza."],
             "answer_index": 0,
             "hints": ["Look for the sentence the others could support.", "Which one is a big idea, not a single moment?"],
             "why": "It states one main idea the rest of the paragraph can back up."},
            {"hook_level": "partial", "title": "Spot the support",
             "explain": "Supporting details give reasons or examples for the topic sentence. If a detail doesn't back up the main idea, it doesn't belong.",
             "question": "Topic sentence: 'Practice makes players better.' Which detail supports it?",
             "choices": [f"Players who practice {b} every day improve faster.",
                         "The gym was painted blue.", "Practice starts at four.", "Some players have long hair."],
             "answer_index": 0,
             "hints": ["Which one gives a reason the topic sentence is true?", "Ignore details that are just facts about something else."],
             "why": "It gives evidence that practice leads to improvement."},
            {"hook_level": "light", "title": "Close it out",
             "explain": "A concluding sentence wraps up the paragraph by restating the main idea in new words.",
             "question": "Which sentence best concludes a paragraph about why sleep matters?",
             "choices": ["Getting enough sleep helps you think, feel and play your best.",
                         "Some people have bunk beds.", "Last night I woke up at 3.", "Pillows can be soft."],
             "answer_index": 0,
             "hints": ["Which one sounds like an ending?", "It should echo the main idea."],
             "why": "It restates the main idea and sums up the paragraph."},
            {"hook_level": "none", "title": "On your own",
             "explain": "Same skill, no hook this time.",
             "question": "These details: teens need about 9 hours of sleep; early classes cut into that; tired students have trouble focusing. Which topic sentence fits?",
             "choices": ["School should start later so teens can get enough sleep.",
                         "Sleep is important for everyone.", "Many teens stay up late on their phones.", "Classes start at 7:30."],
             "answer_index": 0,
             "hints": ["Which choice covers all three details?", "The best topic sentence is specific to these details."],
             "why": "It covers all three details exactly."},
        ]
        return _shuffled({"topic": topic or "Paragraph structure", "interest": interest, "steps": steps,
                "teachback_prompt": "Explain to Lumo what a topic sentence does, and how you spot one.",
                "key_points": ["States the main idea of the paragraph",
                               "Usually comes first",
                               "The supporting details back it up"]})
    steps = [
        {"hook_level": "full", "title": "Same amount, different pieces",
         "explain": f"In {scene}, landing 2 of 4 {a} is the same as 1 of 2. Equivalent fractions name the same amount with different numbers.",
         "question": f"You land 3 of 6 {a}. Which fraction is equivalent?",
         "choices": ["1/2", "1/3", "2/3", "3/4"], "answer_index": 0,
         "hints": ["3 is what part of 6?", "Try dividing top and bottom by 3."],
         "why": "3/6 ÷ 3/3 = 1/2."},
        {"hook_level": "partial", "title": "Scale it up",
         "explain": f"Multiply the top and bottom by the same number to get an equivalent fraction, like doubling a stack of {b}.",
         "question": "Which fraction equals 2/5?",
         "choices": ["4/10", "4/5", "2/10", "5/2"], "answer_index": 0,
         "hints": ["Multiply top and bottom by the same number.", "Try ×2."],
         "why": "2×2 = 4 and 5×2 = 10."},
        {"hook_level": "light", "title": "Simplify",
         "explain": "To simplify, divide top and bottom by the biggest number that goes into both.",
         "question": "Simplify 8/12.",
         "choices": ["2/3", "4/6", "3/4", "1/2"], "answer_index": 0,
         "hints": ["What's the biggest number that divides 8 and 12?", "It's 4."],
         "why": "8 ÷ 4 = 2 and 12 ÷ 4 = 3."},
        {"hook_level": "none", "title": "On your own",
         "explain": "Same skill, no hook this time.",
         "question": "Which fraction is NOT equivalent to 3/4?",
         "choices": ["6/9", "6/8", "9/12", "12/16"], "answer_index": 0,
         "hints": ["Simplify each one.", "Which one doesn't reduce to 3/4?"],
         "why": "6/9 simplifies to 2/3, not 3/4."},
    ]
    return _shuffled({"topic": topic or "Equivalent fractions", "interest": interest, "steps": steps,
            "teachback_prompt": "Explain to Lumo how you know two fractions are equivalent.",
            "key_points": ["They show the same amount",
                           "Multiply or divide top and bottom by the same number",
                           "Simplify to check"]})


def _shuffled(lesson: dict) -> dict:
    """Built-in lessons list the right answer first; shuffle so it isn't always A."""
    import random
    for s in lesson["steps"]:
        right = s["choices"][s["answer_index"]]
        random.shuffle(s["choices"])
        s["answer_index"] = s["choices"].index(right)
    return lesson


def offline_grade(key_points: list[str], answer: str) -> dict:
    words = set(re.findall(r"[a-z]+", answer.lower()))
    got, missing = [], []
    for kp in key_points:
        kw = [w for w in re.findall(r"[a-z]+", kp.lower()) if len(w) > 3]
        (got if kw and sum(w in words for w in kw) >= max(1, len(kw) // 3) else missing).append(kp)
    reply = ("Great explanation, you covered it all!" if not missing
             else f"Nice start. Add this next time: {missing[0].lower()}.")
    return {"got": got, "missing": missing, "reply": reply}
