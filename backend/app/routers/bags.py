import io
import re
import uuid
import zipfile
from pathlib import Path
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel as _BaseModel
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_current_user, get_storage, require_admin, require_uploader
from app.models.bag import Bag
from app.models.job import ConversionJob
from app.schemas.bag import BagList, BagListItem, BagRead, BagUpdate, BagUploadResponse
from app.services import bag_service
from app.services import job_service
from app.services.job_service import dispatch_conversion
from app.services.storage import StorageBackend

router = APIRouter()


def _safe_filename(name: str) -> str:
    """Strip characters that are illegal in most filesystem / NAS filenames."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
templates = None  # set by main.py after filters are registered


@router.post("/upload", status_code=201, response_model=BagUploadResponse)
async def upload_bag(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    description: str | None = Form(None),
    tags: str | None = Form(None),
    team: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    uploader=Depends(require_uploader),
):
    team_list = [t.strip() for t in team.split(",") if t.strip()] if team else None
    if not team_list:
        uploader_team = getattr(uploader, "team", None)
        team_list = [uploader_team] if uploader_team else []
    bag = await bag_service.create_bag(file, name, description, tags, db, storage, uploaded_by_id=uploader.id, team=team_list)
    db.add(bag)
    await db.flush()
    await db.commit()
    await db.refresh(bag)

    job = await job_service.enqueue_conversion(bag, db)
    await db.commit()
    dispatch_conversion(str(bag.id), str(job.id))

    return BagUploadResponse(
        id=str(bag.id),
        name=bag.name,
        status=bag.status,
        job_id=str(job.id),
        created_at=bag.created_at,
    )


@router.get("", response_model=BagList)
async def list_bags(
    status: str | None = None,
    q: str | None = None,
    tags: str | None = None,
    sort: str = "created_at_desc",
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    total, bags = await bag_service.list_bags(db, status, q, tags, sort, limit, offset)
    items = [
        BagListItem(
            id=b.id,
            name=b.name,
            description=b.description,
            status=b.status,
            bag_format=b.bag_format,
            file_size_bytes=b.file_size_bytes,
            rrd_size_bytes=b.rrd_size_bytes,
            duration_sec=b.duration_sec,
            message_count=b.message_count,
            thumbnail_path=b.thumbnail_path,
            tags=b.tags or [],
            created_at=b.created_at,
            topic_count=len(b.topics) if b.topics else 0,
        )
        for b in bags
    ]
    return BagList(total=total, limit=limit, offset=offset, items=items)


@router.get("/tags")
async def list_tags(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    result = await db.execute(text(
        "SELECT DISTINCT unnest(tags) AS tag FROM bags "
        "WHERE tags IS NOT NULL AND array_length(tags, 1) > 0 ORDER BY tag"
    ))
    return [row[0] for row in result.all() if row[0]]


@router.get("/teams")
async def list_teams(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select as _select
    from app.models.team import Team
    result = await db.execute(_select(Team.name).order_by(Team.name))
    return [row[0] for row in result.all()]


@router.get("/grid-partial")
async def grid_partial(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    tags: str | None = None,
    tag_mode: str = "or",
    format: str | None = None,
    team: str | None = None,
    drafts: bool = False,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    _, bags = await bag_service.list_bags(db, status, q, tags, tag_mode, format, "created_at_desc", 20, offset, drafts_only=drafts, team=team or None)
    user = getattr(request.state, "current_user", None)
    can_nas = user and (user.role == "admin" or getattr(user, "can_upload_to_nas", False))
    return templates.TemplateResponse(request, "partials/bag_grid.html", {"bags": bags, "drafts_mode": drafts, "can_nas": can_nas})


@router.get("/{bag_id}/card-partial")
async def card_partial(request: Request, bag_id: str, db: AsyncSession = Depends(get_db)):
    bag = await bag_service.get_bag(db, bag_id)
    user = getattr(request.state, "current_user", None)
    can_nas = bool(user and (user.role == "admin" or getattr(user, "can_upload_to_nas", False)))
    return templates.TemplateResponse(request, "partials/bag_card.html", {"bag": bag, "can_nas": can_nas})


@router.get("/{bag_id}", response_model=BagRead)
async def get_bag(bag_id: str, db: AsyncSession = Depends(get_db)):
    return await bag_service.get_bag(db, bag_id)


class _ThumbnailFrameIn(_BaseModel):
    frame_index: int


@router.post("/{bag_id}/thumbnail/frame", status_code=200)
async def set_thumbnail_from_frame(
    bag_id: str,
    body: _ThumbnailFrameIn,
    db: AsyncSession = Depends(get_db),
    uploader=Depends(require_uploader),
):
    from app.utils.thumbnails import frame_from_sprite
    from app.config import settings as _settings
    bag = await bag_service.get_bag(db, bag_id)
    if not frame_from_sprite(bag_id, body.frame_index):
        raise HTTPException(404, "Sprite not found for this bag")
    bag.thumbnail_path = str(FilePath(_settings.THUMB_DIR) / f"{bag_id}.jpg")
    await db.commit()
    return {"ok": True}


@router.post("/{bag_id}/thumbnail/reextract", status_code=202)
async def reextract_thumbnail(
    bag_id: str,
    db: AsyncSession = Depends(get_db),
    uploader=Depends(require_uploader),
):
    from app.config import settings as _settings
    bag = await bag_service.get_bag(db, bag_id)

    mcap_path = None
    if bag.bag_format in ("ros1_bag", "ros2_db3"):
        mcap_dir = FilePath(_settings.UPLOADS_DIR) / f"{bag_id}_mcap"
        if mcap_dir.is_dir():
            mcap_files = list(mcap_dir.glob("*.mcap"))
            if mcap_files:
                mcap_path = str(mcap_files[0])

    if mcap_path is None:
        mcap_path = bag.upload_path

    from worker.tasks.introspect import extract_thumbnail_task
    extract_thumbnail_task.delay(str(bag.id), mcap_path)
    return {"ok": True, "queued": True}


@router.post("/{bag_id}/thumbnail/upload", status_code=200)
async def upload_custom_thumbnail(
    bag_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    uploader=Depends(require_uploader),
):
    from PIL import Image as _Image
    from app.config import settings as _settings
    bag = await bag_service.get_bag(db, bag_id)
    data = await file.read()
    try:
        img = _Image.open(io.BytesIO(data))
        img.thumbnail((640, 360))
    except Exception:
        raise HTTPException(400, "Invalid image file")
    thumb_dir = FilePath(_settings.THUMB_DIR)
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / f"{bag_id}.jpg"
    img.save(thumb_path, "JPEG", quality=85)
    bag.thumbnail_path = str(thumb_path)
    await db.commit()
    return {"ok": True}


@router.get("/{bag_id}/source")
async def download_bag_source(bag_id: str, db: AsyncSession = Depends(get_db)):
    bag = await bag_service.get_bag(db, bag_id)
    path = FilePath(bag.upload_path)

    if not path.exists():
        raise HTTPException(404, "Source file not found on disk")

    safe_name = _safe_filename(bag.name)

    if path.is_file():
        ext = FilePath(bag.original_filename).suffix  # e.g. ".bag" or ".mcap"
        return FileResponse(
            path=str(path),
            filename=f"{safe_name}{ext}",
            media_type="application/octet-stream",
        )

    # Directory bag (ROS2 multi-file) — zip on the fly
    def zip_dir():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            for f in path.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(path.parent))
        buf.seek(0)
        while chunk := buf.read(65536):
            yield chunk

    return StreamingResponse(
        zip_dir(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )


@router.patch("/{bag_id}")
async def update_bag(bag_id: str, data: BagUpdate, db: AsyncSession = Depends(get_db), user=Depends(require_uploader)):
    bag = await bag_service.get_bag(db, bag_id)
    if user.role != "admin" and bag.uploaded_by_id != user.id:
        raise HTTPException(403, "You can only edit your own bags")
    if data.name is not None:
        bag.name = data.name
    if data.description is not None:
        bag.description = data.description
    if data.tags is not None:
        bag.tags = data.tags
    if data.published is not None:
        bag.published = data.published
    if data.team is not None:
        bag.team = data.team
    await db.commit()
    return {"status": "ok"}


@router.delete("/{bag_id}")
async def delete_bag(
    bag_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if user is None:
        raise HTTPException(403, "Authentication required")
    bag = await bag_service.get_bag(db, bag_id)
    if user.role == "admin":
        pass  # admin can delete anything
    elif user.role == "user" and user.can_delete_own and bag.uploaded_by_id == user.id:
        pass  # user can delete their own bags when toggle is on
    else:
        raise HTTPException(403, "Not allowed to delete this bag")
    await bag_service.delete_bag(db, bag_id)
    return Response(content="", status_code=200)


@router.post("/{bag_id}/reconvert", status_code=202)
async def reconvert_bag(bag_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    bag = await bag_service.get_bag(db, bag_id)
    if bag.status == "converting":
        raise HTTPException(409, detail="Conversion already in progress")
    job = await job_service.enqueue_conversion(bag, db)
    await db.commit()
    dispatch_conversion(str(bag.id), str(job.id))
    return {"job_id": str(job.id), "status": "queued"}
