# Lumo

An AI study companion for students with ADHD. Team 409, Cornell Tech Product Studio.

Lumo teaches each topic through something the student is into, fades that interest
out lesson by lesson, asks the student to teach it back, and paces short sessions
before each deadline instead of one cram night. Parents get a retention view.

## What works

| Screen | What it does |
|---|---|
| **Set up** | **Connect Canvas** (school address + personal access token): Lumo pulls active courses, syllabi (page or uploaded file), modules, assignments, quizzes and calendar events, works out each course's topics and what each test covers, then asks the student only for what's missing (TBA exam dates, what a test covers, a syllabus it couldn't find). Or set up by hand: any grade from 1 to college, any subject, class files, deadlines, .ics calendar. |
| **Today** | Energy check (Low / Okay / Wired sets session length), a 10-day runway of sessions before each deadline, today's sessions, review bank. |
| **Lesson** | Claude writes a 4-step lesson from the class files, framed in the interest Lumo picks. The hook fades each step; step 4 is a plain question that measures transfer. Wrong answers get hints, never a red X. Ends with a teach-back that Claude grades: what you got, what's missing. |
| **Parent view** | Retention without the hook, lessons and sessions done vs planned, weak spots, which interests work for which subject, recent lessons. |

The interest matcher is a Thompson-sampling bandit per subject: each lesson's
first-try accuracy updates its belief about how well that interest teaches that subject.

**Demo mode:** with no API key, Lumo runs on built-in lessons (equivalent fractions and
paragraph structure) so anyone can click through. Add a key for live lessons on any topic.

## Canvas

Students connect with a personal access token (Canvas → Account → Settings → **+ New Access Token**).
The token stays in the browser session only; it is never saved to disk or the repo. Some schools
disable student tokens; a school-wide rollout would use Canvas OAuth with a developer key issued by
the school's Canvas admin. **Try sample Canvas data** on the Set up page shows the full flow without an account.

Without an API key, syllabus reading falls back to simple rules (modules become topics, "Unit N"
items map to Unit N), and lessons outside the two built-in topics show a sample lesson.

## Run it locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then paste your key
streamlit run app.py
```

## Host it on Streamlit Community Cloud (free)

1. Put this folder in a GitHub repo (public or private).
2. Go to https://share.streamlit.io, sign in with GitHub, click **Create app**.
3. Pick the repo and branch, set the main file to `app.py`, then **Deploy**.
4. In the app's **Settings → Secrets**, paste:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   Get a key at https://console.anthropic.com. Optional: `LUMO_MODEL = "claude-sonnet-5-5"`.

Without the secret the app still runs in demo mode.

## Notes

- Progress lives in the session and in `data/<name>.json` on the server. Streamlit
  Cloud can wipe that folder on restart, so use **Download progress / Load progress**
  in the sidebar to keep a student's history across visits.
- Each live lesson is about one Claude call (about 30K tokens in, 5K out, with class files).
- Lessons are prompted to stay faithful to uploaded class material and to be
  school-appropriate, but they are AI-generated: spot-check them before real students use it.

## Files

```
app.py               screens and lesson flow
lumo/llm.py          Claude prompts, JSON parsing, built-in demo lessons
lumo/matcher.py      interest matcher (bandit)
lumo/planner.py      deadline-paced session plan
lumo/state.py        profile, saving, PDF and .ics reading
lumo/canvas.py       Canvas API client and sample data
lumo/framework.py    syllabus reading, deadline merge, missing-info questions
lumo/ui.py           mascot and styling
```
