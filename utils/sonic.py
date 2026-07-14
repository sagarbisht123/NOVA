"""
utils/sonic.py
-----------------
SONIC — the assistant caricature, drawn as an inline SVG (no external file,
renders under Streamlit's strict CSP). A friendly bespectacled researcher:
brown quiff, black glasses, big smile, white shirt + navy striped tie,
suspenders. Used big on the welcome screen and small as the chat avatar.
"""

import base64

import streamlit as st

SONIC_SVG = """
<svg viewBox="0 0 240 280" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="SONIC the research assistant">
  <defs>
    <linearGradient id="s-card" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2b2168"/><stop offset="1" stop-color="#141a2e"/>
    </linearGradient>
    <linearGradient id="s-skin" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f8d0a8"/><stop offset="1" stop-color="#e7ad7f"/>
    </linearGradient>
    <linearGradient id="s-hair" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#7d5636"/><stop offset="1" stop-color="#4e3421"/>
    </linearGradient>
    <linearGradient id="s-tie" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3a4f8a"/><stop offset="1" stop-color="#26325c"/>
    </linearGradient>
    <clipPath id="s-clip"><rect x="8" y="8" width="224" height="264" rx="34"/></clipPath>
    <clipPath id="s-tieclip"><path d="M115 232 L125 232 L131 279 L120 289 L109 279 Z"/></clipPath>
  </defs>
  <rect x="8" y="8" width="224" height="264" rx="34" fill="url(#s-card)"/>
  <g clip-path="url(#s-clip)">
    <!-- shirt -->
    <path d="M18 280 C22 226 64 202 120 202 C176 202 218 226 222 280 Z" fill="#eef2f8"/>
    <!-- suspenders -->
    <path d="M80 205 L96 205 L112 280 L96 280 Z" fill="#b45540"/>
    <path d="M160 205 L144 205 L128 280 L144 280 Z" fill="#b45540"/>
    <!-- collar -->
    <path d="M104 200 L120 217 L98 226 Z" fill="#ffffff"/>
    <path d="M136 200 L120 217 L142 226 Z" fill="#ffffff"/>
    <!-- tie -->
    <path d="M120 214 L110 223 L120 234 L130 223 Z" fill="url(#s-tie)"/>
    <path d="M115 232 L125 232 L131 279 L120 289 L109 279 Z" fill="url(#s-tie)"/>
    <g clip-path="url(#s-tieclip)" stroke="#5a70b4" stroke-width="4" opacity="0.8">
      <line x1="104" y1="250" x2="136" y2="218"/>
      <line x1="104" y1="264" x2="140" y2="228"/>
      <line x1="108" y1="280" x2="140" y2="248"/>
    </g>
    <!-- neck -->
    <rect x="105" y="156" width="30" height="48" rx="14" fill="#e6ad7f"/>
    <!-- ears -->
    <circle cx="66" cy="118" r="11" fill="url(#s-skin)"/>
    <circle cx="174" cy="118" r="11" fill="url(#s-skin)"/>
    <!-- head -->
    <ellipse cx="120" cy="112" rx="56" ry="62" fill="url(#s-skin)"/>
    <!-- cheeks -->
    <ellipse cx="84" cy="140" rx="10" ry="6" fill="#ef9f8f" opacity="0.35"/>
    <ellipse cx="156" cy="140" rx="10" ry="6" fill="#ef9f8f" opacity="0.35"/>
    <!-- hair -->
    <path d="M66 110 C62 54 92 38 120 38 C150 38 178 54 173 110
             C167 92 155 84 140 82 C151 74 154 62 154 62
             C141 76 129 79 120 79 C110 79 101 74 94 64
             C96 74 99 82 99 82 C85 84 73 92 66 110 Z" fill="url(#s-hair)"/>
    <!-- eyebrows -->
    <path d="M83 97 Q97 90 110 97" stroke="#5c3f28" stroke-width="4" fill="none" stroke-linecap="round"/>
    <path d="M130 97 Q143 90 157 97" stroke="#5c3f28" stroke-width="4" fill="none" stroke-linecap="round"/>
    <!-- eyes -->
    <ellipse cx="101" cy="117" rx="9" ry="10" fill="#ffffff"/>
    <ellipse cx="139" cy="117" rx="9" ry="10" fill="#ffffff"/>
    <circle cx="103" cy="118" r="5" fill="#2a2438"/>
    <circle cx="137" cy="118" r="5" fill="#2a2438"/>
    <circle cx="105" cy="116" r="1.6" fill="#ffffff"/>
    <circle cx="139" cy="116" r="1.6" fill="#ffffff"/>
    <!-- nose -->
    <path d="M115 145 Q120 149 125 145" stroke="#d99b6f" stroke-width="3" fill="none" stroke-linecap="round"/>
    <!-- smile -->
    <path d="M97 156 Q120 186 143 156 Q120 172 97 156 Z" fill="#6d3630"/>
    <path d="M101 157 Q120 170 139 157 Q120 165 101 157 Z" fill="#ffffff"/>
    <!-- glasses -->
    <g fill="none" stroke="#171b28" stroke-width="5">
      <rect x="82" y="101" width="38" height="32" rx="13" fill="rgba(255,255,255,0.10)"/>
      <rect x="120" y="101" width="38" height="32" rx="13" fill="rgba(255,255,255,0.10)"/>
      <line x1="118" y1="115" x2="122" y2="115"/>
      <line x1="82" y1="110" x2="67" y2="113"/>
      <line x1="158" y1="110" x2="173" y2="113"/>
    </g>
  </g>
</svg>
"""

SONIC_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(SONIC_SVG.encode("utf-8")).decode("ascii")


def sonic_says(message: str):
    st.markdown(
        f"""
<div class="sonic-row">
  <div class="sonic-avatar"><img src="{SONIC_DATA_URI}" alt="SONIC"/></div>
  <div class="sonic-bubble"><div class="sonic-name">SONIC</div>{message}</div>
</div>
""",
        unsafe_allow_html=True,
    )
