"""Веб-обвязка: шаблоны, flash-сообщения, редиректы, общие константы (разделы 11, 12 ТЗ)."""
import base64
import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import content
import logic
import seed
from models import STATUS_TITLES

BASE_DIR = Path(__file__).resolve().parent

SESSION_COOKIE = "fsp_session"
FLASH_COOKIE = "fsp_flash"
SESSION_TTL_DAYS = 7          # раздел 12.2: TTL сессии — 7 дней
CODE_TTL_MINUTES = 15         # раздел 12.1: TTL кода подтверждения — 15 минут

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Глобальные функции и справочники для шаблонов — чтобы не прокидывать их в каждый контекст
templates.env.globals.update({
    "format_salary": logic.format_salary,
    "specialization_title": logic.specialization_title,
    "grade_title": logic.grade_title,
    "category_title": logic.category_title,
    "tier_label": logic.tier_label,
    # алиас для матрицы видимости: маршруты работодателя кладут в контекст
    # tier_label строкой, и она перекрывает глобальную функцию в шаблоне
    "tier_title": logic.tier_label,
    "profile_level": logic.profile_level,
    "status_title": lambda code: STATUS_TITLES.get(code, code),
    # форматирование и сноски для карточек (разделы 8, 10, 11)
    "format_title": logic.format_title,
    "money": logic.money,
    "percent": logic.percent,
    "place_text": logic.place_text,
    "salary_note": logic.salary_note,
    "mask_name": logic.mask_name,
    "ambitions_labels": logic.ambitions_labels,
    "grade_match_note": logic.grade_match_note,
    "stack_note": logic.stack_note,
    "restricted_reason": logic.restricted_reason,
    "SPECIALIZATIONS": logic.SPECIALIZATIONS,
    "GRADES": logic.GRADES,
    "TEAM_ROLES": logic.TEAM_ROLES,
    "FSP_ROLES": logic.FSP_ROLES,
    "WORK_FORMATS": logic.WORK_FORMATS,
    "VACANCY_FORMATS": logic.VACANCY_FORMATS,
    "AMBITIONS": logic.AMBITIONS,
    "GRADE_MATCH_MODES": logic.GRADE_MATCH_MODES,
    "TIER_FIELDS": logic.TIER_FIELDS,
    "TIER_DESCRIPTIONS": logic.TIER_DESCRIPTIONS,
    "FSP_CATEGORY_TITLES": logic.FSP_CATEGORY_TITLES,
    "MATCH_WEIGHTS": logic.MATCH_WEIGHTS,
    "CONTACT_REVEAL_NOTE": logic.CONTACT_REVEAL_NOTE,
    "EMPLOYER_SURVEY": content.EMPLOYER_SURVEY,
    "CANDIDATE_BAROMETER": content.CANDIDATE_BAROMETER,
    # демо-доступы стенда: подсказка на /login (заполняется сидом, раздел 12.2)
    "demo_accounts": seed.demo_accounts,
    "FSP_DEMO_NOTE": content.FSP_DEMO_NOTE,
    "AUTH_DEMO_NOTE": content.AUTH_DEMO_NOTE,
    "RATING_DEMO_NOTE": content.RATING_DEMO_NOTE,
    "CANDIDATE_STEPS": content.CANDIDATE_STEPS,
    "EMPLOYER_STEPS": content.EMPLOYER_STEPS,
})


class RedirectException(Exception):
    """Редирект из зависимости или обработчика: перехватывается общим exception handler."""

    def __init__(self, url: str, message: Optional[str] = None, kind: str = "error"):
        super().__init__(message or url)
        self.url = url
        self.message = message
        self.kind = kind


def _encode_flash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_flash(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("message"):
        return {"message": str(payload["message"]), "kind": payload.get("kind", "success")}
    return None


def flash(response: RedirectResponse, message: str, kind: str = "success"):
    """Одноразовое сообщение: кладём в cookie, показываем на следующей странице."""
    response.set_cookie(
        FLASH_COOKIE,
        _encode_flash({"message": message, "kind": kind}),
        max_age=120,
        httponly=True,
        samesite="lax",
    )
    return response


def redirect(url: str, message: Optional[str] = None, kind: str = "success") -> RedirectResponse:
    """303 See Other — чтобы браузер после POST делал GET."""
    response = RedirectResponse(url, status_code=303)
    if message:
        flash(response, message, kind)
    return response


def render(request: Request, name: str, title: str, **context: Any):
    """Рендер шаблона: автоматически подмешивает flash, текущего пользователя и заголовок."""
    payload = {
        "request": request,
        "title": title,
        "flash": _decode_flash(request.cookies.get(FLASH_COOKIE)),
        "me": getattr(request.state, "me", None),
        # Необязательные переменные форм: шаблоны проверяют их через {% if %},
        # значение по умолчанию убирает UndefinedError при рендере GET-страниц.
        "errors": [],
        "error": None,
    }
    payload.update(context)
    response = templates.TemplateResponse(request=request, name=name, context=payload)
    if request.cookies.get(FLASH_COOKIE):
        response.delete_cookie(FLASH_COOKIE)
    return response
