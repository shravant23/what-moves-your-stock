"""SQLite via SQLModel. Single-file DB holding the fetch cache and, in later
phases, exposure profiles, sector trends, graph data, and generated reports."""

import shutil
from datetime import datetime

from sqlmodel import Field, Session, SQLModel, create_engine

from .config import BACKEND_DIR, DB_PATH, DEMO_MODE

# In demo deployments the disk is ephemeral: seed a fresh instance from the
# bundled cache of pre-analyzed tickers. Must happen before the engine binds.
_DEMO_SEED = BACKEND_DIR / "data" / "demo_cache.db"
if DEMO_MODE and not DB_PATH.exists() and _DEMO_SEED.exists():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_DEMO_SEED, DB_PATH)


class CacheEntry(SQLModel, table=True):
    """Generic cache for external fetches (EDGAR JSON, filing text, FRED
    observations, yfinance prices). `value` is JSON or raw text."""

    key: str = Field(primary_key=True)
    value: str
    fetched_at: datetime


engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
