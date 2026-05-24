import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.job import JobRead
from app.services.job_service import get_job

router = APIRouter()


@router.get("/{job_id}", response_model=JobRead)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    return await get_job(db, job_id)


@router.get("/{job_id}/stream")
async def stream_job_progress(job_id: str):
    async def event_generator():
        from celery.result import AsyncResult
        from worker.celery_app import celery_app

        while True:
            result = AsyncResult(job_id, app=celery_app)
            state = result.state
            meta = result.info or {}
            pct = meta.get("pct", 0) if isinstance(meta, dict) else 0
            step = meta.get("step", state) if isinstance(meta, dict) else state

            payload = json.dumps({"state": state, "pct": pct, "step": step})
            yield f"data: {payload}\n\n"

            if state in ("SUCCESS", "FAILURE"):
                break
            await asyncio.sleep(1.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
