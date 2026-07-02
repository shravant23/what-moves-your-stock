"""Central configuration. All secrets come from backend/.env (see /.env.example)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BACKEND_DIR / ".env")

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
FRED_API_KEY: str = os.getenv("FRED_API_KEY", "")

# "gemini" (free tier) or "anthropic". Auto: prefer whichever key is set,
# gemini first so the app runs at zero cost by default.
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "") or (
    "gemini" if GEMINI_API_KEY else "anthropic"
)
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# EDGAR rejects requests without a descriptive User-Agent containing a contact.
# Set your own contact email in backend/.env (see .env.example).
EDGAR_USER_AGENT: str = os.getenv(
    "EDGAR_USER_AGENT", "Prism Research contact@example.com"
)

DB_PATH: Path = BACKEND_DIR / "prism.db"

# Anthropic model used when LLM_PROVIDER=anthropic (spec-pinned).
LLM_MODEL: str = "claude-sonnet-4-6"

FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
