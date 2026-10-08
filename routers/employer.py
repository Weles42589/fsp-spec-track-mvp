"""Кабинет работодателя: потребности, банк кандидатов, приглашения, отклики.

Разделы ТЗ: 8 (видимость по тиру), 10.2 (потребности), 10.3 (ранжирование),
10.4 (приглашения), 13.6 (счётчик новых откликов), 14 (анкета и тир).
"""
from fastapi import APIRouter, Depends, Request
from sqlmodel import Session as DBSession

import auth
import helpers
import logic
import services
from database import get_db
from models import (STATUS_ACCEPTED, STATUS_REJECTED, Application, Candidate, Invitation,
                    Vacancy, utcnow)
from web import redirect, render

router = APIRouter(tags=["employer"])


@router.get("/employer")
def employer_home(request: Request, db: DBSession = Depends(get_db)):
    """Дашборд: тир, потребности, отклики, приглашения."""
    employer = auth.require_employer(request)
    new_count = helpers.new_applications_count(db, employer)
    applications = helpers.employer_applications(db, employer)
    applications.sort(key=lambda row: (not row["application"].is_new, -row["match"]["score"]))

    # визит отмечен: счётчик «новых» обнулится при следующем заходе
    employer.last_visit_at = utcnow()
    db.add(employer)
    db.commit()
    db.refresh(employer)

    return render(
        request, "employer_home.html", "Кабинет работодателя",
        employer=employer,
        tier_label=logic.tier_label(employer.tier),
        tier_description=logic.TIER_DESCRIPTIONS.get(employer.tier, ""),
        visible_fields=logic.TIER_FIELDS.get(employer.tier, []),
        vacancies=helpers.list_vacancies(db, employer.id),
        matches=helpers.match_rows(db, employer),
        applications=applications[:10],
        applications_total=len(applications),
        new_applications=new_count,
        invitations=helpers.employer_invitations(db, employer),
        bank_total=len([c for c in helpers.list_candidates(db) if logic.profile_complete(c)]),
    )


@router.get("/employer/survey")
def employer_survey_edit_page(request: Request):
    employer = auth.require_employer(request)
    return render(request, "employer_survey_edit.html", "Анкета процессов",
                  employer=employer, answers=employer.survey_answers or {},
                  tier_label=logic.tier_label(employer.tier))


@router.post("/employer/survey")
async def employer_survey_edit_submit(request: Request, db: DBSession = Depends(get_db)):
    """Изменение ответов мгновенно меняет тир и состав видимых полей (раздел 14)."""
    employer = auth.require_employer(request)
    form = await request.form()
    values = dict(form)
    errors = services.apply_employer_survey(employer, values)
    if errors:
        return render(request, "employer_survey_edit.html", "Анкета процессов",
                      employer=employer, answers=values, errors=errors,
                      tier_label=logic.tier_label(employer.tier))
    db.add(employer)
    db.commit()
    db.refresh(employer)
    return redirect("/employer",
                    f"Анкета обновлена: уровень организации процессов — "
                    f"{logic.tier_label(employer.tier)} (tier {employer.tier}). "
                    f"Видимые поля: {', '.join(logic.TIER_FIELDS.get(employer.tier, []))}",
                    "success")


# ---------------------------------------------------------------------------
# Потребности (раздел 10.2)
# ---------------------------------------------------------------------------

def _own_vacancy(db: DBSession, employer, vacancy_id: int) -> Vacancy:
    """Потребность должна принадлежать текущему работодателю."""
    from web import RedirectException

    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy or vacancy.employer_id != employer.id:
        raise RedirectException("/employer", "Потребность не найдена", "error")
    return vacancy


def vacancy_from_form(employer, values: dict):
    """Собрать потребность из формы. Возвращает (Vacancy, список ошибок)."""
    errors = []
    title = str(values.get("title", "")).strip()
    if not title:
        errors.append("Укажите должность")

    specialization = str(values.get("specialization", "")).strip()
    if specialization not in logic.SPECIALIZATIONS:
        errors.append("Выберите специализацию")

    grade = str(values.get("grade", "")).strip()
    if grade not in logic.GRADES:
        errors.append("Выберите грейд")

    grade_match = str(values.get("grade_match", "any")).strip()
    if grade_match not in logic.GRADE_MATCH_MODES:
        grade_match = "any"

    fmt = str(values.get("format", "")).strip()
    if fmt not in logic.VACANCY_FORMATS:
        errors.append("Выберите формат работы")

    salary_min = logic.parse_int(values.get("salary_min"))
    salary_max = logic.parse_int(values.get("salary_max"))
    salary_error = logic.salary_error(salary_min, salary_max)
    if salary_error:
        errors.append(salary_error)

    if errors:
        return None, errors

    vacancy = Vacancy(
        employer_id=employer.id,
        company=employer.company,
        title=title,
        specialization=specialization,
        grade=grade,
        grade_match=grade_match,
        stack=services.split_list(values.get("stack")),
        salary_min=salary_min,
        salary_max=salary_max,
        format=fmt,
        city=str(values.get("city", "")).strip(),
        team_size=str(values.get("team_size", "")).strip(),
        description=str(values.get("description", "")).strip(),
        open=bool(values.get("open")),
        is_new=True,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    return vacancy, []


@router.get("/employer/vacancies/new")
def vacancy_new_page(request: Request):
    employer = auth.require_employer(request)
    return render(request, "vacancy_form.html", "Новая потребность",
                  employer=employer, values={
                      "company": employer.company,
                      "city": employer.city,
                      "grade_match": "any",
                      "open": True,
                      "format": "remote",
                  }, errors=[])


@router.post("/employer/vacancies/new")
async def vacancy_create(request: Request, db: DBSession = Depends(get_db)):
    employer = auth.require_employer(request)
    form = await request.form()
    values = dict(form)
    vacancy, errors = vacancy_from_form(employer, values)
    if errors:
        return render(request, "vacancy_form.html", "Новая потребность",
                      employer=employer, values=values, errors=errors)

    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)
    return redirect(
        f"/employer/vacancies/{vacancy.id}",
        f"Потребность «{vacancy.title}» создана: "
        f"{logic.specialization_title(vacancy.specialization)}, "
        f"{logic.grade_title(vacancy.grade)} — ранжируем кандидатов",
        "success",
    )


@router.get("/employer/vacancies/{vacancy_id}")
def vacancy_detail_page(request: Request, vacancy_id: int, db: DBSession = Depends(get_db)):
    """Потребность + список кандидатов по убыванию релевантности с объяснением (раздел 10.3)."""
    employer = auth.require_employer(request)
    vacancy = _own_vacancy(db, employer, vacancy_id)
    rows = helpers.vacancy_candidates(db, employer, vacancy)
    restricted = [
        candidate for candidate in helpers.list_candidates(db)
        if logic.profile_complete(candidate)
        and logic.specialization_match(candidate.specialization, vacancy.specialization)
        and not logic.visibility_allows(candidate, employer)
    ]
    invited_ids = {
        invitation.candidate_id
        for invitation in helpers.list_invitations_for_employer(db, employer.id)
        if invitation.vacancy_id == vacancy.id
    }
    return render(
        request, "vacancy_detail.html", vacancy.title or "Потребность",
        employer=employer, vacancy=vacancy,
        card=helpers.vacancy_card(vacancy, employer),
        rows=rows,
        invited_ids=invited_ids,
        restricted_count=len(restricted),
        restricted_names=[logic.mask_name(candidate.name) for candidate in restricted[:5]],
        tier_label=logic.tier_label(employer.tier),
        visible_fields=logic.TIER_FIELDS.get(employer.tier, []),
    )


@router.post("/employer/vacancies/{vacancy_id}/toggle")
async def vacancy_toggle(request: Request, vacancy_id: int, db: DBSession = Depends(get_db)):
    """Опубликовать или скрыть потребность из банка."""
    employer = auth.require_employer(request)
    vacancy = _own_vacancy(db, employer, vacancy_id)
    vacancy.open = not vacancy.open
    vacancy.updated_at = utcnow()
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)
    state = "опубликована в банке" if vacancy.open else "скрыта из банка"
    return redirect(f"/employer/vacancies/{vacancy.id}", f"Потребность {state}", "success")


@router.post("/employer/vacancies/{vacancy_id}/delete")
async def vacancy_delete(request: Request, vacancy_id: int, db: DBSession = Depends(get_db)):
    employer = auth.require_employer(request)
    vacancy = _own_vacancy(db, employer, vacancy_id)
    title = vacancy.title
    db.delete(vacancy)
    db.commit()
    return redirect("/employer", f"Потребность «{title}» удалена", "success")


@router.post("/employer/vacancies/{vacancy_id}/invite")
async def vacancy_invite(request: Request, vacancy_id: int, db: DBSession = Depends(get_db)):
    """Приглашение кандидату (раздел 10.4). Доступно только по открытым профилям."""
    employer = auth.require_employer(request)
    vacancy = _own_vacancy(db, employer, vacancy_id)
    form = await request.form()
    candidate_id = logic.parse_int(form.get("candidate_id"))
    candidate = db.get(Candidate, candidate_id) if candidate_id else None
    back_url = f"/employer/vacancies/{vacancy.id}"

    if candidate is None:
        return redirect(back_url, "Кандидат не найден", "error")
    if not logic.profile_complete(candidate):
        return redirect(back_url, "Профиль кандидата неполный — приглашение недоступно", "error")
    if not logic.visibility_allows(candidate, employer):
        return redirect(back_url,
                        f"Профиль закрыт: {logic.restricted_reason(candidate)}", "error")

    existing = helpers.find_invitation(db, candidate.id, vacancy.id)
    if existing:
        return redirect(back_url,
                        f"Приглашение уже отправлено, статус: {logic.status_title(existing.status)}",
                        "success")

    message = str(form.get("message", "")).strip() or (
        f"Приглашаем на позицию «{vacancy.title}» в {employer.company}"
    )
    invitation = Invitation(
        employer_id=employer.id,
        candidate_id=candidate.id,
        vacancy_id=vacancy.id,
        message=message,
        salary_min=vacancy.salary_min,
        salary_max=vacancy.salary_max,
        status="sent",
        is_new=True,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    match = logic.score_match(candidate, vacancy)
    return redirect(
        back_url,
        f"Приглашение отправлено: {candidate.name}, {logic.specialization_title(candidate.specialization)}, "
        f"релевантность {match['score']}% ({match['summary']})",
        "success",
    )


# ---------------------------------------------------------------------------
# Банк кандидатов (разделы 8, 10.1)
# ---------------------------------------------------------------------------

@router.get("/employer/bank")
def bank_page(request: Request, db: DBSession = Depends(get_db), spec: str = ""):
    employer = auth.require_employer(request)
    candidates = [c for c in helpers.list_candidates(db) if logic.profile_complete(c)]
    if spec in logic.SPECIALIZATIONS:
        candidates = [c for c in candidates if logic.specialization_match(c.specialization, spec)]
    # амбициозные выше, затем по баллам ФСП (разделы 6.3, 9.2)
    candidates.sort(key=lambda c: (-int(logic.is_ambitious(c)), -c.fsp_score, c.name))

    rows = [{"card": helpers.candidate_card(c, employer.tier)} for c in candidates]
    open_count = len([row for row in rows if row["card"]["is_open"]])
    return render(
        request, "employer_bank.html", "Банк кандидатов",
        employer=employer, rows=rows, spec=spec,
        open_count=open_count,
        restricted_count=len(rows) - open_count,
        tier_label=logic.tier_label(employer.tier),
        visible_fields=logic.TIER_FIELDS.get(employer.tier, []),
    )


@router.get("/employer/candidates/{candidate_id}")
def candidate_detail_page(request: Request, candidate_id: int, db: DBSession = Depends(get_db)):
    """Профиль кандидата: состав полей зависит от тира работодателя (раздел 8)."""
    employer = auth.require_employer(request)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        return redirect("/employer/bank", "Кандидат не найден", "error")
    if not logic.profile_complete(candidate):
        return redirect("/employer/bank", "Профиль кандидата неполный и не участвует в подборе", "error")

    if not logic.visibility_allows(candidate, employer):
        return render(
            request, "employer_candidate_restricted.html", "Профиль закрыт",
            employer=employer, candidate_masked=logic.mask_name(candidate.name),
            specialization_title=logic.specialization_title(candidate.specialization),
            reason=logic.restricted_reason(candidate),
            tier_label=logic.tier_label(employer.tier),
        )

    profile = logic.candidate_visible_profile(candidate, employer.tier)
    return render(
        request, "employer_candidate_detail.html", profile["name"],
        employer=employer, candidate=candidate, profile=profile,
        full=helpers.candidate_full(candidate) if employer.tier == 3 else None,
        tier_label=logic.tier_label(employer.tier),
        visible_fields=logic.TIER_FIELDS.get(employer.tier, []),
        vacancies=helpers.list_vacancies(db, employer.id),
        red_flags=logic.red_flags(candidate),
    )


# ---------------------------------------------------------------------------
# Отклики и приглашения (разделы 10.3, 10.4, 13.6)
# ---------------------------------------------------------------------------

def _own_row(db: DBSession, employer, model, row_id: int, back_url: str):
    """Запись должна принадлежать текущему работодателю."""
    from web import RedirectException

    row = db.get(model, row_id)
    if not row or row.employer_id != employer.id:
        raise RedirectException(back_url, "Запись не найдена", "error")
    return row


@router.get("/employer/applications")
def applications_page(request: Request, db: DBSession = Depends(get_db)):
    employer = auth.require_employer(request)
    rows = helpers.employer_applications(db, employer)
    rows.sort(key=lambda row: row["match"]["score"], reverse=True)
    new_count = helpers.new_applications_count(db, employer)
    return render(
        request, "employer_applications.html", "Отклики кандидатов",
        employer=employer, rows=rows, new_count=new_count,
        accepted_count=len([row for row in rows if row["application"].status == STATUS_ACCEPTED]),
        rejected_count=len([row for row in rows if row["application"].status == STATUS_REJECTED]),
        pending_count=len([row for row in rows if row["application"].status not in
                           (STATUS_ACCEPTED, STATUS_REJECTED)]),
    )


@router.post("/employer/applications/{application_id}/status")
async def application_status(request: Request, application_id: int, db: DBSession = Depends(get_db)):
    """Принять или отклонить отклик — кандидат сразу видит статус (раздел 10.3)."""
    employer = auth.require_employer(request)
    application = _own_row(db, employer, Application, application_id, "/employer/applications")
    form = await request.form()
    status = str(form.get("status", "")).strip()
    if status not in (STATUS_ACCEPTED, STATUS_REJECTED):
        return redirect("/employer/applications", "Недопустимый статус отклика", "error")

    application.status = status
    application.is_new = False
    application.updated_at = utcnow()
    db.add(application)
    db.commit()
    db.refresh(application)

    text = ("Отклик принят — кандидат видит статус «принято»" if status == STATUS_ACCEPTED
            else "Отклик отклонён — кандидат видит статус «отклонено»")
    return redirect("/employer/applications", text, "success")


@router.get("/employer/invitations")
def invitations_page(request: Request, db: DBSession = Depends(get_db)):
    employer = auth.require_employer(request)
    rows = helpers.employer_invitations(db, employer)
    return render(
        request, "employer_invitations.html", "Отправленные приглашения",
        employer=employer, rows=rows,
        accepted_count=len([row for row in rows if row["invitation"].status == STATUS_ACCEPTED]),
        rejected_count=len([row for row in rows if row["invitation"].status == STATUS_REJECTED]),
        pending_count=len([row for row in rows if row["invitation"].status not in
                           (STATUS_ACCEPTED, STATUS_REJECTED)]),
    )


@router.post("/employer/invitations/{invitation_id}/status")
async def invitation_status(request: Request, invitation_id: int, db: DBSession = Depends(get_db)):
    """Работодатель может отозвать приглашение или отметить его принятым вручную."""
    employer = auth.require_employer(request)
    invitation = _own_row(db, employer, Invitation, invitation_id, "/employer/invitations")
    form = await request.form()
    status = str(form.get("status", "")).strip()
    if status not in (STATUS_ACCEPTED, STATUS_REJECTED):
        return redirect("/employer/invitations", "Недопустимый статус приглашения", "error")

    invitation.status = status
    invitation.updated_at = utcnow()
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return redirect("/employer/invitations",
                    f"Статус приглашения изменён на «{logic.status_title(status)}»", "success")
