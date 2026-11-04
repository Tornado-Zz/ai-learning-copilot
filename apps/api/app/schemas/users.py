"""Schemas for GET /users/me and PUT /users/me/profile (contract 6.1, 6.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    display_name: str
    timezone: str
    timezone_source: str = Field(examples=["default", "user_confirmed"])


class ProfileOut(BaseModel):
    study_days: list[int] = Field(examples=[[1, 3, 5]])
    daily_minutes: int = Field(examples=[60])
    weekly_minutes: int = Field(examples=[180], description="生成列 cardinality(study_days) * daily_minutes")


class SkillSnapshotOut(BaseModel):
    code: str
    name_zh: str
    level: int = Field(description="用户能力等级 0–4，由契约 3.3 解析，不是技能树层级")
    state: str = Field(examples=["unassessed", "assessed_below_threshold", "established"])
    evidence_kind: str | None
    evidence_strength: str = Field(examples=["none", "assessed", "verified"])


class MeResponse(BaseModel):
    user: UserOut
    profile: ProfileOut
    skills: list[SkillSnapshotOut]


class ProfileUpdateRequest(BaseModel):
    study_days: list[int]
    daily_minutes: int
    timezone: str
    timezone_confirmed: bool = False
