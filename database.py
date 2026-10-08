"""Подключение к SQLite.

Путь к БД можно переопределить переменной окружения DATABASE_URL
(используется в docker-compose, чтобы данные жили в volume).
"""
import os

from sqlmodel import Session, SQLModel, create_engine

sqlite_url = os.environ.get("DATABASE_URL", "sqlite:///database.db")
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})


def get_db():
    """Зависимость FastAPI: одна сессия БД на запрос (раздел 16.2)."""
    with Session(engine) as session:
        yield session


def init_db() -> None:
    """Создать таблицы (раздел 15.1 «Минимальный состав»).

    Импорт ``models`` обязателен: без него классы не попадут в SQLModel.metadata
    и ``create_all`` не создаст таблицы.
    """
    import models  # noqa: F401  — регистрация моделей в metadata

    SQLModel.metadata.create_all(engine)
