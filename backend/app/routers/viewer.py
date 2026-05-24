from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services.bag_service import get_bag

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/local", response_class=HTMLResponse)
async def local_viewer_page(request: Request):
    return templates.TemplateResponse(request, "local_viewer.html", {})


@router.get("/{bag_id}", response_class=HTMLResponse)
async def viewer_page(bag_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    bag = await get_bag(db, bag_id)
    return templates.TemplateResponse(request, "viewer.html", {"bag": bag})
