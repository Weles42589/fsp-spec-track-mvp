"""Регрессия разделов 6.1 и 8.1: шапка сертификата КИТ не задаёт специализацию.

В любом сертификате есть строка «Прошел(а) тестирование по специальности …»
(пример раздела 8.1). Если искать ключевые слова по всему распознанному тексту,
слово «тестирование» срабатывает раньше «сервер»/«frontend» и уводит любую анкету
в QA. Специализация берётся только из поля специальности, которое достаёт
``kit_parser.parse_kit_text``, — за это отвечает ``logic.kit_specialty_text``.
"""
from __future__ import annotations

import pytest

import kit_parser
import logic
import seed
from models import Candidate

# Реальные специальности демо-стенда (seed.DEMO_CANDIDATES) + честный QA-случай
SPECIALTIES = [
    ("Специалист по серверной разработке (Python/Go)", "backend"),
    ("Frontend-разработчик (React/TypeScript)", "frontend"),
    ("Специалист по данным и машинному обучению", "ds"),
    ("Специалист технической поддержки (L1/L2/L3)", "support"),
    ("Тестирование программного обеспечения", "qa"),
]

# До правки эти две специальности из-за шапки сертификата становились QA
BROKEN_BEFORE_FIX = [
    ("Специалист по серверной разработке (Python/Go)", "backend"),
    ("Frontend-разработчик (React/TypeScript)", "frontend"),
]


def certified(specialty: str, email: str = "demo.kit@fsp.test") -> Candidate:
    """Кандидат с текстом сертификата КИТ формата раздела 8.1."""
    text = seed.kit_certificate("Демо Кандидат ФСП", specialty, 90, "middle",
                                "Москва", "15.12.2025 10:00:00",
                                "20251215-12-M-101845")
    return Candidate(name="Демо Кандидат ФСП", email=email, kit_connected=True,
                     kit_raw=text, kit_source="text")


@pytest.mark.parametrize("specialty,expected", SPECIALTIES)
def test_parser_reads_specialty_field(specialty, expected):
    """Парсер отдаёт отдельное поле специальности, а не весь текст документа."""
    parsed = kit_parser.parse_kit_text(certified(specialty).kit_raw) or {}
    assert parsed["kit_specialization"] == specialty
    assert parsed["specialization"] == expected
    assert parsed["grade"] == "middle" and parsed["kit_score"] == 90


def test_certificate_header_is_not_a_specialty():
    """Шапка «Прошел(а) тестирование …» в поле специальности не попадает."""
    parsed = kit_parser.parse_kit_text(kit_parser.DEMO_CERTIFICATE_TEXT) or {}
    assert parsed["kit_specialization"].startswith("Специалист технической поддержки")
    assert "тестирован" not in parsed["kit_specialization"].lower()
    assert parsed["specialization"] == "support"


@pytest.mark.parametrize("specialty,expected", SPECIALTIES)
def test_resolve_specialization_uses_kit_specialty_field(specialty, expected):
    candidate = certified(specialty)
    assert logic.kit_specialty_text(candidate) == specialty
    resolved = logic.resolve_specialization(candidate)
    assert resolved["code"] == expected
    assert resolved["source"] == "kit"


@pytest.mark.parametrize("specialty,expected", BROKEN_BEFORE_FIX)
def test_whole_certificate_text_would_force_qa(specialty, expected):
    """Причина правки: поиск по всему тексту всегда давал QA."""
    candidate = certified(specialty)
    assert logic.detect_specialization(candidate.kit_raw, [], [], "")[0] == "qa"
    assert logic.resolve_specialization(candidate)["code"] == expected


def test_manual_choice_beats_kit_specialty():
    """Ручной выбор в анкете побеждает автоопределение (раздел 6.1)."""
    candidate = certified("Специалист по серверной разработке (Python/Go)")
    candidate.specialization = "qa"
    candidate.specialization_manual = True
    resolved = logic.resolve_specialization(candidate)
    assert resolved["code"] == "qa" and resolved["source"] == "manual"


def test_without_kit_falls_back_to_fsp_then_stack():
    """Нет сертификата — специализация из дисциплин ФСП, потом из стека."""
    from_fsp = certified("Специалист по серверной разработке (Python/Go)",
                          email="anna.sokolova@fsp.demo")
    from_fsp.kit_connected = False
    from_fsp.kit_raw = ""
    from_fsp.fsp_connected = True
    assert logic.kit_specialty_text(from_fsp) == ""
    assert logic.resolve_specialization(from_fsp)["source"] == "fsp"

    from_stack = Candidate(name="Демо Кандидат ФСП", email="demo.stack@fsp.test",
                           stack=["Docker", "Kubernetes", "CI/CD"])
    resolved = logic.resolve_specialization(from_stack)
    assert resolved["code"] == "devops" and resolved["source"] == "stack"
