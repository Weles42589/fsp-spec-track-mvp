"""Демо-данные стенда для защиты проекта (п. 12.2 документации).

Набор подобран так, чтобы на одной базе показать все правила раздела 6 ТЗ:
матрицу видимости (топ ФСП, мидл, новичок с амбициями, новичок без амбиций),
верификацию грейда сертификатом КИТ, категории истории ФСП, тиры работодателей
и ранжирование кандидатов под потребность.

Данные создаются штатными сервисами — теми же функциями, которые вызывает
реальная регистрация (``services.apply_candidate_profile``, ``services.connect_fsp``,
``services.apply_kit``, ``services.apply_employer_profile``,
``services.apply_employer_survey``). Поэтому демо-анкеты не могут разойтись
с правилами приложения: грейд, специализация, амбициозность, категория ФСП и тир
рассчитываются, а не записываются вручную.

Запуск:
    uvicorn main:app --reload    # при старте база заполняется, если она пустая
    python3.13 seed.py           # то же самое вручную: пустая база → демо-набор
    python3.13 seed.py --force   # очистить базу и пересобрать стенд заново
"""
import argparse
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

import fsp_mock
import logic
import services
from database import engine, init_db
from models import (STATUS_ACCEPTED, STATUS_SENT, Achievement, Application, Candidate,
                    Employer, Invitation, UserSession, Vacancy, utcnow)

# ---------------------------------------------------------------------------
# Сертификаты КИТ: текст формата раздела 8.1 → штатный парсер
# ---------------------------------------------------------------------------

KIT_CERTIFICATE_TEXT = """КИТ
{name}
Прошел(а) тестирование по специальности {specialty}
Результат {score} баллов из 100
Уровень Грейда {grade_title}
Город {city}
Выдан {issued}
{number}
"""


def kit_certificate(name: str, specialty: str, score: int, grade: str, city: str,
                    issued: str, number: str) -> str:
    """Собрать текст сертификата КИТ (раздел 8.1).

    Дальше текст идёт через ``services.parse_kit_upload`` — как настоящая загрузка
    файла, поэтому номер, дату и специальность распознаёт рабочий парсер.
    """
    return KIT_CERTIFICATE_TEXT.format(
        name=name,
        specialty=specialty,
        score=score,
        grade_title=logic.grade_title(grade),
        city=city,
        issued=issued,
        number=number,
    )


# ---------------------------------------------------------------------------
# Кандидаты: 6 анкет, каждая — своя строка матрицы видимости (раздел 6.5)
# ---------------------------------------------------------------------------

DEMO_CANDIDATES: List[Dict[str, Any]] = [
    {
        "key": "top",
        "label": "топ ФСП: senior, КИТ 95 (золото), категория S, капитан, амбициозный",
        "email": "artem.petrov@fsp.demo",
        "profile": {
            "city": "Москва",
            "team_role": "капитан",
            "work_format": logic.WORK_FORMAT_INFLUENCE,
            "stack": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "fsp_role": "капитан",
            "ambitions": ["captain", "influence", "wide_stack", "fsp_captain"],
        },
        "fsp": True,
        "kit": {
            "specialty": "Специалист по серверной разработке (Python/Go)",
            "score": 95,
            "grade": "senior",
            "city": "Москва",
            "issued": "15.12.2025",
            "number": "20251215-12-S-101845",
        },
    },
    {
        "key": "middle",
        "label": "крепкий мидл: middle, КИТ 72 (серебро), категория B, участник",
        "email": "anna.sokolova@fsp.demo",
        "profile": {
            "city": "Санкт-Петербург",
            "team_role": "разработчик",
            "work_format": logic.WORK_FORMAT_INFLUENCE,
            "stack": ["React", "TypeScript", "Node.js"],
            "fsp_role": "участник",
            "ambitions": ["influence", "wide_stack"],
        },
        "fsp": True,
        "kit": {
            "specialty": "Frontend-разработчик (React/TypeScript)",
            "score": 72,
            "grade": "middle",
            "city": "Санкт-Петербург",
            "issued": "10.02.2026",
            "number": "20260210-08-M-103402",
        },
    },
    {
        "key": "junior_ambitious",
        "label": "новичок с амбициями: junior, КИТ 45, бронза ФСП (3-е место), капитан",
        "email": "mark.ivanov@fsp.demo",
        "profile": {
            "city": "Казань",
            "team_role": "капитан",
            "work_format": logic.WORK_FORMAT_INFLUENCE,
            "stack": ["Python", "pandas", "Airflow"],
            "fsp_role": "капитан",
            "ambitions": ["captain", "influence", "wide_stack", "fsp_captain"],
        },
        "fsp": True,
        "kit": {
            "specialty": "Специалист по данным и машинному обучению",
            "score": 45,
            "grade": "junior",
            "city": "Казань",
            "issued": "14.03.2026",
            "number": "20260314-22-J-104118",
        },
    },
    {
        "key": "junior_plain",
        "label": "новичок без амбиций: junior, без КИТ, без ФСП",
        "email": "egor.timofeev@demo.local",
        "name": "Тимофеев Егор Павлович",
        "profile": {
            "city": "Воронеж",
            "team_role": "исполнитель",
            "work_format": logic.WORK_FORMAT_EXECUTE,
            "stack": ["helpdesk", "Jira"],
            "specialization": "support",   # выбран вручную: ни КИТ, ни ФСП нет
            "fsp_role": "",
            "ambitions": [],
        },
        "fsp": False,
        "kit": None,
    },
    {
        "key": "no_fsp",
        "label": "кандидат без ФСП: middle, КИТ 80 (серебро), история ФСП не подключена",
        "email": "pavel.kulagin@demo.local",
        "name": "Кулагин Павел Дмитриевич",
        "profile": {
            "city": "Москва",
            "team_role": "разработчик",
            "work_format": logic.WORK_FORMAT_INFLUENCE,
            "stack": ["Python", "pandas", "scikit-learn", "SQL"],
            "fsp_role": "",
            "ambitions": ["influence", "wide_stack"],
        },
        "fsp": False,
        "kit": {
            "specialty": "Специалист по данным и машинному обучению",
            "score": 80,
            "grade": "middle",
            "city": "Москва",
            "issued": "28.01.2026",
            "number": "20260128-05-M-103777",
        },
    },
    {
        "key": "no_kit",
        "label": "кандидат без КИТ: junior, категория B, грейд не верифицирован",
        "email": "maria.lebedeva@fsp.demo",
        "profile": {
            "city": "Новосибирск",
            "team_role": "разработчик",
            "work_format": logic.WORK_FORMAT_EXECUTE,
            "stack": ["Python", "Linux", "Wireshark"],
            "fsp_role": "разработчик",   # как в реестре ФСП: старшая роль — разработчик
            "ambitions": ["wide_stack"],
        },
        "fsp": True,
        "kit": None,
    },
]


# ---------------------------------------------------------------------------
# Работодатели: три тира — 6, 4 и 2 «здоровых» ответа анкеты (разделы 6.4, 7.1)
# ---------------------------------------------------------------------------

DEMO_EMPLOYERS: List[Dict[str, Any]] = [
    {
        "key": "progress",
        "company": "Прогресс-Софт",
        "email": "hr@progress-soft.demo",
        "contact_name": "Ковалёва Ирина",
        "position": "Руководитель отдела разработки",
        "city": "Москва",
        "description": "Продуктовая компания: собственный SaaS для логистики, 240 сотрудников, "
                       "разработка полностью in-house. Правка попадает на тестовый стенд в день "
                       "готовности, онбординг с наставником и чек-листом, на инженера заложено "
                       "8 000 ₽ в месяц (питание, спорт, ДМС).",
        # все 6 ответов — вариант А (здоровый) → тир 3
        "answers": {field: True for field in logic.TIER_QUESTIONS},
    },
    {
        "key": "stabilit",
        "company": "СтабилИТ",
        "email": "hr@stabilit.demo",
        "contact_name": "Дорохов Олег",
        "position": "HR-директор",
        "city": "Санкт-Петербург",
        "description": "Разработчик отраслевых сервисов, 90 сотрудников. Релиз в тестовый контур "
                       "занимает день, рабочее место чинят одним запросом в службу заботы, "
                       "удалённым выдают ноутбуки. Часть модулей делают подрядчики, бюджет "
                       "на инженера — 8 000 ₽ в месяц.",
        # 4 здоровых ответа из 6 → тир 2
        "answers": {
            "q1_lead_time": True,
            "q2_support": True,
            "q3_remote": False,
            "q4_mistake": True,
            "q5_outsource": False,
            "q6_benefits": True,
        },
    },
    {
        "key": "fastdev",
        "company": "Быстрая разработка",
        "email": "hr@fast-dev.demo",
        "contact_name": "Соболева Марина",
        "position": "Директор",
        "city": "Казань",
        "description": "Студия заказной разработки, 25 сотрудников: быстро берём задачи в работу "
                       "и держим короткий цикл согласований. Часть процессов ещё выстраиваем: "
                       "периферию сотрудник согласует с АХО, отдельные модули закрывает подрядчик, "
                       "релиз на стенд — раз в несколько дней.",
        # 2 здоровых ответа из 6 → тир 1
        "answers": {
            "q1_lead_time": False,
            "q2_support": True,
            "q3_remote": False,
            "q4_mistake": False,
            "q5_outsource": False,
            "q6_benefits": True,
        },
    },
]


# ---------------------------------------------------------------------------
# Потребности: 4 карточки, по одной на каждый сценарий подбора (раздел 10.3)
# ---------------------------------------------------------------------------

DEMO_VACANCIES: List[Dict[str, Any]] = [
    {
        "key": "backend_middle",
        "employer": "progress",
        "title": "Backend Middle",
        "specialization": "backend",
        "grade": "middle",
        "grade_match": "plus_minus",
        "stack": ["Python", "FastAPI", "PostgreSQL"],
        "salary_min": 250000,
        "salary_max": 350000,
        "format": "hybrid",
        "city": "Москва",
        "team_size": "12 инженеров",
        "description": "Продуктовая команда логистического SaaS: API на FastAPI, PostgreSQL, "
                       "очереди и интеграции с перевозчиками. Код-ревью и парное программирование, "
                       "релиз в тестовый контур в день готовности задачи.",
    },
    {
        "key": "frontend_junior",
        "employer": "stabilit",
        "title": "Frontend Junior",
        "specialization": "frontend",
        "grade": "junior",
        "grade_match": "plus_minus",
        "stack": ["React", "TypeScript", "CSS"],
        "salary_min": 120000,
        "salary_max": 180000,
        "format": "remote",
        "city": "Санкт-Петербург",
        "team_size": "6 инженеров",
        "description": "Команда интерфейсов отраслевого сервиса: React, TypeScript, дизайн-система. "
                       "Наставник на первые три месяца, задачи нарезаем так, чтобы новичок выходил "
                       "на первую правку в продуктиве в течение недели.",
    },
    {
        "key": "ds_middle",
        "employer": "progress",
        "title": "DS Middle",
        "specialization": "ds",
        "grade": "middle",
        "grade_match": "plus_minus",
        "stack": ["Python", "pandas", "scikit-learn"],
        "salary_min": 220000,
        "salary_max": 300000,
        "format": "hybrid",
        "city": "Москва",
        "team_size": "8 инженеров",
        "description": "Модели прогнозирования загрузки складов и качества данных: pandas, "
                       "scikit-learn, витрины в PostgreSQL. Модель уходит на стенд после ревью "
                       "и прогона метрик, вместе с объяснением допущений.",
    },
    {
        "key": "support_senior",
        "employer": "fastdev",
        "title": "Support Senior",
        "specialization": "support",
        "grade": "senior",
        "grade_match": "plus_minus",
        "stack": ["helpdesk", "Jira", "SQL"],
        "salary_min": 90000,
        "salary_max": 130000,
        "format": "office",
        "city": "Казань",
        "team_size": "3 инженера",
        "description": "Третья линия поддержки заказчиков студии: разбор инцидентов, регламенты, "
                       "обучение первой линии. Нужен опыт самостоятельного расследования сложных "
                       "обращений и работа с запросами напрямую к базе.",
    },
]


# ---------------------------------------------------------------------------
# Приглашения: принято и отправлено — оба статуса раздела 6.8 (раздел 10.4)
# ---------------------------------------------------------------------------

DEMO_INVITATIONS: List[Dict[str, Any]] = [
    {
        "employer": "progress",
        "candidate": "top",
        "vacancy": "backend_middle",
        "status": STATUS_ACCEPTED,
        "message": "Артём Игоревич, ваш профиль в банке — категория S, 95 баллов КИТ, роль "
                   "капитана команды. Нужен сильный backend в продуктовую команду: готовы "
                   "обсудить задачи и вилку на этой неделе.",
    },
    {
        "employer": "stabilit",
        "candidate": "middle",
        "vacancy": "frontend_junior",
        "status": STATUS_SENT,
        "message": "Анна Дмитриевна, собираем команду интерфейсов. Ваш профиль (middle, 72 балла "
                   "КИТ, история ФСП) подходит под задачу — расскажем про стек и формат работы, "
                   "если приглашение интересно.",
    },
]

# ---------------------------------------------------------------------------
# Создание записей: те же шаги, что и настоящая регистрация
# ---------------------------------------------------------------------------

def candidate_name(item: Dict[str, Any]) -> str:
    """ФИО анкеты: для профилей из реестра ФСП берём имя из мока (раздел 9.4)."""
    return str(item.get("name") or fsp_mock.FSP_REGISTRY[item["email"]]["name"])


def create_candidate(db: Session, item: Dict[str, Any]) -> Candidate:
    """Шаги 1–3 регистрации кандидата: профиль → ФСП → сертификат КИТ."""
    name = candidate_name(item)
    candidate = Candidate(email=item["email"])

    form: Dict[str, Any] = {"name": name, "consent": True, "visible_in_bank": True}
    form.update(item["profile"])
    errors = services.apply_candidate_profile(candidate, form)
    if errors:
        raise ValueError(f"Демо-анкета «{name}» не прошла валидацию: {'; '.join(errors)}")

    if item["fsp"]:
        services.connect_fsp(candidate)

    kit = item.get("kit")
    if kit:
        text = kit_certificate(name=name, specialty=kit["specialty"], score=kit["score"],
                               grade=kit["grade"], city=kit["city"], issued=kit["issued"],
                               number=kit["number"])
        parsed = services.parse_kit_upload(f"kit-{item['key']}.txt", text.encode("utf-8"))
        if parsed["error"]:
            raise ValueError(f"Сертификат КИТ «{name}» не распознан: {parsed['error']}")
        services.apply_kit(candidate, parsed, "text")

    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def create_employer(db: Session, item: Dict[str, Any]) -> Employer:
    """Шаги 1–2 регистрации работодателя: компания → анкета из 6 вопросов → тир."""
    employer = Employer(email=item["email"])

    errors = services.apply_employer_profile(employer, {
        "company": item["company"],
        "position": item["position"],
        "contact_name": item["contact_name"],
        "city": item["city"],
        "description": item["description"],
        "consent": True,
    })
    if errors:
        raise ValueError(f"Компания «{item['company']}» не прошла валидацию: {'; '.join(errors)}")

    # анкета принимает строки «true»/«false» — как значение радиокнопок формы
    answers = {field: ("true" if item["answers"].get(field) else "false")
               for field in logic.TIER_QUESTIONS}
    errors = services.apply_employer_survey(employer, answers)
    if errors:
        raise ValueError(f"Анкета «{item['company']}» не прошла валидацию: {'; '.join(errors)}")

    db.add(employer)
    db.commit()
    db.refresh(employer)
    return employer


def create_vacancy(db: Session, item: Dict[str, Any], employer: Employer) -> Vacancy:
    """Потребность работодателя — те же поля, что заполняет форма /employer/vacancies/new."""
    vacancy = Vacancy(
        employer_id=employer.id,
        company=employer.company,
        title=item["title"],
        specialization=item["specialization"],
        grade=item["grade"],
        grade_match=item["grade_match"],
        stack=list(item["stack"]),
        salary_min=item["salary_min"],
        salary_max=item["salary_max"],
        format=item["format"],
        city=item["city"],
        team_size=item["team_size"],
        description=item["description"],
        open=True,
        is_new=True,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)
    return vacancy


def create_invitation(db: Session, item: Dict[str, Any], employer: Employer,
                      candidate: Candidate, vacancy: Vacancy) -> Invitation:
    """Приглашение: вилка копируется из потребности, принятое — уже не «новое»."""
    invitation = Invitation(
        employer_id=employer.id,
        candidate_id=candidate.id,
        vacancy_id=vacancy.id,
        message=item["message"],
        salary_min=vacancy.salary_min,
        salary_max=vacancy.salary_max,
        status=item["status"],
        is_new=item["status"] != STATUS_ACCEPTED,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


# ---------------------------------------------------------------------------
# Публичный API сида
# ---------------------------------------------------------------------------

# Порядок очистки: сначала ссылки, потом владельцы — список читается и безопасен
# при переносе на СУБД с включёнными внешними ключами
CLEAR_ORDER = (Invitation, Application, Vacancy, Achievement, UserSession, Candidate, Employer)


def db_is_empty(db: Session) -> bool:
    """Пустая ли база: нет ни одной записи ни в одной таблице приложения."""
    return all(db.exec(select(model)).first() is None for model in CLEAR_ORDER)


def seed_demo(db: Session) -> Dict[str, Any]:
    """Создать демо-набор: 6 кандидатов, 3 работодателя, 4 потребности, 2 приглашения."""
    candidates: Dict[str, Candidate] = {}
    for item in DEMO_CANDIDATES:
        candidates[item["key"]] = create_candidate(db, item)

    employers: Dict[str, Employer] = {}
    for item in DEMO_EMPLOYERS:
        employers[item["key"]] = create_employer(db, item)

    vacancies: Dict[str, Vacancy] = {}
    for item in DEMO_VACANCIES:
        vacancies[item["key"]] = create_vacancy(db, item, employers[item["employer"]])

    invitations: List[Invitation] = [
        create_invitation(db, item, employers[item["employer"]],
                          candidates[item["candidate"]], vacancies[item["vacancy"]])
        for item in DEMO_INVITATIONS
    ]
    return {
        "candidates": candidates,
        "employers": employers,
        "vacancies": vacancies,
        "invitations": invitations,
    }


def ensure_demo_data(db: Session) -> bool:
    """Заполнить базу демо-данными, если она пустая. True — сид сработал.

    Вызывается один раз при старте приложения (п. 12.2 документации). Повторные запуски
    ничего не меняют: в базе уже есть записи, поэтому условие «пустая база» ложно.
    """
    if not db_is_empty(db):
        return False
    seed_demo(db)
    return True


def clear_db(db: Session) -> None:
    """Удалить все записи — используется флагом --force для пересборки стенда."""
    for model in CLEAR_ORDER:
        for row in db.exec(select(model)).all():
            db.delete(row)
    db.commit()


def reset_demo(db: Session) -> Dict[str, Any]:
    """Очистить базу и собрать демо-набор заново."""
    clear_db(db)
    return seed_demo(db)


def demo_accounts() -> List[Dict[str, str]]:
    """Демо-доступы для подсказки на /login: кто есть на стенде и что показывает."""
    accounts: List[Dict[str, str]] = []
    for item in DEMO_CANDIDATES:
        accounts.append({
            "role": "candidate",
            "email": item["email"],
            "name": candidate_name(item),
            "note": item["label"],
        })
    for item in DEMO_EMPLOYERS:
        tier = logic.employer_tier(item["answers"])
        accounts.append({
            "role": "employer",
            "email": item["email"],
            "name": item["company"],
            "note": f"{logic.tier_label(tier)} (tier {tier})",
        })
    return accounts


# ---------------------------------------------------------------------------
# Отчёт о стенде: печатается при запуске сида, удобен на защите проекта
# ---------------------------------------------------------------------------

def _kit_text(candidate: Candidate) -> str:
    if not candidate.kit_connected:
        return "не загружен"
    return f"{candidate.kit_score} баллов, {candidate.kit_certificate_number}"


def _fsp_text(candidate: Candidate) -> str:
    if not candidate.fsp_connected:
        return "не подключён"
    return f"{candidate.fsp_score} баллов, категория {candidate.fsp_category}"


def summary_lines(db: Session) -> List[str]:
    """Человекочитаемый отчёт о демо-стенде: анкеты, тиры, потребности, видимость."""
    candidates = db.exec(select(Candidate)).all()
    employers = db.exec(select(Employer)).all()
    vacancies = db.exec(select(Vacancy)).all()
    invitations = db.exec(select(Invitation)).all()
    lines: List[str] = []

    lines.append(f"Кандидаты ({len(candidates)}):")
    for candidate in candidates:
        verified = "" if candidate.is_verified else " — грейд не верифицирован"
        ambition = "амбициозный" if candidate.ambition else "без выраженных амбиций"
        lines.append(
            f"  • {candidate.name} ({candidate.email}): "
            f"{logic.specialization_title(candidate.specialization)}, "
            f"{logic.grade_title(candidate.grade)}{verified}; "
            f"КИТ {_kit_text(candidate)}; ФСП {_fsp_text(candidate)}; {ambition}; "
            f"уровень профиля «{logic.profile_level(candidate)}», "
            f"виден работодателю с тира {logic.candidate_min_tier(candidate)}"
        )

    lines.append(f"Работодатели ({len(employers)}):")
    for employer in employers:
        lines.append(
            f"  • {employer.company} ({employer.email}): {logic.tier_label(employer.tier)} "
            f"(tier {employer.tier}), здоровых ответов анкеты "
            f"{logic.tier_score(employer.survey_answers)} из {len(logic.TIER_QUESTIONS)}"
        )

    lines.append(f"Потребности ({len(vacancies)}):")
    for vacancy in vacancies:
        mode = logic.GRADE_MATCH_MODES.get(vacancy.grade_match,
                                           logic.GRADE_MATCH_MODES[logic.DEFAULT_GRADE_MATCH_MODE])
        lines.append(
            f"  • {vacancy.title} — {vacancy.company}: "
            f"{logic.specialization_title(vacancy.specialization)}, "
            f"{logic.grade_title(vacancy.grade)} ({mode}), "
            f"{logic.format_salary(vacancy.salary_min, vacancy.salary_max)}, "
            f"{logic.format_title(vacancy.format)}"
        )

    names = {candidate.id: candidate.name for candidate in candidates}
    companies = {employer.id: employer.company for employer in employers}
    lines.append(f"Приглашения ({len(invitations)}):")
    for invitation in invitations:
        lines.append(
            f"  • {companies.get(invitation.employer_id, 'работодатель')} → "
            f"{logic.mask_name(names.get(invitation.candidate_id, 'кандидат'))}: "
            f"{logic.status_title(invitation.status)}"
        )

    for tier in (3, 2, 1):
        visible = len(logic.visible_candidates(candidates, tier))
        lines.append(f"Матрица видимости, tier {tier} ({logic.tier_label(tier)}): "
                     f"{visible} анкет из {len(candidates)}")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    """Ручной запуск сида: python3.13 seed.py [--force]."""
    parser = argparse.ArgumentParser(
        description="Демо-данные стенда ФСП «спец. трек» (п. 12.2 документации)")
    parser.add_argument("--force", action="store_true",
                        help="очистить базу и пересобрать стенд заново")
    args = parser.parse_args(argv)

    init_db()
    with Session(engine) as db:
        if args.force:
            reset_demo(db)
            print("База очищена и заполнена демо-данными заново.")
        elif ensure_demo_data(db):
            print("База была пустой — заполнена демо-данными.")
        else:
            print("База не пустая — демо-данные не менялись "
                  "(пересобрать стенд: python3.13 seed.py --force).")
        print()
        for line in summary_lines(db):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

