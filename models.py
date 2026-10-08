"""Модели данных платформы (раздел 5 ТЗ).

Все модели — SQLModel (SQLAlchemy + Pydantic), хранение — SQLite.
Помимо полей из ТЗ в моделях есть несколько служебных полей
(помечены комментарием «служебное»): они нужны для пошаговой регистрации,
согласия на обработку данных (152-ФЗ) и отметок времени.

Статусы приглашений и откликов (раздел 6.8): sent → viewed → accepted/rejected.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

STATUS_SENT = "sent"
STATUS_VIEWED = "viewed"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"

STATUS_TITLES = {
    STATUS_SENT: "отправлено",
    STATUS_VIEWED: "просмотрено",
    STATUS_ACCEPTED: "принято",
    STATUS_REJECTED: "отклонено",
}

# Значение «грейд из сертификата КИТ» — выше senior (раздел 6.2)
GRADE_FROM_KIT = "kit"


def utcnow() -> str:
    """Единый формат времени — строка UTC в ISO-8601."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Candidate(SQLModel, table=True):
    """Кандидат (раздел 5.1 ТЗ)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    email: str = Field(index=True, unique=True)
    city: str = ""

    # специализация: КИТ → ФСП → стек → ручной выбор (раздел 6.1)
    specialization: str = ""
    specialization_manual: bool = False  # служебное: выбрано вручную, автоопределение не трогает

    # амбициозность: ≥2 флагов (раздел 6.3)
    team_role: str = ""
    work_format: str = ""
    stack: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    fsp_role: str = ""
    ambitions: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    grade_override: str = ""  # служебное: ручной грейд, если КИТ не загружен

    # история ФСП (раздел 9)
    fsp_connected: bool = False
    fsp_demo: bool = False        # служебное: данные заполнены мок-реестром
    fsp_score: int = 0
    fsp_category: str = "D"

    # сертификат КИТ (раздел 6.2)
    kit_connected: bool = False
    kit_certificate_number: str = ""
    kit_competition: str = ""
    kit_place: Optional[int] = None
    kit_team: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    kit_grade: str = ""
    kit_score: Optional[int] = None   # баллы из сертификата (раздел 8.2)
    kit_date: str = ""
    kit_raw: str = ""             # служебное: распознанный текст сертификата
    kit_source: str = ""          # служебное: pdf / text

    # служебные поля
    consent: bool = False         # согласие на обработку данных (152-ФЗ)
    visible_in_bank: bool = True  # видимость в банке (раздел 8)
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)

    # --- производные значения: не хранятся, считаются по правилам раздела 6 ---

    @property
    def grade(self) -> str:
        """Итоговый грейд: КИТ → ручной выбор → барометр → junior (раздел 6.2)."""
        from logic import resolve_grade

        return resolve_grade(self.kit_grade, self.kit_certificate_number,
                             self.ambitions, self.grade_override)["grade"]

    @property
    def ambition(self) -> bool:
        """Барометр амбиций: сумма флагов ≥ 2 (раздел 6.3)."""
        from logic import compute_ambition

        return compute_ambition(self.team_role, self.work_format, self.stack, self.fsp_role)

    @property
    def is_verified(self) -> bool:
        """Грейд подтверждён внешним провайдером КИТ (разделы 6.2, 8.2)."""
        return bool(self.kit_connected and (self.kit_grade or self.kit_certificate_number))

    @property
    def is_public(self) -> bool:
        """Синоним visible_in_bank: так правило читают функции видимости (раздел 8.4)."""
        return bool(self.visible_in_bank)


class Employer(SQLModel, table=True):
    """Работодатель (раздел 5.2 ТЗ) + анкета из 6 вопросов (разделы 7.1, 14)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    company: str = Field(index=True)
    email: str = Field(index=True, unique=True)
    contact_name: str = ""
    position: str = ""
    city: str = ""
    description: str = ""

    # ответы анкеты: 6 булевых полей (вариант А = True); tier считается из них
    survey_answers: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    tier: int = 1

    # служебные поля
    consent: bool = False
    last_visit_at: str = ""       # для счётчика «новых откликов» (раздел 13.6)
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)

    @property
    def survey_completed(self) -> bool:
        """Анкета заполнена, если даны ответы на все 6 вопросов."""
        return len(self.survey_answers or {}) >= 6


class Vacancy(SQLModel, table=True):
    """Потребность работодателя (раздел 5.3 ТЗ).

    Может быть открытой вакансией (is_new показывает «новую» для кандидата)
    или внутренней потребностью для подбора (open=False — не публикуется).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    employer_id: int = Field(index=True, foreign_key="employer.id")
    company: str = ""             # служебное: копия названия компании для карточек
    title: str = ""
    specialization: str = ""
    grade: str = ""
    grade_match: str = "any"      # any / exact / plus_minus (раздел 10.3)
    stack: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    salary_min: int = 0
    salary_max: int = 0
    format: str = ""              # remote / hybrid / office
    city: str = ""
    team_size: str = ""
    description: str = ""
    open: bool = True             # служебное: публикуется ли в банке потребностей
    is_new: bool = True           # служебное: «новая» для кандидата (раздел 13.3)
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)


class Achievement(SQLModel, table=True):
    """Достижение ФСП (раздел 5.4 ТЗ). Заполняется из мока реестра ФСП."""

    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(index=True, foreign_key="candidate.id")
    discipline: str = ""
    competition: str = ""
    place: Optional[int] = None
    role: str = ""                # капитан / архитектор / разработчик / участник
    points: int = 0
    date: Optional[str] = None


class Invitation(SQLModel, table=True):
    """Приглашение работодателя кандидату (раздел 5.5 ТЗ) — основная механика."""

    id: Optional[int] = Field(default=None, primary_key=True)
    employer_id: int = Field(index=True, foreign_key="employer.id")
    candidate_id: int = Field(index=True, foreign_key="candidate.id")
    vacancy_id: Optional[int] = Field(default=None, foreign_key="vacancy.id")
    message: str = ""
    salary_min: int = 0
    salary_max: int = 0
    status: str = STATUS_SENT
    is_new: bool = True           # служебное: не просмотрено кандидатом
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)


class Application(SQLModel, table=True):
    """Отклик кандидата на потребность (раздел 5.6 ТЗ)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(index=True, foreign_key="candidate.id")
    employer_id: int = Field(index=True, foreign_key="employer.id")
    vacancy_id: Optional[int] = Field(default=None, foreign_key="vacancy.id")
    message: str = ""
    status: str = STATUS_SENT
    is_new: bool = True           # служебное: не просмотрено работодателем
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)


class UserSession(SQLModel, table=True):
    """Сессия пользователя (раздел 12.4 ТЗ).

    Имя таблицы — `session`. Класс назван UserSession, чтобы не конфликтовать
    с `sqlmodel.Session` (подключение к БД).

    До подтверждения кода запись хранит «незавершённую регистрацию»:
    user_id пустой, есть email, role и временный code.
    """

    __tablename__ = "session"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True)
    user_id: Optional[int] = None
    email: str = ""               # служебное: email незавершённой регистрации
    role: str = "candidate"       # candidate / employer
    code: Optional[str] = None
    code_expires_at: Optional[str] = None
    is_verified: bool = False     # служебное: email подтверждён кодом
    created_at: str = Field(default_factory=utcnow)
