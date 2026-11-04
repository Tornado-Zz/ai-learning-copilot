"""Schemas for GET /progress/overview and GET /capstone/readiness (v0.1.1).

Both payloads are real aggregates: no field is a demonstration constant, and an
empty account returns the same shape with zeros and an empty domain list.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class LessonSummaryOut(BaseModel):
    total: int = Field(description="已发布课程总数（目录规模，与用户无关）")
    completed: int
    in_progress: int
    not_started: int = Field(description="total − completed − in_progress，不小于 0")
    minutes_completed: int = Field(description="已 completed 课程的 lessons.estimated_minutes 之和")


class PlanSummaryOut(BaseModel):
    week_start: date = Field(description="按 users.timezone 计算的本周周一")
    scheduled: int
    done: int
    skipped: int
    minutes_done: int = Field(description="本周 done 行的 planned_minutes 之和")
    minutes_scheduled: int = Field(description="本周仍 scheduled 行的 planned_minutes 之和")


class PracticeSummaryOut(BaseModel):
    exercises_total: int = Field(description="已发布练习总数")
    exercises_attempted: int = Field(description="去重后的已作答练习数")
    exercises_passed: int = Field(description="去重后的已通过练习数（is_passed=true）")
    submissions_total: int
    by_evidence: dict[str, int] = Field(
        description="按 submissions.verification_method 分组计数；没有出现的口径不占键"
    )


class CapabilityDomainOut(BaseModel):
    skill_code: str
    name: str = Field(description="skills.name_zh")
    level: int = Field(description="该能力域按契约 3.3 解析出的当前等级")
    source: str | None = Field(description="user_skill_levels.evidence_kind，尚未建立等级时为 null")


class CapabilitySummaryOut(BaseModel):
    average_level: float = Field(description="user_skill_levels.level 的算术平均，保留 1 位小数")
    domains: list[CapabilityDomainOut]


class ActivityDayOut(BaseModel):
    date: date
    minutes: int = Field(description="该本地日期 done 行的 planned_minutes 之和；缺失日期为 0")


class ProgressOverviewResponse(BaseModel):
    lessons: LessonSummaryOut
    plan: PlanSummaryOut
    practice: PracticeSummaryOut
    capability: CapabilitySummaryOut
    activity: list[ActivityDayOut] = Field(description="最近 7 天（含今天）逐日，缺失补 0")


class CapstoneRequirementOut(BaseModel):
    key: str
    label: str
    required: int
    actual: int
    met: bool = Field(description="actual >= required")


class CapstoneReadinessResponse(BaseModel):
    ready: bool = Field(description="四条要求全部 met 时为 true")
    requirements: list[CapstoneRequirementOut]
    note: str
