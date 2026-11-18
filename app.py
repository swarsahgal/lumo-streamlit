"""Lumo: an AI study companion for students with ADHD.

Run locally:  streamlit run app.py
"""
import json
from datetime import date, datetime

import streamlit as st

from lumo import canvas, framework, importers, llm, matcher, planner, state, ui

st.set_page_config(page_title="Lumo", page_icon="🟣", layout="wide")
ui.css()
P = state.profile()
PAGES = ["Set up", "Today", "Lesson", "Parent view"]
if "page" not in st.session_state:
    st.session_state.page = "Today" if P["onboarded"] else "Set up"
if "_goto" in st.session_state:  # navigation requested before the nav widget renders
    st.session_state.page = st.session_state.pop("_goto")


def go(page):
    st.session_state["_goto"] = page


def persist():
    state.save(P)


# ================================================================ sidebar
with st.sidebar:
    st.markdown(ui.mascot(72), unsafe_allow_html=True)
    st.markdown(f"### {'Hi ' + P['name'] if P['name'] else 'Lumo'}")
    if llm.live():
        st.caption(f"Live: lessons written by Claude ({llm.model()})")
    else:
        st.caption("Demo mode: built-in lessons. Add an ANTHROPIC_API_KEY secret for live lessons.")
    st.radio("Go to", PAGES, key="page", label_visibility="collapsed")
    live_cv = st.session_state.get("canvas_live")
    if P.get("canvas"):
        st.caption(f"Canvas connected · {P['canvas'].get('connected', '')}")
        if live_cv and st.button("Refresh from Canvas", width="stretch"):
            with st.spinner("Checking Canvas for new deadlines…"):
                try:
                    raw = canvas.pull(canvas.Canvas(live_cv["base"], live_cv["token"]))
                    keep = {c["subject"] for c in st.session_state.get("fw", [])}
                    st.session_state.canvas_raw = raw
                    st.session_state.fw = framework.build(
                        [c for c in raw["courses"]], state.level_label(P["grade"]))
                    st.session_state.gaps_done = False
                    go("Set up")
                except Exception as e:
                    st.error(f"Refresh failed: {e}")
            st.rerun()
    st.divider()
    st.download_button("Download progress", json.dumps(P, indent=1),
                       file_name=f"lumo-{state.slug(P['name'] or 'student')}.json",
                       mime="application/json", width="stretch")
    up = st.file_uploader("Load progress", type=["json"], label_visibility="collapsed")
    if up is not None and st.button("Load this file", width="stretch"):
        st.session_state.profile = {**state.blank_profile(), **json.loads(up.getvalue())}
        st.session_state.pop("lesson", None)
        st.rerun()
    if st.button("Start over", width="stretch"):
        for k in ["profile", "lesson", "page", "canvas_raw", "canvas_live", "fw", "gaps_done"]:
            st.session_state.pop(k, None)
        st.rerun()


# ================================================================ set up
def page_setup():
    st.markdown('<p class="eyebrow">Set up</p>', unsafe_allow_html=True)
    st.title("Let’s set up your semester")
    ui.say("Paste your calendar link or drop in your syllabi, and I’ll find your classes, tests and due dates. "
           "I’ll only ask you about what I can’t find.")

    c1, c2, c3 = st.columns(3)
    if c1.button("Try the demo student (Sam)", width="stretch"):
        st.session_state.profile = state.demo_profile()
        go("Today")
        st.rerun()
    if c2.button("Try sample Canvas data (Maya)", width="stretch"):
        st.session_state.canvas_raw = canvas.sample()
        st.session_state.canvas_live = None
        st.session_state.pop("fw", None)
        st.rerun()
    with c3:
        returning = st.text_input("Returning? Your first name", placeholder="Load saved progress",
                                  label_visibility="collapsed")
        if returning and st.button("Load my progress", width="stretch"):
            saved = state.load_saved(returning)
            if saved:
                st.session_state.profile = saved
                go("Today")
                st.rerun()
            st.warning("No saved progress under that name on this server.")

    canvas_section()

    st.subheader("About you")
    c1, c2 = st.columns([2, 1])
    P["name"] = c1.text_input("First name", P["name"])
    lvl = state.level_label(P["grade"])
    P["grade"] = c2.selectbox("Grade or level", state.LEVELS,
                              index=state.LEVELS.index(lvl) if lvl in state.LEVELS else 6)

    st.subheader("What are you into?")
    st.caption("Pick a few. Lumo chooses which one to use for each topic.")
    options = sorted(set(state.INTEREST_OPTIONS + P["interests"]))
    P["interests"] = st.multiselect("Interests", options, default=P["interests"],
                                    label_visibility="collapsed")
    extra = st.text_input("Something else?", placeholder="e.g. skateboarding, anime, F1")
    if extra and st.button("Add interest"):
        P["interests"].append(extra.strip().title())
        st.rerun()

    with st.expander("Classes, files and deadlines (add or edit by hand)",
                     expanded=not P.get("canvas")):
        manual_setup()

    st.divider()
    ready = P["name"] and P["interests"]
    if st.button("Build my plan", type="primary", disabled=not ready):
        P["onboarded"] = True
        persist()
        go("Today")
        st.rerun()
    if not ready:
        st.caption("Add your name and at least one interest to continue.")


def canvas_section():
    st.subheader("Bring in your classes")
    raw = st.session_state.get("canvas_raw")
    if not raw:
        import_sources()
        return

    who = raw["student"].get("name") or "you"
    if not P["name"] and raw["student"].get("name"):
        P["name"] = raw["student"]["name"]
    courses = raw["courses"]
    st.success(f"Found {len(courses)} class{'es' if len(courses) != 1 else ''}"
               f"{' for ' + who if who != 'you' else ''}. Untick any you don’t want help with.")
    fw = st.session_state.get("fw")
    if fw is None:
        picked = [c for c in courses if st.checkbox(
            f"**{c['name']}** · {len(c['items'])} items · {'syllabus found' if c['syllabus'] else 'no syllabus'}",
            value=True, key=f"pick_{c['id']}")]
        c1, c2 = st.columns([1, 3])
        if c1.button("Read my courses", type="primary", disabled=not picked):
            with st.spinner("Reading syllabi and lining up your deadlines…"):
                st.session_state.fw = framework.build(picked, state.level_label(P["grade"]))
            st.rerun()
        if c2.button("Start again"):
            for k in ["canvas_raw", "canvas_live", "fw", "sources"]:
                st.session_state.pop(k, None)
            st.rerun()
        return

    st.markdown("#### Here’s what I found")
    for c in fw:
        dated = [d for d in c["deadlines"] if d["due"]]
        with st.expander(f"{c['subject']} · {len(dated)} dated deadlines · {len(c['topics'])} topics"):
            if c["topics"]:
                st.markdown(" ".join(f"<span class='pill'>{t}</span>" for t in c["topics"]),
                            unsafe_allow_html=True)
            for d in sorted(c["deadlines"], key=lambda d: d["due"] or "9999"):
                st.markdown(f"<span class='pill gold'>{d['due'] or 'no date'}</span> **{d['title']}** "
                            f"· {d['kind']}{' · ' + d['topic'] if d['topic'] else ''} "
                            f"<span style='color:#7A7D99'>({d['source']})</span>", unsafe_allow_html=True)

    qs = framework.gaps(fw)
    answered = st.session_state.get("gaps_done", False)
    if qs and not answered:
        st.markdown("#### A few things I couldn’t find")
        ui.say("Answer what you can and skip the rest. You can always add more later.", mood="think")
        with st.form("gaps"):
            ans = {}
            for q in qs:
                k = q["id"]
                if q["type"] == "date":
                    ans[k] = st.date_input(q["q"], value=None, min_value=date.today(), key=f"g_{k}")
                elif q["type"] == "file":
                    ans[k] = st.file_uploader(q["q"], type=importers.TEXT_TYPES, key=f"g_{k}")
                elif q["type"] == "new_exam":
                    a, b = st.columns([2, 1])
                    ans[k] = (a.text_input(q["q"], placeholder="e.g. Chapter 5 test", key=f"g_{k}t"),
                              b.date_input("Date", value=None, min_value=date.today(), key=f"g_{k}d"))
                else:
                    ans[k] = st.text_input(q["q"], key=f"g_{k}")
            if st.form_submit_button("Save and build my plan", type="primary"):
                apply_gaps(fw, qs, ans)
                st.session_state.gaps_done = True
                st.rerun()
    else:
        apply_framework(fw)
        st.info(f"{len(P['deadlines'])} deadlines across {len(fw)} classes are in your plan. "
                "Add your interests below, then build your plan.")
        if st.button("Start over with Canvas"):
            for k in ["canvas_raw", "canvas_live", "fw", "gaps_done", "sources"]:
                st.session_state.pop(k, None)
            st.rerun()


def import_sources():
    """Calendar link, syllabus files, screenshots or a Canvas token. Any mix."""
    srcs = st.session_state.setdefault("sources", [])
    t1, t2, t3, t4 = st.tabs(["📅 Calendar link", "📄 Syllabus & files", "📸 Screenshot", "🔑 Canvas token"])
    with t1:
        st.markdown("Paste your **Canvas Calendar Feed** link. It has every assignment, quiz and test "
                    "across all your classes, and works without any school permission.")
        with st.expander("Where do I find it?"):
            st.markdown("**Canvas:** open **Calendar**, then click **Calendar Feed** at the bottom right "
                        "and copy the link.\n\n"
                        "**Google Calendar:** Settings → your calendar → *Secret address in iCal format*.\n\n"
                        "**Outlook:** Settings → Calendar → Shared calendars → *Publish a calendar* → ICS link.")
        url = st.text_input("Calendar feed link", placeholder="https://canvas.myschool.edu/feeds/calendars/user_….ics")
        if st.button("Add calendar", type="primary", disabled=not url):
            try:
                with st.spinner("Reading your calendar…"):
                    found = importers.fetch_ics(url, llm._secret("LUMO_TZ") or importers.DEFAULT_TZ)
                srcs.extend(found)
                st.success(f"Found {sum(len(c['items']) for c in found)} upcoming items in {len(found)} classes.")
            except Exception as e:
                st.error(str(e) if isinstance(e, ValueError) else f"Couldn’t open that link ({type(e).__name__}).")
    with t2:
        st.markdown("Drop in syllabi, schedules, slides or study guides. One file per class works best. "
                    "Lumo finds the class, topics and test dates.")
        files = st.file_uploader("Syllabus files", type=importers.TEXT_TYPES, accept_multiple_files=True,
                                 label_visibility="collapsed", key="syl_files")
        if files and st.button("Add files", type="primary"):
            with st.spinner("Reading your files…"):
                for f in files:
                    text = importers.file_text(f.name, f.getvalue())
                    if text.strip():
                        srcs.append(importers.course_from_file(f.name, text))
            st.success(f"Added {len(files)} file{'s' if len(files) != 1 else ''}.")
    with t3:
        st.markdown("Screenshot your Canvas **To Do** list, planner or calendar and drop it here.")
        if not llm.live():
            st.caption("Reading screenshots needs the API key (live mode).")
        shots = st.file_uploader("Screenshots", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
                                 label_visibility="collapsed", key="shots")
        if shots and st.button("Read screenshots", type="primary", disabled=not llm.live()):
            with st.spinner("Reading your screenshots…"):
                for f in shots:
                    mime = "image/png" if f.name.lower().endswith(".png") else "image/jpeg"
                    srcs.extend(importers.courses_from_screenshot(f.getvalue(), mime))
            st.success("Done.")
    with t4:
        st.markdown("If your school allows Canvas access tokens, this pulls syllabi and modules too.")
        c1, c2 = st.columns([1, 1])
        base = c1.text_input("Your school’s Canvas address", placeholder="canvas.myschool.edu")
        token = c2.text_input("Canvas access token", type="password", help="Only kept for this session. Never saved.")
        st.caption("Canvas → Account → Settings → **+ New Access Token**. Some schools turn this off.")
        if st.button("Connect Canvas", disabled=not (base and token)):
            try:
                with st.spinner("Reading your Canvas…"):
                    cv = canvas.Canvas(base, token)
                    data = canvas.pull(cv)
                    st.session_state.canvas_live = {"base": cv.base, "token": token}
                srcs.extend(data["courses"])
                if data["student"].get("name") and not P["name"]:
                    P["name"] = data["student"]["name"]
                st.success(f"Found {len(data['courses'])} courses.")
            except canvas.CanvasError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Couldn’t reach Canvas at that address ({type(e).__name__}).")

    if srcs:
        merged = importers.merge(srcs)
        n = sum(len(c["items"]) for c in merged)
        st.markdown(f"**So far:** {len(merged)} classes, {n} deadlines. Add more above, or continue.")
        c1, c2 = st.columns([1, 3])
        if c1.button("Continue", type="primary"):
            st.session_state.canvas_raw = {"student": {}, "courses": merged}
            st.rerun()
        if c2.button("Clear"):
            st.session_state.sources = []
            st.rerun()


def apply_gaps(fw, qs, ans):
    notes = {}
    for q in qs:
        a, c = ans.get(q["id"]), fw[q["course"]]
        if not a:
            continue
        if q["type"] == "date":
            c["deadlines"][q["deadline"]]["due"] = a.isoformat()
        elif q["type"] == "topic":
            c["deadlines"][q["deadline"]]["topic"] = a.strip()
            if a.strip() not in c["topics"]:
                c["topics"].append(a.strip())
        elif q["type"] == "topics":
            c["topics"] = [t.strip() for t in a.split(",") if t.strip()]
        elif q["type"] == "file":
            c["syllabus"] = state.extract_text(a)
        elif q["type"] == "new_exam":
            title, d = a
            if title and d:
                c["deadlines"].append({"title": title, "due": d.isoformat(), "kind": "exam",
                                       "topic": title, "source": "You"})
        elif q["type"] == "note":
            notes.setdefault(q["course"], []).append(f"Q: {q['q']}\nA: {a}")
    for ci, lines in notes.items():
        fw[ci]["syllabus"] += "\n\nNotes from the student:\n" + "\n".join(lines)


def apply_framework(fw):
    """Write the Canvas framework into the profile (idempotent)."""
    P["subjects"] = list(dict.fromkeys(c["subject"] for c in fw))
    manual = [d for d in P["deadlines"] if d.get("source") in (None, "You (manual)")]
    P["deadlines"] = framework.to_profile_deadlines(fw) + manual
    for c in fw:
        mats = [m for m in P["materials"].get(c["subject"], []) if m["name"] != "Canvas syllabus"]
        if c["syllabus"].strip():
            topics = "Topics: " + ", ".join(c["topics"]) + "\n\n" if c["topics"] else ""
            mats.insert(0, {"name": "Canvas syllabus", "text": topics + c["syllabus"]})
        P["materials"][c["subject"]] = mats
    P["canvas"] = {"connected": date.today().isoformat(),
                   "base": (st.session_state.get("canvas_live") or {}).get("base", "sample")}


def manual_setup():
    P["subjects"] = st.multiselect("Subjects", sorted(set(state.SUBJECT_OPTIONS + P["subjects"])),
                                   default=P["subjects"], accept_new_options=True)
    for subj in P["subjects"]:
        st.markdown(f"**{subj}: class files**")
        files = st.file_uploader(f"Notes, slides, packets or study guides for {subj}",
                                 type=importers.TEXT_TYPES, accept_multiple_files=True,
                                 key=f"files_{subj}", label_visibility="collapsed")
        for f in files or []:
            have = {m["name"] for m in P["materials"].get(subj, [])}
            if f.name not in have:
                P["materials"].setdefault(subj, []).append({"name": f.name, "text": state.extract_text(f)})
        for m in P["materials"].get(subj, []):
            st.caption(f"✅ {m['name']} · {len(m['text'].split())} words")

    st.markdown("**Deadlines**")
    with st.form("add_deadline", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns([2, 1, 2, 1, 1])
        title = c1.text_input("What’s due", placeholder="Unit 4 test")
        subj = c2.selectbox("Subject", P["subjects"] or state.SUBJECT_OPTIONS)
        topic = c3.text_input("Topic", placeholder="Equivalent fractions")
        kind = c4.selectbox("Type", ["exam", "quiz", "assignment"])
        due = c5.date_input("Due", min_value=date.today())
        if st.form_submit_button("Add deadline") and title:
            P["deadlines"].append({"title": title, "subject": subj, "topic": topic or title,
                                   "due": due.isoformat(), "kind": kind, "source": "You (manual)"})
    c1, c2 = st.columns([3, 1])
    ics = c1.file_uploader("Or upload a calendar (.ics)", type=["ics"])
    ics_subj = c2.selectbox("Calendar subject", P["subjects"] or state.SUBJECT_OPTIONS, key="ics_subj")
    if ics is not None and st.button("Import calendar"):
        found = state.parse_ics(ics.getvalue().decode("utf-8", "ignore"), ics_subj)
        for f in found:
            f["source"] = "You (manual)"
        P["deadlines"].extend(found)
        st.success(f"Added {len(found)} upcoming events.")
    for i, dl in enumerate(sorted(P["deadlines"], key=lambda d: d["due"])):
        c1, c2 = st.columns([6, 1])
        c1.markdown(f"<span class='pill gold'>{dl['due']}</span> **{dl['title']}** · {dl['subject']} · {dl['topic']}",
                    unsafe_allow_html=True)
        if c2.button("Remove", key=f"rm_{i}_{dl['title']}"):
            P["deadlines"].remove(dl)
            st.rerun()


# ================================================================ today
def page_today():
    today = date.today()
    st.markdown(f'<p class="eyebrow">{today.strftime("%A, %b %d")}</p>', unsafe_allow_html=True)
    st.title(f"Hey {P['name'] or 'there'}")

    st.markdown("**How’s your energy?**")
    P["energy"] = st.radio("Energy", list(planner.ENERGY_MINUTES), horizontal=True,
                           index=list(planner.ENERGY_MINUTES).index(P["energy"]),
                           label_visibility="collapsed")
    mins = planner.ENERGY_MINUTES[P["energy"]]
    ui.say(f"Got it. Sessions today are {mins} minutes. I’ll change the length, not the goal.")

    st.markdown("**Next 10 days**")
    cells = planner.runway(P["deadlines"], today)
    cols = st.columns(len(cells))
    for col, cell in zip(cols, cells):
        d = date.fromisoformat(cell["day"])
        dots = "".join('<span class="dot"></span> ' for _ in cell["sessions"])
        dots += "".join('<span class="dot due"></span> ' for _ in cell["due"])
        col.markdown(f"<div class='day {'today' if d == today else ''}'>{d.strftime('%a')}<br><b>{d.day}</b><br>{dots or '&nbsp;'}</div>",
                     unsafe_allow_html=True)
    st.caption("● study session   ■ deadline")

    todays = [s for s in planner.build_plan(P["deadlines"], today) if s["day"] == today.isoformat()]
    done_today = {(h["subject"], h["topic"]) for h in P["history"] if h["date"] == today.isoformat()}
    st.subheader("Today")
    if not P["deadlines"]:
        st.info("No deadlines yet. Add some in Set up, or start any lesson from the Lesson page.")
    elif not todays:
        st.write("Nothing scheduled today. Nice. You can still do a quick lesson.")
    for s in todays:
        finished = (s["subject"], s["topic"]) in done_today
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"<span class='eyebrow'>{s['subject']} · {mins} min</span><br>"
                        f"<b style='font-size:1.25rem'>{s['topic']}</b><br>"
                        f"<span style='color:#5C5F7D'>For {s['for']}, due {s['due']}</span>",
                        unsafe_allow_html=True)
            if finished:
                c2.success("Done")
            else:
                c2.button("Start", key=f"start_{s['subject']}_{s['topic']}", type="primary",
                          on_click=start_pending, args=(s["subject"], s["topic"]))

    if P["review_bank"]:
        st.subheader("Review bank")
        st.caption("Ideas that needed a second look. Lumo brings these back into your next lessons.")
        for r in P["review_bank"][-6:]:
            st.markdown(f"<span class='pill'>{r['subject']}</span> {r['concept']}", unsafe_allow_html=True)
    persist()


def start_pending(subject, topic):
    st.session_state.pending = {"subject": subject, "topic": topic}
    st.session_state.pop("lesson", None)
    go("Lesson")


# ================================================================ lesson
def material_for(subject):
    return "\n\n".join(m["text"] for m in P["materials"].get(subject, []))


def begin_lesson(subject, topic):
    interests = P["interests"] or ["everyday life"]
    interest = matcher.pick_interest(P["bandit"], subject, interests)
    weak = [r["concept"] for r in P["review_bank"] if r["subject"] == subject][-3:]
    with st.spinner(f"Lumo is building a {subject} lesson around {interest}…"):
        try:
            lesson = llm.generate_lesson(subject, topic, state.level_label(P["grade"]), interest,
                                         material_for(subject), weak)
        except Exception as e:  # network, key or parse problems
            st.error(f"Couldn’t build that lesson: {e}")
            return
    st.session_state.lesson = {
        "subject": subject, "topic": lesson.get("topic", topic), "interest": interest,
        "data": lesson, "step": 0, "tries": [0] * len(lesson["steps"]),
        "first_try": [None] * len(lesson["steps"]), "solved": False,
        "phase": "steps", "feedback": None, "started": datetime.now().isoformat(),
    }


def page_lesson():
    L = st.session_state.get("lesson")
    pending = st.session_state.pop("pending", None)
    if pending and not L:
        begin_lesson(pending["subject"], pending["topic"])
        L = st.session_state.get("lesson")

    if not L:
        st.markdown('<p class="eyebrow">Lesson</p>', unsafe_allow_html=True)
        st.title("What are we learning?")
        subjects = P["subjects"] or state.SUBJECT_OPTIONS
        subject = st.selectbox("Subject", subjects)
        suggestions = [d["topic"] for d in P["deadlines"] if d["subject"] == subject]
        mat = material_for(subject)
        if mat and st.button("Find topics in my class files"):
            with st.spinner("Reading your files…"):
                st.session_state[f"topics_{subject}"] = llm.suggest_topics(subject, mat)
        suggestions += st.session_state.get(f"topics_{subject}", [])
        suggestions = list(dict.fromkeys(suggestions))
        if suggestions:
            pick = st.radio("From your classes", suggestions + ["Something else"], horizontal=False)
        else:
            pick = "Something else"
        topic = pick if pick != "Something else" else st.text_input(
            "Topic", placeholder="Equivalent fractions" if subject == "Math" else "Paragraph structure")
        if not llm.live():
            st.caption("Demo mode covers equivalent fractions (Math) and paragraph structure (English).")
        if st.button("Start lesson", type="primary", disabled=not topic):
            begin_lesson(subject, topic)
            st.rerun()
        return

    data, steps = L["data"], L["data"]["steps"]
    st.markdown(f'<p class="eyebrow">{L["subject"]} · {len(steps)} steps</p>', unsafe_allow_html=True)
    st.title(L["topic"])
    st.progress((L["step"] + (1 if L["phase"] != "steps" else 0)) / (len(steps) + 1))

    if L["phase"] == "steps":
        i = L["step"]
        s = steps[i]
        if i == 0:
            if data.get("sample"):
                st.info(f"Demo mode: Lumo can’t write a {L['subject']} lesson on “{L['topic']}” without an "
                        "API key, so this is a built-in sample lesson. Add a key in the app’s Secrets for real lessons.")
            ui.say(f"Let’s do this one with <b>{L['interest'].lower()}</b>.")
        st.markdown(f"### {s['title']}")
        st.markdown(f"<div class='card'>{s['explain']}</div>", unsafe_allow_html=True)
        st.markdown(f"**{s['question']}**")
        choice = st.radio("Choose", s["choices"], index=None, key=f"q_{i}_{L['tries'][i]}",
                          label_visibility="collapsed", disabled=L["solved"])
        fb = L["feedback"]
        if not L["solved"]:
            if st.button("Check", type="primary", disabled=choice is None):
                correct = s["choices"].index(choice) == s["answer_index"]
                L["tries"][i] += 1
                if L["first_try"][i] is None:
                    L["first_try"][i] = correct
                if correct:
                    L["solved"], L["feedback"] = True, ("ok", s.get("why", ""))
                elif L["tries"][i] >= 3:
                    L["solved"] = True
                    L["feedback"] = ("show", f"The answer is **{s['choices'][s['answer_index']]}**. {s.get('why', '')}")
                else:
                    L["feedback"] = ("hint", s["hints"][min(L["tries"][i] - 1, len(s["hints"]) - 1)])
                st.rerun()
        if fb:
            kind, text = fb
            if kind == "ok":
                ui.say(f"Yes! {text}")
            elif kind == "hint":
                ui.say(f"Not quite. Here’s a nudge: {text}", mood="think")
            else:
                ui.say(f"That one was tricky. {text} I’ll bring it back later.", mood="think")
        if L["solved"] and st.button("Next", type="primary"):
            L["solved"], L["feedback"] = False, None
            if i + 1 < len(steps):
                L["step"] += 1
            else:
                L["phase"] = "teachback"
            st.rerun()

    elif L["phase"] == "teachback":
        st.markdown("### Teach it back")
        ui.say(data.get("teachback_prompt", "Explain it to me in your own words."))
        answer = st.text_area("Your explanation", height=140, placeholder="Type like you’re explaining to a friend…")
        if st.button("Send to Lumo", type="primary", disabled=not answer.strip()):
            with st.spinner("Lumo is reading…"):
                try:
                    g = llm.grade_teachback(L["topic"], data.get("teachback_prompt", ""),
                                            data.get("key_points", []), answer)
                except Exception as e:
                    st.error(f"Couldn’t check that: {e}")
                    return
            finish_lesson(L, g)
            st.rerun()

    else:
        g = L["grade"]
        st.markdown("### What Lumo noticed")
        ui.say(g.get("reply", "Nice work."))
        for k in g.get("got", []):
            st.markdown(f"✅ {k}")
        for k in g.get("missing", []):
            st.markdown(f"🟡 **Missing:** {k}")
        if g.get("missing"):
            st.caption("Missing pieces go to your review bank for the next session.")
        transfer = L["first_try"][-1]
        st.markdown(f"<div class='card'><span class='eyebrow'>Without the hook</span><br>"
                    f"{'Got the plain question on the first try. The skill transferred.' if transfer else 'The plain question took a few tries. Lumo will keep the hook a bit longer next time.'}</div>",
                    unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if c1.button("Back to Today", type="primary", width="stretch"):
            st.session_state.pop("lesson", None)
            go("Today")
            st.rerun()
        if c2.button("Another lesson", width="stretch"):
            st.session_state.pop("lesson", None)
            st.rerun()


def finish_lesson(L, grade):
    steps = L["data"]["steps"]
    first = [bool(x) for x in L["first_try"]]
    reward = sum(first) / len(first)
    matcher.update(P["bandit"], L["subject"], L["interest"], reward)
    today = date.today().isoformat()
    for s, t in zip(steps, L["tries"]):
        if t >= 3:
            P["review_bank"].append({"concept": f"{L['topic']}: {s['title']}", "subject": L["subject"], "added": today})
    for m in grade.get("missing", []):
        P["review_bank"].append({"concept": f"{L['topic']}: {m}", "subject": L["subject"], "added": today})
    started = datetime.fromisoformat(L["started"])
    P["history"].append({
        "date": today, "subject": L["subject"], "topic": L["topic"], "interest": L["interest"],
        "first_try": first, "tries": L["tries"], "transfer": first[-1],
        "teach_got": len(grade.get("got", [])), "teach_missing": grade.get("missing", []),
        "minutes": max(1, round((datetime.now() - started).seconds / 60)),
    })
    L["grade"], L["phase"] = grade, "done"
    persist()


# ================================================================ parent view
def page_parent():
    st.markdown('<p class="eyebrow">Parent view</p>', unsafe_allow_html=True)
    st.title(f"{P['name'] or 'Your student'}’s semester")
    H = P["history"]
    if not H:
        st.info("Finish a lesson and the dashboard fills in here.")
        return
    today = date.today()
    transfers = [h["transfer"] for h in H]
    planned_so_far = [s for s in planner.build_plan(P["deadlines"],
                      date.fromisoformat(min(h["date"] for h in H))) if s["day"] <= today.isoformat()]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Retention without the hook", f"{round(100 * sum(transfers) / len(transfers))}%",
              help="Share of lessons where the final, hook-free question was right on the first try.")
    c2.metric("Lessons done", len(H))
    c3.metric("Sessions done vs planned", f"{len(H)} / {max(len(planned_so_far), len(H))}")
    c4.metric("Minutes studied", sum(h["minutes"] for h in H))

    st.subheader("Retention without the hook, over time")
    rolling, run = [], []
    for t in transfers:
        run.append(1 if t else 0)
        rolling.append(round(100 * sum(run[-5:]) / len(run[-5:])))
    st.line_chart({"Retention % (last 5 lessons)": rolling}, height=220)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Needs a second look")
        if P["review_bank"]:
            for r in P["review_bank"][-8:][::-1]:
                st.markdown(f"<span class='pill'>{r['subject']}</span> {r['concept']}", unsafe_allow_html=True)
        else:
            st.write("Nothing flagged yet.")
    with c2:
        st.subheader("What works for this kid")
        rows = matcher.table(P["bandit"], P["subjects"], P["interests"])
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch",
                         column_config={"Fit": st.column_config.ProgressColumn("Fit", min_value=0, max_value=100, format="%d%%")})
        st.caption("Lumo learns which interest works best for each subject.")

    st.subheader("Upcoming")
    for dl in sorted(P["deadlines"], key=lambda d: d["due"]):
        if dl["due"] >= today.isoformat():
            n = len(planner.session_days(today, date.fromisoformat(dl["due"])))
            st.markdown(f"<span class='pill gold'>{dl['due']}</span> **{dl['title']}** · {n} short sessions planned before it",
                        unsafe_allow_html=True)

    st.subheader("Recent lessons")
    st.dataframe([{"Date": h["date"], "Subject": h["subject"], "Topic": h["topic"],
                   "Interest": h["interest"], "First-try": f"{sum(h['first_try'])}/{len(h['first_try'])}",
                   "Transfer": "✅" if h["transfer"] else "—"} for h in H[::-1][:10]],
                 hide_index=True, width="stretch")


# ================================================================ router
{"Set up": page_setup, "Today": page_today, "Lesson": page_lesson,
 "Parent view": page_parent}[st.session_state.page]()
