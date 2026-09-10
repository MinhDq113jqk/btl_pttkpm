from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_engine(
            settings.sqlalchemy_url(), pool_size=5, max_overflow=10,
            pool_pre_ping=True, pool_timeout=10, echo=False, hide_parameters=True,
            connect_args={"options": "-c timezone=UTC -c statement_timeout=10000"},
        )
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def ping(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def get_session(self):
        return self.sessions()

    def close(self) -> None:
        self.engine.dispose()


def get_session(request: Request) -> Generator[Session, None, None]:
    # Services explicitly commit successful business transactions.
    with request.app.state.database.sessions() as session:
        yield session
