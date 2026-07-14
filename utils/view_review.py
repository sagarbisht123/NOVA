"""
utils/view_review.py
-----------------------
REVIEW stage: lets the user edit SONIC's framed Problem / Objective /
Additional Context before launching the search.
"""

import streamlit as st

from utils.sonic import sonic_says
from utils.state import reset_all


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
