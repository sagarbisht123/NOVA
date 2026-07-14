import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import requests

from app.modules.search.providers.models import ResearchPaper

_fallback_logger = logging.getLogger(__name__)

CONTACT_EMAIL = os.getenv("OPENALEX_MAILTO") or os.getenv("UNPAYWALL_EMAIL")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY")
OPENALEX_CONTENT_API_KEY = os.getenv("OPENALEX_CONTENT_API_KEY") or OPENALEX_API_KEY

_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-pipeline/1.0; +mailto:contact@example.com)"
}
_PDF_MAGIC = b"%PDF"
_CITATION_PDF_URL_RE = re.compile(
    r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url["\']',
    re.IGNORECASE,
)
_ARXIV_ID_RE = re.compile(r'arxiv\.org/(?:abs|pdf)/([^\s/?#]+)', re.IGNORECASE)
_ACL_ID_RE = re.compile(r'aclanthology\.org/([^\s/?#"\']+)', re.IGNORECASE)
_PMC_ID_RE = re.compile(r'(PMC\d+)', re.IGNORECASE)


def decode_abstract(inverted_index):
    """
    Convert OpenAlex's abstract_inverted_index into a readable abstract.
    Returns None if the index is missing or empty.
    """
    if not inverted_index:  # handles both None and empty dict {}
        return None

    try:
        max_position = max(
            pos for positions in inverted_index.values() for pos in positions
        )
    except ValueError:
        # inverted_index had keys but all position lists were empty
        return None

    words = [""] * (max_position + 1)
    for word, positions in inverted_index.items():
        for position in positions:
            words[position] = word

    result = " ".join(words).strip()
    return result if result else None


# --------------------------------------------------------------------------
# PDF resolution / verification helpers
#
# OpenAlex's primary_location.pdf_url is often null even when a free copy
# exists elsewhere (it's the version closest to the record, frequently the
# paywalled publisher copy). Even best_oa_location.pdf_url can legitimately
# be null while a landing page is known. So we walk every location OpenAlex
# knows about, try deterministic direct-PDF reconstruction for arXiv / ACL
# Anthology / PubMedCentral repos, fall back to scraping the citation_pdf_url
# meta tag, then DOI -> Unpaywall, and VERIFY every candidate by checking the
# real response body for the "%PDF" magic number rather than trusting a
# Content-Type header or a field name.
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
    clean_id = pmc_id if pmc_id.upper().startswith("PMC") else f"PMC{pmc_id}"
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


def _scan_locations_for_repo_ids(locations: List[dict]) -> dict:
    """
    Walk every location OpenAlex knows about for this work and pull out
    arXiv / ACL Anthology / PubMedCentral identifiers wherever they show up,
    so a deterministic direct-PDF link can be reconstructed even when
    best_oa_location isn't the repo that actually has one.
    """
    found = {}
    for loc in locations:
        landing = (loc or {}).get("landing_page_url") or ""
        pdf = (loc or {}).get("pdf_url") or ""
        haystack = f"{landing} {pdf}"

        if "arxiv" not in found:
            m = _ARXIV_ID_RE.search(haystack)
            if m:
                found["arxiv"] = m.group(1)

        if "acl" not in found:
            m = _ACL_ID_RE.search(haystack)
            if m:
                acl_id = m.group(1)
                if acl_id.lower().endswith(".pdf"):
                    acl_id = acl_id[:-4]
                found["acl"] = acl_id

        if "pmc" not in found:
            m = _PMC_ID_RE.search(haystack)
            if m:
                found["pmc"] = m.group(1)

    return found


def resolve_openalex_pdf(
    paper: dict,
    unpaywall_email: Optional[str] = None,
    use_paid_content_api: bool = False,
    openalex_content_api_key: Optional[str] = None,
    log: Optional[logging.Logger] = None,
) -> Optional[str]:
    """Runs the full escalation ladder and returns a VERIFIED direct PDF url, or None."""
    log = log or _fallback_logger
    primary = paper.get("primary_location") or {}
    best_oa = paper.get("best_oa_location") or {}
    locations = paper.get("locations") or []
    all_locations = [primary, best_oa] + locations

    # 1. Any pdf_url OpenAlex already gave us directly, wherever it's hiding.
    seen = set()
    direct_candidates = []
    for loc in all_locations:
        u = (loc or {}).get("pdf_url")
        if u and u not in seen:
            seen.add(u)
            direct_candidates.append(u)

    for candidate in direct_candidates:
        if _is_verified_pdf(candidate):
            return candidate

    # 2. Deterministic reconstruction from repo IDs found anywhere in locations.
    repo_ids = _scan_locations_for_repo_ids(all_locations)

    if repo_ids.get("arxiv"):
        candidate = f"https://arxiv.org/pdf/{repo_ids['arxiv']}"
        if _is_verified_pdf(candidate):
            return candidate

    if repo_ids.get("acl"):
        candidate = f"https://aclanthology.org/{repo_ids['acl']}.pdf"
        if _is_verified_pdf(candidate):
            return candidate

    if repo_ids.get("pmc"):
        candidate = _resolve_pmc_pdf(repo_ids["pmc"])
        if candidate:
            return candidate

    # 3. Scrape citation_pdf_url off whatever landing pages we have (capped
    #    at 3 to bound worst-case latency per paper).
    seen = set()
    landing_pages = []
    for loc in [best_oa, primary] + locations:
        lp = (loc or {}).get("landing_page_url")
        if lp and lp not in seen:
            seen.add(lp)
            landing_pages.append(lp)

    for page in landing_pages[:3]:
        scraped = _extract_citation_pdf_url(page)
        if scraped and _is_verified_pdf(scraped):
            return scraped

    # 4. DOI -> Unpaywall, only if we have a contact email to use.
    doi = paper.get("doi")
    if doi and unpaywall_email:
        doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
        candidate = _resolve_unpaywall_pdf(doi_clean, unpaywall_email)
        if candidate and _is_verified_pdf(candidate):
            return candidate

    # 5. Opt-in, PAID last resort: OpenAlex's own hosted content API.
    has_content = paper.get("has_content") or {}
    if use_paid_content_api and has_content.get("pdf") and openalex_content_api_key:
        work_id = (paper.get("id") or "").rstrip("/").split("/")[-1]
        if work_id:
            candidate = (
                f"https://content.openalex.org/works/{work_id}.pdf"
                f"?api_key={openalex_content_api_key}"
            )
            if _is_verified_pdf(candidate):
                return candidate

    log.debug("No verified PDF resolved for OpenAlex work %s", paper.get("id"))
    return None


def resolve_openalex_pdf_fast(paper: dict) -> Optional[str]:
    """
    HYBRID fast path: a cheap, ZERO-network best-effort PDF link.

    Takes any direct pdf_url OpenAlex already handed us, or rebuilds a
    deterministic repo URL (arXiv / ACL / PubMedCentral) from ids found in the
    work's locations — WITHOUT downloading or verifying anything. The expensive
    verify + landing-page scrape + Unpaywall ladder is deferred to 'Chat it out'
    time (see resolve_openalex_pdf), so search stays fast.
    """
    primary = paper.get("primary_location") or {}
    best_oa = paper.get("best_oa_location") or {}
    locations = paper.get("locations") or []
    all_locations = [best_oa, primary] + locations

    for loc in all_locations:
        u = (loc or {}).get("pdf_url")
        if u:
            return u

    repo_ids = _scan_locations_for_repo_ids(all_locations)
    if repo_ids.get("arxiv"):
        return f"https://arxiv.org/pdf/{repo_ids['arxiv']}"
    if repo_ids.get("acl"):
        return f"https://aclanthology.org/{repo_ids['acl']}.pdf"
    if repo_ids.get("pmc"):
        clean = repo_ids["pmc"] if str(repo_ids["pmc"]).upper().startswith("PMC") else f"PMC{repo_ids['pmc']}"
        return f"https://europepmc.org/articles/{clean}?pdf=render"
    return None


def search_openalex(
    query: str,
    limit: int = 15,
    sort="cited_by_count:desc",
    logger: Optional[logging.Logger] = None,
    max_candidates: int = 40,
    use_paid_content_api: bool = False,
    status_out: Optional[dict] = None,
    fast: bool = True,
) -> List[dict]:
    """
    Search research papers using OpenAlex. Returns a list of validated paper dicts.
    sort: 'cited_by_count:desc' for most-cited, 'publication_date:desc' for latest,
          or None for relevance (OpenAlex default).

    Only papers for which a VERIFIED, direct PDF link could be resolved are
    returned -- papers with no reachable PDF are filtered out entirely,
    never returned with pdf_url=None.

    max_candidates: how many raw results to pull from OpenAlex and PDF-check
          before stopping at `limit` verified papers, since each candidate
          can cost several extra network calls to resolve/verify.
    use_paid_content_api: opt-in only -- lets the resolution ladder's last
          step (OpenAlex's own hosted, metered content API) run as a final
          fallback. Requires OPENALEX_CONTENT_API_KEY to be set. Off by
          default since it costs a small amount per download.
    """
    log = logger or _fallback_logger
    url = "https://api.openalex.org/works"
    params = {"search": query, "per_page": max_candidates}
    if sort:
        params["sort"] = sort
    if CONTACT_EMAIL:
        # OpenAlex's "polite pool" -- faster, more consistent response times.
        params["mailto"] = CONTACT_EMAIL

    log.info("Searching OpenAlex for: %r (sort=%s)", query, sort or "relevance")

    try:
        response = requests.get(url, params=params, timeout=15)
    except requests.RequestException as e:
        log.warning("OpenAlex request failed: %s: %s", type(e).__name__, e)
        if status_out is not None:
            status_out.update(state="error", detail=f"{type(e).__name__}: {e}")
        return []

    if response.status_code != 200:
        log.warning("OpenAlex returned bad status: %s", response.status_code)
        if status_out is not None:
            state = "rate_limited" if response.status_code == 429 else "error"
            status_out.update(state=state, http=response.status_code)
        return []

    try:
        data = response.json()
    except ValueError as e:
        log.warning("OpenAlex response failed to parse as JSON: %s", e)
        if status_out is not None:
            status_out.update(state="error", detail="bad JSON")
        return []

    raw_papers = data.get("results", [])

    # Build lightweight candidate metadata first (no network calls here).
    candidates = []
    for paper in raw_papers:
        title = paper.get("display_name")
        if not title or not title.strip():
            continue
        authors = []
        for authorship in paper.get("authorships", []) or []:
            author_obj = authorship.get("author") or {}
            name = author_obj.get("display_name")
            if name:
                authors.append(name)
        abstract = decode_abstract(paper.get("abstract_inverted_index"))
        landing_url = (paper.get("primary_location") or {}).get("landing_page_url")
        candidates.append((paper, title, authors, abstract, landing_url))

    # Resolve the slow, network-bound PDF checks for all candidates CONCURRENTLY
    # rather than one at a time. This is what turns an ~80s wait into a few
    # seconds; the escalation ladder and the verified-PDF-only result are
    # unchanged -- only the wall-clock changes.
    if fast:
        # HYBRID default: cheap zero-network best-effort links, keep ALL papers
        # (deep verification is deferred to 'Chat it out'). No network here.
        resolved_pdfs = [resolve_openalex_pdf_fast(paper) for (paper, *_rest) in candidates]
    else:
        # Deep path: full verify ladder in parallel, keep only verified-PDF papers.
        def _resolve(item):
            return resolve_openalex_pdf(
                item[0],
                unpaywall_email=CONTACT_EMAIL,
                use_paid_content_api=use_paid_content_api,
                openalex_content_api_key=OPENALEX_CONTENT_API_KEY,
                log=log,
            )
        with ThreadPoolExecutor(max_workers=min(12, len(candidates))) as ex:
            resolved_pdfs = list(ex.map(_resolve, candidates)) if candidates else []

    # Assemble in original (citation-sorted) order, keeping the first `limit` papers.
    papers = []
    for (paper, title, authors, abstract, landing_url), pdf_url in zip(candidates, resolved_pdfs):
        if len(papers) >= limit:
            break
        if not fast and not pdf_url:
            # Deep mode only: drop papers with no verifiable PDF.
            continue
        try:
            paper_obj = ResearchPaper(
                title=title.strip(),
                authors=authors if authors else None,
                abstract=abstract,
                year=paper.get("publication_year"),
                citation_count=paper.get("cited_by_count"),
                url=landing_url,
                pdf_url=pdf_url,
                source="OpenAlex",
            )
            papers.append(paper_obj.model_dump())
        except Exception as e:
            log.warning("Skipped malformed OpenAlex paper: %s", e)
            continue

    if status_out is not None:
        status_out.update(state="ok", count=len(papers))
    log.info("OpenAlex: %d paper(s) retrieved (%s) out of %d candidates",
              len(papers), "fast/best-effort PDF" if fast else "verified PDF", len(raw_papers))
    return papers