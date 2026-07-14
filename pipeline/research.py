"""
Research stage.
Fetches the full text of each selected story (primary + corroborating
sources) and distills it into a fact brief the hosts can actually cite —
numbers, quotes, names — instead of riffing on a headline.
"""

import json
import logging

import config
from pipeline.cost_tracker import tracker

logger = logging.getLogger(__name__)

MAX_SOURCES_PER_STORY = 2
MAX_ARTICLE_CHARS = 8000
MIN_USEFUL_CHARS = 400


def _fetch_article_text(url: str) -> str | None:
    """Fetch a URL and extract readable article text. None on failure."""
    if not url:
        return None
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded, include_comments=False, include_tables=False
            )
            if text and len(text) >= MIN_USEFUL_CHARS:
                return text[:MAX_ARTICLE_CHARS]
    except Exception as e:
        logger.debug(f"trafilatura failed for {url}: {e}")

    # Fallback: plain requests + extract from raw HTML
    try:
        import requests
        import trafilatura

        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ContextWindowBot/1.0)"},
        )
        if resp.ok:
            text = trafilatura.extract(resp.text, include_comments=False)
            if text and len(text) >= MIN_USEFUL_CHARS:
                return text[:MAX_ARTICLE_CHARS]
    except Exception as e:
        logger.debug(f"requests fallback failed for {url}: {e}")

    return None


def _distill_brief(client, topic: dict, sources: list[dict]) -> dict | None:
    """Boil fetched articles down to a citable fact brief."""
    src_blob = "\n\n---\n\n".join(
        f"[{s['source'] or 'unknown'}] {s['url']}\n{s['text']}" for s in sources
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            max_tokens=800,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You distill news articles into fact briefs for podcast "
                        "hosts. Include ONLY facts stated in the provided articles "
                        "— no outside knowledge, no speculation. Prefer concrete "
                        "specifics: numbers, dates, names, direct quotes."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Story: {topic['title']}\n\nArticles:\n{src_blob}\n\n"
                        "Return JSON:\n"
                        '{"key_facts": [5-8 bullet strings, each a concrete fact],\n'
                        ' "numbers_and_quotes": [exact figures and short direct '
                        'quotes, each with who said it / where it comes from],\n'
                        ' "context": "1-2 sentences of essential background",\n'
                        ' "open_questions": [1-3 things the articles do NOT answer],\n'
                        ' "sources": [publication names covered here]}'
                    ),
                },
            ],
        )
        usage = resp.usage
        if usage:
            tracker.record(
                step="research", model="gpt-4o-mini",
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
            )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.error(f"Brief distillation failed for '{topic['title'][:60]}': {e}")
        return None


def research_topics(topics: list[dict]) -> list[dict]:
    """
    Attach a fact brief to each topic (topic["brief"]).

    Fetch failures degrade gracefully: a story with no fetchable source
    keeps brief=None and the hosts fall back to the ranked summary.
    """
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)

    for topic in topics:
        candidates = [{"source": topic.get("source", ""), "url": topic.get("url", "")}]
        candidates += topic.get("alt_sources", [])

        sources = []
        for cand in candidates:
            if len(sources) >= MAX_SOURCES_PER_STORY:
                break
            text = _fetch_article_text(cand.get("url", ""))
            if text:
                sources.append({**cand, "text": text})

        if not sources:
            topic["brief"] = None
            logger.warning(
                f"No article text fetched for '{topic['title'][:60]}' — "
                "hosts will rely on the summary only"
            )
            continue

        topic["brief"] = _distill_brief(client, topic, sources)
        n_facts = len((topic["brief"] or {}).get("key_facts", []))
        logger.info(
            f"Researched '{topic['title'][:60]}' — {len(sources)} source(s), "
            f"{n_facts} key facts"
        )

    return topics
