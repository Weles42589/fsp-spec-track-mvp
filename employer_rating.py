"""Мок-рейтинг компании (раздел 14.1 ТЗ).

В продакшене сигналы (госзакупки, реестр отечественного ПО, отзывы сотрудников,
соотношение зарплат топ-менеджмента и инженеров) парсятся из открытых источников.
В MVP значения детерминированные: для демо-компаний заданы явно, для остальных —
воспроизводимо вычисляются из хеша названия. Рейтинг видит только кандидат.
"""
import hashlib
from typing import Any, Dict, List, Optional

from logic import tier_label

# Явные мок-значения для демо-компаний (раздел 14.1): четыре компании из ТЗ
# и три работодателя демонстрационного стенда (seed.py)
RATING_MOCK: Dict[str, Dict[str, Any]] = {
    "ТехКорп": {"tenders": 18, "in_registry": True, "reviews": 4.6, "salary_ratio": 3.2},
    "Вектор Софт": {"tenders": 7, "in_registry": True, "reviews": 4.1, "salary_ratio": 4.4},
    "ПромТех Групп": {"tenders": 12, "in_registry": False, "reviews": 3.9, "salary_ratio": 5.1},
    "ОлдЛайн": {"tenders": 1, "in_registry": False, "reviews": 2.8, "salary_ratio": 8.6},
    "Прогресс-Софт": {"tenders": 16, "in_registry": True, "reviews": 4.7, "salary_ratio": 3.4},
    "СтабилИТ": {"tenders": 9, "in_registry": True, "reviews": 4.0, "salary_ratio": 4.6},
    "Быстрая разработка": {"tenders": 3, "in_registry": False, "reviews": 3.4, "salary_ratio": 5.9},
}


def company_signals(company: str) -> Dict[str, Any]:
    """Сигналы о компании: тендеры, реестр ПО, отзывы, соотношение зарплат."""
    name = (company or "").strip()
    if name in RATING_MOCK:
        return dict(RATING_MOCK[name])

    digest = hashlib.md5(name.encode("utf-8")).hexdigest()
    seed = int(digest, 16)
    return {
        "tenders": seed % 25,
        "in_registry": seed % 2 == 0,
        "reviews": round(3.0 + (seed >> 3) % 20 / 10.0, 1),
        "salary_ratio": round(2.0 + (seed >> 7) % 60 / 10.0, 1),
    }


def company_rating(company: str, tier: Optional[int] = None) -> Dict[str, Any]:
    """Итоговый рейтинг 0–10 + объяснение. Детерминированно, без внешних запросов.

    `tier` — уровень организации процессов работодателя. Если он неизвестен
    (карточку видит кандидат до приглашения), этот сигнал в рейтинг не добавляется:
    цифра тира не раскрывается никому, кроме самого работодателя (раздел 6.4).
    """
    signals = company_signals(company)
    score = 3.0
    explanation: List[str] = []

    reviews = float(signals["reviews"])
    score += (reviews - 3.0) * 1.5
    explanation.append(f"средняя оценка сотрудников: {reviews:.1f} из 5")

    if signals["in_registry"]:
        score += 1.0
        explanation.append("компания в реестре отечественного ПО")
    else:
        explanation.append("в реестре отечественного ПО не найдена")

    tenders = int(signals["tenders"])
    score += min(tenders, 20) / 20.0 * 1.5
    explanation.append(f"публичных закупок и тендеров за год: {tenders}")

    ratio = float(signals["salary_ratio"])
    if ratio > 5.0:
        score -= (ratio - 5.0) * 0.6
        explanation.append(f"разрыв зарплат топ-менеджмента и инженеров: ×{ratio:.1f}")

    if tier is None:
        explanation.append("анкета процессов работодателя в рейтинге не учитывается")
    else:
        score += (int(tier) - 2) * 0.8
        explanation.append(f"анкета процессов: {tier_label(tier)}")

    score = round(max(0.0, min(10.0, score)), 1)
    if score >= 7.5:
        label = "высокий"
    elif score >= 5.0:
        label = "средний"
    else:
        label = "низкий"

    return {"score": score, "label": label, "signals": signals, "explanation": explanation}
