"""
reranking.py

Reranks papers by semantic similarity to the Research Intent using SPECTER
(allenai-specter) — an embedding model trained specifically on academic
paper title/abstract pairs, rather than a generic sentence embedding model.

Install once:
    pip install sentence-transformers
"""

import logging
from typing import Optional

from sentence_transformers import SentenceTransformer
import numpy as np

# Loaded once at module import time — NOT inside the function.
# Loading a transformer model from disk/HF hub takes a few seconds; if this
# were inside the function, every call would reload it, which is wasteful
# if this function gets called more than once in a session.
_MODEL = SentenceTransformer("sentence-transformers/allenai-specter")

_fallback_logger = logging.getLogger(__name__)


def rerank_by_relevance(
    research_intent: str,
    papers: dict[str, str],
    top_n: int = 10,
    logger: Optional[logging.Logger] = None,
) -> dict[str, str]:
    """
    Rerank papers by semantic similarity to the Research Intent.

    Parameters
    ----------
    research_intent : str
        The full Research Intent text (Problem + Objective + Additional
        Context, or however you've combined it) — used as the query vector.
    papers : dict[str, str]
        {normalized_title: abstract} — the aggregator's title/abstract pairs.
    top_n : int
        How many top-ranked papers to keep. Default 15.
    logger : logging.Logger, optional
        Node-scoped logger from the caller. Falls back to a module logger
        when this function is used standalone.

    Returns
    -------
    dict[str, str]
        A NEW dict, same {normalized_title: abstract} shape, containing only
        the top_n most relevant entries, ordered from most to least relevant.
        Insertion order is preserved (Python 3.7+ dicts are ordered), so
        iterating this dict gives you the ranking directly.
    """
    log = logger or _fallback_logger

    if not papers:
        return {}

    # --- Guard against empty/whitespace-only abstracts ---
    # These can't be meaningfully embedded for relevance comparison. Rather
    # than crash or silently mis-rank them, exclude them from ranking and
    # log which ones were skipped so nothing disappears without a trace.
    valid_titles = []
    valid_abstracts = []
    skipped_no_abstract = []

    for normalized_title, abstract in papers.items():
        if abstract and abstract.strip():
            valid_titles.append(normalized_title)
            valid_abstracts.append(abstract)
        else:
            skipped_no_abstract.append(normalized_title)

    if skipped_no_abstract:
        log.info("Skipped %d paper(s) with no abstract: %s", len(skipped_no_abstract), skipped_no_abstract)

    if not valid_abstracts:
        log.info("No papers had usable abstracts — returning empty result.")
        return {}

    # --- Embed the query (Research Intent) and all candidate abstracts ---
    # normalize_embeddings=True means each vector has unit length, so a
    # simple dot product between two vectors IS the cosine similarity —
    # no separate cosine-similarity library call needed.
    query_embedding = _MODEL.encode(
        research_intent,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    paper_embeddings = _MODEL.encode(
        valid_abstracts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        batch_size=32,
        show_progress_bar=False,
    )

    # --- Cosine similarity of every paper against the query, in one shot ---
    similarities = paper_embeddings @ query_embedding  # shape: (num_papers,)

    # --- Sort by similarity, descending ---
    ranked_indices = np.argsort(-similarities)

    # --- Log the full ranking for visibility/debugging before truncating ---
    ranking_lines = "\n".join(
        f"    {similarities[idx]:.4f}  {valid_titles[idx]}" for idx in ranked_indices
    )
    log.info("Full relevance ranking (%d papers, title : similarity score):\n%s", len(valid_titles), ranking_lines)

    top_indices = ranked_indices[:top_n]

    dropped_count = len(valid_titles) - len(top_indices)
    if dropped_count > 0:
        log.info("Kept top %d, dropped %d lower-relevance paper(s).", len(top_indices), dropped_count)

    # --- Build the result dict in ranked order ---
    result = {
        valid_titles[idx]: valid_abstracts[idx]
        for idx in top_indices
    }

    return result


if __name__ == "__main__":
    # Quick standalone test
    test_intent = (
        "Identify a robust methodology for comparing the fuel efficiency of "
        "human-driven and reinforcement-learning-controlled vehicles in "
        "car-following maneuvers, accounting for speed, acceleration, and headway."
    )
    test_papers = {
        "ecofollower an environmentfriendly car following model": (
            "This study introduces EcoFollower, a novel eco-car-following "
            "model developed using reinforcement learning to optimize fuel "
            "consumption in car-following scenarios."
        ),
        "predicting fuel research octane number using spectra": (
            "We show that an accurate statistical model for the Research "
            "Octane Number of gasoline can be constructed using infrared "
            "absorbance spectroscopy data."
        ),
    }

    reranked = rerank_by_relevance(test_intent, test_papers, top_n=15)
    print("\nFinal reranked result:")
    for title, abstract in reranked.items():
        print(f"- {title}")
