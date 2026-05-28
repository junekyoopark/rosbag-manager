from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services import auth_service


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"

router = APIRouter()
templates = None  # set by main.py


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, db: AsyncSession = Depends(get_db)):
    if await auth_service.user_count(db) > 0:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "setup.html", {"error": ""})


@router.post("/setup")
async def do_setup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if await auth_service.user_count(db) > 0:
        return RedirectResponse(url="/", status_code=303)
    if password != confirm_password:
        return templates.TemplateResponse(request, "setup.html",
            {"error": "Passwords do not match."}, status_code=400)
    if len(password) < 8:
        return templates.TemplateResponse(request, "setup.html",
            {"error": "Password must be at least 8 characters."}, status_code=400)
    username = username.strip()
    if not username:
        return templates.TemplateResponse(request, "setup.html",
            {"error": "Username cannot be empty."}, status_code=400)
    user = await auth_service.create_user(db, username, password, role="admin")
    request.session["user_id"] = str(user.id)
    return RedirectResponse(url="/", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/", db: AsyncSession = Depends(get_db)):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
    if await auth_service.user_count(db) == 0:
        return RedirectResponse(url="/setup", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": ""})


@router.post("/auth/login")
async def do_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.authenticate(db, username, password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": "Invalid username or password"},
            status_code=401,
        )
    request.session["user_id"] = str(user.id)

    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = _client_ip(request)
    user.last_login_ua = request.headers.get("User-Agent", "")[:512]
    await db.commit()

    return RedirectResponse(url=next or "/", status_code=303)


@router.post("/auth/logout")
async def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/auth/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request):
    return templates.TemplateResponse(request, "change_password.html", {"error": "", "success": ""})


@router.post("/auth/change-password")
async def do_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    from app.services.auth_service import hash_password, verify_password
    user = request.state.current_user
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if new_password != confirm_password:
        return templates.TemplateResponse(request, "change_password.html",
            {"error": "New passwords do not match.", "success": ""}, status_code=400)
    if len(new_password) < 8:
        return templates.TemplateResponse(request, "change_password.html",
            {"error": "Password must be at least 8 characters.", "success": ""}, status_code=400)
    if not verify_password(current_password, user.hashed_password):
        return templates.TemplateResponse(request, "change_password.html",
            {"error": "Current password is incorrect.", "success": ""}, status_code=400)
    from sqlalchemy import select
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.hashed_password = hash_password(new_password)
    await db.commit()
    return templates.TemplateResponse(request, "change_password.html",
        {"error": "", "success": "Password updated successfully."})
