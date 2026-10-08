"""Детерминированная бизнес-логика платформы (раздел 6 ТЗ).

Никакого ML, эмбеддингов и внешних сервисов: только словари, регулярные
выражения, сравнения и сортировки. Номер пункта ТЗ указан у каждой функции.
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

SPECIALIZATIONS: Dict[str, str] = {
    "backend": "Backend-разработка",
    "frontend": "Frontend-разработка",
    "ds": "Анализ данных / ML",
    "devops": "DevOps",
    "qa": "Тестирование / QA",
    "support": "Техническая поддержка",
    "security": "Информационная безопасность",
    "mobile": "Мобильная разработка",
    "embedded": "Робототехника / Embedded",
    "other": "Другое",
}

GRADES: Dict[str, str] = {"junior": "Junior", "middle": "Middle", "senior": "Senior"}

TEAM_ROLES: List[str] = ["капитан", "архитектор", "разработчик", "исполнитель"]

WORK_FORMAT_INFLUENCE = "обсуждаем и влияю"
WORK_FORMAT_EXECUTE = "сказали — делаю"

WORK_FORMATS: Dict[str, str] = {
    WORK_FORMAT_INFLUENCE: "Обсуждаем всё за 2 часа переговоров, я влияю на решения",
    WORK_FORMAT_EXECUTE: "Сказали — делаю, чёткие задачи",
}

FSP_ROLES: List[str] = ["капитан", "архитектор", "разработчик", "участник"]

VACANCY_FORMATS: Dict[str, str] = {
    "remote": "удалённо",
    "office": "офис",
    "hybrid": "гибрид",
}

FSP_CATEGORIES: List[str] = ["S", "A", "B", "C", "D"]

# Слова для категории ФСП (раздел 9.2): видны только кандидату
FSP_CATEGORY_TITLES: Dict[str, str] = {
    "S": "топ-уровень: стабильные победы в чемпионатах",
    "A": "высокий уровень: регулярные призовые места",
    "B": "уверенный уровень: есть призовые выступления",
    "C": "начинающий уровень: отдельные участия",
    "D": "история ФСП не найдена",
}

# Флаги барометра амбиций (раздел 6.3): код → формулировка для кандидата
AMBITIONS: Dict[str, str] = {
    "captain": "роль в команде — капитан или архитектор",
    "influence": "формат работы — «обсуждаем и влияю»",
    "wide_stack": "широкий стек (3 и более направлений)",
    "fsp_captain": "роль в команде ФСП — капитан или архитектор",
}

# Сколько флагов дают вердикт «амбициозный профиль» (порог раздела 6.3)
AMBITION_THRESHOLD = 2

# Названия тиров — то, что видит кандидат (раздел 6.4). Цифра работодателю не показывается.
TIER_LABELS: Dict[int, str] = {
    3: "развитые процессы",
    2: "базовые процессы",
    1: "начальные процессы",
}

CAPTAIN_ROLES = ("капитан", "архитектор")

# Поля анкеты работодателя (разделы 5.2 и 7.1)
TIER_QUESTIONS: List[str] = [
    "q1_lead_time",
    "q2_support",
    "q3_remote",
    "q4_mistake",
    "q5_outsource",
    "q6_benefits",
]

GRADE_ALIASES: Dict[str, str] = {
    "junior": "junior", "j": "junior", "джуниор": "junior", "начинающий": "junior",
    "middle": "middle", "m": "middle", "мидл": "middle", "средний": "middle",
    "senior": "senior", "s": "senior", "сеньор": "senior", "старший": "senior",
    "lead": "senior", "ведущий": "senior",
}

# Маппинг стека на специализацию (раздел 6.1). Порядок задаёт приоритет при равенстве.
STACK_SPEC_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("backend", ["python", "java", "go", "c#", "php", "backend", "fastapi", "django", "spring"]),
    ("frontend", ["react", "vue", "angular", "javascript", "typescript", "html", "css", "frontend"]),
    ("ds", ["pytorch", "tensorflow", "sklearn", "pandas", "ml", "ds", "data"]),
    ("qa", ["qa", "selenium", "pytest", "тестирован"]),
    ("support", ["support", "техподдержк", "helpdesk"]),
    ("devops", ["devops", "docker", "kubernetes", "ci/cd"]),
    ("security", ["security", "безопасн", "pentest"]),
]

# Маппинг дисциплин ФСП на специализацию (раздел 6.1)
FSP_DISCIPLINE_KEYWORDS: List[Tuple[str, str]] = [
    ("алгоритм", "backend"),
    ("безопасн", "security"),
    ("данн", "ds"),
    ("ml", "ds"),
    ("ai", "ds"),
    ("робот", "embedded"),
    ("беспилот", "embedded"),   # расширение: дисциплины БАС
    ("мобильн", "mobile"),
    ("фронт", "frontend"),
    ("вёрстк", "frontend"),
    ("поддержк", "support"),
    ("тестирован", "qa"),
    ("продуктов", "backend"),   # расширение: продуктовое программирование
]

# Маппинг текста специальности из КИТ-сертификата на код специализации (разделы 6.1, 8.5)
KIT_SPECIALTY_KEYWORDS: List[Tuple[str, str]] = [
    ("технической поддержки", "support"),
    ("поддержк", "support"),
    ("информационной безопасности", "security"),
    ("безопасн", "security"),
    ("данным", "ds"),
    ("аналитик", "ds"),
    ("машинн", "ds"),
    ("data", "ds"),
    ("тестирован", "qa"),
    ("qa", "qa"),
    ("devops", "devops"),
    ("мобильн", "mobile"),
    ("робот", "embedded"),
    ("фронт", "frontend"),
    ("frontend", "frontend"),
    ("веб", "frontend"),
    ("backend", "backend"),
    ("сервер", "backend"),
    ("python", "backend"),
    ("разработ", "backend"),
]

# Словарь маркеров сомнительных вакансий (раздел 14.4 ТЗ, демо-версия)
RED_FLAG_MARKERS: List[str] = [
    "молодой дружный коллектив",
    "дружный коллектив",
    "как семья",
    "мы одна семья",
    "стрессоустойчив",
    "ненормированный рабочий день",
    "готовность к переработкам",
    "переработк",
    "работаем на результат, а не на время",
    "печеньки",
    "зарплата по итогам собеседования",
    "амбициозный и голодный",
    "быстрый карьерный рост без опыта",
    "оформление по желанию",
]


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _keyword_hit(text: str, keyword: str) -> bool:
    """Поиск ключевого слова: короткие ASCII-токены — по границам слова, прочие — подстрокой."""
    lowered = (text or "").lower()
    if not lowered or not keyword:
        return False
    if re.fullmatch(r"[a-z0-9+#/.]{1,3}", keyword):
        pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])"
        return re.search(pattern, lowered) is not None
    return keyword.lower() in lowered


def format_salary(salary_from: int, salary_to: int) -> str:
    """Вилка зарплаты в человекочитаемом виде. Вилка обязательна по ТЗ (раздел 5.3)."""
    def money(value: int) -> str:
        return f"{int(value):,}".replace(",", " ")

    if not salary_from and not salary_to:
        return "вилка не указана"
    if salary_from and salary_to and salary_from != salary_to:
        return f"{money(salary_from)} – {money(salary_to)} ₽"
    return f"от {money(salary_from or salary_to)} ₽"


def specialization_title(code: str) -> str:
    return SPECIALIZATIONS.get(code, SPECIALIZATIONS["other"])


def grade_title(code: str) -> str:
    return GRADES.get(code, code)


def category_title(value: Any) -> str:
    """Заголовок категории.

    Кандидат → «специализация · грейд» (категория раздела 6.6);
    строка или None → категория истории ФСП словами (S/A/B/C/D, раздел 9.2).
    """
    if value is None or isinstance(value, str):
        code = str(value or "").strip().upper()
        return FSP_CATEGORY_TITLES.get(code, code or "—")
    return f"{specialization_title(value.specialization)} · {grade_title(value.grade)}"


def normalize_grade(raw: Optional[str]) -> Optional[str]:
    """Senior → senior, «мидл» → middle. Не распознали → None (раздел 8.2)."""
    if not raw:
        return None
    token = str(raw).strip().lower().rstrip(".")
    if token in GRADE_ALIASES:
        return GRADE_ALIASES[token]
    for alias, grade in GRADE_ALIASES.items():
        if len(alias) > 3 and alias in token:
            return grade
    return None


# ---------------------------------------------------------------------------
# 6.1. Определение специализации кандидата
# ---------------------------------------------------------------------------

def detect_kit_specialization(text: Optional[str]) -> Optional[str]:
    """Специальность из КИТ-сертификата → код специализации. Не распознали → None."""
    spec_text = (text or "").strip()
    if not spec_text:
        return None
    for keyword, spec in KIT_SPECIALTY_KEYWORDS:
        if _keyword_hit(spec_text, keyword):
            return spec
    return None


def detect_fsp_specialization(disciplines: Iterable[str]) -> Optional[str]:
    """Первая дисциплина ФСП, которая маппится на специализацию."""
    for discipline in disciplines or ():
        if not discipline:
            continue
        for keyword, spec in FSP_DISCIPLINE_KEYWORDS:
            if _keyword_hit(discipline, keyword):
                return spec
    return None


def detect_stack_specialization(stack: Any) -> Optional[str]:
    """Специализация по стеку: побеждает группа с наибольшим числом совпадений."""
    text = stack_text(stack)
    if not text:
        return None
    best_spec: Optional[str] = None
    best_hits = 0
    for spec, keywords in STACK_SPEC_KEYWORDS:
        hits = sum(1 for kw in keywords if _keyword_hit(text, kw))
        if hits > best_hits:
            best_spec, best_hits = spec, hits
    return best_spec


def detect_specialization(
    kit_specialization: Optional[str] = None,
    fsp_disciplines: Sequence[str] = (),
    stack: str = "",
    manual: str = "",
) -> Tuple[str, str]:
    """Приоритет источников: КИТ → ФСП → стек → ручной выбор (раздел 6.1).

    Возвращает пару (specialization, specialization_source).
    """
    spec = detect_kit_specialization(kit_specialization)
    if spec:
        return spec, "kit"
    spec = detect_fsp_specialization(fsp_disciplines)
    if spec:
        return spec, "fsp"
    spec = detect_stack_specialization(stack)
    if spec:
        return spec, "stack"
    if manual in SPECIALIZATIONS:
        return manual, "manual"
    return "other", "manual"


# ---------------------------------------------------------------------------
# 6.3 / 7.3. Амбициозность кандидата
# ---------------------------------------------------------------------------

def stack_text(value: Any) -> str:
    """Стек в виде строки: список/кортеж → «a, b, c», строка → как есть.

    В моделях стек хранится списком (JSON), а часть правил раздела 6/7
    исторически работает со строкой — функция снимает это расхождение.
    """
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def is_wide_stack(stack: Any) -> bool:
    """«Широкий стек» — ≥ 3 элементов (раздел 7.3)."""
    if isinstance(stack, (list, tuple, set)):
        return len([item for item in stack if str(item).strip()]) >= 3
    return stack_text(stack).count(",") >= 2


def ambition_flags(
    team_role: str = "",
    work_format: str = "",
    stack: str = "",
    fsp_role: Optional[str] = None,
) -> List[str]:
    """Флаги барометра амбиций — каждый свой (раздел 6.3). Возвращает описания флагов."""
    return [AMBITIONS[code] for code in ambition_codes(team_role, work_format, stack, fsp_role)]


def compute_ambition(
    team_role: str = "",
    work_format: str = "",
    stack: str = "",
    fsp_role: Optional[str] = None,
) -> bool:
    """ambition = True, если сумма флагов ≥ 2 (разделы 6.3 и 7.3)."""
    return len(ambition_flags(team_role, work_format, stack, fsp_role)) >= 2


# ---------------------------------------------------------------------------
# 6.4. Тир работодателя
# ---------------------------------------------------------------------------

def tier_score(source: Any) -> int:
    """Сумма «здоровых» ответов анкеты, 0–6. Принимает Employer, dict или список bool."""
    if source is None:
        return 0
    if isinstance(source, dict):
        values = [source.get(q, False) for q in TIER_QUESTIONS]
    elif isinstance(source, (list, tuple)):
        values = list(source)[: len(TIER_QUESTIONS)]
    else:
        values = [getattr(source, q, False) for q in TIER_QUESTIONS]
    return sum(1 for value in values if bool(value))


def compute_tier(source: Any) -> int:
    """5–6 → тир 3, 3–4 → тир 2, 0–2 → тир 1 (раздел 6.4). В БД не хранится."""
    score = tier_score(source)
    if score >= 5:
        return 3
    if score >= 3:
        return 2
    return 1


def tier_label(tier: Any) -> str:
    """Как тир называется для кандидата (раздел 6.4). Работодателю не показывается."""
    return TIER_LABELS.get(int(tier or 1), TIER_LABELS[1])


# ---------------------------------------------------------------------------
# 6.5. Матрица видимости
# ---------------------------------------------------------------------------

def is_top_fsp(candidate: Any) -> bool:
    """«Топ ФСП»: grade = senior И (fsp_category ∈ {S, A} ИЛИ
    fsp_role = капитан/архитектор И fsp_score > 0) — раздел 6.5."""
    if (candidate.grade or "").lower() != "senior":
        return False
    if (candidate.fsp_category or "").upper() in ("S", "A"):
        return True
    return (
        (candidate.fsp_role or "").strip().lower() in CAPTAIN_ROLES
        and (candidate.fsp_score or 0) > 0
    )


def candidate_min_tier(candidate: Any) -> int:
    """Минимальный тир работодателя, который видит кандидата (раздел 6.5).

    1 — новичок без амбиций (виден всем), 2 — мидлы/сеньоры и амбициозные новички,
    3 — только топ ФСП.
    """
    if is_top_fsp(candidate):
        return 3
    grade = (candidate.grade or "").lower()
    if grade in ("middle", "senior"):
        return 2
    if grade == "junior":
        captain = (candidate.fsp_role or "").strip().lower() in CAPTAIN_ROLES
        if candidate.ambition or captain:
            return 2
        return 1
    return 1


def is_visible(candidate: Any, tier: int) -> bool:
    """Виден ли кандидат работодателю данного тира: чем выше тир, тем шире банк."""
    return int(tier) >= candidate_min_tier(candidate)


def profile_level(candidate: Any) -> str:
    """Человеческое название строки матрицы видимости — показывается только кандидату."""
    if is_top_fsp(candidate):
        return "топ ФСП"
    grade = (candidate.grade or "").lower()
    if grade == "senior":
        return "опытный специалист"
    if grade == "middle":
        return "мидл"
    if candidate.ambition:
        return "новичок с амбициями"
    return "новичок без амбиций"


def visible_candidates(candidates: Iterable[Any], tier: int, only_public: bool = True) -> List[Any]:
    """Банк кандидатов, доступный тиру работодателя."""
    result = []
    for candidate in candidates:
        if only_public and not getattr(candidate, "is_public", True):
            continue
        if is_visible(candidate, tier):
            result.append(candidate)
    return result


# ---------------------------------------------------------------------------
# 6.6. Ранжирование внутри категории
# ---------------------------------------------------------------------------

def rank_key(candidate: Any) -> Tuple:
    """Ключ сортировки (раздел 6.6): верификация → КИТ-балл → ФСП-балл → роль ФСП → амбиции."""
    return (
        0 if candidate.is_verified else 1,
        -(candidate.kit_score or 0),
        -(candidate.fsp_score or 0),
        0 if (candidate.fsp_role or "").strip().lower() in CAPTAIN_ROLES else 1,
        0 if candidate.ambition else 1,
        candidate.id or 0,  # детерминированный тай-брейк при полном равенстве
    )


def stack_tokens(text: Any) -> List[str]:
    """Разбивает стек на элементы: список → как есть, строка → по запятым, слэшам, переносам."""
    if isinstance(text, (list, tuple, set)):
        parts = [str(item) for item in text]
    else:
        parts = re.split(r"[,;/\n|]+", str(text or ""))
    tokens = [part.strip(" .-()[]").lower() for part in parts]
    return [token for token in tokens if token]


def stack_match(need_stack: Any, candidate_stack: Any) -> Tuple[List[str], int]:
    """Пересечение стека потребности и стека кандидата: (список совпадений, всего токенов)."""
    tokens = stack_tokens(need_stack)
    if not tokens:
        return [], 0
    candidate_tokens = stack_tokens(candidate_stack)
    joined = " ".join(candidate_tokens)
    matched = [token for token in tokens if token in candidate_tokens or token in joined]
    return matched, len(tokens)


def sort_candidates(candidates: Iterable[Any], need_stack: str = "") -> List[Any]:
    """Сортировка внутри категории по правилам 6.6.

    Если у потребности работодателя задан стек, выше поднимаются кандидаты
    с большим пересечением стека (объяснимая выдача по потребности);
    внутри равных по стеку — строгий порядок 6.6.
    """
    items = list(candidates)
    tokens = stack_tokens(need_stack)
    if tokens:
        def key_with_need(candidate: Any) -> Tuple:
            candidate_text = stack_text(candidate.stack).lower()
            matched = sum(1 for t in tokens if t and t in candidate_text)
            return (-matched,) + rank_key(candidate)

        items.sort(key=key_with_need)
    else:
        items.sort(key=rank_key)
    return items


def filter_by_category(candidates: Iterable[Any], specialization: str = "", grade: str = "") -> List[Any]:
    """Категория = специализация + грейд (раздел 6.6). Пустые фильтры не сужают выборку."""
    result = []
    for candidate in candidates:
        if specialization and candidate.specialization != specialization:
            continue
        if grade and candidate.grade != grade:
            continue
        result.append(candidate)
    return result


# ---------------------------------------------------------------------------
# Объяснимость выдачи (требование ТЗ ФСП, п. 2.1) и маркеры вакансий (п. 14.4)
# ---------------------------------------------------------------------------

def explain_candidate(candidate: Any, need_stack: str = "") -> List[str]:
    """Почему кандидат в подборке и на этой позиции. Тир работодателя не раскрывается."""
    reasons: List[str] = []
    if candidate.is_verified:
        score = f", {candidate.kit_score} баллов" if candidate.kit_score is not None else ""
        reasons.append(f"грейд подтверждён сертификатом КИТ{score}")
    else:
        reasons.append("грейд заявлен кандидатом самостоятельно, не верифицирован")
    if (candidate.fsp_score or 0) > 0:
        reasons.append(
            f"достижения ФСП: {candidate.fsp_score} баллов, категория {candidate.fsp_category}"
        )
        if (candidate.fsp_role or "").strip():
            reasons.append(f"роль в команде ФСП — {candidate.fsp_role}")
    else:
        reasons.append("история ФСП отсутствует")
    if candidate.ambition:
        reasons.append("амбициозный профиль (барометр амбиций: ≥ 2 флагов)")
    matched, total = stack_match(need_stack, candidate.stack)
    if total:
        if matched:
            reasons.append(
                "совпадение стека с потребностью: "
                + ", ".join(matched)
                + f" ({len(matched)} из {total})"
            )
        else:
            reasons.append(f"стек не пересекается с требуемым (0 из {total})")
    return reasons


def scan_markers(text: Optional[str]) -> List[str]:
    """Маркеры сомнительного описания вакансии (раздел 14.4 ТЗ, демо-словарь)."""
    lowered = (text or "").lower()
    return [marker for marker in RED_FLAG_MARKERS if marker in lowered]


def validate_salary(salary_from: Any, salary_to: Any) -> Optional[str]:
    """Вилка зарплаты обязательна везде (разделы 5.3, 6.7). Возвращает текст ошибки или None."""
    try:
        low = int(salary_from or 0)
        high = int(salary_to or 0)
    except (TypeError, ValueError):
        return "Вилка зарплаты должна быть числом"
    if low <= 0 or high <= 0:
        return "Укажите вилку зарплаты: обе границы обязательны и больше нуля"
    if low > high:
        return "Нижняя граница вилки не может быть больше верхней"
    return None


def validate_email(email: Optional[str]) -> Optional[str]:
    """Минимальная проверка email — регистрация выполняется по электронной почте (ТЗ ФСП, 2.2.4)."""
    value = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        return "Укажите корректный email"
    return None


def mask_name(name: Optional[str]) -> str:
    """Анонимизация ФИО для работодателя до принятия приглашения (раздел 6.7)."""
    value = (name or "").strip()
    if not value:
        return "Кандидат"
    parts = value.split()
    if len(parts) == 1:
        return parts[0][0] + "•" * 4
    return " ".join([parts[0][0] + ".", parts[1][0] + "."])


# ---------------------------------------------------------------------------
# Расширение для веб-слоя: справочники тиров, парсеры форм, статусы
# (разделы 6.4, 6.5, 10.3, 10.4)
# ---------------------------------------------------------------------------

from models import STATUS_TITLES  # noqa: E402  — models не импортирует logic, цикла нет

# Состав полей карточки кандидата, доступный работодателю (разделы 6.5, 6.7, 11.15).
# Показывается работодателю, чтобы он понимал, почему часть данных скрыта.
TIER_FIELDS: Dict[int, List[str]] = {
    1: ["специализация", "грейд", "метка верификации", "баллы КИТ", "стек",
        "достижения ФСП кратко"],
    2: ["специализация", "грейд", "метка верификации", "баллы КИТ", "стек",
        "достижения ФСП кратко", "амбициозность", "роль в команде ФСП"],
    3: ["специализация", "грейд", "метка верификации", "баллы КИТ", "стек",
        "достижения ФСП", "амбициозность", "роль в команде ФСП", "город", "полный профиль"],
}

# Расшифровка словесных названий тиров: видна кандидату и используется в документации
TIER_DESCRIPTIONS: Dict[int, str] = {
    3: "развитые процессы: доступны все профили банка, включая топ ФСП",
    2: "базовые процессы: доступны новички с амбициями, мидлы и сеньоры; топ ФСП закрыт",
    1: "начальные процессы: доступны только новички без амбиций",
}

# Единственное правило раскрытия контактов (п. 5 и п. 10 раздела 6.7)
CONTACT_REVEAL_NOTE = ("ФИО и контакты кандидата раскрываются работодателю только после того, "
                       "как кандидат принял приглашение")

# Режимы сопоставления грейда потребности и кандидата (раздел 10.3)
GRADE_MATCH_MODES: Dict[str, str] = {
    "exact": "строго указанный грейд",
    "plus_minus": "указанный грейд ± 1 уровень",
    "any": "грейд не важен",
}

DEFAULT_GRADE_MATCH_MODE = "plus_minus"

GRADE_ORDER: Dict[str, int] = {"junior": 1, "middle": 2, "senior": 3}


def status_title(code: Optional[str]) -> str:
    """Название статуса приглашения/отклика (раздел 10.4)."""
    return STATUS_TITLES.get(code or "", code or "")


def parse_int(value: Any) -> Optional[int]:
    """Безопасный разбор числа из формы: пустая строка и мусор → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def parse_bool(value: Any) -> bool:
    """Значение чекбокса/радио из формы → bool."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "on", "yes", "да")


def parse_list(value: Any) -> List[str]:
    """Список из формы: список → как есть, строка → по запятым и переносам."""
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = [part.strip() for part in re.split(r"[,;\n|]+", str(value or ""))]
    return [item for item in items if item]


def salary_error(salary_from: Any, salary_to: Any) -> Optional[str]:
    """Проверка вилки (раздел 5.3). Обёртка над validate_salary для веб-слоя."""
    return validate_salary(salary_from, salary_to)


def salary_note(salary_from: Any, salary_to: Any) -> str:
    """Вилка в человекочитаемом виде. Обёртка над format_salary для веб-слоя."""
    return format_salary(parse_int(salary_from) or 0, parse_int(salary_to) or 0)


def detect_grade(raw: Any) -> Optional[str]:
    """Синоним normalize_grade — единая точка определения грейда (раздел 8.2)."""
    return normalize_grade(raw if isinstance(raw, str) else str(raw or "") or None)


def specialization_match(candidate_spec: Optional[str], need_spec: Optional[str]) -> bool:
    """Совпадение специализации кандидата и потребности (раздел 6.6)."""
    if not need_spec or not candidate_spec:
        return False
    return str(candidate_spec).lower() == str(need_spec).lower()


def grade_priority(grade: Optional[str]) -> int:
    """Числовой приоритет грейда: senior=3, middle=2, junior=1, прочее=0."""
    return GRADE_ORDER.get(str(grade or "").lower(), 0)


def grade_matches(candidate_grade: Optional[str], need_grade: Optional[str],
                  mode: str = "") -> bool:
    """Подходит ли грейд кандидата под требование потребности (раздел 10.3).

    Режимы: exact — строго этот грейд, plus_minus — ± 1 уровень, any — грейд не важен.
    Неизвестный режим трактуется как режим по умолчанию (plus_minus).
    """
    if not need_grade:
        return True
    matcher = str(mode or DEFAULT_GRADE_MATCH_MODE).strip().lower()
    if matcher not in GRADE_MATCH_MODES:
        matcher = DEFAULT_GRADE_MATCH_MODE
    if matcher == "any":
        return True
    candidate_rank = grade_priority(candidate_grade)
    need_rank = grade_priority(need_grade)
    if matcher == "exact":
        return candidate_rank == need_rank
    return abs(candidate_rank - need_rank) <= 1


def is_ambitious(candidate: Any) -> bool:
    """Амбициозность кандидата по барометру (раздел 6.3)."""
    if hasattr(candidate, "ambition"):
        return bool(candidate.ambition)
    return compute_ambition(
        getattr(candidate, "team_role", ""),
        getattr(candidate, "work_format", ""),
        getattr(candidate, "stack", ""),
        getattr(candidate, "fsp_role", None),
    )


# ---------------------------------------------------------------------------
# 6.1 (веб-обёртка). Как определена специализация кандидата
# ---------------------------------------------------------------------------

SPECIALIZATION_SOURCES: Dict[str, str] = {
    "kit": "по специальности из сертификата КИТ",
    "fsp": "по дисциплине ФСП",
    "stack": "по указанному стеку",
    "manual": "выбрана вручную",
}


def fsp_disciplines(candidate: Any) -> List[str]:
    """Дисциплины из истории ФСП кандидата (раздел 9). Без подключения — пустой список."""
    import fsp_mock  # локальный импорт: fsp_mock от logic не зависит, цикла нет

    if not getattr(candidate, "fsp_connected", False):
        return []
    history = fsp_mock.get_achievements(getattr(candidate, "email", ""))
    return fsp_mock.disciplines(history.get("achievements") or [])


def kit_specialty_text(candidate: Any) -> str:
    """Строка специальности из сертификата КИТ, а не весь распознанный текст.

    ``detect_kit_specialization`` ищет ключевые слова, поэтому ей нельзя отдавать
    весь текст сертификата: слово «тестирование» из шапки документа (раздел 8.1)
    есть в любом сертификате и уводило бы специализацию в QA.
    """
    import kit_parser  # локальный импорт: kit_parser зависит от logic, цикла нет

    raw = str(getattr(candidate, "kit_raw", "") or "")
    if not raw:
        return ""
    parsed = kit_parser.parse_kit_text(raw) or {}
    return str(parsed.get("kit_specialization") or "")


def resolve_specialization(candidate: Any) -> Dict[str, Any]:
    """Специализация и источник её определения (раздел 6.1).

    Приоритет: КИТ → ФСП → стек → ручной выбор. Ручной выбор побеждает, если
    кандидат сам отметил специализацию в анкете (`specialization_manual`).
    """
    manual = str(getattr(candidate, "specialization", "") or "")
    if getattr(candidate, "specialization_manual", False) and manual in SPECIALIZATIONS:
        code, source = manual, "manual"
    else:
        code, source = detect_specialization(
            kit_specialty_text(candidate),
            fsp_disciplines(candidate),
            getattr(candidate, "stack", ""),
            manual,
        )
    label = SPECIALIZATION_SOURCES.get(source, source)
    return {
        "code": code,
        "source": source,
        "source_label": label,
        "note": f"{specialization_title(code)} — определена {label}",
    }


# ---------------------------------------------------------------------------
# 6.2 (веб-обёртка). Итоговый грейд кандидата
# ---------------------------------------------------------------------------

GRADE_SOURCES: Dict[str, str] = {
    "kit": "подтверждён сертификатом КИТ",
    "kit_number": "определён по букве в номере сертификата КИТ",
    "manual": "выбран кандидатом",
    "barometer": "предварительно оценён по барометру амбиций",
    "default": "по умолчанию",
}

CERTIFICATE_GRADE_LETTERS: Dict[str, str] = {"J": "junior", "M": "middle", "S": "senior"}


def grade_from_certificate_number(number: Any) -> Optional[str]:
    """Буква грейда в номере сертификата КИТ формата ГГГГММДД-Н-X-ННН (раздел 8.2)."""
    match = re.search(r"\d{8}-\d+-([JMSjms])-\d+", str(number or ""))
    if not match:
        return None
    return CERTIFICATE_GRADE_LETTERS.get(match.group(1).upper())


def resolve_grade(kit_grade: Any = None, certificate_number: Any = None,
                  ambitions: Any = None, manual_grade: Any = None) -> Dict[str, Any]:
    """Итоговый грейд: КИТ → ручной выбор → барометр амбиций → junior (раздел 6.2).

    Возвращает {"grade", "verified", "grade_source", "source_label", "note"}.
    Верифицированным считается только грейд из сертификата КИТ (разделы 6.2 и 8.4):
    он влияет на матрицу видимости и на ранжирование внутри категории.
    """
    grade = normalize_grade(kit_grade)
    source = "kit"
    if not grade:
        grade = grade_from_certificate_number(certificate_number)
        source = "kit_number"
    verified = bool(grade)
    if not grade:
        grade = normalize_grade(manual_grade)
        source = "manual"
    if not grade:
        flags = [item for item in as_list(ambitions) if item in AMBITIONS]
        if len(flags) >= AMBITION_THRESHOLD:
            grade, source = "middle", "barometer"
        else:
            grade, source = "junior", "default"
    label = GRADE_SOURCES.get(source, source)
    return {
        "grade": grade,
        "verified": verified,
        "grade_source": source,
        "source_label": label,
        "note": f"{grade_title(grade)} — {label}",
    }


def resolve_grade_for(candidate: Any) -> Dict[str, Any]:
    """resolve_grade по полям кандидата — единая точка для моделей, хелперов и сервисов."""
    return resolve_grade(
        getattr(candidate, "kit_grade", None),
        getattr(candidate, "kit_certificate_number", None),
        getattr(candidate, "ambitions", None),
        getattr(candidate, "grade_override", None),
    )


# ---------------------------------------------------------------------------
# 6.3 (веб-обёртка). Барометр амбиций: коды флагов и формулировки
# ---------------------------------------------------------------------------

def ambition_codes(team_role: str = "", work_format: str = "", stack: Any = "",
                   fsp_role: Optional[str] = None) -> List[str]:
    """Коды сработавших флагов барометра (раздел 6.3) — ключи словаря AMBITIONS."""
    codes: List[str] = []
    if (team_role or "").strip().lower() in CAPTAIN_ROLES:
        codes.append("captain")
    if (work_format or "").strip().lower() == WORK_FORMAT_INFLUENCE:
        codes.append("influence")
    if is_wide_stack(stack):
        codes.append("wide_stack")
    if (fsp_role or "").strip().lower() in CAPTAIN_ROLES:
        codes.append("fsp_captain")
    return codes


def ambitions_flags(candidate: Any) -> List[str]:
    """Коды флагов барометра по анкете кандидата (раздел 6.3)."""
    return ambition_codes(
        getattr(candidate, "team_role", ""),
        getattr(candidate, "work_format", ""),
        getattr(candidate, "stack", ""),
        getattr(candidate, "fsp_role", None),
    )


def ambitions_labels(codes: Any) -> List[str]:
    """Формулировки флагов по их кодам — то, что видит кандидат в кабинете."""
    return [AMBITIONS[str(code)] for code in as_list(codes) if str(code) in AMBITIONS]


def ambitions_note(candidate: Any) -> str:
    """Вердикт барометра одной строкой (разделы 6.3 и 7.3)."""
    flags = ambitions_flags(candidate)
    total = len(flags)
    verdict = ("амбициозный профиль" if total >= AMBITION_THRESHOLD
               else "профиль без выраженных амбиций")
    listed = ", ".join(ambitions_labels(flags)) or "флаги не сработали"
    return (f"Барометр амбиций: {total} из {len(AMBITIONS)} флагов "
            f"(порог — {AMBITION_THRESHOLD}). Сработало: {listed}. Вердикт: {verdict}")



# ---------------------------------------------------------------------------
# 7.3 / 8.4 (веб-обёртка). Полнота профиля, ограничения, состав видимых полей
# ---------------------------------------------------------------------------

# Обязательные поля анкеты кандидата: без них профиль не участвует в подборе
PROFILE_REQUIRED_FIELDS: List[Tuple[str, str]] = [
    ("name", "имя и фамилия"),
    ("specialization", "специализация"),
    ("team_role", "роль в команде"),
    ("work_format", "формат работы"),
]


def missing_profile_fields(candidate: Any) -> List[str]:
    """Чего не хватает в анкете кандидата (разделы 7.3 и 8.4)."""
    missing = [
        title for field, title in PROFILE_REQUIRED_FIELDS
        if not str(getattr(candidate, field, "") or "").strip()
    ]
    if not getattr(candidate, "consent", False):
        missing.append("согласие на обработку персональных данных (152-ФЗ)")
    return missing


def profile_complete(candidate: Any) -> bool:
    """Профиль заполнен — кандидат участвует в банке, ранжировании и приглашениях."""
    return not missing_profile_fields(candidate)


def restricted_reason(candidate: Any) -> str:
    """Почему профиль закрыт. Формулировка не раскрывает тир работодателя (раздел 6.4)."""
    missing = missing_profile_fields(candidate)
    if missing:
        return "профиль заполнен не полностью: " + ", ".join(missing)
    if not getattr(candidate, "is_public", True):
        return "кандидат скрыл профиль из банка"
    return "уровень профиля выше, чем доступен при текущем уровне организации процессов"


def visibility_allows(candidate: Any, employer: Any) -> bool:
    """Доступен ли кандидат работодателю: полный профиль + открытость + матрица 6.5."""
    tier = getattr(employer, "tier", None)
    if tier is None or not profile_complete(candidate):
        return False
    if not getattr(candidate, "is_public", True):
        return False
    return is_visible(candidate, int(tier))


def candidate_visible_profile(candidate: Any, tier: Any = None) -> Dict[str, Any]:
    """Состав полей кандидата, доступный работодателю данного тира (разделы 6.5, 6.7, 11.15).

    До принятия приглашения ФИО и контакты не раскрываются никому: в карточке лежит
    маскированное имя, а настоящие ФИО и email — в ключах `real_name` и `email`,
    которые шаблоны используют только для приглашений со статусом accepted
    (п. 5 и п. 10 раздела 6.7). Чем ниже тир, тем меньше полей: tier 1 не видит
    амбициозность и роль в команде ФСП, tier 2 — город и полный профиль.
    """
    tier_value = int(tier) if tier is not None else 0
    complete = profile_complete(candidate)
    public = bool(getattr(candidate, "is_public", True))
    matrix_ok = is_visible(candidate, tier_value) if tier is not None else False
    is_open = bool(complete and public and matrix_ok)
    grade = resolve_grade_for(candidate)

    if not complete:
        note = "Профиль заполнен не полностью — кандидат не участвует в подборе"
    elif not public:
        note = "Кандидат скрыл профиль из банка — приглашение недоступно"
    elif not matrix_ok:
        note = "Профиль недоступен при текущем уровне организации процессов"
    else:
        note = ("Профиль открыт: " + ", ".join(TIER_FIELDS.get(tier_value, TIER_FIELDS[1]))
                + ". " + CONTACT_REVEAL_NOTE)

    profile: Dict[str, Any] = {
        "id": getattr(candidate, "id", None),
        "is_open": is_open,
        "is_restricted": not is_open,
        "restricted_reason": "" if is_open else restricted_reason(candidate),
        "visibility_note": note,
        "visible_fields": TIER_FIELDS.get(tier_value, TIER_FIELDS[1]) if is_open else [],
        # анонимная часть карточки — видна всегда
        "name": mask_name(getattr(candidate, "name", "")),
        "real_name": str(getattr(candidate, "name", "") or ""),
        "email": str(getattr(candidate, "email", "") or ""),
        "specialization": getattr(candidate, "specialization", "") or "",
        "specialization_title": specialization_title(getattr(candidate, "specialization", "")),
        "category": category_title(candidate),
        "grade": grade["grade"],
        "grade_title": grade_title(grade["grade"]),
        "grade_note": grade["note"],
        "verified": grade["verified"],
        "kit_score": getattr(candidate, "kit_score", None),
        "stack": parse_list(getattr(candidate, "stack", "")),
        "profile_level": profile_level(candidate),
        # достижения ФСП кратко — видны всем тирам (раздел 11.15)
        "fsp_connected": bool(getattr(candidate, "fsp_connected", False)),
        "fsp_score": int(getattr(candidate, "fsp_score", 0) or 0),
        "fsp_category": str(getattr(candidate, "fsp_category", "") or "D"),
        "fsp_category_title": category_title(getattr(candidate, "fsp_category", "") or "D"),
        # доступно с tier 2
        "fsp_role": str(getattr(candidate, "fsp_role", "") or ""),
        "is_ambitious": is_ambitious(candidate),
        "ambition_hidden": False,
        # доступно с tier 3
        "city": str(getattr(candidate, "city", "") or ""),
    }
    if tier_value < 3:
        profile["city"] = ""
    if tier_value < 2:
        profile["fsp_role"] = ""
        profile["is_ambitious"] = None
        profile["ambition_hidden"] = True
    return profile


def red_flags(candidate: Any) -> List[str]:
    """На что обратить внимание в профиле кандидата. Тир работодателя не раскрывается."""
    flags: List[str] = []
    if not getattr(candidate, "is_verified", False):
        flags.append("грейд не подтверждён сертификатом КИТ")
    missing = missing_profile_fields(candidate)
    if missing:
        flags.append("профиль заполнен не полностью: " + ", ".join(missing))
    if not getattr(candidate, "is_public", True):
        flags.append("кандидат скрыл профиль из банка — приглашение недоступно")
    if int(getattr(candidate, "fsp_score", 0) or 0) <= 0:
        flags.append("история ФСП не найдена: 0 баллов, категория D")
    if not is_ambitious(candidate):
        flags.append("барометр амбиций: меньше двух флагов")
    if (getattr(candidate, "specialization", "") or "") in ("", "other"):
        flags.append("специализация не определена автоматически — уточните в анкете")
    return flags


# ---------------------------------------------------------------------------
# 6.6 / 10.3 (веб-обёртка). Релевантность пары «кандидат ↔ потребность»
# ---------------------------------------------------------------------------

# Веса признаков в процентах, сумма = 100. Никакого ML и эмбеддингов (раздел 14.8):
# только словари, сравнения и арифметика, каждый признак объясняется текстом (п. 2.1).
MATCH_WEIGHTS: Dict[str, int] = {
    "specialization": 35,   # категория: специализация кандидата и потребности
    "stack": 25,            # доля совпавших элементов стека потребности
    "grade": 20,            # грейд с учётом режима сопоставления (exact/plus_minus/any)
    "verified": 10,         # верификация грейда сертификатом КИТ
    "fsp": 10,              # история ФСП: баллы, категория, роль + амбициозность
}

# Баллы за категорию истории ФСП внутри критерия «история ФСП» (разделы 6.6 и 9.2)
MATCH_FSP_POINTS: Dict[str, int] = {"S": 10, "A": 9, "B": 7, "C": 5, "D": 2}


def score_match(candidate: Any, vacancy: Any) -> Dict[str, Any]:
    """Релевантность пары «кандидат ↔ потребность» в процентах и её объяснение.

    Возвращает {"score", "summary", "reasons", "grade_ok", "specialization_ok",
    "stack_matched", "stack_total", "category"} — ровно те ключи, которые читают
    карточки потребностей (раздел 11.10) и карточки кандидатов (раздел 11.16).
    """
    reasons: List[str] = []

    need_spec = str(getattr(vacancy, "specialization", "") or "")
    spec_ok = specialization_match(getattr(candidate, "specialization", ""), need_spec)
    spec_points = MATCH_WEIGHTS["specialization"] if spec_ok else 0
    if spec_ok:
        reasons.append(f"специализация совпадает: {specialization_title(need_spec)}")
    else:
        reasons.append(
            "специализация не совпадает: у кандидата "
            f"{specialization_title(getattr(candidate, 'specialization', ''))}, "
            f"в потребности {specialization_title(need_spec)}"
        )

    matched, total = stack_match(getattr(vacancy, "stack", ""), getattr(candidate, "stack", ""))
    if total:
        stack_points = round(MATCH_WEIGHTS["stack"] * len(matched) / total)
        tail = f" ({', '.join(matched)})" if matched else ""
        reasons.append(f"стек: совпало {len(matched)} из {total}{tail}")
    else:
        own = len(stack_tokens(getattr(candidate, "stack", "")))
        if own >= 3:
            stack_points = MATCH_WEIGHTS["stack"]
        elif own:
            stack_points = MATCH_WEIGHTS["stack"] // 2
        else:
            stack_points = 0
        reasons.append(
            "стек в потребности не указан — оцениваем ширину стека кандидата "
            f"({own} элемент(ов))"
        )

    need_grade = str(getattr(vacancy, "grade", "") or "")
    mode = str(getattr(vacancy, "grade_match", "") or DEFAULT_GRADE_MATCH_MODE)
    candidate_grade = str(getattr(candidate, "grade", "") or "")
    if not need_grade or mode.strip().lower() == "any":
        grade_points = MATCH_WEIGHTS["grade"]
        grade_ok = True
        reasons.append("грейд в потребности не задан — ограничений по грейду нет")
    else:
        grade_ok = grade_matches(candidate_grade, need_grade, mode)
        note = GRADE_MATCH_MODES.get(mode.strip().lower(), GRADE_MATCH_MODES[DEFAULT_GRADE_MATCH_MODE])
        if grade_ok:
            grade_points = MATCH_WEIGHTS["grade"]
            reasons.append(f"грейд подходит: {grade_title(candidate_grade)} ({note})")
        elif abs(grade_priority(candidate_grade) - grade_priority(need_grade)) == 1:
            grade_points = MATCH_WEIGHTS["grade"] // 2
            reasons.append(
                f"грейд соседний: у кандидата {grade_title(candidate_grade)}, "
                f"в потребности {grade_title(need_grade)} ({note})"
            )
        else:
            grade_points = 0
            reasons.append(
                f"грейд не совпадает: у кандидата {grade_title(candidate_grade)}, "
                f"в потребности {grade_title(need_grade)} ({note})"
            )

    verified = bool(getattr(candidate, "is_verified", False))
    verified_points = MATCH_WEIGHTS["verified"] if verified else MATCH_WEIGHTS["verified"] // 3
    reasons.append(
        "грейд верифицирован сертификатом КИТ" if verified
        else "грейд заявлен кандидатом самостоятельно, не верифицирован"
    )

    fsp_score = parse_int(getattr(candidate, "fsp_score", 0)) or 0
    category = str(getattr(candidate, "fsp_category", "") or "").strip().upper()
    if not category:
        category = category_from_score(fsp_score)
    fsp_points = MATCH_FSP_POINTS.get(category, MATCH_FSP_POINTS["D"])
    if is_ambitious(candidate):
        fsp_points = min(MATCH_WEIGHTS["fsp"], fsp_points + 1)
    ambition_tail = ", амбициозный профиль" if is_ambitious(candidate) else ""
    reasons.append(f"история ФСП: {fsp_score} баллов, категория {category}{ambition_tail}")

    score = spec_points + stack_points + grade_points + verified_points + fsp_points
    score = max(0, min(100, score))
    summary = (f"{specialization_title(getattr(candidate, 'specialization', ''))} · "
               f"{grade_title(candidate_grade)}: релевантность {score}%")
    return {
        "score": score,
        "summary": summary,
        "reasons": reasons,
        "grade_ok": grade_ok,
        "specialization_ok": spec_ok,
        "stack_matched": matched,
        "stack_total": total,
        "category": category_title(candidate),
    }


def rank_candidates(candidates: Iterable[Any], vacancy: Any,
                    tier: Any = None) -> List[Tuple[Any, Dict[str, Any]]]:
    """Подборка кандидатов под потребность (разделы 6.5–6.7).

    Порядок действий из п. 3–4 раздела 6.7: фильтр по матрице видимости и полноте
    профиля → отбор по категории (специализация потребности) → сортировка по
    убыванию релевантности, внутри равных — строгий порядок раздела 6.6 (rank_key).
    Возвращает пары (candidate, match). Если `tier` не передан, фильтр видимости
    не применяется — вызывающий код обязан сам исключить недоступные профили.
    """
    rows: List[Tuple[Any, Dict[str, Any]]] = []
    need_spec = str(getattr(vacancy, "specialization", "") or "")
    for candidate in candidates:
        if not profile_complete(candidate):
            continue
        if not getattr(candidate, "is_public", True):
            continue
        if tier is not None and not is_visible(candidate, int(tier)):
            continue
        if not specialization_match(getattr(candidate, "specialization", ""), need_spec):
            continue
        rows.append((candidate, score_match(candidate, vacancy)))
    rows.sort(key=lambda pair: (-pair[1]["score"],) + rank_key(pair[0]))
    return rows


def grade_match_note(grade: Any, mode: Any = "") -> str:
    """Как потребность трактует грейд (раздел 10.3) — текст для карточки."""
    matcher = str(mode or DEFAULT_GRADE_MATCH_MODE).strip().lower()
    if matcher not in GRADE_MATCH_MODES:
        matcher = DEFAULT_GRADE_MATCH_MODE
    if matcher == "any" or not str(grade or "").strip():
        return "грейд не важен — смотрим на стек, верификацию и достижения ФСП"
    return f"{grade_title(normalize_grade(grade) or '')} — {GRADE_MATCH_MODES[matcher]}"


def stack_note(stack: Any, title: str = "") -> str:
    """Подсказка по стеку потребности (разделы 6.1 и 10.3)."""
    tokens = stack_tokens(stack)
    if not tokens:
        if title:
            return f"стек не указан — специализация определяется по должности «{title}»"
        return "стек не указан"
    return "стек потребности: " + ", ".join(tokens)


# ---------------------------------------------------------------------------
# Мелкие веб-обёртки: единые точки разбора и форматирования для шаблонов
# ---------------------------------------------------------------------------

def as_list(value: Any) -> List[str]:
    """Синоним parse_list: единый разбор списков из форм и из БД (раздел 7.3)."""
    return parse_list(value)


def email_error(email: Any) -> Optional[str]:
    """Обёртка validate_email для маршрутов входа и регистрации (раздел 2.2.4)."""
    return validate_email(email)


def employer_tier(source: Any) -> int:
    """Обёртка compute_tier: тир считается из анкеты (раздел 6.4).

    Значение дублируется в поле Employer.tier, чтобы страницы читали его без
    пересчёта; источником истины остаются ответы анкеты.
    """
    return compute_tier(source)


def category_from_score(score: Any) -> str:
    """Категория истории ФСП по баллам (раздел 9.2). Пороги — как в мок-реестре."""
    import fsp_mock  # локальный импорт: fsp_mock от logic не зависит, цикла нет

    return fsp_mock.compute_fsp_category(parse_int(score) or 0)


def place_text(place: Any) -> str:
    """Место в чемпионате словами: 1 → «1-е место», пусто → «место не указано»."""
    number = parse_int(place)
    if not number or number <= 0:
        return "место не указано"
    return f"{number}-е место"


def format_title(code: Any) -> str:
    """Формат работы потребности словами (раздел 5.3): remote → «удалённо»."""
    value = str(code or "").strip().lower()
    return VACANCY_FORMATS.get(value, value or "не указан")


def money(value: Any) -> str:
    """Сумма с разделением разрядов: 120000 → «120 000 ₽»."""
    number = parse_int(value)
    if number is None:
        return "—"
    return f"{number:,}".replace(",", "\u00a0") + "\u00a0₽"


def percent(value: Any) -> str:
    """Целое число процентов для шаблонов: 85 → «85%»."""
    number = parse_int(value)
    return "—" if number is None else f"{number}%"




