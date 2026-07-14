import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from langgraph.types import Command

from app.core.logging_config import get_node_logger
from app.modules.intent.graph import graph as intent_graph
from app.modules.intent.schemas import (
    IntentResumeRequest,
    IntentResumeResponse,
    IntentStartRequest,
    IntentStartResponse,
)
from app.modules.search.jobs import create_job, run_search_job

router = APIRouter(prefix="/intent", tags=["intent"])


@router.post("/start", response_model=IntentStartResponse)
def start_intent(payload: IntentStartRequest):
    """Runs the intent graph's parallel framing + polish nodes. The graph
    hits human_review_node's interrupt() immediately, so this call always
    returns the paused state — it never runs to completion on its own."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    logger = get_node_logger(thread_id, "api.intent_start")
    logger.info("New research query received (%d chars)", len(payload.user_query))

    result = intent_graph.invoke({"user_query": payload.user_query, "run_id": thread_id}, config=config)

    if "__interrupt__" not in result:
        # Defensive: should never happen given the graph's fixed structure,
        # but fail loudly rather than return a malformed response.
        logger.error("Intent graph did not pause for review as expected")
        raise HTTPException(status_code=500, detail="Intent graph did not pause for review as expected.")

    interrupt_payload = result["__interrupt__"][0].value
    logger.info("Intent framing complete — paused for human review")

    return IntentStartResponse(
        thread_id=thread_id,
        polished_research_intent=interrupt_payload["polished_research_intent"],
        instruction=interrupt_payload["instruction"],
    )


@router.post("/resume", response_model=IntentResumeResponse)
def resume_intent(payload: IntentResumeRequest, background_tasks: BackgroundTasks):
    """Resumes the paused intent graph with the human-edited text, then
    immediately kicks off the search graph as a background job using the
    resulting human_verified_intent — no separate /search/start call needed."""
    config = {"configurable": {"thread_id": payload.thread_id}}
    logger = get_node_logger(payload.thread_id, "api.intent_resume")
    logger.info("Resuming intent graph with human-edited text")

    result = intent_graph.invoke(Command(resume=payload.edited_intent), config=config)

    if "human_verified_intent" not in result:
        logger.error("No paused intent graph found for this thread_id, or it was already resumed")
        raise HTTPException(
            status_code=404,
            detail="No paused intent graph found for this thread_id, or it has already been resumed.",
        )

    human_verified_intent = result["human_verified_intent"]

    job_id = str(uuid.uuid4())
    create_job(job_id, payload.thread_id)
    logger.info("Human-verified intent finalized — starting search job %s", job_id)
    background_tasks.add_task(run_search_job, job_id, human_verified_intent, payload.thread_id)

    return IntentResumeResponse(
        thread_id=payload.thread_id,
        human_verified_intent=human_verified_intent,
        job_id=job_id,
        status="running",
    )
