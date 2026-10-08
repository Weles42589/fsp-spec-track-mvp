"""Мок реестра ФСП (раздел 9 ТЗ).

Реального API ФСП на хакатоне нет, поэтому модуль имитирует ответ внешней
системы: словарь «email участника → ФИО и список достижений».
В продакшене эти данные приходят из реестра ФСП (см. DOCUMENTATION.md).
"""
from typing import Any, Dict, List, Optional

# Пороги категорий (раздел 9.2): ≥150 → S, ≥100 → A, ≥60 → B, ≥30 → C, <30 → D
FSP_CATEGORY_THRESHOLDS: List[tuple] = [
    (150, "S"),
    (100, "A"),
    (60, "B"),
    (30, "C"),
    (0, "D"),
]

# Приоритет ролей: если роль в анкете не указана, берём старшую из достижений
ROLE_PRIORITY = ["капитан", "архитектор", "разработчик", "участник"]

# Тестовые данные (раздел 9.3): 8 кандидатов, разные сценарии
FSP_REGISTRY: Dict[str, Dict[str, Any]] = {
    # 1. Топ ФСП — сеньор, капитан, несколько первых мест
    "artem.petrov@fsp.demo": {
        "name": "Петров Артём Игоревич",
        "achievements": [
            {
                "discipline": "Программирование алгоритмическое",
                "competition": "Чемпионат России 2025",
                "place": 1,
                "role": "капитан",
                "points": 60,
                "date": "2025-04-18",
            },
            {
                "discipline": "Программирование алгоритмическое",
                "competition": "Кубок Федерации 2025",
                "place": 1,
                "role": "капитан",
                "points": 55,
                "date": "2025-02-09",
            },
            {
                "discipline": "Программирование продуктовое",
                "competition": "Цифровой атом 2025",
                "place": 2,
                "role": "капитан",
                "points": 45,
                "date": "2025-06-27",
            },
        ],
    },
    # 2. Крепкий мидл — B-категория, три призовых места
    "anna.sokolova@fsp.demo": {
        "name": "Соколова Анна Дмитриевна",
        "achievements": [
            {
                "discipline": "Программирование продуктовое",
                "competition": "Foncode 2026",
                "place": 2,
                "role": "разработчик",
                "points": 30,
                "date": "2026-01-30",
            },
            {
                "discipline": "Программирование алгоритмическое",
                "competition": "Кубок Федерации 2025",
                "place": 3,
                "role": "разработчик",
                "points": 25,
                "date": "2025-02-10",
            },
            {
                "discipline": "Программирование продуктовое",
                "competition": "Цифровой атом 2025",
                "place": 4,
                "role": "разработчик",
                "points": 20,
                "date": "2025-06-28",
            },
        ],
    },
    # 3. Новичок с амбициями — junior, капитан команды, бронза
    "mark.ivanov@fsp.demo": {
        "name": "Иванов Марк Сергеевич",
        "achievements": [
            {
                "discipline": "Программирование алгоритмическое",
                "competition": "КиберТатами 2026",
                "place": 3,
                "role": "капитан",
                "points": 20,
                "date": "2026-03-14",
            },
            {
                "discipline": "Программирование продуктовое",
                "competition": "Foncode 2026",
                "place": 6,
                "role": "капитан",
                "points": 15,
                "date": "2026-01-31",
            },
        ],
    },
    # 4. Новичок без достижений — только участие
    "olga.smirnova@fsp.demo": {
        "name": "Смирнова Ольга Павловна",
        "achievements": [
            {
                "discipline": "Программирование продуктовое",
                "competition": "КиберТатами 2026",
                "place": 18,
                "role": "участник",
                "points": 10,
                "date": "2026-03-15",
            },
        ],
    },
    # 5. DevOps-архитектор, категория A
    "sergey.orlov@fsp.demo": {
        "name": "Орлов Сергей Николаевич",
        "achievements": [
            {
                "discipline": "Программирование робототехники",
                "competition": "Чемпионат России 2025",
                "place": 2,
                "role": "архитектор",
                "points": 40,
                "date": "2025-04-19",
            },
            {
                "discipline": "Программирование беспилотных авиационных систем",
                "competition": "Цифровой атом 2025",
                "place": 2,
                "role": "архитектор",
                "points": 35,
                "date": "2025-06-28",
            },
            {
                "discipline": "Программирование робототехники",
                "competition": "Foncode 2026",
                "place": 3,
                "role": "разработчик",
                "points": 35,
                "date": "2026-01-31",
            },
        ],
    },
    # 6. Информационная безопасность, senior, категория B
    "maria.lebedeva@fsp.demo": {
        "name": "Лебедева Мария Андреевна",
        "achievements": [
            {
                "discipline": "Программирование систем информационной безопасности",
                "competition": "Чемпионат России 2025",
                "place": 2,
                "role": "разработчик",
                "points": 35,
                "date": "2025-04-20",
            },
            {
                "discipline": "Программирование систем информационной безопасности",
                "competition": "КиберТатами 2026",
                "place": 3,
                "role": "разработчик",
                "points": 30,
                "date": "2026-03-15",
            },
        ],
    },
    # 7. Робототехника / embedded, капитан
    "nikita.zaitsev@fsp.demo": {
        "name": "Зайцев Никита Олегович",
        "achievements": [
            {
                "discipline": "Программирование робототехники",
                "competition": "Кубок Федерации 2025",
                "place": 1,
                "role": "капитан",
                "points": 45,
                "date": "2025-02-10",
            },
            {
                "discipline": "Программирование беспилотных авиационных систем",
                "competition": "Foncode 2026",
                "place": 4,
                "role": "разработчик",
                "points": 30,
                "date": "2026-02-01",
            },
        ],
    },
    # 8. Продуктовая разработка, junior, одно выступление
    "sofia.morozova@fsp.demo": {
        "name": "Морозова София Ильинична",
        "achievements": [
            {
                "discipline": "Программирование продуктовое",
                "competition": "Кубок Федерации 2025",
                "place": 9,
                "role": "участник",
                "points": 25,
                "date": "2025-02-11",
            },
        ],
    },
}

EMPTY_RESULT: Dict[str, Any] = {"name": None, "achievements": []}


def get_achievements(email: Optional[str]) -> Dict[str, Any]:
    """Достижения ФСП по email.

    Если email в реестре нет — возвращаем пустой объект: кандидат без истории ФСП
    должен обрабатываться корректно (обязательный сценарий раздела 9.2).
    """
    if not email:
        return dict(EMPTY_RESULT)
    record = FSP_REGISTRY.get(email.strip().lower())
    if not record:
        return dict(EMPTY_RESULT)
    return {
        "name": record.get("name"),
        "achievements": [dict(item) for item in record.get("achievements", [])],
    }


def has_history(email: Optional[str]) -> bool:
    """Есть ли у участника история в реестре ФСП."""
    return bool(get_achievements(email)["achievements"])


def compute_fsp_score(achievements: Optional[List[Dict[str, Any]]]) -> int:
    """Сумма баллов за достижения (раздел 9.2)."""
    if not achievements:
        return 0
    total = 0
    for item in achievements:
        try:
            total += int(item.get("points", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def compute_fsp_category(score: int) -> str:
    """Категория по порогам: ≥150 S, ≥100 A, ≥60 B, ≥30 C, иначе D (раздел 9.2)."""
    value = int(score or 0)
    for threshold, category in FSP_CATEGORY_THRESHOLDS:
        if value >= threshold:
            return category
    return "D"


def best_role(achievements: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Старшая роль из достижений: капитан > архитектор > разработчик > участник."""
    roles = {(item.get("role") or "").strip().lower() for item in (achievements or [])}
    for role in ROLE_PRIORITY:
        if role in roles:
            return role
    return None


def disciplines(achievements: Optional[List[Dict[str, Any]]]) -> List[str]:
    """Список дисциплин — источник специализации №2 (раздел 6.1)."""
    return [item.get("discipline", "") for item in (achievements or []) if item.get("discipline")]
