"""Демо-данные стенда (seed.py): состав, правила раздела 6 и идемпотентность.

Сид проверяется на отдельной временной базе — свой engine, чтобы не пересекаться
с данными смоук-тестов из conftest.py и не трогать ``database.db`` репозитория.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import logic
import seed
from models import (STATUS_ACCEPTED, STATUS_SENT, Application, Candidate, Employer,
                    Invitation, Vacancy)


def snapshot(db: Session) -> dict:
    """Снимок стенда простыми типами: объекты не нужны после закрытия сессии."""
    candidates = db.exec(select(Candidate)).all()
    employers = db.exec(select(Employer)).all()
    vacancies = db.exec(select(Vacancy)).all()
    invitations = db.exec(select(Invitation)).all()
    names = {row.id: row.name for row in candidates}
    companies = {row.id: row.company for row in employers}
    return {
        "candidates": [{
            "email": row.email,
            "name": row.name,
            "city": row.city,
            "consent": row.consent,
            "public": row.is_public,
            "complete": logic.profile_complete(row),
            "specialization": row.specialization,
            "specialization_source": logic.resolve_specialization(row)["source"],
            "grade": row.grade,
            "verified": row.is_verified,
            "kit_connected": row.kit_connected,
            "kit_score": row.kit_score,
            "kit_number": row.kit_certificate_number,
            "fsp_connected": row.fsp_connected,
            "fsp_score": row.fsp_score,
            "fsp_category": row.fsp_category,
            "fsp_role": row.fsp_role,
            "ambitious": row.ambition,
            "top_fsp": logic.is_top_fsp(row),
            "min_tier": logic.candidate_min_tier(row),
            "profile_level": logic.profile_level(row),
        } for row in candidates],
        "employers": [{
            "email": row.email,
            "company": row.company,
            "tier": row.tier,
            "answers": {question: bool(row.survey_answers.get(question))
                        for question in logic.TIER_QUESTIONS},
            "healthy": logic.tier_score(row.survey_answers),
            "survey_completed": row.survey_completed,
            "consent": row.consent,
        } for row in employers],
        "vacancies": [{
            "title": row.title,
            "company": row.company,
            "specialization": row.specialization,
            "grade": row.grade,
            "grade_match": row.grade_match,
            "open": row.open,
            "salary": (row.salary_min, row.salary_max),
        } for row in vacancies],
        "invitations": [{
            "company": companies.get(row.employer_id, ""),
            "candidate": names.get(row.candidate_id, ""),
            "status": row.status,
            "is_new": row.is_new,
            "vacancy_id": row.vacancy_id,
            "salary": (row.salary_min, row.salary_max),
        } for row in invitations],
    }


@pytest.fixture(scope="module")
def stand_engine():
    """Отдельная база с демо-набором: создаётся один раз на модуль."""
    db_path = pathlib.Path(tempfile.mkdtemp(prefix="fsp-seed-")) / "seed.db"
    engine = create_engine("sqlite:///" + str(db_path),
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        assert seed.db_is_empty(db) is True
        assert seed.ensure_demo_data(db) is True
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def stand(stand_engine) -> dict:
    with Session(stand_engine) as db:
        return snapshot(db)


def by_email(stand: dict, email: str) -> dict:
    rows = [row for row in stand["candidates"] if row["email"] == email]
    assert rows, f"в демо-наборе нет кандидата {email}"
    return rows[0]


# ---------------------------------------------------------------------------
# Состав стенда
# ---------------------------------------------------------------------------

def test_seed_creates_expected_counts(stand):
    assert len(stand["candidates"]) == 6
    assert len(stand["employers"]) == 3
    assert len(stand["vacancies"]) == 4
    assert len(stand["invitations"]) == 2


def test_every_seeded_profile_is_complete_and_public(stand):
    for row in stand["candidates"]:
        assert row["complete"] is True, row["email"]
        assert row["public"] is True, row["email"]
        assert row["consent"] is True, row["email"]
        assert row["city"], row["email"]


def test_seed_is_idempotent_when_db_is_not_empty(stand_engine):
    """Повторный вызов ничего не добавляет: база уже не пустая."""
    with Session(stand_engine) as db:
        assert seed.db_is_empty(db) is False
        assert seed.ensure_demo_data(db) is False
        assert len(db.exec(select(Candidate)).all()) == 6
        assert len(db.exec(select(Employer)).all()) == 3


# ---------------------------------------------------------------------------
# Кандидаты: шесть строк матрицы видимости и верификации грейда
# ---------------------------------------------------------------------------

def test_top_fsp_candidate(stand):
    row = by_email(stand, "artem.petrov@fsp.demo")
    assert row["grade"] == "senior" and row["verified"] is True
    assert row["kit_score"] == 95 and row["kit_number"].endswith("-S-101845")
    assert row["fsp_connected"] is True and row["fsp_category"] == "S"
    assert row["fsp_score"] == 160 and row["fsp_role"] == "капитан"
    assert row["ambitious"] is True and row["top_fsp"] is True
    assert row["min_tier"] == 3 and row["profile_level"] == "топ ФСП"
    assert row["specialization"] == "backend"
    assert row["specialization_source"] == "kit"


def test_strong_middle_candidate(stand):
    row = by_email(stand, "anna.sokolova@fsp.demo")
    assert row["grade"] == "middle" and row["verified"] is True
    assert row["kit_score"] == 72
    assert row["fsp_category"] == "B" and row["fsp_role"] == "участник"
    assert row["min_tier"] == 2 and row["profile_level"] == "мидл"
    assert row["specialization"] == "frontend"


def test_ambitious_junior_with_bronze(stand):
    row = by_email(stand, "mark.ivanov@fsp.demo")
    assert row["grade"] == "junior" and row["verified"] is True
    assert row["kit_score"] == 45
    assert row["fsp_category"] == "C" and row["fsp_role"] == "капитан"
    assert row["ambitious"] is True
    assert row["min_tier"] == 2 and row["profile_level"] == "новичок с амбициями"
    assert row["specialization"] == "ds"


def test_junior_without_ambitions_kit_and_fsp(stand):
    row = by_email(stand, "egor.timofeev@demo.local")
    assert row["kit_connected"] is False and row["verified"] is False
    assert row["fsp_connected"] is False and row["fsp_score"] == 0
    assert row["fsp_category"] == "D"
    assert row["grade"] == "junior" and row["ambitious"] is False
    assert row["min_tier"] == 1 and row["profile_level"] == "новичок без амбиций"
    assert row["specialization"] == "support"
    # ручная специализация в анкете побеждает стек: ни КИТ, ни ФСП нет (раздел 6.1)
    assert row["specialization_source"] == "manual"


def test_middle_without_fsp_history(stand):
    row = by_email(stand, "pavel.kulagin@demo.local")
    assert row["fsp_connected"] is False and row["fsp_score"] == 0
    assert row["grade"] == "middle" and row["verified"] is True
    assert row["kit_score"] == 80
    assert row["min_tier"] == 2 and row["specialization"] == "ds"


def test_junior_without_kit_is_not_verified(stand):
    row = by_email(stand, "maria.lebedeva@fsp.demo")
    assert row["kit_connected"] is False and row["verified"] is False
    assert row["fsp_connected"] is True and row["fsp_category"] == "B"
    assert row["grade"] == "junior" and row["min_tier"] == 1


# ---------------------------------------------------------------------------
# Работодатели, потребности, приглашения
# ---------------------------------------------------------------------------

def test_employer_tiers_follow_survey_answers(stand):
    tiers = {row["company"]: row for row in stand["employers"]}
    assert set(tiers) == {"Прогресс-Софт", "СтабилИТ", "Быстрая разработка"}
    assert (tiers["Прогресс-Софт"]["tier"], tiers["Прогресс-Софт"]["healthy"]) == (3, 6)
    assert (tiers["СтабилИТ"]["tier"], tiers["СтабилИТ"]["healthy"]) == (2, 4)
    assert (tiers["Быстрая разработка"]["tier"],
            tiers["Быстрая разработка"]["healthy"]) == (1, 2)
    for row in stand["employers"]:
        assert row["survey_completed"] is True and row["consent"] is True
        assert row["healthy"] == logic.tier_score(row["answers"])
        assert row["tier"] == logic.compute_tier(row["answers"])


def test_vacancies_cover_four_scenarios(stand):
    needs = {row["title"]: row for row in stand["vacancies"]}
    assert set(needs) == {"Backend Middle", "Frontend Junior", "DS Middle",
                          "Support Senior"}
    assert (needs["Backend Middle"]["company"], needs["Backend Middle"]["specialization"],
            needs["Backend Middle"]["grade"]) == ("Прогресс-Софт", "backend", "middle")
    assert (needs["Frontend Junior"]["company"], needs["Frontend Junior"]["specialization"],
            needs["Frontend Junior"]["grade"]) == ("СтабилИТ", "frontend", "junior")
    assert (needs["DS Middle"]["company"], needs["DS Middle"]["specialization"],
            needs["DS Middle"]["grade"]) == ("Прогресс-Софт", "ds", "middle")
    assert (needs["Support Senior"]["company"], needs["Support Senior"]["specialization"],
            needs["Support Senior"]["grade"]) == ("Быстрая разработка", "support", "senior")
    for row in stand["vacancies"]:
        assert row["open"] is True and row["grade_match"] == "plus_minus"
        assert row["salary"][0] < row["salary"][1]


def test_invitations_have_accepted_and_sent(stand):
    rows = {row["candidate"]: row for row in stand["invitations"]}
    accepted = rows["Петров Артём Игоревич"]
    assert accepted["company"] == "Прогресс-Софт"
    assert accepted["status"] == STATUS_ACCEPTED and accepted["is_new"] is False
    sent = rows["Соколова Анна Дмитриевна"]
    assert sent["company"] == "СтабилИТ"
    assert sent["status"] == STATUS_SENT and sent["is_new"] is True
    for row in stand["invitations"]:
        assert row["vacancy_id"] and row["salary"][0] < row["salary"][1]


# ---------------------------------------------------------------------------
# Правила раздела 6 на демо-наборе
# ---------------------------------------------------------------------------

def test_visibility_matrix_by_tier(stand):
    rows = stand["candidates"]
    assert len([row for row in rows if row["min_tier"] <= 1]) == 2
    assert len([row for row in rows if row["min_tier"] <= 2]) == 5
    assert len([row for row in rows if row["min_tier"] <= 3]) == 6


def test_ranking_under_demo_needs(stand_engine):
    """Топ ФСП — первый в backend, DS ранжирует мидла выше новичка, tier 1 видит junior."""
    with Session(stand_engine) as db:
        candidates = db.exec(select(Candidate)).all()
        employers = {row.company: row for row in db.exec(select(Employer)).all()}
        needs = {row.title: row for row in db.exec(select(Vacancy)).all()}

        backend = logic.rank_candidates(candidates, needs["Backend Middle"],
                                        employers["Прогресс-Софт"].tier)
        assert [row[0].name for row in backend] == ["Петров Артём Игоревич"]
        assert backend[0][1]["score"] == 100

        data = logic.rank_candidates(candidates, needs["DS Middle"],
                                     employers["Прогресс-Софт"].tier)
        assert [row[0].name for row in data] == ["Кулагин Павел Дмитриевич",
                                                 "Иванов Марк Сергеевич"]
        assert data[0][1]["score"] > data[1][1]["score"]

        frontend = logic.rank_candidates(candidates, needs["Frontend Junior"],
                                         employers["СтабилИТ"].tier)
        assert [row[0].name for row in frontend] == ["Соколова Анна Дмитриевна"]

        support = logic.rank_candidates(candidates, needs["Support Senior"],
                                        employers["Быстрая разработка"].tier)
        assert [row[0].name for row in support] == ["Тимофеев Егор Павлович"]
        assert support[0][1]["grade_ok"] is False   # junior против senior — честно


def test_top_fsp_is_hidden_from_lower_tiers(stand_engine):
    with Session(stand_engine) as db:
        candidates = db.exec(select(Candidate)).all()
        top = [row for row in candidates if logic.is_top_fsp(row)]
        assert len(top) == 1
        assert logic.is_visible(top[0], 3) is True
        assert logic.is_visible(top[0], 2) is False
        assert logic.is_visible(top[0], 1) is False


def test_demo_accounts_cover_the_stand(stand):
    accounts = seed.demo_accounts()
    emails = [row["email"] for row in accounts]
    assert len(accounts) == 9
    for row in stand["candidates"] + stand["employers"]:
        assert row["email"] in emails
    for account in accounts:
        assert account["role"] in ("candidate", "employer")
        assert account["name"] and account["note"]


def test_reset_demo_rebuilds_the_stand(stand_engine):
    """--force: полная очистка и пересборка стенда дают тот же состав."""
    with Session(stand_engine) as db:
        created = seed.reset_demo(db)
        assert set(created) == {"candidates", "employers", "vacancies", "invitations"}
        assert len(db.exec(select(Candidate)).all()) == 6
        assert len(db.exec(select(Vacancy)).all()) == 4
        assert len(db.exec(select(Invitation)).all()) == 2
        assert len(db.exec(select(Application)).all()) == 0
        assert seed.summary_lines(db)[0] == "Кандидаты (6):"

