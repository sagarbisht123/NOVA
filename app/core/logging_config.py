"""
Per-run logging.

Every user-submitted research query gets one identifier — the `thread_id`
handed back by POST /intent/start — that flows through both graphs as
`run_id`: the intent graph's ResearchIntentState carries it from the start,
and app/modules/search/jobs.py threads the same value into the search
graph's ResearchSearchState when it kicks off the background job. Every
node in both graphs, plus the API providers and reranker they call, logs
through `get_node_logger(run_id, ...)`, so logs/{run_id}.log ends up with
the complete story for that one input: every node's output, paper counts
per source, and any failure with its exception, in call order.
"""

import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_run_loggers: dict[str, logging.Logger] = {}


def _safe_filename(run_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in run_id)


def _get_run_logger(run_id: str) -> logging.Logger:
    """
    One logger per run_id, writing to logs/{run_id}.log plus the console.
    propagate=False so records don't also bubble up to the root logger's
    own console handler and print twice.
    """
    if run_id in _run_loggers:
        return _run_loggers[run_id]

    logger = logging.getLogger(f"run.{run_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # `logging.getLogger` returns the SAME object process-wide, so guard against
    # re-attaching handlers if this logger was already set up — otherwise a host
    # that re-executes the module (e.g. Streamlit re-running the script, which can
    # bypass the _run_loggers cache) stacks duplicate handlers and every line gets
    # written to the file N times.
    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_DIR / f"{_safe_filename(run_id)}.log", encoding="utf-8")
        file_handler.setFormatter(_FORMATTER)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(_FORMATTER)
        logger.addHandler(console_handler)

    _run_loggers[run_id] = logger
    return logger


def get_node_logger(run_id: str, node_name: str) -> logging.Logger:
    """
    Logger for one node/step within one run, e.g.
    get_node_logger(run_id, "intent.problem") or
    get_node_logger(run_id, "search.arxiv"). Records go to
    logs/{run_id}.log (and the console) via the shared run-level logger.
    """
    return _get_run_logger(run_id).getChild(node_name)
