"""
utils/view_chat.py
---------------------
CHAT stage (download -> vectorize -> Q&A over one paper): replays history and
streams new answers with page citations.
"""

import streamlit as st

from utils.chat_engine import ensure_chat_ready
from utils.sonic import SONIC_DATA_URI, sonic_says


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
