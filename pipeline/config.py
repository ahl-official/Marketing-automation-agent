"""
Configuration loader.

All secrets come from environment variables (see .env.example).
Never hardcode keys here - this file is safe to commit to git.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Check your .env file against .env.example."
        )
    return value


@dataclass(frozen=True)
class Settings:
    # Config source (Apps Script Web App - same one used in the n8n build)
    apps_script_url: str
    apps_script_token: str

    # Collection APIs
    serper_api_key: str
    google_places_api_key: str

    # AI synthesis (Groq - free tier, OpenAI-compatible)
    groq_api_key: str
    groq_model: str

    # Storage / delivery (archive AND doc publishing both use the same
    # Apps Script Web App as config - no separate credential needed)
    slack_bot_token: str
    slack_content_channel: str
    slack_alerts_channel: str

    geo: str


def load_settings() -> Settings:
    return Settings(
        apps_script_url=_require("APPS_SCRIPT_URL"),
        apps_script_token=_require("APPS_SCRIPT_TOKEN"),
        serper_api_key=_require("SERPER_API_KEY"),
        google_places_api_key=_require("GOOGLE_PLACES_API_KEY"),
        groq_api_key=_require("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        slack_bot_token=_require("SLACK_BOT_TOKEN"),
        slack_content_channel=os.getenv("SLACK_CONTENT_CHANNEL", "#content-team"),
        slack_alerts_channel=os.getenv("SLACK_ALERTS_CHANNEL", "#automation-alerts"),
        geo=os.getenv("RESEARCH_GEO", "IN,AE,US"),
    )
