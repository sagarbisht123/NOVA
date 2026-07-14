from typing import Literal

from pydantic import BaseModel


class IntentStartRequest(BaseModel):
    user_query: str


class IntentStartResponse(BaseModel):
    thread_id: str
    polished_research_intent: str
    instruction: str


class IntentResumeRequest(BaseModel):
    thread_id: str
    edited_intent: str


class IntentResumeResponse(BaseModel):
    thread_id: str
    human_verified_intent: str
    job_id: str
    status: Literal["running"]
