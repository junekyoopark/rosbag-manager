from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services import auth_service

router = APIRouter()
templates = None  # set by main.py


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
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
    return RedirectResponse(url=next or "/", status_code=303)


@router.post("/auth/logout")
async def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
