"""Сквозной сценарий работодателя: анкета → тир → потребность → банк → приглашение.

Перенос /tmp/smoke_employer.py в pytest. Сценарий проверяет основную механику
платформы (работодатель находит кандидата и приглашает) и привязанные к ней
бизнес-правила:

  * анкета из 6 ответов определяет тир, а тир — состав открытых полей;
  * банк и страница потребности ранжируют кандидатов по убыванию релевантности;
  * закрытый профиль отдаёт отдельный шаблон и не даёт отправить приглашение;
  * чужая потребность недоступна (303 на свой кабинет);
  * контакты кандидата раскрываются работодателю только после принятия приглашения;
  * загрузка сертификата КИТ верифицирует грейд, а «мусорный» файл не проходит.

Данные сценария создаются поверх общих сид-кандидатов (фикстура ``seed``), поэтому
модуль не конфликтует со свипами маршрутов.
"""
from __future__ import annotations

import re

import pytest
from sqlmodel import Session, select

import database
import fsp_mock
import helpers
import kit_parser
import logic
import services
from conftest import (SPECIALIZATIONS, SURVEY_FIELDS, build_employer, build_vacancy,
                      session_token)
from models import (STATUS_ACCEPTED, STATUS_SENT, Application, Candidate, Employer,
                    Invitation, Vacancy)


# ---------------------------------------------------------------------------
# HTTP-хелперы: 303 не проходим, поэтому редирект виден как отдельный результат
# ---------------------------------------------------------------------------

def get(client, token, path, needles=(), expect=200):
    """GET с нужной ролью: проверяем код и наличие иголок в HTML."""
    client.cookies.clear()
    if token:
        client.cookies.set("fsp_session", token)
    response = client.get(path)
    assert response.status_code == expect, (path, response.status_code,
                                            response.text[:800])
    missing = [needle for needle in needles if needle not in response.text]
    assert not missing, (path, missing)
    return response


def post(client, token, path, data=None, expect=303):
    """POST формы: успешная запись всегда уходит редиректом 303 (PRG)."""
    client.cookies.clear()
    if token:
        client.cookies.set("fsp_session", token)
    response = client.post(path, data=data or {})
    assert response.status_code == expect, (path, response.status_code,
                                            response.text[:800])
    return response


@pytest.fixture(scope="module")
def flow(seed):
    """Данные сценария: работодатель тира 3, работодатель тира 1, потребности."""
    with Session(database.engine) as db:
        emp_tier3 = build_employer(db, "flow.tier3@test.demo", "Флоу Софт", healthy=True)
        emp_tier1 = build_employer(db, "flow.tier1@test.demo", "Флоу Плюс", healthy=False)
        vacancy_open = build_vacancy(db, emp_tier3, "Backend-разработчик",
                                     published=True, grade="middle")
        vacancy_hidden = build_vacancy(db, emp_tier3, "Инженер платформы",
                                       published=False, grade="senior")
        return {
            "seed": seed,
            "emp_tier3": emp_tier3.id,
            "emp_tier1": emp_tier1.id,
            "vacancy_open": vacancy_open.id,
            "vacancy_hidden": vacancy_hidden.id,
            "t3": session_token(emp_tier3, "employer", "flow-t3"),
            "t1": session_token(emp_tier1, "employer", "flow-t1"),
        }
# ---------------------------------------------------------------------------
# Анкета процессов → тир → состав открытых полей (разделы 7.1, 11.15)
# ---------------------------------------------------------------------------

def test_survey_answers_define_tier():
    """6 «здоровых» ответов → тир 3, ни одного → тир 1, четыре → тир 2."""
    assert logic.employer_tier({field: True for field in SURVEY_FIELDS}) == 3
    assert logic.employer_tier({field: False for field in SURVEY_FIELDS}) == 1
    four = {field: index < 4 for index, field in enumerate(SURVEY_FIELDS)}
    assert logic.employer_tier(four) == 2


def test_tier_decides_visible_fields():
    """Тир решает состав полей: 6 → 8 → 10 (раздел 11.15).

    Тиры 1 и 2 видят достижения ФСП кратко, тир 3 — полностью. Город и полный
    профиль доступны только тиру 3, амбициозность и роль в команде ФСП — с тира 2.
    """
    assert len(logic.TIER_FIELDS[1]) == 6
    assert len(logic.TIER_FIELDS[2]) == 8
    assert len(logic.TIER_FIELDS[3]) == 10
    assert set(logic.TIER_FIELDS[1]) < set(logic.TIER_FIELDS[2])
    assert set(logic.TIER_FIELDS[2]) - {"достижения ФСП кратко"} < set(logic.TIER_FIELDS[3])
    assert "достижения ФСП" in logic.TIER_FIELDS[3]
    for field in ("город", "полный профиль"):
        assert field not in logic.TIER_FIELDS[1], field
        assert field not in logic.TIER_FIELDS[2], field
    for field in ("амбициозность", "роль в команде ФСП"):
        assert field not in logic.TIER_FIELDS[1], field


def test_match_weights_sum_to_100():
    """Веса релевантности дают ровно 100 (раздел 6.5): 35 + 25 + 20 + 10 + 10."""
    assert sum(logic.MATCH_WEIGHTS.values()) == 100
    assert logic.MATCH_WEIGHTS["specialization"] == 35
    assert logic.MATCH_WEIGHTS["stack"] == 25


def test_survey_post_recalculates_tier(client):
    """POST /employer/survey перезаписывает ответы и пересчитывает тир."""
    with Session(database.engine) as db:
        employer = build_employer(db, "flow.survey@test.demo", "Анкета Тест",
                                 healthy=False)
        employer_id = employer.id
        token = session_token(employer, "employer", "flow-survey")
    assert employer_id and token
    post(client, token, "/employer/survey",
         {field: "true" for field in SURVEY_FIELDS})
    with Session(database.engine) as db:
        refreshed = db.get(Employer, employer_id)
        assert refreshed.tier == 3
        assert all(refreshed.survey_answers.values())
        assert refreshed.survey_completed


def test_employer_without_survey_redirected(client):
    """Без анкеты процессов кабинет закрыт: 303 на /register/employer/survey."""
    with Session(database.engine) as db:
        employer = Employer(email="flow.nosurvey@test.demo", company="Без Анкеты",
                            consent=True)
        db.add(employer)
        db.commit()
        db.refresh(employer)
        assert not employer.survey_completed
        token = session_token(employer, "employer", "flow-nosurvey")
    response = get(client, token, "/employer", expect=303)
    assert response.headers["location"].startswith("/register/employer/survey")


def test_foreign_vacancy_redirects(client, flow):
    """Чужая потребность недоступна: 303 и никакого содержимого."""
    response = get(client, flow["t1"], "/employer/vacancies/%d" % flow["vacancy_open"],
                   expect=303)
    assert response.headers["location"].startswith("/employer")


# ---------------------------------------------------------------------------
# Банк кандидатов и подборка по потребности
# ---------------------------------------------------------------------------

OPEN_COUNT_RE = re.compile(r"Открытых профилей: <strong>(\d+)</strong>")
RESTRICTED_COUNT_RE = re.compile(
    r"закрыто матрицей видимости или настройками кандидата: <strong>(\d+)</strong>")


def _bank_counts(page_text: str) -> tuple:
    """Счётчики банка со страницы: (открытые профили, закрытые)."""
    open_match = OPEN_COUNT_RE.search(page_text)
    restricted_match = RESTRICTED_COUNT_RE.search(page_text)
    assert open_match and restricted_match, page_text[:500]
    return int(open_match.group(1)), int(restricted_match.group(1))


def test_bank_visibility_follows_matrix(client, flow):
    """Тир 3 видит больше кандидатов: топ ФСП отсекается матрицей (раздел 8.4).

    Банк показывает все анкеты с полным профилем, но закрытые — с маркером
    «Почему закрыт» и без данных, поэтому сравниваем счётчики страницы и состав
    карточки на уровне ``helpers.candidate_card``.
    """
    page_tier3 = get(client, flow["t3"], "/employer/bank", ["Банк кандидатов"])
    page_tier1 = get(client, flow["t1"], "/employer/bank", ["Банк кандидатов"])
    open_tier3, restricted_tier3 = _bank_counts(page_tier3.text)
    open_tier1, restricted_tier1 = _bank_counts(page_tier1.text)
    assert open_tier3 > open_tier1, (open_tier3, open_tier1)
    assert restricted_tier3 < restricted_tier1, (restricted_tier3, restricted_tier1)

    with Session(database.engine) as db:
        candidates = [row for row in helpers.list_candidates(db)
                      if logic.profile_complete(row) and row.visible_in_bank]
        tier1_ids = {row.id for row in logic.visible_candidates(candidates, 1)}
        restricted = [row for row in logic.visible_candidates(candidates, 3)
                      if row.id not in tier1_ids]
        assert restricted, "матрица видимости не отсекла ни одного профиля"
        top_fsp = [row for row in candidates if logic.is_top_fsp(row)]
        assert top_fsp, "в демо-данных нет ни одного топ-кандидата ФСП"
        for candidate in top_fsp:
            assert logic.candidate_min_tier(candidate) == 3, candidate.email
        for candidate in restricted:
            # скрыт от тира 1: минимум второй тир (топ ФСП — третий)
            assert logic.candidate_min_tier(candidate) >= 2, candidate.email
            assert logic.is_visible(candidate, 3)
            assert not logic.is_visible(candidate, 1)
            card_tier3 = helpers.candidate_card(candidate, 3)["profile"]
            card_tier1 = helpers.candidate_card(candidate, 1)["profile"]
            assert card_tier3["is_open"] is True and card_tier3["city"]
            assert card_tier1["is_open"] is False
            assert card_tier1["city"] == ""
            assert card_tier1["fsp_role"] == "" and card_tier1["is_ambitious"] is None
            # ФИО не публикуется в банке ни на одном тире
            assert candidate.name not in page_tier3.text
            assert candidate.name not in page_tier1.text
            # страница профиля: тиру 3 открыта, тиру 1 — объяснение ограничения
            get(client, flow["t3"], "/employer/candidates/%d" % candidate.id,
                ["Пригласить", "Барометр амбиций"])
            get(client, flow["t1"], "/employer/candidates/%d" % candidate.id,
                ["Профиль закрыт", "Доступ ограничен"])


def test_vacancy_page_ranks_by_relevance(client, flow):
    """Подборка на странице потребности отсортирована по убыванию релевантности."""
    url = "/employer/vacancies/%d" % flow["vacancy_open"]
    page = get(client, flow["t3"], url, ["Кандидаты по убыванию релевантности"])
    with Session(database.engine) as db:
        employer = db.get(Employer, flow["emp_tier3"])
        vacancy = db.get(Vacancy, flow["vacancy_open"])
        rows = helpers.vacancy_candidates(db, employer, vacancy)
    assert rows, "подборка пуста: ни один кандидат не прошёл фильтр"
    scores = [row["match"]["score"] for row in rows]
    assert scores == sorted(scores, reverse=True), scores
    assert all(0 <= score <= 100 for score in scores), scores
    first_name = rows[0]["candidate"]["profile"]["name"]
    assert first_name in page.text, first_name


def test_hidden_vacancy_not_in_needs_bank(client, flow, seed):
    """Потребность с open=False не публикуется в банке /needs."""
    page = get(client, seed["tokens"]["candidate"], "/needs", ["Банк потребностей"])
    assert "Инженер платформы" not in page.text
    assert "Backend-разработчик" in page.text
    get(client, seed["tokens"]["candidate"],
        "/needs/%d" % flow["vacancy_hidden"], expect=303)
# ---------------------------------------------------------------------------
# Сертификат КИТ: распознавание и отказоустойчивость (разделы 6.2, 6.3)
# ---------------------------------------------------------------------------

def test_kit_certificate_parsed():
    """Демо-сертификат распознаётся: номер, дисциплина, грейд, баллы, дата."""
    parsed = services.parse_kit_upload(
        "kit.txt", kit_parser.DEMO_CERTIFICATE_TEXT.encode("utf-8"))
    assert parsed["error"] == ""
    assert parsed["certificate_number"] == "20260119-37-S-102905"
    assert "КИТ i.moscow" in parsed["competition"]
    assert parsed["grade"] == "senior"          # буква S в номере сертификата
    assert parsed["kit_score"] == 84
    assert parsed["date"] == "19.01.2026"
    assert parsed["specialization"] == "support"


def test_kit_garbage_file_rejected():
    """Файл без признаков сертификата не проходит: ошибка, грейда и баллов нет."""
    parsed = services.parse_kit_upload("notes.txt", "просто заметки".encode("utf-8"))
    assert parsed["error"]
    assert parsed["place"] is None
    assert parsed["team"] == []
    assert not parsed["grade"]
    assert parsed["kit_score"] is None


def test_kit_is_the_only_verification_source():
    """Верификацию грейда даёт только КИТ: после удаления сертификата она снимается."""
    with Session(database.engine) as db:
        candidate = Candidate(email="flow.kit@test.demo", name="Тестов Кит", consent=True)
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        assert logic.resolve_grade_for(candidate)["verified"] is False

        parsed = services.parse_kit_upload(
            "kit.txt", kit_parser.DEMO_CERTIFICATE_TEXT.encode("utf-8"))
        services.apply_kit(candidate, parsed, "text")
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        grade = logic.resolve_grade_for(candidate)
        assert grade["verified"] is True
        assert grade["grade"] == "senior"
        assert candidate.kit_score == 84
        assert candidate.kit_certificate_number == parsed["certificate_number"]

        services.remove_kit(candidate)
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        assert logic.resolve_grade_for(candidate)["verified"] is False


# ---------------------------------------------------------------------------
# Закрытый профиль и приглашение (разделы 8.4, 10.4)
# ---------------------------------------------------------------------------

def _invitation_ids(employer_id: int) -> set:
    with Session(database.engine) as db:
        rows = db.exec(
            select(Invitation).where(Invitation.employer_id == employer_id)).all()
        return {row.id for row in rows}


def test_restricted_profile_blocks_invitation(client, flow, seed):
    """Скрытый профиль: отдельный шаблон, причина закрытия, приглашение не создаётся."""
    hidden_id = seed["hidden_id"]
    get(client, flow["t3"], "/employer/candidates/%d" % hidden_id,
        ["Профиль закрыт", "Доступ ограничен", "Приглашение недоступно"])
    before = _invitation_ids(flow["emp_tier3"])
    post(client, flow["t3"], "/employer/vacancies/%d/invite" % flow["vacancy_open"],
         {"candidate_id": hidden_id, "message": "Приглашаем в команду"})
    assert _invitation_ids(flow["emp_tier3"]) == before, "приглашение закрытому профилю"


def test_invite_reveals_contacts_only_after_accept(client, flow, seed):
    """Приглашение → ожидание → принятие: контакты видны только после принятия."""
    candidate_id = seed["verified_id"]
    with Session(database.engine) as db:
        candidate_email = db.get(Candidate, candidate_id).email

    post(client, flow["t3"], "/employer/vacancies/%d/invite" % flow["vacancy_open"],
         {"candidate_id": candidate_id, "message": "Приглашаем в команду"})

    with Session(database.engine) as db:
        invitation = db.exec(select(Invitation).where(
            Invitation.employer_id == flow["emp_tier3"],
            Invitation.vacancy_id == flow["vacancy_open"])).first()
        assert invitation is not None
        assert invitation.status == STATUS_SENT
        assert invitation.salary_min > 0 and invitation.salary_max > 0
        invitation_id = invitation.id

    waiting = get(client, flow["t3"], "/employer/invitations",
                  ["Отправленные приглашения", "скроют до принятия приглашения"])
    assert candidate_email not in waiting.text, "контакты раскрыты до принятия"

    post(client, seed["tokens"]["candidate"],
         "/candidate/invitations/%d/accept" % invitation_id)
    with Session(database.engine) as db:
        assert db.get(Invitation, invitation_id).status == STATUS_ACCEPTED

    accepted = get(client, flow["t3"], "/employer/invitations",
                   ["Отправленные приглашения", "принято: 1"])
    assert candidate_email in accepted.text, "контакты не раскрылись после принятия"


def test_duplicate_invitation_not_created(client, flow, seed):
    """Повторное приглашение тому же кандидату по той же потребности не создаётся."""
    url = "/employer/vacancies/%d/invite" % flow["vacancy_open"]
    payload = {"candidate_id": seed["verified_id"], "message": "Ещё раз"}
    post(client, flow["t3"], url, payload)      # первое приглашение (или повтор уже существующего)
    before = _invitation_ids(flow["emp_tier3"])
    post(client, flow["t3"], url, payload)      # дубль — новая запись не появляется
    assert _invitation_ids(flow["emp_tier3"]) == before


# ---------------------------------------------------------------------------
# Отклик кандидата и решение работодателя (раздел 10.3)
# ---------------------------------------------------------------------------

def test_application_flow(client, flow, seed):
    """Отклик → статус «принят»: кандидат откликается, работодатель меняет статус."""
    post(client, seed["tokens"]["candidate"],
         "/needs/%d/apply" % flow["vacancy_open"], {"message": "Готов обсудить задачу"})
    with Session(database.engine) as db:
        application = db.exec(select(Application).where(
            Application.candidate_id == seed["verified_id"],
            Application.vacancy_id == flow["vacancy_open"])).first()
        assert application is not None
        assert application.status == STATUS_SENT
        assert application.employer_id == flow["emp_tier3"]
        application_id = application.id

    post(client, flow["t3"], "/employer/applications/%d/status" % application_id,
         {"status": STATUS_ACCEPTED})
    with Session(database.engine) as db:
        assert db.get(Application, application_id).status == STATUS_ACCEPTED
    get(client, flow["t3"], "/employer/applications", ["Отклики кандидатов", "принят"])

    # недопустимый статус отклоняется редиректом, запись не меняется
    post(client, flow["t3"], "/employer/applications/%d/status" % application_id,
         {"status": "invented"})
    with Session(database.engine) as db:
        assert db.get(Application, application_id).status == STATUS_ACCEPTED


def test_candidate_sees_application_status(client, flow, seed):
    """Статус отклика виден кандидату в кабинете (раздел 13.4)."""
    post(client, seed["tokens"]["candidate"], "/needs/%d/apply" % flow["vacancy_open"],
         {"message": "Повторный отклик"})
    get(client, seed["tokens"]["candidate"], "/candidate/applications",
        ["Мои отклики", "Backend-разработчик"])


# ---------------------------------------------------------------------------
# Жизненный цикл потребности и разделы кабинета
# ---------------------------------------------------------------------------

def test_vacancy_create_toggle_delete(client, flow):
    """Создание потребности, снятие с публикации и удаление."""
    post(client, flow["t3"], "/employer/vacancies/new", {
        "title": "Инженер данных (тест)", "specialization": SPECIALIZATIONS[0],
        "grade": "junior", "grade_match": "exact", "salary_min": "150000",
        "salary_max": "220000", "format": "hybrid", "city": "Москва",
        "team_size": "8 человек", "description": "Работа над платформой",
        "stack": "Python", "open": "on",
    })
    with Session(database.engine) as db:
        vacancy = db.exec(
            select(Vacancy).where(Vacancy.title == "Инженер данных (тест)")).first()
        assert vacancy is not None
        assert vacancy.employer_id == flow["emp_tier3"]
        assert vacancy.open is True
        vacancy_id = vacancy.id

    post(client, flow["t3"], "/employer/vacancies/%d/toggle" % vacancy_id, {})
    with Session(database.engine) as db:
        assert db.get(Vacancy, vacancy_id).open is False

    post(client, flow["t3"], "/employer/vacancies/%d/delete" % vacancy_id, {})
    with Session(database.engine) as db:
        assert db.get(Vacancy, vacancy_id) is None


def test_employer_cabinet_pages(client, flow):
    """Разделы кабинета работодателя открываются и показывают свои данные."""
    get(client, flow["t3"], "/employer", ["Флоу Софт", "Потребности и подбор"])
    get(client, flow["t3"], "/employer/survey", ["Анкета"])
    get(client, flow["t3"], "/employer/bank", ["Банк кандидатов"])
    get(client, flow["t3"], "/employer/bank?spec=" + SPECIALIZATIONS[0])
    get(client, flow["t3"], "/employer/vacancies/new", ["Новая потребность", "salary_min"])
    get(client, flow["t3"], "/employer/vacancies/%d" % flow["vacancy_hidden"],
        ["скрыта из банка"])
    get(client, flow["t3"], "/employer/applications", ["Отклики кандидатов"])
    get(client, flow["t3"], "/employer/invitations", ["Отправленные приглашения"])
    get(client, flow["t1"], "/employer", ["Флоу Плюс"])


def test_registration_data_is_seeded_from_mock_registry():
    """Мок-реестр ФСП отдаёт историю всем демо-кандидатам (заглушка вместо API)."""
    assert len(fsp_mock.FSP_REGISTRY) >= 6
    for email, record in fsp_mock.FSP_REGISTRY.items():
        achievements = fsp_mock.get_achievements(email)["achievements"]
        assert record["name"], email
        assert isinstance(achievements, list), email
