import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_db, require_admin
from app.services import auth_service
from app.models.team import Team

router = APIRouter()
templates = None  # set by main.py


async def _list_teams(db: AsyncSession) -> list[str]:
    result = await db.execute(select(Team.name).order_by(Team.name))
    return [row[0] for row in result.all()]


@router.get("", response_class=HTMLResponse)
async def admin_users_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    users = await auth_service.list_users(db)
    teams = await _list_teams(db)
    return templates.TemplateResponse(
        request, "admin/users.html", {"users": users, "current_user": current_user, "teams": teams}
    )


@router.post("/teams/create")
async def create_team(
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    name = name.strip()
    if name:
        existing = await db.get(Team, name)
        if not existing:
            db.add(Team(name=name))
            await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/teams/{team_name}/delete")
async def delete_team(
    team_name: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    team = await db.get(Team, team_name)
    if team:
        await db.delete(team)
        await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/team")
async def set_user_team(
    user_id: str,
    team: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user:
        user.team = team or None
        await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/create")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    email: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    existing = await auth_service.get_user_by_username(db, username)
    if existing:
        users = await auth_service.list_users(db)
        return templates.TemplateResponse(
            request,
            "admin/users.html",
            {"users": users, "current_user": current_user, "error": f"Username '{username}' already exists"},
            status_code=400,
        )
    await auth_service.create_user(db, username, password, role, email or None)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/delete")
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    uid = uuid.UUID(user_id)
    if uid == current_user.id:
        users = await auth_service.list_users(db)
        return templates.TemplateResponse(
            request,
            "admin/users.html",
            {"users": users, "current_user": current_user, "error": "Cannot delete your own account"},
            status_code=400,
        )
    await auth_service.delete_user(db, uid)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/role")
async def change_role(
    user_id: str,
    role: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    await auth_service.set_user_role(db, uuid.UUID(user_id), role)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/toggle-active")
async def toggle_active(
    user_id: str,
    is_active: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    await auth_service.set_user_active(db, uuid.UUID(user_id), is_active == "true")
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/toggle-delete-own")
async def toggle_delete_own(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from sqlalchemy import select
    from app.models.user import User
    uid = uuid.UUID(user_id)
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user:
        user.can_delete_own = not user.can_delete_own
        await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/toggle-nas")
async def toggle_nas(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from sqlalchemy import select
    from app.models.user import User
    uid = uuid.UUID(user_id)
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user:
        user.can_upload_to_nas = not user.can_upload_to_nas
        await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/{user_id}/toggle-nas-import")
async def toggle_nas_import(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from sqlalchemy import select
    from app.models.user import User
    uid = uuid.UUID(user_id)
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user:
        user.can_import_from_nas = not user.can_import_from_nas
        await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)
