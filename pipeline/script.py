"""
Script generator.
Orchestrates a conversation between AI hosts (and optional guests)
to produce a full podcast episode script.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic
from openai import OpenAI

import config
from pipeline.cost_tracker import tracker

logger = logging.getLogger(__name__)

SCRIPT_FORMAT_VERSION = 7
MAX_TURN_WORDS = 48
MAX_SENTENCE_WORDS = 22
SIGNOFF_CTA = config.PODCAST_SIGNOFF_CTA

_INVALID_JSON_ESCAPE = re.compile(r'\\(?!["\\/bfnrtu])')


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = config.PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _json_payload(text: str) -> str:
    """Extract a JSON object from plain text or a fenced model response."""
    if "```json" in text:
        return text.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    return text.strip()


def _parse_plan_json(text: str) -> dict:
    """Parse a plan, repairing only backslashes that are invalid in JSON."""
    payload = _json_payload(text)
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        repaired = _INVALID_JSON_ESCAPE.sub(r"\\\\", payload)
        if repaired == payload:
            raise
        logger.warning("Repaired invalid backslash escape in showrunner JSON")
        return json.loads(repaired)


def _topics_block(topics: list[dict]) -> str:
    """Serialize topics + researched fact briefs for the showrunner."""
    blocks = []
    for t in topics:
        lines = [
            f"### [{t.get('category', 'main').upper()}]"
            f"{' [MUST COVER]' if t.get('must_cover') else ''} {t['title']}",
            f"Summary: {t.get('summary', '')}",
        ]
        if t.get("angle"):
            lines.append(f"Angle: {t['angle']}")
        for pc in t.get("prior_coverage", []):
            facts = "; ".join(pc.get("facts", [])[:2])
            lines.append(
                f"- PRIOR COVERAGE (this show, {pc.get('date')}): "
                f"\"{pc.get('title')}\"" + (f" — {facts}" if facts else "")
            )
        brief = t.get("brief")
        if brief:
            if brief.get("context"):
                lines.append(f"Background: {brief['context']}")
            for fact in brief.get("key_facts", []):
                lines.append(f"- FACT: {fact}")
            for nq in brief.get("numbers_and_quotes", []):
                lines.append(f"- QUOTE/NUMBER: {nq}")
            for q in brief.get("open_questions", []):
                lines.append(f"- OPEN QUESTION: {q}")
            if brief.get("sources"):
                lines.append(f"Sources: {', '.join(brief['sources'])}")
        else:
            lines.append(
                "(No full article was retrievable — only the summary above is "
                "verified. The hosts must stay high-level on this one.)"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _build_episode_prompt(
    topics: list[dict],
    date: str,
    roster: list[str],
    prior_predictions: list[dict] | None = None,
    special_note: str = "",
    episode_mode: str = "daily",
    landscape: dict | None = None,
    friday_profile: dict | None = None,
) -> str:
    """Fill in the showrunner template with today's topics and roster."""
    template_name = (
        "weekly_showrunner.txt" if episode_mode == "weekly_landscape"
        else "showrunner.txt"
    )
    template = _load_prompt(template_name)
    if episode_mode == "weekly_landscape":
        from pipeline.landscape import friday_review_profile
        friday_profile = friday_profile or friday_review_profile(landscape, topics)
    else:
        friday_profile = {}

    duration = friday_profile.get(
        "target_duration_minutes", config.EPISODE_DURATION_MINUTES
    )
    word_count = duration * 150  # ~150 words/min spoken
    min_word_count = int(word_count * 0.8)  # hard floor

    # Friday's length and weekly share are evidence-sized. Daily episodes retain
    # their existing duration calibration.
    if episode_mode == "weekly_landscape":
        friday_scale = friday_profile["scale"]
        if friday_scale == "quiet":
            main_story_count = 2
            main_exchanges = 2
            cold_open_exchanges = 1
            lightning_exchanges = 1
            signoff_exchanges = 1
            segment_range = "exactly 5"
            weekly_segment_range = "exactly 1 compact segment"
        elif friday_scale == "standard":
            main_story_count = 2
            main_exchanges = 3
            cold_open_exchanges = 1
            lightning_exchanges = 1
            signoff_exchanges = 1
            segment_range = "5-6"
            weekly_segment_range = "1-2 segments"
        else:
            main_story_count = 1
            main_exchanges = 5
            cold_open_exchanges = 2
            lightning_exchanges = 2
            signoff_exchanges = 2
            segment_range = "6-7"
            weekly_segment_range = "2-3 segments; it may be the episode's spine"
    elif duration >= 25:
        main_story_count = 3
        main_exchanges = 12       # deep dives, ~5-7 min each
        cold_open_exchanges = 3
        lightning_exchanges = 4
        signoff_exchanges = 4
    elif duration >= 15:
        main_story_count = 2
        main_exchanges = 8
        cold_open_exchanges = 2
        lightning_exchanges = 3
        signoff_exchanges = 3
    else:
        main_story_count = 2
        main_exchanges = 5
        cold_open_exchanges = 2
        lightning_exchanges = 2
        signoff_exchanges = 2

    if episode_mode != "weekly_landscape":
        friday_scale = "not_applicable"
        segment_range = "as specified below"
        weekly_segment_range = "not applicable"

    # Build dynamic host description
    speaker_parts = []
    for name in roster:
        company = config.SPEAKERS[name]["company"]
        role = config.SPEAKERS[name]["role"]
        if role == "guest":
            speaker_parts.append(f"guest {name} ({company})")
        else:
            speaker_parts.append(f"{name} ({company})")

    if len(speaker_parts) == 2:
        hosts_description = f"hosted by {speaker_parts[0]} and {speaker_parts[1]}"
    else:
        hosts_description = (
            "hosted by "
            + ", ".join(speaker_parts[:-1])
            + f", and {speaker_parts[-1]}"
        )

    speaker_names = ", ".join(f'"{name}"' for name in roster)

    # Build optional guest segment text
    guests_in_roster = [n for n in roster if config.SPEAKERS[n]["role"] == "guest"]
    if guests_in_roster:
        guest_names = " and ".join(guests_in_roster)
        guest_segment = (
            f"3b. GUEST SPOTLIGHT — {guest_names} shares a unique perspective "
            f"on one main story. Hosts ask pointed questions. ({main_exchanges} exchanges)\n"
        )
    else:
        guest_segment = ""

    topics_text = _topics_block(topics)

    if prior_predictions:
        predictions_text = "\n".join(
            f"- {p.get('host', '?')} predicted (on {p.get('date', '?')}): "
            f"{p.get('prediction', '')}"
            for p in prior_predictions
        )
    else:
        predictions_text = "(none on record — skip the accountability beat)"

    special_note_text = special_note or "(none — do not invent an announcement)"
    if landscape:
        from pipeline.landscape import compact_landscape_context
        landscape_text = compact_landscape_context(landscape)
    else:
        landscape_text = "(not a weekly landscape episode)"

    return template.format(
        date=date,
        topics=topics_text,
        predictions=predictions_text,
        special_note=special_note_text,
        landscape=landscape_text,
        duration=duration,
        word_count=word_count,
        min_word_count=min_word_count,
        hosts_description=hosts_description,
        show_title=config.PODCAST_TITLE,
        publication_format=config.PUBLICATION_FORMAT,
        publication_audience=config.PUBLICATION_AUDIENCE,
        signoff_instruction=config.PODCAST_SIGNOFF_INSTRUCTION,
        speaker_names=speaker_names,
        guest_segment=guest_segment,
        main_story_count=main_story_count,
        main_exchanges=main_exchanges,
        cold_open_exchanges=cold_open_exchanges,
        lightning_exchanges=lightning_exchanges,
        signoff_exchanges=signoff_exchanges,
        friday_scale=friday_scale,
        weekly_review_percent=round(
            friday_profile.get("weekly_review_share", 0) * 100
        ),
        weekly_review_turns=friday_profile.get(
            "weekly_review_turns_per_speaker", 0
        ),
        friday_activity_score=friday_profile.get("activity_score", 0),
        distinct_weekly_events=friday_profile.get("distinct_weekly_events", 0),
        distinct_daily_events=friday_profile.get("distinct_daily_events", 0),
        verified_players_moved=friday_profile.get("verified_players_moved", 0),
        segment_range=segment_range,
        weekly_segment_range=weekly_segment_range,
    )


def generate_script(
    topics: list[dict],
    roster: list[str] | None = None,
    prior_predictions: list[dict] | None = None,
    special_note: str = "",
    episode_date: str | None = None,
    episode_mode: str = "daily",
    landscape: dict | None = None,
    friday_profile: dict | None = None,
) -> dict:
    """
    Generate the full episode script.

    Strategy:
    1. Showrunner pass (Claude): plan the segments — beats, leads, and
       conflict-of-interest flags. No dialogue.
    2. Turn-by-turn conversation: each speaker's OWN model writes each of
       its turns as a reply to what was actually said before it, grounded
       in the researched fact briefs.

    Returns the complete script as a dict with title, description, segments, and roster.
    """
    if roster is None:
        roster = config.get_episode_roster()

    if episode_mode == "weekly_landscape" and not friday_profile:
        from pipeline.landscape import friday_review_profile
        friday_profile = friday_review_profile(landscape, topics)

    if episode_date:
        date_str = datetime.strptime(episode_date, "%Y-%m-%d").strftime("%B %d, %Y")
    else:
        date_str = datetime.now().strftime("%B %d, %Y")

    logger.info("Step 1: Showrunner pass — planning segments and beats...")
    plan = _generate_episode_plan(
        topics,
        date_str,
        roster,
        prior_predictions,
        special_note=special_note,
        episode_mode=episode_mode,
        landscape=landscape,
        friday_profile=friday_profile,
    )

    logger.info("Step 2: Turn-by-turn conversation — each host speaks for itself...")
    final_script = _run_conversation(
        plan,
        topics,
        roster,
        date_str,
        special_note=special_note,
        landscape=landscape,
    )
    _enforce_signoff_cta(final_script, roster)

    logger.info("Step 3: Generating YouTube-optimized title...")
    final_script["youtube_title"] = _generate_youtube_title(final_script, topics)

    # Attach roster metadata for downstream consumers
    final_script["roster"] = roster
    final_script["special_note"] = special_note
    final_script["episode_mode"] = episode_mode
    final_script["landscape_week_end"] = (landscape or {}).get("week_end")
    final_script["friday_profile"] = friday_profile or None
    final_script["target_duration_minutes"] = (
        (friday_profile or {}).get("target_duration_minutes")
        or config.EPISODE_DURATION_MINUTES
    )
    final_script["script_format_version"] = SCRIPT_FORMAT_VERSION

    return final_script


def _generate_episode_plan(
    topics: list[dict],
    date_str: str,
    roster: list[str],
    prior_predictions: list[dict] | None = None,
    special_note: str = "",
    episode_mode: str = "daily",
    landscape: dict | None = None,
    friday_profile: dict | None = None,
) -> dict:
    """Showrunner pass: Claude plans the episode structure — no dialogue."""
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    episode_prompt = _build_episode_prompt(
        topics,
        date_str,
        roster,
        prior_predictions,
        special_note=special_note,
        episode_mode=episode_mode,
        landscape=landscape,
        friday_profile=friday_profile,
    )

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=6000,
        # Keep thinking off — Sonnet 5 enables it by default, which spends
        # output tokens and adds non-text blocks to response.content
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": episode_prompt}],
        system=(
            f"You are the showrunner of a {episode_mode.replace('_', ' ')} podcast. Plan the episode as "
            "specified. Return ONLY valid JSON — structure and beats, never "
            "dialogue."
        ),
    )

    tracker.record(
        step="episode_plan",
        model=config.CLAUDE_MODEL,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        speaker="Claude",
    )

    text = next(b.text for b in response.content if b.type == "text")

    try:
        plan = _parse_plan_json(text)
    except json.JSONDecodeError as first_error:
        logger.warning(
            "Showrunner returned malformed JSON (%s); requesting one repair",
            first_error,
        )
        repair = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=6000,
            thinking={"type": "disabled"},
            system=(
                "You repair malformed JSON. Return ONLY the corrected JSON object. "
                "Preserve every field and value; change only syntax required to parse."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Parser error: {first_error}\n\n"
                    "Repair this showrunner plan:\n"
                    f"{text}"
                ),
            }],
        )
        tracker.record(
            step="episode_plan_repair",
            model=config.CLAUDE_MODEL,
            input_tokens=repair.usage.input_tokens,
            output_tokens=repair.usage.output_tokens,
            speaker="Claude",
        )
        repaired_text = next(b.text for b in repair.content if b.type == "text")
        try:
            plan = _parse_plan_json(repaired_text)
        except json.JSONDecodeError as final_error:
            logger.error("Failed to parse repaired episode plan: %s", final_error)
            logger.debug("Raw repaired response: %s", repaired_text[:500])
            raise

    n_segs = len(plan.get("segments", []))
    logger.info(f"Episode plan: '{plan.get('title', '?')}' with {n_segs} segments")
    return plan


# ---------------------------------------------------------------------------
# API client factory
# ---------------------------------------------------------------------------

def _get_api_clients(roster: list[str]) -> dict:
    """
    Create API clients for each speaker in the roster.
    Skips speakers whose API keys are not configured.
    Returns {speaker_name: client_instance}.
    """
    clients = {}

    for speaker in roster:
        speaker_config = config.SPEAKERS[speaker]
        api_type = speaker_config["api_type"]

        try:
            if api_type == "anthropic" and config.ANTHROPIC_API_KEY:
                clients[speaker] = Anthropic(api_key=config.ANTHROPIC_API_KEY)
            elif api_type == "openai" and config.OPENAI_API_KEY:
                clients[speaker] = OpenAI(api_key=config.OPENAI_API_KEY)
            elif api_type == "google" and config.GOOGLE_AI_API_KEY:
                import google.generativeai as genai
                genai.configure(api_key=config.GOOGLE_AI_API_KEY)
                clients[speaker] = genai.GenerativeModel(speaker_config["model"])
            elif api_type == "xai" and config.XAI_API_KEY:
                clients[speaker] = OpenAI(
                    api_key=config.XAI_API_KEY,
                    base_url="https://api.x.ai/v1",
                )
            else:
                logger.warning(
                    f"No API key for {speaker} ({api_type}) — "
                    "will use initial script text for this speaker"
                )
        except Exception as e:
            logger.warning(f"Failed to create client for {speaker}: {e}")

    return clients


# ---------------------------------------------------------------------------
# Turn-by-turn conversation engine
# ---------------------------------------------------------------------------

BANNED_FILLER = (
    "IMPORTANT: Do NOT use filler phrases like 'honestly', 'if I'm being honest', "
    "'that's a great point', 'absolutely', 'let's dive in', 'at the end of the day', "
    "or 'it's worth noting'. NEVER open a turn with your co-host's name or with "
    "agreement markers like 'Exactly', 'You're right', or 'You're absolutely right' "
    "— just say your thing. Disagreeing or complicating is more interesting than "
    "agreeing. Use varied, natural language."
)


def _load_personas(roster: list[str]) -> dict[str, str]:
    personas = {}
    for speaker in roster:
        prompt_file = config.SPEAKERS[speaker]["persona_prompt"]
        try:
            personas[speaker] = _load_prompt(prompt_file).format(
                show_title=config.PODCAST_TITLE,
                publication_format=config.PUBLICATION_FORMAT,
            )
        except FileNotFoundError:
            logger.warning(f"No persona prompt found for {speaker}: {prompt_file}")
    return personas


def _match_topic(topic_label: str | None, topics: list[dict]) -> dict | None:
    """Find the researched topic a plan segment refers to."""
    if not topic_label:
        return None
    label = topic_label.lower().strip()
    for t in topics:
        title = t["title"].lower().strip()
        if label in title or title in label or title[:40] == label[:40]:
            return t
    return None


def _clean_turn(text: str, speaker: str) -> str:
    """Strip attribution prefixes, quotes, and stage directions."""
    text = text.strip().strip('"').strip()
    prefix = f"{speaker}:"
    if text.lower().startswith(prefix.lower()):
        text = text[len(prefix):].strip()
    return text


def _speech_shape_issues(text: str) -> list[str]:
    """Return cadence risks that should trigger one same-host rewrite."""
    issues = []
    words = text.split()
    if len(words) > MAX_TURN_WORDS:
        issues.append(f"turn has {len(words)} words")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    longest = max((len(sentence.split()) for sentence in sentences), default=0)
    if longest > MAX_SENTENCE_WORDS:
        issues.append(f"sentence has {longest} words")
    if text.count('"') % 2:
        issues.append("turn has an unmatched quotation mark")
    return issues


def _clip_moment_text(value) -> str:
    """Normalize the showrunner's free-form clip direction into prompt text."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("direction", "summary", "hook", "description", "text"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "; ".join(
            text for item in value if (text := _clip_moment_text(item))
        )
    return ""


def _turn_prompt(
    seg: dict,
    topic_data: dict | None,
    dialogue: list[dict],
    completed: list[str],
    speaker: str,
    turn_idx: int,
    total_turns: int,
    date_str: str,
    participants: list[str],
    special_note: str = "",
    landscape: dict | None = None,
) -> str:
    """Build the user prompt for one conversational turn."""
    seg_type = seg.get("type", "")
    topic_label = seg.get("topic") or ""
    others = [p for p in participants if p != speaker]

    parts = [
        f"Today is {date_str}. You're recording {config.PODCAST_TITLE} with "
        f"{', '.join(others)}.",
        f"CURRENT SEGMENT: {seg_type}" + (f" — {topic_label}" if topic_label else ""),
    ]

    beats = seg.get("beats") or []
    if beats:
        parts.append("SHOWRUNNER BEATS (cover what's still uncovered, in your own way):\n"
                     + "\n".join(f"- {b}" for b in beats))

    clip_moment = _clip_moment_text(seg.get("clip_moment"))
    if clip_moment:
        parts.append(
            "PLANNED CLIP MOMENT — a self-contained, fact-grounded short-form "
            f"exchange this segment must create: {clip_moment}"
        )

    if topic_data:
        pcs = topic_data.get("prior_coverage") or []
        if pcs:
            parts.append(
                "THIS SHOW'S PRIOR COVERAGE — you both covered this before; "
                "treat it as a developing story and reference what changed:\n"
                + "\n".join(
                    f"- {pc.get('date')}: \"{pc.get('title')}\" "
                    f"({'; '.join(pc.get('facts', [])[:2])})"
                    for pc in pcs
                )
            )
        brief = topic_data.get("brief")
        if brief:
            parts.append(
                "FACT BRIEF — the ONLY facts you may cite. Use the specifics: "
                "numbers, names, quotes. Do not invent details beyond this:\n"
                + json.dumps(brief, ensure_ascii=False, indent=1)
            )
        else:
            parts.append(
                f"STORY SUMMARY (no full article was retrievable — stay "
                f"high-level, do NOT invent specifics): {topic_data.get('summary', '')}"
            )

    if landscape and seg_type in {
        "week_in_review", "frontier_board", "under_the_radar", "hype_check"
    }:
        from pipeline.landscape import compact_landscape_context
        parts.append(
            "WEEKLY LANDSCAPE EVIDENCE — use only these sourced status claims. "
            "Say when evidence is uncertain; do not manufacture movement:\n"
            + compact_landscape_context(landscape)
        )

    conflict = seg.get("conflict_of_interest")
    if conflict == speaker:
        parts.append(
            "NOTE: this story is about the company that made you. Disclose "
            "that conflict of interest naturally and expect your co-host to "
            "push you on it. Don't be defensive — be candid."
        )
    elif conflict and conflict in participants:
        parts.append(
            f"NOTE: this story is about the company that made {conflict}. "
            f"Keep them honest — press them on the parts their maker would "
            f"rather not talk about. Friendly, but pointed."
        )

    if completed:
        parts.append("EARLIER IN THIS EPISODE: " + " | ".join(completed[-6:]))

    if dialogue:
        convo = "\n".join(f"{l['speaker']}: {l['text']}" for l in dialogue[-10:])
        parts.append(f"THE CONVERSATION SO FAR IN THIS SEGMENT:\n{convo}")

    # Role-specific instruction for this turn
    if seg_type == "intro":
        task = (
            f"Welcome listeners to {config.PODCAST_TITLE}, mention today's date, "
            "and tee up the episode."
        )
        if special_note and turn_idx == 0:
            task += (
                " Include this operator-supplied announcement clearly and naturally "
                f"in this turn; do not skip it: {special_note}"
            )
    elif seg_type == "cold_open" and turn_idx == 0:
        task = "Open the show with a punchy, curiosity-grabbing line about the top story. No greetings yet."
    elif seg_type == "sign_off":
        if turn_idx < len(participants):
            task = ("Give your 'one thing to watch' — a specific, checkable "
                    "prediction related to today's stories. One prediction only.")
        elif turn_idx == len(participants):
            task = (
                "Predictions are done — do NOT give another one. Give a short, warm "
                "goodbye in 25 words or less. Do not mention subscriptions or any "
                "platform; the show's standard CTA is inserted automatically."
            )
        else:
            task = ("Predictions are done — do NOT give another one. Just wrap "
                    "with a short, warm goodbye in 25 words or less. Do not repeat "
                    "the subscribe/follow request.")
    elif turn_idx == 0:
        prev = seg.get("_prev_topic")
        handoff = (
            f"A musical transition just played after the discussion of "
            f"'{prev}'. Open with a quick, natural handoff into this story — "
            "a connecting thought or a clean pivot, not a hard reset. Then "
            if prev else "Open this segment: "
        )
        task = (handoff + "introduce the story crisply (what happened, "
                "why it matters) using specifics from the brief.")
    else:
        task = ("React to what was just said — agree, push back, or build on it "
                "with something NEW from the brief or your own perspective. If you "
                "genuinely see it differently, say so and argue it.")

    if (
        clip_moment
        and seg_type in ("main_story", "lightning_round")
        and turn_idx == len(participants)
    ):
        task += (
            " Make this the planned clip moment. Open with a decisive, standalone "
            "sentence—not agreement or a transition—then deliver the specific fact, "
            "tension, analogy, or stakes and a clear payoff. A new viewer must "
            "understand it without hearing the rest of the episode."
        )

    if turn_idx == total_turns - 1 and seg_type not in ("intro", "sign_off"):
        task += " Then land the segment — a closing thought or handoff, not a summary."

    parts.append(
        f"YOUR TASK: {task}\n\n"
        f"Write YOUR next spoken turn only — usually 24-48 words; cold opens and "
        f"goodbyes may be shorter. Use two or three complete sentences, with no "
        f"sentence over {MAX_SENTENCE_WORDS} words. Keep each sentence syntactically "
        f"simple so it can be spoken continuously without a mid-clause breath. "
        f"Plain text only. No name prefix, quotes, or stage directions.\n{BANNED_FILLER}"
    )
    return "\n\n".join(parts)


def _enforce_signoff_cta(script: dict, roster: list[str]) -> None:
    """Insert one canonical CTA and remove any model-generated duplicates."""
    sign_off = next(
        (segment for segment in script.get("segments", [])
         if segment.get("type") == "sign_off"),
        None,
    )
    dialogue = sign_off.get("dialogue", []) if sign_off else []
    if not dialogue:
        return

    # The first pass through the roster contains predictions; goodbyes begin
    # on the next turn. Models sometimes append an unsolicited CTA to a
    # prediction, so scan the whole sign-off while distinguishing calls to
    # action from legitimate news discussion that names a platform.
    target_idx = min(len(roster), len(dialogue) - 1)
    platform_pattern = re.compile(r"\b(?:youtube|spotify)\b", re.IGNORECASE)
    cta_action_pattern = re.compile(
        r"\b(?:subscribe|follow\s+(?:us|on)|find\s+us|catch\s+us|listen\s+on)\b",
        re.IGNORECASE,
    )

    def is_platform_cta(sentence: str) -> bool:
        platforms = set(match.group(0).lower() for match in platform_pattern.finditer(sentence))
        return len(platforms) == 2 or (bool(platforms) and bool(cta_action_pattern.search(sentence)))

    for idx in range(len(dialogue)):
        text = dialogue[idx].get("text", "")
        sentences = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
        dialogue[idx]["text"] = " ".join(
            sentence.strip() for sentence in sentences
            if sentence.strip() and not is_platform_cta(sentence)
        )

    goodbye = dialogue[target_idx].get("text", "").strip()
    dialogue[target_idx]["text"] = SIGNOFF_CTA + (f" {goodbye}" if goodbye else "")


def _speak(client, speaker: str, persona: str, user_content: str) -> str | None:
    """Have one speaker's own model produce its next turn."""
    speaker_config = config.SPEAKERS[speaker]
    api_type = speaker_config["api_type"]
    model = speaker_config["model"]

    if api_type == "anthropic":
        response = client.messages.create(
            model=model,
            max_tokens=400,
            thinking={"type": "disabled"},
            system=persona,
            messages=[{"role": "user", "content": user_content}],
        )
        tracker.record(
            step="conversation", model=model, speaker=speaker,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return next(b.text for b in response.content if b.type == "text").strip()

    elif api_type in ("openai", "xai"):
        response = client.chat.completions.create(
            model=model,
            max_tokens=400,
            messages=[
                {"role": "system", "content": persona},
                {"role": "user", "content": user_content},
            ],
        )
        usage = response.usage
        if usage:
            tracker.record(
                step="conversation", model=model, speaker=speaker,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
            )
        return response.choices[0].message.content.strip()

    elif api_type == "google":
        response = client.generate_content(f"{persona}\n\n{user_content}")
        meta = getattr(response, "usage_metadata", None)
        if meta:
            tracker.record(
                step="conversation", model=model, speaker=speaker,
                input_tokens=getattr(meta, "prompt_token_count", 0),
                output_tokens=getattr(meta, "candidates_token_count", 0),
            )
        return response.text.strip()

    return None


def _run_conversation(
    plan: dict,
    topics: list[dict],
    roster: list[str],
    date_str: str,
    special_note: str = "",
    landscape: dict | None = None,
) -> dict:
    """
    Generate the episode as an actual conversation: each turn is written by
    that speaker's own model, replying to what was really said before it.
    """
    personas = _load_personas(roster)
    clients = _get_api_clients(roster)
    speakers = [s for s in roster if s in clients and s in personas]
    if len(speakers) < 2:
        raise RuntimeError(
            f"Need at least 2 speakers with API keys and personas, got {speakers}"
        )

    segments_out = []
    completed: list[str] = []
    prev_topic_label: str | None = None

    for seg in plan.get("segments", []):
        # Give the segment opener the previous topic for a verbal handoff
        seg["_prev_topic"] = prev_topic_label
        # Rotation starts with the plan's lead
        lead = seg.get("lead")
        order = list(speakers)
        if lead in order:
            order = order[order.index(lead):] + order[:order.index(lead)]

        turns_per = max(1, int(seg.get("turns_per_speaker", 2)))
        total_turns = turns_per * len(order)
        topic_label = seg.get("topic")
        topic_data = _match_topic(topic_label, topics)

        dialogue: list[dict] = []
        for turn_idx in range(total_turns):
            speaker = order[turn_idx % len(order)]
            prompt = _turn_prompt(
                seg, topic_data, dialogue, completed, speaker,
                turn_idx, total_turns, date_str, order, special_note, landscape,
            )
            text = None
            for attempt in (1, 2):
                try:
                    text = _speak(clients[speaker], speaker, personas[speaker], prompt)
                    break
                except Exception as e:
                    logger.warning(f"Turn failed for {speaker} (attempt {attempt}): {e}")
            if text:
                cleaned = _clean_turn(text, speaker)
                issues = _speech_shape_issues(cleaned)
                if issues:
                    rewrite_prompt = (
                        prompt
                        + "\n\nREWRITE REQUIRED: Your previous draft creates TTS cadence risks ("
                        + "; ".join(issues)
                        + "). Preserve its facts and point, but rewrite it in 24-48 words "
                        f"using two or three complete sentences of no more than "
                        f"{MAX_SENTENCE_WORDS} words each. DRAFT:\n{cleaned}"
                    )
                    try:
                        rewritten = _speak(
                            clients[speaker], speaker, personas[speaker], rewrite_prompt
                        )
                        if rewritten:
                            cleaned = _clean_turn(rewritten, speaker)
                    except Exception as e:
                        logger.warning("Cadence rewrite failed for %s: %s", speaker, e)
                dialogue.append({"speaker": speaker, "text": cleaned})

        if dialogue:
            segments_out.append(
                {"type": seg.get("type", "main_story"), "topic": topic_label,
                 "dialogue": dialogue}
            )
            if topic_label:
                prev_topic_label = topic_label
            tail = dialogue[-1]["text"][:90]
            completed.append(f"{seg.get('type')}" + (f" on '{topic_label}'" if topic_label else "")
                             + f" (ended: \"{tail}...\")")
            logger.info(
                f"Segment '{seg.get('type')}'"
                + (f" — {topic_label}" if topic_label else "")
                + f": {len(dialogue)} turns"
            )

    if not segments_out:
        raise RuntimeError("Conversation produced no segments")

    return {
        "title": plan.get("title", f"{config.PODCAST_TITLE} — {date_str}"),
        "description": plan.get("description", ""),
        "segments": segments_out,
    }


def _generate_youtube_title(script: dict, topics: list[dict]) -> str:
    """Generate a click-worthy YouTube title from the episode content."""
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    episode_title = script.get("title", "")
    main_topics = [t["title"] for t in topics if t.get("category") == "main"][:3]
    topics_str = "; ".join(main_topics) if main_topics else "AI news"

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=100,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You write YouTube video titles for a {config.PUBLICATION_FORMAT} "
                    f"called '{config.PODCAST_TITLE}' hosted by ChatGPT and Claude.\n\n"
                    "Rules for great YouTube titles:\n"
                    "- MAX 62 characters (hard limit)\n"
                    "- Lead with recognizable companies, people, or products\n"
                    "- State the concrete conflict or consequence in plain English\n"
                    "- Make one clear promise; do not summarize the whole episode\n"
                    "- Avoid generic words like 'interesting', 'amazing', 'incredible'\n"
                    "- Don't use all caps, excessive punctuation, or vague clever phrasing\n"
                    "- Do NOT include the show name; the thumbnail and channel provide the brand\n"
                    "- Good pattern: 'Apple Sues OpenAI Over Alleged Trade-Secret Theft'\n\n"
                    "Return ONLY the title text, nothing else."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Episode script title: {episode_title}\n"
                    f"Main topics: {topics_str}\n\n"
                    "Write a click-worthy YouTube title."
                ),
            },
        ],
        temperature=0.9,
    )

    usage = resp.usage
    if usage:
        tracker.record(
            step="youtube_title", model="gpt-4o-mini",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )

    yt_title = resp.choices[0].message.content.strip().strip('"')
    logger.info(f"YouTube title: {yt_title}")
    return yt_title


def save_script(script: dict, output_dir: Path) -> Path:
    """Save the script to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "script.json"
    path.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Script saved to {path}")
    return path
