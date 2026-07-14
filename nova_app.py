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

from utils import paths  # noqa: F401  — MUST be first: wires sys.path + chdir + .env

import streamlit as st

from utils.agents import boot
from utils.state import init_session_state
from utils.styles import inject_styles
from utils.view_chat import render_chat
from utils.view_refining import render_refining
from utils.view_results import render_results
from utils.view_review import render_review
from utils.view_searching import render_searching
from utils.view_welcome import render_welcome

# ---------------------------------------------------------------------------
# 1. PAGE CONFIG + THEME  (must be the first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(page_title="NOVA · Research Assistant", page_icon="✦", layout="wide")
inject_styles()

# ---------------------------------------------------------------------------
# 2. SESSION STATE
# ---------------------------------------------------------------------------
init_session_state()

# ---------------------------------------------------------------------------
# 3. HEADER
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
# 4. ROUTER
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
