"""
utils/agents.py
------------------
Heavy model / graph loading, cached once per Streamlit server process.

`load_agents()` and `warm_chatbot_models()` are decorated with
@st.cache_resource so they only build once no matter how many times the
script reruns (Streamlit reruns the whole script top-to-bottom on every
interaction) -- that caching behavior has to survive the module split
unchanged, so these stay exactly as they were, just moved.
"""

import streamlit as st


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
