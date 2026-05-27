import time
import uuid as _uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.services.bag_service import get_bag

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

_TEMP_RRD_DIR = Path(settings.RRD_DIR) / "_temp"
_TEMP_TTL = 7200  # 2 hours


def _cleanup_temp():
    if not _TEMP_RRD_DIR.exists():
        return
    cutoff = time.time() - _TEMP_TTL
    for f in _TEMP_RRD_DIR.glob("*.rrd"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
        except OSError:
            pass


@router.get("/local", response_class=HTMLResponse)
async def local_viewer_page(request: Request):
    return templates.TemplateResponse(request, "local_viewer.html", {})


@router.post("/local/temp-rrd")
async def upload_temp_rrd(file: UploadFile = File(...)):
    _cleanup_temp()
    _TEMP_RRD_DIR.mkdir(parents=True, exist_ok=True)
    file_id = str(_uuid.uuid4())
    dest = _TEMP_RRD_DIR / f"{file_id}.rrd"
    with open(dest, "wb") as f:
        while chunk := await file.read(65536):
            f.write(chunk)
    return {"url": f"/bags/local/temp-rrd/{file_id}.rrd"}


@router.get("/local/temp-rrd/{file_id}.rrd")
async def serve_temp_rrd(file_id: str):
    try:
        _uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(400, "Invalid file ID")
    path = _TEMP_RRD_DIR / f"{file_id}.rrd"
    if not path.exists():
        raise HTTPException(404, "Temp RRD not found or expired")
    return FileResponse(path, media_type="application/octet-stream")


@router.get("/{bag_id}", response_class=HTMLResponse)
async def viewer_page(bag_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    bag = await get_bag(db, bag_id)
    return templates.TemplateResponse(request, "viewer.html", {"bag": bag})
