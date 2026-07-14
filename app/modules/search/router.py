from fastapi import APIRouter, HTTPException

from app.modules.search.jobs import get_job
from app.modules.search.schemas import SearchStatusResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/status/{job_id}", response_model=SearchStatusResponse)
def search_status(job_id: str):
    """Poll this until status is 'done' (or 'error'). On 'done',
    clustered_papers is the final payload the UI renders."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id.")
    return SearchStatusResponse(**job)
