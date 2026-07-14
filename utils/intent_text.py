"""
utils/intent_text.py
-----------------------
INTENT text <-> 3-field form conversion.

The backend hands us ONE string with three headed sections. We split it into
three editable fields and MUST rebuild the exact same "Problem: / Objective:
/ Additional Context:" shape before sending it into the search graph -- its
prompts assume that literal structure.
"""

import re

_SECTION_PATTERN = re.compile(
    r"Problem:\s*(.*?)\n\s*Objective:\s*(.*?)\n\s*Additional Context:\s*(.*)",
    re.S,
)


def split_intent_sections(text: str):
    m = _SECTION_PATTERN.search(text or "")
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    return (text or "").strip(), "", ""


def join_intent_sections(problem: str, objective: str, additional_context: str) -> str:
    ac = additional_context.strip() or "None specified."
    return (
        f"Problem:\n{problem.strip()}\n\n"
        f"Objective:\n{objective.strip()}\n\n"
        f"Additional Context:\n{ac}"
    )
