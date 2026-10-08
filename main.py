"""Точка входа платформы ФСП «спец. трек».

Запуск:
    uvicorn main:app --reload
    → http://127.0.0.1:8000

Здесь собраны: приложение, шаблоны, статика, middleware сессии (раздел 16.2),
обработчик флеш-редиректов (раздел 12.5) и подключение роутеров.
"""
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

import auth
import helpers
import seed
import web
from database import engine, get_db, init_db
from routers import auth as auth_router
from routers import candidate as candidate_router
from routers import employer as employer_router
from routers import registration as registration_router

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создаём таблицы при старте и заполняем демо-данными пустую базу.

    Сид срабатывает один раз: если в базе уже есть записи, она остаётся как есть
    (п. 12.2 документации). Пересобрать стенд вручную — ``python3.13 seed.py --force``.
    """
    init_db()
    with Session(engine) as db:
        seed.ensure_demo_data(db)
    yield


app = FastAPI(
    title="ФСП «спец. трек»",
    description="Веб-платформа для взаимодействия амбициозных ИТ-специалистов и "
                "организаций с высоким уровнем процессов",
    version="1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

# Шаблоны и их глобальные справочники живут в web.py (раздел 11.1) — здесь только статика
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.middleware("http")
async def session_middleware(request: Request, call_next):
    """Читаем session cookie и кладём Principal в request.state.me (раздел 16.2)."""
    token = request.cookies.get(web.SESSION_COOKIE)
    request.state.session_token = token
    request.state.me = None
    if token:
        with Session(engine) as db:
            request.state.me = auth.principal_for_token(db, token)
    return await call_next(request)


@app.exception_handler(web.RedirectException)
async def redirect_exception_handler(request: Request, exc: web.RedirectException):
    """Флеш-сообщение в cookie + 303-редирект (раздел 12.5)."""
    response = RedirectResponse(exc.url, status_code=303)
    return web.flash(response, exc.message, exc.kind)


app.include_router(auth_router.router)
app.include_router(registration_router.router)
app.include_router(candidate_router.router)
app.include_router(employer_router.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Входная страница: авторизованных сразу отправляем дальше (раздел 11.1).

    Незавершённая регистрация ведёт на анкету, подтверждённый вход — в кабинет.
    Гостям показываем лендинг со счётчиками банка (раздел 13.1).
    """
    me = getattr(request.state, "me", None)
    if me is not None and me.is_authenticated:
        target = me.register_url if me.needs_registration else me.home_url
        return RedirectResponse(target, status_code=303)
    return web.render(request, "index.html", "ФСП «спец. трек»",
                      stats=helpers.public_stats(db))


@app.get("/health")
def health():
    """Техническая проверка для стенда (п. 12.1 документации)."""
    return {"status": "ok", "app": "ФСП «спец. трек»"}
