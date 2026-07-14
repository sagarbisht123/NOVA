"""
NOVA — Research, guided by SONIC
================================================================
A single Streamlit app that stitches together the two projects, unchanged:

  • agent/          the research pipeline (structured_agent's `app/` package):
                    INTENT graph  -> SEARCH + CLUSTER graph
  • chatbot_core/   the single-PDF Q&A chatbot (Qa.py + vectorizeer.py)

NOVA is the product. SONIC is the assistant persona that talks you through it.

Flow:
  USER RESEARCH IDEA
     -> INTENT agent frames it (Problem / Objective / Additional Context)
     -> you review/edit it
     -> SEARCH agent fetches + reranks + clusters papers
     -> results shown as clean thumbnails (title, authors, links)
     -> "Chat it out" on any paper: its PDF is downloaded, vectorized by
        vectorizeer.build_vectorstore, and you Q&A over it with Qa.py's chain.

This file is UI + wiring only. It does NOT change any agent or chatbot logic —
it imports their functions and drives them.

Run:
    streamlit run nova_app.py        # from inside the NOVA/ folder
"""

import base64
import hashlib
import os
import random
import re
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# 0. PATHS  — make both sub-projects importable without touching their code
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent
os.chdir(BASE)                                   # ./vectorstores, ./downloads resolve under NOVA/
sys.path.insert(0, str(BASE))                    # `import app...`  (the agent package)
sys.path.insert(0, str(BASE / "chatbot_core"))   # `import Qa`, `from vectorizeer import ...`

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

import requests
import streamlit as st

DOWNLOADS_DIR = BASE / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
VECTORSTORES_DIR = BASE / "vectorstores"

PDF_UA = {"User-Agent": "Mozilla/5.0 (compatible; NOVA-research/1.0)"}

# Decorative, index-based — purely visual.
CLUSTER_ACCENTS = ["#7c5cff", "#22d3ee", "#f59e0b", "#ec4899", "#34d399", "#60a5fa", "#a78bfa", "#f472b6"]
SOURCE_COLORS = {"arXiv": "#e05263", "SemanticScholar": "#4c8bf5", "OpenAlex": "#2fa572"}

# ---------------------------------------------------------------------------
# SONIC — the assistant caricature, drawn as an inline SVG (no external file,
# renders under Streamlit's strict CSP). A friendly bespectacled researcher:
# brown quiff, black glasses, big smile, white shirt + navy striped tie,
# suspenders. Used big on the welcome screen and small as the chat avatar.
# ---------------------------------------------------------------------------
SONIC_SVG = """
<svg viewBox="0 0 240 280" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="SONIC the research assistant">
  <defs>
    <linearGradient id="s-card" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2b2168"/><stop offset="1" stop-color="#141a2e"/>
    </linearGradient>
    <linearGradient id="s-skin" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f8d0a8"/><stop offset="1" stop-color="#e7ad7f"/>
    </linearGradient>
    <linearGradient id="s-hair" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#7d5636"/><stop offset="1" stop-color="#4e3421"/>
    </linearGradient>
    <linearGradient id="s-tie" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3a4f8a"/><stop offset="1" stop-color="#26325c"/>
    </linearGradient>
    <clipPath id="s-clip"><rect x="8" y="8" width="224" height="264" rx="34"/></clipPath>
    <clipPath id="s-tieclip"><path d="M115 232 L125 232 L131 279 L120 289 L109 279 Z"/></clipPath>
  </defs>
  <rect x="8" y="8" width="224" height="264" rx="34" fill="url(#s-card)"/>
  <g clip-path="url(#s-clip)">
    <!-- shirt -->
    <path d="M18 280 C22 226 64 202 120 202 C176 202 218 226 222 280 Z" fill="#eef2f8"/>
    <!-- suspenders -->
    <path d="M80 205 L96 205 L112 280 L96 280 Z" fill="#b45540"/>
    <path d="M160 205 L144 205 L128 280 L144 280 Z" fill="#b45540"/>
    <!-- collar -->
    <path d="M104 200 L120 217 L98 226 Z" fill="#ffffff"/>
    <path d="M136 200 L120 217 L142 226 Z" fill="#ffffff"/>
    <!-- tie -->
    <path d="M120 214 L110 223 L120 234 L130 223 Z" fill="url(#s-tie)"/>
    <path d="M115 232 L125 232 L131 279 L120 289 L109 279 Z" fill="url(#s-tie)"/>
    <g clip-path="url(#s-tieclip)" stroke="#5a70b4" stroke-width="4" opacity="0.8">
      <line x1="104" y1="250" x2="136" y2="218"/>
      <line x1="104" y1="264" x2="140" y2="228"/>
      <line x1="108" y1="280" x2="140" y2="248"/>
    </g>
    <!-- neck -->
    <rect x="105" y="156" width="30" height="48" rx="14" fill="#e6ad7f"/>
    <!-- ears -->
    <circle cx="66" cy="118" r="11" fill="url(#s-skin)"/>
    <circle cx="174" cy="118" r="11" fill="url(#s-skin)"/>
    <!-- head -->
    <ellipse cx="120" cy="112" rx="56" ry="62" fill="url(#s-skin)"/>
    <!-- cheeks -->
    <ellipse cx="84" cy="140" rx="10" ry="6" fill="#ef9f8f" opacity="0.35"/>
    <ellipse cx="156" cy="140" rx="10" ry="6" fill="#ef9f8f" opacity="0.35"/>
    <!-- hair -->
    <path d="M66 110 C62 54 92 38 120 38 C150 38 178 54 173 110
             C167 92 155 84 140 82 C151 74 154 62 154 62
             C141 76 129 79 120 79 C110 79 101 74 94 64
             C96 74 99 82 99 82 C85 84 73 92 66 110 Z" fill="url(#s-hair)"/>
    <!-- eyebrows -->
    <path d="M83 97 Q97 90 110 97" stroke="#5c3f28" stroke-width="4" fill="none" stroke-linecap="round"/>
    <path d="M130 97 Q143 90 157 97" stroke="#5c3f28" stroke-width="4" fill="none" stroke-linecap="round"/>
    <!-- eyes -->
    <ellipse cx="101" cy="117" rx="9" ry="10" fill="#ffffff"/>
    <ellipse cx="139" cy="117" rx="9" ry="10" fill="#ffffff"/>
    <circle cx="103" cy="118" r="5" fill="#2a2438"/>
    <circle cx="137" cy="118" r="5" fill="#2a2438"/>
    <circle cx="105" cy="116" r="1.6" fill="#ffffff"/>
    <circle cx="139" cy="116" r="1.6" fill="#ffffff"/>
    <!-- nose -->
    <path d="M115 145 Q120 149 125 145" stroke="#d99b6f" stroke-width="3" fill="none" stroke-linecap="round"/>
    <!-- smile -->
    <path d="M97 156 Q120 186 143 156 Q120 172 97 156 Z" fill="#6d3630"/>
    <path d="M101 157 Q120 170 139 157 Q120 165 101 157 Z" fill="#ffffff"/>
    <!-- glasses -->
    <g fill="none" stroke="#171b28" stroke-width="5">
      <rect x="82" y="101" width="38" height="32" rx="13" fill="rgba(255,255,255,0.10)"/>
      <rect x="120" y="101" width="38" height="32" rx="13" fill="rgba(255,255,255,0.10)"/>
      <line x1="118" y1="115" x2="122" y2="115"/>
      <line x1="82" y1="110" x2="67" y2="113"/>
      <line x1="158" y1="110" x2="173" y2="113"/>
    </g>
  </g>
</svg>
"""

SONIC_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(SONIC_SVG.encode("utf-8")).decode("ascii")

# SONIC's motivational one-liners, shown while a paper is being vectorized.
SONIC_QUOTES = [
    "Great research isn't found — it's framed. You already did the hard part.",
    "Every paper you read is a shortcut someone left for you. Let's decode this one.",
    "Reading fast is fine. Understanding deeply is the flex. Hang tight — I'm doing the deep part.",
    "The best researchers ask better questions, not more of them. Get yours ready.",
    "Curiosity is a muscle. You're clearly training it. Almost there…",
    "One good paper can change the whole direction. Could be this one.",
    "I'm turning every page into something you can just… ask. Two seconds.",
    "Knowledge compounds. This is you, quietly getting sharper.",
]


# ---------------------------------------------------------------------------
# 1. PAGE CONFIG + THEME  (must be the first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(page_title="NOVA · Research Assistant", page_icon="✦", layout="wide")

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


# ---------------------------------------------------------------------------
# 2. HEAVY MODEL / GRAPH LOADING  (cached once per process)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def load_agents():
    """Import the compiled LangGraph agents. Importing the search graph also
    loads the SPECTER reranker model at module import time (by design)."""
    from app.modules.intent.graph import graph as intent_graph
    from app.modules.search.graph import graph as search_graph
    return intent_graph, search_graph


@st.cache_resource(show_spinner=False)
def warm_chatbot_models():
    """Pre-load the chatbot's embedding + cross-encoder models at startup so the
    first 'Chat it out' click doesn't pay the model-load cost. We instantiate the
    exact models the chatbot uses (BAAI/bge-base-en-v1.5 + BAAI/bge-reranker-base),
    warming the weights into the HF/torch cache."""
    from vectorizeer import get_embeddings
    from langchain_community.cross_encoders import HuggingFaceCrossEncoder
    embeddings = get_embeddings()
    reranker = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-base")
    return embeddings, reranker


def boot():
    """Run the one-time heavy loads behind a single friendly splash."""
    if st.session_state.get("_booted"):
        return
    with st.spinner("✦ Waking up SONIC — loading the research + reading models…"):
        load_agents()
        warm_chatbot_models()
    st.session_state["_booted"] = True


# ---------------------------------------------------------------------------
# 3. INTENT TEXT <-> 3-FIELD FORM
# ---------------------------------------------------------------------------
# The backend hands us ONE string with three headed sections. We split it into
# three editable fields and MUST rebuild the exact same
# "Problem: / Objective: / Additional Context:" shape before sending it into the
# search graph — its prompts assume that literal structure.
_SECTION_PATTERN = re.compile(
    r"Problem:\s*(.*?)\n\s*Objective:\s*(.*?)\n\s*Additional Context:\s*(.*)",
    re.S,
)


def split_intent_sections(text: str):
    m = _SECTION_PATTERN.search(text or "")
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    return (text or "").strip(), "", ""


def join_intent_sections(problem: str, objective: str, additional_context: str) -> str:
    ac = additional_context.strip() or "None specified."
    return (
        f"Problem:\n{problem.strip()}\n\n"
        f"Objective:\n{objective.strip()}\n\n"
        f"Additional Context:\n{ac}"
    )


# ---------------------------------------------------------------------------
# 4. SMALL HELPERS
# ---------------------------------------------------------------------------
def first_available(d):
    """First non-empty value in a {source: value} dict (record fields are
    dict-keyed by source after aggregation)."""
    if not isinstance(d, dict):
        return d or None
    for v in d.values():
        if v:
            return v
    return None


def author_line(authors, year):
    authors = authors or []
    if authors:
        shown = ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else "")
    else:
        shown = "Unknown authors"
    return f"{shown}  ·  {year or 'n.d.'}"


_PDF_MAGIC = b"%PDF"


def _download_if_pdf(url: str) -> "str | None":
    """Download url, but only keep it if the bytes are a real PDF (starts with
    %PDF) — a best-effort link that's actually an HTML landing page returns None
    so we can fall back to deep resolution. Cached by URL hash."""
    if not url:
        return None
    key = hashlib.md5(url.encode("utf-8")).hexdigest()[:16]
    dest = DOWNLOADS_DIR / f"{key}.pdf"
    if dest.is_file() and dest.stat().st_size > 0:
        return str(dest)
    try:
        resp = requests.get(url, headers=PDF_UA, timeout=45, stream=True, allow_redirects=True)
        if resp.status_code != 200:
            return None
        it = resp.iter_content(chunk_size=32768)
        first = next(it, b"")
        if not first.startswith(_PDF_MAGIC):
            return None  # HTML landing page or something else, not a PDF
        with open(dest, "wb") as f:
            f.write(first)
            for chunk in it:
                if chunk:
                    f.write(chunk)
        return str(dest) if dest.stat().st_size > 0 else None
    except requests.RequestException:
        return None


def resolve_and_download_pdf(record: dict) -> "str | None":
    """Robustly obtain a readable PDF for a paper at 'Chat it out' time (the
    HYBRID deep step). Search only stored a cheap best-effort link; here we:
       1) try each best-effort pdf link directly (keep it only if it's a real PDF);
       2) if those are landing pages / dead, scrape the citation_pdf_url meta tag
          off them and off the paper's source page(s), then download + verify.
    Returns a local path, or None if nothing yields real PDF bytes."""
    from app.modules.search.providers.semantic_scholar import _extract_citation_pdf_url

    pdf_candidates = [v for v in (record.get("pdf_url") or {}).values() if v]
    page_candidates = [v for v in (record.get("url") or {}).values() if v]

    for cand in pdf_candidates:                       # 1) direct best-effort PDFs
        path = _download_if_pdf(cand)
        if path:
            return path
    for page in pdf_candidates + page_candidates:     # 2) deep: scrape landing pages
        scraped = _extract_citation_pdf_url(page)
        if scraped:
            path = _download_if_pdf(scraped)
            if path:
                return path
    return None


def sonic_says(message: str):
    st.markdown(
        f"""
<div class="sonic-row">
  <div class="sonic-avatar"><img src="{SONIC_DATA_URI}" alt="SONIC"/></div>
  <div class="sonic-bubble"><div class="sonic-name">SONIC</div>{message}</div>
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 5. SESSION STATE
# ---------------------------------------------------------------------------
DEFAULTS = {
    "stage": "welcome",          # welcome | refining | review | searching | results
    "run_id": "",
    "user_query": "",
    "problem": "",
    "objective": "",
    "context": "",
    "clusters": [],
    "papers_by_key": {},         # normalized_title -> full record (flattened, for chat lookup)
    "active_chat": None,         # normalized_title of the paper being chatted, or None
    "chats": {},                 # normalized_title -> {retriever, chain, messages, title}
    "source_status": {},         # {"Semantic Scholar": {"state": "rate_limited", ...}, ...}
    "error": "",
    "_intent_done_for": "",      # run-once guards (keyed by run_id)
    "_search_done_for": "",
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


def wipe_disk_cache():
    """Delete every cached vectorstore and downloaded PDF so a new search starts
    from a clean slate — no old paper's chunks or PDFs can leak in."""
    for folder in (VECTORSTORES_DIR, DOWNLOADS_DIR):
        try:
            if folder.exists():
                shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(exist_ok=True)
        except Exception:
            pass


def reset_all(wipe_cache: bool = True):
    """Full memory refresh: clear this session's results + open chats, and
    (by default) wipe the on-disk vectorstore/PDF caches too."""
    for k, v in DEFAULTS.items():
        st.session_state[k] = v if not isinstance(v, (list, dict)) else type(v)()
    st.session_state["stage"] = "welcome"
    if wipe_cache:
        wipe_disk_cache()


# ---------------------------------------------------------------------------
# 6. HEADER
# ---------------------------------------------------------------------------
st.markdown(
    """
<div class="nova-brand">
  <span class="nova-star">✦</span>
  <span class="nova-mark">NOVA</span>
  <span class="nova-sub">Research&nbsp;Assistant</span>
  <span class="sonic-chip"><span class="sonic-dot"></span> SONIC online</span>
</div>
""",
    unsafe_allow_html=True,
)

boot()


# ---------------------------------------------------------------------------
# 7. STAGE: WELCOME
# ---------------------------------------------------------------------------
def render_welcome():
    left, right = st.columns([0.9, 1.1], gap="large")

    # LEFT — SONIC, big, "asking"
    with left:
        st.markdown(
            f'<div class="hero-figure"><img src="{SONIC_DATA_URI}" alt="SONIC"/>'
            f'<div class="hero-name">SONIC · your research buddy</div></div>',
            unsafe_allow_html=True,
        )

    # RIGHT — the speech + your answer
    with right:
        st.markdown(
            """
<div class="hero-speech">
  <div class="sonic-name">SONIC</div>
  hey, wass up 👋<br>what's on your mind about research today?<br>
  Dump the raw idea on me — the messier the better. I'll shape it into something sharp.
</div>
<div class="hero-answer-label">✍️ your answer</div>
""",
            unsafe_allow_html=True,
        )
        query = st.text_area(
            "your research idea",
            value=st.session_state.get("user_query", ""),
            height=160,
            placeholder="e.g. I want to compare fuel efficiency of human-driven vs RL-controlled cars in "
                        "car-following… comparing is hard because velocity, acceleration, headway all change at once…",
            label_visibility="collapsed",
        )
        go = st.button("Let's go  ✦", type="primary", use_container_width=True)
        if go:
            if not query.strip():
                st.toast("Give me something to work with first 🙂")
            else:
                st.session_state.user_query = query.strip()
                st.session_state.run_id = str(uuid.uuid4())
                st.session_state.stage = "refining"
                st.rerun()


# ---------------------------------------------------------------------------
# 8. STAGE: REFINING  (runs the INTENT graph up to the human-review interrupt)
# ---------------------------------------------------------------------------
def render_refining():
    sonic_says("that seems great — lemme juss refine it ✨")
    run_id = st.session_state.run_id
    # Guard: run the intent graph exactly once per query, even if the host
    # re-executes this stage's script body more than once before it transitions.
    if st.session_state.get("_intent_done_for") == run_id:
        return
    intent_graph, _ = load_agents()
    config = {"configurable": {"thread_id": run_id}}
    try:
        with st.spinner("Framing the problem, objective & context… grounding it with a quick web search…"):
            result = intent_graph.invoke(
                {"user_query": st.session_state.user_query, "run_id": run_id},
                config=config,
            )
        interrupt_payload = result["__interrupt__"][0].value
        problem, objective, context = split_intent_sections(interrupt_payload["polished_research_intent"])
        st.session_state.problem = problem
        st.session_state.objective = objective
        st.session_state.context = context
        st.session_state["_intent_done_for"] = run_id
        st.session_state.stage = "review"
    except Exception as e:
        st.session_state.error = f"{type(e).__name__}: {e}"
        st.session_state.stage = "welcome"
    st.rerun()


# ---------------------------------------------------------------------------
# 9. STAGE: REVIEW  (edit the framed intent, then launch the search)
# ---------------------------------------------------------------------------
def render_review():
    sonic_says("here's how I framed it. Tweak anything that's off, then I'll go hunting 🔍")

    st.markdown('<div class="field-label">🧩 Problem</div>', unsafe_allow_html=True)
    problem = st.text_area("problem", value=st.session_state.problem, height=140, label_visibility="collapsed")
    st.markdown('<div class="field-label">🎯 Objective</div>', unsafe_allow_html=True)
    objective = st.text_area("objective", value=st.session_state.objective, height=110, label_visibility="collapsed")
    st.markdown('<div class="field-label">🗂️ Additional Context</div>', unsafe_allow_html=True)
    context = st.text_area("context", value=st.session_state.context, height=110, label_visibility="collapsed")

    c1, c2, _ = st.columns([1.4, 1, 4])
    with c1:
        find = st.button("Find the papers  🔍", type="primary", use_container_width=True)
    with c2:
        over = st.button("Start over", use_container_width=True)

    if over:
        reset_all()
        st.rerun()
    if find:
        if not problem.strip() or not objective.strip():
            st.toast("Problem and Objective can't be empty.")
        else:
            st.session_state.problem = problem
            st.session_state.objective = objective
            st.session_state.context = context
            st.session_state.stage = "searching"
            st.rerun()


# ---------------------------------------------------------------------------
# 10. STAGE: SEARCHING  (resume intent graph -> STREAM the SEARCH+CLUSTER graph
#     so the UI ticks each step off live instead of hanging on one spinner)
# ---------------------------------------------------------------------------
_SEARCH_STEPS = [
    ("arxiv", "Searching arXiv"),
    ("semantic_scholar", "Searching Semantic Scholar"),
    ("open_alex", "Searching OpenAlex"),
    ("aggregation", "Merging &amp; deduplicating"),
    ("reranker", "Re-ranking by relevance (SPECTER)"),
    ("clustering", "Clustering by approach"),
]


def _search_steps_html(completed: set, counts: dict) -> str:
    sources_done = all(s in completed for s in ("arxiv", "semantic_scholar", "open_alex"))

    def state_of(key):
        if key in completed:
            return "done"
        if key in ("arxiv", "semantic_scholar", "open_alex"):
            return "active"
        if key == "aggregation":
            return "active" if sources_done else "pending"
        if key == "reranker":
            return "active" if "aggregation" in completed else "pending"
        if key == "clustering":
            return "active" if "reranker" in completed else "pending"
        return "pending"

    rows = []
    for key, label in _SEARCH_STEPS:
        s = state_of(key)
        ic = "✓" if s == "done" else ("•" if s == "pending" else "")
        cnt = f'<span class="step-count">{counts[key]} papers</span>' if key in counts else ""
        rows.append(f'<div class="step-row {s}"><div class="step-ic">{ic}</div><div>{label}</div>{cnt}</div>')
    return '<div class="search-wrap">' + "".join(rows) + "</div>"


def render_searching():
    from langgraph.types import Command

    sonic_says("on it — scouring arXiv, Semantic Scholar &amp; OpenAlex, then reranking and clustering "
               "by approach 🔎")

    run_id = st.session_state.run_id
    # Guard: run the resume + search graph exactly once per query.
    if st.session_state.get("_search_done_for") == run_id:
        return
    intent_graph, search_graph = load_agents()
    config = {"configurable": {"thread_id": run_id}}
    edited_intent = join_intent_sections(
        st.session_state.problem, st.session_state.objective, st.session_state.context
    )

    board = st.empty()
    board.markdown(_search_steps_html(set(), {}), unsafe_allow_html=True)
    try:
        with st.spinner("Finalizing your research intent…"):
            resume_result = intent_graph.invoke(Command(resume=edited_intent), config=config)
        human_verified_intent = resume_result["human_verified_intent"]

        # Stream the search graph: each node's completion ticks a step off live.
        completed, counts, final_state = set(), {}, {}
        source_field = {"arxiv": "arXiv_paper", "semantic_scholar": "Semantic_Scholar_paper",
                        "open_alex": "Open_Alex_paper"}
        for update in search_graph.stream(
            {"ResearchIntent": human_verified_intent, "run_id": run_id}, stream_mode="updates"
        ):
            for node_name, delta in update.items():
                completed.add(node_name)
                if isinstance(delta, dict):
                    final_state.update(delta)
                    if node_name in source_field:
                        counts[node_name] = len(delta.get(source_field[node_name]) or [])
            board.markdown(_search_steps_html(completed, counts), unsafe_allow_html=True)

        clusters = final_state.get("clustered_papers") or []

        # flatten every paper into a lookup keyed by its normalized_title (the
        # cluster dict key) so "Chat it out" can find the record anywhere.
        papers_by_key = {}
        for cluster in clusters:
            for norm_title, record in (cluster.get("papers") or {}).items():
                papers_by_key[norm_title] = record

        st.session_state.clusters = clusters
        st.session_state.papers_by_key = papers_by_key
        st.session_state.source_status = {
            "arXiv": final_state.get("arxiv_status") or {},
            "Semantic Scholar": final_state.get("semantic_scholar_status") or {},
            "OpenAlex": final_state.get("open_alex_status") or {},
        }
        st.session_state["_search_done_for"] = run_id
        st.session_state.stage = "results"
    except Exception as e:
        st.session_state.error = f"{type(e).__name__}: {e}"
        st.session_state.stage = "review"
    st.rerun()


# ---------------------------------------------------------------------------
# 11. STAGE: RESULTS  (clean thumbnails, grouped by approach cluster)
# ---------------------------------------------------------------------------
def render_paper_card(norm_title: str, record: dict):
    title = record.get("title") or norm_title.title()
    page_url = first_available(record.get("url"))
    pdf_url = first_available(record.get("pdf_url"))
    sources = record.get("source") or []

    with st.container(border=True):
        st.markdown(f'<div class="paper-title">{title}</div>', unsafe_allow_html=True)

        badges = "".join(
            f'<span class="src-badge" style="color:{SOURCE_COLORS.get(s, "#8b93a7")};'
            f'border-color:{SOURCE_COLORS.get(s, "#8b93a7")}55;background:{SOURCE_COLORS.get(s, "#8b93a7")}18;">{s}</span>'
            for s in sources
        )
        st.markdown(
            f'<div class="paper-meta">{author_line(record.get("authors"), record.get("year"))}<br>{badges}</div>',
            unsafe_allow_html=True,
        )

        b1, b2, b3 = st.columns(3)
        with b1:
            if page_url:
                st.link_button("📄 Paper", page_url, use_container_width=True)
            else:
                st.button("📄 Paper", disabled=True, use_container_width=True, key=f"np_{norm_title}")
        with b2:
            if pdf_url:
                st.link_button("⬇ PDF", pdf_url, use_container_width=True)
            else:
                st.button("⬇ PDF", disabled=True, use_container_width=True, key=f"npdf_{norm_title}")
        with b3:
            # Enabled whenever there's any link to try — the real PDF is
            # resolved/verified on click (HYBRID deep step).
            if pdf_url or page_url:
                if st.button("💬 Chat it out", type="primary", use_container_width=True, key=f"chat_{norm_title}"):
                    st.session_state.active_chat = norm_title
                    st.rerun()
            else:
                st.button("💬 Chat it out", disabled=True, use_container_width=True, key=f"nochat_{norm_title}",
                          help="No source link to fetch a PDF from.")


def render_source_status():
    """Show per-source status so a rate-limited/failed source is never invisible."""
    status = st.session_state.get("source_status") or {}
    if not status:
        return
    chips = []
    for name, s in status.items():
        state = (s or {}).get("state")
        if state == "ok":
            chips.append(f'<span class="src-stat ok">{name} ✓ {s.get("count", 0)}</span>')
        elif state == "rate_limited":
            chips.append(f'<span class="src-stat warn">{name} ⚠ rate-limited (HTTP {s.get("http", 429)})</span>')
        elif state == "error":
            detail = s.get("detail") or f'HTTP {s.get("http", "?")}'
            chips.append(f'<span class="src-stat err">{name} ✕ {detail}</span>')
        else:
            chips.append(f'<span class="src-stat muted">{name} —</span>')
    st.markdown('<div class="src-stat-row">' + "".join(chips) + "</div>", unsafe_allow_html=True)


def render_results():
    clusters = st.session_state.clusters
    total = sum(len(c.get("papers") or {}) for c in clusters)

    if not clusters or total == 0:
        sonic_says("hmm, I couldn't pull solid matches for that one — see the source status below. "
                   "If a source is rate-limited, that's usually why. Try again in a bit, or loosen the framing.")
        render_source_status()
        if st.button("Start over", type="primary"):
            reset_all(); st.rerun()
        return

    sonic_says(f"these are the best matches 🎯<br>{total} papers, grouped into {len(clusters)} approaches. "
               "Hit <b>Chat it out</b> on any paper to actually talk to it.")
    render_source_status()

    top = st.columns([1, 1, 4])
    with top[0]:
        if st.button("🔄 New search", use_container_width=True):
            reset_all(); st.rerun()

    for i, cluster in enumerate(clusters):
        papers = cluster.get("papers") or {}
        if not papers:
            continue
        accent = CLUSTER_ACCENTS[i % len(CLUSTER_ACCENTS)]
        label = cluster.get("label", "Approach")
        rationale = cluster.get("rationale", "")

        st.markdown(
            f'<div class="cluster-head"><div class="cluster-bar" style="background:{accent};"></div>'
            f'<div class="cluster-title">{label}</div></div>',
            unsafe_allow_html=True,
        )
        if rationale:
            st.markdown(f'<div class="cluster-why">{rationale}</div>', unsafe_allow_html=True)

        items = list(papers.items())
        for row_start in range(0, len(items), 2):
            cols = st.columns(2)
            for col, (norm_title, record) in zip(cols, items[row_start:row_start + 2]):
                with col:
                    render_paper_card(norm_title, record)


# ---------------------------------------------------------------------------
# 12. CHAT VIEW  (download -> vectorize -> Q&A over one paper)
# ---------------------------------------------------------------------------
def _vec_loading_html(quote: str, phase: str) -> str:
    return (
        f'<div class="vec-wrap"><div class="vec-figure"><img src="{SONIC_DATA_URI}" alt="SONIC"/></div>'
        f'<div class="vec-quote"><span class="q">SONIC:</span> &ldquo;{quote}&rdquo;</div>'
        f'<div class="vec-phase">{phase}</div></div>'
    )


def _prepare_chat_blocking(record: dict, holder: dict):
    """Background-thread worker: resolve+download the real PDF, then vectorize
    and build the retriever/chain. Touches NO st.* (thread-safe). Results go in
    `holder`. Kept in a thread so the main thread can animate a progress bar +
    motivational quote while this slow work runs."""
    try:
        pdf_path = resolve_and_download_pdf(record)
        if not pdf_path:
            holder["error"] = ("Couldn't find a readable open-access PDF for this paper — it may be "
                               "paywalled. Use the 📄 Paper button to read it on the source site.")
            return
        from vectorizeer import build_vectorstore
        from Qa import get_llm, get_retriever, build_chain
        vs = build_vectorstore(pdf_path)
        holder["session"] = {"retriever": get_retriever(vs), "chain": build_chain(get_llm())}
    except Exception as e:
        holder["error"] = f"Couldn't prepare this paper for chat: {type(e).__name__}: {e}"


def ensure_chat_ready(norm_title: str):
    """Build (once) the retriever + chain for this paper's PDF and stash them in
    session_state. The slow download+vectorize runs in a background thread while
    the main thread shows a live progress bar + a rotating SONIC pep-quote."""
    if norm_title in st.session_state.chats:
        return st.session_state.chats[norm_title], None

    record = st.session_state.papers_by_key.get(norm_title, {})
    title = record.get("title") or norm_title.title()

    holder: dict = {}
    worker = threading.Thread(target=_prepare_chat_blocking, args=(record, holder), daemon=True)

    quotes = random.sample(SONIC_QUOTES, len(SONIC_QUOTES))
    panel, bar = st.empty(), st.progress(0)
    worker.start()
    pct, start = 6, time.time()
    while worker.is_alive():
        pct = min(pct + 2, 92)                       # ease toward 92%; real finish snaps to 100
        phase = ("Fetching the PDF…" if pct < 30
                 else "Reading & vectorizing every page…" if pct < 80 else "Almost there…")
        quote = quotes[int((time.time() - start) // 4) % len(quotes)]   # rotate every ~4s
        panel.markdown(_vec_loading_html(quote, phase), unsafe_allow_html=True)
        bar.progress(pct)
        time.sleep(0.35)
    worker.join()
    bar.progress(100)
    panel.empty(); bar.empty()

    if holder.get("error"):
        return None, holder["error"]

    session = holder["session"]
    session.update({"messages": [], "title": title})
    st.session_state.chats[norm_title] = session
    return session, None


def render_chat():
    from langchain_core.messages import HumanMessage, AIMessage
    from Qa import format_docs

    norm_title = st.session_state.active_chat
    record = st.session_state.papers_by_key.get(norm_title, {})
    title = record.get("title") or norm_title.title()

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("← Back to papers", use_container_width=True):
            st.session_state.active_chat = None
            st.rerun()

    st.markdown(f'<div class="cluster-head"><div class="cluster-bar" style="background:#7c5cff;"></div>'
                f'<div class="cluster-title">💬 {title}</div></div>', unsafe_allow_html=True)

    session, err = ensure_chat_ready(norm_title)
    if err:
        st.error(err)
        return

    sonic_says("ask me anything about this paper — I've read every page 📄 I'll ground every answer in the "
               "actual text and cite the pages.")

    # replay history
    for msg in session["messages"]:
        with st.chat_message("user" if msg["role"] == "user" else "assistant",
                             avatar="🧑‍🔬" if msg["role"] == "user" else SONIC_DATA_URI):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask about this paper…")
    if prompt:
        with st.chat_message("user", avatar="🧑‍🔬"):
            st.markdown(prompt)
        session["messages"].append({"role": "user", "content": prompt})

        # build LangChain chat history from prior turns (exclude the just-added question)
        history = []
        for m in session["messages"][:-1]:
            history.append(HumanMessage(content=m["content"]) if m["role"] == "user"
                           else AIMessage(content=m["content"]))

        with st.chat_message("assistant", avatar=SONIC_DATA_URI):
            try:
                docs = session["retriever"].invoke(prompt)
                context = format_docs(docs)

                def token_stream():
                    for chunk in session["chain"].stream(
                        {"question": prompt, "chat_history": history, "context": context}
                    ):
                        if chunk.content:
                            yield chunk.content

                answer = st.write_stream(token_stream())
                pages = sorted({f"p.{d.metadata.get('page')}" for d in docs})
                if pages:
                    st.caption("sources: " + ", ".join(pages))
            except Exception as e:
                answer = f"Sorry — I hit an error answering that: {type(e).__name__}: {e}"
                st.error(answer)

        session["messages"].append({"role": "assistant", "content": answer})


# ---------------------------------------------------------------------------
# 13. ROUTER
# ---------------------------------------------------------------------------
if st.session_state.error:
    st.warning(f"Something went sideways: {st.session_state.error}")
    st.session_state.error = ""

stage = st.session_state.stage

if stage == "results" and st.session_state.active_chat:
    render_chat()
elif stage == "welcome":
    render_welcome()
elif stage == "refining":
    render_refining()
elif stage == "review":
    render_review()
elif stage == "searching":
    render_searching()
elif stage == "results":
    render_results()
else:
    render_welcome()
