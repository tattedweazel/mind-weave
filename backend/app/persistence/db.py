from sqlalchemy import event
from sqlmodel import Session, create_engine

from app.core.config import settings

_is_sqlite = "sqlite" in settings.DATABASE_URL

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def create_db_and_tables():
    from app.persistence.tables import SQLModel

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
