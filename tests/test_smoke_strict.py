"""Рендер всех GET-страниц при Jinja2 StrictUndefined.

Перенос /tmp/smoke_strict.py в pytest. Смысл проверки: в шаблонах не осталось
переменных, которые маршруты забывают передать в контекст. При обычном
``Undefined`` такой шаблон молча рендерит пустую строку, а при ``StrictUndefined``
падает — поэтому свип идёт в строгом режиме.

Дополнительно проверяется страница закрытого профиля
(``/employer/candidates/{id}`` для кандидата, скрытого из банка): она рендерится
отдельным шаблоном ``employer_candidate_restricted.html`` и в обычный свип
по параметрам маршрута не попадает.
"""
from __future__ import annotations

import pytest
from jinja2 import UndefinedError

from conftest import all_get_paths, fill_path

# Минимум страниц с кодом 200 для каждой роли: ниже этого числа свип считается
# проваленным (значит, часть страниц начала редиректить или падать).
MINIMUM_RENDERED = {"anon": 2, "candidate": 8, "employer": 9}


def test_strict_undefined_is_active(strict_templates):
    """Санити-чек фикстуры: строгий режим действительно включён."""
    with pytest.raises(UndefinedError):
        strict_templates.from_string("{{ missing_variable }}").render()


@pytest.mark.parametrize("identity", ["anon", "candidate", "employer"])
def test_pages_render_under_strict_undefined(client, seed, identities,
                                             strict_templates, identity):
    """Ни одна страница под выбранной ролью не падает в строгом режиме."""
    token = dict((label, value) for label, value in identities)[identity]
    targets = [(path, fill_path(path, seed["ids"])) for path in all_get_paths()]
    # закрытый профиль: отдельный шаблон, добираем вручную
    targets.append(("/employer/candidates/{candidate_id}",
                    "/employer/candidates/%d" % seed["hidden_id"]))

    rendered = 0
    problems = []
    for path, url in targets:
        client.cookies.clear()
        if token:
            client.cookies.set("fsp_session", token)
        try:
            response = client.get(url)
        except Exception as exc:  # noqa: BLE001 - UndefinedError приходит сюда
            problems.append(f"{identity} {url} [{path}]: {type(exc).__name__}: "
                            f"{str(exc).splitlines()[0]}")
            continue
        if response.status_code == 200:
            rendered += 1
        elif response.status_code >= 400:
            problems.append(f"{identity} {url} [{path}] → HTTP {response.status_code}")

    assert not problems, "\n".join(problems)
    assert rendered >= MINIMUM_RENDERED[identity], (identity, rendered)


def test_restricted_profile_page_renders(client, seed, strict_templates):
    """Страница закрытого профиля рендерится и объясняет ограничение доступа."""
    token = seed["tokens"]["employer"]
    client.cookies.set("fsp_session", token)
    response = client.get("/employer/candidates/%d" % seed["hidden_id"])
    assert response.status_code == 200
    for needle in ("Профиль закрыт", "Доступ ограничен", "Приглашение недоступно"):
        assert needle in response.text, needle


def test_open_profile_page_renders(client, seed, strict_templates):
    """Страница открытого профиля: КИТ, история ФСП, барометр и кнопка приглашения."""
    client.cookies.set("fsp_session", seed["tokens"]["employer"])
    response = client.get("/employer/candidates/%d" % seed["verified_id"])
    assert response.status_code == 200
    for needle in ("Сертификат КИТ", "История ФСП", "Барометр амбиций", "Пригласить"):
        assert needle in response.text, needle
