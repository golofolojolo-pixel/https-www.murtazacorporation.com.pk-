#!/usr/bin/env python3
"""
fetch_articles.py

Monthly pipeline for Murtaza Corporation's "Engineering Articles" page.

What it does, in order:
  1. DISCOVER  - Search free, keyless RSS sources (Google News RSS search,
                 plus any custom feeds you add) to find real, recently
                 published articles about stainless steel (SS) and mild/
                 carbon steel (MS) pipe specifically. No LLM call happens
                 in this step, so it never requires a paid/billed Gemini
                 project.
  2. RESOLVE   - Decode Google News' obfuscated redirect links to the real
                 publisher URL (via googlenewsdecoder).
  3. FETCH     - Download the actual article page and extract its real text.
  4. PRE-FILTER - Cheap, deterministic rejection of obviously-ineligible
                 candidates (India-linked domains/titles, book-review
                 titles, off-topic content, known low-value domains)
                 BEFORE spending an LLM call on them.
  5. CLASSIFY+SUMMARIZE - Ask Gemini (free tier, plain text generation -
                 no paid Google Search grounding tool) to first judge
                 whether the article is actually eligible under the strict
                 rules below, and only then summarize ONLY the fetched
                 text into ~8-10 short lines. The model cannot invent
                 facts that aren't in the source text, and articles that
                 fail the eligibility check are skipped entirely.
  6. DEDUPE    - Skip URLs already listed in data/published_articles.json.
  7. INSERT    - Add new, image-free cards into engineering-articles.html
                 that link OUT to the original article (curation, not
                 republishing).

This script only edits files on disk. It does not commit, push, or open a
pull request - that's handled by the GitHub Actions workflow, which uses
peter-evans/create-pull-request so a human always reviews before anything
merges.

STRICT CONTENT RULES (as of this version):
  - Must be specifically about stainless steel (SS) or mild/carbon steel
    (MS) pipe. Articles about valves, flanges, or other components with
    no substantial pipe-specific content do NOT qualify.
  - Must be educational/informative - explains a concept, standard,
    technique, or a genuinely important industry development. Thin
    market-research stat dumps, ads, or routine promotional company news
    with no real educational value are rejected.
  - Must NOT be a book review, article review, or any literary/media
    review content.
  - Must NOT be primarily about India, an Indian company, or written from
    an Indian trade-publication's perspective.

Environment variables:
  GEMINI_API_KEY          Required. API key for the Gemini API.
  ARTICLES_PER_RUN        Optional. Defaults to 2 (matches "1-2 per run").
  MIN_SOURCE_CHARS        Optional. Defaults to 800.
  MAX_GEMINI_CALLS_PER_RUN Optional. Defaults to 8. Hard ceiling on how many
                          Gemini requests (including retries) a single run
                          will ever make, so a bad run can't burn through
                          the whole daily free-tier quota (20/day as of
                          this writing) in one go.
"""

import json
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse, quote

import requests
import trafilatura
from google import genai
from google.genai import types
from googlenewsdecoder import gnewsdecoder

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(REPO_ROOT, "engineering-articles.html")
TRACKING_PATH = os.path.join(REPO_ROOT, "data", "published_articles.json")

CARD_MARKER = "<!-- AUTO-CARDS:START (script inserts new card as first child here) -->"

# Only used for the classification+summarization step (plain text
# generation - no paid Google Search grounding tool involved, so this
# stays on the free tier).
MODEL_SUMMARIZE = "gemini-flash-latest"

ARTICLES_PER_RUN = int(os.environ.get("ARTICLES_PER_RUN", "2"))
MIN_SOURCE_CHARS = int(os.environ.get("MIN_SOURCE_CHARS", "800"))

# Hard ceiling on Gemini requests for the whole run (see module docstring).
# Free tier is commonly 20 requests/day - default here leaves headroom for
# other runs/testing that day, rather than assuming this run owns the
# entire daily budget.
MAX_GEMINI_CALLS_PER_RUN = int(os.environ.get("MAX_GEMINI_CALLS_PER_RUN", "8"))

USER_AGENT = "Mozilla/5.0 (compatible; MurtazaArticleBot/1.0)"

# Optional: paste direct RSS feed URLs from trade publications you trust
# here (e.g. a publication's own /feed page). Direct feeds are more
# reliable than Google News search since there's no redirect to resolve.
# Leave empty to rely on Google News RSS search alone.
CUSTOM_RSS_FEEDS = [
    # "https://example-trade-publication.com/feed",
]

# Rotate through a subset of these each run so coverage stays broad over
# time rather than repeating the same query every month. STRICTLY anchored
# on "steel pipe" (SS or MS) - no valve-only / flange-only / instrumentation
# -only topics, since those don't satisfy the "strictly pipe" requirement.
TOPIC_POOL = [
    "stainless steel pipe manufacturing standards",
    "carbon steel pipe corrosion prevention industrial plants",
    "welded vs seamless steel pipe manufacturing specification",
    "steel pipe welding procedures weld quality inspection",
    "stainless steel pipe pitting crevice corrosion chloride",
    "mild steel pipe industrial applications specification",
    "steel pipe wall thickness schedule selection ASME",
    "ASTM ASME steel pipe standards specification",
    "steel pipe mill test certificate EN 10204 traceability",
    "steel pipe manufacturing quality control fabrication",
    "hygienic sanitary stainless steel pipe tubing standards",
    "steel pipeline safety regulations pipe integrity",
]

# --- Fast, deterministic pre-filters (run BEFORE any LLM call) ------------

# Reject candidates whose domain or title suggests an Indian publication /
# company, or where the TLD is .in. This is a heuristic, not a guarantee -
# the LLM classification step below is a second, stricter check for cases
# this misses (e.g. an India-based story on a .com domain with no obvious
# marker in the title).
INDIA_DOMAIN_MARKERS = [
    ".in",          # TLD
    "india",        # e.g. tubepipeindia.com
]

# Known low-value / off-topic domains you don't want cluttering the feed,
# or that reliably fail the "educational, not a stat dump" rule anyway and
# so are never worth spending a fetch + Gemini call on. Grow this list as
# junk sources show up in PRs or run logs.
DOMAIN_DENYLIST = [
    "indexbox.io",            # thin market-size/forecast stat dumps
    "openpr.com",              # press-release / market-report aggregator
    "marketdataforecast.com",  # market-research report teasers, not articles
    "vocal.media",             # low-quality open blogging platform, off-topic hits
]

BOOK_REVIEW_TITLE_MARKERS = [
    "book review",
    "review of the book",
    "author interview",
    "book excerpt",
]

# Cheap relevance gate: title (and later, fetched text) must show some
# real sign of being about steel pipe before we spend a fetch/LLM call on
# it. This is deliberately generous (OR of many terms) - it's here to
# catch obviously off-topic RSS mismatches (e.g. an "Audi exhaust pipe"
# blog post matched on the word "pipe"), not to replace the strict LLM
# eligibility check.
RELEVANCE_TERMS = [
    "steel", "stainless", "ss pipe", "ms pipe", "carbon steel",
    "pipeline", "piping", "astm", "asme", "welded", "seamless",
    "corrosion", "alloy", "metallurg", "mill test", "schedule 40",
    "schedule 80", "en 10204",
]

OFF_TOPIC_TITLE_MARKERS = [
    "exhaust", "muffler", "car", "vehicle", "automotive", "audi", "bmw",
    "toyota", "honda", "tailpipe",
]


def title_is_relevant(title):
    """Very cheap sanity check on the RSS title alone, before any network
    fetch. Returns False if the title looks unambiguously off-topic (e.g.
    car exhaust content matched only because it contains the word 'pipe'),
    or if it shows literally none of the expected steel/pipe vocabulary."""
    title_l = (title or "").lower()

    for marker in OFF_TOPIC_TITLE_MARKERS:
        if marker in title_l:
            return False

    # Require at least one relevance term in the title. This is generous
    # on purpose (title alone is a weak signal) - real topic/eligibility
    # filtering still happens via fails_fast_prefilter + the LLM step.
    return any(term in title_l for term in RELEVANCE_TERMS)


def fails_fast_prefilter(domain, title):
    """Returns a rejection reason string if the candidate should be
    skipped without ever spending a fetch or LLM call on it, or None if it
    passes the fast filter (still subject to the stricter LLM check
    later)."""
    domain_l = (domain or "").lower()
    title_l = (title or "").lower()

    for marker in INDIA_DOMAIN_MARKERS:
        if marker in domain_l:
            return f"domain matches India marker '{marker}'"

    for denied in DOMAIN_DENYLIST:
        if denied.lower() in domain_l:
            return f"domain is denylisted ({denied})"

    for marker in BOOK_REVIEW_TITLE_MARKERS:
        if marker in title_l:
            return f"title matches book-review marker '{marker}'"

    if not title_is_relevant(title):
        return "title shows no steel/pipe relevance (or matches an off-topic marker)"

    return None


# ---------------------------------------------------------------------------
# Step 1: Discover real candidate articles via free RSS sources (no billing)
# ---------------------------------------------------------------------------

def _parse_rss_items(xml_bytes):
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:
            items.append({"title": title, "url": link})
    return items


def discover_candidates(topics, excluded_urls, want_count):
    """Finds real candidate articles using free, keyless RSS sources:
    Google News RSS search (per topic) plus any custom feeds you've added
    above. No LLM call happens here, so this step never touches billing."""
    candidates = []
    seen = set(excluded_urls)

    for topic in topics:
        rss_url = (
            "https://news.google.com/rss/search?q="
            f"{quote(topic)}+when:180d&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            resp = requests.get(rss_url, timeout=15, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        except requests.RequestException:
            continue

        for item in _parse_rss_items(resp.content):
            if item["url"] not in seen:
                seen.add(item["url"])
                candidates.append(item)

    for feed_url in CUSTOM_RSS_FEEDS:
        try:
            resp = requests.get(feed_url, timeout=15, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        except requests.RequestException:
            continue
        for item in _parse_rss_items(resp.content):
            if item["url"] not in seen:
                seen.add(item["url"])
                candidates.append(item)

    random.shuffle(candidates)
    return candidates[: want_count * 8]  # slightly wider pool since filters are stricter now


def resolve_real_url(url):
    """Google News RSS <link> values are obfuscated redirect URLs, not the
    actual article URL. This decodes them to the real source URL so that
    (a) we can fetch the real page text, and (b) the published card links
    to the original publisher, not to Google News."""
    if "news.google.com" not in url:
        return url
    try:
        result = gnewsdecoder(url, interval=1)
    except Exception:
        return None
    if result and result.get("status"):
        return result.get("decoded_url")
    return None


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
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None

    text = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
    if not text or len(text) < MIN_SOURCE_CHARS:
        return None
    return text


# ---------------------------------------------------------------------------
# Step 3: Classify eligibility AND summarize, strictly from the fetched text
# ---------------------------------------------------------------------------

class QuotaExhaustedError(Exception):
    """Raised when Gemini reports the daily/free-tier quota is exhausted.
    Unlike a transient 503 'high demand' error, retrying this within the
    same run is pointless - every subsequent call will fail identically
    until the quota resets. Callers should stop issuing new Gemini calls
    for the rest of the run when they see this, rather than burning
    retries (and log noise) on every remaining candidate."""
    pass


def _is_quota_exhausted_error(exc):
    """Distinguishes a hard quota/rate-limit exhaustion from a transient
    error (like a 503 'high demand' blip) worth retrying. Gemini reports
    quota exhaustion as a 429 RESOURCE_EXHAUSTED with 'quota' in the
    message - we check for that combination rather than any 429, in case
    a future error taxonomy adds other 429 reasons that ARE worth
    retrying."""
    msg = str(exc).lower()
    return "resource_exhausted" in msg and "quota" in msg


def classify_and_summarize(client, title, url, source_text, max_attempts=3):
    """Asks Gemini to (a) judge whether the article is eligible under the
    strict content rules, and (b) if eligible, summarize ONLY the given
    text. No search tool is attached, which keeps the model from pulling
    in outside claims.

    Returns a dict: {"eligible": bool, "reason": str, "summary": str|None}
    or None if the call failed after retries.

    Retries a couple of times on transient server errors (e.g. 503 'high
    demand') before giving up on this one article - a temporary hiccup on
    one candidate shouldn't crash the whole run. Raises QuotaExhaustedError
    immediately (no retries) if the quota is exhausted, since retrying that
    is guaranteed to fail and just wastes the run's remaining time."""

    # Trim very long articles to keep the prompt focused and cheap.
    trimmed = source_text[:12000]

    prompt = f"""
You are screening a candidate article for an industrial steel pipe company's
curated articles feed. Judge ELIGIBILITY first, using ONLY the article text
provided below (do not use outside knowledge to guess at facts not present).

An article is ELIGIBLE only if ALL of the following are true:
1. It is specifically about stainless steel (SS) or mild/carbon steel (MS)
   PIPE - manufacturing, standards, specifications, corrosion, welding,
   fabrication, testing, applications, or maintenance of steel pipe.
   Articles primarily about valves, flanges, or other components, with no
   substantial pipe-specific content, do NOT qualify.
2. It is educational/informative - it explains a concept, standard,
   technique, or a genuinely important industry development that a piping
   engineer or buyer should know. Thin market-research statistic dumps,
   advertisements, or routine promotional company news with no real
   educational content do NOT qualify.
3. It is NOT a book review, article review, or any literary/media review.
4. It is NOT primarily about India, an Indian company, or written from an
   Indian trade publication's perspective (check for Indian company names,
   INR/rupee pricing, Indian place names, or an Indian publisher context).

Respond with ONLY a JSON object (no markdown fences, no extra text) in
exactly this shape:
{{
  "eligible": true or false,
  "reason": "one short sentence explaining the eligibility decision",
  "summary": "8 to 10 short sentences in plain, engineering-audience prose,
    third person, no bullet points, no markdown, based ONLY on the article
    text below - or null if not eligible"
}}

Title: {title}

Article text:
\"\"\"
{trimmed}
\"\"\"
""".strip()

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_SUMMARIZE,
                contents=prompt,
            )
            raw = (response.text or "").strip()
            # Strip accidental markdown code fences if the model adds them.
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
            data = json.loads(raw)
            if not isinstance(data, dict) or "eligible" not in data:
                print("  -> unexpected response shape from model, skipping.")
                return None
            return data
        except json.JSONDecodeError as exc:
            print(f"  -> could not parse model response as JSON (attempt {attempt}/{max_attempts}): {exc}")
        except Exception as exc:
            if _is_quota_exhausted_error(exc):
                # Don't retry - every remaining attempt will fail the same
                # way, and each one still counts as a burned request.
                print(f"  -> Gemini quota exhausted, aborting retries for this article: {exc}")
                raise QuotaExhaustedError(str(exc)) from exc
            print(f"  -> Gemini call failed (attempt {attempt}/{max_attempts}): {exc}")

        if attempt < max_attempts:
            time.sleep(5 * attempt)  # 5s, then 10s
        else:
            print("  -> giving up on this article after repeated failures.")
            return None


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
    # repeating the same query. (Seeded per-run, not globally, so it
    # doesn't also pin candidate shuffling below to the month.)
    month_index = datetime.now(timezone.utc).month
    topic_rng = random.Random(month_index)
    topics = topic_rng.sample(TOPIC_POOL, k=min(4, len(TOPIC_POOL)))

    print(f"Topics this run: {topics}")

    candidates = discover_candidates(topics, excluded_urls, ARTICLES_PER_RUN)
    print(f"Discovered {len(candidates)} candidate URLs via free RSS sources.")

    accepted = []
    gemini_calls_used = 0
    quota_exhausted = False

    for candidate in candidates:
        if len(accepted) >= ARTICLES_PER_RUN:
            break

        if quota_exhausted:
            print("  -> skipping remaining candidates: Gemini quota already exhausted this run.")
            break

        if gemini_calls_used >= MAX_GEMINI_CALLS_PER_RUN:
            print(
                f"  -> reached MAX_GEMINI_CALLS_PER_RUN ({MAX_GEMINI_CALLS_PER_RUN}) "
                "for this run, stopping to preserve quota for future runs."
            )
            break

        try:
            url = candidate["url"]
            real_url = resolve_real_url(url)
            if not real_url:
                print(f"  -> could not resolve real URL for {url[:80]}, skipping.")
                continue
            if real_url in excluded_urls:
                continue

            domain = urlparse(real_url).netloc.replace("www.", "")
            title = candidate["title"] or real_url

            # Fast, free, deterministic rejection before spending a fetch
            # or an LLM call.
            prefilter_reason = fails_fast_prefilter(domain, title)
            if prefilter_reason:
                print(f"  -> pre-filter rejected ({prefilter_reason}): {title[:80]}")
                continue

            print(f"Fetching: {real_url}")
            text = fetch_article_text(real_url)
            if not text:
                print("  -> could not extract usable text, skipping.")
                continue

            gemini_calls_used += 1
            try:
                result = classify_and_summarize(client, title, real_url, text)
            except QuotaExhaustedError:
                quota_exhausted = True
                print("  -> stopping this run: Gemini free-tier quota exhausted.")
                break

            if not result:
                print("  -> classification/summarization failed, skipping.")
                continue

            if not result.get("eligible"):
                print(f"  -> rejected by content rules: {result.get('reason', 'no reason given')}")
                continue

            summary = (result.get("summary") or "").strip()
            if not summary:
                print("  -> marked eligible but no summary returned, skipping.")
                continue

            accepted.append(
                {
                    "url": real_url,
                    "title": title,
                    "summary": summary,
                    "read_minutes": estimate_read_minutes(text),
                    "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                }
            )
            print(f"  -> accepted: {title}")
            excluded_urls.add(real_url)
        except Exception as exc:
            print(f"  -> unexpected error on this candidate, skipping: {exc}")
            continue

    if quota_exhausted:
        print(
            "NOTE: this run stopped early because the Gemini free-tier daily "
            "quota was exhausted. If this keeps happening, either lower "
            "MAX_GEMINI_CALLS_PER_RUN's competition by running less often, "
            "reduce ARTICLES_PER_RUN, or move to a paid Gemini tier."
        )

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
