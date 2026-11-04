"""Schemas for the v0.1.3 capstone submission (capstone_submissions).

诚实性口径（冻结）：本版本是单用户本地应用，不存在第三方评审者。评审结果永远由
本人给出，因此 reviewer 只有 'self' 一个合法值，本文件的任何字段都不得让调用方
以为发生过人工或外部评审。真正的人工评审需要多用户与鉴权，属后续版本。

形状即契约，没有多余字段：

* POST   /capstone/submissions             -> 201, 完整对象
* PATCH  /capstone/submissions/{id}        -> 200, 完整对象（只有 draft 可改）
* GET    /capstone/submissions             -> {items[], total}
* POST   /capstone/submissions/{id}/submit -> 200, 完整对象（draft -> submitted）
* POST   /capstone/submissions/{id}/review -> 200, 完整对象（submitted -> reviewed）

四条长度校验（title 1..120、summary 1..4000、run_instructions 1..4000、
repo_url <= 300 且为空或 http(s) 链接）在请求模型里表达，超限由统一错误体回 422；
状态机校验不在这里，它属于 app.services.capstone。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

CAPSTONE_LIMIT_DEFAULT = 20
CAPSTONE_LIMIT_MAX = 100

TITLE_MAX_LENGTH = 120
TEXT_MAX_LENGTH = 4000
REPO_URL_MAX_LENGTH = 300

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_REVIEWED = "reviewed"

VERDICT_PASS = "pass"
VERDICT_NEEDS_WORK = "needs_work"

# 自评是本版本唯一的评审方式，也是数据库里唯一合法的 reviewer 值。
REVIEWER_SELF = "self"


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _http_url_or_none(value: str | None) -> str | None:
    """空值放行（作品可以先不填链接），非空则必须是 http(s) 绝对地址。"""
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("repo_url 必须是 http 或 https 链接")
    return candidate


class CapstoneSubmissionCreateRequest(BaseModel):
    """POST body: 一份结业作品的草稿。"""

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    summary: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)
    repo_url: str | None = Field(default=None, max_length=REPO_URL_MAX_LENGTH)
    run_instructions: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)
    self_checks: list[str] = Field(default_factory=list, description="自检清单，默认空数组")

    _check_repo_url = field_validator("repo_url")(_http_url_or_none)


class CapstoneSubmissionUpdateRequest(BaseModel):
    """PATCH body: 只改请求里出现的字段；其余字段保持原值。"""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX_LENGTH)
    summary: str | None = Field(default=None, min_length=1, max_length=TEXT_MAX_LENGTH)
    repo_url: str | None = Field(default=None, max_length=REPO_URL_MAX_LENGTH)
    run_instructions: str | None = Field(default=None, min_length=1, max_length=TEXT_MAX_LENGTH)
    self_checks: list[str] | None = None

    _check_repo_url = field_validator("repo_url")(_http_url_or_none)

    @model_validator(mode="after")
    def _reject_null_for_not_null_columns(self) -> "CapstoneSubmissionUpdateRequest":
        """显式 null 只对 repo_url 有意义（清空链接）；其余列 NOT NULL，422 而不是 500。"""
        for name in ("title", "summary", "run_instructions", "self_checks"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} 不能为 null")
        return self

    def changes(self) -> dict[str, object]:
        """请求里出现的列及其新值，供服务层拼 SET 子句（列名来自本模型，非用户输入）。"""
        editable = ("title", "summary", "repo_url", "run_instructions", "self_checks")
        return {name: getattr(self, name) for name in editable if name in self.model_fields_set}


class CapstoneReviewRequest(BaseModel):
    """POST /review body：结论只能由本人给出，因此必须显式确认自评。"""

    verdict: Literal["pass", "needs_work"] = Field(description="pass / needs_work")
    note: str | None = Field(default=None, description="本人写给自己的评审说明")
    self_review_confirmed: bool = Field(
        default=False,
        description="必须显式为 true：这条结论是本人对自己作品的评审，不存在第三方评审者",
    )


class CapstoneSubmissionOut(BaseModel):
    """A complete capstone row; the one shape every endpoint returns."""

    id: int
    user_id: int
    title: str
    summary: str
    repo_url: str | None = None
    run_instructions: str
    self_checks: list[str]
    readiness_snapshot: dict[str, Any] | None = Field(
        default=None, description="POST /submit 时写入的四条达标要求快照；草稿为 null"
    )
    status: str = Field(description="draft / submitted / reviewed")
    verdict: str | None = Field(default=None, description="pass / needs_work / null")
    reviewer: str | None = Field(
        default=None, description="恒为 'self'（本人自评）；本版本不存在第三方评审者"
    )
    reviewer_note: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("submitted_at", "reviewed_at", "created_at", "updated_at")
    def _serialize_times(self, value: datetime | None) -> str | None:
        return None if value is None else _iso_z(value)


class CapstoneSubmissionListResponse(BaseModel):
    items: list[CapstoneSubmissionOut]
    total: int = Field(description="当前用户的全部作品数，不受 limit 影响")


__all__ = [
    "CAPSTONE_LIMIT_DEFAULT",
    "CAPSTONE_LIMIT_MAX",
    "REPO_URL_MAX_LENGTH",
    "REVIEWER_SELF",
    "STATUS_DRAFT",
    "STATUS_REVIEWED",
    "STATUS_SUBMITTED",
    "TEXT_MAX_LENGTH",
    "TITLE_MAX_LENGTH",
    "VERDICT_NEEDS_WORK",
    "VERDICT_PASS",
    "CapstoneReviewRequest",
    "CapstoneSubmissionCreateRequest",
    "CapstoneSubmissionListResponse",
    "CapstoneSubmissionOut",
    "CapstoneSubmissionUpdateRequest",
]
