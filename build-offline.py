#!/usr/bin/env python3
"""
build-offline.py — Architise offline build script
Fetches Catamaran font (Google Fonts) and Dagre layout library (cdnjs),
inlines everything as base64 / inline JS, and writes index-offline.html —
a fully self-contained, 100% offline file.

Run once from the Archimate-engine directory:
    python3 build-offline.py

Requirements: Python 3.7+, requests library
    pip install requests          (or: pip3 install requests)
"""

import re, sys, base64, pathlib

try:
    import requests
except ImportError:
    print("Missing 'requests' — run:  pip install requests")
    sys.exit(1)

SRC  = pathlib.Path("index.html")
DEST = pathlib.Path("index-offline.html")

if not SRC.exists():
    print(f"Could not find {SRC}. Run this script from the Archimate-engine folder.")
    sys.exit(1)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Architise-build/1.0)"}

# ── Step 1: Catamaran font ─────────────────────────────────────────────────
WEIGHTS       = [400, 500, 600, 700, 800, 900]
FONT_CSS_URL  = (
    "https://fonts.googleapis.com/css2?"
    "family=Catamaran:wght@" + ";".join(map(str, WEIGHTS)) + "&display=swap"
)

print("1/3  Fetching Catamaran font CSS…")
try:
    r = requests.get(FONT_CSS_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
except Exception as e:
    print(f"     ERROR: {e}")
    sys.exit(1)

font_css  = r.text
woff2_urls = re.findall(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", font_css)
print(f"     Found {len(woff2_urls)} woff2 font file(s).")

for url in woff2_urls:
    print(f"     Downloading {url.split('/')[-1][:50]}…")
    try:
        data = requests.get(url, timeout=20)
        data.raise_for_status()
        b64 = base64.b64encode(data.content).decode()
        font_css = font_css.replace(url, f"data:font/woff2;base64,{b64}")
    except Exception as e:
        print(f"     WARNING: could not inline {url}: {e}")

inline_font = (
    "  <style>\n"
    "/* Catamaran — inlined for offline use */\n"
    f"{font_css}\n"
    "  </style>"
)

# ── Step 2: Dagre library ─────────────────────────────────────────────────
DAGRE_URL = "https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js"
print("2/3  Fetching Dagre layout library…")
try:
    dagre_js = requests.get(DAGRE_URL, timeout=20).text
    inline_dagre = f"  <script>\n/* dagre 0.8.5 — inlined for offline use */\n{dagre_js}\n  </script>"
    print(f"     OK ({round(len(dagre_js)/1024)} KB)")
except Exception as e:
    print(f"     WARNING: could not inline Dagre: {e}")
    inline_dagre = None

# ── Step 3: Patch HTML ───────────────────────────────────────────────────
print("3/3  Patching HTML…")
html = SRC.read_text(encoding="utf-8")

# Replace the 3 Google Fonts link tags with inline CSS
html = re.sub(
    r'[ \t]*<link[^>]+fonts\.googleapis\.com[^>]*>\s*\n'
    r'[ \t]*<link[^>]+fonts\.gstatic\.com[^>]*>\s*\n'
    r'[ \t]*<link[^>]+fonts\.googleapis\.com/css2[^>]*>',
    inline_font,
    html, count=1
)

# Replace the cdnjs dagre <script src=…> tag with inline script
if inline_dagre:
    html = re.sub(
        r'[ \t]*<script[^>]+dagre[^>]*></script>',
        inline_dagre,
        html, count=1
    )

DEST.write_text(html, encoding="utf-8")
size_kb = round(DEST.stat().st_size / 1024)
print(f"\nDone!  Written to: {DEST}  ({size_kb} KB)")
print("Open index-offline.html in any browser — no internet required.")
