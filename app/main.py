import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.modules.intent.router import router as intent_router
from app.modules.search.router import router as search_router

# Root config for anything logged outside a specific run (server
# startup/shutdown, module-level fallback loggers used when a provider
# function is called standalone rather than from a graph node). Per-request
# logs go through app.core.logging_config.get_node_logger instead, which
# writes its own logs/{run_id}.log and does not propagate up to this root
# handler — so this does not duplicate those.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(title="Research Assistant Pipeline API")

# Dev-friendly CORS. Lock this down to your actual frontend origin(s) before
# deploying anywhere real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(intent_router)
app.include_router(search_router)
