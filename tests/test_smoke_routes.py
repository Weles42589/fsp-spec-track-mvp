"""Свип по всем GET-маршрутам: 5xx, исключения и дыры в разграничении доступа.

Перенос /tmp/smoke_all.py в pytest. Проверяется:
  * все шаблоны компилируются (включая парциалы);
  * ни один GET-маршрут не падает с 5xx и не бросает исключение — ни под одной ролью;
  * аноним не попадает в приватные разделы (303 на /login);
  * кандидат и работодатель не видят чужие кабинеты (303, а не 200);
  * /health и лендинг отвечают 200.
"""
from __future__ import annotations

import pathlib

import pytest

import web
from conftest import all_get_paths, fill_path

# Публичные страницы: доступны без сессии (раздел 12.3 ТЗ).
PUBLIC_PREFIXES = ("/", "/health", "/login", "/verify", "/logout", "/register")

# Ожидаемые коды: 200 — страница, 303 — guard-редирект, 404 — объект не найден.
ALLOWED_CODES = {200, 303, 404}

# Ключевые шаблоны: страницы обоих кабинетов и все парциалы.
KEY_TEMPLATES = [
    "base.html", "index.html", "login.html", "verify.html",
    "register_candidate_profile.html", "register_candidate_fsp.html",
    "register_candidate_kit.html", "register_employer_profile.html",
    "register_employer_survey.html",
    "candidate_home.html", "candidate_edit.html", "candidate_applications.html",
    "candidate_invitations.html", "candidate_invitation_detail.html",
    "needs.html", "need_detail.html",
    "employer_home.html", "employer_survey_edit.html", "employer_bank.html",
    "employer_candidate_detail.html", "employer_candidate_restricted.html",
    "employer_applications.html", "employer_invitations.html",
    "vacancy_detail.html", "vacancy_form.html",
    "_partial_candidate_card.html", "_partial_match.html",
    "_partial_profile_form.html", "_partial_survey_form.html",
    "_partial_vacancy_card.html",
]


def is_public(path: str) -> bool:
    """Путь доступен без сессии (лендинг и шаги входа/регистрации)."""
    return path == "/" or path.startswith(PUBLIC_PREFIXES[1:])


@pytest.mark.parametrize("template", KEY_TEMPLATES)
def test_template_compiles(template):
    """Каждый ключевой шаблон существует и компилируется."""
    assert (pathlib.Path("templates") / template).is_file(), template
    web.templates.env.get_template(template)


def test_all_templates_compile():
    """Полный обход templates/: компиляция без ошибок, список не пуст."""
    names = sorted(p.name for p in pathlib.Path("templates").glob("*.html"))
    assert len(names) >= len(KEY_TEMPLATES), names
    assert set(KEY_TEMPLATES) <= set(names), set(KEY_TEMPLATES) - set(names)
    broken = {}
    for name in names:
        try:
            web.templates.env.get_template(name)
        except Exception as exc:  # noqa: BLE001 - собираем все ошибки в один отчёт
            broken[name] = f"{type(exc).__name__}: {exc}"
    assert not broken, broken



@pytest.mark.parametrize("identity", ["anon", "candidate", "employer"])
def test_get_paths_have_no_server_errors(client, seed, identity):
    """Свип всех GET-путей под выбранной ролью: без 5xx и без исключений."""
    token = {"anon": None,
             "candidate": seed["tokens"]["candidate"],
             "employer": seed["tokens"]["employer"]}[identity]
    paths = all_get_paths()
    assert paths, "OpenAPI-схема пуста"
    failures = []
    for path in paths:
        url = fill_path(path, seed["ids"])
        client.cookies.clear()
        if token:
            client.cookies.set("fsp_session", token)
        try:
            response = client.get(url)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"EXC {identity} {url}: {type(exc).__name__}: {exc}")
            continue
        if response.status_code not in ALLOWED_CODES:
            failures.append(f"HTTP {response.status_code} {identity} {url} [{path}]")
    assert not failures, "\n".join(failures)
    assert len(paths) >= 20, paths


def test_anonymous_redirected_to_login(client, seed):
    """Аноним на любом приватном пути получает 303 на /login."""
    checked = 0
    failures = []
    for path in all_get_paths():
        if is_public(path):
            continue
        client.cookies.clear()
        response = client.get(fill_path(path, seed["ids"]))
        checked += 1
        location = response.headers.get("location", "")
        if response.status_code != 303 or not location.startswith("/login"):
            failures.append(f"{path} → {response.status_code} {location!r}")
    assert checked >= 10, checked
    assert not failures, "\n".join(failures)


def test_role_isolation(client, seed):
    """Кандидат не видит /employer*, работодатель не видит /candidate* и /needs*."""
    failures = []
    cases = [
        ("candidate", seed["tokens"]["candidate"], ("/employer",)),
        ("employer", seed["tokens"]["employer"], ("/candidate", "/needs")),
    ]
    for label, token, blocked in cases:
        for path in all_get_paths():
            if not path.startswith(blocked):
                continue
            client.cookies.clear()
            client.cookies.set("fsp_session", token)
            response = client.get(fill_path(path, seed["ids"]))
            if response.status_code == 200:
                failures.append(f"{label} получил 200 на {path}")
            elif response.status_code not in ALLOWED_CODES:
                failures.append(f"{label} на {path} → {response.status_code}")
    assert not failures, "\n".join(failures)


def test_health_and_landing(client):
    """/health — JSON для стенда, / — лендинг 200."""
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    landing = client.get("/")
    assert landing.status_code == 200
    assert "ФСП" in landing.text
