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

# Overridable so the test suite can run against a throwaway database.
DB_PATH: Path = Path(os.getenv("PRISM_DB_PATH") or (BACKEND_DIR / "prism.db"))

# Public-demo deployment mode: pre-analyzed tickers are served from the
# bundled cache (never expiring), and analysis of new tickers is disabled so
# visitors can't drain the host's LLM quota.
DEMO_MODE: bool = os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes")

# Anthropic model used when LLM_PROVIDER=anthropic (spec-pinned).
LLM_MODEL: str = "claude-sonnet-4-6"

FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
