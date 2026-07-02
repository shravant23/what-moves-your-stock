"""SQLite via SQLModel. Single-file DB holding the fetch cache and, in later
phases, exposure profiles, sector trends, graph data, and generated reports."""

from datetime import datetime

from sqlmodel import Field, Session, SQLModel, create_engine

from .config import DB_PATH


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
