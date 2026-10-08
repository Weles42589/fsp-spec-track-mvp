"""Кабинет кандидата: профиль, ФСП, КИТ, видимость, банк потребностей, отклики.

Разделы ТЗ: 8 (видимость), 9 (ФСП), 6.2 (КИТ), 10.5 (потребности), 13 (кабинет).
"""
from fastapi import APIRouter, Depends, Request
from sqlmodel import Session as DBSession

import auth
import helpers
import logic
import services
from database import get_db
from models import (STATUS_ACCEPTED, STATUS_REJECTED, STATUS_VIEWED, Application,
                    Invitation, Vacancy, utcnow)
from web import redirect, render

router = APIRouter(tags=["candidate"])


@router.get("/candidate")
def candidate_home(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    invitations = helpers.candidate_invitations(db, candidate)
    applications = helpers.candidate_applications(db, candidate)
    return render(
        request, "candidate_home.html", "Кабинет кандидата",
        candidate=candidate,
        full=helpers.candidate_full(candidate),
        fsp=helpers.fsp_block(candidate),
        kit=helpers.kit_block(candidate),
        invitations=invitations,
        applications=applications,
        new_invitations=len([row for row in invitations if row["invitation"].is_new]),
        needs_count=len([v for v in helpers.list_vacancies(db) if v.open]),
    )


@router.get("/candidate/edit")
def candidate_edit_page(request: Request):
    candidate = auth.require_candidate(request)
    return render(request, "candidate_edit.html", "Редактирование профиля",
                  candidate=candidate, values={
                      "name": candidate.name,
                      "city": candidate.city,
                      "team_role": candidate.team_role,
                      "work_format": candidate.work_format,
                      "stack": ", ".join(candidate.stack or []),
                      "fsp_role": candidate.fsp_role,
                      "ambitions": candidate.ambitions or [],
                      "specialization": candidate.specialization,
                  })


@router.post("/candidate/edit")
async def candidate_edit_submit(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    form = await request.form()
    values = dict(form)
    values["ambitions"] = form.getlist("ambitions")
    values["consent"] = candidate.consent or form.get("consent")
    # видимость в банке переключается отдельной формой /candidate/visibility (раздел 8.4):
    # здесь сохраняем текущее состояние, иначе сохранение анкеты раскрыло бы скрытый профиль
    values["visible_in_bank"] = candidate.visible_in_bank

    errors = services.apply_candidate_profile(candidate, values)
    if errors:
        return render(request, "candidate_edit.html", "Редактирование профиля",
                      candidate=candidate, values=values, errors=errors)

    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return redirect("/candidate",
                    "Профиль обновлён — пересчитаны грейд, категория и видимость", "success")


@router.post("/candidate/visibility")
async def candidate_visibility_submit(request: Request, db: DBSession = Depends(get_db)):
    """Переключить видимость в банке (раздел 8.4)."""
    candidate = auth.require_candidate(request)
    form = await request.form()
    candidate.visible_in_bank = str(form.get("visible_in_bank", "")) == "on"
    candidate.updated_at = utcnow()
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    state = "виден работодателям" if candidate.visible_in_bank else "скрыт из банка"
    return redirect("/candidate", f"Профиль {state}", "success")


@router.post("/candidate/fsp/connect")
async def candidate_fsp_connect(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    result = services.connect_fsp(candidate)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    if result["has_history"]:
        message = (f"ФСП подключён: {result['score']} баллов, категория {result['category']} "
                   f"({result['category_title']})")
    else:
        message = "История в реестре ФСП не найдена: 0 баллов, категория D"
    return redirect("/candidate", message, "success")


@router.post("/candidate/fsp/disconnect")
async def candidate_fsp_disconnect(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    services.disconnect_fsp(candidate)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return redirect("/candidate", "История ФСП отключена, баллы обнулены", "success")


@router.post("/candidate/kit")
async def candidate_kit_upload(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    form = await request.form()
    upload = form.get("kit_file")
    filename = getattr(upload, "filename", "") or ""
    if not filename:
        return redirect("/candidate", "Выберите файл сертификата (PDF или TXT)", "error")

    raw = await upload.read()
    parsed = services.parse_kit_upload(filename, raw)
    if parsed["error"]:
        return redirect("/candidate", f"Не удалось разобрать сертификат: {parsed['error']}", "error")

    source = "pdf" if filename.lower().endswith(".pdf") else "text"
    parsed = services.apply_kit(candidate, parsed, source)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return redirect(
        "/candidate",
        f"Сертификат обновлён: {parsed['competition']}, {parsed['place_text']}. "
        f"Грейд: {logic.grade_title(parsed['resolved_grade'])}",
        "success",
    )


@router.post("/candidate/kit/remove")
async def candidate_kit_remove(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    services.remove_kit(candidate)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return redirect("/candidate", "Сертификат КИТ удалён, грейд пересчитан по барометру", "success")


# ---------------------------------------------------------------------------
# Банк потребностей и отклики (разделы 10.5, 10.6, 14)
# ---------------------------------------------------------------------------

@router.get("/needs")
def needs_page(request: Request, db: DBSession = Depends(get_db)):
    """Список открытых потребностей, отсортированный по релевантности кандидату."""
    candidate = auth.require_candidate(request)
    rows = []
    for vacancy in helpers.list_vacancies(db):
        if not vacancy.open:
            continue
        employer = helpers.employer_by_id(db, vacancy.employer_id)
        match = logic.score_match(candidate, vacancy)
        rows.append({
            "card": helpers.vacancy_card(vacancy, employer, viewer=candidate, match=match),
            "match": match,
            "employer": employer,
            "applied": helpers.find_application(db, candidate.id, vacancy.id) is not None,
        })
    rows.sort(key=lambda row: (-row["match"]["score"], row["card"]["title"]))
    return render(request, "needs.html", "Банк потребностей",
                  candidate=candidate, rows=rows,
                  specialization_title=logic.specialization_title(candidate.specialization),
                  grade_title=logic.grade_title(logic.resolve_grade(
                      candidate.kit_grade, candidate.kit_certificate_number,
                      candidate.ambitions)["grade"]))


@router.get("/needs/{vacancy_id}")
def need_detail_page(request: Request, vacancy_id: int, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy or not vacancy.open:
        return redirect("/needs", "Потребность не найдена или снята с публикации", "error")
    employer = helpers.employer_by_id(db, vacancy.employer_id)
    match = logic.score_match(candidate, vacancy)
    return render(request, "need_detail.html", vacancy.title or "Потребность",
                  candidate=candidate, employer=employer, match=match,
                  card=helpers.vacancy_card(vacancy, employer, viewer=candidate, match=match),
                  application=helpers.find_application(db, candidate.id, vacancy.id),
                  profile_complete=logic.profile_complete(candidate))


@router.post("/needs/{vacancy_id}/apply")
async def need_apply(request: Request, vacancy_id: int, db: DBSession = Depends(get_db)):
    """Отклик кандидата на потребность."""
    candidate = auth.require_candidate(request)
    vacancy = db.get(Vacancy, vacancy_id)
    if not vacancy or not vacancy.open:
        return redirect("/needs", "Потребность не найдена или снята с публикации", "error")
    if not logic.profile_complete(candidate):
        return redirect("/candidate",
                        "Откликнуться можно только с заполненным профилем: роль, формат работы, "
                        "специализация и согласие на обработку данных", "error")
    if helpers.find_application(db, candidate.id, vacancy.id):
        return redirect(f"/needs/{vacancy.id}", "Вы уже откликнулись на эту потребность", "success")

    form = await request.form()
    application = Application(
        candidate_id=candidate.id,
        employer_id=vacancy.employer_id,
        vacancy_id=vacancy.id,
        message=str(form.get("message", "")).strip(),
        status="sent",
        is_new=True,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return redirect(f"/needs/{vacancy.id}",
                    f"Отклик отправлен в «{vacancy.company}». Статус виден в кабинете", "success")


@router.get("/candidate/applications")
def applications_page(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    rows = helpers.candidate_applications(db, candidate)
    rows.sort(key=lambda row: row["application"].created_at or "", reverse=True)
    return render(request, "candidate_applications.html", "Мои отклики",
                  candidate=candidate, rows=rows)


# ---------------------------------------------------------------------------
# Приглашения (разделы 10.4, 13.3)
# ---------------------------------------------------------------------------

def _own_invitation(db: DBSession, candidate, invitation_id: int) -> Invitation:
    """Приглашение должно существовать и принадлежать текущему кандидату."""
    from web import RedirectException

    invitation = db.get(Invitation, invitation_id)
    if not invitation or invitation.candidate_id != candidate.id:
        raise RedirectException("/candidate/invitations", "Приглашение не найдено", "error")
    return invitation


@router.get("/candidate/invitations")
def invitations_page(request: Request, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    rows = helpers.candidate_invitations(db, candidate)
    # новые — сверху, дальше по убыванию релевантности (раздел 10.3)
    rows.sort(key=lambda row: (not row["invitation"].is_new, -row["match"]["score"]))
    return render(request, "candidate_invitations.html", "Приглашения",
                  candidate=candidate, rows=rows,
                  new_count=len([row for row in rows if row["invitation"].is_new]))


@router.get("/candidate/invitations/{invitation_id}")
def invitation_detail_page(request: Request, invitation_id: int, db: DBSession = Depends(get_db)):
    """Открытие приглашения переводит статус sent → viewed (раздел 10.4)."""
    candidate = auth.require_candidate(request)
    invitation = _own_invitation(db, candidate, invitation_id)
    if invitation.status == "sent":
        invitation.status = STATUS_VIEWED
    invitation.is_new = False
    invitation.updated_at = utcnow()
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    vacancy = db.get(Vacancy, invitation.vacancy_id) if invitation.vacancy_id else None
    employer = helpers.employer_by_id(db, invitation.employer_id)
    match = logic.score_match(candidate, vacancy) if vacancy else None
    card = helpers.vacancy_card(vacancy, employer, viewer=candidate, match=match) if vacancy else None
    return render(request, "candidate_invitation_detail.html", "Приглашение",
                  candidate=candidate, invitation=invitation, vacancy=card, match=match,
                  employer=employer,
                  salary_note=logic.salary_note(invitation.salary_min, invitation.salary_max))


@router.post("/candidate/invitations/{invitation_id}/accept")
async def invitation_accept(request: Request, invitation_id: int, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    invitation = _own_invitation(db, candidate, invitation_id)
    invitation.status = STATUS_ACCEPTED
    invitation.is_new = False
    invitation.updated_at = utcnow()
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return redirect("/candidate/invitations",
                    "Приглашение принято — работодатель видит статус «принято»", "success")


@router.post("/candidate/invitations/{invitation_id}/reject")
async def invitation_reject(request: Request, invitation_id: int, db: DBSession = Depends(get_db)):
    candidate = auth.require_candidate(request)
    invitation = _own_invitation(db, candidate, invitation_id)
    invitation.status = STATUS_REJECTED
    invitation.is_new = False
    invitation.updated_at = utcnow()
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return redirect("/candidate/invitations",
                    "Приглашение отклонено — работодатель видит статус «отклонено»", "success")
