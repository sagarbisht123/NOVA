from typing import List, Literal, Optional

from pydantic import BaseModel


class SearchStatusResponse(BaseModel):
    job_id: str
    status: Literal["running", "done", "error"]
    clustered_papers: Optional[List[dict]] = None
    error: Optional[str] = None
