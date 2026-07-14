"""
utils/styles.py
------------------
NOVA's CSS theme, injected once via inject_styles(). Was a bare
st.markdown(..., unsafe_allow_html=True) call at module scope in the
original single-file app; wrapped in a function here so nova_app.py controls
exactly when it runs (right after st.set_page_config, same as before).
"""

import streamlit as st


def inject_styles():
    st.markdown(
        """
<style>
:root {
  --nova-bg: #080b16;
  --nova-card: #111828;
  --nova-card-2: #0d1322;
  --nova-border: rgba(255,255,255,0.08);
  --nova-text: #e6e9f2;
  --nova-muted: #8b93a7;
  --nova-accent: #7c5cff;
  --nova-accent-2: #22d3ee;
}

/* page background: subtle cosmic gradient */
.stApp {
  background:
    radial-gradient(1200px 600px at 12% -10%, rgba(124,92,255,0.18), transparent 55%),
    radial-gradient(1000px 500px at 100% 0%, rgba(34,211,238,0.12), transparent 50%),
    var(--nova-bg);
}
.block-container { padding-top: 2.2rem; max-width: 1180px; }

/* hide default chrome */
#MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }

/* ---- NOVA brand header ---- */
.nova-brand { display:flex; align-items:center; gap:14px; margin-bottom: 2px; }
.nova-mark {
  font-size: 2.1rem; font-weight: 800; letter-spacing: .06em;
  background: linear-gradient(120deg, #b8a7ff, #7c5cff 45%, #22d3ee);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.nova-star { font-size: 1.7rem; filter: drop-shadow(0 0 8px rgba(124,92,255,.7)); }
.nova-sub { color: var(--nova-muted); font-size: .82rem; letter-spacing:.14em; text-transform: uppercase; }
.sonic-chip {
  margin-left:auto; display:flex; align-items:center; gap:8px;
  background: rgba(124,92,255,0.1); border:1px solid rgba(124,92,255,0.35);
  color:#cdbcff; padding:6px 14px; border-radius:999px; font-size:.78rem; font-weight:600;
}
.sonic-dot { width:8px; height:8px; border-radius:50%; background:#22d3ee; box-shadow:0 0 8px #22d3ee; }

/* ---- SONIC speech bubble ---- */
.sonic-row { display:flex; gap:14px; align-items:flex-start; margin: 20px 0 8px; }
.sonic-avatar {
  flex:0 0 48px; width:48px; height:48px; border-radius:14px; overflow:hidden;
  box-shadow: 0 0 22px rgba(124,92,255,.45);
}
.sonic-avatar img { width:100%; height:100%; object-fit:cover; display:block; }
.sonic-bubble {
  background: var(--nova-card); border:1px solid var(--nova-border);
  border-radius: 4px 16px 16px 16px; padding: 14px 18px; color: var(--nova-text);
  font-size: 1.02rem; line-height:1.5; max-width: 760px;
}
.sonic-name { color:#9d8cff; font-weight:700; font-size:.72rem; letter-spacing:.1em; text-transform:uppercase; margin-bottom:4px; }

/* ---- cluster section header ---- */
.cluster-head { display:flex; align-items:center; gap:12px; margin: 26px 0 6px; }
.cluster-bar { width:5px; height:30px; border-radius:3px; }
.cluster-title { font-size:1.22rem; font-weight:700; color:#f2f4fb; }
.cluster-why { color:var(--nova-muted); font-size:.88rem; line-height:1.5; margin: 0 0 6px 17px; max-width: 900px; }

/* ---- paper card (native bordered containers) ---- */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: linear-gradient(180deg, var(--nova-card), var(--nova-card-2));
  border: 1px solid var(--nova-border) !important; border-radius: 16px !important;
  transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
  transform: translateY(-3px); border-color: rgba(124,92,255,0.5) !important;
  box-shadow: 0 12px 30px rgba(0,0,0,0.4);
}
.paper-title { font-size: 1.02rem; font-weight: 700; color:#f2f4fb; line-height:1.35; margin-bottom:6px; }
.paper-meta { color: var(--nova-muted); font-size: .82rem; margin-bottom: 10px; }
.src-badge { display:inline-block; padding:2px 9px; border-radius:999px; font-size:.68rem; font-weight:700;
  margin-right:6px; border:1px solid transparent; }

/* ---- buttons ---- */
.stButton > button, .stLinkButton > a {
  border-radius: 10px !important; font-weight: 600 !important; font-size: .84rem !important;
  border: 1px solid var(--nova-border) !important; background: rgba(255,255,255,0.04) !important;
  color: #dfe3ee !important; transition: all .14s ease;
}
.stButton > button:hover, .stLinkButton > a:hover {
  border-color: rgba(124,92,255,0.6) !important; background: rgba(124,92,255,0.12) !important; color:#fff !important;
}
/* primary buttons (Chat it out, main CTAs) */
.stButton > button[kind="primary"] {
  background: linear-gradient(120deg, #7c5cff, #22d3ee) !important; border: none !important;
  color: #0a0e1a !important; font-weight: 800 !important; box-shadow: 0 6px 18px rgba(124,92,255,.4) !important;
}
.stButton > button[kind="primary"]:hover { filter: brightness(1.08); color:#0a0e1a !important; }

/* text inputs / textareas */
.stTextArea textarea, .stTextInput input {
  background: rgba(8,11,22,0.7) !important; border:1px solid var(--nova-border) !important;
  color: var(--nova-text) !important; border-radius: 12px !important;
}
.stChatInput textarea { background: var(--nova-card) !important; }

/* review field labels */
.field-label { font-weight:700; color:#cbd0e0; margin: 8px 0 2px; font-size:.9rem; }

/* ---- welcome hero (SONIC on the left, big) ---- */
.hero-figure { display:flex; flex-direction:column; align-items:center; justify-content:center; }
.hero-figure img { height:52vh; max-height:540px; width:auto; filter: drop-shadow(0 20px 40px rgba(124,92,231,.35)); }
.hero-name { margin-top:14px; font-weight:800; letter-spacing:.12em; color:#c9c3ff; font-size:.9rem; }
.hero-speech {
  background: var(--nova-card); border:1px solid var(--nova-border);
  border-radius: 18px 18px 18px 4px; padding: 20px 22px; color: var(--nova-text);
  font-size: 1.18rem; line-height:1.55; position:relative; margin-bottom: 18px;
}
.hero-speech .sonic-name { color:#9d8cff; font-weight:700; font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; margin-bottom:8px; }
.hero-answer-label { color:var(--nova-muted); font-size:.82rem; text-transform:uppercase; letter-spacing:.1em; margin: 6px 0 8px; }

/* ---- live search checklist ---- */
.search-wrap { max-width: 620px; margin: 6px auto 0; }
.step-row { display:flex; align-items:center; gap:14px; padding:11px 4px; font-size:1rem; color:var(--nova-muted); border-bottom:1px solid rgba(255,255,255,.05); }
.step-ic { width:26px; height:26px; border-radius:50%; flex:0 0 26px; display:flex; align-items:center; justify-content:center; font-size:.8rem; border:2px solid rgba(255,255,255,.14); }
.step-row.done { color:#dfe3ee; }
.step-row.done .step-ic { background:linear-gradient(120deg,#7c5cff,#22d3ee); border-color:transparent; color:#0a0e1a; font-weight:800; }
.step-row.active { color:#fff; }
.step-row.active .step-ic { border-color:#7c5cff; border-top-color:transparent; animation: spin .8s linear infinite; }
.step-count { margin-left:auto; font-size:.8rem; color:var(--nova-muted); }
@keyframes spin { to { transform: rotate(360deg); } }

/* ---- vectorize loading (progress + SONIC quote) ---- */
.vec-wrap { max-width: 640px; margin: 10px auto; text-align:center; }
.vec-figure img { height:150px; width:auto; filter: drop-shadow(0 10px 26px rgba(124,92,231,.4)); }
.vec-quote { color:#cbd0e6; font-size:1.12rem; line-height:1.55; font-style:italic; margin:18px auto 6px; max-width:520px; min-height:3em; }
.vec-quote .q { color:#9d8cff; font-weight:700; }
.vec-phase { color:var(--nova-muted); font-size:.85rem; margin-top:10px; }

/* ---- chat bubbles (custom, with SONIC caricature) ---- */
.chat-row { display:flex; gap:14px; align-items:flex-start; margin:14px 0; }
.chat-row.user { flex-direction: row-reverse; }
.chat-av { flex:0 0 42px; width:42px; height:42px; border-radius:12px; overflow:hidden; box-shadow:0 0 14px rgba(124,92,255,.35); }
.chat-av svg { width:100%; height:100%; display:block; }
.chat-av.user { display:flex; align-items:center; justify-content:center; font-size:1.4rem; background:linear-gradient(135deg,#1c2540,#0f1526); box-shadow:none; border:1px solid var(--nova-border); }
.chat-bub { background:var(--nova-card); border:1px solid var(--nova-border); border-radius:4px 16px 16px 16px; padding:12px 16px; color:var(--nova-text); line-height:1.55; max-width:760px; }
.chat-row.user .chat-bub { border-radius:16px 4px 16px 16px; background:rgba(124,92,231,.12); border-color:rgba(124,92,231,.3); }

/* per-source status chips */
.src-stat-row { display:flex; flex-wrap:wrap; gap:8px; margin: 2px 0 18px; }
.src-stat { font-size:.74rem; font-weight:600; padding:4px 11px; border-radius:999px; border:1px solid transparent; }
.src-stat.ok    { color:#5eead4; background:rgba(45,212,191,.10); border-color:rgba(45,212,191,.35); }
.src-stat.warn  { color:#fbbf24; background:rgba(251,191,36,.12); border-color:rgba(251,191,36,.45); }
.src-stat.err   { color:#f87171; background:rgba(248,113,113,.12); border-color:rgba(248,113,113,.45); }
.src-stat.muted { color:#8b93a7; background:rgba(255,255,255,.04); border-color:var(--nova-border); }
</style>
""",
        unsafe_allow_html=True,
    )
