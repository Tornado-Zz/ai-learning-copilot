"""Schemas for the study plan: GET /study-plan/preview (in memory) and the
persisted week plan (GET /study-plan, POST /study-plan/generate), contract 6.5 + Sprint 2 R1-R6.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer


class PlanDayOut(BaseModel):
    """Preview day: date plus the minutes this day may use. Nothing is persisted."""

    date: str = Field(examples=["2026-02-02"])
    minutes: int


class StageAdviceOut(BaseModel):
    skill_code: str
    name_zh: str
    level: int
    state: str
    suggestion: str


class StudyPlanPreviewResponse(BaseModel):
    computed: bool
    persisted: bool
    days: list[PlanDayOut]
    note: str
    weekly_minutes: int
    timezone: str
    focus_stage: str | None
    advice: str
    stages: list[StageAdviceOut]


class PlanItemOut(BaseModel):
    """One persisted plan item.

    Sprint 6: target_id points at a real lessons.id when kind='lesson' and at a
    real exercises.id when kind='exercise' (service check plus the database
    trigger). target_title / target_href are resolved by the service so the web
    client renders the link without a second request.
    """

    id: int
    kind: str
    target_id: int
    lesson_code: str | None
    lesson_title: str | None = Field(
        description="kind='lesson' 时为课程标题；practice 行没有课程标题，用 target_title"
    )
    target_title: str | None = Field(
        default=None, description="lesson 标题或 exercise 标题，供前端直接渲染"
    )
    target_href: str | None = Field(
        default=None, description="kind='lesson' → /learn/{id}；kind='exercise' → /practice/{id}"
    )
    planned_minutes: int
    status: str
    rationale: str
    dedupe_key: str


class StudyPlanDayOut(BaseModel):
    plan_date: date
    weekday: int = Field(description="1=周一 … 7=周日，来自 users.timezone 的本地日历")
    planned_minutes: int = Field(description="= total_minutes，保留给现有客户端")
    scheduled_minutes: int = Field(
        description="待执行（scheduled）项的分钟数；生成时不超过 daily_minutes − history_minutes"
    )
    history_minutes: int = Field(description="已完成 / 已跳过（done + skipped）项的分钟数")
    total_minutes: int = Field(
        description=(
            "scheduled_minutes + history_minutes，即该日已分配的分钟数。历史终态"
            "（done/skipped）的分钟仍计入当日已分配预算，因此生成时新排课额度 ="
            " daily_minutes − history_minutes。total_minutes <= daily_minutes 只在"
            "生成那一刻成立：用户事后调小 daily_minutes，该日 total 就可能超过新额度，"
            "前端必须显示超限提示，不得断言无条件恒成立。"
        )
    )
    items: list[PlanItemOut]


class PlanItemUpdateRequest(BaseModel):
    """PATCH body: only a still-scheduled item may become done or skipped."""

    status: Literal["done", "skipped"]


class PlanItemResponse(PlanItemOut):
    """The single item returned by PATCH, with its place in the week."""

    week_start: date
    plan_date: date
    updated_at: datetime

    @field_serializer("updated_at")
    def _serialize_updated_at(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class UnscheduledLessonOut(BaseModel):
    """A lesson the generator could not place this week, with the reason."""

    lesson_id: int
    code: str
    title: str
    estimated_minutes: int
    reason: str


class StudyPlanResponse(BaseModel):
    week_start: date
    week_end: date
    today: date = Field(
        description="按 users.timezone 计算的当前本地日期，前端判断「今天」只认这个字段"
    )
    timezone: str
    daily_minutes: int
    study_days: list[int]
    weekly_planned_minutes: int
    items_total: int
    scheduled_items: int = Field(description="待执行的计划项行数（scheduled）")
    history_items: int = Field(description="历史行数（done + skipped），不计入待执行")
    expired_items: int = Field(
        default=0, description="已作废（expired）的历史行数，不计入 R1/R2 预算"
    )
    lesson_items: int
    exercise_items: int
    review_items: int
    days: list[StudyPlanDayOut]


class StudyPlanGeneratedResponse(StudyPlanResponse):
    generated: bool
    unscheduled: list[UnscheduledLessonOut] = Field(default_factory=list)
