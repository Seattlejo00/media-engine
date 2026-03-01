import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# --- Paths ---
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
PROMPTS_DIR = BASE_DIR / "prompts"

# --- API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# --- Episode Settings ---
EPISODE_DURATION_MINUTES = int(os.getenv("EPISODE_DURATION_MINUTES", "12"))
CLIP_DURATION_SECONDS = int(os.getenv("CLIP_DURATION_SECONDS", "45"))
DAILY_RUN_HOUR = int(os.getenv("DAILY_RUN_HOUR", "6"))
TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")

# --- TTS ---
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai")
CLAUDE_VOICE = os.getenv("CLAUDE_VOICE", "onyx")
CHATGPT_VOICE = os.getenv("CHATGPT_VOICE", "nova")

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

# --- Models ---
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CHATGPT_MODEL = "gpt-4o"
