"""Аутентификация и разграничение доступа (раздел 12 ТЗ).

Паролей нет: вход по email + одноразовый 6-значный код. Код в MVP показывается
прямо на экране (заглушка вместо SMTP). Сессия — случайный токен в cookie
(httponly, samesite=lax) плюс запись в таблице `session`.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from fastapi import Request
from sqlmodel import Session as DBSession
from sqlmodel import select

from models import Candidate, Employer, UserSession, utcnow
from web import CODE_TTL_MINUTES, SESSION_TTL_DAYS, RedirectException

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def generate_code() -> str:
    """6-значный код подтверждения (раздел 12.1)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_token() -> str:
    return secrets.token_urlsafe(24)


def is_session_expired(created_at: Optional[str]) -> bool:
    created = _parse_ts(created_at) or _now()
    return _now() > created + timedelta(days=SESSION_TTL_DAYS)


class Principal:
    """Текущий пользователь: сессия + связанный кандидат или работодатель."""

    def __init__(self, session: UserSession, candidate: Optional[Candidate] = None,
                 employer: Optional[Employer] = None):
        self.session = session
        self.candidate = candidate
        self.employer = employer

    @property
    def role(self) -> str:
        return self.session.role

    @property
    def is_authenticated(self) -> bool:
        return bool(self.session and self.session.is_verified and not is_session_expired(self.session.created_at))

    @property
    def user(self) -> Any:
        return self.candidate or self.employer

    @property
    def email(self) -> str:
        return (self.user.email if self.user else self.session.email) or ""

    @property
    def title(self) -> str:
        if self.candidate:
            return self.candidate.name
        if self.employer:
            return self.employer.company
        return self.session.email

    @property
    def home_url(self) -> str:
        return "/employer" if self.role == "employer" else "/candidate"

    @property
    def register_url(self) -> str:
        return "/register/employer" if self.role == "employer" else "/register/candidate"

    @property
    def needs_registration(self) -> bool:
        return self.is_authenticated and self.user is None

    @property
    def is_candidate(self) -> bool:
        """Сессия кандидата: так роль читают навигация и входная страница."""
        return self.role == "candidate"

    @property
    def is_employer(self) -> bool:
        """Сессия работодателя."""
        return self.role == "employer"


def find_candidate_by_email(db: DBSession, email: str) -> Optional[Candidate]:
    email = (email or "").strip().lower()
    return db.exec(select(Candidate).where(Candidate.email == email)).first()


def find_employer_by_email(db: DBSession, email: str) -> Optional[Employer]:
    email = (email or "").strip().lower()
    return db.exec(select(Employer).where(Employer.email == email)).first()


def find_user(db: DBSession, email: str, role: str) -> Any:
    if role == "employer":
        return find_employer_by_email(db, email)
    return find_candidate_by_email(db, email)


def start_login(db: DBSession, email: str, role: str) -> UserSession:
    """POST /login: создать сессию с кодом. Запись без user_id — «незавершённая регистрация»."""
    email = (email or "").strip().lower()
    stale = db.exec(
        select(UserSession).where(
            UserSession.email == email,
            UserSession.role == role,
            UserSession.is_verified == False,  # noqa: E712 - сравнение для SQL-выражения
        )
    ).all()
    for row in stale:
        db.delete(row)

    user = find_user(db, email, role)
    session_row = UserSession(
        token=generate_token(),
        email=email,
        role=role,
        user_id=getattr(user, "id", None),
        code=generate_code(),
        code_expires_at=(_now() + timedelta(minutes=CODE_TTL_MINUTES)).strftime(TIME_FORMAT),
        is_verified=False,
        created_at=utcnow(),
    )
    db.add(session_row)
    db.commit()
    db.refresh(session_row)
    return session_row


def principal_for_token(db: DBSession, token: Optional[str]) -> Optional[Principal]:
    """Восстановить пользователя из cookie-токена. Протухшую сессию удаляем."""
    if not token:
        return None
    session_row = db.exec(select(UserSession).where(UserSession.token == token)).first()
    if not session_row:
        return None
    if is_session_expired(session_row.created_at):
        db.delete(session_row)
        db.commit()
        return None

    candidate = employer = None
    if session_row.user_id:
        if session_row.role == "employer":
            employer = db.get(Employer, session_row.user_id)
        else:
            candidate = db.get(Candidate, session_row.user_id)
    if session_row.user_id and not (candidate or employer):
        session_row.user_id = None
        db.add(session_row)
        db.commit()
    return Principal(session_row, candidate=candidate, employer=employer)


def verify_code(db: DBSession, principal: Optional[Principal], code: str) -> Tuple[bool, Optional[str]]:
    """POST /verify: проверить код, подтвердить email, привязать пользователя."""
    if principal is None:
        return False, "Сессия не найдена — запросите код заново"
    session_row = principal.session
    if not session_row.code:
        return False, "Код уже использован — запросите новый"
    if (code or "").strip() != session_row.code:
        return False, "Неверный код подтверждения"
    expires_at = _parse_ts(session_row.code_expires_at)
    if expires_at and _now() > expires_at:
        return False, "Срок действия кода истёк (15 минут) — запросите новый"

    session_row.is_verified = True
    session_row.code = None
    session_row.code_expires_at = None
    if not session_row.user_id:
        user = find_user(db, session_row.email, session_row.role)
        if user:
            session_row.user_id = user.id
    db.add(session_row)
    db.commit()
    db.refresh(session_row)
    return True, None


def bind_session_user(db: DBSession, principal: Principal, user: Any) -> None:
    """Привязать созданного при регистрации пользователя к текущей сессии."""
    principal.session.user_id = user.id
    db.add(principal.session)
    db.commit()
    db.refresh(principal.session)
    if isinstance(user, Candidate):
        principal.candidate = user
    elif isinstance(user, Employer):
        principal.employer = user


def logout(db: DBSession, principal: Optional[Principal]) -> None:
    if principal is not None and principal.session is not None:
        db.delete(principal.session)
        db.commit()


# ---------------------------------------------------------------------------
# Зависимости маршрутов: разграничение доступа (раздел 12.3)
# ---------------------------------------------------------------------------

def current_principal(request: Request) -> Optional[Principal]:
    return getattr(request.state, "me", None)


def require_principal(request: Request, role: str) -> Principal:
    """Нужна подтверждённая сессия указанной роли. Чужой кабинет → редирект на свой."""
    principal = current_principal(request)
    login_url = f"/login?role={role}"
    if principal is None or not principal.is_authenticated:
        raise RedirectException(login_url, "Сначала войдите по email и коду", "error")
    if principal.role != role:
        raise RedirectException(principal.home_url, "Раздел недоступен для вашей роли", "error")
    return principal


def require_new_user(request: Request, role: str) -> Principal:
    """Шаги регистрации: сессия подтверждена, но запись пользователя ещё не создана."""
    principal = require_principal(request, role)
    if principal.user is not None:
        raise RedirectException(principal.home_url, "Профиль уже заполнен", "success")
    return principal


def require_candidate(request: Request) -> Candidate:
    """Кабинет кандидата: регистрация должна быть начата."""
    principal = require_principal(request, "candidate")
    if principal.candidate is None:
        raise RedirectException("/register/candidate", "Заполните профиль кандидата", "error")
    return principal.candidate


def require_employer(request: Request) -> Employer:
    """Кабинет работодателя: анкета из 6 вопросов должна быть заполнена."""
    principal = require_principal(request, "employer")
    if principal.employer is None:
        raise RedirectException("/register/employer", "Заполните профиль компании", "error")
    if not principal.employer.survey_completed:
        raise RedirectException("/register/employer/survey", "Заполните анкету процессов", "error")
    return principal.employer
