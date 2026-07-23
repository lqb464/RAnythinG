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
    "postgresql://ranything:ranything@localhost:5432/ranything",
)

# External project ids (e.g. user_<id>) need headroom beyond short notebook keys.
NOTEBOOK_ID_LEN = 64

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True)
    email = Column(String(320), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)


class NotebookRow(Base):
    __tablename__ = "notebooks"
    id = Column(String(NOTEBOOK_ID_LEN), primary_key=True)
    name = Column(String(255), nullable=False)
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class SourceRow(Base):
    __tablename__ = "sources"
    id = Column(String(36), primary_key=True)
    notebook_id = Column(
        String(NOTEBOOK_ID_LEN),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename = Column(String(512), nullable=False)
    raw_bytes = Column(LargeBinary, nullable=True)
    parsed_text = Column(Text, nullable=False, default="")


class NoteRow(Base):
    __tablename__ = "notes"
    id = Column(String(64), primary_key=True)
    notebook_id = Column(
        String(NOTEBOOK_ID_LEN),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(512), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)


class ChatRow(Base):
    __tablename__ = "chat_messages"
    id = Column(String(36), primary_key=True)
    notebook_id = Column(
        String(NOTEBOOK_ID_LEN),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False)


class StudioOutputRow(Base):
    __tablename__ = "studio_outputs"
    id = Column(String(36), primary_key=True)
    notebook_id = Column(
        String(NOTEBOOK_ID_LEN),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool = Column(String(64), nullable=False)
    label = Column(String(512), nullable=False, default="")
    sources_json = Column(Text, nullable=False, default="[]")
    result_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False)


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_schema(conn) -> None:
    """Widen notebook id columns and add owner_id / studio_outputs for existing DBs."""
    dialect = engine.dialect.name
    if dialect != "postgresql":
        return

    widens = [
        ("notebooks", "id"),
        ("sources", "notebook_id"),
        ("notes", "notebook_id"),
        ("chat_messages", "notebook_id"),
        ("studio_outputs", "notebook_id"),
    ]
    for table, col in widens:
        exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table},
        ).fetchone()
        if not exists:
            continue
        col_exists = conn.execute(
            text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": col},
        ).fetchone()
        if col_exists and (col_exists[0] is None or col_exists[0] < NOTEBOOK_ID_LEN):
            conn.execute(
                text(f'ALTER TABLE "{table}" ALTER COLUMN "{col}" TYPE VARCHAR({NOTEBOOK_ID_LEN})')
            )

    nb_exists = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'notebooks'"
        )
    ).fetchone()
    if nb_exists:
        owner_col = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'notebooks' "
                "AND column_name = 'owner_id'"
            )
        ).fetchone()
        if not owner_col:
            conn.execute(text("ALTER TABLE notebooks ADD COLUMN owner_id VARCHAR(36)"))
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_notebooks_owner_id ON notebooks (owner_id)")
            )


def init_db() -> None:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        _migrate_schema(conn)
        conn.commit()


def db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
