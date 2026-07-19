"""Weekly AI landscape state and editorial-audit history.

Friday episodes compare a structured player snapshot with the prior week and
the last seven days of researched coverage. Durable copies live in R2; local
episode checkpoints remain the source used by the current production run.
"""

import io
import json
import logging
from datetime import datetime, timedelta

import config
from distribution.podcast_host import _r2_client, hosting_configured
from pipeline.cost_tracker import tracker
from pipeline.topics import TRACKED_PLAYERS

logger = logging.getLogger(__name__)

SNAPSHOT_KEY = "memory/landscape_snapshot.json"
AUDIT_HISTORY_KEY = "memory/editorial_audits.json"
AUDIT_RETENTION_DAYS = 14
WEEKLY_REVIEW_WEEKDAY = 4  # Monday=0, Friday=4
TRAJECTORIES = {"rising", "steady", "slipping", "unclear"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}


def is_weekly_review(date_str: str) -> bool:
    """Return whether this production date is the Friday weekly review."""
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() == WEEKLY_REVIEW_WEEKDAY


def _download_json(key: str, default):
    if not hosting_configured():
        return default
    try:
        buf = io.BytesIO()
        _r2_client().download_fileobj(config.R2_BUCKET_NAME, key, buf)
        return json.loads(buf.getvalue().decode("utf-8"))
    except Exception as exc:
        logger.info("No durable %s loaded (%s)", key, exc)
        return default


def _upload_json(key: str, payload) -> None:
    if not hosting_configured():
        logger.info("R2 unavailable; not persisting %s", key)
        return
    body = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
    _r2_client().upload_fileobj(
        io.BytesIO(body),
        config.R2_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": "application/json"},
    )


def load_landscape_snapshot() -> dict | None:
    """Load the most recently published Friday snapshot."""
    return _download_json(SNAPSHOT_KEY, None)


def persist_landscape_snapshot(snapshot: dict) -> None:
    """Publish a successfully produced Friday snapshot as durable state."""
    _upload_json(SNAPSHOT_KEY, snapshot)
    logger.info("Landscape snapshot persisted for %s", snapshot.get("week_end"))


def load_editorial_audits() -> list[dict]:
    """Load recent daily candidate/selection audits, oldest first."""
    history = _download_json(AUDIT_HISTORY_KEY, [])
    return history if isinstance(history, list) else []


def persist_editorial_audit(audit: dict, date_str: str) -> None:
    """Append one successfully published day's coverage audit to R2."""
    history = [item for item in load_editorial_audits() if item.get("date") != date_str]
    history.append({**audit, "date": date_str})
    cutoff = (
        datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=AUDIT_RETENTION_DAYS)
    ).strftime("%Y-%m-%d")
    history = sorted(
        (item for item in history if item.get("date", "") >= cutoff),
        key=lambda item: item.get("date", ""),
    )
    _upload_json(AUDIT_HISTORY_KEY, history)
    logger.info("Editorial audit history persisted (%d days)", len(history))


def _evidence_item(
    *, date: str, title: str, source: str = "", url: str = "",
    summary: str = "", facts: list[str] | None = None,
    players: list[str] | None = None,
    selected: bool = False, must_cover: bool = False,
) -> dict:
    return {
        "date": date,
        "title": title,
        "summary": summary,
        "source": source,
        "url": url,
        "facts": (facts or [])[:3],
        "players": players or [],
        "selected": selected,
        "must_cover": must_cover,
    }


def _weekly_evidence(topics: list[dict], audit: dict, date_str: str) -> list[dict]:
    from pipeline.memory import load_threads

    start = (
        datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=6)
    ).strftime("%Y-%m-%d")
    evidence: list[dict] = []

    for day in load_threads():
        if not start <= day.get("date", "") < date_str:
            continue
        for story in day.get("stories", []):
            evidence.append(_evidence_item(
                date=day["date"],
                title=story.get("title", ""),
                summary=story.get("summary", ""),
                source=story.get("source", ""),
                url=story.get("url", ""),
                facts=story.get("facts", []),
                players=story.get("tracked_players", []),
                selected=True,
                must_cover=bool(story.get("must_cover")),
            ))

    omission_indexes = {
        item.get("index")
        for item in audit.get("model_high_impact_omissions", [])
        if isinstance(item.get("index"), int)
    }
    audits = [
        item for item in load_editorial_audits()
        if start <= item.get("date", "") < date_str
    ] + [{**audit, "date": date_str}]
    for day in audits:
        day_omissions = {
            item.get("index")
            for item in day.get("model_high_impact_omissions", [])
            if isinstance(item.get("index"), int)
        }
        if day.get("date") == date_str:
            day_omissions |= omission_indexes
        for candidate in day.get("candidates", []):
            if not (
                candidate.get("selected")
                or candidate.get("must_cover")
                or candidate.get("index") in day_omissions
            ):
                continue
            evidence.append(_evidence_item(
                date=day.get("date", ""),
                title=candidate.get("title", ""),
                summary=candidate.get("description", ""),
                source=candidate.get("source", ""),
                url=candidate.get("url", ""),
                players=candidate.get("tracked_players", []),
                selected=bool(candidate.get("selected")),
                must_cover=bool(candidate.get("must_cover")),
            ))

    for topic in topics:
        brief = topic.get("brief") or {}
        evidence.append(_evidence_item(
            date=date_str,
            title=topic.get("title", ""),
            summary=topic.get("summary", ""),
            source=topic.get("source", ""),
            url=topic.get("url", ""),
            facts=brief.get("key_facts", []),
            players=topic.get("tracked_players", []),
            selected=True,
            must_cover=bool(topic.get("must_cover")),
        ))

    unique: dict[tuple[str, str], dict] = {}
    for item in evidence:
        key = (item["date"], item["title"].lower().strip())
        existing = unique.get(key)
        if not existing or (item["facts"] and not existing["facts"]):
            unique[key] = item
    return list(unique.values())


def _weekly_coverage_metrics(audit: dict, date_str: str) -> dict:
    """Compute auditable seven-day coverage measurements without model judgment."""
    start = (
        datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=6)
    ).strftime("%Y-%m-%d")
    audits = [
        item for item in load_editorial_audits()
        if start <= item.get("date", "") < date_str
    ] + [{**audit, "date": date_str}]
    candidates = [
        candidate for day in audits for candidate in day.get("candidates", [])
    ]
    must_cover = [item for item in candidates if item.get("must_cover")]
    must_cover_selected = [item for item in must_cover if item.get("selected")]
    players_seen = sorted({
        player for item in candidates for player in item.get("tracked_players", [])
    })
    players_covered = sorted({
        player for item in candidates if item.get("selected")
        for player in item.get("tracked_players", [])
    })
    recall = (
        round(len(must_cover_selected) / len(must_cover) * 100, 1)
        if must_cover else 100.0
    )
    return {
        "days_audited": len(audits),
        "candidate_count": len(candidates),
        "must_cover_count": len(must_cover),
        "must_cover_selected": len(must_cover_selected),
        "must_cover_recall_percent": recall,
        "tracked_players_seen": players_seen,
        "tracked_players_covered": players_covered,
        "unresolved_must_cover": [
            item.get("title", "") for item in must_cover if not item.get("selected")
        ][:10],
    }


def _normalize_snapshot(
    raw: dict,
    previous: dict | None,
    date_str: str,
    allowed_urls: set[str] | None = None,
) -> dict:
    prior_players = {
        item.get("id"): item for item in (previous or {}).get("players", [])
    }
    returned_players = {
        item.get("id"): item for item in raw.get("players", [])
        if item.get("id") in TRACKED_PLAYERS
    }
    players = []
    for player_id, definition in TRACKED_PLAYERS.items():
        prior = prior_players.get(player_id, {})
        item = returned_players.get(player_id, {})
        trajectory = item.get("trajectory", "unclear")
        confidence = item.get("confidence", "low")
        evidence = (item.get("evidence") or [])[:4]
        if allowed_urls is not None:
            evidence = [
                source for source in evidence if source.get("url") in allowed_urls
            ]
        changed = bool(item.get("changed"))
        if trajectory in {"rising", "slipping"}:
            if evidence:
                changed = True
            else:
                trajectory = "unclear"
        if changed and not evidence:
            changed = False
            trajectory = "unclear"
            confidence = "low"
        prior_flagship = prior.get("current_flagship")
        proposed_flagship = item.get("current_flagship")
        if str(proposed_flagship or "").lower() == "unknown":
            proposed_flagship = None
        if (
            allowed_urls is not None
            and proposed_flagship
            and proposed_flagship != prior_flagship
            and not evidence
        ):
            proposed_flagship = None
        players.append({
            "id": player_id,
            "name": definition["name"],
            "current_flagship": proposed_flagship or prior_flagship or "Unknown",
            "changed": changed,
            "change_summary": (
                item.get("change_summary")
                if changed or evidence
                else "No verified material change this week."
            ),
            "trajectory": trajectory if trajectory in TRAJECTORIES else "unclear",
            "confidence": confidence if confidence in CONFIDENCE_LEVELS else "low",
            "evidence": evidence,
            "last_covered": item.get("last_covered") or prior.get("last_covered"),
            "watch_next": item.get("watch_next") or prior.get("watch_next") or "No specific watch item.",
        })
    end = datetime.strptime(date_str, "%Y-%m-%d")
    def sourced(items: list[dict], url_field: str = "evidence_url") -> list[dict]:
        if allowed_urls is None:
            return items
        return [item for item in items if item.get(url_field) in allowed_urls]

    return {
        "schema_version": 1,
        "week_start": (end - timedelta(days=6)).strftime("%Y-%m-%d"),
        "week_end": date_str,
        "headline": raw.get("headline") or "The AI landscape this week",
        "summary": raw.get("summary") or "A sourced weekly status of the leading AI labs.",
        "top_moves": sourced((raw.get("top_moves") or [])[:3]),
        "under_the_radar": sourced((raw.get("under_the_radar") or [])[:2]),
        "hype_check": sourced((raw.get("hype_check") or [])[:2]),
        "next_week": (raw.get("next_week") or [])[:4],
        "players": players,
    }


def generate_landscape_snapshot(
    topics: list[dict], audit: dict, date_str: str
) -> dict:
    """Generate the evidence-grounded snapshot used by Friday's episode and site."""
    from openai import OpenAI

    previous = load_landscape_snapshot()
    evidence = _weekly_evidence(topics, audit, date_str)
    player_registry = {
        player_id: player["name"] for player_id, player in TRACKED_PLAYERS.items()
    }
    prompt = {
        "week_ending": date_str,
        "tracked_players": player_registry,
        "previous_snapshot": previous,
        "evidence": evidence,
    }
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=3000,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You maintain a weekly, evidence-grounded map of the AI landscape. "
                    "Use ONLY the supplied evidence and previous snapshot. Do not infer a "
                    "new flagship, movement, or benchmark result from outside knowledge. "
                    "If evidence is insufficient, say Unknown or use trajectory 'unclear'. "
                    "Carry forward a prior flagship only when no supplied evidence changes it. "
                    "A player with no verified material change must have changed=false. "
                    "Evidence entries must include claim, source_title, url, and date copied "
                    "from the supplied evidence; never invent a URL. Return JSON with: "
                    "headline, summary, top_moves (max 3: player_ids, summary, evidence_url), "
                    "under_the_radar (max 2: summary, evidence_url), hype_check (max 2: "
                    "summary, evidence_url), next_week (max 4 strings), and players. Each "
                    "player: id, current_flagship, changed, change_summary, trajectory "
                    "(rising|steady|slipping|unclear), confidence (high|medium|low), evidence "
                    "(max 4), last_covered (YYYY-MM-DD or null), watch_next. Include every "
                    "tracked player exactly once. Rising/slipping requires explicit evidence."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    usage = response.usage
    if usage:
        tracker.record(
            step="landscape_snapshot",
            model="gpt-4o-mini",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )
    raw = json.loads(response.choices[0].message.content)
    allowed_urls = {item["url"] for item in evidence if item.get("url")}
    snapshot = _normalize_snapshot(raw, previous, date_str, allowed_urls)
    snapshot["evidence_count"] = len(evidence)
    snapshot["coverage_metrics"] = _weekly_coverage_metrics(audit, date_str)
    return snapshot


def compact_landscape_context(snapshot: dict | None) -> str:
    """Serialize only the sourced fields the showrunner and hosts need."""
    if not snapshot:
        return "(no weekly landscape snapshot available)"
    return json.dumps({
        "headline": snapshot.get("headline"),
        "summary": snapshot.get("summary"),
        "top_moves": snapshot.get("top_moves", []),
        "under_the_radar": snapshot.get("under_the_radar", []),
        "hype_check": snapshot.get("hype_check", []),
        "next_week": snapshot.get("next_week", []),
        "players": [
            item for item in snapshot.get("players", [])
            if item.get("changed") or item.get("trajectory") != "steady"
        ],
    }, ensure_ascii=False, indent=1)


def friday_review_profile(
    snapshot: dict | None,
    topics: list[dict] | None = None,
    max_duration: int | None = None,
) -> dict:
    """Size Friday's weekly component from distinct, verified developments."""
    from pipeline.topics import consolidate_topic_events

    snapshot = snapshot or {}
    weekly_items = []
    for field in ("top_moves", "under_the_radar", "hype_check"):
        for item in snapshot.get(field, []) or []:
            summary = item.get("summary", "")
            if not summary or not item.get("evidence_url"):
                continue
            weekly_items.append({
                "title": summary,
                "description": summary,
                "url": item.get("evidence_url", ""),
                "source": "weekly landscape",
                "tracked_players": item.get("player_ids", []),
                "editorial_lane": "models_products",
            })
    topic_events = consolidate_topic_events(topics or [])
    topic_url_sets = []
    for topic in topic_events:
        urls = {topic.get("url", "")}
        urls.update(
            source.get("url", "") for source in topic.get("alt_sources", [])
        )
        urls.update(
            source.get("url", "")
            for source in topic.get("supporting_articles", [])
        )
        topic_url_sets.append(urls - {""})

    matched_topic_events = set()
    unmatched_weekly_items = []
    for item in weekly_items:
        match = next(
            (
                index for index, urls in enumerate(topic_url_sets)
                if item.get("url") in urls
            ),
            None,
        )
        if match is None:
            unmatched_weekly_items.append(item)
        else:
            matched_topic_events.add(match)
    weekly_event_count = len(matched_topic_events) + len(
        consolidate_topic_events(unmatched_weekly_items)
    )
    verified_players = {
        player_id
        for move in snapshot.get("top_moves", []) or []
        if move.get("evidence_url")
        for player_id in move.get("player_ids", [])
    }
    daily_event_count = len(topic_events)
    activity_score = weekly_event_count + len(verified_players)
    ceiling = max(4, max_duration or config.EPISODE_DURATION_MINUTES)

    if activity_score <= 2:
        scale = "quiet"
        duration = min(ceiling, 6)
        review_share = 0.25
        review_turns = 1
    elif activity_score <= 5:
        scale = "standard"
        duration = min(ceiling, 8)
        review_share = 0.5
        review_turns = 2
    else:
        scale = "dominant"
        duration = ceiling
        review_share = 0.75
        review_turns = 4

    return {
        "scale": scale,
        "target_duration_minutes": duration,
        "weekly_review_share": review_share,
        "weekly_review_turns_per_speaker": review_turns,
        "activity_score": activity_score,
        "distinct_weekly_events": weekly_event_count,
        "verified_players_moved": len(verified_players),
        "distinct_daily_events": daily_event_count,
    }
