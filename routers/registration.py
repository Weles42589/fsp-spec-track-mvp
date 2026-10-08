"""Пошаговая регистрация: кандидат (3 шага) и работодатель (2 шага). Раздел 7 ТЗ."""
from fastapi import APIRouter, Depends, Request
from sqlmodel import Session as DBSession

import auth
import fsp_mock
import helpers
import logic
import services
from content import CANDIDATE_STEPS, EMPLOYER_STEPS
from database import get_db
from models import Candidate, Employer
from web import redirect, render

router = APIRouter(tags=["registration"])


# ---------------------------------------------------------------------------
# Кандидат: шаг 1 — профиль и барометр амбиций
# ---------------------------------------------------------------------------

@router.get("/register/candidate")
def candidate_profile_page(request: Request):
    principal = auth.require_new_user(request, "candidate")
    return render(request, "register_candidate_profile.html", "Анкета кандидата — шаг 1",
                  step=1, steps=CANDIDATE_STEPS, email=principal.session.email, values={})


@router.post("/register/candidate")
async def candidate_profile_submit(request: Request, db: DBSession = Depends(get_db)):
    principal = auth.require_new_user(request, "candidate")
    form = await request.form()
    values = dict(form)
    values["ambitions"] = form.getlist("ambitions")

    candidate = Candidate(email=principal.session.email)
    errors = services.apply_candidate_profile(candidate, values)
    if errors:
        return render(request, "register_candidate_profile.html", "Анкета кандидата — шаг 1",
                      step=1, steps=CANDIDATE_STEPS, email=principal.session.email,
                      values=values, errors=errors)

    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    auth.bind_session_user(db, principal, candidate)
    specialization = logic.specialization_title(candidate.specialization)
    return redirect(
        "/register/candidate/fsp",
        f"Профиль сохранён: {specialization}, грейд {logic.grade_title(candidate.grade_override)}. "
        "Дальше — история ФСП",
        "success",
    )


# ---------------------------------------------------------------------------
# Кандидат: шаг 2 — история ФСП
# ---------------------------------------------------------------------------

@router.get("/register/candidate/fsp")
def candidate_fsp_page(request: Request):
    candidate = auth.require_candidate(request)
    return render(request, "register_candidate_fsp.html", "История ФСП — шаг 2",
                  step=2, steps=CANDIDATE_STEPS, candidate=candidate,
                  fsp=helpers.fsp_block(candidate),
                  preview=fsp_mock.get_achievements(candidate.email),
                  demo_emails=sorted(fsp_mock.FSP_REGISTRY))


@router.post("/register/candidate/fsp")
async def candidate_fsp_submit(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    form = await request.form()
    action = str(form.get("action", "connect"))

    if action == "skip":
        return redirect("/register/candidate/kit",
                        "Шаг ФСП пропущен — подключение доступно позже в кабинете", "success")

    result = services.connect_fsp(candidate)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    if result["has_history"]:
        message = (f"ФСП подключён: {result['score']} баллов, категория {result['category']} "
                   f"({result['category_title']})")
    else:
        message = ("История в реестре ФСП не найдена: 0 баллов, категория D. "
                   "Профиль остаётся в банке — это нормальный сценарий")
    return redirect("/register/candidate/kit", message, "success")


# ---------------------------------------------------------------------------
# Кандидат: шаг 3 — сертификат КИТ
# ---------------------------------------------------------------------------

@router.get("/register/candidate/kit")
def candidate_kit_page(request: Request):
    candidate = auth.require_candidate(request)
    return render(request, "register_candidate_kit.html", "Сертификат КИТ — шаг 3",
                  step=3, steps=CANDIDATE_STEPS, candidate=candidate,
                  kit=helpers.kit_block(candidate))


@router.post("/register/candidate/kit")
async def candidate_kit_submit(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    form = await request.form()

    if str(form.get("action", "")) == "skip":
        return redirect("/candidate",
                        "Регистрация завершена. Сертификат КИТ можно добавить позже", "success")

    upload = form.get("kit_file")
    filename = getattr(upload, "filename", "") or ""
    errors = []
    if not filename:
        errors.append("Выберите файл сертификата (PDF или TXT)")
    parsed = None
    if not errors:
        raw = await upload.read()
        parsed = services.parse_kit_upload(filename, raw)
        if parsed["error"]:
            errors.append(parsed["error"])
            errors.append("Проверьте файл: нужен сертификат КИТ в PDF или его текстовая копия")

    if errors:
        return render(request, "register_candidate_kit.html", "Сертификат КИТ — шаг 3",
                      step=3, steps=CANDIDATE_STEPS, candidate=candidate,
                      kit=helpers.kit_block(candidate), errors=errors)

    source = "pdf" if filename.lower().endswith(".pdf") else "text"
    parsed = services.apply_kit(candidate, parsed, source)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return redirect(
        "/candidate",
        f"Сертификат КИТ загружен: {parsed['competition']}, место {parsed['place']} "
        f"({parsed['place_text']}). Грейд: {logic.grade_title(parsed['resolved_grade'])}",
        "success",
    )


# ---------------------------------------------------------------------------
# Работодатель: шаг 1 — данные компании
# ---------------------------------------------------------------------------

@router.get("/register/employer")
def employer_profile_page(request: Request):
    principal = auth.require_new_user(request, "employer")
    return render(request, "register_employer_profile.html", "Анкета работодателя — шаг 1",
                  step=1, steps=EMPLOYER_STEPS, email=principal.session.email, values={})


@router.post("/register/employer")
async def employer_profile_submit(request: Request, db: DBSession = Depends(get_db)):
    principal = auth.require_new_user(request, "employer")
    form = await request.form()
    values = dict(form)

    employer = Employer(email=principal.session.email)
    errors = services.apply_employer_profile(employer, values)
    if errors:
        return render(request, "register_employer_profile.html", "Анкета работодателя — шаг 1",
                      step=1, steps=EMPLOYER_STEPS, email=principal.session.email,
                      values=values, errors=errors)

    db.add(employer)
    db.commit()
    db.refresh(employer)
    auth.bind_session_user(db, principal, employer)
    return redirect("/register/employer/survey",
                    f"Компания «{employer.company}» добавлена. Осталась анкета из 6 вопросов",
                    "success")


# ---------------------------------------------------------------------------
# Работодатель: шаг 2 — анкета процессов (6 вопросов → тир)
# ---------------------------------------------------------------------------

@router.get("/register/employer/survey")
def employer_survey_page(request: Request):
    principal = auth.require_principal(request, "employer")
    employer = principal.employer
    if employer is None:
        raise_auth_redirect()
    return render(request, "register_employer_survey.html", "Анкета процессов — шаг 2",
                  step=2, steps=EMPLOYER_STEPS, employer=employer,
                  answers=employer.survey_answers or {})


@router.post("/register/employer/survey")
async def employer_survey_submit(request: Request, db: DBSession = Depends(get_db)):
    principal = auth.require_principal(request, "employer")
    employer = principal.employer
    if employer is None:
        raise_auth_redirect()

    form = await request.form()
    values = dict(form)
    errors = services.apply_employer_survey(employer, values)
    if errors:
        return render(request, "register_employer_survey.html", "Анкета процессов — шаг 2",
                      step=2, steps=EMPLOYER_STEPS, employer=employer,
                      answers=values, errors=errors)

    db.add(employer)
    db.commit()
    db.refresh(employer)
    return redirect(
        "/employer",
        f"Анкета заполнена: ваш уровень организации процессов — {logic.tier_label(employer.tier)} "
        f"(tier {employer.tier}). Он определяет, какие поля кандидатов вы видите",
        "success",
    )


def raise_auth_redirect():
    """Профиль компании не найден — вернуть на шаг 1 регистрации."""
    from web import RedirectException

    raise RedirectException("/register/employer", "Сначала заполните данные компании", "error")
