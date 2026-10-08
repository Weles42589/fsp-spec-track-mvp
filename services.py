"""Прикладные операции над анкетами (раздел 7 ТЗ).

Здесь живёт то, что делают шаги регистрации и кабинет: валидация формы,
подключение ФСП, разбор сертификата КИТ, пересчёт производных полей,
анкета работодателя и расчёт тира. Маршруты остаются тонкими.
"""
from typing import Any, Dict, List

import fsp_mock
import kit_parser
import logic
from content import EMPLOYER_SURVEY
from models import Candidate, Employer, utcnow


def split_list(raw: Any) -> List[str]:
    """Список строк из формы: «a, b; c» или уже список."""
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").replace(";", ",").replace("\n", ",")
    return [part.strip() for part in text.split(",") if part.strip()]


def refresh_candidate(candidate: Candidate) -> Dict[str, Any]:
    """Пересчитать производные поля: грейд, баллы и категорию ФСП, специализацию.

    Грейд: КИТ → барометр амбиций → junior (раздел 6.2).
    Специализация определяется автоматически, только если не выбрана вручную.
    """
    grade = logic.resolve_grade(candidate.kit_grade, candidate.kit_certificate_number,
                                candidate.ambitions)
    candidate.grade_override = candidate.grade_override or grade["grade"]

    if candidate.fsp_connected:
        achievements = fsp_mock.get_achievements(candidate.email)["achievements"]
        score = fsp_mock.compute_fsp_score(achievements)
        candidate.fsp_score = score
        candidate.fsp_category = logic.category_from_score(score)

    if not candidate.specialization_manual:
        resolved = logic.resolve_specialization(candidate)
        if resolved["code"]:
            candidate.specialization = resolved["code"]

    candidate.updated_at = utcnow()
    return grade


def apply_candidate_profile(candidate: Candidate, form: Dict[str, Any]) -> List[str]:
    """Шаг 1 анкеты кандидата: профиль + барометр амбиций. Возвращает список ошибок."""
    errors: List[str] = []

    name = str(form.get("name", "")).strip()
    if not name:
        errors.append("Укажите имя и фамилию")

    team_role = str(form.get("team_role", "")).strip()
    if team_role not in logic.TEAM_ROLES:
        errors.append("Выберите роль в команде")

    work_format = str(form.get("work_format", "")).strip()
    if work_format not in logic.WORK_FORMATS:
        errors.append("Выберите комфортный формат работы")

    specialization = str(form.get("specialization", "")).strip()
    if specialization not in logic.SPECIALIZATIONS:
        specialization = ""

    fsp_role = str(form.get("fsp_role", "")).strip()
    if fsp_role not in logic.FSP_ROLES:
        fsp_role = ""

    ambitions = [item for item in logic.as_list(form.get("ambitions")) if item in logic.AMBITIONS]
    if not form.get("consent"):
        errors.append("Нужно согласие на обработку данных (152-ФЗ)")

    if errors:
        return errors

    candidate.name = name
    candidate.city = str(form.get("city", "")).strip()
    candidate.team_role = team_role
    candidate.work_format = work_format
    candidate.stack = split_list(form.get("stack"))
    candidate.fsp_role = fsp_role
    candidate.ambitions = ambitions
    candidate.consent = True
    candidate.visible_in_bank = bool(form.get("visible_in_bank", True))
    if specialization:
        candidate.specialization = specialization
        candidate.specialization_manual = True
    else:
        candidate.specialization_manual = False
        candidate.specialization = ""
    refresh_candidate(candidate)
    return []


def connect_fsp(candidate: Candidate) -> Dict[str, Any]:
    """Шаг 2: подключить историю ФСП из реестра (в MVP — мок, раздел 9.4)."""
    candidate.fsp_connected = True
    candidate.fsp_demo = True
    achievements = fsp_mock.get_achievements(candidate.email)["achievements"]
    grade = refresh_candidate(candidate)
    return {
        "achievements": achievements,
        "has_history": bool(achievements),
        "score": candidate.fsp_score,
        "category": candidate.fsp_category,
        "category_title": logic.category_title(candidate.fsp_category),
        "grade": grade["grade"],
    }


def disconnect_fsp(candidate: Candidate) -> None:
    candidate.fsp_connected = False
    candidate.fsp_demo = False
    candidate.fsp_score = 0
    candidate.fsp_category = "D"
    refresh_candidate(candidate)


KIT_COMPETITION_TITLE = "КИТ i.moscow"   # центр оценки компетенций (раздел 2 ТЗ)


def _empty_kit(raw: str, error: str) -> Dict[str, Any]:
    """Результат-заглушка, когда сертификат не распознан (раздел 8.4).

    Словарь той же формы, что и успешный разбор, чтобы маршруты не падали
    на отсутствующих ключах: пустые значения + текст ошибки.
    """
    return {
        "certificate_number": "",
        "competition": "",
        "place": None,
        "team": [],
        "grade": "",
        "kit_score": None,
        "date": "",
        "raw": raw,
        "specialization": "",
        "kit_specialization": "",
        "name": None,
        "place_text": logic.place_text(None),
        "error": error,
    }


def parse_kit_upload(filename: str, raw_bytes: bytes) -> Dict[str, Any]:
    """Разобрать загруженный сертификат и нормализовать поля для анкеты.

    PDF идёт через pdfplumber, остальные файлы читаются как текст. kit_parser
    при любой ошибке возвращает None (раздел 8.4), поэтому здесь всегда словарь
    с ключом «error»: пустая строка — разбор успешен, иначе текст для кандидата.
    """
    data = raw_bytes or b""
    if (filename or "").lower().endswith(".pdf"):
        raw_text = kit_parser.extract_pdf_text(data) or ""
    else:
        raw_text = data.decode("utf-8", errors="ignore")

    parsed = kit_parser.parse_kit_text(raw_text) if raw_text.strip() else None
    if not parsed:
        return _empty_kit(
            raw_text,
            "файл не похож на сертификат КИТ — заполните данные вручную в кабинете",
        )

    specialty = parsed.get("kit_specialization") or ""
    number = parsed.get("kit_number") or ""
    return {
        "certificate_number": number,
        "competition": f"{KIT_COMPETITION_TITLE} · {specialty}" if specialty else KIT_COMPETITION_TITLE,
        # место и команда в сертификате КИТ не печатаются (раздел 8.1) — остаются пустыми
        "place": None,
        "team": [],
        "grade": parsed.get("grade") or "",
        "kit_score": parsed.get("kit_score"),
        "date": parsed.get("kit_date") or "",
        "raw": raw_text,
        "specialization": parsed.get("specialization") or "",
        "kit_specialization": specialty,
        "name": parsed.get("name"),
        "place_text": logic.place_text(None),
        "error": "",
    }


def apply_kit(candidate: Candidate, parsed: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Шаг 3: записать разобранный сертификат. Грейд КИТ имеет высший приоритет."""
    candidate.kit_connected = True
    candidate.kit_source = source
    candidate.kit_certificate_number = parsed["certificate_number"]
    candidate.kit_competition = parsed["competition"]
    candidate.kit_place = parsed["place"]
    candidate.kit_team = parsed["team"]
    candidate.kit_grade = parsed["grade"]
    candidate.kit_score = parsed.get("kit_score")
    candidate.kit_date = parsed["date"]
    candidate.kit_raw = parsed["raw"]
    if not candidate.specialization_manual and parsed["specialization"]:
        candidate.specialization = parsed["specialization"]
    grade = refresh_candidate(candidate)
    parsed["resolved_grade"] = grade["grade"]
    parsed["grade_note"] = grade["note"]
    return parsed


def remove_kit(candidate: Candidate) -> None:
    candidate.kit_connected = False
    candidate.kit_source = ""
    candidate.kit_certificate_number = ""
    candidate.kit_competition = ""
    candidate.kit_place = None
    candidate.kit_team = []
    candidate.kit_grade = ""
    candidate.kit_score = None
    candidate.kit_date = ""
    candidate.kit_raw = ""
    refresh_candidate(candidate)


# ---------------------------------------------------------------------------
# Работодатель
# ---------------------------------------------------------------------------

def apply_employer_profile(employer: Employer, form: Dict[str, Any]) -> List[str]:
    """Шаг 1 анкеты работодателя: данные компании."""
    errors: List[str] = []
    company = str(form.get("company", "")).strip()
    if not company:
        errors.append("Укажите название компании")
    position = str(form.get("position", "")).strip()
    if not position:
        errors.append("Укажите должность контактного лица")
    if not form.get("consent"):
        errors.append("Нужно согласие на обработку данных (152-ФЗ)")
    if errors:
        return errors

    employer.company = company
    employer.position = position
    employer.contact_name = str(form.get("contact_name", "")).strip()
    employer.city = str(form.get("city", "")).strip()
    employer.description = str(form.get("description", "")).strip()
    employer.consent = True
    employer.updated_at = utcnow()
    return []


def apply_employer_survey(employer: Employer, form: Dict[str, Any]) -> List[str]:
    """Шаг 2: анкета из 6 вопросов → ответы и тир (разделы 7.1, 14).

    Все вопросы обязательны: вариант «не знаю» не предусмотрен, иначе тир
    невозможно посчитать.
    """
    errors: List[str] = []
    answers: Dict[str, bool] = {}
    for item in EMPLOYER_SURVEY:
        field = str(item["field"])
        raw = form.get(field)
        if raw not in ("true", "false"):
            errors.append(f"Ответьте на вопрос: {item['question']}")
            continue
        answers[field] = raw == "true"

    if errors:
        return errors

    employer.survey_answers = answers
    employer.tier = logic.employer_tier(answers)
    employer.updated_at = utcnow()
    return []
