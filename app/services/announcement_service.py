from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.db_models import AnnouncementModel


class AnnouncementService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _load_edit_history(item: AnnouncementModel) -> list[dict[str, Any]]:
        raw = item.edit_history_json
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        return list(parsed) if isinstance(parsed, list) else []

    @classmethod
    def _serialize_item(cls, item: AnnouncementModel, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        edit_history = history if history is not None else cls._load_edit_history(item)
        return {
            "id": item.id,
            "title": item.title,
            "summary": item.summary,
            "updated_by": item.updated_by,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "is_pinned": bool(item.is_pinned),
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "edit_history": edit_history,
        }

    @classmethod
    def _append_history(
        cls,
        item: AnnouncementModel,
        *,
        actor: str,
        action: str,
        edited_at: str,
    ) -> list[dict[str, Any]]:
        history = cls._load_edit_history(item)
        history.append(
            {
                "action": action,
                "editor": actor,
                "edited_at": edited_at,
                "title": item.title,
                "summary": item.summary,
                "is_pinned": bool(item.is_pinned),
            }
        )
        item.edit_history_json = json.dumps(history[-100:], ensure_ascii=False)
        return history[-100:]

    @classmethod
    def serialize(cls, item: AnnouncementModel) -> dict[str, Any]:
        return cls._serialize_item(item)

    def list_announcements(self, limit: int = 20) -> list[dict[str, Any]]:
        stmt = (
            select(AnnouncementModel)
            .order_by(
                AnnouncementModel.is_pinned.desc(),
                AnnouncementModel.updated_at.desc(),
                AnnouncementModel.id.desc(),
            )
            .limit(max(1, min(int(limit or 20), 200)))
        )
        return [self.serialize(row) for row in self.db.scalars(stmt)]

    def create_announcement(
        self,
        *,
        summary: str,
        updated_by: str,
        title: str | None = None,
        is_pinned: bool = False,
    ) -> dict[str, Any]:
        clean_summary = str(summary or "").strip()
        clean_title = str(title or "").strip() or None
        clean_updated_by = str(updated_by or "").strip() or "admin"
        if not clean_summary:
            raise ValueError("summary is required")
        now = utcnow()
        item = AnnouncementModel(
            title=clean_title,
            summary=clean_summary,
            updated_by=clean_updated_by,
            updated_at=now,
            is_pinned=bool(is_pinned),
            created_at=now,
        )
        self._append_history(
            item,
            actor=clean_updated_by,
            action="create",
            edited_at=now.isoformat(),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self.serialize(item)

    def update_announcement(
        self,
        announcement_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        is_pinned: bool | None = None,
        updated_by: str | None = None,
    ) -> dict[str, Any]:
        item = self.db.get(AnnouncementModel, announcement_id)
        if not item:
            raise KeyError("announcement not found")
        if title is not None:
            item.title = str(title or "").strip() or None
        if summary is not None:
            clean_summary = str(summary or "").strip()
            if not clean_summary:
                raise ValueError("summary is required")
            item.summary = clean_summary
        if is_pinned is not None:
            item.is_pinned = bool(is_pinned)
        item.updated_by = str(updated_by or item.updated_by or "admin").strip() or "admin"
        item.updated_at = utcnow()
        history = self._append_history(
            item,
            actor=item.updated_by,
            action="update",
            edited_at=item.updated_at.isoformat(),
        )
        self.db.commit()
        self.db.refresh(item)
        return self._serialize_item(item, history)

    def delete_announcement(self, announcement_id: int) -> dict[str, Any]:
        item = self.db.get(AnnouncementModel, announcement_id)
        if not item:
            raise KeyError("announcement not found")
        snapshot = self.serialize(item)
        self.db.delete(item)
        self.db.commit()
        return snapshot
