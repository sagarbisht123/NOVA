from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ResearchPaper(BaseModel):
    title: str = Field(description="The title of the paper")
    authors: Optional[List[str]] = Field(description="The list of the authors of the paper mentioned.", default=None)
    abstract: Optional[str] = Field(description="The abstract or the summary of the mentioned research paper.", default=None)
    year: Optional[int] = Field(description="The year in which the paper was published, leave if not mentioned", default=None)
    citation_count: Optional[int] = Field(description="The citation count of the paper, leave if not mentioned", default=None)
    url: Optional[str] = Field(description="The url of the research given on the source", default=None)
    pdf_url: Optional[str] = Field(description="The pdf url of the research paper if mentioned", default=None)
    source: Literal["arXiv", "SemanticScholar", "OpenAlex"] = Field(
        description="The source from which it was extracted 'arXiv' , 'SemanticScholar' or 'OpenAlex'"
    )
