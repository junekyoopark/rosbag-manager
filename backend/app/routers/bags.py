import io
import re
import uuid
import zipfile
from pathlib import Path
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_storage, require_admin
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
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    admin=Depends(require_admin),
):
    bag = await bag_service.create_bag(file, name, description, tags, db, storage, uploaded_by_id=admin.id)
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


@router.get("/grid-partial")
async def grid_partial(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    tags: str | None = None,
    tag_mode: str = "or",
    format: str | None = None,
    drafts: bool = False,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    _, bags = await bag_service.list_bags(db, status, q, tags, tag_mode, format, "created_at_desc", 20, offset, drafts_only=drafts)
    user = getattr(request.state, "current_user", None)
    can_nas = user and (user.role == "admin" or getattr(user, "can_upload_to_nas", False))
    return templates.TemplateResponse(request, "partials/bag_grid.html", {"bags": bags, "drafts_mode": drafts, "can_nas": can_nas})


@router.get("/{bag_id}/card-partial")
async def card_partial(request: Request, bag_id: str, db: AsyncSession = Depends(get_db)):
    bag = await bag_service.get_bag(db, bag_id)
    return templates.TemplateResponse(request, "partials/bag_card.html", {"bag": bag})


@router.get("/{bag_id}", response_model=BagRead)
async def get_bag(bag_id: str, db: AsyncSession = Depends(get_db)):
    return await bag_service.get_bag(db, bag_id)


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
async def update_bag(bag_id: str, data: BagUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    bag = await bag_service.get_bag(db, bag_id)
    if data.name is not None:
        bag.name = data.name
    if data.description is not None:
        bag.description = data.description
    if data.tags is not None:
        bag.tags = data.tags
    if data.published is not None:
        bag.published = data.published
    await db.commit()
    return {"status": "ok"}


@router.delete("/{bag_id}")
async def delete_bag(bag_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
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
