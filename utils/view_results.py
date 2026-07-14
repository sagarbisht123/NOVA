"""
utils/view_results.py
------------------------
RESULTS stage: clean paper thumbnails grouped by approach cluster, plus the
per-source status strip.
"""

import streamlit as st

from utils.constants import CLUSTER_ACCENTS, SOURCE_COLORS
from utils.papers import author_line, first_available
from utils.sonic import sonic_says
from utils.state import reset_all


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
