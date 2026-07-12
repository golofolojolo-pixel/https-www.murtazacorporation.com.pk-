#!/usr/bin/env python3
"""
fetch_articles.py

Monthly pipeline for Murtaza Corporation's "Engineering Articles" page.

What it does, in order:
  1. DISCOVER  - Ask Gemini (with Google Search grounding) to find real,
                 recently published, reputable engineering/technical articles
                 relevant to Murtaza Corporation's business (stainless &
                 carbon steel piping, tubes, fittings, flanges, valves,
                 corrosion, MTRs/EN 10204, welding & fabrication).
  2. FETCH     - Download the actual article page and extract its real text.
  3. SUMMARIZE - Ask Gemini to summarize ONLY the fetched text into ~10
                 short lines. No search tool is used at this step, so the
                 model cannot invent facts that aren't in the source text.
  4. DEDUPE    - Skip URLs already listed in data/published_articles.json.
  5. INSERT    - Add new, image-free cards into engineering-articles.html
                 that link OUT to the original article (curation, not
                 republishing).

This script only edits files on disk. It does not commit, push, or open a
pull request - that's handled by the GitHub Actions workflow, which uses
peter-evans/create-pull-request so a human always reviews before anything
merges.

Environment variables:
  GEMINI_API_KEY      Required. API key for the Gemini API.
  ARTICLES_PER_RUN    Optional. Defaults to 2 (matches "1-2 per run").
"""

import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import trafilatura
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(REPO_ROOT, "engineering-articles.html")
TRACKING_PATH = os.path.join(REPO_ROOT, "data", "published_articles.json")

CARD_MARKER = "<!-- AUTO-CARDS:START (script inserts new card as first child here) -->"

MODEL_DISCOVER = "gemini-flash-latest"
MODEL_SUMMARIZE = "gemini-flash-latest"

ARTICLES_PER_RUN = int(os.environ.get("ARTICLES_PER_RUN", "2"))

# Rotate through a subset of these each run so coverage stays broad over time
# rather than repeating the same query every month.
TOPIC_POOL = [
    "304 vs 316 stainless steel selection for industrial piping",
    "carbon steel pipe corrosion prevention in industrial plants",
    "welded vs seamless pipe fittings manufacturing and specification",
    "flange types and gasket selection for process piping",
    "industrial valve selection (ball, gate, check, camlock) best practices",
    "instrumentation tubing standards and installation practices",
    "EN 10204 mill test certificates and material traceability",
    "ASTM/ASME piping standards updates for stainless and carbon steel",
    "structural steel fabrication techniques and quality control",
    "pipe welding procedures and weld quality inspection",
    "pitting and crevice corrosion in chloride environments",
    "hygienic (sanitary) stainless tubing for food and dairy processing",
]

MIN_SOURCE_CHARS = 800  # skip pages that are too thin to summarize responsibly


# ---------------------------------------------------------------------------
# Step 1: Discover real candidate articles via Gemini + Google Search grounding
# ---------------------------------------------------------------------------

def discover_candidates(client, topics, excluded_urls, want_count):
    """Uses Gemini's Google Search grounding tool to find real articles.

    Grounding metadata returns actual URLs the model found via search, so
    we don't rely on the model to type out a URL from memory (which risks
    hallucination). We treat grounding_chunks as the source of truth.
    """
    excluded_list = "\n".join(f"- {u}" for u in list(excluded_urls)[:50]) or "(none yet)"
    topics_list = "\n".join(f"- {t}" for t in topics)

    prompt = f"""
Find recent (ideally last 90 days, but high-quality evergreen technical
references are acceptable) real, published engineering/technical articles
on the following topics, written for an industrial B2B audience buying
stainless and carbon steel piping products:

{topics_list}

Prefer reputable sources: trade publications, engineering standards
organizations, manufacturer technical resources, and industry education
sites. Avoid marketing/sales pages, forums, and low-quality content mills.

Do NOT include any of these URLs, which have already been used:
{excluded_list}

Return {want_count * 4} good candidate articles.
""".strip()

    response = client.models.generate_content(
        model=MODEL_DISCOVER,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )

    candidates = []
    seen = set()

    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
    except (AttributeError, IndexError, TypeError):
        chunks = []

    for chunk in chunks:
        web = getattr(chunk, "web", None)
        uri = getattr(web, "uri", None) if web else None
        title = getattr(web, "title", None) if web else None
        if uri and uri not in seen and uri not in excluded_urls:
            seen.add(uri)
            candidates.append({"url": uri, "title": title or ""})

    return candidates


# ---------------------------------------------------------------------------
# Step 2: Fetch real article text
# ---------------------------------------------------------------------------

def fetch_article_text(url):
    """Downloads a URL and extracts the main article text. Returns None on
    failure (paywall, blocked, too short, non-HTML, etc.) so the caller can
    skip to the next candidate rather than summarizing junk."""
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MurtazaArticleBot/1.0)"},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None

    text = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
    if not text or len(text) < MIN_SOURCE_CHARS:
        return None
    return text


# ---------------------------------------------------------------------------
# Step 3: Summarize strictly from the fetched text
# ---------------------------------------------------------------------------

def summarize_article(client, title, url, source_text):
    """Asks Gemini to summarize ONLY the given text. No search tool is
    attached here, which keeps the model from pulling in outside claims."""

    # Trim very long articles to keep the prompt focused and cheap.
    trimmed = source_text[:12000]

    prompt = f"""
Summarize the following article in EXACTLY 8 to 10 short sentences, written
in plain, engineering-audience prose (no bullet points, no headers, no
markdown). Base the summary ONLY on the text provided below - do not add
outside facts, opinions, or claims that are not present in the text. Do not
mention that you are summarizing. Write in third person.

Title: {title}

Article text:
\"\"\"
{trimmed}
\"\"\"
""".strip()

    response = client.models.generate_content(
        model=MODEL_SUMMARIZE,
        contents=prompt,
    )

    summary = (response.text or "").strip()
    if not summary:
        return None
    return summary


# ---------------------------------------------------------------------------
# Step 4/5: Tracking file + HTML card generation
# ---------------------------------------------------------------------------

def load_tracking():
    if not os.path.exists(TRACKING_PATH):
        return []
    with open(TRACKING_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tracking(entries):
    os.makedirs(os.path.dirname(TRACKING_PATH), exist_ok=True)
    with open(TRACKING_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def estimate_read_minutes(text):
    words = len(text.split())
    return max(1, round(words / 200))


def html_escape(s):
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_card_html(article):
    domain = urlparse(article["url"]).netloc.replace("www.", "")
    title = html_escape(article["title"])
    summary = html_escape(article["summary"])
    minutes = article["read_minutes"]

    return f"""      <a class="card card-curated" href="{article['url']}" target="_blank" rel="noopener noreferrer">
        <div class="card-body">
          <p class="num">{domain} &middot; curated &middot; {minutes} min read</p>
          <h3>{title}</h3>
          <p>{summary}</p>
          <p class="hint">Read full article <i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i></p>
        </div>
      </a>
"""


def insert_cards_into_html(new_cards_html):
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    if CARD_MARKER not in html:
        raise RuntimeError(
            f"Could not find card marker in {HTML_PATH}. "
            "The page structure may have changed - insert manually."
        )

    html = html.replace(CARD_MARKER, CARD_MARKER + "\n" + new_cards_html, 1)

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    tracking = load_tracking()
    excluded_urls = {entry["url"] for entry in tracking}

    # Rotate topics by month so coverage broadens over time instead of
    # repeating the same query.
    month_index = datetime.now(timezone.utc).month
    random.seed(month_index)
    topics = random.sample(TOPIC_POOL, k=min(4, len(TOPIC_POOL)))

    print(f"Topics this run: {topics}")

    candidates = discover_candidates(client, topics, excluded_urls, ARTICLES_PER_RUN)
    print(f"Discovered {len(candidates)} candidate URLs via search grounding.")

    accepted = []
    for candidate in candidates:
        if len(accepted) >= ARTICLES_PER_RUN:
            break

        url = candidate["url"]
        print(f"Fetching: {url}")
        text = fetch_article_text(url)
        if not text:
            print("  -> could not extract usable text, skipping.")
            continue

        title = candidate["title"] or url
        summary = summarize_article(client, title, url, text)
        if not summary:
            print("  -> summarization failed, skipping.")
            continue

        accepted.append(
            {
                "url": url,
                "title": title,
                "summary": summary,
                "read_minutes": estimate_read_minutes(text),
                "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }
        )
        print(f"  -> accepted: {title}")

    if not accepted:
        print("No new articles were accepted this run. Nothing to do.")
        return

    cards_html = "".join(build_card_html(a) for a in accepted)
    insert_cards_into_html(cards_html)

    tracking = accepted + tracking  # newest first
    save_tracking(tracking)

    print(f"Inserted {len(accepted)} new article card(s) into {HTML_PATH}.")


if __name__ == "__main__":
    main()
