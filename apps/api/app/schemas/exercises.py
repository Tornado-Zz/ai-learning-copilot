"""Schemas for the exercise catalogue and submissions (Sprint 3 stage B).

B1/B2 are reflected in the shapes themselves:

* ExerciseDetailOut carries prompt, starter code and the visible self-check
  cases only. required_patterns, forbidden_patterns and expected_output are the
  answer keys and are never fields of a response model.
* SubmissionJudgedOut answers exactly the frozen seven keys; verification
  strength is stated as a label (已验证（静态规则） / 未验证（自检）), never as
  verified.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_serializer

# B2: judge input is text only, so its size is capped; an oversized blob is a 422.
CODE_TEXT_MAX_LENGTH = 20000
CLAIMED_OUTPUT_MAX_LENGTH = 20000
RECENT_LIMIT_DEFAULT = 20
RECENT_LIMIT_MAX = 50


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ExerciseVisibleTestOut(BaseModel):
    """One visible self-check case the learner can run by hand (B3 requires >= 2).

    The canonical pair is name/expect. input/expected repeat the same two values
    under the names apps/web/src/lib/exercises.ts already reads; keeping both
    sides of the product working costs two duplicate strings, and dropping the
    aliases later is a one-line change on either side.
    """

    name: str
    expect: str
    input: str = ""
    expected: str = ""


class SubmissionEvidenceOut(BaseModel):
    """How a submission was judged, in the B1 vocabulary."""

    submission_id: int
    attempt_no: int
    is_passed: bool | None
    judging_mode: str
    verification_method: str
    verification_strength: str
    evidence_label: str
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso_z(value)


class ExerciseListItemOut(BaseModel):
    """List row for /practice: metadata plus this user's latest submission."""

    id: int
    code: str
    lesson_id: int
    lesson_code: str
    title: str
    order_index: int
    difficulty: int
    estimated_minutes: int
    content_version: int
    status: str
    visible_test_count: int
    passed_count: int = Field(
        default=0, description="当前用户在这道题上 is_passed=true 的提交数"
    )
    last_submission: SubmissionEvidenceOut | None = None


class ExerciseListResponse(BaseModel):
    items: list[ExerciseListItemOut]
    total: int


class ExerciseDetailOut(ExerciseListItemOut):
    """Detail: adds the prompt and the starting code, and nothing else.

    The answer keys (required_patterns / forbidden_patterns / expected_output)
    are not part of this model: the detail query does not even read them.
    """

    prompt: str
    starter_code: str
    visible_tests: list[ExerciseVisibleTestOut]


class SubmissionCreateRequest(BaseModel):
    """POST body. Claiming a result locally is what switches the mode.

    self_reported_passed is None -> static rule judging.
    self_reported_passed present -> self check; the conclusion is the user's own
    claim and is labelled 未验证（自检）. No path makes it verified, and no path
    executes the code.
    """

    code_text: str = Field(
        min_length=1,
        max_length=CODE_TEXT_MAX_LENGTH,
        description="用户提交的代码文本，系统只做静态模式匹配，绝不执行",
    )
    claimed_output: str | None = Field(
        default=None,
        max_length=CLAIMED_OUTPUT_MAX_LENGTH,
        description="可选：用户自报的运行输出，与题库 expected_output 做归一化文本比对",
    )
    self_reported_passed: bool | None = Field(
        default=None,
        description="可选：用户自述本地运行通过（true）或未通过（false）；填了就走自检，标未验证",
    )


class SubmissionCheckOut(BaseModel):
    name: str
    passed: bool
    detail: str


class SubmissionJudgedOut(BaseModel):
    """The frozen response shape of POST /exercises/{id}/submissions."""

    submission_id: int
    judging_mode: str
    verification_method: str
    verification_strength: str
    evidence_label: str
    is_passed: bool | None
    checks: list[SubmissionCheckOut]


class SubmissionHistoryItemOut(SubmissionEvidenceOut):
    """One row of GET /exercises/{id}/submissions (newest first)."""


class SubmissionHistoryResponse(BaseModel):
    items: list[SubmissionHistoryItemOut]
    total: int


class RecentSubmissionItemOut(SubmissionEvidenceOut):
    """One row of GET /submissions/recent, carrying the exercise it belongs to."""

    exercise_id: int
    exercise_code: str
    exercise_title: str
    lesson_id: int


class RecentSubmissionsResponse(BaseModel):
    items: list[RecentSubmissionItemOut]
    total: int


__all__ = [
    "CODE_TEXT_MAX_LENGTH",
    "CLAIMED_OUTPUT_MAX_LENGTH",
    "ExerciseDetailOut",
    "ExerciseListItemOut",
    "ExerciseListResponse",
    "ExerciseVisibleTestOut",
    "RECENT_LIMIT_DEFAULT",
    "RECENT_LIMIT_MAX",
    "RecentSubmissionItemOut",
    "RecentSubmissionsResponse",
    "SubmissionCheckOut",
    "SubmissionCreateRequest",
    "SubmissionEvidenceOut",
    "SubmissionHistoryItemOut",
    "SubmissionHistoryResponse",
    "SubmissionJudgedOut",
]
