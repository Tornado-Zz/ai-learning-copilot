"""Schemas for POST /diagnostics and GET /diagnostics/history (contract 6.3)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_serializer


class AnswerIn(BaseModel):
    choice: str


class DiagnosticSubmitRequest(BaseModel):
    attempt_token: str | None = Field(
        default=None,
        max_length=64,
        description="同一次诊断的网络重试复用同一 token：重试幂等返回原批次，新 token 追加新批次",
    )
    question_set_version: str
    rule_version: str
    answers: dict[str, AnswerIn]


class DomainScoreOut(BaseModel):
    skill_code: str
    correct: int
    total: int
    rate: float
    level: int
    state: str


class DiagnosticSubmitResponse(BaseModel):
    attempt_id: int
    rule_version: str
    domains: list[DomainScoreOut]


class PaperOptionOut(BaseModel):
    key: str
    text: str


class PaperQuestionOut(BaseModel):
    id: str
    order: int
    type: str
    prompt: str
    options: list[PaperOptionOut]
    domain_code: str


class DiagnosticPaperResponse(BaseModel):
    """The 20-question paper. It has no answer field by construction."""

    question_set_version: str
    rule_version: str
    total: int
    questions: list[PaperQuestionOut]


class HistoryAttemptOut(BaseModel):
    attempt_id: int
    submitted_at: datetime
    question_set_version: str
    rule_version: str
    total_correct: int
    total_questions: int
    domains: list[DomainScoreOut]

    @field_serializer("submitted_at")
    def _iso_z(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class DiagnosticHistoryResponse(BaseModel):
    items: list[HistoryAttemptOut]
    next_cursor: str | None
    has_more: bool


class AttemptQuestionOut(BaseModel):
    """One question of a submitted batch, joined with the live question set."""

    id: str
    order: int
    type: str = Field(description="题型，取自题库：single_choice / code_reading / bug_fix")
    domain_code: str
    prompt: str
    options: list[PaperOptionOut]
    selected: str | None
    correct: str
    is_correct: bool
    explanation: str | None


class DiagnosticAttemptDetailResponse(BaseModel):
    """Per-question verdicts. Only this endpoint carries the answer key."""

    attempt_id: int
    submitted_at: datetime
    question_set_version: str
    rule_version: str
    total_correct: int
    total_questions: int
    domains: list[DomainScoreOut]
    questions: list[AttemptQuestionOut]

    @field_serializer("submitted_at")
    def _iso_z(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
