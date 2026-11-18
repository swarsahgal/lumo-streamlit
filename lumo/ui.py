"""Look and feel: the Lumo mascot and a little CSS in the deck's indigo style."""
import streamlit as st

MASCOT = """<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 340 340" role="img" aria-label="Lumo">
<circle cx="170" cy="170" r="150" fill="#8F8CF7"/>
<circle cx="170" cy="170" r="150" fill="none" stroke="#B9B7FB" stroke-width="6" opacity=".6"/>
<ellipse cx="120" cy="100" rx="40" ry="22" fill="#FFFFFF" opacity=".22" transform="rotate(-30 120 100)"/>
<circle cx="128" cy="160" r="30" fill="#FFFFFF"/><circle cx="212" cy="160" r="30" fill="#FFFFFF"/>
<circle cx="{px1}" cy="164" r="15" fill="#1A1B2E"/><circle cx="{px2}" cy="164" r="15" fill="#1A1B2E"/>
<circle cx="{hx1}" cy="158" r="5" fill="#FFFFFF"/><circle cx="{hx2}" cy="158" r="5" fill="#FFFFFF"/>
<ellipse cx="96" cy="212" rx="18" ry="10" fill="#F7A8C8" opacity=".55"/><ellipse cx="244" cy="212" rx="18" ry="10" fill="#F7A8C8" opacity=".55"/>
<path d="{mouth}" stroke="#1A1B2E" stroke-width="10" fill="none" stroke-linecap="round"/>
<circle cx="268" cy="66" r="22" fill="#5AD4B8"/>
</svg>"""

MOUTHS = {"happy": "M130 222 q40 36 80 0", "think": "M140 230 q30 -8 60 0", "wow": "M160 225 q10 -16 20 0 q-10 16 -20 0"}


def mascot(size=64, mood="happy", look="center"):
    dx = {"left": -8, "center": 0, "right": 8}[look]
    return MASCOT.format(s=size, px1=128 + dx, px2=212 + dx, hx1=123 + dx, hx2=207 + dx,
                         mouth=MOUTHS.get(mood, MOUTHS["happy"]))


def say(text: str, mood="happy"):
    """Lumo speech bubble."""
    st.markdown(
        f"""<div class="lumo-say">{mascot(52, mood)}<div class="bubble">{text}</div></div>""",
        unsafe_allow_html=True)


def css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap');
html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea { font-family: 'Nunito', sans-serif !important; }
h1, h2, h3 { font-weight: 900 !important; color: #1A1B2E; }
.lumo-say { display:flex; gap:12px; align-items:flex-start; margin: 6px 0 14px; }
.lumo-say svg { flex: none; }
.lumo-say .bubble { background:#ECEEF6; border-radius: 18px; padding: 12px 16px; font-size: 1.05rem; line-height: 1.45; color:#1A1B2E; }
.card { background:#fff; border:2px solid #DCDEEA; border-bottom-width:6px; border-radius:20px; padding:16px 18px; margin-bottom:12px; }
.eyebrow { font-size:.78rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; color:#5B57D1; }
.pill { display:inline-block; padding:3px 10px; border-radius:999px; background:#E7E6FB; color:#2E2A86; font-weight:700; font-size:.8rem; margin-right:4px; }
.pill.gold { background:#FBEFD9; color:#7A4E0F; }
.day { text-align:center; border-radius:12px; padding:6px 2px; background:#F5F5FB; font-size:.75rem; }
.day.today { outline:2px solid #5B57D1; }
.dot { width:14px; height:14px; border-radius:50%; background:#5B57D1; display:inline-block; margin-top:4px; }
.dot.due { background:#E9B860; border-radius:4px; }
.hook-bar { height:8px; border-radius:8px; background:#E7E6FB; overflow:hidden; margin:4px 0 10px; }
.hook-bar > div { height:100%; background:#5B57D1; }
.stButton button { border-radius: 14px !important; font-weight: 800 !important; border-bottom-width: 4px !important; }
</style>""", unsafe_allow_html=True)
