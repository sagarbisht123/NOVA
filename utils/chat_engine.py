"""
utils/chat_engine.py
-----------------------
Threaded chat-prep: downloading + vectorizing a paper's PDF and building its
retriever/chain off the main thread, while the main thread animates a
progress bar + rotating SONIC pep-quote. `ensure_chat_ready()` is the public
entrypoint; it stashes the built session (retriever, chain, messages, title)
in st.session_state.chats keyed by the paper's normalized title.
"""

import random
import threading
import time

import streamlit as st

from utils.constants import SONIC_QUOTES
from utils.papers import resolve_and_download_pdf
from utils.sonic import SONIC_DATA_URI


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
