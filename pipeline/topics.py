"""
Topic discovery engine.
Pulls trending AI/tech news from multiple sources and ranks them for the daily episode.
"""

import json
import logging
from datetime import datetime, timedelta

import requests

import config
from pipeline.cost_tracker import tracker

logger = logging.getLogger(__name__)

# Fallback RSS feeds if NewsAPI key isn't set
RSS_SOURCES = [
    "https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=OpenAI+OR+Anthropic+OR+Google+AI&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=AI+regulation+OR+AI+safety&hl=en-US&gl=US&ceid=US:en",
]

NEWSAPI_CATEGORIES = [
    "artificial intelligence",
    "OpenAI OR Anthropic OR Google DeepMind",
    "AI regulation OR AI safety OR machine learning",
    "tech industry layoffs OR tech earnings OR startup funding",
]


def fetch_from_newsapi() -> list[dict]:
    """Fetch top AI/tech headlines from NewsAPI."""
    if not config.NEWS_API_KEY:
        logger.warning("No NEWS_API_KEY set, skipping NewsAPI")
        return []

    articles = []
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    for query in NEWSAPI_CATEGORIES:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "from": yesterday,
                    "sortBy": "relevancy",
                    "language": "en",
                    "pageSize": 5,
                    "apiKey": config.NEWS_API_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            for a in data.get("articles", []):
                articles.append(
                    {
                        "title": a["title"],
                        "description": a.get("description", ""),
                        "source": a["source"]["name"],
                        "url": a["url"],
                        "published": a.get("publishedAt", ""),
                    }
                )
        except Exception as e:
            logger.error(f"NewsAPI query failed for '{query}': {e}")

    return articles


def fetch_from_google_rss() -> list[dict]:
    """Fallback: parse Google News RSS for AI topics."""
    import xml.etree.ElementTree as ET

    articles = []
    for url in RSS_SOURCES:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:5]:
                title = item.findtext("title", "")
                # Google News titles often end with " - Source Name"
                source = ""
                if " - " in title:
                    title, source = title.rsplit(" - ", 1)
                articles.append(
                    {
                        "title": title.strip(),
                        "description": item.findtext("description", ""),
                        "source": source.strip(),
                        "url": item.findtext("link", ""),
                        "published": item.findtext("pubDate", ""),
                    }
                )
        except Exception as e:
            logger.error(f"RSS fetch failed for {url}: {e}")

    return articles


def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove near-duplicate articles by title similarity."""
    seen_titles = set()
    unique = []
    for a in articles:
        # Simple dedup: normalize and check first 50 chars
        key = a["title"].lower().strip()[:50]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(a)
    return unique


def rank_topics(articles: list[dict]) -> list[dict]:
    """
    Use OpenAI to rank and select the best topics for today's episode.
    Returns the top 5-6 stories, ranked by podcast-worthiness.
    """
    from openai import OpenAI

    if not articles:
        logger.error("No articles found — cannot rank topics")
        return []

    client = OpenAI(api_key=config.OPENAI_API_KEY)

    articles_text = "\n".join(
        f"{i+1}. [{a['source']}] {a['title']}: {a['description']}"
        for i, a in enumerate(articles)
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a podcast producer for 'The Context Window', a show hosted by "
                    "Claude (Anthropic) and ChatGPT (OpenAI). Pick the 5-6 most "
                    "podcast-worthy stories from this list.\n\n"
                    "STRICT RELEVANCE FILTER — only select stories that are DIRECTLY about:\n"
                    "- AI models, products, or companies (OpenAI, Anthropic, Google, Meta, etc.)\n"
                    "- AI regulation, policy, or safety\n"
                    "- Major tech industry moves that involve AI\n"
                    "- How AI is changing specific industries or jobs\n"
                    "- Robotics and autonomous systems\n\n"
                    "REJECT stories about:\n"
                    "- Generic industry reports that just mention 'AI' as a buzzword\n"
                    "- Products/industries that aren't primarily about AI (escalators, appliances, etc.)\n"
                    "- Clickbait or low-substance articles\n"
                    "- Stories with '[Removed]' or empty descriptions\n\n"
                    "Prioritize:\n"
                    "1. Breaking news the hosts can have genuine opinions about\n"
                    "2. Stories that directly affect AI systems or the AI industry\n"
                    "3. Stories with real human impact worth debating\n"
                    "4. Variety — don't pick 5 stories about the same thing\n\n"
                    "Return JSON: {\"stories\": [{\"rank\": 1, \"title\": \"...\", "
                    "\"summary\": \"1-2 sentence summary\", \"angle\": \"why this is "
                    "good for the podcast\", \"category\": \"main|lightning\"}]}\n"
                    "Mark 2-3 as 'main' (deep discussion) and the rest as 'lightning' "
                    "(quick takes). If fewer than 5 stories pass the relevance filter, "
                    "return only the ones that do."
                ),
            },
            {"role": "user", "content": f"Today's articles:\n{articles_text}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    # Track usage
    usage = resp.usage
    if usage:
        tracker.record(
            step="topic_ranking", model="gpt-4o-mini",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )

    try:
        result = json.loads(resp.choices[0].message.content)
        return result.get("stories", [])
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"Failed to parse ranked topics: {e}")
        # Fallback: return first 5 articles as-is
        return [
            {
                "rank": i + 1,
                "title": a["title"],
                "summary": a["description"],
                "angle": "",
                "category": "main" if i < 3 else "lightning",
            }
            for i, a in enumerate(articles[:5])
        ]


def discover_topics() -> list[dict]:
    """
    Main entry point. Fetches news from all sources, deduplicates, and ranks.
    Returns ranked list of topics ready for script generation.
    """
    logger.info("Discovering today's topics...")

    # Fetch from all sources
    articles = fetch_from_newsapi()
    if len(articles) < 5:
        logger.info("Supplementing with Google RSS...")
        articles.extend(fetch_from_google_rss())

    logger.info(f"Found {len(articles)} raw articles")

    # Deduplicate
    articles = deduplicate(articles)
    logger.info(f"{len(articles)} unique articles after dedup")

    # Rank
    ranked = rank_topics(articles)
    logger.info(f"Selected {len(ranked)} topics for today's episode")

    return ranked
