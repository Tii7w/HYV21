"""Bildirim merkezi ve gerçek zamanlı olay akışı (SSE)."""

import asyncio
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..agent.notifier import notification_payload
from ..db import get_db
from ..events import bus
from ..models import Notification, User, utcnow
from ..security import current_user

router = APIRouter(prefix="/api", tags=["notifications"])
HEARTBEAT_SECONDS = 20


@router.get("/notifications")
def list_notifications(limit: int = Query(default=50, ge=1, le=200), user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    items = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(limit))
    unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    return {"items": [notification_payload(n) for n in items], "unread": unread}


@router.post("/notifications/{note_id}/read")
def mark_read(note_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    note = db.get(Notification, note_id)
    if note is None or note.user_id != user.id:
        raise HTTPException(404, "Bildirim bulunamadı.")
    note.read_at = note.read_at or utcnow()
    db.commit()
    return notification_payload(note)


@router.post("/notifications/read-all")
def mark_all_read(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()
    return {"ok": True}


@router.get("/events")
async def events(request: Request, user: User = Depends(current_user)) -> StreamingResponse:
    queue = bus.subscribe(user.id, user.role == "admin")

    async def stream():
        try:
            yield "retry: 5000\n\n"
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"event: {message['event']}\ndata: {json.dumps(message['data'], ensure_ascii=False, default=str)}\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
