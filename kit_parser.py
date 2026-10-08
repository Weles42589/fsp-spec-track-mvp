"""Парсер PDF-сертификата КИТ i.moscow (раздел 8 ТЗ).

Извлекает грейд, баллы, специальность, номер и дату сертификата.
Библиотека — pdfplumber. Главное правило раздела 8.4: при любой ошибке
возвращаем None и предлагаем кандидату ручной ввод, приложение не падает.
"""
import io
import re
from typing import Any, Dict, List, Optional

from logic import detect_kit_specialization, normalize_grade

SCORE_RE = re.compile(r"Результат\s+(\d+)\s*балл", re.IGNORECASE)
GRADE_RE = re.compile(r"Уровень\s+Грейда\s+([A-Za-zА-Яа-яЁё]+)", re.IGNORECASE)
NUMBER_RE = re.compile(r"(\d{8}-\d+-[JMSjms]-\d+)")
DATE_RE = re.compile(r"Выдан\s+(\d{2}\.\d{2}\.\d{4})")
SPECIALTY_RE = re.compile(r"по\s+специальности\s+(.+)", re.IGNORECASE)

# Буква грейда внутри номера сертификата YYYYMMDD-NN-X-NNNNNN (раздел 8.2)
NUMBER_GRADE_LETTERS = {"J": "junior", "M": "middle", "S": "senior"}

# Пример реального сертификата из раздела 8.1 — используется для демо-загрузки и тестов
DEMO_CERTIFICATE_TEXT = """КИТ
Бурцева Вероника Львовна
Прошел(а) тестирование по специальности Специалист технической поддержки (L1/L2/L3)
Результат 84 баллов из 100
Уровень Грейда Senior
Город Москва
Выдан 19.01.2026 00:51:36
20260119-37-S-102905
"""


def _grade_from_number(number: Optional[str]) -> Optional[str]:
    """Резервный способ определить грейд — по букве J/M/S в номере сертификата."""
    if not number:
        return None
    match = re.search(r"\d{8}-\d+-([JMSjms])-\d+", number)
    if not match:
        return None
    return NUMBER_GRADE_LETTERS.get(match.group(1).upper())


def _clamp_score(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, value))


def _guess_name(lines: List[str]) -> Optional[str]:
    """ФИО в сертификате идёт сразу после заголовка «КИТ»."""
    cleaned = [line.strip() for line in lines if line.strip()]
    for index, line in enumerate(cleaned):
        if line.upper() == "КИТ" and index + 1 < len(cleaned):
            candidate = cleaned[index + 1]
            words = candidate.split()
            if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
                return candidate
    return None


def parse_kit_text(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Разбор уже извлечённого текста сертификата.

    Возвращает словарь с полями (нераспознанные — None) либо None,
    если не нашлось вообще ничего (раздел 8.4).
    """
    if not text or not text.strip():
        return None

    lines = text.splitlines()
    score_match = SCORE_RE.search(text)
    grade_match = GRADE_RE.search(text)
    number_match = NUMBER_RE.search(text)
    date_match = DATE_RE.search(text)
    specialty_match = SPECIALTY_RE.search(text)

    number = number_match.group(1) if number_match else None
    specialty_text = specialty_match.group(1).strip() if specialty_match else None
    if specialty_text:
        # обрезаем хвост типа «(L1/L2/L3) 20260119-37-S-102905», если он попал в захват
        specialty_text = re.split(r"\s{2,}|\n", specialty_text)[0].strip()

    grade = normalize_grade(grade_match.group(1) if grade_match else None)
    if not grade:
        grade = _grade_from_number(number)

    result = {
        "kit_score": _clamp_score(score_match.group(1) if score_match else None),
        "grade": grade,
        "kit_number": number,
        "kit_date": date_match.group(1) if date_match else None,
        "kit_specialization": specialty_text,
        "specialization": detect_kit_specialization(specialty_text),
        "name": _guess_name(lines),
    }

    found = [
        value
        for key, value in result.items()
        if value is not None and key != "name"
    ]
    if not found:
        return None
    return result


def extract_pdf_text(data: bytes) -> Optional[str]:
    """Извлечение текста из PDF через pdfplumber. Ошибка → None."""
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - библиотека есть в requirements.txt
        return None
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception:
        return None
    text = "\n".join(pages).strip()
    return text or None


def parse_kit_pdf(data: Optional[bytes]) -> Optional[Dict[str, Any]]:
    """Полный цикл: PDF → текст → поля сертификата. Любая ошибка → None (раздел 8.4)."""
    if not data:
        return None
    text = extract_pdf_text(data)
    if not text:
        return None
    return parse_kit_text(text)
