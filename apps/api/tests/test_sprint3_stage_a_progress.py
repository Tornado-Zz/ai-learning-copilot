"""Sprint 3 阶段 A 的课程进度回归用例：周限定同步（A1）与并发单调（A2）。

隔离策略沿用既有集成用例：所有写入都发生在 conftest.db_session 的外层事务里，
测试结束整体回滚，断言全部按本测试自建的 user_id 限定；全程不执行 DELETE /
TRUNCATE / DROP，真实用户数据一行都不改。

A2 的并发用例只能在这一个事务里制造竞态：同一 (user_id, lesson_id) 的两次写入
必须互相可见，而任何提交都会永久污染真实库。于是两个「请求」是两个独立
AsyncSession，绑定到测试自己的连接、加入同一个外层事务（见 _JoinedSession），
由 asyncio.gather 并发执行——落败的一方只有数据库层的 WHERE 能拦住。
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import COURSE_PROGRESS_REGRESSION, ApiError
from app.schemas.lessons import LessonProgressUpdateRequest
from app.services import lessons as lessons_service

pytestmark = pytest.mark.integration


class _JoinedSession(AsyncSession):
    """加入测试外层事务的 session（A2 并发用例专用）。

    rollback_only 让兄弟 session 自己不开 SAVEPOINT，再把事务边界改成空操作：
    写入本来就活在外层事务里，由 db_session 统一回滚。若沿用默认的
    create_savepoint，两个并发 session 会在同一连接上互相释放对方的 SAVEPOINT，
    而那正是 testonly 的假故障，不是被测行为。
    """

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


SELECT_OTHER_LESSON = text(
    "SELECT id FROM lessons WHERE status = 'published' AND deleted_at IS NULL "
    "AND id <> :lesson_id ORDER BY stage, order_index, id LIMIT 1"
)
SELECT_WEEK_START = text(
    "SELECT (date_trunc('week', now() AT TIME ZONE :timezone))::date"
)
SELECT_PUBLISHED_LESSON = text(
    "SELECT id FROM lessons WHERE status = 'published' AND deleted_at IS NULL "
    "ORDER BY stage, order_index, id LIMIT 1"
)
INSERT_PLAN_ITEM = text(
    """
    INSERT INTO study_plan_items (
        user_id, week_start, plan_date, kind, target_id, planned_minutes,
        status, rationale, dedupe_key
    )
    VALUES (
        :user_id, :week_start, :plan_date, 'lesson', :target_id, :planned_minutes,
        'scheduled', :rationale, :dedupe_key
    )
    RETURNING id
    """
)
SELECT_PLAN_STATUS = text(
    "SELECT id, status FROM study_plan_items WHERE user_id = :user_id AND id = ANY(:ids)"
)
SELECT_PROGRESS = text(
    """
    SELECT status, self_assessment, progress_pct, time_spent_seconds,
           started_at, completed_at, updated_at
    FROM learning_progress
    WHERE user_id = :user_id AND lesson_id = :lesson_id
    """
)
COUNT_PROGRESS = text(
    "SELECT count(*) FROM learning_progress WHERE user_id = :user_id"
)


async def _published_lesson(session: AsyncSession) -> int:
    return int((await session.execute(SELECT_PUBLISHED_LESSON)).scalar_one())


async def _published_lesson_after(session: AsyncSession, lesson_id: int) -> int:
    """同一 seed 里的另一门已发布课程，用来再跑一次反序并发。"""
    return int((await session.execute(SELECT_OTHER_LESSON, {"lesson_id": lesson_id})).scalar_one())


async def _timezone(session: AsyncSession, user_id: int) -> str:
    # 用服务自己的常量读时区：本周一必须和被测代码认定的是同一周。
    return str(
        (
            await session.execute(
                lessons_service.SELECT_USER_TIMEZONE, {"user_id": user_id}
            )
        ).scalar_one()
    )


async def _monday(session: AsyncSession, timezone_name: str) -> date:
    return (await session.execute(SELECT_WEEK_START, {"timezone": timezone_name})).scalar_one()


async def _plan_item(
    session: AsyncSession,
    user_id: int,
    week_start: date,
    plan_date: date,
    lesson_id: int,
) -> int:
    """一条 scheduled 计划项；dedupe_key 与 DATABASE.md 4.14 同构。"""
    return int(
        (
            await session.execute(
                INSERT_PLAN_ITEM,
                {
                    "user_id": user_id,
                    "week_start": week_start,
                    "plan_date": plan_date,
                    "target_id": lesson_id,
                    "planned_minutes": 20,
                    "rationale": f"pytest 计划项 {plan_date.isoformat()}",
                    "dedupe_key": (
                        f"{week_start.isoformat()}|{plan_date.isoformat()}|lesson|{lesson_id}"
                    ),
                },
            )
        ).scalar_one()
    )


async def _plan_statuses(
    session: AsyncSession, user_id: int, item_ids: list[int]
) -> dict[int, str]:
    rows = (
        await session.execute(SELECT_PLAN_STATUS, {"user_id": user_id, "ids": item_ids})
    ).mappings().all()
    return {int(row["id"]): str(row["status"]) for row in rows}


async def _progress(
    session: AsyncSession, user_id: int, lesson_id: int
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                SELECT_PROGRESS, {"user_id": user_id, "lesson_id": lesson_id}
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _upsert_params(
    user_id: int, lesson_id: int, status: str, progress_pct: int
) -> dict[str, object]:
    """服务里 save_progress 组装的参数，原样交给同一条 UPSERT。"""
    return {
        "user_id": user_id,
        "lesson_id": lesson_id,
        "status": status,
        "self_assessment": 0,
        "progress_pct": progress_pct,
        "time_spent_seconds": 0,
        "started_now": status != "not_started",
        "completed_now": status == "completed",
    }


async def _save(
    session: AsyncSession, user_id: int, lesson_id: int, status: str
) -> dict[str, Any]:
    """跑一次真实的服务调用：成功返回 200 载荷，被拒返回 ApiError 摘要。"""
    try:
        body = await lessons_service.save_progress(
            session, user_id, lesson_id, LessonProgressUpdateRequest(status=status)
        )
        return {"status_code": 200, "body": body}
    except ApiError as exc:
        return {"status_code": exc.status_code, "code": exc.code, "details": exc.details}

async def test_a1_completing_a_lesson_settles_only_the_current_weeks_plan_item(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    """① 上周 + 本周同一课程都是 scheduled：完成后只有本周变 done，上周原样。"""
    user_id = int(test_user["id"])
    lesson_id = await _published_lesson(db_session)
    timezone_name = await _timezone(db_session, user_id)
    monday = await _monday(db_session, timezone_name)
    last_monday = monday - timedelta(days=7)
    next_monday = monday + timedelta(days=7)
    current = await _plan_item(db_session, user_id, monday, monday, lesson_id)
    previous = await _plan_item(
        db_session, user_id, last_monday, last_monday + timedelta(days=2), lesson_id
    )
    following = await _plan_item(db_session, user_id, next_monday, next_monday, lesson_id)
    before = await _plan_statuses(db_session, user_id, [current, previous, following])
    assert set(before.values()) == {"scheduled"}

    result = await lessons_service.save_progress(
        db_session, user_id, lesson_id, LessonProgressUpdateRequest(status="completed")
    )

    after = await _plan_statuses(db_session, user_id, [current, previous, following])
    assert result["status"] == "completed"
    assert result["plan_items_completed"] == 1, "只有本周那一行允许被同步"
    assert after[current] == "done", "本周 scheduled 行必须变 done"
    assert after[previous] == "scheduled", "上周的 scheduled 行不得被顺手置 done"
    assert after[following] == "scheduled", "下周的 scheduled 行同样不动"
    print(
        f"A1 周限定: 本周 {current}=done 上周 {previous}=scheduled "
        f"下周 {following}=scheduled timezone={timezone_name} monday={monday} "
        f"plan_items_completed={result['plan_items_completed']}"
    )


async def test_a2_concurrent_requests_never_regress(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    """② asyncio.gather 两个独立 session：in_progress 与 completed 抢同一行。"""
    user_id = int(test_user["id"])
    lesson_id = await _published_lesson(db_session)
    other_lesson = await _published_lesson_after(db_session, lesson_id)

    def _sibling() -> AsyncSession:
        # 绑定到测试自己的连接：两个独立 session 共享同一个外层事务，
        # 这样它们才能看见彼此对同一行的未提交写入（真实竞态的唯一复现方式）。
        return _JoinedSession(
            bind=db_session.bind,
            expire_on_commit=False,
            join_transaction_mode="rollback_only",
        )

    async def _request(status: str, target: int) -> dict[str, Any]:
        return await _save(_sibling(), user_id, target, status)

    # 两门课各跑一次并发，任务创建顺序相反：asyncio.gather 的完成顺序不可控，
    # 但两种交错都必须收敛到 completed，且落败方拿 422 而不是覆盖。
    early_start, late_start = await asyncio.gather(
        _request("in_progress", lesson_id),
        _request("completed", lesson_id),
    )
    first_settled, then_started = await asyncio.gather(
        _request("completed", other_lesson),
        _request("in_progress", other_lesson),
    )

    stored = await _progress(db_session, user_id, lesson_id)
    assert stored is not None
    assert stored["status"] == "completed", "并发结束后状态不得倒退"
    assert int(stored["progress_pct"]) == 100, "progress_pct 必须是 GREATEST 的结果"
    assert stored["started_at"] is not None
    assert stored["completed_at"] is not None, "completed 行必须带 completed_at"
    assert late_start["status_code"] == 200, "completed 请求必须落地"
    assert late_start["body"]["status"] == "completed"
    assert early_start["status_code"] in (200, 422), early_start
    if early_start["status_code"] == 422:
        assert early_start["code"] == COURSE_PROGRESS_REGRESSION
        assert early_start["details"]["current_status"] == "completed"

    stored_other = await _progress(db_session, user_id, other_lesson)
    assert stored_other is not None
    assert stored_other["status"] == "completed", "反序并发同样不得倒退"
    assert int(stored_other["progress_pct"]) == 100
    assert stored_other["completed_at"] is not None
    assert first_settled["status_code"] == 200
    assert then_started["status_code"] in (200, 422), then_started
    if then_started["status_code"] == 422:
        assert then_started["code"] == COURSE_PROGRESS_REGRESSION
    assert {
        early_start["status_code"],
        then_started["status_code"],
    } <= {200, 422}

    # 竞态窗口的确定性复现：拿掉服务层预检，直接再发一次回退写入。
    refused = await db_session.execute(
        lessons_service.UPSERT_PROGRESS,
        _upsert_params(user_id, lesson_id, "in_progress", 1),
    )
    assert refused.mappings().first() is None, "WHERE 不成立时 RETURNING 必须为空"
    assert await _progress(db_session, user_id, lesson_id) == stored, "回退必须零写入"
    print(
        f"A2 并发: [先 in_progress] in_progress={early_start['status_code']} "
        f"completed={late_start['status_code']} 终态 {stored['status']}/"
        f"{stored['progress_pct']} completed_at={stored['completed_at'] is not None} | "
        f"[先 completed] completed={first_settled['status_code']} "
        f"in_progress={then_started['status_code']} 终态 {stored_other['status']}/"
        f"{stored_other['progress_pct']} | 绕过预检再写 in_progress -> RETURNING 空且行不变"
    )


async def test_a2_completed_to_in_progress_is_422_with_zero_writes(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    """③ completed -> in_progress 仍是 422，且服务层与数据库层都零写入。"""
    user_id = int(test_user["id"])
    lesson_id = await _published_lesson(db_session)
    assert (await _save(db_session, user_id, lesson_id, "in_progress"))["status_code"] == 200
    assert (await _save(db_session, user_id, lesson_id, "completed"))["status_code"] == 200
    snapshot = await _progress(db_session, user_id, lesson_id)
    assert snapshot is not None and snapshot["status"] == "completed"

    refused = await _save(db_session, user_id, lesson_id, "in_progress")
    assert refused["status_code"] == 422, refused
    assert refused["code"] == COURSE_PROGRESS_REGRESSION
    assert refused["details"]["field"] == "status"
    assert refused["details"]["reason"] == "course_progress_regression"
    assert refused["details"]["current_status"] == "completed"
    assert refused["details"]["requested_status"] == "in_progress"
    assert await _progress(db_session, user_id, lesson_id) == snapshot, (
        "服务层拒绝必须零写入（updated_at 都不能变）"
    )

    # 绕过服务层预检：条件更新自己兜底，同样一行都不写。
    bypass = await db_session.execute(
        lessons_service.UPSERT_PROGRESS,
        _upsert_params(user_id, lesson_id, "in_progress", 1),
    )
    assert bypass.mappings().first() is None, "ON CONFLICT 的 WHERE 不成立时必须为空"
    assert await _progress(db_session, user_id, lesson_id) == snapshot
    print(
        f"A2 回退: completed->in_progress 服务层 422 {refused['code']} "
        f"数据库层 RETURNING 空 行不变 status={snapshot['status']} "
        f"pct={snapshot['progress_pct']} updated_at 稳定"
    )


async def test_a2_repeating_the_same_status_is_idempotent_200(
    db_session: AsyncSession, test_user: dict[str, object]
) -> None:
    """④ 同状态重复提交是幂等 200：时间戳不自相矛盾，也不新增行。"""
    user_id = int(test_user["id"])
    lesson_id = await _published_lesson(db_session)
    timezone_name = await _timezone(db_session, user_id)
    monday = await _monday(db_session, timezone_name)
    item = await _plan_item(db_session, user_id, monday, monday, lesson_id)
    progress_rows_before = int(
        (await db_session.execute(COUNT_PROGRESS, {"user_id": user_id})).scalar_one()
    )

    assert (await _save(db_session, user_id, lesson_id, "in_progress"))["status_code"] == 200
    first = await _save(db_session, user_id, lesson_id, "completed")
    assert first["status_code"] == 200, first
    repeat = await _save(db_session, user_id, lesson_id, "completed")
    assert repeat["status_code"] == 200, repeat

    body_first = first["body"]
    body_repeat = repeat["body"]
    assert body_repeat["status"] == "completed"
    assert body_repeat["progress_pct"] == 100
    assert body_repeat["completed_at"] == body_first["completed_at"], (
        "COALESCE 必须保住第一次的 completed_at"
    )
    assert body_repeat["started_at"] == body_first["started_at"]
    assert body_first["plan_items_completed"] == 1, "第一次完成同步本周计划项"
    assert body_repeat["plan_items_completed"] == 0, "重复提交没有可同步的行"
    assert await _plan_statuses(db_session, user_id, [item]) == {item: "done"}
    assert int(
        (await db_session.execute(COUNT_PROGRESS, {"user_id": user_id})).scalar_one()
    ) == progress_rows_before + 1, "幂等重复不得新增行"
    print(
        f"A2 幂等: 重复 completed 200 pct={body_repeat['progress_pct']} "
        f"completed_at 不变={body_repeat['completed_at'] == body_first['completed_at']} "
        f"plan_items_completed={body_first['plan_items_completed']}->"
        f"{body_repeat['plan_items_completed']} 行数 {progress_rows_before}->"
        f"{progress_rows_before + 1}"
    )
