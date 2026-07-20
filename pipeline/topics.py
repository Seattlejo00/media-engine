"""
Topic discovery engine.
Pulls trending AI/tech news from multiple sources and ranks them for the daily episode.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests

import config
from pipeline.cost_tracker import tracker

logger = logging.getLogger(__name__)

# Fallback RSS feeds if NewsAPI key isn't set
TRACKED_PLAYERS = {
    "openai": {"name": "OpenAI", "aliases": ("openai", "chatgpt", "gpt-")},
    "anthropic": {"name": "Anthropic", "aliases": ("anthropic", "claude")},
    "google": {"name": "Google DeepMind", "aliases": ("google deepmind", "deepmind", "gemini")},
    "meta": {"name": "Meta", "aliases": ("meta", "meta ai", "llama")},
    "xai": {"name": "xAI", "aliases": ("xai", "x.ai", "grok")},
    "deepseek": {"name": "DeepSeek", "aliases": ("deepseek",)},
    "moonshot": {"name": "Moonshot/Kimi", "aliases": ("moonshot ai", "kimi")},
    "alibaba": {"name": "Alibaba/Qwen", "aliases": ("alibaba", "qwen")},
    "mistral": {"name": "Mistral", "aliases": ("mistral ai", "mistral")},
}

OFFICIAL_DOMAINS = {
    "openai.com", "anthropic.com", "deepmind.google", "blog.google",
    "ai.meta.com", "x.ai", "deepseek.com", "moonshot.ai", "kimi.com",
    "qwenlm.ai", "alibabacloud.com", "mistral.ai",
}

RSS_SOURCES = [
    "https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=OpenAI+OR+Anthropic+OR+Google+DeepMind+OR+Meta+AI+OR+xAI&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=DeepSeek+OR+Kimi+OR+Moonshot+AI+OR+Qwen+OR+Mistral+AI&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=AI+regulation+OR+AI+safety&hl=en-US&gl=US&ceid=US:en",
]

NEWSAPI_CATEGORIES = [
    "artificial intelligence",
    "OpenAI OR Anthropic OR Google DeepMind OR Meta AI OR xAI",
    "DeepSeek OR Moonshot AI OR Kimi OR Qwen OR Mistral AI",
    "AI model launch OR AI agent OR open weights",
    "AI regulation OR AI safety OR AI policy",
    "AI research OR AI benchmark",
    "AI chips OR AI compute OR AI datacenter",
    "AI startup funding OR AI acquisition OR AI enterprise adoption",
]

MAJOR_EVENT_PATTERN = re.compile(
    r"\b(?:launch(?:es|ed)?|release(?:s|d)?|unveil(?:s|ed)?|introduc(?:e|es|ed)|"
    r"debut(?:s|ed)?|arriv(?:e|es|ed)|drop(?:s|ped)?|"
    r"announce(?:s|d)?|open[- ]weights?|frontier model|flagship model|"
    r"acquir(?:e|es|ed)|merger|raises? \$|funding round|files? (?:an? )?s-1)\b",
    re.IGNORECASE,
)
POLICY_EVENT_PATTERN = re.compile(
    r"\b(?:ai act|executive order|regulation|regulator|law|legislation|ban|"
    r"injunction|antitrust|safety incident)\b",
    re.IGNORECASE,
)

MODEL_EVENT_PATTERN = re.compile(
    r"\b(?:gpt[- ]?[a-z]?\d+(?:\.\d+)*|claude[- ]?[a-z]*\d+(?:\.\d+)*|"
    r"gemini[- ]?[a-z]*\d+(?:\.\d+)*|grok[- ]?[a-z]*\d+(?:\.\d+)*|"
    r"llama[- ]?\d+(?:\.\d+)*|qwen[- ]?[a-z]*\d+(?:\.\d+)*|"
    r"kimi[- ]?[a-z]*\d+(?:\.\d+)*|deepseek[- ]?[a-z]*\d+(?:\.\d+)*|"
    r"mistral[- ]?[a-z]*\d+(?:\.\d+)*)\b",
    re.IGNORECASE,
)
EVENT_STOPWORDS = {
    "about", "after", "against", "from", "into", "launch", "launches",
    "model", "models", "new", "open", "releases", "says", "that", "the",
    "their", "this", "with", "world", "worlds",
}
EVENT_ACTION_PATTERNS = {
    "release": re.compile(
        r"\b(?:launch(?:es|ed)?|release[sd]?|ship(?:s|ped)?|unveil(?:s|ed)?)\b",
        re.I,
    ),
    "funding": re.compile(r"\b(?:funding|fundraise|raises?|valuation|valued)\b", re.I),
    "benchmark": re.compile(r"\b(?:benchmark|evaluation|evals?|score[sd]?)\b", re.I),
    "pricing": re.compile(r"\b(?:price|prices|pricing|subscription|costs?)\b", re.I),
    "partnership": re.compile(r"\b(?:partner(?:s|ed|ship)?|deal|agreement)\b", re.I),
    "acquisition": re.compile(r"\b(?:acquire[sd]?|acquisition|merger)\b", re.I),
    "policy": re.compile(r"\b(?:law|lawsuit|policy|regulat(?:e|es|ed|ion))\b", re.I),
    "outage": re.compile(r"\b(?:outage|downtime|incident)\b", re.I),
}


def _source_priority(article: dict) -> int:
    """Prefer first-party announcements, then fully identified publications."""
    host = urlparse(article.get("url") or "").netloc.lower().removeprefix("www.")
    if any(host == domain or host.endswith(f".{domain}") for domain in OFFICIAL_DOMAINS):
        return 0
    return 1 if article.get("source") else 2


def _players_for(text: str) -> list[str]:
    haystack = text.lower()

    def has_alias(alias: str) -> bool:
        if alias.endswith("-"):
            return alias in haystack
        return bool(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", haystack))

    return [
        player_id
        for player_id, player in TRACKED_PLAYERS.items()
        if any(has_alias(alias) for alias in player["aliases"])
    ]


def _editorial_lane(text: str) -> str:
    haystack = text.lower()
    if any(word in haystack for word in ("regulation", "policy", "law", "safety", "governance")):
        return "policy_safety"
    if any(word in haystack for word in ("chip", "compute", "datacenter", "gpu")):
        return "compute"
    if any(word in haystack for word in ("research", "paper", "benchmark", "study")):
        return "research"
    if any(word in haystack for word in ("funding", "acquisition", "enterprise", "revenue", "ipo")):
        return "industry"
    return "models_products"


def audit_candidates(articles: list[dict]) -> list[dict]:
    """Attach landscape metadata and deterministic must-cover signals."""
    audited = []
    for article in articles:
        item = dict(article)
        text = f"{item.get('title', '')} {item.get('description', '')}"
        players = _players_for(text)
        is_player_event = bool(players and MAJOR_EVENT_PATTERN.search(text))
        is_policy_event = bool(POLICY_EVENT_PATTERN.search(text) and "ai" in text.lower())
        item["tracked_players"] = players
        item["editorial_lane"] = _editorial_lane(text)
        item["source_priority"] = _source_priority(item)
        item["must_cover"] = is_player_event or is_policy_event
        if is_player_event:
            names = ", ".join(TRACKED_PLAYERS[p]["name"] for p in players)
            item["must_cover_reason"] = f"Major tracked-player event: {names}"
        elif is_policy_event:
            item["must_cover_reason"] = "Potentially consequential AI policy or safety event"
        audited.append(item)
    return audited


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
                    "pageSize": 10,
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


def fetch_official_updates() -> list[dict]:
    """Fetch first-party lab updates so launches do not depend on press pickup."""
    if not config.NEWS_API_KEY:
        return []
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": "model OR launch OR release OR agent OR research",
                "domains": ",".join(sorted(OFFICIAL_DOMAINS)),
                "from": yesterday,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 20,
                "apiKey": config.NEWS_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return [
            {
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "source": (item.get("source") or {}).get("name", "Official update"),
                "url": item.get("url", ""),
                "published": item.get("publishedAt", ""),
            }
            for item in resp.json().get("articles", [])
            if item.get("title") and item.get("url")
        ]
    except Exception as exc:
        logger.warning("Official-source discovery failed: %s", exc)
        return []


def fetch_from_google_rss() -> list[dict]:
    """Fallback: parse Google News RSS for AI topics."""
    import xml.etree.ElementTree as ET

    articles = []
    for url in RSS_SOURCES:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:10]:
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
    """
    Remove near-duplicate articles by title similarity.

    Duplicates aren't discarded outright — other outlets covering the same
    story are kept on the primary as corroborating sources for the
    research stage.
    """
    seen: dict[str, dict] = {}
    unique = []
    for a in sorted(articles, key=_source_priority):
        # Simple dedup: normalize and check first 50 chars
        key = a["title"].lower().strip()[:50]
        if key not in seen:
            a.setdefault("alt_sources", [])
            seen[key] = a
            unique.append(a)
        else:
            primary = seen[key]
            if a.get("url") and a["url"] != primary.get("url"):
                primary["alt_sources"].append(
                    {"source": a.get("source", ""), "url": a["url"]}
                )
    return unique


def _event_text(article: dict) -> str:
    """Return event-level text from both discovery and researched checkpoints."""
    brief = article.get("brief") or {}
    facts = " ".join(brief.get("key_facts") or [])
    return " ".join(str(value or "") for value in (
        article.get("title"),
        article.get("description"),
        article.get("summary"),
        brief.get("context"),
        facts,
    ))


def _event_tokens(article: dict) -> set[str]:
    text = _event_text(article)
    return {
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in EVENT_STOPWORDS
    }


def _model_event_ids(article: dict) -> set[str]:
    text = _event_text(article)
    return {
        re.sub(r"[^a-z0-9]", "", match.group(0).lower())
        for match in MODEL_EVENT_PATTERN.finditer(text)
    }


def _event_actions(article: dict) -> set[str]:
    text = _event_text(article)
    return {
        action for action, pattern in EVENT_ACTION_PATTERNS.items()
        if pattern.search(text)
    }


def _same_event(left: dict, right: dict) -> bool:
    """Conservatively identify separate articles about one underlying event."""
    left_models = _model_event_ids(left)
    right_models = _model_event_ids(right)
    if left_models & right_models:
        left_actions = _event_actions(left)
        right_actions = _event_actions(right)
        if left_actions and right_actions:
            return bool(left_actions & right_actions)

    left_players = set(left.get("tracked_players") or [])
    right_players = set(right.get("tracked_players") or [])
    if left_players and right_players and not left_players.intersection(right_players):
        return False
    if left.get("editorial_lane") != right.get("editorial_lane"):
        return False

    left_tokens = _event_tokens(left)
    right_tokens = _event_tokens(right)
    union = left_tokens | right_tokens
    return bool(union) and len(left_tokens & right_tokens) / len(union) >= 0.42


def _canonical_event_score(article: dict) -> tuple[int, int, int]:
    title = article.get("title", "")
    return (
        _source_priority(article),
        0 if MAJOR_EVENT_PATTERN.search(title) else 1,
        -len(article.get("description", "")),
    )


def consolidate_topic_events(articles: list[dict]) -> list[dict]:
    """Collapse article-level duplicates into one canonical editorial event."""
    clusters: list[list[dict]] = []
    for article in articles:
        cluster = next(
            (items for items in clusters if _same_event(article, items[0])), None
        )
        if cluster is None:
            clusters.append([article])
        else:
            cluster.append(article)

    consolidated = []
    for cluster in clusters:
        canonical = min(cluster, key=_canonical_event_score)
        primary = dict(canonical)
        sources = list(primary.get("alt_sources") or [])
        supporting = list(primary.get("supporting_articles") or [])
        for item in cluster:
            if item is canonical:
                continue
            supporting.append({
                "title": item.get("title", ""),
                "description": item.get("description") or item.get("summary", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
            })
            if item.get("url") and item.get("url") != primary.get("url"):
                sources.append({"source": item.get("source", ""), "url": item["url"]})
            supporting.extend(item.get("supporting_articles") or [])
            sources.extend(item.get("alt_sources") or [])
        primary["alt_sources"] = list({
            source.get("url", ""): source for source in sources if source.get("url")
        }.values())[:6]
        primary["supporting_articles"] = list({
            source.get("url", ""): source
            for source in supporting if source.get("url")
        }.values())[:6]
        primary["event_article_count"] = sum(
            max(1, int(item.get("event_article_count", 1))) for item in cluster
        )
        primary["must_cover"] = any(bool(item.get("must_cover")) for item in cluster)
        if primary["must_cover"] and not primary.get("must_cover_reason"):
            primary["must_cover_reason"] = next(
                (item.get("must_cover_reason", "") for item in cluster if item.get("must_cover")),
                "High-impact editorial event",
            )
        consolidated.append(primary)
    return consolidated


def _force_priority_stories(
    stories: list[dict], articles: list[dict], priority_indexes: list[int], limit: int = 6
) -> list[dict]:
    """Guarantee audited high-impact candidates survive model ranking."""
    selected_indexes = {s.get("index") for s in stories if isinstance(s.get("index"), int)}
    for idx in priority_indexes:
        if idx in selected_indexes or not 1 <= idx <= len(articles):
            continue
        article = articles[idx - 1]
        forced = {
            "rank": len(stories) + 1,
            "index": idx,
            "title": article["title"],
            "summary": article.get("description", ""),
            "angle": article.get("must_cover_reason") or "High-impact landscape event",
            "category": "main",
            "selection_reason": "coverage_audit",
            "url": article.get("url", ""),
            "source": article.get("source", ""),
            "alt_sources": article.get("alt_sources", [])[:2],
            "tracked_players": article.get("tracked_players", []),
            "editorial_lane": article.get("editorial_lane"),
            "must_cover": bool(article.get("must_cover")),
            "must_cover_reason": article.get("must_cover_reason", ""),
            "event_article_count": article.get("event_article_count", 1),
            "supporting_articles": article.get("supporting_articles", []),
        }
        if len(stories) >= limit:
            replace_at = next(
                (i for i in range(len(stories) - 1, -1, -1)
                 if stories[i].get("index") not in priority_indexes),
                None,
            )
            if replace_at is None:
                break
            stories[replace_at] = forced
        else:
            stories.append(forced)
        selected_indexes.add(idx)
    for rank, story in enumerate(stories[:limit], 1):
        story["rank"] = rank
    return stories[:limit]


def rank_topics(articles: list[dict], audit: dict | None = None) -> list[dict]:
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
        f"{i+1}. {'[MUST COVER] ' if a.get('must_cover') else ''}"
        f"[{a['source']}] {a['title']}: {a['description']}"
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
                    "Coverage obligations:\n"
                    "- Include every [MUST COVER] item unless it is a duplicate or demonstrably false.\n"
                    "- Optimize for an accurate picture of the AI landscape, not merely entertaining conversation.\n"
                    "- Treat frontier model launches, availability/pricing changes, major policy, safety incidents, and major lab moves as high priority.\n\n"
                    "Prioritize:\n"
                    "1. Consequence for the competitive AI landscape\n"
                    "2. Breaking news the hosts can have genuine opinions about\n"
                    "3. Stories with real human impact worth debating\n"
                    "4. Variety across labs and editorial lanes\n\n"
                    "Return JSON: {\"stories\": [{\"rank\": 1, \"index\": <the "
                    "article's number in the list>, \"title\": \"...\", "
                    "\"summary\": \"1-2 sentence summary\", \"angle\": \"why this is "
                    "necessary for understanding the landscape\", \"category\": \"main|lightning\"}], "
                    "\"high_impact_omissions\": [{\"index\": <article number>, \"reason\": \"why excluding it would distort the daily picture\"}]}\n"
                    "Only list an omission when it is at least as consequential as a selected story.\n"
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
        stories = [
            item for item in (result.get("stories") or []) if isinstance(item, dict)
        ]
        model_omissions = [
            item for item in (result.get("high_impact_omissions") or [])
            if isinstance(item, dict)
        ]
        priority_indexes = [
            i for i, article in enumerate(articles, 1) if article.get("must_cover")
        ]
        for omission in model_omissions:
            idx = omission.get("index")
            if isinstance(idx, int) and idx not in priority_indexes:
                priority_indexes.append(idx)
        stories = _force_priority_stories(stories, articles, priority_indexes)
        # Link each ranked story back to its source article so the
        # research stage can fetch the full text
        for s in stories:
            idx = s.get("index")
            src = None
            if isinstance(idx, int) and 1 <= idx <= len(articles):
                src = articles[idx - 1]
            else:
                # Fallback: match by title prefix
                key = (s.get("title") or "").lower().strip()[:40]
                src = next(
                    (a for a in articles if a["title"].lower().strip().startswith(key)),
                    None,
                )
            if src:
                s["url"] = src.get("url", "")
                s["source"] = src.get("source", "")
                s["alt_sources"] = src.get("alt_sources", [])[:2]
                s["tracked_players"] = src.get("tracked_players", [])
                s["editorial_lane"] = src.get("editorial_lane")
                s["must_cover"] = bool(src.get("must_cover"))
                s["must_cover_reason"] = src.get("must_cover_reason", "")
                s["event_article_count"] = src.get("event_article_count", 1)
                s["supporting_articles"] = src.get("supporting_articles", [])
        if audit is not None:
            audit["model_high_impact_omissions"] = model_omissions
            audit["priority_indexes"] = priority_indexes
        return stories
    except (json.JSONDecodeError, IndexError, TypeError, AttributeError) as e:
        logger.error(f"Failed to parse ranked topics: {e}")
        fallback = [
            {
                "rank": i + 1,
                "index": i + 1,
                "title": a["title"],
                "summary": a["description"],
                "angle": "",
                "category": "main" if i < 3 else "lightning",
                "url": a.get("url", ""),
                "source": a.get("source", ""),
                "alt_sources": a.get("alt_sources", [])[:2],
                "tracked_players": a.get("tracked_players", []),
                "editorial_lane": a.get("editorial_lane"),
                "must_cover": bool(a.get("must_cover")),
                "must_cover_reason": a.get("must_cover_reason", ""),
                "event_article_count": a.get("event_article_count", 1),
                "supporting_articles": a.get("supporting_articles", []),
            }
            for i, a in enumerate(articles[:5])
        ]
        priority_indexes = [
            i for i, article in enumerate(articles, 1) if article.get("must_cover")
        ]
        if audit is not None:
            audit["model_high_impact_omissions"] = []
            audit["priority_indexes"] = priority_indexes
        return _force_priority_stories(fallback, articles, priority_indexes)


def _build_editorial_audit(
    articles: list[dict], ranked: list[dict], ranking_audit: dict | None = None
) -> dict:
    selected_indexes = {
        story.get("index") for story in ranked if isinstance(story.get("index"), int)
    }
    selected_reasons = {
        story.get("index"): story.get("selection_reason") or "daily_ranker"
        for story in ranked if isinstance(story.get("index"), int)
    }
    omission_reasons = {
        item.get("index"): item.get("reason", "Model-identified high-impact omission")
        for item in (ranking_audit or {}).get("model_high_impact_omissions", [])
        if isinstance(item, dict) and isinstance(item.get("index"), int)
    }
    candidates = []
    for index, article in enumerate(articles, 1):
        candidates.append({
            "index": index,
            "title": article.get("title", ""),
            "description": article.get("description", ""),
            "source": article.get("source", ""),
            "url": article.get("url", ""),
            "published": article.get("published", ""),
            "tracked_players": article.get("tracked_players", []),
            "editorial_lane": article.get("editorial_lane"),
            "must_cover": bool(article.get("must_cover")),
            "must_cover_reason": article.get("must_cover_reason", ""),
            "selected": index in selected_indexes,
            "selection_reason": (
                selected_reasons.get(index)
                or omission_reasons.get(index)
                or "Below the daily editorial cutoff"
            ),
        })
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "candidate_count": len(candidates),
        "selected_count": len(ranked),
        "candidates": candidates,
        "unresolved_must_cover": [
            item for item in candidates if item["must_cover"] and not item["selected"]
        ],
    }


def discover_topics_with_audit() -> tuple[list[dict], dict]:
    """
    Main entry point. Fetches news from all sources, deduplicates, and ranks.
    Returns ranked list of topics ready for script generation.
    """
    logger.info("Discovering today's topics...")

    # Fetch from all sources
    articles = fetch_from_newsapi()
    articles.extend(fetch_official_updates())
    if len(articles) < 5:
        logger.info("Supplementing with Google RSS...")
        articles.extend(fetch_from_google_rss())

    logger.info(f"Found {len(articles)} raw articles")

    # Deduplicate
    articles = audit_candidates(deduplicate(articles))
    article_count = len(articles)
    articles = consolidate_topic_events(articles)
    logger.info(
        "%d unique articles consolidated into %d editorial events",
        article_count,
        len(articles),
    )

    # Rank
    ranking_audit: dict = {}
    ranked = rank_topics(articles, audit=ranking_audit)
    logger.info(f"Selected {len(ranked)} topics for today's episode")
    audit = _build_editorial_audit(articles, ranked, ranking_audit)
    audit.update(ranking_audit)
    if audit["unresolved_must_cover"]:
        logger.warning(
            "Coverage audit left %d must-cover candidate(s) unselected",
            len(audit["unresolved_must_cover"]),
        )
    return ranked, audit


def discover_topics() -> list[dict]:
    """Backward-compatible topic discovery entry point."""
    topics, _ = discover_topics_with_audit()
    return topics


def audit_existing_topics(topics: list[dict]) -> dict:
    """Create a conservative audit when resuming a pre-audit topic checkpoint."""
    articles = []
    ranked = []
    for index, topic in enumerate(topics, 1):
        article = dict(topic)
        article["index"] = index
        article.setdefault("tracked_players", _players_for(
            f"{article.get('title', '')} {article.get('summary', '')}"
        ))
        article.setdefault("editorial_lane", _editorial_lane(article.get("title", "")))
        article.setdefault("must_cover", False)
        articles.append(article)
        ranked.append({**topic, "index": index, "selection_reason": "resumed_checkpoint"})
    audit = _build_editorial_audit(articles, ranked)
    audit["checkpoint_reconstruction"] = True
    return audit
