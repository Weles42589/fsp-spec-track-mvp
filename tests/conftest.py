"""Общее окружение смоук-тестов (перенос скриптов из /tmp в tests/).

Важно: ``database.py`` читает ``DATABASE_URL`` в момент импорта, поэтому переменная
выставляется ДО импорта модулей приложения. Тесты работают на временной копии БД и
не трогают ``database.db`` из репозитория.

Порядок подготовки повторяет смоук-скрипты:
  1. временная БД → ``database.init_db()``;
  2. сид-данные: кандидаты из мок-реестра ФСП (один с КИТ, один скрыт из банка),
     работодатель тира 3 и работодатель тира 1, потребности, отклик, приглашение;
  3. ``TestClient(main.app, follow_redirects=False)`` — редиректы не проходим, чтобы
     видеть работу guard-функций (303) и не маскировать ошибки доступа.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_DB = pathlib.Path(tempfile.mkdtemp(prefix="fsp-tests-")) / "fsp_test.db"

os.environ["DATABASE_URL"] = "sqlite:///" + str(TEST_DB)
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jinja2 import StrictUndefined, Undefined  # noqa: E402
from sqlmodel import Session  # noqa: E402

import content  # noqa: E402
import database  # noqa: E402
import fsp_mock  # noqa: E402
import kit_parser  # noqa: E402
import logic  # noqa: E402
import main  # noqa: E402
import services  # noqa: E402
import web  # noqa: E402
from models import (Application, Candidate, Employer, Invitation,  # noqa: E402
                    UserSession, Vacancy, utcnow)

database.init_db()

TEAM_ROLES = list(logic.TEAM_ROLES)
WORK_FORMATS = list(logic.WORK_FORMATS)
FSP_ROLES = list(logic.FSP_ROLES)
AMBITIONS = list(logic.AMBITIONS)
SPECIALIZATIONS = list(logic.SPECIALIZATIONS)
SURVEY_FIELDS = [item["field"] for item in content.EMPLOYER_SURVEY]


# ---------------------------------------------------------------------------
# Хелперы подготовки данных
# ---------------------------------------------------------------------------

def session_token(user, role: str, tag: str = "test") -> str:
    """Подтверждённая сессия в обход /login + /verify.

    В демо-сборке код показывается прямо на странице /verify, поэтому в тестах
    запись ``session`` создаётся напрямую: это не подменяет аутентификацию, а
    лишь убирает из смоук-проверок лишние шаги.
    """
    with Session(database.engine) as db:
        row = UserSession(token=f"{tag}-{uuid.uuid4().hex[:16]}", user_id=user.id,
                          email=user.email, role=role, is_verified=True,
                          created_at=utcnow())
        db.add(row)
        db.commit()
        return row.token


def build_candidate(db, email: str, index: int, kit: bool = False,
                    hidden: bool = False) -> Candidate:
    """Кандидат из мок-реестра ФСП: полный профиль, история ФСП, опционально КИТ."""
    candidate = Candidate(email=email, name=fsp_mock.FSP_REGISTRY[email]["name"])
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    errors = services.apply_candidate_profile(candidate, {
        "name": candidate.name,
        "city": "Москва" if index % 2 == 0 else "Обнинск",
        "team_role": TEAM_ROLES[index % len(TEAM_ROLES)],
        "work_format": WORK_FORMATS[index % len(WORK_FORMATS)],
        "specialization": SPECIALIZATIONS[index % len(SPECIALIZATIONS)],
        "fsp_role": FSP_ROLES[index % len(FSP_ROLES)],
        "ambitions": AMBITIONS[:3] if index % 2 == 0 else AMBITIONS[:1],
        "stack": "Python, FastAPI, PostgreSQL",
        "consent": "on",
        "visible_in_bank": not hidden,
    })
    assert not errors, errors
    services.connect_fsp(candidate)
    if kit:
        parsed = services.parse_kit_upload(
            "kit.txt", kit_parser.DEMO_CERTIFICATE_TEXT.encode("utf-8"))
        assert parsed.get("error") == "", parsed
        services.apply_kit(candidate, parsed, "text")
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate
def build_employer(db, email: str, company: str, healthy: bool) -> Employer:
    """Работодатель с заполненной анкетой: healthy=True → тир 3, иначе тир 1."""
    employer = Employer(email=email, company=company, consent=True)
    db.add(employer)
    db.commit()
    db.refresh(employer)
    assert not services.apply_employer_profile(employer, {
        "company": company,
        "position": "Руководитель направления",
        "contact_name": "Смирнова Ольга",
        "city": "Москва",
        "description": "Продуктовая разработка",
        "consent": "on",
    })
    answer = "true" if healthy else "false"
    assert not services.apply_employer_survey(
        employer, {field: answer for field in SURVEY_FIELDS})
    db.add(employer)
    db.commit()
    db.refresh(employer)
    return employer


def build_vacancy(db, employer: Employer, title: str, published: bool = True,
                  grade: str = "middle") -> Vacancy:
    """Потребность работодателя: published=False — не видна в банке /needs."""
    vacancy = Vacancy(employer_id=employer.id, company=employer.company, title=title,
                      specialization=SPECIALIZATIONS[0], grade=grade, grade_match="exact",
                      stack=["Python", "FastAPI", "PostgreSQL"], salary_min=150000,
                      salary_max=220000, format="hybrid", city="Москва",
                      team_size="8 человек", description="Работа над платформой",
                      open=published)
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)
    return vacancy


def all_get_paths() -> list:
    """Все GET-пути приложения.

    Маршруты FastAPI в этой версии вложены в _IncludedRouter, поэтому перечень
    надёжнее брать из OpenAPI-схемы. Служебные пути документации пропускаем.
    """
    skip = ("/static", "/docs", "/redoc", "/openapi", "/api/docs")
    return [path for path, ops in main.app.openapi()["paths"].items()
            if "get" in ops and not path.startswith(skip)]


def fill_path(path: str, ids: dict) -> str:
    """Подставить известные id в шаблон пути, неизвестные — единицей."""
    filled = path
    for key in re.findall(r"{(\w+)}", path):
        filled = filled.replace("{%s}" % key, str(ids.get(key, 1)))
    return filled
# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def seed() -> dict:
    """Базовые данные на всю сессию pytest: кандидаты, работодатели, потребности."""
    with Session(database.engine) as db:
        emails = sorted(fsp_mock.FSP_REGISTRY)
        candidates = [build_candidate(db, email, index, kit=(index == 0),
                                      hidden=(index == 1))
                      for index, email in enumerate(emails)]
        emp_tier3 = build_employer(db, "hr@tier3.demo", "Атом Софт", healthy=True)
        emp_tier1 = build_employer(db, "hr@tier1.demo", "Процессы Плюс", healthy=False)
        vac_open = build_vacancy(db, emp_tier3, "Backend-разработчик")
        vac_hidden = build_vacancy(db, emp_tier3, "Инженер платформы", published=False)
        vac_foreign = build_vacancy(db, emp_tier1, "DevOps-инженер")
        verified, hidden = candidates[0], candidates[1]
        application = Application(candidate_id=verified.id, employer_id=emp_tier3.id,
                                  vacancy_id=vac_open.id, message="Готов обсудить задачу")
        invitation = Invitation(employer_id=emp_tier3.id, candidate_id=verified.id,
                                vacancy_id=vac_open.id, message="Приглашаем в команду",
                                salary_min=150000, salary_max=220000)
        db.add(application)
        db.add(invitation)
        db.commit()
        db.refresh(application)
        db.refresh(invitation)
        ids = {
            "candidate_id": verified.id,
            "employer_id": emp_tier3.id,
            "vacancy_id": vac_open.id,
            "need_id": vac_open.id,
            "application_id": application.id,
            "invitation_id": invitation.id,
        }
        tokens = {
            "candidate": session_token(verified, "candidate", "seed-cand"),
            "employer": session_token(emp_tier3, "employer", "seed-emp"),
        }
        return {
            "ids": ids,
            "tokens": tokens,
            "candidates": candidates,
            "verified_id": verified.id,
            "hidden_id": hidden.id,
            "no_kit_id": candidates[2].id,
            "emp_tier3": emp_tier3.id,
            "emp_tier1": emp_tier1.id,
            "vac_open": vac_open.id,
            "vac_hidden": vac_hidden.id,
            "vac_foreign": vac_foreign.id,
            "application": application.id,
            "invitation": invitation.id,
        }


@pytest.fixture()
def client() -> TestClient:
    """TestClient без прохождения редиректов: guard-функции видно по коду 303."""
    return TestClient(main.app, follow_redirects=False)


@pytest.fixture()
def identities(seed) -> list:
    """Три роли для свипа: аноним, кандидат, работодатель."""
    return [("anon", None),
            ("candidate", seed["tokens"]["candidate"]),
            ("employer", seed["tokens"]["employer"])]


@pytest.fixture()
def strict_templates():
    """Jinja2 в режиме StrictUndefined: ловим непереданные переменные контекста.

    Окружение общее для всего процесса, поэтому после теста прежнее значение
    возвращаем — иначе строгий режим «протечёт» в соседние тесты.
    """
    previous = web.templates.env.undefined
    web.templates.env.undefined = StrictUndefined
    yield web.templates.env
    web.templates.env.undefined = previous
    assert web.templates.env.undefined is Undefined
