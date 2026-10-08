"""Вход и подтверждение email (раздел 12.1 ТЗ).

Паролей нет: POST /login создаёт сессию и 6-значный код, POST /verify его проверяет.
В MVP код показывается на странице — заглушка вместо SMTP.
"""
from fastapi import APIRouter, Depends, Request
from sqlmodel import Session as DBSession

import auth
import logic
from database import get_db
from web import SESSION_COOKIE, SESSION_TTL_DAYS, redirect, render

router = APIRouter(tags=["auth"])

ROLES = ("candidate", "employer")
ROLE_TITLES = {"candidate": "кандидат", "employer": "работодатель"}


def _role(value: str) -> str:
    return value if value in ROLES else "candidate"


@router.get("/login")
def login_page(request: Request, role: str = "candidate"):
    principal = auth.current_principal(request)
    if principal is not None:
        if principal.is_authenticated:
            return redirect(principal.home_url, "Вы уже вошли", "success")
        return redirect("/verify")
    return render(request, "login.html", "Вход", role=_role(role), role_titles=ROLE_TITLES,
                  email="")


@router.post("/login")
async def login_submit(request: Request, db: DBSession = Depends(get_db)):
    form = await request.form()
    email = str(form.get("email", "")).strip()
    role = _role(str(form.get("role", "candidate")))
    error = logic.email_error(email)
    if error:
        return render(request, "login.html", "Вход", error=error, email=email,
                      role=role, role_titles=ROLE_TITLES)

    session_row = auth.start_login(db, email, role)
    response = redirect("/verify", f"Код подтверждения отправлен на {email}", "success")
    response.set_cookie(
        SESSION_COOKIE,
        session_row.token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/verify")
def verify_page(request: Request):
    principal = auth.current_principal(request)
    if principal is None:
        return redirect("/login", "Сессия не найдена — запросите код заново", "error")
    if principal.is_authenticated:
        return redirect(principal.home_url if principal.user else principal.register_url)
    if not principal.session.code:
        return redirect("/login", "Код уже использован — запросите новый", "error")
    return render(
        request,
        "verify.html",
        "Подтверждение email",
        email=principal.session.email,
        role=principal.session.role,
        role_title=ROLE_TITLES.get(principal.session.role, "кандидат"),
        demo_code=principal.session.code,
    )


@router.post("/verify")
async def verify_submit(request: Request, db: DBSession = Depends(get_db)):
    principal = auth.current_principal(request)
    if principal is None:
        return redirect("/login", "Сессия не найдена — запросите код заново", "error")
    if principal.is_authenticated:
        return redirect(principal.home_url if principal.user else principal.register_url)

    form = await request.form()
    code = str(form.get("code", ""))
    ok, error = auth.verify_code(db, principal, code)
    if not ok:
        return render(
            request,
            "verify.html",
            "Подтверждение email",
            error=error,
            email=principal.session.email,
            role=principal.session.role,
            role_title=ROLE_TITLES.get(principal.session.role, "кандидат"),
            demo_code=principal.session.code,
        )

    if principal.user:
        return redirect(principal.home_url, "Email подтверждён — добро пожаловать", "success")
    return redirect(
        principal.register_url,
        f"Email подтверждён. Заполните анкету: {ROLE_TITLES.get(principal.role, 'профиль')}",
        "success",
    )


@router.post("/logout")
def logout_submit(request: Request, db: DBSession = Depends(get_db)):
    auth.logout(db, auth.current_principal(request))
    response = redirect("/", "Вы вышли из системы", "success")
    response.delete_cookie(SESSION_COOKIE)
    return response
