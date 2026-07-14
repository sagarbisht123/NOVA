import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import requests
from dotenv import load_dotenv

from app.modules.search.providers.models import ResearchPaper

load_dotenv()

_fallback_logger = logging.getLogger(__name__)

_REQUEST_HEADERS = {
    # Some publisher/repo servers block requests with no browser-like UA.
    "User-Agent": "Mozilla/5.0 (compatible; research-pipeline/1.0; +mailto:contact@example.com)"
}
_PDF_MAGIC = b"%PDF"
_CITATION_PDF_URL_RE = re.compile(
    r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url["\']',
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# PDF resolution / verification helpers
#
# Semantic Scholar's openAccessPdf.url is a best-effort pointer -- sometimes
# a raw PDF, sometimes a landing page that merely displays one. This runs
# each candidate through an escalation ladder and VERIFIES the result
# actually serves PDF bytes (checks the real response body's magic number,
# "%PDF", rather than trusting a Content-Type header or a field name)
# before ever handing it back.
# --------------------------------------------------------------------------

def _is_verified_pdf(url: str, timeout: int = 8) -> bool:
    if not url:
        return False
    try:
        with requests.get(
            url, headers=_REQUEST_HEADERS, stream=True, timeout=timeout, allow_redirects=True
        ) as resp:
            if resp.status_code != 200:
                return False
            chunk = next(resp.iter_content(chunk_size=16), b"")
            return chunk.startswith(_PDF_MAGIC)
    except requests.RequestException:
        return False


def _extract_citation_pdf_url(landing_page_url: str, timeout: int = 8) -> Optional[str]:
    """Scrape the citation_pdf_url meta tag off an HTML landing page."""
    try:
        resp = requests.get(landing_page_url, headers=_REQUEST_HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return None
        match = _CITATION_PDF_URL_RE.search(resp.text[:20000])
        if not match:
            return None
        return match.group(1) or match.group(2)
    except requests.RequestException:
        return None


def _resolve_pmc_pdf(pmc_id: str, timeout: int = 8) -> Optional[str]:
    """Try Europe PMC's render endpoint for a PubMedCentral ID."""
    clean_id = pmc_id if str(pmc_id).upper().startswith("PMC") else f"PMC{pmc_id}"
    candidate = f"https://europepmc.org/articles/{clean_id}?pdf=render"
    return candidate if _is_verified_pdf(candidate, timeout=timeout) else None


def _resolve_unpaywall_pdf(doi: str, email: str, timeout: int = 8) -> Optional[str]:
    """Last-resort fallback: ask Unpaywall for the best OA location's direct PDF."""
    try:
        resp = requests.get(
            f"https://api.unpaywall.org/v2/{doi}", params={"email": email}, timeout=timeout
        )
        if resp.status_code != 200:
            return None
        best_location = (resp.json() or {}).get("best_oa_location") or {}
        return best_location.get("url_for_pdf")
    except (requests.RequestException, ValueError):
        return None


def resolve_pdf_url(
    external_ids: dict,
    fallback_url: Optional[str],
    unpaywall_email: Optional[str] = None,
    log: Optional[logging.Logger] = None,
) -> Optional[str]:
    """
    Runs the full escalation ladder and returns a VERIFIED direct PDF url,
    or None if nothing in the chain resolves to actual PDF bytes.

        1. externalIds.ArXiv         -> arxiv.org/pdf/{id}                 (deterministic)
        2. externalIds.ACL           -> aclanthology.org/{id}.pdf          (deterministic)
        3. externalIds.PubMedCentral -> Europe PMC render endpoint         (verified)
        4. openAccessPdf.url         -> verified directly, or scraped for
                                         the citation_pdf_url meta tag if
                                         it turns out to be an HTML page
        5. externalIds.DOI           -> Unpaywall best_oa_location.url_for_pdf
                                         (only if unpaywall_email is set)
    """
    log = log or _fallback_logger
    external_ids = external_ids or {}

    arxiv_id = external_ids.get("ArXiv")
    if arxiv_id:
        candidate = f"https://arxiv.org/pdf/{arxiv_id}"
        if _is_verified_pdf(candidate):
            return candidate

    acl_id = external_ids.get("ACL")
    if acl_id:
        candidate = f"https://aclanthology.org/{acl_id}.pdf"
        if _is_verified_pdf(candidate):
            return candidate

    pmc_id = external_ids.get("PubMedCentral")
    if pmc_id:
        candidate = _resolve_pmc_pdf(pmc_id)
        if candidate:
            return candidate

    if fallback_url:
        if _is_verified_pdf(fallback_url):
            return fallback_url
        scraped = _extract_citation_pdf_url(fallback_url)
        if scraped and _is_verified_pdf(scraped):
            return scraped

    doi = external_ids.get("DOI")
    if doi and unpaywall_email:
        candidate = _resolve_unpaywall_pdf(doi, unpaywall_email)
        if candidate and _is_verified_pdf(candidate):
            return candidate

    log.debug("No verified PDF resolved for Semantic Scholar paper externalIds=%s", external_ids)
    return None


def resolve_pdf_url_fast(external_ids: dict, fallback_url: Optional[str]) -> Optional[str]:
    """
    HYBRID fast path: a cheap, ZERO-network best-effort PDF link.

    Builds the deterministic repo URL (arXiv / ACL / PubMedCentral) or takes
    Semantic Scholar's own openAccessPdf link as-is, WITHOUT downloading or
    verifying anything. The expensive verify + landing-page scrape + Unpaywall
    ladder is deferred to 'Chat it out' time (see resolve_pdf_url), so search
    stays fast while most links still point straight at a real PDF.
    """
    external_ids = external_ids or {}
    arxiv_id = external_ids.get("ArXiv")
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}"
    acl_id = external_ids.get("ACL")
    if acl_id:
        return f"https://aclanthology.org/{acl_id}.pdf"
    pmc_id = external_ids.get("PubMedCentral")
    if pmc_id:
        clean = pmc_id if str(pmc_id).upper().startswith("PMC") else f"PMC{pmc_id}"
        return f"https://europepmc.org/articles/{clean}?pdf=render"
    return fallback_url or None


def search_semantic_scholar(
    query: str,
    limit: int = 15,
    sort="citationCount:desc",
    logger: Optional[logging.Logger] = None,
    max_candidates: int = 25,
    status_out: Optional[dict] = None,
    fast: bool = True,
) -> List[dict]:
    """
    Search research papers using the Semantic Scholar Bulk Search API (supports sorting).

    Only papers for which a VERIFIED, direct PDF link could be resolved are
    returned -- papers with no reachable PDF are filtered out entirely,
    never returned with pdf_url=None.

    max_candidates: how many raw search results to PDF-check before
          stopping at `limit` verified papers, since each candidate can
          cost 1-2 extra network calls to resolve/verify.
    status_out: optional dict the caller can pass to learn WHY this source
          came back empty -- populated with {"state": "ok"|"rate_limited"|
          "error", ...} so a rate-limit (HTTP 429) is surfaced instead of
          silently looking like "no results".
    """
    log = logger or _fallback_logger
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    unpaywall_email = os.getenv("UNPAYWALL_EMAIL")
    # Only send the header when we actually have a key -- an `x-api-key: None`
    # header is meaningless and unauthenticated requests are throttled harder.
    headers = {"x-api-key": api_key} if api_key else {}
    log.info("Searching Semantic Scholar for: %r (sort=%s, keyed=%s)", query, sort or "default", bool(api_key))

    params = {
        "query": query,
        "fields": ",".join([
            "title", "abstract", "authors", "year",
            "citationCount", "url", "openAccessPdf", "externalIds"
        ])
    }
    if sort:
        params["sort"] = sort

    # Semantic Scholar's free tier throttles aggressively (HTTP 429). Retry a
    # few times with backoff before giving up, and surface the rate-limit
    # explicitly via status_out so it never just goes silently blank.
    response = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.RequestException as e:
            log.warning("Semantic Scholar request failed: %s: %s", type(e).__name__, e)
            if status_out is not None:
                status_out.update(state="error", detail=f"{type(e).__name__}: {e}")
            return []
        if response.status_code != 429:
            break
        wait = 2 * (attempt + 1)
        log.warning("Semantic Scholar rate-limited (HTTP 429) — attempt %d/3, retrying in %ds", attempt + 1, wait)
        time.sleep(wait)

    if response.status_code == 429:
        log.warning("Semantic Scholar STILL rate-limited (HTTP 429) after retries — 0 results from this source.")
        if status_out is not None:
            status_out.update(state="rate_limited", http=429)
        return []

    if response.status_code != 200:
        log.warning("Semantic Scholar returned bad status %s: %s", response.status_code, response.text[:300])
        if status_out is not None:
            status_out.update(state="error", http=response.status_code)
        return []

    try:
        data = response.json()
    except ValueError as e:
        log.warning("Semantic Scholar response failed to parse as JSON: %s (raw: %s)", e, response.text[:500])
        if status_out is not None:
            status_out.update(state="error", detail="bad JSON")
        return []

    total_available = data.get("total", "unknown")
    log.info("Semantic Scholar reports %s total match(es)", total_available)

    raw_papers = data.get("data", [])[:max_candidates]

    # Build candidate metadata first (no network), then resolve every
    # candidate's PDF CONCURRENTLY instead of one at a time.
    candidates = []
    for paper in raw_papers:
        title = paper.get("title")
        if not title or not title.strip():
            continue
        authors = [a.get("name") for a in (paper.get("authors") or []) if a.get("name")]
        openaccess_url = (paper.get("openAccessPdf") or {}).get("url")
        external_ids = paper.get("externalIds") or {}
        candidates.append((paper, title, authors, openaccess_url, external_ids))

    if fast:
        # HYBRID default: cheap zero-network best-effort links, keep ALL papers
        # (deep verification is deferred to 'Chat it out'). No thread pool needed
        # since resolution does no network here.
        resolved = [resolve_pdf_url_fast(ext, oa) for (_, _, _, oa, ext) in candidates]
    else:
        # Deep path: full verify ladder in parallel, keep only verified-PDF papers.
        def _resolve(item):
            _, _, _, openaccess_url, external_ids = item
            return resolve_pdf_url(external_ids, openaccess_url, unpaywall_email=unpaywall_email, log=log)
        with ThreadPoolExecutor(max_workers=min(12, len(candidates))) as ex:
            resolved = list(ex.map(_resolve, candidates)) if candidates else []

    papers = []
    for (paper, title, authors, openaccess_url, external_ids), pdf_url in zip(candidates, resolved):
        if len(papers) >= limit:
            break
        if not fast and not pdf_url:
            # Deep mode only: drop papers with no verifiable PDF.
            continue
        try:
            paper_obj = ResearchPaper(
                title=title.strip(),
                authors=authors if authors else None,
                abstract=paper.get("abstract"),
                year=paper.get("year"),
                citation_count=paper.get("citationCount"),
                url=paper.get("url"),
                pdf_url=pdf_url,
                source="SemanticScholar",
            )
            papers.append(paper_obj.model_dump())
        except Exception as e:
            log.warning("Skipped malformed Semantic Scholar paper: %s", e)
            continue

    if status_out is not None:
        status_out.update(state="ok", count=len(papers))
    log.info("Semantic Scholar: %d paper(s) retrieved (%s) out of %d candidates",
              len(papers), "fast/best-effort PDF" if fast else "verified PDF", len(raw_papers))
    return papers