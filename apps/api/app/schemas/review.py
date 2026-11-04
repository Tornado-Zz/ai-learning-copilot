"""Schemas for the v0.1.2 mistake book and spaced repetition (review_items).

The shapes are the frozen contract, nothing more:

* GET  /review/items   -> items[], total, due_total
* POST /review/items/{id}/result -> id, streak, interval_days, next_review_on,
  status, due
* GET  /review/summary -> pending, due_today, done, next_due_on

next_review_on stays a plain date: it is a local calendar day derived from
users.timezone, so serialising it as an instant would invent a UTC offset the
rule never used.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

REVIEW_LIMIT_DEFAULT = 20
REVIEW_LIMIT_MAX = 100

STATUS_PENDING = "pending"
STATUS_DONE = "done"
LAST_RESULT_PASSED = "passed"
LAST_RESULT_FAILED = "failed"


class ReviewItemOut(BaseModel):
    """One row of the mistake book, with the exercise it points at."""

    id: int
    exercise_id: int
    exercise_title: str
    lesson_id: int
    streak: int
    interval_days: int
    next_review_on: date
    status: str = Field(description="pending（还需复习）/ done（已连续通过 3 次）")
    due: bool = Field(
        description="status='pending' 且 next_review_on <= 今天（今天按 users.timezone 取）"
    )
    last_result: str | None = Field(default=None, description="passed / failed / null")


class ReviewItemsResponse(BaseModel):
    items: list[ReviewItemOut]
    total: int = Field(description="与本次过滤条件一致的条目总数，不受 limit 影响")
    due_total: int = Field(description="当前用户全部到期待复习条目数，不受 due/limit 影响")


class ReviewResultRequest(BaseModel):
    """POST body: the learner's own verdict on one review attempt."""

    passed: bool = Field(description="true 走答对规则（推进间隔），false 走答错规则（重置）")


class ReviewResultOut(BaseModel):
    id: int
    streak: int
    interval_days: int
    next_review_on: date
    status: str
    due: bool


class ReviewSummaryOut(BaseModel):
    """No rows is not an error: every count is 0 and next_due_on is null."""

    pending: int
    due_today: int
    done: int
    next_due_on: date | None = None


__all__ = [
    "LAST_RESULT_FAILED",
    "LAST_RESULT_PASSED",
    "REVIEW_LIMIT_DEFAULT",
    "REVIEW_LIMIT_MAX",
    "STATUS_DONE",
    "STATUS_PENDING",
    "ReviewItemOut",
    "ReviewItemsResponse",
    "ReviewResultOut",
    "ReviewResultRequest",
    "ReviewSummaryOut",
]
