import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_current_user
from app.models.lichtblick_layout import LichtblickLayout

router = APIRouter()


# ── CRUD ──────────────────────────────────────────────────────────

@router.get("/api/layouts")
async def list_layouts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LichtblickLayout).order_by(LichtblickLayout.name))
    layouts = result.scalars().all()
    return [{"id": l.id, "name": l.name} for l in layouts]


@router.post("/api/layouts")
async def create_layout(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    raw = await file.read()
    try:
        parsed = json.loads(raw)
        content = json.dumps(parsed)
    except Exception:
        return JSONResponse({"error": "Invalid JSON file"}, status_code=400)

    name = name.strip() or file.filename or "Layout"
    db.add(LichtblickLayout(
        name=name,
        content=content,
        created_by_id=user.id if user else None,
    ))
    await db.commit()
    return RedirectResponse(url="/live", status_code=303)


@router.post("/api/layouts/{layout_id}/delete")
async def delete_layout(
    layout_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    layout = await db.get(LichtblickLayout, layout_id)
    if layout:
        # allow creator or admin to delete
        if user and (user.role == "admin" or layout.created_by_id == user.id):
            await db.delete(layout)
            await db.commit()
    return RedirectResponse(url="/live", status_code=303)


# ── Lichtblick launcher ───────────────────────────────────────────

@router.get("/lichtblick-launch", response_class=HTMLResponse)
async def lichtblick_launch(
    request: Request,
    layout_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    import httpx

    # Fetch Lichtblick HTML from the internal container
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://lichtblick:8080/", timeout=5)
            html = resp.text
    except Exception as e:
        return HTMLResponse(f"<p>Could not reach Lichtblick container: {e}</p>", status_code=502)

    # Inject <base href> (same as nginx does for /lichtblick/)
    html = html.replace("<head>", '<head><base href="/lichtblick/">', 1)

    # Inject layout
    if layout_id:
        layout = await db.get(LichtblickLayout, layout_id)
        if layout:
            html = html.replace(
                "LICHTBLICK_SUITE_DEFAULT_LAYOUT = [][0]",
                f"LICHTBLICK_SUITE_DEFAULT_LAYOUT = {layout.content}",
                1,
            )

    return HTMLResponse(html)
