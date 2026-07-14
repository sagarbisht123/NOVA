import logging
import xml.etree.ElementTree as ET
from typing import List, Optional

import requests

from app.modules.search.providers.models import ResearchPaper

_fallback_logger = logging.getLogger(__name__)


def search_arxiv(query: str, max_results: int = 10, logger: Optional[logging.Logger] = None) -> List[dict]:
    """
    Search papers from arXiv. Returns a list of validated paper dicts.
    """
    log = logger or _fallback_logger
    log.info("Searching arXiv for query: %s", query)
    query = query.replace(" ", "+")

    url = (
        f"https://export.arxiv.org/api/query?"
        f"search_query={query}"
        f"&start=0"
        f"&max_results={max_results}"
        f"&sortBy=relevance"
        f"&sortOrder=descending"
    )

    try:
        response = requests.get(url, timeout=15)
    except requests.RequestException as e:
        log.warning("arXiv request failed: %s: %s", type(e).__name__, e)
        return []

    if response.status_code != 200:
        log.warning("arXiv returned bad status: %s", response.status_code)
        return []

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        log.warning("arXiv response failed to parse as XML: %s", e)
        return []

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", namespace)

    papers = []

    for entry in entries:
        title_el = entry.find("atom:title", namespace)
        if title_el is None or not title_el.text or not title_el.text.strip():
            continue
        title = title_el.text.strip()

        summary_el = entry.find("atom:summary", namespace)
        abstract = summary_el.text.strip() if summary_el is not None and summary_el.text else None

        authors = []
        for author_el in entry.findall("atom:author", namespace):
            name_el = author_el.find("atom:name", namespace)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        published_el = entry.find("atom:published", namespace)
        year = None
        if published_el is not None and published_el.text and len(published_el.text) >= 4:
            try:
                year = int(published_el.text[:4])
            except ValueError:
                year = None

        pdf_link = None
        for link in entry.findall("atom:link", namespace):
            if link.attrib.get("title") == "pdf":
                pdf_link = link.attrib.get("href")
                break

        id_el = entry.find("atom:id", namespace)
        url_val = id_el.text.strip() if id_el is not None and id_el.text else None

        try:
            paper = ResearchPaper(
                title=title,
                authors=authors if authors else None,
                abstract=abstract,
                year=year,
                citation_count=None,  # arXiv never provides this
                url=url_val,
                pdf_url=pdf_link,
                source="arXiv",
            )
            papers.append(paper.model_dump())
        except Exception as e:
            log.warning("Skipped malformed arXiv entry: %s", e)
            continue  # skip malformed entries rather than crash the whole batch

    log.info("arXiv: %d paper(s) retrieved", len(papers))
    return papers
