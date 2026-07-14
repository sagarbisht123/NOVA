"""
utils/view_refining.py
-------------------------
REFINING stage: runs the INTENT graph up to its human-review interrupt, then
hands the framed Problem / Objective / Additional Context off to the REVIEW
stage.
"""

import streamlit as st

from utils.agents import load_agents
from utils.intent_text import split_intent_sections
from utils.sonic import sonic_says


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
