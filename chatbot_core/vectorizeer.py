"""
vectorize.py
------------
Builds (or loads, if already built) a persisted vectorstore for a single research
paper PDF. Designed to be imported by qa.py, but can also be run standalone:

    python vectorize.py /path/to/paper.pdf

Chunking strategy:
  1. Split the paper by detected section headers ("1 Introduction", "3.2 Inference
     with V-RAG", etc.) so each chunk is a real semantic unit, not an arbitrary
     page cut.
  2. Within each section, protect table-like blocks (lines dense with numbers) so
     they stay intact as their own chunk instead of getting sliced by the
     recursive splitter.
  3. Any remaining oversized prose is split with RecursiveCharacterTextSplitter
     (paragraph -> sentence -> word fallback separators).
  4. If no section headers are detected at all (unusual paper formatting), falls
     back to page-wise chunks with a small overlap so nothing is silently lost.

Install once:
    pip install --break-system-packages pymupdf langchain langchain-core \
        langchain-text-splitters langchain-chroma langchain-community \
        sentence-transformers chromadb

Embedding model: BAAI/bge-base-en-v1.5 (local, ~440MB, runs fine on CPU or a
sliver of GPU -- no API key, no rate limits, no VRAM worries).
"""

import os
import re
import sys
import hashlib

import fitz  # PyMuPDF
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

# Matches headers like "1 Introduction", "3.2 Inference with V-RAG", "6 Conclusion"
HEADER_PATTERN = re.compile(r'\n(\d{1,2}(?:\.\d{1,2})?\s+[A-Z][A-Za-z][^\n]{2,60})(?=\n)')

# A line "looks like a table row" if enough of its tokens are numeric.
NUMERIC_TOKEN = re.compile(r'^-?\d+\.\d+$|^\d+$')
PAGE_OVERLAP_CHARS = 200
MAX_CHUNK_CHARS = 900


def get_pdf_hash(pdf_path: str) -> str:
    """Short content hash -> stable, unique persist directory per PDF."""
    with open(pdf_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()[:12]


def extract_sections(pdf_path: str):
    """Return a list of {title, text, page} dicts, one per detected section.

    Falls back to page-wise chunks (with overlap) if no section headers are
    detected, so unusual paper formats still produce usable chunks.
    """
    doc = fitz.open(pdf_path)
    full_text = ""
    page_map = []  # (char_start, char_end, page_number) per page
    for i, page in enumerate(doc):
        t = page.get_text()
        page_map.append((len(full_text), len(full_text) + len(t), i + 1))
        full_text += t

    matches = list(HEADER_PATTERN.finditer(full_text))
    sections = []

    if matches:
        # Preamble before the first header = title/authors/abstract
        if matches[0].start() > 0:
            preamble = full_text[:matches[0].start()].strip()
            if preamble:
                page_no = next(p for s, e, p in page_map if s <= 0 < e)
                sections.append({"title": "Abstract / Preamble", "text": preamble, "page": page_no})

        for idx, m in enumerate(matches):
            start = m.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
            title = m.group(1).strip()
            body = full_text[m.end():end].strip()
            if body:
                page_no = next(p for s, e, p in page_map if s <= start < e)
                sections.append({"title": title, "text": body, "page": page_no})
    else:
        print("[vectorize] No section headers detected -- falling back to page-wise chunking.")
        page_texts = [page.get_text() for page in doc]
        for i, t in enumerate(page_texts):
            prefix = page_texts[i - 1][-PAGE_OVERLAP_CHARS:] if i > 0 else ""
            sections.append({"title": f"Page {i + 1}", "text": prefix + t, "page": i + 1})

    return sections


def _looks_tabular(line: str) -> bool:
    tokens = line.split()
    if len(tokens) < 3:
        return False
    numeric = sum(1 for t in tokens if NUMERIC_TOKEN.match(t))
    return (numeric / len(tokens)) >= 0.4


def _split_protecting_tables(text: str, splitter: RecursiveCharacterTextSplitter):
    """Group consecutive table-like lines into their own block; split the rest
    normally. Returns a list of (is_table: bool, chunk_text: str)."""
    lines = text.split("\n")
    blocks = []
    buf, buf_is_table = [], None

    for line in lines:
        is_table = _looks_tabular(line)
        if buf_is_table is None:
            buf_is_table = is_table
        if is_table == buf_is_table:
            buf.append(line)
        else:
            blocks.append((buf_is_table, "\n".join(buf)))
            buf, buf_is_table = [line], is_table
    if buf:
        blocks.append((buf_is_table, "\n".join(buf)))

    chunks = []
    for is_table, block_text in blocks:
        block_text = block_text.strip()
        if not block_text:
            continue
        if is_table or len(block_text) <= MAX_CHUNK_CHARS:
            chunks.append((is_table, block_text))
        else:
            for piece in splitter.split_text(block_text):
                chunks.append((False, piece))
    return chunks


def get_embeddings():
    """Local, lightweight embedding model -- no API key, no rate limits."""
    from langchain_community.embeddings import HuggingFaceBgeEmbeddings
    return HuggingFaceBgeEmbeddings(
        model_name="BAAI/bge-base-en-v1.5",
        model_kwargs={"device": "cpu"},  # set to "cuda" if your GPU has headroom to spare
        encode_kwargs={"normalize_embeddings": True},
    )


def build_vectorstore(pdf_path: str, persist_root: str = "./vectorstores", force_rebuild: bool = False):
    """Build a new vectorstore for pdf_path, or load the existing one if it was
    already built for this exact file."""
    pdf_hash = get_pdf_hash(pdf_path)
    persist_dir = os.path.join(persist_root, pdf_hash)
    embeddings = get_embeddings()

    if os.path.isdir(persist_dir) and os.listdir(persist_dir) and not force_rebuild:
        print(f"[vectorize] Existing vectorstore found at {persist_dir} -- loading it.")
        return Chroma(persist_directory=persist_dir, embedding_function=embeddings)

    print(f"[vectorize] Building vectorstore for: {pdf_path}")
    sections = extract_sections(pdf_path)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=700, chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " "],
    )

    docs = []
    for sec in sections:
        for is_table, piece_text in _split_protecting_tables(sec["text"], splitter):
            docs.append(Document(
                page_content=piece_text,
                metadata={
                    "section": sec["title"],
                    "page": sec["page"],
                    "type": "table" if is_table else "text",
                    "source": os.path.basename(pdf_path),
                },
            ))

    if not docs:
        raise ValueError(
            f"No extractable text found in {pdf_path}. This PDF may be scanned "
            "(image-only) rather than a native text PDF -- it needs OCR first."
        )

    print(f"[vectorize] {len(docs)} chunks created across {len(sections)} sections.")
    os.makedirs(persist_dir, exist_ok=True)
    vectorstore = Chroma.from_documents(docs, embeddings, persist_directory=persist_dir)
    print(f"[vectorize] Saved to {persist_dir}")
    return vectorstore


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python vectorize.py /path/to/paper.pdf")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        sys.exit(1)

    build_vectorstore(path)