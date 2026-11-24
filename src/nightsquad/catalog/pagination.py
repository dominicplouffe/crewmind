"""Cursor pagination and time windows for list operations (IF-3.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute


class PageRequest(BaseModel):
    """Inputs every list operation accepts (IF-3.5)."""

    after: str | None = Field(None, description="Cursor from the previous page's `next`.")
    limit: int = Field(50, ge=1, le=200, description="How many items to return.")
    since: datetime | None = Field(None, description="Only items at or after this time.")
    until: datetime | None = Field(None, description="Only items before this time.")


async def fetch_page[Row](
    session: AsyncSession,
    statement: Select[Row],
    page: PageRequest,
    *,
    key: InstrumentedAttribute[Any],
    at: InstrumentedAttribute[datetime],
) -> tuple[list[Row], str | None]:
    """Run `statement` for one page, ordered by `key`. Returns the rows and the next cursor."""
    if page.since is not None:
        statement = statement.where(at >= page.since)
    if page.until is not None:
        statement = statement.where(at < page.until)
    if page.after is not None:
        statement = statement.where(key > _decode(page.after, key))
    statement = statement.order_by(key).limit(page.limit + 1)
    rows = list((await session.execute(statement)).scalars())
    if len(rows) <= page.limit:
        return rows, None
    rows = rows[: page.limit]
    return rows, str(getattr(rows[-1], key.key))


def _decode(cursor: str, key: InstrumentedAttribute[Any]) -> Any:
    return int(cursor) if key.type.python_type is int else cursor
