from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.db_models import ErrorCodeSequenceModel, SolutionRecordModel


class ErrorCodeService:
    def __init__(self, db: Session):
        self.db = db

    def allocate(self, prefix: str) -> str:
        normalized = str(prefix or "").strip().upper()
        if len(normalized) != 2:
            raise ValueError("错误码前缀必须为 2 位字母。")

        for _ in range(50):
            sequence = self.db.get(ErrorCodeSequenceModel, normalized)
            if not sequence:
                sequence = ErrorCodeSequenceModel(prefix=normalized, next_value=2, updated_at=utcnow())
                self.db.add(sequence)
                number = 1
            else:
                number = max(1, int(sequence.next_value or 1))
                sequence.next_value = number + 1
                sequence.updated_at = utcnow()

            candidate = f"{normalized}{number:04d}"
            exists = self.db.scalar(select(SolutionRecordModel.id).where(SolutionRecordModel.error_code == candidate))
            if exists:
                self.db.flush()
                continue
            self.db.flush()
            return candidate
        raise RuntimeError("错误码生成冲突次数过多，请稍后重试。")
