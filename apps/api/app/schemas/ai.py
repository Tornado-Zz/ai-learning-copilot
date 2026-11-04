"""Schemas for the Sprint 4 AI tutor surface.

The request shape is frozen: question (1..2000), assistance_level, and an
optional context carrying a lesson id and/or an exercise id. Nothing else is
accepted, so there is no field through which a caller could upload submitted
code text - context is a pair of foreign keys, not a payload.

The response shape is frozen too: the answer, the model, the assistance level,
the usage numbers, the latency and citations. Sprint 5 fills citations from the
knowledge base it retrieved for this question: each entry names the source, its
URL, when it was fetched and whether that is older than KNOWLEDGE_STALE_DAYS. An
empty list is still the honest answer for a question nothing matched - retrieval
is additive, never a condition for answering.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.schemas.knowledge import KnowledgeCitation

# The four assistance levels the contract allows; assistance_level is the only
# vocabulary that may appear in ai_interactions as well.
AssistanceLevel = Literal["none", "hint", "partial_code", "full_answer"]

QUESTION_MIN_LENGTH = 1
QUESTION_MAX_LENGTH = 2000
# The list endpoint returns a preview, never the answer: 120 characters is enough
# for the learner to recognise the exchange and too little to re-read it from here.
ANSWER_PREVIEW_LENGTH = 120
INTERACTIONS_LIMIT_DEFAULT = 20
INTERACTIONS_LIMIT_MAX = 50


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class AiContextIn(BaseModel):
    """Optional provenance: which lesson and/or exercise the question is about."""

    lesson_id: int | None = Field(default=None, ge=1, description="相关课程 id")
    exercise_id: int | None = Field(default=None, ge=1, description="相关练习 id")


class TutorRequest(BaseModel):
    """POST /ai/tutor body."""

    question: str = Field(
        min_length=QUESTION_MIN_LENGTH,
        max_length=QUESTION_MAX_LENGTH,
        description="学员的问题，1–2000 字",
    )
    assistance_level: AssistanceLevel = Field(
        description="期望的帮助程度：none / hint / partial_code / full_answer"
    )
    context: AiContextIn | None = Field(
        default=None, description="可选上下文，只带课程 / 练习 id，不带任何代码文本"
    )

    @field_validator("question")
    @classmethod
    def _question_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question 不能只有空白字符")
        return stripped


class AiUsageOut(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TutorResponseOut(BaseModel):
    """200 body of POST /ai/tutor."""

    interaction_id: int
    answer: str
    model: str
    assistance_level: str
    usage: AiUsageOut
    latency_ms: int
    citations: list[KnowledgeCitation] = Field(default_factory=list)


class AiInteractionItemOut(BaseModel):
    """One row of GET /ai/interactions. answer is a preview, never the full text."""

    id: int
    question_preview: str
    assistance_level: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    status: str
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso_z(value)


class AiInteractionListResponse(BaseModel):
    items: list[AiInteractionItemOut]
    total: int


__all__ = [
    "ANSWER_PREVIEW_LENGTH",
    "AiContextIn",
    "AiInteractionItemOut",
    "AiInteractionListResponse",
    "AiUsageOut",
    "AssistanceLevel",
    "INTERACTIONS_LIMIT_DEFAULT",
    "INTERACTIONS_LIMIT_MAX",
    "QUESTION_MAX_LENGTH",
    "QUESTION_MIN_LENGTH",
    "KnowledgeCitation",
    "TutorRequest",
    "TutorResponseOut",
]
