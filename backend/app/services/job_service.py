import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import ConversionJob
from app.models.bag import Bag


async def get_job(db: AsyncSession, job_id: str) -> ConversionJob:
    stmt = select(ConversionJob).where(ConversionJob.id == uuid.UUID(job_id))
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, detail="Job not found")
    return job


async def enqueue_conversion(bag: Bag, db: AsyncSession) -> ConversionJob:
    # Delete any existing job for this bag
    stmt = select(ConversionJob).where(ConversionJob.bag_id == bag.id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.flush()

    job_id = uuid.uuid4()
    job = ConversionJob(
        id=job_id,
        bag_id=bag.id,
        celery_task_id=str(job_id),
        status="queued",
    )
    db.add(job)
    bag.status = "pending"
    return job


def dispatch_conversion(bag_id: str, job_id: str) -> None:
    from worker.tasks.convert import convert_bag
    convert_bag.apply_async(args=[bag_id], task_id=job_id)
