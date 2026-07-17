"""
Story memory.
The show's cross-episode brain: which stories it has covered, what the
facts were, and what each host predicted. Lives in R2 next to the feed
state so the ephemeral CI runner remembers yesterday.

Gives the show two "real news desk" behaviors:
- developing stories ("when we covered this Tuesday, X — today it's Y")
- prediction accountability ("I said Apple would respond in 48h. I was wrong.")
"""

import json
import logging
from datetime import datetime, timedelta

import config
from pipeline.cost_tracker import tracker
from distribution.podcast_host import hosting_configured, _r2_client

logger = logging.getLogger(__name__)

MEMORY_KEY = "memory/story_threads.json"
RETENTION_DAYS = 30
MATCH_WINDOW_DAYS = 14


def load_threads() -> list[dict]:
    """Episode-history entries, oldest first. Empty when unavailable."""
    if not hosting_configured():
        return []
    try:
        import io

        s3 = _r2_client()
        buf = io.BytesIO()
        s3.download_fileobj(config.R2_BUCKET_NAME, MEMORY_KEY, buf)
        return json.loads(buf.getvalue().decode("utf-8"))
    except Exception as e:
        logger.info(f"No story memory loaded ({e}) — starting fresh")
        return []


def _save_threads(threads: list[dict]) -> None:
    if not hosting_configured():
        return
    try:
        import io

        s3 = _r2_client()
        body = json.dumps(threads, ensure_ascii=False, indent=1).encode("utf-8")
        s3.upload_fileobj(
            io.BytesIO(body), config.R2_BUCKET_NAME, MEMORY_KEY,
            ExtraArgs={"ContentType": "application/json"},
        )
        logger.info(f"Story memory saved ({len(threads)} days)")
    except Exception as e:
        logger.error(f"Failed to save story memory: {e}")


def _extract_predictions(script: dict) -> list[dict]:
    """Pull each host's 'one thing to watch' out of the sign-off."""
    sign_off = next(
        (s for s in script.get("segments", []) if s.get("type") == "sign_off"),
        None,
    )
    if not sign_off:
        return []
    convo = "\n".join(
        f"{l['speaker']}: {l['text']}" for l in sign_off.get("dialogue", [])
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            max_tokens=300,
            messages=[
                {"role": "system", "content": (
                    "Extract each speaker's forward-looking prediction from this "
                    "podcast sign-off. Return JSON: {\"predictions\": [{\"host\": "
                    "\"...\", \"prediction\": \"one sentence, specific and "
                    "checkable\"}]}. If a speaker made no real prediction, omit them."
                )},
                {"role": "user", "content": convo},
            ],
        )
        usage = resp.usage
        if usage:
            tracker.record(
                step="memory", model="gpt-4o-mini",
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
            )
        return json.loads(resp.choices[0].message.content).get("predictions", [])
    except Exception as e:
        logger.warning(f"Prediction extraction failed: {e}")
        return []


def update_after_episode(topics: list[dict], script: dict, date_str: str) -> None:
    """Append today's coverage + predictions to memory; prune old days."""
    if not hosting_configured():
        return
    threads = load_threads()
    threads = [t for t in threads if t.get("date") != date_str]  # idempotent re-runs

    stories = []
    for t in topics:
        brief = t.get("brief") or {}
        stories.append({
            "title": t["title"],
            "category": t.get("category", "main"),
            "facts": (brief.get("key_facts") or [])[:3],
        })

    threads.append({
        "date": date_str,
        "episode_title": script.get("title", ""),
        "stories": stories,
        "predictions": _extract_predictions(script),
    })

    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    threads = [t for t in threads if t.get("date", "") >= cutoff]
    threads.sort(key=lambda t: t.get("date", ""))
    _save_threads(threads)


def enrich_with_memory(topics: list[dict], date_str: str) -> list[dict] | None:
    """
    Attach prior coverage to today's topics and return yesterday's
    predictions (None when memory is unavailable/empty).

    topics gain topic["prior_coverage"] = [{date, title, facts}] where a
    past story matches.
    """
    threads = load_threads()
    if not threads:
        return None

    cutoff = (datetime.now() - timedelta(days=MATCH_WINDOW_DAYS)).strftime("%Y-%m-%d")
    past = [
        {"date": day["date"], "title": s["title"], "facts": s.get("facts", [])}
        for day in threads if day.get("date", "") >= cutoff and day.get("date") != date_str
        for s in day.get("stories", [])
    ]

    if past:
        past_text = "\n".join(
            f"{i}. ({p['date']}) {p['title']}" for i, p in enumerate(past)
        )
        today_text = "\n".join(f"{i}. {t['title']}" for i, t in enumerate(topics))
        try:
            from openai import OpenAI

            client = OpenAI(api_key=config.OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                max_tokens=300,
                messages=[
                    {"role": "system", "content": (
                        "Match today's news stories against this show's past "
                        "coverage. Two items match ONLY if they concern the same "
                        "developing story (same company/event/lawsuit/product — "
                        "not merely the same theme). Return JSON: {\"matches\": "
                        "[{\"today\": <today index>, \"past\": [<past indexes>]}]}"
                    )},
                    {"role": "user", "content": (
                        f"TODAY'S STORIES:\n{today_text}\n\nPAST COVERAGE:\n{past_text}"
                    )},
                ],
            )
            usage = resp.usage
            if usage:
                tracker.record(
                    step="memory", model="gpt-4o-mini",
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                )
            for m in json.loads(resp.choices[0].message.content).get("matches", []):
                ti = m.get("today")
                if isinstance(ti, int) and 0 <= ti < len(topics):
                    prior = [
                        past[pi] for pi in m.get("past", [])
                        if isinstance(pi, int) and 0 <= pi < len(past)
                    ][:3]
                    if prior:
                        topics[ti]["prior_coverage"] = prior
                        logger.info(
                            f"Follow-up story: '{topics[ti]['title'][:50]}' "
                            f"({len(prior)} prior mentions)"
                        )
        except Exception as e:
            logger.warning(f"Prior-coverage matching failed: {e}")

    # Yesterday's predictions = most recent day before today with any
    latest = next(
        (day for day in reversed(threads)
         if day.get("date") != date_str and day.get("predictions")),
        None,
    )
    if latest:
        return [
            {**p, "date": latest["date"]} for p in latest["predictions"]
        ]
    return None
