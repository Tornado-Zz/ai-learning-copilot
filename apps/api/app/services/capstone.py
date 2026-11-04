"""Capstone submission: draft -> submitted -> reviewed (v0.1.3, table capstone_submissions).

三态状态机是本模块的全部规则，逐条可测：

S1 创建只产生 draft：submitted_at / verdict / reviewer / reviewed_at 全为 null。
S2 PATCH 只有 draft 可改，其它状态一律 409 CAPSTONE_INVALID_STATE（一个字节都不写）。
S3 POST /submit 是 draft -> submitted，并在**同一事务**里写入 readiness_snapshot 与
   submitted_at。readiness 未达标不拒绝提交：作品可以先交，四条要求的快照记录了
   交的那一刻达标与否，提示由界面负责。
S4 POST /review 是 submitted -> reviewed，写 verdict / reviewer = 'self' /
   reviewer_note / reviewed_at。reviewer 恒为 'self'：本版本是单用户本地应用，
   不存在第三方评审者，请求体里也没有任何字段可以让它取别的值。

诚实性口径不需要应用层"记得"：数据库的
ck_capstone_submissions_reviewed_complete 与 ck_capstone_submissions_reviewer
让"已评审但缺结论 / 缺评审者 / 评审者不是本人"这类行根本写不进去。

调用约束：本模块所有写函数都不 commit。创建 + 提交 + 评审的事务边界属于路由，
与 app.services.review 同一口径。
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    NOT_FOUND,
    ApiError,
    capstone_invalid_state,
    self_review_not_confirmed,
)
from app.schemas.capstone import (
    REVIEWER_SELF,
    STATUS_DRAFT,
    STATUS_SUBMITTED,
    CapstoneReviewRequest,
    CapstoneSubmissionCreateRequest,
    CapstoneSubmissionUpdateRequest,
)
from app.services import progress as progress_service

# 每个端点返回同一份完整对象，列顺序只在这里出现一次。
COLUMNS = """
    id, user_id, title, summary, repo_url, run_instructions, self_checks,
    readiness_snapshot, status, verdict, reviewer, reviewer_note,
    submitted_at, reviewed_at, created_at, updated_at
"""

INSERT_SUBMISSION = text(
    f"""
    INSERT INTO capstone_submissions (
        user_id, title, summary, repo_url, run_instructions, self_checks
    )
    VALUES (
        :user_id, :title, :summary, :repo_url, :run_instructions,
        CAST(:self_checks AS jsonb)
    )
    RETURNING {COLUMNS}
    """
)

SELECT_OWN = text(
    f"""
    SELECT {COLUMNS}
    FROM capstone_submissions
    WHERE id = :submission_id AND user_id = :user_id
    """
)

# 排序口径：created_at DESC, id DESC —— 同一事务里 now() 相同，id 是稳定的第二键。
SELECT_LIST = text(
    f"""
    SELECT {COLUMNS}
    FROM capstone_submissions
    WHERE user_id = :user_id
    ORDER BY created_at DESC, id DESC
    LIMIT CAST(:limit AS integer)
    """
)

COUNT_OWN = text("SELECT count(*) FROM capstone_submissions WHERE user_id = :user_id")

# S3：状态守卫写在 WHERE 里，并发的第二次提交命中 0 行而不是覆盖第一次的快照。
SUBMIT_DRAFT = text(
    f"""
    UPDATE capstone_submissions
    SET status = 'submitted',
        readiness_snapshot = CAST(:readiness_snapshot AS jsonb),
        submitted_at = now(),
        updated_at = now()
    WHERE id = :submission_id AND user_id = :user_id AND status = 'draft'
    RETURNING {COLUMNS}
    """
)

# S4：reviewer 在 SQL 里写死 'self'，请求体无法影响它。
REVIEW_SUBMITTED = text(
    f"""
    UPDATE capstone_submissions
    SET status = 'reviewed',
        verdict = :verdict,
        reviewer = '{REVIEWER_SELF}',
        reviewer_note = :reviewer_note,
        reviewed_at = now(),
        updated_at = now()
    WHERE id = :submission_id AND user_id = :user_id AND status = 'submitted'
    RETURNING {COLUMNS}
    """
)

# PATCH 能改的列就是这五个；片段来自本模块的常量，不是用户输入。
_EDITABLE_ORDER = ("title", "summary", "repo_url", "run_instructions", "self_checks")
_SET_FRAGMENTS = {
    "title": "title = :title",
    "summary": "summary = :summary",
    "repo_url": "repo_url = :repo_url",
    "run_instructions": "run_instructions = :run_instructions",
    "self_checks": "self_checks = CAST(:self_checks AS jsonb)",
}


def _json_value(raw: object) -> Any:
    """Read a JSONB column defensively: a driver may hand back a str or the value."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


def _encode(value: object) -> str:
    """One JSONB parameter encoding for both self_checks and the readiness snapshot."""
    return json.dumps(value, ensure_ascii=False, default=str)


def _payload(row: Mapping[str, Any]) -> dict[str, object]:
    """The one response shape: every column, JSONB decoded, no derived field."""
    self_checks = _json_value(row["self_checks"])
    snapshot = _json_value(row["readiness_snapshot"])
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "repo_url": row["repo_url"],
        "run_instructions": str(row["run_instructions"]),
        "self_checks": [str(item) for item in self_checks]
        if isinstance(self_checks, list)
        else [],
        "readiness_snapshot": snapshot if isinstance(snapshot, dict) else None,
        "status": str(row["status"]),
        "verdict": row["verdict"],
        "reviewer": row["reviewer"],
        "reviewer_note": row["reviewer_note"],
        "submitted_at": row["submitted_at"],
        "reviewed_at": row["reviewed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def _own_row(
    session: AsyncSession, *, user_id: int, submission_id: int
) -> dict[str, object]:
    """The row as this user sees it, or 404: someone else's work does not exist here."""
    row = (
        (
            await session.execute(
                SELECT_OWN, {"submission_id": submission_id, "user_id": user_id}
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ApiError(404, NOT_FOUND, "结业作品不存在，或不属于当前用户")
    return _payload(row)


async def create_submission(
    session: AsyncSession,
    *,
    user_id: int,
    payload: CapstoneSubmissionCreateRequest,
) -> dict[str, object]:
    """POST /capstone/submissions: a new draft. Nothing else can be created directly."""
    row = (
        (
            await session.execute(
                INSERT_SUBMISSION,
                {
                    "user_id": user_id,
                    "title": payload.title,
                    "summary": payload.summary,
                    "repo_url": payload.repo_url,
                    "run_instructions": payload.run_instructions,
                    "self_checks": _encode(payload.self_checks),
                },
            )
        )
        .mappings()
        .one()
    )
    return _payload(row)


async def get_submission(
    session: AsyncSession, *, user_id: int, submission_id: int
) -> dict[str, object]:
    """GET /capstone/submissions/{id}."""
    return await _own_row(session, user_id=user_id, submission_id=submission_id)


async def list_submissions(
    session: AsyncSession, *, user_id: int, limit: int
) -> dict[str, object]:
    """GET /capstone/submissions: created_at DESC, id DESC; total ignores limit."""
    rows = (
        (
            await session.execute(
                SELECT_LIST, {"user_id": user_id, "limit": limit}
            )
        )
        .mappings()
        .all()
    )
    total = int((await session.execute(COUNT_OWN, {"user_id": user_id})).scalar_one())
    return {"items": [_payload(row) for row in rows], "total": total}


async def update_submission(
    session: AsyncSession,
    *,
    user_id: int,
    submission_id: int,
    payload: CapstoneSubmissionUpdateRequest,
) -> dict[str, object]:
    """PATCH /capstone/submissions/{id}: draft only, and only the fields sent."""
    current = await _own_row(session, user_id=user_id, submission_id=submission_id)
    if current["status"] != STATUS_DRAFT:
        raise capstone_invalid_state(str(current["status"]), "update")
    changes = payload.changes()
    if not changes:
        # 空 PATCH 是合法请求：没有任何列要改，返回当前行。
        return current
    assignments = ", ".join(
        _SET_FRAGMENTS[name] for name in _EDITABLE_ORDER if name in changes
    )
    statement = text(
        f"""
        UPDATE capstone_submissions
        SET {assignments}, updated_at = now()
        WHERE id = :submission_id AND user_id = :user_id AND status = 'draft'
        RETURNING {COLUMNS}
        """
    )
    params: dict[str, object] = {
        "submission_id": submission_id,
        "user_id": user_id,
        **{name: value for name, value in changes.items() if name != "self_checks"},
    }
    if "self_checks" in changes:
        params["self_checks"] = _encode(changes["self_checks"])
    row = (await session.execute(statement, params)).mappings().first()
    if row is None:
        # 读与写之间状态被改了：同样是"当前状态不允许该操作"，而不是静默成功。
        raise capstone_invalid_state(str(current["status"]), "update")
    return _payload(row)


async def submit_submission(
    session: AsyncSession, *, user_id: int, submission_id: int
) -> dict[str, object]:
    """POST /capstone/submissions/{id}/submit: draft -> submitted, snapshot in one transaction.

    readiness 未达标不是拒绝理由：四条要求的结果原样写进 readiness_snapshot，
    达标与否由快照记录、由界面提示。快照与状态迁移在同一个事务里落库。
    """
    current = await _own_row(session, user_id=user_id, submission_id=submission_id)
    if current["status"] != STATUS_DRAFT:
        raise capstone_invalid_state(str(current["status"]), "submit")
    # 与 GET /capstone/readiness 同一份计算：两条路径不可能给出不同结论。
    snapshot = await progress_service.read_capstone_readiness(session, user_id)
    row = (
        (
            await session.execute(
                SUBMIT_DRAFT,
                {
                    "submission_id": submission_id,
                    "user_id": user_id,
                    "readiness_snapshot": _encode(snapshot),
                },
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise capstone_invalid_state(str(current["status"]), "submit")
    return _payload(row)


async def review_submission(
    session: AsyncSession,
    *,
    user_id: int,
    submission_id: int,
    payload: CapstoneReviewRequest,
) -> dict[str, object]:
    """POST /capstone/submissions/{id}/review: submitted -> reviewed, always a self-review.

    确认位先于状态校验：没有 self_review_confirmed = true 的请求不进入状态机，
    也就不会因为状态不同而得到两种错误码。
    """
    current = await _own_row(session, user_id=user_id, submission_id=submission_id)
    if payload.self_review_confirmed is not True:
        raise self_review_not_confirmed()
    if current["status"] != STATUS_SUBMITTED:
        raise capstone_invalid_state(str(current["status"]), "review")
    row = (
        (
            await session.execute(
                REVIEW_SUBMITTED,
                {
                    "submission_id": submission_id,
                    "user_id": user_id,
                    "verdict": payload.verdict,
                    "reviewer_note": payload.note,
                },
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise capstone_invalid_state(str(current["status"]), "review")
    return _payload(row)


__all__ = [
    "create_submission",
    "get_submission",
    "list_submissions",
    "review_submission",
    "submit_submission",
    "update_submission",
]
