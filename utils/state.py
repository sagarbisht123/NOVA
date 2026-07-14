"""
utils/state.py
-----------------
Session-state schema, initialization, and reset/wipe logic.
"""

import shutil

import streamlit as st

from utils.paths import DOWNLOADS_DIR, VECTORSTORES_DIR

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


def init_session_state():
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
