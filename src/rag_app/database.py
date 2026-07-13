import os
from datetime import datetime
from typing import Generator, Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://rananything:rananything@localhost:5432/rananything",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class NotebookRow(Base):
    __tablename__ = "notebooks"
    id = Column(String(8), primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class SourceRow(Base):
    __tablename__ = "sources"
    id = Column(String(36), primary_key=True)
    notebook_id = Column(String(8), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(512), nullable=False)
    raw_bytes = Column(LargeBinary, nullable=True)
    parsed_text = Column(Text, nullable=False, default="")


class NoteRow(Base):
    __tablename__ = "notes"
    id = Column(String(64), primary_key=True)
    notebook_id = Column(String(8), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(512), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)


class ChatRow(Base):
    __tablename__ = "chat_messages"
    id = Column(String(36), primary_key=True)
    notebook_id = Column(String(8), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False)
    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False)


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)


def db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
