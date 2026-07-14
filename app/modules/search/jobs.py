"""
In-memory job tracking for the search graph.

The search graph (3 external APIs + a local SPECTER rerank pass + a
structured-output clustering call) can take tens of seconds, so it runs as a
FastAPI BackgroundTask rather than inline in a request. Progress is tracked
in this plain dict, which the client polls via GET /search/status/{job_id}.

Import note: `search_graph` is imported at module level (not inside the
function) so that importing this module — which happens once, at FastAPI
startup — is what triggers loading the SPECTER embedding model in
app/modules/search/reranking.py. That way the multi-second model load
happens once at boot, not on the first user's search request.

Limitation to be aware of: this dict lives in a single Python process's
memory. It resets on server restart and is NOT shared across multiple
uvicorn workers (`--workers N`). Fine for a single dev/demo server; swap for
Redis or a DB-backed job table if this ever needs to run with more than one
worker process.
"""

from typing import Optional

from app.core.logging_config import get_node_logger
from app.modules.search.graph import graph as search_graph

JOBS: dict[str, dict] = {}


def create_job(job_id: str, run_id: str) -> None:
    JOBS[job_id] = {"job_id": job_id, "status": "running", "clustered_papers": None, "error": None}
    get_node_logger(run_id, "job").info("Search job %s created", job_id)


def get_job(job_id: str) -> Optional[dict]:
    return JOBS.get(job_id)


def run_search_job(job_id: str, research_intent: str, run_id: str) -> None:
    """Runs the search graph synchronously. Called via BackgroundTasks,
    which executes sync callables in a threadpool — so this does not block
    the event loop for other requests while it runs."""
    logger = get_node_logger(run_id, "job")
    logger.info("Search job %s started", job_id)
    try:
        result = search_graph.invoke({"ResearchIntent": research_intent, "run_id": run_id})
        clustered_papers = result["clustered_papers"]
        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["clustered_papers"] = clustered_papers
        logger.info("Search job %s completed: %d cluster(s) produced", job_id, len(clustered_papers or []))
    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = f"{type(e).__name__}: {e}"
        logger.exception("Search job %s failed", job_id)
