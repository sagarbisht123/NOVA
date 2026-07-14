"""
utils/constants.py
---------------------
Static data shared across views: cluster accent colors, per-source badge
colors, and SONIC's motivational one-liners shown while a paper is being
vectorized.
"""

# Decorative, index-based — purely visual.
CLUSTER_ACCENTS = ["#7c5cff", "#22d3ee", "#f59e0b", "#ec4899", "#34d399", "#60a5fa", "#a78bfa", "#f472b6"]
SOURCE_COLORS = {"arXiv": "#e05263", "SemanticScholar": "#4c8bf5", "OpenAlex": "#2fa572"}

# SONIC's motivational one-liners, shown while a paper is being vectorized.
SONIC_QUOTES = [
    "Great research isn't found — it's framed. You already did the hard part.",
    "Every paper you read is a shortcut someone left for you. Let's decode this one.",
    "Reading fast is fine. Understanding deeply is the flex. Hang tight — I'm doing the deep part.",
    "The best researchers ask better questions, not more of them. Get yours ready.",
    "Curiosity is a muscle. You're clearly training it. Almost there…",
    "One good paper can change the whole direction. Could be this one.",
    "I'm turning every page into something you can just… ask. Two seconds.",
    "Knowledge compounds. This is you, quietly getting sharper.",
]
