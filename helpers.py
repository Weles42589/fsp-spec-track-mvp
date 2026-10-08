"""Общие сборки данных для страниц: карточки, матрица видимости, подсказки.

Всё, что связано с разграничением доступа по тиру работодателя (раздел 8),
проходит через этот модуль — маршруты сами поля не фильтруют.
"""
from typing import Any, Dict, List, Optional

from sqlmodel import Session as DBSession
from sqlmodel import select

import fsp_mock
import logic
from employer_rating import company_rating
from models import Application, Candidate, Employer, Invitation, Vacancy


def grade_from_candidate(candidate: Candidate) -> str:
    """Итоговый грейд кандидата: КИТ → ручной выбор → барометр → junior (раздел 6.2)."""
    return logic.resolve_grade_for(candidate)["grade"]


def fsp_block(candidate: Candidate) -> Dict[str, Any]:
    """Блок ФСП: подключение, баллы, категория, достижения."""
    achievements = fsp_mock.get_achievements(candidate.email).get("achievements", [])
    score = fsp_mock.compute_fsp_score(achievements)
    category = logic.category_from_score(score)
    return {
        "connected": candidate.fsp_connected,
        "has_history": bool(achievements),
        "score": score,
        "category": category,
        "category_title": logic.category_title(category),
        "achievements": achievements,
        "disciplines": fsp_mock.disciplines(achievements),
        "best_role": fsp_mock.best_role(achievements),
    }


def kit_block(candidate: Candidate) -> Dict[str, Any]:
    """Блок КИТ: сертификат, место, состав, грейд из сертификата."""
    grade = logic.resolve_grade_for(candidate)
    return {
        "connected": candidate.kit_connected,
        "certificate_number": candidate.kit_certificate_number,
        "competition": candidate.kit_competition,
        "place": candidate.kit_place,
        "place_text": logic.place_text(candidate.kit_place),
        "team": candidate.kit_team or [],
        "grade_from_certificate": candidate.kit_grade,
        "grade": grade["grade"],
        "grade_note": grade["note"],
        "raw": candidate.kit_raw or "",
    }


def candidate_full(candidate: Candidate) -> Dict[str, Any]:
    """Полный профиль: виден самому кандидату и работодателю tier 3."""
    resolved = logic.resolve_specialization(candidate)
    grade = logic.resolve_grade_for(candidate)
    return {
        "profile": logic.candidate_visible_profile(candidate, tier=3),
        "specialization_source": resolved["source"],
        "specialization_source_label": resolved["source_label"],
        "specialization_note": resolved["note"],
        "grade": grade["grade"],
        "grade_title": logic.grade_title(grade["grade"]),
        "grade_note": grade["note"],
        "grade_source": grade["grade_source"],
        "ambitions": candidate.ambitions or [],
        "ambitions_labels": logic.ambitions_labels(candidate.ambitions or []),
        "ambitions_flags": len(logic.ambitions_flags(candidate)),
        "ambitions_note": logic.ambitions_note(candidate),
        "is_ambitious": logic.is_ambitious(candidate),
        "profile_complete": logic.profile_complete(candidate),
        "profile_level": logic.profile_level(candidate),
        "red_flags": logic.red_flags(candidate),
        "fsp": fsp_block(candidate),
        "kit": kit_block(candidate),
        "fsp_demo": candidate.fsp_demo,
    }


def candidate_card(candidate: Candidate, viewer_tier: Optional[int]) -> Dict[str, Any]:
    """Карточка в банке: поля отфильтрованы по тиру смотрящего (раздел 8)."""
    profile = logic.candidate_visible_profile(candidate, viewer_tier)
    full = candidate_full(candidate) if profile["is_open"] and viewer_tier == 3 else None
    return {
        "id": candidate.id,
        "profile": profile,
        "full": full,
        "is_open": profile["is_open"],
        "is_restricted": profile["is_restricted"],
        "visibility_note": profile["visibility_note"],
        "restricted_reason": logic.restricted_reason(candidate),
        "profile_complete": logic.profile_complete(candidate),
        "profile_level": logic.profile_level(candidate),
        "specialization_title": logic.specialization_title(candidate.specialization),
        "grade_title": logic.grade_title(grade_from_candidate(candidate)),
        "fsp_category": candidate.fsp_category,
        "fsp_connected": candidate.fsp_connected,
        "kit_connected": candidate.kit_connected,
        "name": candidate.name,
        "city": candidate.city,
        "email": candidate.email,
        "team_role": candidate.team_role,
    }


def employer_by_id(db: DBSession, employer_id: Optional[int]) -> Optional[Employer]:
    if not employer_id:
        return None
    return db.get(Employer, employer_id)


def vacancy_card(vacancy: Vacancy, employer: Optional[Employer] = None,
                 viewer: Optional[Candidate] = None,
                 match: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Карточка потребности. Рейтинг компании добавляется только для кандидата (раздел 14)."""
    card: Dict[str, Any] = {
        "id": vacancy.id,
        "employer_id": vacancy.employer_id,
        "title": vacancy.title,
        "company": vacancy.company,
        "specialization": vacancy.specialization,
        "specialization_title": logic.specialization_title(vacancy.specialization),
        "grade": vacancy.grade,
        "grade_title": logic.grade_title(vacancy.grade),
        "grade_match": vacancy.grade_match,
        "grade_note": logic.grade_match_note(vacancy.grade, vacancy.grade_match),
        "stack": vacancy.stack or [],
        "stack_note": logic.stack_note(vacancy.stack or [], vacancy.title or ""),
        "salary_min": vacancy.salary_min,
        "salary_max": vacancy.salary_max,
        "salary_note": logic.salary_note(vacancy.salary_min, vacancy.salary_max),
        "format": vacancy.format,
        "city": vacancy.city,
        "team_size": vacancy.team_size,
        "description": vacancy.description,
        "open": vacancy.open,
        "is_new": bool(vacancy.is_new),
        "match": match,
    }
    if viewer is not None:
        card["company_rating"] = company_rating(vacancy.company, employer.tier if employer else None)
    return card


def match_rows(db: DBSession, employer: Employer,
               candidates: Optional[List[Candidate]] = None) -> List[Dict[str, Any]]:
    """Пары «потребность ↔ кандидат» в порядке убывания релевантности (раздел 10)."""
    all_candidates = candidates if candidates is not None else list_candidates(db)
    rows: List[Dict[str, Any]] = []
    for vacancy in list_vacancies(db, employer.id):
        ranked = logic.rank_candidates(all_candidates, vacancy, tier=employer.tier)
        items = [
            {
                "candidate": candidate_card(candidate, employer.tier),
                "match": match,
                "candidate_id": candidate.id,
            }
            for candidate, match in ranked
        ]
        restricted = [
            candidate for candidate in all_candidates
            if logic.profile_complete(candidate)
            and logic.specialization_match(candidate.specialization, vacancy.specialization)
            and not logic.visibility_allows(candidate, employer)
        ]
        rows.append({
            "vacancy": vacancy,
            "items": items,
            "open_count": len(items),
            "restricted_count": len(restricted),
            "restricted_names": [logic.mask_name(candidate.name) for candidate in restricted[:5]],
        })
    return rows


def candidate_invitations(db: DBSession, candidate: Candidate) -> List[Dict[str, Any]]:
    rows = []
    for invitation in list_invitations_for_candidate(db, candidate.id):
        vacancy = db.get(Vacancy, invitation.vacancy_id)
        if not vacancy:
            continue
        employer = employer_by_id(db, vacancy.employer_id)
        match = logic.score_match(candidate, vacancy)
        rows.append({
            "invitation": invitation,
            "vacancy": vacancy_card(vacancy, employer, viewer=candidate, match=match),
            "match": match,
            "employer": employer,
        })
    return rows


def candidate_applications(db: DBSession, candidate: Candidate) -> List[Dict[str, Any]]:
    rows = []
    for application in list_applications_for_candidate(db, candidate.id):
        vacancy = db.get(Vacancy, application.vacancy_id)
        if not vacancy:
            continue
        employer = employer_by_id(db, vacancy.employer_id)
        rows.append({
            "application": application,
            "vacancy": vacancy_card(vacancy, employer, viewer=candidate),
            "employer": employer,
        })
    return rows


def employer_applications(db: DBSession, employer: Employer) -> List[Dict[str, Any]]:
    rows = []
    for application in list_applications_for_employer(db, employer.id):
        candidate = db.get(Candidate, application.candidate_id)
        vacancy = db.get(Vacancy, application.vacancy_id)
        if not candidate or not vacancy:
            continue
        rows.append({
            "application": application,
            "candidate": candidate_card(candidate, employer.tier),
            "match": logic.score_match(candidate, vacancy),
            "vacancy": vacancy,
        })
    return rows


def employer_invitations(db: DBSession, employer: Employer) -> List[Dict[str, Any]]:
    rows = []
    for invitation in list_invitations_for_employer(db, employer.id):
        candidate = db.get(Candidate, invitation.candidate_id)
        vacancy = db.get(Vacancy, invitation.vacancy_id)
        if not candidate or not vacancy:
            continue
        rows.append({
            "invitation": invitation,
            "candidate": candidate_card(candidate, employer.tier),
            "match": logic.score_match(candidate, vacancy),
            "vacancy": vacancy,
        })
    return rows


def vacancy_candidates(db: DBSession, employer: Employer, vacancy: Vacancy) -> List[Dict[str, Any]]:
    ranked = logic.rank_candidates(list_candidates(db), vacancy, tier=employer.tier)
    return [
        {
            "candidate": candidate_card(candidate, employer.tier),
            "match": match,
            "candidate_id": candidate.id,
        }
        for candidate, match in ranked
    ]


def list_candidates(db: DBSession) -> List[Candidate]:
    return list(db.exec(select(Candidate)).all())


def list_employers(db: DBSession) -> List[Employer]:
    return list(db.exec(select(Employer)).all())


def list_vacancies(db: DBSession, employer_id: Optional[int] = None) -> List[Vacancy]:
    statement = select(Vacancy)
    if employer_id:
        statement = statement.where(Vacancy.employer_id == employer_id)
    return list(db.exec(statement).all())


def list_invitations_for_candidate(db: DBSession, candidate_id: int) -> List[Invitation]:
    return list(db.exec(select(Invitation).where(Invitation.candidate_id == candidate_id)).all())


def list_invitations_for_employer(db: DBSession, employer_id: int) -> List[Invitation]:
    return list(db.exec(select(Invitation).where(Invitation.employer_id == employer_id)).all())


def list_applications_for_candidate(db: DBSession, candidate_id: int) -> List[Application]:
    return list(db.exec(select(Application).where(Application.candidate_id == candidate_id)).all())


def list_applications_for_employer(db: DBSession, employer_id: int) -> List[Application]:
    return list(db.exec(select(Application).where(Application.employer_id == employer_id)).all())


def find_invitation(db: DBSession, candidate_id: int, vacancy_id: int) -> Optional[Invitation]:
    return db.exec(
        select(Invitation).where(
            Invitation.candidate_id == candidate_id,
            Invitation.vacancy_id == vacancy_id,
        )
    ).first()


def find_application(db: DBSession, candidate_id: int, vacancy_id: int) -> Optional[Application]:
    return db.exec(
        select(Application).where(
            Application.candidate_id == candidate_id,
            Application.vacancy_id == vacancy_id,
        )
    ).first()


def new_applications_count(db: DBSession, employer: Employer) -> int:
    """Сколько откликов пришло после последнего визита работодателя."""
    applications = list_applications_for_employer(db, employer.id)
    if not employer.last_visit_at:
        return len([application for application in applications if application.is_new])
    return len([
        application for application in applications
        if (application.created_at or "") > employer.last_visit_at
    ])


def public_stats(db: DBSession) -> Dict[str, int]:
    """Счётчики для лендинга."""
    return {
        "candidates": len(list_candidates(db)),
        "employers": len(list_employers(db)),
        "vacancies": len([v for v in list_vacancies(db) if v.open]),
    }
