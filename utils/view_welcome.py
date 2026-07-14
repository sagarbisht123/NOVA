"""
utils/view_welcome.py
------------------------
WELCOME stage: SONIC's big hero figure + the free-text box where the user
dumps their raw research idea.
"""

import uuid

import streamlit as st

from utils.sonic import SONIC_DATA_URI


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
