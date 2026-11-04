"""Schemas for GET /skills (contract 6.4)."""

from __future__ import annotations

from pydantic import BaseModel


class SkillOut(BaseModel):
    code: str
    name_zh: str
    level: str = "domain"
    order_index: int


class SkillsResponse(BaseModel):
    skills: list[SkillOut]
