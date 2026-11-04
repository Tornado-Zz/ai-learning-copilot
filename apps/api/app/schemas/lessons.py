"""Schemas for GET /lessons, GET /lessons/{id} and PUT /lessons/{id}/progress (Sprint 2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

ProgressStatus = Literal["not_started", "in_progress", "completed"]

SELF_ASSESSMENT_MIN = 0
# Sprint 2 freezes the lesson self-assessment at L2: it never grants L3/L4 and
# never writes user_skill_levels, so anything above L2 is a 422.
SELF_ASSESSMENT_MAX = 2


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class LessonProgressOut(BaseModel):
    """One user's progress on one lesson. Absent (null) means never opened."""

    status: str
    self_assessment: int
    progress_pct: int
    time_spent_seconds: int
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @field_serializer("started_at", "completed_at", "updated_at")
    def _serialize_times(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_z(value)


class LessonListItemOut(BaseModel):
    """List row: metadata and progress only, never the lesson body."""

    id: int
    code: str
    title: str
    summary: str | None
    stage: int
    order_index: int
    estimated_minutes: int
    content_version: int
    status: str
    skill_code: str | None
    progress: LessonProgressOut | None


class LessonListResponse(BaseModel):
    items: list[LessonListItemOut]
    total: int


class LessonExampleOut(BaseModel):
    title: str
    code: str
    output: str | None = None
    notes: list[str] = Field(default_factory=list)


class CommonMistakeOut(BaseModel):
    mistake: str
    why: str
    fix: str


class SelfCheckOut(BaseModel):
    question: str
    answer: str


class LessonContentOut(BaseModel):
    """The five blocks every lesson must carry (goal / explain / example / mistakes / self check)."""

    schema_version: int
    goal: str
    explanation: list[str]
    example: LessonExampleOut
    common_mistakes: list[CommonMistakeOut]
    self_check: list[SelfCheckOut]


class LessonDetailOut(LessonListItemOut):
    content: LessonContentOut


class LessonProgressUpdateRequest(BaseModel):
    """PUT body. status is required; the other fields are optional.

    time_spent_seconds is the client's cumulative dwell time for this lesson
    (an absolute value, not a delta); the stored value is monotonic.
    """

    status: ProgressStatus
    self_assessment: int | None = Field(
        default=None,
        ge=SELF_ASSESSMENT_MIN,
        le=SELF_ASSESSMENT_MAX,
        description="课程自评 L0–L2，只写 learning_progress，永不写 user_skill_levels",
    )
    time_spent_seconds: int | None = Field(default=None, ge=0)
    progress_pct: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="可选：客户端上报的阅读完成率，服务端只增不减，completed 时固定 100",
    )


class LessonProgressResponse(BaseModel):
    lesson_id: int
    status: str
    plan_items_completed: int = Field(
        default=0,
        description="本次「课程完成」在同一事务内一并置为 done 的本周计划项行数",
    )
    self_assessment: int
    progress_pct: int
    time_spent_seconds: int
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @field_serializer("started_at", "completed_at", "updated_at")
    def _serialize_times(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_z(value)
