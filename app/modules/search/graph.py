from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, List, Dict, Literal, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from app.core.logging_config import get_node_logger
from app.modules.search.providers.arxiv import search_arxiv
from app.modules.search.providers.semantic_scholar import search_semantic_scholar
from app.modules.search.providers.openalex import search_openalex
from app.modules.search.reranking import rerank_by_relevance
import re
import unicodedata
import os


load_dotenv()

second_api_key = os.getenv("SECOND_GROQ_API_KEY")
api_key = os.getenv("GROQ_API_KEY")
# Setting up model
llm = ChatGroq(model = 'openai/gpt-oss-120b',api_key=second_api_key)
llm_2 = ChatGroq(model='openai/gpt-oss-120b',api_key=second_api_key)

# State of the Agent
class ResearchSearchState(TypedDict):
    run_id : str
    ResearchIntent : str
    Open_Alex_paper: List[dict]
    Semantic_Scholar_paper : List[dict]
    arXiv_paper: List[dict]
    aggregator : dict
    reranked_papers : dict
    clustered_papers : List[dict]
    # Per-source status so the UI can surface WHY a source came back empty
    # (e.g. Semantic Scholar rate-limited) instead of it looking silently blank.
    # Distinct keys per source -> no concurrent-write conflict across the
    # parallel fetch nodes.
    arxiv_status : dict
    semantic_scholar_status : dict
    open_alex_status : dict

class ClusterItem(BaseModel):
    cluster_id: int
    label: str = Field(description="Short, specific approach name")
    rationale: str = Field(description="2-3 sentence explanation of what unifies this cluster")
    paper_ids: List[int]

class ClusteringOutput(BaseModel):
    clusters: List[ClusterItem]

# Defining Nodes
def arXiv_papers(state: ResearchSearchState)-> ResearchSearchState:
    logger = get_node_logger(state["run_id"], "search.arxiv")
    prompt = f"""You are converting a Research Intent into a search query for the arXiv API.

arXiv search is PURELY LEXICAL — it does not understand natural language, intent,
or reasoning. It only matches literal keyword overlap using field-prefixed terms.

RULES FOR THE QUERY YOU PRODUCE:
- Use only these field prefixes: ti: (title), abs: (abstract), all: (all fields).
  Default to all: unless a term is clearly a proper technical name that belongs in a title.
- Combine terms using ONLY uppercase AND, OR, ANDNOT. No other operators exist.
- Do NOT nest field prefixes inside parentheses (e.g. all:(ti:(x)) is invalid/ambiguous
  on arXiv and must be avoided).
- Keep the structure FLAT: field:term AND field:term AND (term1 OR term2) is fine;
  deeper nesting is not.
- Extract only concrete technical noun phrases from the Problem and Objective sections.
  Do NOT use Additional Context — arXiv cannot reason about constraints, exclusions,
  or preferences, only literal keyword matches.
- Multi-word technical phrases should be joined with + between words (arXiv API convention),
  e.g. reinforcement+learning.
- Produce 4-6 core technical terms maximum. More terms narrow results without arXiv
  being able to judge relevance the way a ranked search engine would.
- Output ONLY the final query string in arXiv API syntax. No explanation, no preamble.

Research Intent:
{state['ResearchIntent']}"""
    try:
        query = llm.invoke(prompt).content
    except Exception:
        logger.exception("LLM call failed while generating the arXiv query")
        raise
    query = query.strip().strip('"').strip("'")
    logger.info("arXiv query: %s", query)
    papers = search_arxiv(query=query, logger=logger)
    logger.info("arXiv returned %d paper(s)", len(papers))
    return {'arXiv_paper': papers, 'arxiv_status': {"state": "ok", "count": len(papers)}}

def semantic_scholar_papers(state : ResearchSearchState)-> ResearchSearchState:
    logger = get_node_logger(state["run_id"], "search.semantic_scholar")
    prompt = f"""You are converting a Research Intent into a search query for the Semantic Scholar Search API. This endpoint matches terms ONLY against each paper's title and abstract.

CRITICAL BEHAVIOR TO UNDERSTAND FIRST:
This is an EXACT MATCH system, not a semantic/fuzzy search. There is no "close enough."
Bare words or quoted phrases placed next to each other with no operator between them
are implicitly ANDed — ALL of them must appear, verbatim, in the same paper's title or
abstract. This means every additional required term you add narrows the result set
further and increases the risk of zero results. A SINGLE required phrase that doesn't
match the field's actual standard terminology (e.g. requiring "human-operated" when
the literature actually says "human-driven") can zero out the entire query, even if
every other term in it is correct.

SYNTAX AVAILABLE:
- Bare word or phrase with no operator: still REQUIRED (ANDed with everything else),
  not optional. There is no implicit OR between adjacent terms.
- "exact phrase": double-quote a multi-word phrase that must appear exactly as
  written, word-for-word. Only use this for terminology you are highly confident
  is the field's standard phrasing.
- +term: explicitly required (behaves the same as a bare term — the + is for
  clarity/emphasis, not a different matching rule).
- -term: term must NOT appear. Use only for genuine exclusions the researcher
  explicitly stated.
- (a | b | c): matches ANY of the listed alternatives — use this to hedge against
  terminology uncertainty for a single concept.
- Parentheses group | and + clauses; keep grouping to 1 level deep.

RULES FOR CONSTRUCTING THE QUERY:
- Identify at most 2 CORE concepts from Problem + Objective that are essential to
  the research question, and require each with a quoted exact phrase (using + or
  bare — same effect). Do not require more than 2 concepts — since all required
  terms are ANDed, each additional one multiplies the risk of zero results.
- For ANY concept where you are not fully certain of the field's standard exact
  wording (e.g. how a specific comparison, method, or entity type is typically
  phrased in academic writing), do NOT lock it to a single quoted phrase. Instead,
  express it as an OR group of 2-3 plausible standard phrasings, e.g.
  ("human-driven" | "human-operated" | "manually driven"). This is especially
  important for adjective/description phrases (how something is characterized),
  which vary more across papers than core technical nouns do.
- Use (a | b) groups only for genuine synonymous variants of ONE concept — do not
  invent alternative concepts, methods, or approaches not present in the Research
  Intent.
- Do NOT use - exclusions unless Additional Context explicitly states something
  should be excluded.
- Keep the total query under ~15 words worth of terms. Favor 2 required core
  concepts plus 1 hedged OR group over stacking many required exact phrases.
- Output ONLY the final query string. No explanation, no preamble.

Research Intent:
{state['ResearchIntent']}"""
    try:
        query = llm.invoke(prompt).content
    except Exception:
        logger.exception("LLM call failed while generating the Semantic Scholar query")
        raise
    query = query.strip().strip('"').strip("'")
    logger.info("Semantic Scholar query: %s", query)
    status: dict = {}
    papers = search_semantic_scholar(query=query, logger=logger, status_out=status)
    logger.info("Semantic Scholar returned %d paper(s)", len(papers))
    return {'Semantic_Scholar_paper': papers, 'semantic_scholar_status': status}

def Open_alex_papers(state : ResearchSearchState)-> ResearchSearchState:
    logger = get_node_logger(state["run_id"], "search.openalex")
    prompt = f"""You are converting a Research Intent into a search query for the OpenAlex /works
search endpoint, which searches titles, abstracts, and available fulltext.

CRITICAL BEHAVIOR TO ACCOUNT FOR:
Words not separated by explicit boolean operators are treated as AND by default.
This means a long plain-keyword query risks ZERO results if any single term is too
narrow, because ALL terms must match. You must actively defend against this.

SYNTAX AVAILABLE:
- Uppercase AND, OR, NOT only (lowercase will not be recognized as operators).
- "exact phrase" for phrases that must appear together.
- Parentheses for grouping.

RULES FOR CONSTRUCTING THE QUERY:
- Identify 2-4 DISTINCT core concepts from Problem + Objective (not more — each
  AND-ed concept multiplies the risk of zero results).
- For each core concept, group any synonym/near-synonym terms together with OR
  inside parentheses, e.g. ("fuel efficiency" OR "fuel consumption").
- Join the distinct concept groups with AND.
- Use quotes around every multi-word phrase — unquoted multi-word phrases will be
  split into individual AND-ed words, which is almost always too strict.
- Do NOT use NOT unless Additional Context explicitly names something to exclude.
- Do NOT add synonyms or terms not implied by the Research Intent, even to "help"
  recall — only group terms that are genuinely equivalent phrasings of the same idea.
- Output ONLY the final query string. No explanation, no preamble.

Research Intent:
{state['ResearchIntent']}"""
    try:
        query = llm.invoke(prompt).content
    except Exception:
        logger.exception("LLM call failed while generating the OpenAlex query")
        raise
    query = query.strip().strip('"').strip("'")
    logger.info("OpenAlex query: %s", query)
    status: dict = {}
    papers = search_openalex(query=query, logger=logger, status_out=status)
    logger.info("OpenAlex returned %d paper(s)", len(papers))
    return {'Open_Alex_paper': papers, 'open_alex_status': status}

def normalize_title(title: str) -> str:
    """
    Produce a normalized string used ONLY for matching titles across sources.
    Never stored on the paper record itself — purely a dedup key.
    """
    if not title:
        return ""

    # Normalize unicode (curly quotes, accented chars) to a comparable ASCII-ish form
    text = unicodedata.normalize("NFKD", title)
    text = "".join(c for c in text if not unicodedata.combining(c))

    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)   # strip punctuation (colons, hyphens, periods, etc.)
    text = re.sub(r"\s+", " ", text)      # collapse whitespace
    return text.strip()

def merge_paper_entry(existing: dict, new: dict) -> dict:
    """
    Merge a newly-encountered paper into an existing aggregated entry
    for the same normalized title. No information is dropped —
    source-varying fields (source, citation_count, url, pdf_url)
    are kept per-source in dicts.
    """
    new_source = new.get("source")

    # --- title: keep the longer/more complete one ---
    existing_title = existing.get("title") or ""
    new_title = new.get("title") or ""
    merged_title = new_title if len(new_title) > len(existing_title) else existing_title

    # --- authors: union, order-preserving ---
    merged_authors = list(existing.get("authors") or [])
    for author in (new.get("authors") or []):
        if author not in merged_authors:
            merged_authors.append(author)

    # --- abstract: keep the longer one ---
    existing_abstract = existing.get("abstract")
    new_abstract = new.get("abstract")
    if existing_abstract and new_abstract:
        merged_abstract = existing_abstract if len(existing_abstract) >= len(new_abstract) else new_abstract
    else:
        merged_abstract = existing_abstract or new_abstract

    # --- year: first non-null wins (should agree across sources) ---
    merged_year = existing.get("year") if existing.get("year") is not None else new.get("year")

    # --- source-varying fields: dict keyed by source, nothing overwritten ---
    merged_citation_count = dict(existing.get("citation_count") or {})
    merged_citation_count[new_source] = new.get("citation_count")

    merged_url = dict(existing.get("url") or {})
    merged_url[new_source] = new.get("url")

    merged_pdf_url = dict(existing.get("pdf_url") or {})
    merged_pdf_url[new_source] = new.get("pdf_url")

    merged_sources = list(existing.get("source") or [])
    if new_source not in merged_sources:
        merged_sources.append(new_source)

    return {
        "title": merged_title,
        "authors": merged_authors or None,
        "abstract": merged_abstract,
        "year": merged_year,
        "source": merged_sources,
        "citation_count": merged_citation_count,
        "url": merged_url,
        "pdf_url": merged_pdf_url,
    }

def aggregator_node(state: ResearchSearchState) -> ResearchSearchState:
    logger = get_node_logger(state["run_id"], "search.aggregate")
    arxiv_papers = state.get("arXiv_paper", []) or []
    openalex_papers = state.get("Open_Alex_paper", []) or []
    semantic_scholar_papers_list = state.get("Semantic_Scholar_paper", []) or []
    all_papers = arxiv_papers + openalex_papers + semantic_scholar_papers_list

    aggregated: dict[str, dict] = {}

    for paper in all_papers:
        key = normalize_title(paper.get("title"))
        if not key:
            continue

        if key in aggregated:
            aggregated[key] = merge_paper_entry(aggregated[key], paper)
        else:
            # first time seeing this title — wrap single-source fields
            # into the same dict-keyed-by-source shape used by merges,
            # so every entry has a UNIFORM shape whether it came from
            # 1 source or all 3
            source = paper.get("source")
            aggregated[key] = {
                "title": paper.get("title"),
                "authors": paper.get("authors"),
                "abstract": paper.get("abstract"),
                "year": paper.get("year"),
                "source": [source],
                "citation_count": {source: paper.get("citation_count")},
                "url": {source: paper.get("url")},
                "pdf_url": {source: paper.get("pdf_url")},
            }

    logger.info(
        "Aggregated %d raw records (arXiv=%d, OpenAlex=%d, SemanticScholar=%d) into %d unique papers after dedup",
        len(all_papers), len(arxiv_papers), len(openalex_papers), len(semantic_scholar_papers_list), len(aggregated),
    )
    return {"aggregator": aggregated}

def reranker_node(state: ResearchSearchState) -> ResearchSearchState:
    """
    Reranks the aggregated papers by semantic similarity to the Research Intent,
    keeps the top 15, and returns the FULL records (not just title:abstract)
    for those top 15 — in the same order the reranker ranked them.
    """
    logger = get_node_logger(state["run_id"], "search.rerank")
    aggregator = state["aggregator"]

    # --- Build the {normalized_title: abstract} view the reranker expects ---
    papers_for_rerank: dict[str, str] = {
        normalized_title: record.get("abstract")
        for normalized_title, record in aggregator.items()
    }
    logger.info("Reranking %d aggregated papers by semantic similarity to the intent", len(papers_for_rerank))
    # --- Run the rerank ---
    top_papers = rerank_by_relevance(
        research_intent=state["ResearchIntent"],
        papers=papers_for_rerank,
        top_n=15,
        logger=logger,
    )

    # --- Rebuild full records for only the titles that survived reranking,
    #     preserving the ranked order (top_papers is an ordered dict) ---
    reranked_full: dict[str, dict] = {}
    for normalized_title in top_papers:
        record = aggregator.get(normalized_title)
        if record is not None:
            reranked_full[normalized_title] = record

    dropped_count = len(aggregator) - len(reranked_full)
    logger.info(
        "Kept top %d of %d papers after semantic reranking (%d dropped)",
        len(reranked_full), len(aggregator), dropped_count,
    )

    return {"reranked_papers": reranked_full}

def build_clustered_output(
    clustering_result: ClusteringOutput,
    id_to_title: dict[int, str],
    aggregator: dict,
) -> list[dict]:
    """
    Converts {cluster_id, label, rationale, paper_ids} clusters into:
    [{"label": ..., "rationale": ..., "papers": {normalized_title: full_aggregator_record, ...}}, ...]
    """
    output = []

    for cluster in clustering_result.clusters:
        papers_in_cluster = {}

        for pid in cluster.paper_ids:
            normalized_title = id_to_title.get(pid)
            if normalized_title is None:
                continue  # LLM hallucinated an ID that was never sent — skip, don't crash

            record = aggregator.get(normalized_title)
            if record is None:
                continue  # defensive: shouldn't happen if id_to_title is built correctly

            papers_in_cluster[normalized_title] = record

        output.append({
            "label": cluster.label,
            "rationale": cluster.rationale,
            "papers": papers_in_cluster,
        })

    return output

def prepare_papers_for_clustering(aggregator: dict) -> tuple[list[dict], dict[int, str]]:
    """
    Convert the aggregator dict into the (id, title, abstract) form needed for the
    clustering prompt, plus an id -> normalized_title map to reverse-lookup results.

    Papers with no abstract are excluded from clustering input (title alone is too
    weak a signal for approach-based grouping) but returned separately so they can
    still be surfaced to the user as "not clustered" rather than silently dropped.
    """
    clustering_input = []
    id_to_title: dict[int, str] = {}
    excluded_no_abstract: list[str] = []

    paper_id = 0
    for normalized_title, record in aggregator.items():
        abstract = record.get("abstract")

        if not abstract or not abstract.strip():
            excluded_no_abstract.append(normalized_title)
            continue

        clustering_input.append({
            "id": paper_id,
            "title": record.get("title") or normalized_title,
            "abstract": abstract,
        })
        id_to_title[paper_id] = normalized_title
        paper_id += 1

    return clustering_input, id_to_title

def clustering_node(state: ResearchSearchState) -> ResearchSearchState:
    logger = get_node_logger(state["run_id"], "search.cluster")
    clustering_input , id_to_title = prepare_papers_for_clustering(state['reranked_papers'])
    logger.info("Clustering %d paper(s) with usable abstracts into approach groups", len(clustering_input))

    prompt = f"""You are helping a researcher make sense of a set of retrieved papers by organizing
them into methodologically distinct APPROACH CLUSTERS.

You will receive:
1. A RESEARCH INTENT (Problem / Objective / Additional Context) — this defines what
   the researcher is actually trying to figure out.
2. A numbered list of papers, each with a title and abstract.

YOUR GOAL:
All these papers were retrieved because they already share a common TOPIC with the
Research Intent — that overlap is not useful information on its own. Your job is to
find the more useful signal underneath: the DIFFERENT APPROACHES, METHODS, or
STRATEGIES these papers take toward addressing that shared topic. Think of each
cluster as answering the question: "If the researcher wanted to pursue THIS
direction, which papers would be their starting point?"

USE THE RESEARCH INTENT TO GUIDE WHAT COUNTS AS A MEANINGFUL DISTINCTION:
- The Objective tells you what decision or comparison the researcher actually cares
  about — let it sharpen which methodological differences matter versus which are
  noise. If the Objective is about comparing two paradigms, treat "which paradigm
  does this paper represent" as a primary clustering axis, not an incidental detail.
- The Additional Context may reveal known approaches the researcher is already aware
  of, or constraints (like avoiding full retraining) — clusters that map onto these
  should be called out explicitly, since they connect directly to something the
  researcher already flagged as relevant.

FOR EACH CLUSTER, PRODUCE:
- cluster_id: a sequential integer starting at 0, unique per cluster.
- label: a short, specific name for the actual approach (not a vague topic word) —
  e.g. "Reinforcement-learning-based car-following control policies," not "RL papers."
- rationale: 2-3 sentences explaining WHAT unifies these papers methodologically,
  and WHY this represents a distinct direction the researcher could pursue or
  compare against, relative to the other clusters.
- paper_ids: the list of paper IDs belonging to this cluster.

SIZING THE CLUSTERS:
- Aim for 4-7 clusters when the paper count comfortably supports that many distinct
  methodological groupings. This is a target, not a quota — with a small paper set,
  fewer, larger clusters are correct; do not manufacture extra clusters just to hit
  the range, and do not force a paper into a cluster it doesn't methodologically fit.
- If two clusters would end up nearly identical in meaning, merge them instead of
  keeping both.
- If some papers do not fit coherently into any clear methodological group, place
  them together in one final cluster labeled "Other / Mixed Approaches" rather than
  forcing a false fit elsewhere. One honest catch-all beats several padded clusters.

HARD CONSTRAINTS:
- Every paper ID in the input must appear in exactly one cluster, including the
  catch-all if used. None may be omitted or duplicated across clusters.
- Do not invent methods, results, or claims not supported by the given title/abstract
  text — ground every rationale only in what's actually stated.

RESEARCH INTENT:
{state["ResearchIntent"]}

PAPERS:
{clustering_input}
"""

    structured_llm = llm_2.with_structured_output(ClusteringOutput)

    try:
        clustering_result = structured_llm.invoke(prompt)
    except Exception as e:
        logger.exception("Structured LLM invocation failed during clustering: %s: %s", type(e).__name__, e)
        return {"clustered_papers": []}

    clustered = build_clustered_output(clustering_result, id_to_title, state["aggregator"])
    total_clustered_papers = sum(len(c["papers"]) for c in clustered)
    logger.info("Clustering produced %d cluster(s) covering %d paper(s)", len(clustered), total_clustered_papers)

    return {"clustered_papers": clustered}

# Building The Graph
builder = StateGraph(ResearchSearchState)

builder.add_node('arxiv',arXiv_papers)
builder.add_node('semantic_scholar',semantic_scholar_papers)
builder.add_node('open_alex',Open_alex_papers)
builder.add_node('aggregation',aggregator_node)
builder.add_node('reranker', reranker_node)
builder.add_node('clustering',clustering_node)

builder.add_edge(START,'arxiv')
builder.add_edge(START,'semantic_scholar')
builder.add_edge(START,'open_alex')
builder.add_edge('arxiv','aggregation')
builder.add_edge('semantic_scholar','aggregation')
builder.add_edge('open_alex','aggregation')
builder.add_edge('aggregation','reranker')
builder.add_edge('reranker','clustering')
builder.add_edge('clustering',END)

graph = builder.compile()

if __name__ == "__main__":
    # Manual standalone test — only runs when you execute this file directly
    # (`python -m app.modules.search.graph`), never on import.
    input_research_intent_5 = """Problem:
Large language models frequently produce fluent, confident-sounding answers that contain factual errors, and existing hallucination-detection methods disagree substantially with each other when applied to the same model outputs, making it unclear which detection approach should be trusted for deployment decisions.

Objective:
Identify hallucination-detection methods for large language models that show consistent, reliable performance across different model families and task types, rather than being effective only in the narrow setting they were originally evaluated on.

Additional Context:
- Focus on post-hoc detection methods applied to generated text, not training-time interventions like RLHF.
- Known approaches the researcher is aware of: self-consistency sampling, retrieval-based fact verification, and uncertainty/entropy-based methods.
- Interested primarily in open-domain question answering and summarization tasks, not code generation."""

    result = graph.invoke({"ResearchIntent": input_research_intent_5, "run_id": "standalone-test"})
    print(result["clustered_papers"])
