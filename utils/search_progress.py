"""
utils/search_progress.py
---------------------------
Live checklist renderer for the SEARCHING stage: turns the set of completed
LangGraph node names + per-source paper counts into the step-by-step HTML
checklist markup.
"""

_SEARCH_STEPS = [
    ("arxiv", "Searching arXiv"),
    ("semantic_scholar", "Searching Semantic Scholar"),
    ("open_alex", "Searching OpenAlex"),
    ("aggregation", "Merging &amp; deduplicating"),
    ("reranker", "Re-ranking by relevance (SPECTER)"),
    ("clustering", "Clustering by approach"),
]


def search_steps_html(completed: set, counts: dict) -> str:
    sources_done = all(s in completed for s in ("arxiv", "semantic_scholar", "open_alex"))

    def state_of(key):
        if key in completed:
            return "done"
        if key in ("arxiv", "semantic_scholar", "open_alex"):
            return "active"
        if key == "aggregation":
            return "active" if sources_done else "pending"
        if key == "reranker":
            return "active" if "aggregation" in completed else "pending"
        if key == "clustering":
            return "active" if "reranker" in completed else "pending"
        return "pending"

    rows = []
    for key, label in _SEARCH_STEPS:
        s = state_of(key)
        ic = "✓" if s == "done" else ("•" if s == "pending" else "")
        cnt = f'<span class="step-count">{counts[key]} papers</span>' if key in counts else ""
        rows.append(f'<div class="step-row {s}"><div class="step-ic">{ic}</div><div>{label}</div>{cnt}</div>')
    return '<div class="search-wrap">' + "".join(rows) + "</div>"
