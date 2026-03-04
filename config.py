import os
import platform
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# --- Ensure ffmpeg is in PATH (Windows WinGet install location) ---
if platform.system() == "Windows":
    _winget_links = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links"
    if _winget_links.exists() and str(_winget_links) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = str(_winget_links) + os.pathsep + os.environ.get("PATH", "")

# --- Paths ---
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
PROMPTS_DIR = BASE_DIR / "prompts"

# --- API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")

# --- Episode Settings ---
EPISODE_DURATION_MINUTES = int(os.getenv("EPISODE_DURATION_MINUTES", "30"))
CLIP_DURATION_SECONDS = int(os.getenv("CLIP_DURATION_SECONDS", "45"))
MAX_CLIPS_UPLOAD = int(os.getenv("MAX_CLIPS_UPLOAD", "4"))  # YouTube daily limit safety
DAILY_RUN_HOUR = int(os.getenv("DAILY_RUN_HOUR", "6"))
TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")

# --- TTS ---
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai")

# --- Podcast Metadata ---
PODCAST_TITLE = os.getenv("PODCAST_TITLE", "The AI Daily")
PODCAST_DESCRIPTION = os.getenv(
    "PODCAST_DESCRIPTION",
    "ChatGPT and Claude discuss the day's biggest stories — as themselves.",
)
RSS_FEED_URL = os.getenv("RSS_FEED_URL", "")

# --- YouTube ---
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")

# --- Twitter/X ---
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")

# --- TikTok ---
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")

# --- Podcast Hosting (Cloudflare R2 / S3-compatible) ---
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")  # e.g. https://podcast.distomostech.com

# --- Models ---
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CHATGPT_MODEL = "gpt-4o"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3")

# --- Guest Episode Settings ---
GUEST_EPISODE_DAY = os.getenv("GUEST_EPISODE_DAY", "Friday")
GUEST_FORMAT = os.getenv("GUEST_FORMAT", "guest_friday")  # "guest_friday" or "roundtable"

# --- Speaker Registry ---
# Central data structure that all modules use.
# Adding a new AI = one dict entry here + one persona prompt file.
SPEAKERS = {
    "Claude": {
        "company": "Anthropic",
        "voice": os.getenv("CLAUDE_VOICE", "onyx"),
        "tts_speed": 1.1,
        "color": (204, 120, 50),
        "model": CLAUDE_MODEL,
        "api_type": "anthropic",
        "persona_prompt": "claude_host.txt",
        "role": "host",
    },
    "ChatGPT": {
        "company": "OpenAI",
        "voice": os.getenv("CHATGPT_VOICE", "nova"),
        "tts_speed": 1.1,
        "color": (16, 163, 127),
        "model": CHATGPT_MODEL,
        "api_type": "openai",
        "persona_prompt": "chatgpt_host.txt",
        "role": "host",
    },
    "Gemini": {
        "company": "Google",
        "voice": os.getenv("GEMINI_VOICE", "echo"),
        "tts_speed": 1.1,
        "color": (66, 133, 244),
        "model": GEMINI_MODEL,
        "api_type": "google",
        "persona_prompt": "gemini_guest.txt",
        "role": "guest",
    },
    "Grok": {
        "company": "xAI",
        "voice": os.getenv("GROK_VOICE", "fable"),
        "tts_speed": 1.1,
        "color": (239, 68, 68),
        "model": GROK_MODEL,
        "api_type": "xai",
        "persona_prompt": "grok_guest.txt",
        "role": "guest",
    },
}


# --- API key lookup (maps api_type -> env var) ---
_API_KEY_MAP = {
    "anthropic": ANTHROPIC_API_KEY,
    "openai": OPENAI_API_KEY,
    "google": GOOGLE_AI_API_KEY,
    "xai": XAI_API_KEY,
}


def speaker_has_api_key(name: str) -> bool:
    """Check if a speaker's API key is configured (non-empty)."""
    api_type = SPEAKERS[name]["api_type"]
    return bool(_API_KEY_MAP.get(api_type, ""))


def get_hosts() -> list[str]:
    """Return permanent host speaker names."""
    return [name for name, s in SPEAKERS.items() if s["role"] == "host"]


def get_guests() -> list[str]:
    """Return guest speaker names that have valid API keys.

    A guest without an API key can't write their own lines,
    so they're excluded — no one speaks unless they write it.
    """
    return [
        name for name, s in SPEAKERS.items()
        if s["role"] == "guest" and speaker_has_api_key(name)
    ]


def get_all_guests() -> list[str]:
    """Return ALL guest speaker names (regardless of key status)."""
    return [name for name, s in SPEAKERS.items() if s["role"] == "guest"]


def get_episode_roster(date: datetime | None = None) -> list[str]:
    """
    Determine which speakers participate in today's episode.

    - Normal days: just the permanent hosts
    - Guest day (default Friday): hosts + one rotating guest
    - Roundtable format: hosts + all guests

    Only guests with valid API keys are eligible — no one speaks
    unless they can write their own lines.
    """
    if date is None:
        date = datetime.now()

    hosts = get_hosts()

    if date.strftime("%A") == GUEST_EPISODE_DAY:
        guests = get_guests()  # already filtered by API key
        if not guests:
            return hosts
        if GUEST_FORMAT == "roundtable":
            return hosts + guests
        # Rotate guests week by week
        week_num = date.isocalendar()[1]
        guest = guests[week_num % len(guests)]
        return hosts + [guest]

    return hosts
