"""
utils/papers.py
------------------
Paper record + PDF helpers: pulling a display value out of a per-source
dict, formatting an author line, and robustly resolving + downloading a real
PDF for a paper at "Chat it out" time.
"""

import hashlib

import requests

from utils.paths import DOWNLOADS_DIR, PDF_UA


def first_available(d):
    """First non-empty value in a {source: value} dict (record fields are
    dict-keyed by source after aggregation)."""
    if not isinstance(d, dict):
        return d or None
    for v in d.values():
        if v:
            return v
    return None


def author_line(authors, year):
    authors = authors or []
    if authors:
        shown = ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else "")
    else:
        shown = "Unknown authors"
    return f"{shown}  ·  {year or 'n.d.'}"


_PDF_MAGIC = b"%PDF"


def _download_if_pdf(url: str) -> "str | None":
    """Download url, but only keep it if the bytes are a real PDF (starts with
    %PDF) — a best-effort link that's actually an HTML landing page returns None
    so we can fall back to deep resolution. Cached by URL hash."""
    if not url:
        return None
    key = hashlib.md5(url.encode("utf-8")).hexdigest()[:16]
    dest = DOWNLOADS_DIR / f"{key}.pdf"
    if dest.is_file() and dest.stat().st_size > 0:
        return str(dest)
    try:
        resp = requests.get(url, headers=PDF_UA, timeout=45, stream=True, allow_redirects=True)
        if resp.status_code != 200:
            return None
        it = resp.iter_content(chunk_size=32768)
        first = next(it, b"")
        if not first.startswith(_PDF_MAGIC):
            return None  # HTML landing page or something else, not a PDF
        with open(dest, "wb") as f:
            f.write(first)
            for chunk in it:
                if chunk:
                    f.write(chunk)
        return str(dest) if dest.stat().st_size > 0 else None
    except requests.RequestException:
        return None


def resolve_and_download_pdf(record: dict) -> "str | None":
    """Robustly obtain a readable PDF for a paper at 'Chat it out' time (the
    HYBRID deep step). Search only stored a cheap best-effort link; here we:
       1) try each best-effort pdf link directly (keep it only if it's a real PDF);
       2) if those are landing pages / dead, scrape the citation_pdf_url meta tag
          off them and off the paper's source page(s), then download + verify.
    Returns a local path, or None if nothing yields real PDF bytes."""
    from app.modules.search.providers.semantic_scholar import _extract_citation_pdf_url

    pdf_candidates = [v for v in (record.get("pdf_url") or {}).values() if v]
    page_candidates = [v for v in (record.get("url") or {}).values() if v]

    for cand in pdf_candidates:                       # 1) direct best-effort PDFs
        path = _download_if_pdf(cand)
        if path:
            return path
    for page in pdf_candidates + page_candidates:     # 2) deep: scrape landing pages
        scraped = _extract_citation_pdf_url(page)
        if scraped:
            path = _download_if_pdf(scraped)
            if path:
                return path
    return None
