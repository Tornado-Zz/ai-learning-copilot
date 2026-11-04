"""GET /skills: the six domain skills (contract 6.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.skills import SkillsResponse
from app.services import catalog

router = APIRouter(tags=["skills"])


@router.get("/skills", response_model=SkillsResponse, summary="六个技能域（只返回 domain 级）")
async def read_skills(session: AsyncSession = Depends(get_db)) -> SkillsResponse:
    rows = await catalog.list_domain_skills(session)
    return SkillsResponse(
        skills=[
            {
                "code": str(row["code"]),
                "name_zh": str(row["name_zh"]),
                "level": str(row["level"]),
                "order_index": int(row["order_index"]),
            }
            for row in rows
        ]
    )
