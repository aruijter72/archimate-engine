#!/usr/bin/env python3
"""
build-offline.py — Architise offline build script
Fetches the Catamaran font from Google Fonts, inlines it as base64,
and writes index-offline.html — a fully self-contained, 100% offline file.

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

WEIGHTS = [400, 500, 600, 700, 800, 900]
FONT_CSS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Catamaran:wght@" + ";".join(map(str, WEIGHTS)) + "&display=swap"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Architise-build/1.0)"}

print("Fetching Catamaran font CSS from Google Fonts…")
try:
    r = requests.get(FONT_CSS_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
except Exception as e:
    print(f"Could not fetch font CSS: {e}")
    sys.exit(1)

font_css = r.text
woff2_urls = re.findall(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", font_css)
print(f"Found {len(woff2_urls)} woff2 font file(s).")

def fetch_b64(url):
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return base64.b64encode(resp.content).decode()

# Build inline @font-face blocks
inline_faces = []
for url in woff2_urls:
    print(f"  Downloading {url.split('/')[-1][:40]}…")
    b64 = fetch_b64(url)
    # Replace the remote URL reference with a data URI in the CSS block
    font_css = font_css.replace(url, f"data:font/woff2;base64,{b64}")

inline_css = f"<style>\n/* Catamaran — inlined for offline use */\n{font_css}\n</style>"

# Read source HTML
html = SRC.read_text(encoding="utf-8")

# Remove the three Google Fonts link tags and replace with inline CSS
html = re.sub(
    r'<link[^>]+fonts\.googleapis\.com[^>]*>\s*\n?'
    r'<link[^>]+fonts\.gstatic\.com[^>]*>\s*\n?'
    r'<link[^>]+fonts\.googleapis\.com/css2[^>]*>\s*\n?',
    inline_css + "\n",
    html, count=1
)

DEST.write_text(html, encoding="utf-8")
size_kb = round(DEST.stat().st_size / 1024)
print(f"\nDone! Offline build written to: {DEST}  ({size_kb} KB)")
print("Open index-offline.html in any browser — no internet required.")
