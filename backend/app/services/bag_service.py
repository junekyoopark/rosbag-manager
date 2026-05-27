import uuid
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.bag import Bag
from app.models.job import ConversionJob
from app.models.topic import Topic
from app.services.storage import StorageBackend


ALLOWED_EXTENSIONS = {".bag", ".mcap", ".db3", ".zip"}


def detect_format_from_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    mapping = {
        ".bag": "ros1_bag",
        ".mcap": "ros2_mcap",
        ".db3": "ros2_db3",
        ".zip": "ros2_mcap",  # assume zip contains a ROS2 bag; refined after unzip
    }
    return mapping.get(suffix, "unknown")


async def unzip_ros2_bag(zip_path: Path, bag_id: str) -> Path:
    out_dir = zip_path.parent / f"{bag_id}_unzipped"
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)
    zip_path.unlink(missing_ok=True)
    # Look for a directory containing metadata.yaml
    for child in out_dir.rglob("metadata.yaml"):
        return child.parent
    # Fallback: look for a bare .mcap or .db3
    for ext in (".mcap", ".db3", ".bag"):
        candidates = list(out_dir.rglob(f"*{ext}"))
        if candidates:
            return candidates[0]
    raise ValueError(f"No recognizable bag content found in zip: {zip_path}")


async def create_bag(
    file: UploadFile,
    name: str | None,
    description: str | None,
    tags: str | None,
    db: AsyncSession,
    storage: StorageBackend,
    uploaded_by_id=None,
    team: list[str] | None = None,
) -> tuple[Bag, ConversionJob]:
    max_bytes = settings.MAX_UPLOAD_SIZE_GB * 1_073_741_824
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(422, f"Unsupported file type: {file.filename}")

    bag_id = str(uuid.uuid4())
    upload_path = await storage.save(file, bag_id)

    if suffix == ".zip":
        upload_path = await unzip_ros2_bag(upload_path, bag_id)

    actual_size = upload_path.stat().st_size
    if actual_size > max_bytes:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(413, "File too large")

    bag_format = detect_format_from_extension(file.filename)
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    bag = Bag(
        id=uuid.UUID(bag_id),
        name=name or Path(file.filename).stem,
        description=description,
        original_filename=file.filename,
        bag_format=bag_format,
        upload_path=str(upload_path),
        file_size_bytes=actual_size,
        status="pending",
        tags=tag_list,
        uploaded_by_id=uploaded_by_id,
        team=team,
    )
    db.add(bag)
    return bag


async def list_bags(
    db: AsyncSession,
    status: str | None,
    q: str | None,
    tags: str | None,
    tag_mode: str,
    format: str | None,
    sort: str,
    limit: int,
    offset: int,
    drafts_only: bool = False,
    team: str | None = None,
) -> tuple[int, list[Bag]]:
    stmt = select(Bag).options(selectinload(Bag.job), selectinload(Bag.topics), selectinload(Bag.uploader))

    if drafts_only:
        stmt = stmt.where(Bag.status == "ready", Bag.published.is_(False))
    else:
        stmt = stmt.where(
            or_(Bag.status != "ready", Bag.published.is_(True))
        )

    if status and not drafts_only:
        stmt = stmt.where(Bag.status == status)

    if q:
        stmt = stmt.where(
            or_(
                Bag.name.ilike(f"%{q}%"),
                Bag.description.ilike(f"%{q}%"),
                func.array_to_string(Bag.tags, ' ').ilike(f"%{q}%"),
            )
        )

    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_mode == "and":
            for tag in tag_list:
                stmt = stmt.where(Bag.tags.any(tag))
        else:
            stmt = stmt.where(or_(*[Bag.tags.any(tag) for tag in tag_list]))

    if format == "ros1":
        stmt = stmt.where(Bag.bag_format == "ros1_bag")
    elif format == "ros2":
        stmt = stmt.where(Bag.bag_format.in_(["ros2_mcap", "ros2_db3"]))

    if team:
        team_list = [t.strip() for t in team.split(",") if t.strip()]
        stmt = stmt.where(or_(*[Bag.team.any(t) for t in team_list]))

    sort_map = {
        "created_at_desc": Bag.created_at.desc(),
        "created_at_asc": Bag.created_at.asc(),
        "name_asc": Bag.name.asc(),
        "duration_desc": Bag.duration_sec.desc(),
    }
    stmt = stmt.order_by(sort_map.get(sort, Bag.created_at.desc()))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.limit(min(limit, 100)).offset(offset)
    result = await db.execute(stmt)
    bags = result.scalars().all()
    return total, list(bags)


async def get_bag(db: AsyncSession, bag_id: str) -> Bag:
    stmt = (
        select(Bag)
        .where(Bag.id == uuid.UUID(bag_id))
        .options(selectinload(Bag.job), selectinload(Bag.topics), selectinload(Bag.uploader))
    )
    result = await db.execute(stmt)
    bag = result.scalar_one_or_none()
    if not bag:
        raise HTTPException(404, detail="Bag not found")
    return bag


async def delete_bag(db: AsyncSession, bag_id: str) -> None:
    import shutil
    bag = await get_bag(db, bag_id)

    for path in [bag.upload_path, bag.rrd_path, bag.thumbnail_path]:
        if path:
            p = Path(path)
            if p.is_dir():
                # unzipped ROS2 bag directory — delete the whole _unzipped parent
                parent = p.parent
                shutil.rmtree(parent if parent.name.endswith("_unzipped") else p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)

    # Intermediate MCAP directory created during ROS1/db3 conversion (never stored in DB)
    mcap_dir = Path(settings.UPLOADS_DIR) / f"{bag_id}_mcap"
    if mcap_dir.exists():
        shutil.rmtree(mcap_dir, ignore_errors=True)

    if bag.job and bag.job.celery_task_id:
        try:
            from worker.celery_app import celery_app
            celery_app.control.revoke(bag.job.celery_task_id, terminate=True)
        except Exception:
            pass

    await db.delete(bag)
    await db.commit()
