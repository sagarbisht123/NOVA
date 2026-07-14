"""
qa.py
-----
Interactive Q&A over a single research paper. Handles vectorization
automatically -- just point it at a PDF:

    python qa.py /path/to/paper.pdf

First run on a given PDF builds the vectorstore (may take a moment while the
embedding model loads); every run after that loads the cached vectorstore
instantly since it's keyed by the PDF's content hash.

Requires a Groq API key. Create a .env file in this same directory containing:

    GROQ_API_KEY=your-key-here

Install once (on top of vectorize.py's requirements):
    pip install --break-system-packages langchain langchain-community \
        langchain-classic langchain-groq python-dotenv

Note: LangChain 1.0+ split ContextualCompressionRetriever and
CrossEncoderReranker out of the core `langchain` package into the new
`langchain-classic` package -- that's why langchain-classic is required above.

Swap LLM providers: replace get_llm() below with e.g. ChatOpenAI or
ChatAnthropic if you'd rather not use Groq.
"""

import os
import sys

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever

from vectorizeer import build_vectorstore

load_dotenv()  # reads GROQ_API_KEY from a .env file in the current directory

QA_SYSTEM_PROMPT = """You are a research assistant helping someone deeply understand a specific paper.
Treat every question as a chance to teach, not just retrieve -- they want both
the facts and why those facts matter.

Ground every answer strictly in the excerpts below. Do not use outside knowledge,
and do not fill gaps with what a similar paper would typically say. If the
excerpts don't contain the answer, say so plainly rather than guessing.

When you answer:
- Be comprehensive: explain the relevant method, result, or claim fully rather
  than a one-line summary. If the question touches a mechanism (an algorithm, a
  fine-tuning task, an experimental setup), walk through how it actually works,
  not just what it's called.
- Surface significance: don't just report what the paper found -- explain why
  it matters. What problem does it solve, what breaks without it, how does it
  compare to prior approaches, what does it enable going forward.
- Stay accessible: write for someone smart but not necessarily a specialist in
  this exact subfield. Define acronyms and technical terms the first time you
  use them, and prefer plain language wherever it loses no precision.
- Cite as you go: every claim should be traceable to a page number from the
  tagged excerpts below. Weave citations naturally into the explanation rather
  than listing them at the end.
- Stay focused: comprehensive isn't the same as padded. Cut anything that
  doesn't help the reader actually understand the paper better.

EXCERPTS:
{context}
"""


def get_llm():
    api_key = os.environ.get("SECOND_GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY not found. Add it to a .env file in this directory "
            "(GROQ_API_KEY=your-key-here) -- load_dotenv() picks it up automatically."
        )
    return ChatGroq(model="llama-3.3-70b-versatile", temperature=0)


def get_retriever(vectorstore, k: int = 15, top_n: int = 5):
    """Retrieve k candidates by similarity, then rerank down to the best top_n
    with a small cross-encoder -- this is the single biggest accuracy lever
    on top of the chunking itself."""
    base_retriever = vectorstore.as_retriever(search_kwargs={"k": k})
    reranker_model = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-base")
    compressor = CrossEncoderReranker(model=reranker_model, top_n=top_n)
    return ContextualCompressionRetriever(base_compressor=compressor, base_retriever=base_retriever)


def format_docs(docs) -> str:
    parts = []
    for d in docs:
        tag = f"[Section: {d.metadata.get('section', '?')} | Page: {d.metadata.get('page', '?')}]"
        parts.append(f"{tag}\n{d.page_content}")
    return "\n\n---\n\n".join(parts)


def build_chain(llm):
    prompt = ChatPromptTemplate.from_messages([
        ("system", QA_SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history"),
        ("human", "{question}"),
    ])
    return prompt | llm


def main():
    if len(sys.argv) < 2:
        print("Usage: python qa.py /path/to/paper.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.isfile(pdf_path):
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    vectorstore = build_vectorstore(pdf_path)
    retriever = get_retriever(vectorstore)
    llm = get_llm()
    chain = build_chain(llm)

    chat_history = []
    print("\nReady. Ask questions about the paper (type 'exit' to quit).\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("exit", "quit"):
            break
        if not question:
            continue

        docs = retriever.invoke(question)
        context = format_docs(docs)

        print("\nAssistant: ", end="", flush=True)
        answer = ""
        for chunk in chain.stream({
            "question": question,
            "chat_history": chat_history,
            "context": context,
        }):
            token = chunk.content
            if token:
                print(token, end="", flush=True)
                answer += token
        print("\n")
 
        sources = sorted(set(f"p.{d.metadata.get('page')}" for d in docs), key=lambda s: s)
        print(f"[sources: {', '.join(sources)}]\n")
 
        chat_history.append(HumanMessage(content=question))
        chat_history.append(AIMessage(content=answer))


if __name__ == "__main__":
    main()