"""
utils/view_searching.py
---------------------------
SEARCHING stage: resumes the INTENT graph past its interrupt, then STREAMS
the SEARCH + CLUSTER graph so the UI ticks each step off live instead of
hanging on one spinner.
"""

import streamlit as st

from utils.agents import load_agents
from utils.intent_text import join_intent_sections
from utils.search_progress import search_steps_html
from utils.sonic import sonic_says


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
    board.markdown(search_steps_html(set(), {}), unsafe_allow_html=True)
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
            board.markdown(search_steps_html(completed, counts), unsafe_allow_html=True)

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
