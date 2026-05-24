import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_admin, get_current_user
from app.models.nas_config import NASConfig

router = APIRouter()
templates = None  # set by main.py


# ── Config ─────────────────────────────────────────────────────

class NASConfigIn(BaseModel):
    enabled: bool = False
    dsm_url: str = ""
    username: str = ""
    password: str | None = None  # None = keep existing
    upload_path: str = "/rosbags"
    verify_ssl: bool = True


@router.get("/config")
async def get_config(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    config = await db.get(NASConfig, 1)
    if not config:
        return {"enabled": False, "dsm_url": "", "username": "",
                "upload_path": "/rosbags", "verify_ssl": True}
    return {
        "enabled": config.enabled,
        "dsm_url": config.dsm_url or "",
        "username": config.username or "",
        "upload_path": config.upload_path,
        "verify_ssl": config.verify_ssl,
    }


@router.post("/config")
async def save_config(data: NASConfigIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    from app.services.nas_service import encrypt_password
    config = await db.get(NASConfig, 1)
    if not config:
        config = NASConfig(id=1)
        db.add(config)
    config.enabled = data.enabled
    config.dsm_url = data.dsm_url.rstrip("/")
    config.username = data.username
    if data.password:
        config.encrypted_password = encrypt_password(data.password)
    config.upload_path = data.upload_path or "/rosbags"
    config.verify_ssl = data.verify_ssl
    config.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "ok"}


@router.get("/folders")
async def list_folders(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    config = await db.get(NASConfig, 1)
    if not config or not config.dsm_url:
        raise HTTPException(400, "NAS not configured")
    from app.services.nas_service import decrypt_password, synology_login, synology_logout, synology_list_shares
    try:
        password = decrypt_password(config.encrypted_password)
        sid = await asyncio.get_event_loop().run_in_executor(
            None, lambda: synology_login(config.dsm_url, config.username, password, config.verify_ssl)
        )
        shares = await asyncio.get_event_loop().run_in_executor(
            None, lambda: synology_list_shares(config.dsm_url, sid, config.verify_ssl)
        )
        synology_logout(config.dsm_url, sid, config.verify_ssl)
        return {"shares": shares}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/test")
async def test_connection(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    config = await db.get(NASConfig, 1)
    if not config or not config.dsm_url:
        raise HTTPException(400, "NAS not configured")
    from app.services.nas_service import decrypt_password, synology_login, synology_logout
    try:
        password = decrypt_password(config.encrypted_password)
        sid = await asyncio.get_event_loop().run_in_executor(
            None, lambda: synology_login(config.dsm_url, config.username, password, config.verify_ssl)
        )
        synology_logout(config.dsm_url, sid, config.verify_ssl)
        return {"status": "ok", "message": "Connection successful"}
    except Exception as e:
        raise HTTPException(400, str(e))


# ── Upload trigger ──────────────────────────────────────────────

def _can_use_nas(user) -> bool:
    if user is None:
        return False
    return user.role == "admin" or getattr(user, "can_upload_to_nas", False)


class NASSendIn(BaseModel):
    dest_path: str | None = None  # overrides config.upload_path when set


@router.post("/bags/{bag_id}/send")
async def send_bag_to_nas(
    bag_id: str,
    body: NASSendIn = NASSendIn(),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not _can_use_nas(user):
        raise HTTPException(403, "NAS upload privilege required")
    config = await db.get(NASConfig, 1)
    if not config or not config.enabled:
        raise HTTPException(400, "NAS upload is not configured")
    from app.services.bag_service import get_bag
    bag = await get_bag(db, bag_id)
    if bag.status != "ready":
        raise HTTPException(409, "Bag must be ready before sending to NAS")
    dest_path = (body.dest_path or "").strip() or config.upload_path
    task_id = str(uuid.uuid4())
    from worker.tasks.nas_upload import upload_bag_to_nas
    upload_bag_to_nas.apply_async(args=[bag_id, dest_path], task_id=task_id)
    return {"task_id": task_id}


# ── Task progress SSE ───────────────────────────────────────────

@router.get("/task/{task_id}/stream")
async def stream_nas_task(task_id: str):
    async def event_generator():
        from celery.result import AsyncResult
        from worker.celery_app import celery_app
        while True:
            result = AsyncResult(task_id, app=celery_app)
            state = result.state
            meta = result.info or {}
            pct = meta.get("pct", 0) if isinstance(meta, dict) else 0
            step = meta.get("step", state) if isinstance(meta, dict) else state
            payload = json.dumps({"state": state, "pct": pct, "step": step})
            yield f"data: {payload}\n\n"
            if state in ("SUCCESS", "FAILURE"):
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Settings page ───────────────────────────────────────────────

@router.get("")
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = getattr(request.state, "current_user", None)
    if not user or user.role != "admin":
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=303)
    config = await db.get(NASConfig, 1)
    return templates.TemplateResponse(request, "admin/nas_settings.html", {"config": config})
