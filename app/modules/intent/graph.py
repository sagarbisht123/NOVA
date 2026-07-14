from typing import TypedDict
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_tavily import TavilySearch
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.core.logging_config import get_node_logger

load_dotenv()


# State definition
class ResearchIntentState(TypedDict):
    run_id: str
    user_query: str
    problem: str
    objective: str
    additional_context: str
    aggregated_intent: str
    search_results: str
    polished_research_intent: str
    human_verified_intent: str

second_api_key = os.getenv("SECOND_GROQ_API_KEY")

# LLM + tools — instantiated once at import time, reused across requests
llm = ChatGroq(model="openai/gpt-oss-120b",api_key =second_api_key)
search_tool = TavilySearch(max_results=5)


# Nodes
def problem_framing(state: ResearchIntentState) -> ResearchIntentState:
    logger = get_node_logger(state["run_id"], "intent.problem")
    prompt = f""" You are extracting the PROBLEM STATEMENT from a researcher's raw, informal research idea.

Your only job: describe what is happening — the gap, limitation, failure mode, or open issue in the current state of the field — as understood from the query.

STRICT RULES:
- Do NOT propose what should be done about it. That is not your job.
- Do NOT suggest methods, techniques, or solutions, even in passing.
- Do NOT include constraints, preferences, or scope limits (time range, baselines, excluded approaches). That belongs elsewhere.
- Write 2-4 sentences, in formal academic register, third person.
- If the query does not clearly state a problem, infer the most reasonable underlying problem implied by the researcher's framing — do not leave it empty, but do not invent specifics not implied by the query.

Output only the problem statement text. No labels, no preamble.

User's raw query:
{state['user_query']}
"""
    logger.info("Framing problem statement from user query (%d chars)", len(state["user_query"]))
    try:
        problem = llm.invoke(prompt).content
    except Exception:
        logger.exception("LLM call failed while framing the problem statement")
        raise
    logger.info("Problem statement produced (%d chars): %s", len(problem), problem[:200].replace("\n", " "))
    return {"problem": problem}


def objective_framing(state: ResearchIntentState) -> ResearchIntentState:
    logger = get_node_logger(state["run_id"], "intent.objective")
    prompt = f"""You are extracting the RESEARCH OBJECTIVE from a researcher's raw, informal research idea.

Your only job: describe what the researcher wants to find out, achieve, or resolve — the goal of the research, not the method to get there.

STRICT RULES:
- Do NOT describe the current problem/gap in the field. That belongs elsewhere.
- Do NOT propose a specific method, technique, model, or solution as the objective. Phrase the objective in terms of outcome ("identify", "evaluate", "compare", "reduce", "understand"), never in terms of a specific technique to be applied.
  - Wrong: "Use contrastive learning to reduce hallucinations."
  - Right: "Identify techniques that reduce hallucinations while preserving answer quality."
- Do NOT include constraints, preferred methods, or scope limits. That belongs elsewhere.
- Write 1-3 sentences, in formal academic register, third person.

Output only the objective text. No labels, no preamble.

User's raw query:
{state['user_query']}
"""
    logger.info("Framing research objective from user query")
    try:
        objective = llm.invoke(prompt).content
    except Exception:
        logger.exception("LLM call failed while framing the research objective")
        raise
    logger.info("Objective produced (%d chars): %s", len(objective), objective[:200].replace("\n", " "))
    return {"objective": objective}


def additional_context_framing(state: ResearchIntentState) -> ResearchIntentState:
    logger = get_node_logger(state["run_id"], "intent.context")
    prompt = f"""You are extracting ADDITIONAL CONTEXT from a researcher's raw, informal research idea.

Your only job: capture optional supporting details the researcher mentioned that are NOT the problem and NOT the objective — for example: preferred methods, known approaches they're already aware of, constraints, application domain, exclusions, time range, baseline models/papers to compare against.

STRICT RULES:
- Do NOT restate the problem or the objective in different words.
- Do NOT invent context that isn't implied by the query. It is normal and acceptable for this field to be sparse.
- If the query genuinely contains no such details, output exactly: "None specified."
- If details exist, write them as a short list or 1-3 sentences, in formal academic register.

Output only the additional context text (or "None specified."). No labels, no preamble.

User's raw query:
{state['user_query']}"""
    logger.info("Extracting additional context from user query")
    try:
        additional_context = llm.invoke(prompt).content
    except Exception:
        logger.exception("LLM call failed while extracting additional context")
        raise
    logger.info("Additional context produced (%d chars): %s", len(additional_context), additional_context[:200].replace("\n", " "))
    return {"additional_context": additional_context}


def aggregator(state: ResearchIntentState) -> ResearchIntentState:
    logger = get_node_logger(state["run_id"], "intent.aggregator")
    prompt = f"""You are producing the FINAL RESEARCH INTENT document by harmonizing three independently-drafted sections into one coherent whole.

You will receive:
- PROBLEM: what is currently happening / the gap
- OBJECTIVE: what the researcher wants to find out or achieve
- ADDITIONAL_CONTEXT: optional supporting details (may be "None specified.")

Your job is to make these three sections read as if written together, by:
- Using consistent terminology across all three (e.g., if PROBLEM says "vision-language models" and OBJECTIVE says "VLMs," pick one term and use it consistently)
- Smoothing awkward phrasing or redundancy between sections
- Ensuring pronouns and references are unambiguous across sections (e.g., "this issue" in OBJECTIVE should clearly refer back to something named in PROBLEM)
- Adjusting tone/register so all three sections sound like one voice

STRICT RULES — DO NOT:
- Do NOT move content between sections. If OBJECTIVE contains a method, do not move it to ADDITIONAL_CONTEXT — leave the section boundary as-is, just smooth the language.
- Do NOT add new claims, facts, or specifics that were not present in the original three sections.
- Do NOT remove information for brevity. Every substantive point from all three sections must remain.
- Do NOT collapse the three sections into a single paragraph. Keep them clearly separated under their own headers.
- If ADDITIONAL_CONTEXT is "None specified.", keep it exactly as "None specified." in the output — do not fabricate content for it.

Output in exactly this format:

Problem:
<harmonized problem text>

Objective:
<harmonized objective text>

Additional Context:
<harmonized additional context text, or "None specified.">

Do not include any preamble, explanation, or text outside this format.

Inputs:
PROBLEM:
{state['problem']}

OBJECTIVE:
{state['objective']}

ADDITIONAL_CONTEXT:
{state['additional_context']}"""
    logger.info("Harmonizing problem/objective/context into one intent document")
    try:
        aggregator_intent = llm.invoke(prompt).content
    except Exception:
        logger.exception("LLM call failed while harmonizing the intent sections")
        raise
    logger.info("Aggregated intent produced (%d chars)", len(aggregator_intent))
    return {"aggregated_intent": aggregator_intent}


def web_polish_node(state: ResearchIntentState) -> ResearchIntentState:
    logger = get_node_logger(state["run_id"], "intent.polish")

    # Step 1: derive a concise search query from the aggregated intent
    query_gen_prompt = f"""Given this Research Intent, generate ONE concise web search query
(under 15 words) to find current terminology, related work, or factual grounding
for the topic. Output only the query text, nothing else.

Research Intent:
{state['aggregated_intent']}
"""
    try:
        search_query = llm.invoke(query_gen_prompt).content
    except Exception:
        logger.exception("LLM call failed while generating the web search query")
        raise
    logger.info("Web search query: %s", search_query)

    # Step 2: run the search
    try:
        raw_results = search_tool.invoke({"query": search_query})
    except Exception:
        logger.exception("Tavily web search failed")
        raise
    results = raw_results.get("results", [])
    logger.info("Web search returned %d result(s)", len(results))
    results_text = "\n\n".join(
        f"Source: {r.get('title', 'N/A')}\n{r.get('content', '')}"
        for r in results
    )

    # Step 3: polish the intent using search results, with strict boundaries
    polish_prompt = f"""You are GROUNDING and POLISHING a Research Intent document using web search results.

You will receive the current Research Intent (Problem / Objective / Additional Context)
and a set of web search results related to its topic.

Your ONLY job:
- Correct or sharpen field-specific terminology if the current text uses vague or outdated terms
- Verify and correct named entities (model names, benchmark names, paper titles) if search results
  show the current text has them wrong or imprecise
- Improve clarity and precision of wording

STRICT RULES — DO NOT:
- Do NOT move content between Problem / Objective / Additional Context sections.
- Do NOT change the meaning, scope, or intent of any section.
- Do NOT add citations, links, or references to sources in the output text.
- If the search results are irrelevant or add nothing useful, return the Research Intent unchanged.
- Preserve the exact three-section format with headers: Problem / Objective / Additional Context.

Output in exactly this format, nothing else:

Problem:
<text>

Objective:
<text>

Additional Context:
<text>

Current Research Intent:
{state['aggregated_intent']}

Web Search Results:
{results_text}
"""
    try:
        polished = llm.invoke(polish_prompt)
    except Exception:
        logger.exception("LLM call failed while polishing the research intent")
        raise
    logger.info("Polished research intent produced (%d chars)", len(polished.content))

    return {
        "search_results": results_text,
        "polished_research_intent": polished.content,
    }


def human_review_node(state: ResearchIntentState) -> ResearchIntentState:
    logger = get_node_logger(state["run_id"], "intent.human_review")
    logger.info("Pausing for human review of the polished research intent")
    human_response = interrupt({
        "polished_research_intent": state["polished_research_intent"],
        "instruction": "Review and edit this Research Intent.",
    })
    logger.info("Human-verified intent received (%d chars)", len(human_response))
    return {"human_verified_intent": human_response}


# Graph building
builder = StateGraph(ResearchIntentState)

builder.add_node("problem", problem_framing)
builder.add_node("objective", objective_framing)
builder.add_node("context", additional_context_framing)
builder.add_node("human_review", human_review_node)
builder.add_node("aggregator", aggregator)
builder.add_node("polish", web_polish_node)

builder.add_edge(START, "problem")
builder.add_edge(START, "objective")
builder.add_edge(START, "context")
builder.add_edge("problem", "aggregator")
builder.add_edge("objective", "aggregator")
builder.add_edge("context", "aggregator")
builder.add_edge("aggregator", "polish")
builder.add_edge("polish", "human_review")
builder.add_edge("human_review", END)

# In-process checkpointer — keeps interrupted threads alive between the
# /intent/start and /intent/resume calls. Lives in this worker's memory only:
# fine for a single dev server, but state is lost on restart and isn't shared
# across multiple uvicorn workers. Swap for a SqliteSaver/PostgresSaver if
# that ever matters.
checkpointer = MemorySaver()

graph = builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    # Manual standalone test — only runs when you execute this file directly
    # (`python -m app.modules.intent.graph`), never on import.
    query = """Hi ... well I have been looking into the problem of the driving behaviour in the car following scenarios in this scenarios what needs to be done is I want to analyse the car following behavior for the context of fuel efficicency comparing the human driven vehicle which are not fuel efficient and the RL driven which are excellent in fuel efficiency the comparison is tedious because many variables change at once velocity acceleration relative distance from the vehicle ahead etc so just to compare fuel efficiency is tough. I want to find out the ways in which we can get a good comparing method for both the vehicles"""

    config = {"configurable": {"thread_id": "test-thread-1"}}
    result = graph.invoke({"user_query": query, "run_id": "standalone-test"}, config=config)

    print("--- PAUSED FOR HUMAN REVIEW ---")
    print(result["__interrupt__"])

    edited_text = result["__interrupt__"][0].value["polished_research_intent"]
    final_result = graph.invoke(Command(resume=edited_text), config=config)

    print("\n--- FINAL RESULT ---")
    print(final_result["human_verified_intent"])
