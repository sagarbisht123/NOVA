# ✦ NOVA — Research, guided by SONIC

NOVA is a single Streamlit app that unpacks and connects two existing projects,
**with their logic unchanged**:

- **`app/`** — the research pipeline (the former `structured_agent`'s `app/`
  package): an **intent agent** that frames a raw idea into
  Problem / Objective / Additional Context, and a **search agent** that fetches
  papers (arXiv + Semantic Scholar + OpenAlex), reranks them with SPECTER, and
  clusters them by approach.
- **`chatbot_core/`** — the single-PDF Q&A chatbot (`Qa.py` + `vectorizeer.py`),
  copied verbatim.

**NOVA** is the product. **SONIC** is the assistant persona that talks you
through it.

## The flow

```
your raw research idea
   → SONIC: "lemme juss refine it"      (INTENT agent frames it)
   → you review / edit the framing
   → SONIC: "on it…"                    (SEARCH agent fetches → rerank → cluster)
   → SONIC: "these are the best matches" (clean paper thumbnails, grouped by approach)
   → "💬 Chat it out" on any paper       (its PDF is downloaded, vectorized, and
                                          you Q&A over it — powered by chatbot_core)
```

Each paper thumbnail shows **title, authors, and links only** (no abstract):
a **📄 Paper** button (source page), a **⬇ PDF** button, and a **💬 Chat it out**
button. Clicking *Chat it out* downloads that paper's PDF, runs it through
`vectorizeer.build_vectorstore`, and opens a grounded Q&A chat over it using
`Qa.py`'s retriever + LLM chain.

The chatbot's embedding + reranker models are **pre-loaded at startup** (behind
the "Waking up SONIC…" splash) so the first *Chat it out* click is snappy.

## Layout

```
NOVA/
├── nova_app.py          # the whole Streamlit UI + wiring (this is the only new code)
├── app/                 # the research agent — copied UNCHANGED from structured_agent/app
│   ├── core/logging_config.py     # per-query logs -> NOVA/logs/{run_id}.log
│   └── modules/{intent,search}/   # the two LangGraph agents + providers
├── chatbot_core/        # the single-PDF Q&A chatbot — copied UNCHANGED
│   ├── Qa.py
│   └── vectorizeer.py
├── .streamlit/config.toml         # dark NOVA theme
├── .env                 # GROQ / TAVILY / SEMANTIC_SCHOLAR keys (merged from both projects)
├── requirements.txt
├── run.sh
├── logs/                # one log file per research query
├── downloads/           # PDFs pulled for "Chat it out"
└── vectorstores/        # per-PDF Chroma stores (cached by content hash)
```

`nova_app.py` is UI + orchestration only — it imports the agents' compiled
graphs and the chatbot's functions and drives them. It changes no agent or
chatbot logic.

## Run

```bash
./run.sh
# or explicitly:
/home/sagar/workspace/Langchain/Veritus_project/chatbot/QA/bin/python -m streamlit run nova_app.py
```

Then open the URL Streamlit prints (default http://localhost:8501).

> The combined environment is the chatbot's `QA/` virtualenv, augmented with
> `streamlit` + `langchain-tavily` (a purely additive install — the shared
> langchain/langgraph/torch versions were already identical between the two
> projects). To rebuild from scratch in a fresh venv: `pip install -r requirements.txt`.

## Notes / limitations

- Only papers with a resolvable open-access PDF can be chatted with; the others
  show a disabled *Chat it out* button.
- The intent graph's checkpointer and everything else live in the single
  Streamlit process's memory — fine for one researcher at a time.
- First-ever startup downloads the two local models (BAAI/bge-base + bge-reranker)
  if they aren't already in the HuggingFace cache; subsequent starts are fast.
