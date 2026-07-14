"""
utils/paths.py
-----------------
Filesystem + import-path wiring for NOVA.

This module MUST be the first `utils` import in nova_app.py. It does the
sys.path + chdir + .env side effects that make `import app...` (the agent
package) and `from vectorizeer import ...` / `from Qa import ...` (the
chatbot) resolve later -- so it has to run before any other `utils` module
that needs BASE, DOWNLOADS_DIR, VECTORSTORES_DIR, or PDF_UA. Once nova_app.py
imports this first, every other module gets the same path setup for free via
Python's module cache (re-importing `utils.paths` elsewhere just returns the
already-initialized module, it doesn't re-run this file).
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 0. PATHS  — make both sub-projects importable without touching their code
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent
os.chdir(BASE)                                   # ./vectorstores, ./downloads resolve under NOVA/
sys.path.insert(0, str(BASE))                    # `import app...`  (the agent package)
sys.path.insert(0, str(BASE / "chatbot_core"))   # `import Qa`, `from vectorizeer import ...`

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

DOWNLOADS_DIR = BASE / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
VECTORSTORES_DIR = BASE / "vectorstores"

PDF_UA = {"User-Agent": "Mozilla/5.0 (compatible; NOVA-research/1.0)"}
